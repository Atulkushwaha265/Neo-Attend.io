from database.mysql_connection import get_db
from datetime import date, datetime

db = get_db()
cursor = db.cursor(buffered=True)

today = date.today()
print(f'Checking attendance sessions for: {today}')

cursor.execute('''
    SELECT section_id, is_locked, start_time, end_time, attend_date
    FROM attendance_session 
    WHERE attend_date = %s
    ORDER BY section_id
''', (today,))

sessions = cursor.fetchall()

if sessions:
    print(f'\n📊 Today\'s Attendance Sessions:')
    for session in sessions:
        section_id, is_locked, start_time, end_time, attend_date = session
        status = 'LOCKED' if is_locked else 'OPEN'
        
        print(f'Section {section_id}:')
        print(f'  Status: {status}')
        print(f'  Start Time: {start_time}')
        
        if end_time:
            print(f'  End Time: {end_time}')
        else:
            print(f'  End Time: Not closed yet')
        
        print(f'  Date: {attend_date}')
        print()
else:
    print('❌ No attendance sessions found for today!')

cursor.close()
db.close()
