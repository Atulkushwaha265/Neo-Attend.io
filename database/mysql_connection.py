import mysql.connector


def get_db():
    """Get MySQL database connection."""
    try:
        conn = mysql.connector.connect(
            host="localhost",
            user="root",
            password="#@wj$12#atul",
            database="neoattend",
        )
        return conn
    except Exception as e:
        print(f"Database connection error: {e}")
        raise e


def _table_exists(cursor, table_name):
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
        """,
        (table_name,),
    )
    return cursor.fetchone()[0] > 0


def _column_exists(cursor, table_name, column_name):
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
          AND COLUMN_NAME = %s
        """,
        (table_name, column_name),
    )
    return cursor.fetchone()[0] > 0


def _index_exists(cursor, table_name, index_name):
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM INFORMATION_SCHEMA.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
          AND INDEX_NAME = %s
        """,
        (table_name, index_name),
    )
    return cursor.fetchone()[0] > 0


def _safe_schema_execute(cursor, query, params=None, ignore_error_codes=None):
    if ignore_error_codes is None:
        ignore_error_codes = {1050, 1060, 1061, 1091}

    try:
        cursor.execute(query, params or ())
    except mysql.connector.Error as exc:
        if exc.errno not in ignore_error_codes:
            raise


def ensure_student_auth_columns():
    """Ensure student auth columns exist for secure registration/login."""
    conn = get_db()
    cursor = conn.cursor(buffered=True)

    try:
        if not _table_exists(cursor, "students"):
            return

        if not _column_exists(cursor, "students", "email"):
            _safe_schema_execute(
                cursor,
                """
                ALTER TABLE students
                ADD COLUMN email VARCHAR(255) NULL AFTER name
                """,
            )

        if not _column_exists(cursor, "students", "password"):
            _safe_schema_execute(
                cursor,
                """
                ALTER TABLE students
                ADD COLUMN password VARCHAR(255) NULL AFTER email
                """,
            )

        if not _index_exists(cursor, "students", "students_email_unique"):
            _safe_schema_execute(
                cursor,
                """
                CREATE UNIQUE INDEX students_email_unique
                ON students (email)
                """,
            )

        conn.commit()
    finally:
        cursor.close()
        conn.close()


def ensure_dashboard_tables():
    """Ensure dashboard and communication tables exist for live student/admin views."""
    conn = get_db()
    cursor = conn.cursor(buffered=True)

    try:
        if _table_exists(cursor, "sections") and not _column_exists(cursor, "sections", "course_name"):
            _safe_schema_execute(
                cursor,
                """
                ALTER TABLE sections
                ADD COLUMN course_name VARCHAR(100) NULL AFTER section_name
                """,
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

        if not _column_exists(cursor, "study_materials", "description"):
            _safe_schema_execute(
                cursor,
                """
                ALTER TABLE study_materials
                ADD COLUMN description TEXT NULL AFTER subject
                """,
            )

        if not _column_exists(cursor, "study_materials", "uploaded_by_teacher_id"):
            _safe_schema_execute(
                cursor,
                """
                ALTER TABLE study_materials
                ADD COLUMN uploaded_by_teacher_id INT NULL AFTER section_id
                """,
            )

        if not _index_exists(cursor, "study_materials", "idx_materials_section_date"):
            _safe_schema_execute(
                cursor,
                """
                CREATE INDEX idx_materials_section_date
                ON study_materials (section_id, upload_date)
                """,
            )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS notices (
                id INT AUTO_INCREMENT PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                content TEXT NOT NULL,
                category VARCHAR(50) DEFAULT 'Notice',
                section_id INT NULL,
                urgent BOOLEAN DEFAULT FALSE,
                created_by_teacher_id INT NULL,
                author_role VARCHAR(50) DEFAULT 'admin',
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (section_id) REFERENCES sections(section_id),
                FOREIGN KEY (created_by_teacher_id) REFERENCES teachers(id)
            )
            """
        )

        if not _column_exists(cursor, "notices", "category"):
            _safe_schema_execute(
                cursor,
                """
                ALTER TABLE notices
                ADD COLUMN category VARCHAR(50) DEFAULT 'Notice' AFTER content
                """,
            )

        if not _column_exists(cursor, "notices", "created_by_teacher_id"):
            _safe_schema_execute(
                cursor,
                """
                ALTER TABLE notices
                ADD COLUMN created_by_teacher_id INT NULL AFTER urgent
                """,
            )

        if not _column_exists(cursor, "notices", "author_role"):
            _safe_schema_execute(
                cursor,
                """
                ALTER TABLE notices
                ADD COLUMN author_role VARCHAR(50) DEFAULT 'admin' AFTER created_by_teacher_id
                """,
            )

        if not _index_exists(cursor, "notices", "idx_notices_section_date"):
            _safe_schema_execute(
                cursor,
                """
                CREATE INDEX idx_notices_section_date
                ON notices (section_id, date)
                """,
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

        if not _index_exists(cursor, "class_schedule", "idx_schedule_section_date"):
            _safe_schema_execute(
                cursor,
                """
                CREATE INDEX idx_schedule_section_date
                ON class_schedule (section_id, schedule_date, start_time)
                """,
            )

        conn.commit()
    finally:
        cursor.close()
        conn.close()


def init_db():
    """Initialize database tables."""
    try:
        conn = get_db()
        cursor = conn.cursor()

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
                section_id INT,
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(roll_no, section_id),
                FOREIGN KEY (section_id) REFERENCES sections(section_id)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS attendance_session (
                session_id INT AUTO_INCREMENT PRIMARY KEY,
                section_id INT,
                attend_date DATE NOT NULL,
                is_locked BOOLEAN DEFAULT FALSE,
                start_time TIME,
                end_time TIME,
                UNIQUE(section_id, attend_date),
                FOREIGN KEY (section_id) REFERENCES sections(section_id)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS attendance (
                id INT AUTO_INCREMENT PRIMARY KEY,
                student_id INT,
                section_id INT,
                attend_date DATE NOT NULL,
                attend_time TIME NOT NULL,
                status VARCHAR(20) NOT NULL,
                UNIQUE(student_id, attend_date),
                FOREIGN KEY (student_id) REFERENCES students(id),
                FOREIGN KEY (section_id) REFERENCES sections(section_id)
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
            CREATE TABLE IF NOT EXISTS notices (
                id INT AUTO_INCREMENT PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                content TEXT NOT NULL,
                category VARCHAR(50) DEFAULT 'Notice',
                section_id INT NULL,
                urgent BOOLEAN DEFAULT FALSE,
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
            INSERT INTO sections (section_name, course_name) VALUES
            ('Section A', 'Computer Science'),
            ('Section B', 'Computer Science'),
            ('Section C', 'Computer Science')
            ON DUPLICATE KEY UPDATE
                course_name = VALUES(course_name)
            """
        )

        from werkzeug.security import generate_password_hash

        cursor.execute(
            """
            INSERT INTO teachers (name, email, password, role, section_id)
            VALUES ('Admin', 'admin@neoattend.com', %s, 'admin', NULL)
            ON DUPLICATE KEY UPDATE
                name = VALUES(name)
            """,
            (generate_password_hash("admin123"),),
        )

        conn.commit()
        cursor.close()
        conn.close()

        print("MySQL database initialized successfully!")
    except Exception as e:
        print(f"Database initialization error: {e}")
        raise e
