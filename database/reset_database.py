#!/usr/bin/env python3
"""
PostgreSQL Database Reset Script for NeoAttend
Safely removes all data while preserving table structure
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

def reset_database():
    """Reset all data while preserving structure"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        print("🔄 Starting database reset...")
        print("=" * 50)
        
        # Disable foreign key constraints temporarily
        cursor.execute("SET session_replication_role = replica;")
        
        # Reset sequences (auto-increment counters)
        print("📊 Resetting auto-increment counters...")
        sequences = [
            'teachers_id_seq',
            'sections_section_id_seq', 
            'students_id_seq',
            'attendance_session_session_id_seq',
            'attendance_id_seq'
        ]
        
        for seq in sequences:
            try:
                cursor.execute(f"ALTER SEQUENCE {seq} RESTART WITH 1;")
                print(f"  ✅ Reset sequence: {seq}")
            except Exception as e:
                print(f"  ⚠️  Sequence {seq} not found or already reset: {e}")
        
        # Truncate all tables (delete data, reset auto-increment)
        tables_to_reset = [
            'attendance',           # Child table first
            'attendance_session',   # Child table
            'students',           # Child table
            'teachers',           # Parent table
            'sections'            # Parent table
        ]
        
        print("\n🗑️  Truncating tables...")
        for table in tables_to_reset:
            try:
                cursor.execute(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE;")
                print(f"  ✅ Truncated: {table}")
            except Exception as e:
                print(f"  ❌ Error truncating {table}: {e}")
        
        # Re-enable foreign key constraints
        cursor.execute("SET session_replication_role = DEFAULT;")
        
        # Insert default data
        print("\n📝 Inserting default data...")
        
        # Default sections
        cursor.execute("""
            INSERT INTO sections (section_name) VALUES 
            ('Section A'), ('Section B'), ('Section C')
            ON CONFLICT (section_name) DO NOTHING
        """)
        print("  ✅ Inserted default sections")
        
        # Default admin user
        from werkzeug.security import generate_password_hash
        cursor.execute("""
            INSERT INTO teachers (name, email, password, role) VALUES 
            ('Admin', 'admin@neoattend.com', %s, 'admin')
            ON CONFLICT (email) DO NOTHING
        """, (generate_password_hash('admin123'),))
        print("  ✅ Inserted default admin")
        
        # Commit all changes
        conn.commit()
        cursor.close()
        conn.close()
        
        print("\n🎉 Database reset completed successfully!")
        print("=" * 50)
        
        # Verification
        verify_database_empty()
        
        return True
        
    except Exception as e:
        print(f"❌ Error resetting database: {e}")
        return False

def verify_database_empty():
    """Verify that database is properly reset"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        print("\n🔍 Verifying database state...")
        
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
            status = "✅ Empty" if count == 0 else f"❌ {count} records"
            print(f"  {table}: {status}")
        
        # Check specific expected data
        cursor.execute("SELECT COUNT(*) FROM sections WHERE section_name LIKE 'Section %'")
        section_count = cursor.fetchone()[0]
        print(f"  Default sections: {section_count} (expected: 3)")
        
        cursor.execute("SELECT COUNT(*) FROM teachers WHERE email = 'admin@neoattend.com'")
        admin_count = cursor.fetchone()[0]
        print(f"  Default admin: {admin_count} (expected: 1)")
        
        cursor.close()
        conn.close()
        
        print("\n✅ Database verification completed!")
        
    except Exception as e:
        print(f"❌ Error verifying database: {e}")

def main():
    print("🚀 NeoAttend Database Reset")
    print("=" * 50)
    print("⚠️  WARNING: This will delete ALL data!")
    print("📋 Tables to be reset:")
    print("   - teachers")
    print("   - sections") 
    print("   - students")
    print("   - attendance_session")
    print("   - attendance")
    print("=" * 50)
    
    # Confirm before proceeding
    confirm = input("Type 'RESET' to confirm: ")
    if confirm.upper() != 'RESET':
        print("❌ Reset cancelled!")
        return
    
    print("\n🔄 Proceeding with reset...")
    
    if reset_database():
        print("\n🎯 Next steps:")
        print("1. Restart your Flask application")
        print("2. Register new students")
        print("3. Start taking attendance")
        print("\n🌐 Your app is ready for fresh start!")
    else:
        print("\n❌ Database reset failed!")

if __name__ == "__main__":
    main()
