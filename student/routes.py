from flask import Blueprint, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from database.mysql_connection import get_db

student_bp = Blueprint("student", __name__)


def _redirect_logged_in_staff():
    if "teacher_id" not in session:
        return None

    role = session.get("role", "")
    if role == "admin":
        return redirect(url_for("admin.admin_dashboard"))
    if role == "teacher":
        return redirect(url_for("teacher.teacher_dashboard"))
    return None


def _get_student_profile(db, student_id):
    cursor = db.cursor(dictionary=True, buffered=True)
    cursor.execute(
        """
        SELECT
            s.id,
            s.name,
            s.roll_no,
            s.email,
            s.section_id,
            COALESCE(sec.section_name, 'No Section') AS section_name,
            COALESCE(sec.course_name, 'Computer Science') AS course_name
        FROM students s
        LEFT JOIN sections sec ON s.section_id = sec.section_id
        WHERE s.id = %s
        LIMIT 1
        """,
        (student_id,),
    )
    student = cursor.fetchone()
    cursor.close()
    return student


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


def _get_attendance_stats(db, student_id):
    cursor = db.cursor(dictionary=True, buffered=True)
    cursor.execute(
        """
        SELECT
            COUNT(*) AS total_classes,
            COALESCE(SUM(CASE WHEN status = 'Present' THEN 1 ELSE 0 END), 0) AS present_days,
            COALESCE(SUM(CASE WHEN status = 'Late' THEN 1 ELSE 0 END), 0) AS late_days,
            COALESCE(SUM(CASE WHEN status = 'Absent' THEN 1 ELSE 0 END), 0) AS absent_days,
            COALESCE(
                ROUND(
                    (
                        COALESCE(SUM(CASE WHEN status IN ('Present', 'Late') THEN 1 ELSE 0 END), 0)
                        * 100.0
                    ) / NULLIF(COUNT(*), 0),
                    2
                ),
                0
            ) AS overall_attendance
        FROM attendance
        WHERE student_id = %s
        """,
        (student_id,),
    )
    stats = cursor.fetchone()
    cursor.close()
    return stats or {
        "total_classes": 0,
        "present_days": 0,
        "late_days": 0,
        "absent_days": 0,
        "overall_attendance": 0,
    }


def _get_recent_attendance(db, student_id, limit=12):
    cursor = db.cursor(dictionary=True, buffered=True)
    cursor.execute(
        """
        SELECT
            attend_date,
            attend_time,
            status
        FROM attendance
        WHERE student_id = %s
        ORDER BY attend_date DESC, attend_time DESC
        LIMIT %s
        """,
        (student_id, limit),
    )
    rows = cursor.fetchall()
    cursor.close()

    history = []
    for row in rows:
        history.append(
            {
                "date": row["attend_date"].strftime("%Y-%m-%d") if row["attend_date"] else "",
                "time": str(row["attend_time"]) if row["attend_time"] else "--",
                "status": row["status"] or "Absent",
            }
        )
    return history


def _get_subject_attendance(db, student_id, section_id):
    if not section_id:
        return []

    cursor = db.cursor(dictionary=True, buffered=True)
    cursor.execute(
        """
        SELECT
            cs.subject AS name,
            COUNT(*) AS total_classes,
            COALESCE(SUM(CASE WHEN a.status IN ('Present', 'Late') THEN 1 ELSE 0 END), 0) AS attended,
            COALESCE(
                ROUND(
                    (
                        COALESCE(SUM(CASE WHEN a.status IN ('Present', 'Late') THEN 1 ELSE 0 END), 0)
                        * 100.0
                    ) / NULLIF(COUNT(*), 0),
                    2
                ),
                0
            ) AS percentage
        FROM class_schedule cs
        LEFT JOIN attendance a
            ON a.student_id = %s
           AND a.section_id = cs.section_id
           AND a.attend_date = cs.schedule_date
        WHERE cs.section_id = %s
          AND cs.schedule_date <= CURDATE()
        GROUP BY cs.subject
        ORDER BY cs.subject
        """,
        (student_id, section_id),
    )
    rows = cursor.fetchall()
    cursor.close()

    subjects = []
    for row in rows:
        subjects.append(
            {
                "name": row["name"],
                "total_classes": row["total_classes"] or 0,
                "attended": row["attended"] or 0,
                "percentage": row["percentage"] or 0,
            }
        )
    return subjects


