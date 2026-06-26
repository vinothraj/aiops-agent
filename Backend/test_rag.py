import requests

payload = {
    "title": "Incident #120: Database Timeout",
    "content": "Database timeout observed due to exhausted connection pool. Resolution: Increase Hikari Pool Size from 20 to 50 in configuration.",
    "doc_type": "INCIDENT",
    "source_id": "120"
}

try:
    response = requests.post("http://localhost:8000/api/knowledge/ingest", json=payload)
    print("Ingest Status Code:", response.status_code)
    print("Ingest Response:", response.text)
except Exception as e:
    print("Failed to call ingest API:", e)
