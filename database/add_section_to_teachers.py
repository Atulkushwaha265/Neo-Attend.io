import mysql.connector
from database.mysql_connection import get_db

def add_section_id_to_teachers():
    """Add section_id column to teachers table and assign default sections"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Add section_id column if it doesn't exist
        cursor.execute("""
            ALTER TABLE teachers 
            ADD COLUMN section_id INT,
            ADD FOREIGN KEY (section_id) REFERENCES sections(section_id)
        """)
        
        # Assign section 1 to existing teachers (you can modify this as needed)
        cursor.execute("""
            UPDATE teachers 
            SET section_id = 1 
            WHERE section_id IS NULL AND role = 'teacher'
        """)
        
        # For admin, set section_id to NULL (can view all sections)
        cursor.execute("""
            UPDATE teachers 
            SET section_id = NULL 
            WHERE role = 'admin'
        """)
        
        conn.commit()
        cursor.close()
        conn.close()
        
        print("✅ Successfully added section_id to teachers table")
        
    except Exception as e:
        print(f"Error adding section_id: {e}")
        # If column already exists, that's okay
        if "Duplicate column name" in str(e):
            print("✅ section_id column already exists")
        else:
            raise e

if __name__ == "__main__":
    add_section_id_to_teachers()
