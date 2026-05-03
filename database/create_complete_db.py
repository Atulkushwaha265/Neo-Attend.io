import mysql.connector
from werkzeug.security import generate_password_hash


conn = mysql.connector.connect(
    host="localhost",
    user="root",
    password="#@wj$12#atul",
)
cursor = conn.cursor()

cursor.execute("CREATE DATABASE IF NOT EXISTS neoattend")
cursor.execute("USE neoattend")

cursor.execute(
    """
    CREATE TABLE IF NOT EXISTS sections (
        section_id INT AUTO_INCREMENT PRIMARY KEY,
        section_name VARCHAR(50) UNIQUE NOT NULL,
        course_name VARCHAR(100) NULL
    )
    """
)

cursor.execute(
    """
    CREATE TABLE IF NOT EXISTS teachers (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        email VARCHAR(255) UNIQUE NOT NULL,
        password VARCHAR(255) NOT NULL,
        role VARCHAR(50) DEFAULT 'teacher',
        section_id INT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (section_id) REFERENCES sections(section_id)
    )
    """
)

cursor.execute(
    """
    CREATE TABLE IF NOT EXISTS students (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        email VARCHAR(255) UNIQUE,
        password VARCHAR(255),
        roll_no VARCHAR(50) NOT NULL,
        section_id INT,
        face_data LONGBLOB,
        FOREIGN KEY (section_id) REFERENCES sections(section_id),
        UNIQUE KEY students_roll_section_unique (roll_no, section_id)
    )
    """
)

cursor.execute(
    """
    CREATE TABLE IF NOT EXISTS attendance_session (
        id INT AUTO_INCREMENT PRIMARY KEY,
        section_id INT NOT NULL,
        attend_date DATE NOT NULL,
        is_locked BOOLEAN DEFAULT 0,
        start_time TIME,
        end_time TIME,
        UNIQUE KEY attendance_session_unique (section_id, attend_date),
        FOREIGN KEY (section_id) REFERENCES sections(section_id)
    )
    """
)

cursor.execute(
    """
    CREATE TABLE IF NOT EXISTS attendance (
        id INT AUTO_INCREMENT PRIMARY KEY,
        student_id INT NOT NULL,
        section_id INT NOT NULL,
        attend_date DATE NOT NULL,
        attend_time TIME NOT NULL,
        status ENUM('Present', 'Absent', 'Late') DEFAULT 'Present',
        FOREIGN KEY (student_id) REFERENCES students(id),
        FOREIGN KEY (section_id) REFERENCES sections(section_id),
        UNIQUE KEY attendance_student_date_unique (student_id, attend_date)
    )
    """
)

cursor.execute(
    """
    CREATE TABLE IF NOT EXISTS notices (
        id INT AUTO_INCREMENT PRIMARY KEY,
        title VARCHAR(255) NOT NULL,
        content TEXT NOT NULL,
        category VARCHAR(50) DEFAULT 'Notice',
        section_id INT NULL,
        urgent BOOLEAN DEFAULT 0,
        created_by_teacher_id INT NULL,
        author_role VARCHAR(50) DEFAULT 'admin',
        date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (section_id) REFERENCES sections(section_id),
        FOREIGN KEY (created_by_teacher_id) REFERENCES teachers(id)
    )
    """
)

cursor.execute(
    """
    CREATE TABLE IF NOT EXISTS study_materials (
        id INT AUTO_INCREMENT PRIMARY KEY,
        title VARCHAR(255) NOT NULL,
        subject VARCHAR(100) NOT NULL,
        description TEXT NULL,
        file_path VARCHAR(500) NOT NULL,
        section_id INT NULL,
        uploaded_by_teacher_id INT NULL,
        upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (section_id) REFERENCES sections(section_id),
        FOREIGN KEY (uploaded_by_teacher_id) REFERENCES teachers(id)
    )
    """
)

cursor.execute(
    """
    CREATE TABLE IF NOT EXISTS class_schedule (
        id INT AUTO_INCREMENT PRIMARY KEY,
        section_id INT NOT NULL,
        subject VARCHAR(100) NOT NULL,
        schedule_date DATE NOT NULL,
        start_time TIME NOT NULL,
        end_time TIME NULL,
        room VARCHAR(100) NULL,
        session_type VARCHAR(50) DEFAULT 'Lecture',
        created_by_teacher_id INT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (section_id) REFERENCES sections(section_id),
        FOREIGN KEY (created_by_teacher_id) REFERENCES teachers(id)
    )
    """
)

cursor.execute(
    """
    INSERT INTO sections (section_name, course_name)
    VALUES ('A', 'Computer Science'), ('B', 'Computer Science'), ('C', 'Computer Science')
    ON DUPLICATE KEY UPDATE course_name = VALUES(course_name)
    """
)

cursor.execute(
    """
    INSERT INTO teachers (name, email, password, role)
    VALUES ('Admin', 'admin@neoattend.com', %s, 'admin')
    ON DUPLICATE KEY UPDATE name = VALUES(name)
    """,
    (generate_password_hash("admin123"),),
)

conn.commit()
conn.close()

print("Complete database setup finished.")
print("Default admin login:")
print("  Email: admin@neoattend.com")
print("  Password: admin123")
