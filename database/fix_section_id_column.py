import mysql.connector
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.mysql_connection import get_db

def add_section_id_column():
    """Add section_id column to existing teachers table"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Check if column already exists
        cursor.execute("""
            SELECT COLUMN_NAME 
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_SCHEMA = 'neoattend' 
            AND TABLE_NAME = 'teachers' 
            AND COLUMN_NAME = 'section_id'
        """)
        
        if cursor.fetchone() is None:
            # Column doesn't exist, add it
            cursor.execute("""
                ALTER TABLE teachers 
                ADD COLUMN section_id INT,
                ADD FOREIGN KEY (section_id) REFERENCES sections(section_id)
            """)
            
            # Assign section 1 to existing teachers (excluding admin)
            cursor.execute("""
                UPDATE teachers 
                SET section_id = 1 
                WHERE role = 'teacher' AND section_id IS NULL
            """)
            
            # Set admin section_id to NULL
            cursor.execute("""
                UPDATE teachers 
                SET section_id = NULL 
                WHERE role = 'admin'
            """)
            
            conn.commit()
            print("✅ Successfully added section_id column to teachers table")
        else:
            print("✅ section_id column already exists in teachers table")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"Error adding section_id column: {e}")
        if "Duplicate column name" in str(e):
            print("✅ section_id column already exists")
        else:
            raise e

if __name__ == "__main__":
    add_section_id_column()
