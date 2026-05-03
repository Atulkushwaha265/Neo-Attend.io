#!/usr/bin/env python3
"""
Check current database state
"""

import psycopg2
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def get_db():
    """Get PostgreSQL database connection"""
    try:
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            database=os.getenv('DB_NAME', 'neoattend'),
            user=os.getenv('DB_USER', 'postgres'),
            password=os.getenv('DB_PASSWORD', ''),
            port=os.getenv('DB_PORT', '5432')
        )
        return conn
    except Exception as e:
        print(f"Database connection error: {e}")
        raise e

def check_database():
    """Check current database state"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        print("🔍 Current Database State")
        print("=" * 40)
        
        # Check table counts
        tables = {
            'teachers': 'SELECT COUNT(*) FROM teachers;',
            'sections': 'SELECT COUNT(*) FROM sections;', 
            'students': 'SELECT COUNT(*) FROM students;',
            'attendance_session': 'SELECT COUNT(*) FROM attendance_session;',
            'attendance': 'SELECT COUNT(*) FROM attendance;'
        }
        
        for table, query in tables.items():
            cursor.execute(query)
            count = cursor.fetchone()[0]
            print(f"  {table:15s}: {count:5d} records")
        
        # Check next IDs
        print("\n📊 Next Auto-Increment Values:")
        sequences = [
            ('teachers_id_seq', 'teachers'),
            ('sections_section_id_seq', 'sections'),
            ('students_id_seq', 'students'), 
            ('attendance_session_session_id_seq', 'attendance_session'),
            ('attendance_id_seq', 'attendance')
        ]
        
        for seq, table in sequences:
            try:
                cursor.execute(f"SELECT last_value FROM {seq}")
                last_val = cursor.fetchone()[0]
                print(f"  {table:20s}: {last_val}")
            except:
                print(f"  {table:20s}: 1 (default)")
        
        # Check for any students
        cursor.execute("SELECT name, roll_no FROM students LIMIT 3")
        students = cursor.fetchall()
        
        if students:
            print("\n👥 Sample Students:")
            for student in students:
                print(f"  - {student[0]} ({student[1]})")
        else:
            print("\n👥 No students found")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Error checking database: {e}")

if __name__ == "__main__":
    check_database()
