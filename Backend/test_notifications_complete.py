import sys
import os
from datetime import datetime

# Add app to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database.session import SessionLocal
from app.models.models import Log, LogAnalysis, IncidentDecision, Notification, NotificationRecipient
from app.services.triage.triage_engine import triage_engine
from app.services.notification.notification_agent import notification_agent

def run_test():
    db = SessionLocal()
    try:
        print("=== Phase 7 Notification & Collaboration Verification ===")
        
        # 1. Bootstrap recipients
        print("Bootstrapping default routing recipients...")
        recipients = notification_agent._get_recipients(db, "DEFAULT")
        print(f"Loaded {len(recipients)} default recipients.")
        for r in recipients:
            print(f" - Recipient: {r.recipient_name}, Channel: {r.channel}, Destination: {r.destination}, Category: {r.category}")
            
        # 2. Check if we need to create a test log & analysis or use an existing one
        # Let's search for an existing log of severity ERROR or FATAL
        log = db.query(Log).filter(Log.log_level.in_(["ERROR", "FATAL"])).first()
        if not log:
            print("No existing ERROR/FATAL logs found. Creating a mock log...")
            log = Log(
                timestamp=datetime.utcnow(),
                service_name="payment-service",
                log_level="FATAL",
                message="Database connection pool exhausted. Unable to checkout client session.",
                file_name="connection.go",
                file_path="/src/db/connection.go"
            )
            db.add(log)
            db.commit()
            db.refresh(log)
        
        print(f"Using Log ID: {log.id} ({log.service_name} - {log.log_level})")
        
        # Find or create a LogAnalysis
        analysis = db.query(LogAnalysis).filter(LogAnalysis.log_id == log.id).first()
        if not analysis:
            print("Creating mock LogAnalysis...")
            analysis = LogAnalysis(
                log_id=log.id,
                root_cause="Database connection pool size limits reached under high concurrent volume.",
                root_cause_category="DATABASE",
                severity="P1 Critical",
                confidence_score=0.92,
                recommendation="Increase DB connection pool maximum bounds in deployment spec and add load-shedding middle tier.",
                summary="Payment service database connection starvation causing client transaction failure."
            )
            db.add(analysis)
            db.commit()
            db.refresh(analysis)
            
        print(f"Using Analysis ID: {analysis.id} (Category: {analysis.root_cause_category})")
        
        # 3. Trigger Triage & Escalation & Notification
        print("\nTriggering Triage and Notification flow via triage_engine...")
        decision = triage_engine.triage(db=db, log_id=log.id, analysis_id=analysis.id)
        
        print("\nTriage Decision Output:")
        print(f" - Decision ID: {decision.id}")
        print(f" - Assigned Priority: {decision.priority}")
        print(f" - Action Recommended: {decision.recommended_action}")
        print(f" - GitLab Issue ID: {decision.gitlab_issue_id}")
        
        # 4. Check for generated notifications
        print("\nChecking generated notifications for this decision...")
        notifications = db.query(Notification).filter(Notification.incident_decision_id == decision.id).all()
        print(f"Generated {len(notifications)} notifications:")
        for n in notifications:
            print(f" - Notification ID {n.id} [{n.channel} to {n.recipient_destination}]: Status = {n.status}")
            if n.error_message:
                print(f"   Error: {n.error_message}")
                
        # 5. Check timeline retrieval
        print("\nRetrieving incident chronological timeline...")
        from app.api.endpoints.notifications import get_incident_timeline
        timeline_events = get_incident_timeline(incident_id=decision.id, db=db)
        print(f"Timeline contains {len(timeline_events)} events:")
        for idx, event in enumerate(timeline_events):
            print(f" {idx + 1}. [{event.event_type}] {event.title} - {event.description} ({event.status})")
            
        print("\nVerification Test Completed Successfully!")
        
    except Exception as e:
        print("\nVerification failed with exception:")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    run_test()
