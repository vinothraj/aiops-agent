import sqlite3
import os

db_path = "aiops_dev.db"
conn = sqlite3.connect(db_path)
cur = conn.cursor()

# DB size
size = os.path.getsize(db_path)
print(f"Database file : {db_path}")
print(f"Database size : {size / 1024 / 1024:.2f} MB")
print()

# Tables
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [t[0] for t in cur.fetchall()]
print(f"Tables        : {tables}")
print()

# Row counts
cur.execute("SELECT COUNT(*) FROM logs")
total_logs = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM log_files")
total_files = cur.fetchone()[0]
print(f"Rows in logs      : {total_logs:,}")
print(f"Rows in log_files : {total_files}")
print()

# Breakdown by service + log level
cur.execute("""
    SELECT service_name, log_level, COUNT(*)
    FROM logs
    GROUP BY service_name, log_level
    ORDER BY service_name, log_level
""")
rows = cur.fetchall()
print("Breakdown by service + level:")
for r in rows:
    print(f"  {r[0]:<30} | {r[1]:<8} | {r[2]:,} rows")

print()

# Log files tracked
cur.execute("SELECT file_name, status, last_processed_position, last_processed_time FROM log_files")
files = cur.fetchall()
print("Tracked log files:")
for f in files:
    print(f"  {f[0]:<35} | status={f[1]:<12} | bytes={f[2]:,} | last={f[3]}")

# Sample recent log entry
print()
cur.execute("SELECT id, timestamp, service_name, log_level, message FROM logs ORDER BY id DESC LIMIT 3")
recent = cur.fetchall()
print("3 most recent log entries:")
for r in recent:
    print(f"  [{r[0]}] {r[1]} | {r[2]} | {r[3]} | {r[4][:80]}...")

conn.close()
