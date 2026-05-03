from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from database.mysql_connection import get_db
from utils.decorators import role_required, teacher_required
import mysql.connector
from datetime import date

teacher_bp = Blueprint("teacher", __name__, url_prefix="/teacher")


def _format_time_value(value):
    if value is None:
        return "TBA"

    if hasattr(value, "strftime"):
        return value.strftime("%I:%M %p")

    total_seconds = int(value.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    suffix = "AM" if hours < 12 else "PM"
    display_hour = hours % 12 or 12
    return f"{display_hour:02d}:{minutes:02d} {suffix}"


def _get_assigned_section(db, teacher_id):
    cursor = db.cursor(buffered=True)
    cursor.execute(
        """
        SELECT t.section_id, s.section_name
        FROM teachers t
        LEFT JOIN sections s ON t.section_id = s.section_id
        WHERE t.id = %s
        """,
        (teacher_id,),
    )
    section_data = cursor.fetchone()
    cursor.close()
    return section_data


def _format_notice_rows(rows):
    notices = []
    for row in rows:
        notices.append(
            {
                "title": row[0],
                "category": row[1] or "Notice",
                "content": row[2],
                "section_name": row[3] or "All Sections",
                "urgent": bool(row[4]),
                "date": row[5].strftime("%Y-%m-%d %H:%M") if row[5] else "",
            }
        )
    return notices


def _format_material_rows(rows):
    materials = []
    for row in rows:
        materials.append(
            {
                "title": row[0],
                "subject": row[1],
                "description": row[2] or "",
                "file_path": row[3],
                "section_name": row[4] or "All Sections",
                "upload_date": row[5].strftime("%Y-%m-%d %H:%M") if row[5] else "",
            }
        )
    return materials


def _format_schedule_rows(rows):
    schedules = []
    for row in rows:
        start_time = _format_time_value(row[3])
        end_time = _format_time_value(row[4]) if row[4] else ""
        schedules.append(
            {
                "subject": row[0],
                "section_name": row[1],
                "schedule_date": row[2].strftime("%Y-%m-%d") if row[2] else "",
                "time": start_time if not end_time else f"{start_time} - {end_time}",
                "room": row[5] or "TBA",
                "session_type": row[6] or "Lecture",
            }
        )
    return schedules

@teacher_bp.route("/teacher/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]

        hashed = generate_password_hash(password)

        db = get_db()
        cursor = db.cursor(buffered=True)
        try:
            cursor.execute(
                "INSERT INTO teachers (name,email,password,role) VALUES (%s,%s,%s,%s)",
                (name, email, hashed, "teacher")
            )
            db.commit()
        except:
            return render_template("teacher_register.html", error="Email already exists")

        cursor.close()
        db.close()
        return redirect(url_for("teacher.login"))

    return render_template("teacher_register.html")


@teacher_bp.route("/teacher/login", methods=["GET", "POST"])
def login():
    # Redirect if already logged in
    if 'teacher_id' in session:
        role = session.get('role', '')
        if role == 'admin':
            return redirect(url_for('admin.admin_dashboard'))
        else:
            return redirect(url_for('teacher.teacher_dashboard'))
    
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        db = get_db()
        cursor = db.cursor(buffered=True)
        cursor.execute("SELECT * FROM teachers WHERE email=%s", (email,))
        teacher = cursor.fetchone()
        cursor.close()
        db.close()

        if teacher and check_password_hash(teacher[3], password):  # password is at index 3
            session["teacher_id"] = teacher[0]  # id is at index 0
            session["teacher_name"] = teacher[1]  # name is at index 1
            session["role"] = teacher[4]  # role is at index 4
            
            # Redirect based on role
            if teacher[4] == "admin":
                return redirect(url_for("admin.admin_dashboard"))
            else:
                return redirect(url_for("teacher.teacher_dashboard"))

        return render_template("teacher_login.html", error="Invalid credentials")

    return render_template("teacher_login.html")


@teacher_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


@teacher_bp.route("/teacher/dashboard")
@teacher_required
def teacher_dashboard():
    teacher_name = session.get("teacher_name", "Teacher")
    teacher_id = session.get("teacher_id")
    role = session.get("role", "teacher")
    today = date.today()
    
    # Get teacher's assigned section
    db = get_db()
    cursor = db.cursor(buffered=True)
    cursor.execute("""
        SELECT t.section_id, s.section_name 
        FROM teachers t
        LEFT JOIN sections s ON t.section_id = s.section_id
        WHERE t.id = %s
    """, (teacher_id,))
    section_data = cursor.fetchone()
    
    if not section_data or not section_data[0]:
        cursor.close()
        db.close()
        return "Error: Teacher not assigned to any section. Please contact administrator.", 400
    
    section_id = section_data[0]
    section_name = section_data[1] or "Unknown Section"
    cursor.close()

    # -------- SESSION STATUS --------
    c1 = db.cursor(buffered=True)
    c1.execute("""
        SELECT is_locked
        FROM attendance_session
        WHERE section_id=%s AND attend_date=%s
        ORDER BY start_time DESC
        LIMIT 1
    """, (section_id, today))
    row = c1.fetchone()
    is_locked = row[0] if row else 0
    attendance_status = "LOCK" if is_locked else "OPEN"
    c1.close()

    # -------- TOTAL STUDENTS --------
    c2 = db.cursor(buffered=True)
    c2.execute(
        "SELECT COUNT(*) FROM students WHERE section_id=%s",
        (section_id,)
    )
    total_students = c2.fetchone()[0]
    c2.close()

    # -------- PRESENT --------
    c3 = db.cursor(buffered=True)
    c3.execute("""
        SELECT COUNT(*) FROM attendance
        WHERE attend_date=%s AND section_id=%s AND status='Present'
    """, (today, section_id))
    present_count = c3.fetchone()[0]
    c3.close()

    # -------- LATE --------
    c4 = db.cursor(buffered=True)
    c4.execute("""
        SELECT COUNT(*) FROM attendance
        WHERE attend_date=%s AND section_id=%s AND status='Late'
    """, (today, section_id))
    late_count = c4.fetchone()[0]
    c4.close()

    absent_count = total_students - (present_count + late_count)

    # -------- PERFORMANCE TRACKING --------
    # Get attendance percentage for each student in the last 30 days
    c6 = db.cursor(buffered=True)
    c6.execute("""
        SELECT 
            s.id,
            s.name,
            s.roll_no,
            COUNT(a.id) as total_classes,
            SUM(CASE WHEN a.status IN ('Present', 'Late') THEN 1 ELSE 0 END) as attended_classes,
            ROUND(
                (SUM(CASE WHEN a.status IN ('Present', 'Late') THEN 1 ELSE 0 END) * 100.0) / 
                NULLIF(COUNT(a.id), 0), 
                2
            ) as attendance_percentage
        FROM students s
        LEFT JOIN attendance a ON s.id = a.student_id 
            AND a.attend_date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
        WHERE s.section_id = %s
        GROUP BY s.id, s.name, s.roll_no
        ORDER BY attendance_percentage ASC
    """, (section_id,))
    performance_data = c6.fetchall()
    c6.close()
    
    # Convert to list of dicts and identify low performers
    performance_list = []
    low_performers = []
    for row in performance_data:
        perf = {
            'id': row[0],
            'name': row[1],
            'roll_no': row[2],
            'total_classes': row[3],
            'attended_classes': row[4],
            'attendance_percentage': row[5] or 0
        }
        performance_list.append(perf)
        
        # Flag students below 75% attendance
        if perf['attendance_percentage'] < 75:
            low_performers.append(perf)

    # -------- ATTENDANCE TABLE --------
    c5 = db.cursor(buffered=True)
    c5.execute("""
        SELECT s.roll_no, s.name, sec.section_name,
               COALESCE(a.status,'Absent') AS status,
               a.attend_time
        FROM students s
        JOIN sections sec ON s.section_id = sec.section_id
        LEFT JOIN attendance a
            ON s.id = a.student_id AND a.attend_date=%s
        WHERE s.section_id=%s
        ORDER BY s.roll_no
    """, (today, section_id))
    raw_attendance = c5.fetchall()
    c5.close()
    
    # Convert to list of dicts for template compatibility
    attendance_list = []
    for row in raw_attendance:
        attendance_list.append({
            'roll_no': row[0],
            'name': row[1], 
            'section': row[2],
            'status': row[3],
            'attend_time': str(row[4]) if row[4] else ''
        })

    db.close()

    return render_template(
        "teacher_dashboard.html",
        teacher_name=teacher_name,
        role=role,
        today=today,
        section=section_name,
        section_id=section_id,
        is_locked=is_locked,
        attendance_status=attendance_status,
        total_students=total_students,
        present_count=present_count,
        late_count=late_count,
        absent_count=absent_count,
        attendance=attendance_list,
        performance_list=performance_list,
        low_performers=low_performers
    )


@teacher_bp.route("/teacher/students")
@teacher_required
def view_students():
    teacher_id = session.get("teacher_id")
    teacher_name = session.get("teacher_name", "Teacher")
    
    # Get teacher's assigned section
    db = get_db()
    cursor = db.cursor(buffered=True)
    cursor.execute("""
        SELECT t.section_id, s.section_name 
        FROM teachers t
        LEFT JOIN sections s ON t.section_id = s.section_id
        WHERE t.id = %s
    """, (teacher_id,))
    section_data = cursor.fetchone()
    
    if not section_data or not section_data[0]:
        cursor.close()
        db.close()
        return "Error: Teacher not assigned to any section", 400
    
    section_id = section_data[0]
    section_name = section_data[1]
    
    # Get students in teacher's assigned section
    cursor.execute("""
        SELECT s.id, s.roll_no, s.name, sec.section_name,
               COUNT(a.id) as total_classes,
               SUM(CASE WHEN a.status IN ('Present', 'Late') THEN 1 ELSE 0 END) as attended_classes,
               ROUND(
                   (SUM(CASE WHEN a.status IN ('Present', 'Late') THEN 1 ELSE 0 END) * 100.0) / 
                   NULLIF(COUNT(a.id), 0), 
                   2
               ) as attendance_percentage
        FROM students s
        JOIN sections sec ON s.section_id = sec.section_id
        LEFT JOIN attendance a ON s.id = a.student_id 
            AND a.attend_date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
        WHERE s.section_id = %s
        GROUP BY s.id, s.roll_no, s.name, sec.section_name
        ORDER BY s.roll_no
    """, (section_id,))
    students_data = cursor.fetchall()
    cursor.close()
    db.close()
    
    # Convert to list of dicts
    students_list = []
    for row in students_data:
        students_list.append({
            'id': row[0],
            'roll_no': row[1],
            'name': row[2],
            'section': row[3],
            'total_classes': row[4],
            'attended_classes': row[5],
            'attendance_percentage': row[6] or 0
        })
    
    return render_template(
        "teacher_students.html",
        teacher_name=teacher_name,
        section=section_name,
        students=students_list
    )


@teacher_bp.route("/teacher/attendance")
@teacher_required
def view_attendance():
    from flask import request
    teacher_id = session.get("teacher_id")
    teacher_name = session.get("teacher_name", "Teacher")
    
    # Get date filter (default to today)
    filter_date = request.args.get('date', date.today().strftime('%Y-%m-%d'))
    
    # Get teacher's assigned section
    db = get_db()
    cursor = db.cursor(buffered=True)
    cursor.execute("""
        SELECT t.section_id, s.section_name 
        FROM teachers t
        LEFT JOIN sections s ON t.section_id = s.section_id
        WHERE t.id = %s
    """, (teacher_id,))
    section_data = cursor.fetchone()
    
    if not section_data or not section_data[0]:
        cursor.close()
        db.close()
        return "Error: Teacher not assigned to any section", 400
    
    section_id = section_data[0]
    section_name = section_data[1]
    
    # Get attendance records for the filtered date
    cursor.execute("""
        SELECT s.roll_no, s.name, sec.section_name,
               COALESCE(a.status, 'Absent') AS status,
               a.attend_time
        FROM students s
        JOIN sections sec ON s.section_id = sec.section_id
        LEFT JOIN attendance a
            ON s.id = a.student_id AND a.attend_date=%s
        WHERE s.section_id=%s
        ORDER BY s.roll_no
    """, (filter_date, section_id))
    attendance_data = cursor.fetchall()
    cursor.close()
    db.close()
    
    # Convert to list of dicts
    attendance_list = []
    for row in attendance_data:
        attendance_list.append({
            'roll_no': row[0],
            'name': row[1],
            'section': row[2],
            'status': row[3],
            'attend_time': str(row[4]) if row[4] else ''
        })
    
    return render_template(
        "teacher_attendance.html",
        teacher_name=teacher_name,
        section=section_name,
        attendance=attendance_list,
        filter_date=filter_date
    )


@teacher_bp.route("/teacher/communications", methods=["GET", "POST"])
@teacher_bp.route("/communications", methods=["GET", "POST"])
@teacher_required
def manage_communications():
    teacher_id = session.get("teacher_id")
    teacher_name = session.get("teacher_name", "Teacher")

    db = get_db()
    section_data = _get_assigned_section(db, teacher_id)

    if not section_data or not section_data[0]:
        db.close()
        return "Error: Teacher not assigned to any section. Please contact administrator.", 400

    section_id = section_data[0]
    section_name = section_data[1] or "Unknown Section"

    try:
        if request.method == "POST":
            form_type = request.form.get("form_type", "").strip()
            cursor = db.cursor(buffered=True)

            try:
                if form_type == "notice":
                    title = request.form.get("title", "").strip()
                    category = request.form.get("category", "Notice").strip() or "Notice"
                    content = request.form.get("content", "").strip()
                    urgent = 1 if request.form.get("urgent") else 0

                    if not title or not content:
                        raise ValueError("Notice title and content are required.")

                    cursor.execute(
                        """
                        INSERT INTO notices (
                            title, content, category, section_id, urgent, created_by_teacher_id, author_role
                        ) VALUES (%s, %s, %s, %s, %s, %s, 'teacher')
                        """,
                        (title, content, category, section_id, urgent, teacher_id),
                    )
                    flash("Notice published successfully.", "success")

                elif form_type == "material":
                    title = request.form.get("title", "").strip()
                    subject = request.form.get("subject", "").strip()
                    description = request.form.get("description", "").strip()
                    file_path = request.form.get("file_path", "").strip()

                    if not title or not subject or not file_path:
                        raise ValueError("Material title, subject, and resource link are required.")

                    cursor.execute(
                        """
                        INSERT INTO study_materials (
                            title, subject, description, file_path, section_id, uploaded_by_teacher_id
                        ) VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (title, subject, description, file_path, section_id, teacher_id),
                    )
                    flash("Study material shared successfully.", "success")

                elif form_type == "schedule":
                    subject = request.form.get("subject", "").strip()
                    schedule_date = request.form.get("schedule_date", "").strip()
                    start_time = request.form.get("start_time", "").strip()
                    end_time = request.form.get("end_time", "").strip() or None
                    room = request.form.get("room", "").strip()
                    session_type = request.form.get("session_type", "Lecture").strip() or "Lecture"

                    if not subject or not schedule_date or not start_time:
                        raise ValueError("Schedule subject, date, and start time are required.")

                    cursor.execute(
                        """
                        INSERT INTO class_schedule (
                            section_id, subject, schedule_date, start_time, end_time, room, session_type, created_by_teacher_id
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            section_id,
                            subject,
                            schedule_date,
                            start_time,
                            end_time,
                            room or None,
                            session_type,
                            teacher_id,
                        ),
                    )
                    flash("Schedule entry added successfully.", "success")

                else:
                    raise ValueError("Unsupported communication request.")

                db.commit()
                return redirect(url_for("teacher.manage_communications"))
            except Exception as exc:
                db.rollback()
                flash(str(exc), "error")
            finally:
                cursor.close()

        sections = [(section_id, section_name)]

        cursor = db.cursor(buffered=True)
        cursor.execute(
            """
            SELECT n.title, COALESCE(n.category, 'Notice'), n.content, s.section_name, n.urgent, n.date
            FROM notices n
            LEFT JOIN sections s ON n.section_id = s.section_id
            WHERE n.section_id = %s OR n.section_id IS NULL
            ORDER BY n.date DESC
            LIMIT 12
            """,
            (section_id,),
        )
        notices = _format_notice_rows(cursor.fetchall())
        cursor.close()

        cursor = db.cursor(buffered=True)
        cursor.execute(
            """
            SELECT m.title, m.subject, COALESCE(m.description, ''), m.file_path, s.section_name, m.upload_date
            FROM study_materials m
            LEFT JOIN sections s ON m.section_id = s.section_id
            WHERE m.section_id = %s OR m.section_id IS NULL
            ORDER BY m.upload_date DESC
            LIMIT 12
            """,
            (section_id,),
        )
        materials = _format_material_rows(cursor.fetchall())
        cursor.close()

        cursor = db.cursor(buffered=True)
        cursor.execute(
            """
            SELECT cs.subject, s.section_name, cs.schedule_date, cs.start_time, cs.end_time, cs.room, cs.session_type
            FROM class_schedule cs
            JOIN sections s ON cs.section_id = s.section_id
            WHERE cs.section_id = %s
              AND cs.schedule_date >= CURDATE()
            ORDER BY cs.schedule_date ASC, cs.start_time ASC
            LIMIT 12
            """,
            (section_id,),
        )
        schedules = _format_schedule_rows(cursor.fetchall())
        cursor.close()
    finally:
        db.close()

    return render_template(
        "communications.html",
        page_role="teacher",
        teacher_name=teacher_name,
        section_name=section_name,
        sections=sections,
        allow_all_sections=False,
        notices=notices,
        materials=materials,
        schedules=schedules,
    )
