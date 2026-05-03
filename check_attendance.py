import mysql.connector
from datetime import date

# Connect to database
conn = mysql.connector.connect(
    host="localhost",
    user="root",
    password="#@wj$12#atul",
    database="neoattend"
)
cursor = conn.cursor()

# Check today's attendance
today = date.today()
print(f"Checking attendance for: {today}")

# Check attendance session status
cursor.execute("""
    SELECT section_id, is_locked, start_time, end_time 
    FROM attendance_session 
    WHERE attend_date = %s
""", (today,))
sessions = cursor.fetchall()
print(f"\nAttendance Sessions:")
for session in sessions:
    print(f"Section: {session[0]}, Locked: {session[1]}, Start: {session[2]}, End: {session[3]}")

# Check today's attendance records
cursor.execute("""
    SELECT a.student_id, s.name, s.roll_no, a.attend_time, a.status, sec.section_name
    FROM attendance a
    JOIN students s ON a.student_id = s.id
    JOIN sections sec ON s.section_id = sec.section_id
    WHERE a.attend_date = %s
    ORDER BY a.attend_time
""", (today,))
attendance = cursor.fetchall()
print(f"\nToday's Attendance Records:")
for record in attendance:
    print(f"Student: {record[1]} ({record[2]}), Section: {record[5]}, Time: {record[3]}, Status: {record[4]}")

# Check if attendance session needs to be opened
if not sessions:
    print("\n⚠️ No attendance session found for today!")
    print("You need to open attendance session first.")
else:
    for session in sessions:
        if session[1] == 1:  # is_locked
            print(f"\n⚠️ Section {session[0]} attendance is LOCKED!")
        else:
            print(f"\n✅ Section {session[0]} attendance is OPEN")

cursor.close()
conn.close()
