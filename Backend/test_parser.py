import os
import sys
from datetime import datetime

# Add Backend folder to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database.session import Base
from app.models.models import LogFile, Log
from app.schemas.schemas import LogFileCreate, LogFileUpdate
from app.services.parser import LogParser
from app.repositories.repositories import log_file_repo, log_repo

def run_test():
    print("Starting parser validation test...")
    
    # 1. Create a local SQLite database for verification
    db_path = "test_aiops.db"
    if os.path.exists(db_path):
        os.remove(db_path)
        
    engine = create_engine(f"sqlite:///{db_path}")
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    print("Creating tables in SQLite...")
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    
    # 2. Path to log file
    log_file_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Logs", "ecommerce-site.log")
    print(f"Loading log file: {log_file_path}")
    if not os.path.exists(log_file_path):
        print(f"Error: Log file not found at {log_file_path}!")
        return False
        
    # Read first 500 lines for validation
    with open(log_file_path, "r", encoding="utf-8", errors="replace") as f:
        lines = [f.readline() for _ in range(500)]
    
    # 3. Ingest Log File Record
    file_name = os.path.basename(log_file_path)
    db_file = log_file_repo.create(
        db,
        LogFileCreate(
            file_name=file_name,
            file_path=log_file_path,
            service_name="ecommerce-site",
            last_processed_position=0,
            status="processing"
        )
    )
    print(f"Created LogFile record: ID={db_file.id}, Service={db_file.service_name}")
    
    # 4. Parse lines
    parser = LogParser()
    parsed_logs = parser.parse_lines(lines, file_name, log_file_path)
    print(f"Successfully parsed {len(parsed_logs)} log records (with multiline stacktrace grouping).")
    
    if len(parsed_logs) == 0:
        print("Error: No logs parsed. Check regex matching rules!")
        return False
        
    # 5. Save logs
    db_logs = log_repo.create_many(db, parsed_logs)
    print(f"Ingested {len(db_logs)} records into database.")
    
    # Update LogFile status
    log_file_repo.update(
        db,
        db_file,
        LogFileUpdate(
            last_processed_position=1024, # dummy position
            last_processed_time=datetime.utcnow(),
            status="completed"
        )
    )
    
    # 6. Retrieve statistics summary
    stats = log_repo.get_stats_summary(db)
    print(f"Stats summary: {stats}")
    
    # Assertions
    assert stats["total_logs"] > 0, "No logs recorded in stats!"
    assert stats["error_logs"] > 0, "No error logs parsed!"
    assert stats["services"] == 1, "Incorrect service count!"
    
    # Retrieve some log entries
    all_logs = log_repo.get_all(db, limit=5)
    print("\nSample logs retrieved:")
    for log in all_logs:
        print(f"[{log.timestamp}] {log.log_level} in {log.service_name}: {log.message[:60]}...")
        if log.stacktrace:
            print(f"   [Stacktrace]: {log.stacktrace[:100]}...")
            
    print("\nAll assertions passed successfully!")
    db.close()
    engine.dispose()
    
    # Clean up
    if os.path.exists(db_path):
        os.remove(db_path)
    return True

if __name__ == "__main__":
    success = run_test()
    sys.exit(0 if success else 1)
