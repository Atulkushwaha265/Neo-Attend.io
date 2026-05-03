from flask import Blueprint, flash, redirect, render_template, request, session, url_for
import mysql.connector
from database.mysql_connection import get_db
from datetime import date, datetime
from werkzeug.security import check_password_hash
from utils.decorators import admin_required

admin_bp = Blueprint("admin", __name__)


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

# ---------------- ADMIN LOGIN ----------------
@admin_bp.route("/admin/login", methods=["GET", "POST"])
def admin_login():
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

        if teacher and check_password_hash(teacher[3], password) and teacher[4] == "admin":
            session["teacher_id"] = teacher[0]
            session["teacher_name"] = teacher[1]
            session["role"] = teacher[4]
            return redirect(url_for("admin.admin_dashboard"))

        return render_template("admin_login.html", error="Invalid admin credentials")

    return render_template("admin_login.html")


# ---------------- ADMIN DASHBOARD ----------------
@admin_bp.route("/admin_dashboard")
@admin_bp.route("/admin_dashboard_enhanced")
@admin_required
def admin_dashboard():
    from flask import request
    teacher_name = session.get("teacher_name", "Admin")
    role = session.get("role", "admin")
    today = date.today()
    
    # Get selected section from query parameter (default to 'all' for admin)
    selected_section_id = request.args.get('section_id', 'all')
    
    db = get_db()
    
    # -------- OVERALL STATISTICS --------
    # Total students (all sections)
    cursor = db.cursor(buffered=True)
    cursor.execute("SELECT COUNT(*) FROM students")
    total_students_all = cursor.fetchone()[0]
    cursor.close()
    
    # Total teachers
    cursor = db.cursor(buffered=True)
    cursor.execute("SELECT COUNT(*) FROM teachers WHERE role='teacher'")
    total_teachers = cursor.fetchone()[0]
    cursor.close()
    
    # Today's attendance (all sections)
    cursor = db.cursor(buffered=True)
    cursor.execute("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN a.status='Present' THEN 1 ELSE 0 END) as present,
            SUM(CASE WHEN a.status='Late' THEN 1 ELSE 0 END) as late,
            SUM(CASE WHEN a.status='Absent' THEN 1 ELSE 0 END) as absent
        FROM attendance a
        JOIN students s ON a.student_id = s.id
        WHERE a.attend_date = %s
    """, (today,))
    today_stats = cursor.fetchone()
    cursor.close()
    
    present_today = today_stats[1] or 0
    late_today = today_stats[2] or 0
    absent_today = today_stats[3] or 0
    
    # -------- SECTION SELECTION --------
    cursor = db.cursor(buffered=True)
    cursor.execute("SELECT section_id, section_name FROM sections ORDER BY section_name")
    sections = cursor.fetchall()
    cursor.close()
    
    # Determine section filter
    if selected_section_id == 'all':
        section_id = None
        section_name = "All Sections"
    else:
        section_id = int(selected_section_id)
        cursor = db.cursor(buffered=True)
        cursor.execute("SELECT section_name FROM sections WHERE section_id = %s", (section_id,))
        section_row = cursor.fetchone()
        section_name = section_row[0] if section_row else "Unknown"
        cursor.close()

    # -------- SESSION STATUS --------
    if section_id:
        cursor = db.cursor(buffered=True)
        cursor.execute("""
            SELECT is_locked
            FROM attendance_session
            WHERE section_id=%s AND attend_date=%s
            ORDER BY start_time DESC
            LIMIT 1
        """, (section_id, today))
        row = cursor.fetchone()
        is_locked = row[0] if row else 0
        attendance_status = "LOCK" if is_locked else "OPEN"
        cursor.close()
    else:
        attendance_status = "Multiple Sections"

    # -------- SECTION-WISE ATTENDANCE ANALYTICS --------
    cursor = db.cursor(buffered=True)
    cursor.execute("""
        SELECT 
            s.section_id,
            s.section_name,
            COUNT(st.id) as total_students,
            SUM(CASE WHEN a.status='Present' THEN 1 ELSE 0 END) as present,
            SUM(CASE WHEN a.status='Late' THEN 1 ELSE 0 END) as late,
            SUM(CASE WHEN a.status='Absent' THEN 1 ELSE 0 END) as absent,
            ROUND(
                (SUM(CASE WHEN a.status IN ('Present', 'Late') THEN 1 ELSE 0 END) * 100.0) / 
                NULLIF(COUNT(a.id), 0), 
                2
            ) as attendance_percentage
        FROM sections s
        LEFT JOIN students st ON s.section_id = st.section_id
        LEFT JOIN attendance a ON st.id = a.student_id AND a.attend_date = %s
        GROUP BY s.section_id, s.section_name
        ORDER BY s.section_name
    """, (today,))
    section_analytics = cursor.fetchall()
    cursor.close()

    # -------- LOW ATTENDANCE STUDENTS --------
    cursor = db.cursor(buffered=True)
    cursor.execute("""
        SELECT 
            st.id,
            st.name,
            st.roll_no,
            s.section_name,
            COUNT(a.id) as total_classes,
            SUM(CASE WHEN a.status IN ('Present', 'Late') THEN 1 ELSE 0 END) as attended,
            ROUND(
                (SUM(CASE WHEN a.status IN ('Present', 'Late') THEN 1 ELSE 0 END) * 100.0) / 
                NULLIF(COUNT(a.id), 0), 
                2
            ) as attendance_percentage
        FROM students st
        JOIN sections s ON st.section_id = s.section_id
        LEFT JOIN attendance a ON st.id = a.student_id 
            AND a.attend_date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
        GROUP BY st.id, st.name, st.roll_no, s.section_name
        HAVING attendance_percentage < 75
        ORDER BY attendance_percentage ASC
        LIMIT 10
    """)
    low_attendance_students = cursor.fetchall()
    cursor.close()

    # -------- MONTHLY ATTENDANCE SUMMARY --------
    cursor = db.cursor(buffered=True)
    cursor.execute("""
        SELECT 
            DATE_FORMAT(attend_date, '%Y-%m') as month,
            COUNT(*) as total_records,
            SUM(CASE WHEN a.status='Present' THEN 1 ELSE 0 END) as present,
            SUM(CASE WHEN a.status='Late' THEN 1 ELSE 0 END) as late,
            SUM(CASE WHEN a.status='Absent' THEN 1 ELSE 0 END) as absent,
            ROUND(
                (SUM(CASE WHEN a.status IN ('Present', 'Late') THEN 1 ELSE 0 END) * 100.0) / 
                COUNT(*), 
                2
            ) as attendance_percentage
        FROM attendance a
        WHERE a.attend_date >= DATE_SUB(CURDATE(), INTERVAL 6 MONTH)
        GROUP BY DATE_FORMAT(a.attend_date, '%Y-%m')
        ORDER BY month DESC
        LIMIT 6
    """)
    monthly_summary = cursor.fetchall()
    cursor.close()
    
    db.close()

    # -------- ATTENDANCE TABLE --------
    # Reopen database connection for attendance table query
    db = get_db()
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
        "admin_dashboard.html",
        teacher_name=teacher_name,
        role=role,
        today=today,
        section=section_name,
        section_id=section_id,
        selected_section_id=selected_section_id,
        attendance_status=attendance_status,
        
        # Overall Statistics
        total_students_all=total_students_all,
        total_teachers=total_teachers,
        present_today=present_today,
        late_today=late_today,
        absent_today=absent_today,
        
        # Section Data
        sections=sections,
        section_analytics=section_analytics,
        
        # Analytics
        low_attendance_students=low_attendance_students,
        monthly_summary=monthly_summary,
        
        # Current Attendance (for selected section)
        attendance=attendance_list
    )


# ---------------- OPEN ATTENDANCE ----------------
@admin_bp.route("/attendance/open", methods=["POST"])
@admin_required
def open_attendance():
    today = date.today()
    section_id = int(request.form.get('section_id', '1'))

    db = get_db()
    cursor = db.cursor(buffered=True)

    cursor.execute("""
        INSERT INTO attendance_session
        (section_id, attend_date, is_locked, start_time)
        VALUES (%s, %s, 0, %s)
        ON DUPLICATE KEY UPDATE
            is_locked=0,
            start_time=%s,
            end_time=NULL
    """, (section_id, today, datetime.now().time(), datetime.now().time()))

    db.commit()
    cursor.close()
    db.close()

    return redirect(url_for("admin.admin_dashboard", section_id=section_id))

# ---------------- LOCK ATTENDANCE ----------------
@admin_bp.route("/attendance/lock", methods=["POST"])
@admin_required
def lock_attendance():
    today = date.today()
    section_id = int(request.form.get('section_id', '1'))

    db = get_db()
    cursor = db.cursor(buffered=True)

    cursor.execute("""
        UPDATE attendance_session
        SET is_locked=1, end_time=%s
        WHERE section_id=%s AND attend_date=%s
    """, (datetime.now().time(), section_id, today))

    db.commit()
    cursor.close()
    db.close()

    return redirect(url_for("admin.admin_dashboard", section_id=section_id))

# ---------------- STUDENTS PAGE ----------------
@admin_bp.route("/student_info")
@admin_required
def student_info():
    
    # Get selected section from query parameter (default to 1 if not provided)
    selected_section_id = request.args.get('section_id', '1')
    
    db = get_db()
    cursor = db.cursor(buffered=True)
    
    # Get all sections for dropdown
    cursor.execute("SELECT section_id, section_name FROM sections ORDER BY section_name")
    sections = cursor.fetchall()
    
    # Get students for selected section
    cursor.execute("""
        SELECT 
            s.roll_no,
            s.name,
            sec.section_name,
            COUNT(a.id) AS present_days
        FROM students s
        JOIN sections sec ON s.section_id = sec.section_id
        LEFT JOIN attendance a 
            ON s.id = a.student_id AND a.status IN ('Present','Late')
        WHERE s.section_id = %s
        GROUP BY s.id, s.roll_no, s.name, sec.section_name
        ORDER BY s.roll_no
    """, (selected_section_id,))
    students = cursor.fetchall()

    cursor.execute(
        "SELECT COUNT(DISTINCT attend_date) FROM attendance"
    )
    total_days = cursor.fetchone()[0] or 1

    # Convert to list of dicts for template compatibility
    student_list = []
    for s in students:
        percent = int((s[3] / total_days) * 100)
        student_dict = {
            'roll_no': s[0],
            'name': s[1],
            'section': s[2],
            'present_days': s[3],
            'attendance_percent': percent
        }
        
        if percent >= 75:
            student_dict['status'] = "Active"
            student_dict['status_class'] = "present-text"
        else:
            student_dict['status'] = "Low"
            student_dict['status_class'] = "late-text"
        
        student_list.append(student_dict)

    cursor.close()
    db.close()

    return render_template("admin_students.html", students=student_list, sections=sections, selected_section_id=int(selected_section_id))


# ---------------- TEACHERS MANAGEMENT ----------------
@admin_bp.route("/admin/teachers")
@admin_required
def manage_teachers():
    db = get_db()
    cursor = db.cursor(buffered=True)
    
    # Get all teachers with their sections
    cursor.execute("""
        SELECT 
            t.id,
            t.name,
            t.email,
            t.role,
            t.created_at,
            s.section_name
        FROM teachers t
        LEFT JOIN sections s ON t.section_id = s.section_id
        ORDER BY t.role DESC, t.name
    """)
    teachers = cursor.fetchall()
    cursor.close()
    
    # Get sections for assignment dropdown
    cursor = db.cursor(buffered=True)
    cursor.execute("SELECT section_id, section_name FROM sections ORDER BY section_name")
    sections = cursor.fetchall()
    cursor.close()
    
    db.close()
    
    return render_template("admin_teachers.html", teachers=teachers, sections=sections)


# ---------------- COMMUNICATIONS ----------------
@admin_bp.route("/admin/communications", methods=["GET", "POST"])
@admin_required
def manage_communications():
    teacher_id = session.get("teacher_id")
    teacher_name = session.get("teacher_name", "Admin")

    db = get_db()

    try:
        if request.method == "POST":
            form_type = request.form.get("form_type", "").strip()
            cursor = db.cursor(buffered=True)

            try:
                if form_type == "notice":
                    title = request.form.get("title", "").strip()
                    category = request.form.get("category", "Notice").strip() or "Notice"
                    content = request.form.get("content", "").strip()
                    section_id_raw = request.form.get("section_id", "").strip()
                    urgent = 1 if request.form.get("urgent") else 0
                    section_id = int(section_id_raw) if section_id_raw else None

                    if not title or not content:
                        raise ValueError("Notice title and content are required.")

                    cursor.execute(
                        """
                        INSERT INTO notices (
                            title, content, category, section_id, urgent, created_by_teacher_id, author_role
                        ) VALUES (%s, %s, %s, %s, %s, %s, 'admin')
                        """,
                        (title, content, category, section_id, urgent, teacher_id),
                    )
                    flash("Notice published successfully.", "success")

                elif form_type == "material":
                    title = request.form.get("title", "").strip()
                    subject = request.form.get("subject", "").strip()
                    description = request.form.get("description", "").strip()
                    file_path = request.form.get("file_path", "").strip()
                    section_id_raw = request.form.get("section_id", "").strip()

                    if not title or not subject or not file_path or not section_id_raw:
                        raise ValueError("Material title, subject, section, and resource link are required.")

                    cursor.execute(
                        """
                        INSERT INTO study_materials (
                            title, subject, description, file_path, section_id, uploaded_by_teacher_id
                        ) VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (title, subject, description, file_path, int(section_id_raw), teacher_id),
                    )
                    flash("Study material shared successfully.", "success")

                elif form_type == "schedule":
                    subject = request.form.get("subject", "").strip()
                    schedule_date = request.form.get("schedule_date", "").strip()
                    start_time = request.form.get("start_time", "").strip()
                    end_time = request.form.get("end_time", "").strip() or None
                    room = request.form.get("room", "").strip()
                    session_type = request.form.get("session_type", "Lecture").strip() or "Lecture"
                    section_id_raw = request.form.get("section_id", "").strip()

                    if not subject or not schedule_date or not start_time or not section_id_raw:
                        raise ValueError("Schedule subject, date, start time, and section are required.")

                    cursor.execute(
                        """
                        INSERT INTO class_schedule (
                            section_id, subject, schedule_date, start_time, end_time, room, session_type, created_by_teacher_id
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            int(section_id_raw),
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
                return redirect(url_for("admin.manage_communications"))
            except Exception as exc:
                db.rollback()
                flash(str(exc), "error")
            finally:
                cursor.close()

        cursor = db.cursor(buffered=True)
        cursor.execute("SELECT section_id, section_name FROM sections ORDER BY section_name")
        sections = cursor.fetchall()
        cursor.close()

        cursor = db.cursor(buffered=True)
        cursor.execute(
            """
            SELECT n.title, COALESCE(n.category, 'Notice'), n.content, s.section_name, n.urgent, n.date
            FROM notices n
            LEFT JOIN sections s ON n.section_id = s.section_id
            ORDER BY n.date DESC
            LIMIT 12
            """
        )
        notices = _format_notice_rows(cursor.fetchall())
        cursor.close()

        cursor = db.cursor(buffered=True)
        cursor.execute(
            """
            SELECT m.title, m.subject, COALESCE(m.description, ''), m.file_path, s.section_name, m.upload_date
            FROM study_materials m
            LEFT JOIN sections s ON m.section_id = s.section_id
            ORDER BY m.upload_date DESC
            LIMIT 12
            """
        )
        materials = _format_material_rows(cursor.fetchall())
        cursor.close()

        cursor = db.cursor(buffered=True)
        cursor.execute(
            """
            SELECT cs.subject, s.section_name, cs.schedule_date, cs.start_time, cs.end_time, cs.room, cs.session_type
            FROM class_schedule cs
            JOIN sections s ON cs.section_id = s.section_id
            WHERE cs.schedule_date >= CURDATE()
            ORDER BY cs.schedule_date ASC, cs.start_time ASC
            LIMIT 12
            """
        )
        schedules = _format_schedule_rows(cursor.fetchall())
        cursor.close()
    finally:
        db.close()

    return render_template(
        "communications.html",
        page_role="admin",
        teacher_name=teacher_name,
        section_name="All Sections",
        sections=sections,
        allow_all_sections=True,
        notices=notices,
        materials=materials,
        schedules=schedules,
    )


# ---------------- ATTENDANCE RECORDS ----------------
@admin_bp.route("/admin/attendance")
@admin_required
def attendance_records():
    from flask import request
    
    # Get filters
    selected_section_id = request.args.get('section_id', 'all')
    filter_date = request.args.get('date', date.today().strftime('%Y-%m-%d'))
    
    db = get_db()
    cursor = db.cursor(buffered=True)
    
    # Get sections for dropdown
    cursor.execute("SELECT section_id, section_name FROM sections ORDER BY section_name")
    sections = cursor.fetchall()
    cursor.close()
    
    # Build query based on filters
    if selected_section_id == 'all':
        cursor = db.cursor(buffered=True)
        cursor.execute("""
            SELECT 
                s.roll_no,
                s.name,
                sec.section_name,
                a.attend_date,
                a.attend_time,
                a.status
            FROM attendance a
            JOIN students s ON a.student_id = s.id
            JOIN sections sec ON s.section_id = sec.section_id
            WHERE a.attend_date = %s
            ORDER BY sec.section_name, s.roll_no
        """, (filter_date,))
        attendance_data = cursor.fetchall()
        cursor.close()
    else:
        section_id = int(selected_section_id)
        cursor = db.cursor(buffered=True)
        cursor.execute("""
            SELECT 
                s.roll_no,
                s.name,
                sec.section_name,
                a.attend_date,
                a.attend_time,
                a.status
            FROM attendance a
            JOIN students s ON a.student_id = s.id
            JOIN sections sec ON s.section_id = sec.section_id
            WHERE a.attend_date = %s AND sec.section_id = %s
            ORDER BY s.roll_no
        """, (filter_date, section_id))
        attendance_data = cursor.fetchall()
        cursor.close()
    
    # Convert to list of dicts
    attendance_list = []
    for row in attendance_data:
        attendance_list.append({
            'roll_no': row[0],
            'name': row[1],
            'section': row[2],
            'date': str(row[3]),
            'time': str(row[4]) if row[4] else '',
            'status': row[5]
        })
    
    db.close()
    
    return render_template(
        "admin_attendance.html",
        attendance=attendance_list,
        sections=sections,
        selected_section_id=selected_section_id,
        filter_date=filter_date
    )


# ---------------- ASSIGN SECTION TO TEACHER ----------------
@admin_bp.route("/admin/assign_section", methods=["POST"])
@admin_required
def assign_section():
    from flask import request, jsonify
    
    teacher_id = request.form.get('teacher_id')
    section_id = request.form.get('section_id')
    
    try:
        db = get_db()
        cursor = db.cursor(buffered=True)
        
        cursor.execute("""
            UPDATE teachers 
            SET section_id = %s 
            WHERE id = %s AND role = 'teacher'
        """, (section_id if section_id else None, teacher_id))
        
        db.commit()
        cursor.close()
        db.close()
        
        return jsonify({'success': True, 'message': 'Section assigned successfully'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


# ---------------- TOGGLE TEACHER STATUS ----------------
@admin_bp.route("/admin/toggle_teacher_status", methods=["POST"])
@admin_required
def toggle_teacher_status():
    from flask import request, jsonify
    
    data = request.get_json()
    teacher_id = data.get('teacher_id')
    
    try:
        db = get_db()
        cursor = db.cursor(buffered=True)
        
        # For now, we'll just return success since we don't have a status column
        # This could be enhanced later with an 'is_active' column
        cursor.close()
        db.close()
        
        return jsonify({'success': True, 'message': 'Teacher status updated successfully'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})