def _get_study_materials(db, section_id, limit=20):
    cursor = db.cursor(dictionary=True, buffered=True)
    cursor.execute(
        """
        SELECT
            id,
            title,
            subject,
            COALESCE(description, '') AS description,
            file_path,
            upload_date
        FROM study_materials
        WHERE section_id = %s OR section_id IS NULL
        ORDER BY upload_date DESC
        LIMIT %s
        """,
        (section_id, limit),
    )
    rows = cursor.fetchall()
    cursor.close()

    materials = []
    for row in rows:
        materials.append(
            {
                "id": row["id"],
                "title": row["title"],
                "subject": row["subject"],
                "description": row["description"],
                "file_path": row["file_path"],
                "upload_date": row["upload_date"].strftime("%Y-%m-%d %H:%M")
                if row["upload_date"]
                else "",
            }
        )
    return materials


def _get_notices(db, section_id, limit=20):
    cursor = db.cursor(dictionary=True, buffered=True)
    cursor.execute(
        """
        SELECT
            id,
            title,
            content,
            COALESCE(category, 'Notice') AS category,
            urgent,
            date
        FROM notices
        WHERE section_id = %s OR section_id IS NULL
        ORDER BY urgent DESC, date DESC
        LIMIT %s
        """,
        (section_id, limit),
    )
    rows = cursor.fetchall()
    cursor.close()

    notices = []
    for row in rows:
        notices.append(
            {
                "id": row["id"],
                "title": row["title"],
                "content": row["content"],
                "category": row["category"] or "Notice",
                "urgent": bool(row["urgent"]),
                "date": row["date"].strftime("%Y-%m-%d %H:%M") if row["date"] else "",
            }
        )
    return notices


def _get_schedule(db, section_id, limit=20):
    if not section_id:
        return []

    cursor = db.cursor(dictionary=True, buffered=True)
    cursor.execute(
        """
        SELECT
            id,
            subject,
            schedule_date,
            start_time,
            end_time,
            COALESCE(room, 'TBA') AS room,
            COALESCE(session_type, 'Lecture') AS session_type
        FROM class_schedule
        WHERE section_id = %s
          AND schedule_date >= CURDATE()
        ORDER BY schedule_date ASC, start_time ASC
        LIMIT %s
        """,
        (section_id, limit),
    )
    rows = cursor.fetchall()
    cursor.close()

    upcoming_schedule = []
    for row in rows:
        start_time = _format_time_value(row["start_time"])
        end_time = _format_time_value(row["end_time"]) if row["end_time"] else ""
        time_range = start_time if not end_time else f"{start_time} - {end_time}"
        upcoming_schedule.append(
            {
                "id": row["id"],
                "subject": row["subject"],
                "date": row["schedule_date"].strftime("%Y-%m-%d") if row["schedule_date"] else "",
                "time": time_range,
                "room": row["room"],
                "type": row["session_type"],
            }
        )
    return upcoming_schedule


