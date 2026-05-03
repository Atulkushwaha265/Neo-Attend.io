import mysql.connector
from datetime import date, datetime

# Connect to database
conn = mysql.connector.connect(
    host="localhost",
    user="root",
    password="#@wj$12#atul",
    database="neoattend"
)
cursor = conn.cursor()

# Open attendance session for today
today = date.today()
now = datetime.now().time()

# Insert or update attendance session
cursor.execute("""
    INSERT INTO attendance_session (section_id, attend_date, is_locked, start_time)
    VALUES (1, %s, 0, %s)
    ON DUPLICATE KEY UPDATE
        is_locked = 0,
        start_time = %s,
        end_time = NULL
""", (1, today, now, now))

conn.commit()

print(f"✅ Attendance session opened for Section 1 on {today}")
print(f"Session started at: {now}")

cursor.close()
conn.close()
