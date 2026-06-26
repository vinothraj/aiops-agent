# Future Notification Architecture Design

## Objective
To decouple the Incident Triage Engine from downstream notification consumers (GitLab, Microsoft Teams, Email, Slack, etc.) ensuring that the core engine remains fast, reliable, and unaware of specific notification channels.

## Proposed Architecture: Event-Driven Publisher/Subscriber Model

Currently, the Triage Engine directly calls the `gitlab_agent` synchronously. As we add more notification agents (Teams, Email), calling them sequentially will increase latency and error rates.

### 1. Event Bus / Message Broker
We should implement an internal Event Bus or utilize an external message broker (like RabbitMQ, Redis Pub/Sub, or Kafka depending on enterprise scale). 

### 2. Event Definition
When an incident is classified as actionable (e.g., `CREATE_INCIDENT` or `IMMEDIATE_ESCALATION`), the Triage Engine will publish an event:
```json
{
  "event_type": "incident.actionable",
  "decision_id": 123,
  "priority": "P1",
  "action": "IMMEDIATE_ESCALATION",
  "timestamp": "2026-06-11T12:00:00Z"
}
```

### 3. Subscribing Agents
Each notification agent will act as an independent worker or subscriber listening for `incident.actionable` events:

- **GitLab Agent**: Listens for the event, fetches the `IncidentDecision` from the database, and creates the GitLab issue.
- **Teams Agent**: Listens for the event, formats a Microsoft Teams Adaptive Card, and sends it to the designated webhook.
- **Email Agent**: Listens for the event, generates an HTML template, and sends emails to the on-call engineers via SMTP.

### 4. Benefits
- **Fault Tolerance**: If the GitLab API is down, it won't prevent the Teams alert from being sent.
- **Scalability**: New notification channels can be added by simply subscribing to the event bus without modifying the Triage Engine code.
- **Asynchronous Processing**: The Triage Engine can return a response to the caller immediately after publishing the event, rather than waiting for 3rd party APIs.