def _render_student_dashboard(active_page):
    if "student_id" not in session:
        return redirect(url_for("student.student_login"))

    student_id = session.get("student_id")
    db = get_db()

    try:
        student = _get_student_profile(db, student_id)
        if not student:
            session.clear()
            return redirect(url_for("student.student_login"))

        session["student_name"] = student["name"]
        session["student_roll_no"] = student["roll_no"]
        session["student_section"] = student["section_name"]

        stats = _get_attendance_stats(db, student_id)
        recent_attendance = _get_recent_attendance(db, student_id)
        subject_attendance = _get_subject_attendance(db, student_id, student["section_id"])
        study_materials = _get_study_materials(db, student["section_id"])
        notices = _get_notices(db, student["section_id"])
        upcoming_schedule = _get_schedule(db, student["section_id"])
    finally:
        db.close()

    page_titles = {
        "dashboard": "Dashboard Overview",
        "attendance": "Attendance Details",
        "materials": "Study Materials",
        "notices": "Notice Board",
        "schedule": "Schedule",
    }

    return render_template(
        "student_dashboard.html",
        active_page=active_page,
        page_title=page_titles.get(active_page, "Student Dashboard"),
        student_name=student["name"],
        student_roll_no=student["roll_no"],
        student_section=student["section_name"],
        student_course=student["course_name"],
        overall_attendance=stats["overall_attendance"] or 0,
        total_classes=stats["total_classes"] or 0,
        present_days=stats["present_days"] or 0,
        late_days=stats["late_days"] or 0,
        absent_days=stats["absent_days"] or 0,
        recent_attendance=recent_attendance,
        subject_attendance=subject_attendance,
        study_materials=study_materials,
        notices=notices,
        upcoming_schedule=upcoming_schedule,
        notification_count=len(notices),
        materials_count=len(study_materials),
        upcoming_schedule_count=len(upcoming_schedule),
    )


# ---------------- STUDENT PORTAL ----------------
@student_bp.route("/student")
def student_portal():
    if "student_id" in session:
        return redirect(url_for("student.student_dashboard"))

    staff_redirect = _redirect_logged_in_staff()
    if staff_redirect:
        return staff_redirect

    return render_template("student_portal.html")


# ---------------- STUDENT LOGIN ----------------
@student_bp.route("/student/login", methods=["GET", "POST"])
def student_login():
    if "student_id" in session:
        return redirect(url_for("student.student_dashboard"))

    staff_redirect = _redirect_logged_in_staff()
    if staff_redirect:
        return staff_redirect

    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        password = request.form.get("password")

        if not identifier or not password:
            return render_template("student_login.html", error="Please fill all fields")

        db = get_db()
        cursor = db.cursor(buffered=True)
        cursor.execute(
            """
            SELECT
                s.id,
                s.name,
                s.roll_no,
                COALESCE(sec.section_name, 'No Section') AS section_name,
                s.password
            FROM students s
            LEFT JOIN sections sec ON s.section_id = sec.section_id
            WHERE s.roll_no = %s OR LOWER(s.email) = LOWER(%s)
            LIMIT 1
            """,
            (identifier, identifier),
        )
        student = cursor.fetchone()
        cursor.close()
        db.close()

        if not student:
            return render_template(
                "student_login.html",
                error="No student account found with that roll number or email.",
            )

        if not student[4]:
            return render_template(
                "student_login.html",
                error="Your account exists but has no password set. Please register again or contact the administrator.",
            )

        if check_password_hash(student[4], password):
            session["student_id"] = student[0]
            session["student_name"] = student[1]
            session["student_roll_no"] = student[2]
            session["student_section"] = student[3]
            return redirect(url_for("student.student_dashboard"))

        return render_template(
            "student_login.html",
            error="Invalid password. Please check your roll number/email and password.",
        )

    return render_template("student_login.html")


# ---------------- STUDENT REGISTRATION ----------------
@student_bp.route("/student/register/manual", methods=["GET", "POST"])
def student_register():
    return redirect(url_for("face_register.register_page"))


# ---------------- STUDENT DASHBOARD ----------------
@student_bp.route("/student/dashboard")
def student_dashboard():
    return _render_student_dashboard("dashboard")


@student_bp.route("/student/attendance")
def student_attendance():
    return _render_student_dashboard("attendance")


@student_bp.route("/student/materials")
def student_materials():
    return _render_student_dashboard("materials")


@student_bp.route("/student/notices")
def student_notices():
    return _render_student_dashboard("notices")


@student_bp.route("/student/schedule")
def student_schedule():
    return _render_student_dashboard("schedule")


# ---------------- STUDENT LOGOUT ----------------
@student_bp.route("/student/logout")
def student_logout():
    session.clear()
    return redirect(url_for("home"))
