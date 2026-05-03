import base64
import io
import pickle
from datetime import date, datetime, time

import cv2
import face_recognition
import numpy as np
from PIL import Image
from flask import Blueprint, jsonify, render_template, request

from database.mysql_connection import get_db
from face.camera_utils import (
    get_selected_camera_info,
    list_available_cameras,
    read_camera_frame,
    select_best_camera,
)

face_bp = Blueprint("face_match", __name__, template_folder="../templates")

# ---------------- CONFIG ----------------
LATE_TIME = time(9, 30)
MATCH_TOLERANCE = 0.50
AMBIGUITY_MARGIN = 0.04


# ---------------- LOAD STUDENTS ----------------
def load_student_encodings():
    try:
        db = get_db()
        cursor = db.cursor(buffered=True)
        cursor.execute(
            """
            SELECT id, section_id, face_data
            FROM students
            WHERE face_data IS NOT NULL
            ORDER BY id
            """
        )
        rows = cursor.fetchall()

        ids = []
        sections = []
        encodings = []

        for student_id, section_id, blob in rows:
            ids.append(int(student_id))
            sections.append(int(section_id))
            encodings.append(pickle.loads(blob))

        cursor.close()
        db.close()

        return ids, sections, encodings
    except Exception as e:
        print(f"Error loading encodings: {e}")
        return [], [], []


# Face encodings are cached in memory between requests.
known_ids = []
known_sections = []
known_encodings = []
encodings_loaded = False


def set_encodings_cache(ids, sections, encodings):
    """Replace the in-memory encoding cache with fresh database results."""
    global known_ids, known_sections, known_encodings, encodings_loaded
    known_ids = ids
    known_sections = sections
    known_encodings = encodings
    encodings_loaded = True


def refresh_encodings_cache():
    """Force a reload of all registered encodings from MySQL."""
    ids, sections, encodings = load_student_encodings()
    set_encodings_cache(ids, sections, encodings)
    print(f"Loaded {len(known_encodings)} face encodings from database")
    return known_ids, known_sections, known_encodings


def ensure_encodings_loaded(force_reload=False):
    """Load encodings on first use or refresh them explicitly."""
    global encodings_loaded
    if force_reload or not encodings_loaded:
        refresh_encodings_cache()


def find_best_match(encoding):
    """
    Return the clearest matching student.

    The best face must be:
    1. Within tolerance.
    2. Clearly better than the second-best match.
    """
    if not known_encodings:
        return None, "No registered faces found in the system. Please register students first."

    face_distances = face_recognition.face_distance(known_encodings, encoding)
    if len(face_distances) == 0:
        return None, "No registered faces found in the system. Please register students first."

    ranked_indices = np.argsort(face_distances)
    best_index = int(ranked_indices[0])
    best_distance = float(face_distances[best_index])

    if best_distance > MATCH_TOLERANCE:
        return None, (
            "Unknown face. This face is not registered in the system. "
            f"(Distance: {best_distance:.3f})"
        )

    if len(ranked_indices) > 1:
        second_best_distance = float(face_distances[int(ranked_indices[1])])
        if (second_best_distance - best_distance) < AMBIGUITY_MARGIN:
            return None, (
                "Face match is too close to another registered student. "
                "Try again in better lighting or re-register clearer photos."
            )

    return {
        "student_id": known_ids[best_index],
        "section_id": known_sections[best_index],
        "distance": best_distance,
    }, None

# ---------------- HOME ----------------
@face_bp.route("/attendance")
def attendance_page():
    return render_template("attendance_enhanced.html")


# ---------------- DEBUG ROUTE ----------------
@face_bp.route("/debug_faces", methods=["GET"])
def debug_faces():
    ensure_encodings_loaded(force_reload=True)
    return jsonify(
        {
            "total_encodings": len(known_encodings),
            "known_ids": known_ids,
            "known_sections": known_sections,
            "message": f"System has {len(known_encodings)} registered faces",
        }
    )


@face_bp.route("/debug_camera", methods=["GET"])
def debug_camera():
    selected_camera = get_selected_camera_info() or select_best_camera()
    available_cameras = list_available_cameras()

    return jsonify(
        {
            "success": bool(available_cameras),
            "selected_camera": selected_camera,
            "available_cameras": available_cameras,
            "message": (
                "Camera detected successfully."
                if available_cameras
                else "No working camera was detected."
            ),
        }
    )


# ---------------- MARK ATTENDANCE ----------------
@face_bp.route("/mark_attendance", methods=["POST"])
def mark_attendance():
    try:
        # Always refresh before matching so newly-registered students are included.
        ensure_encodings_loaded(force_reload=True)

        if not request.is_json:
            return jsonify({"success": False, "error": "Expected JSON data"})

        data = request.get_json()
        if "image" not in data:
            return jsonify({"success": False, "error": "No image provided"})

        base64_data = data["image"]
        if "," in base64_data:
            base64_data = base64_data.split(",", 1)[1]

        image_bytes = base64.b64decode(base64_data)
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        rgb_image = np.array(image)

        encodings = face_recognition.face_encodings(rgb_image)
        if len(encodings) == 0:
            return jsonify(
                {
                    "success": False,
                    "error": "No face detected. Please position your face properly in the camera.",
                }
            )

        if len(encodings) > 1:
            return jsonify(
                {
                    "success": False,
                    "error": "Multiple faces detected. Please ensure only one student is in front of the camera.",
                }
            )

        match, match_error = find_best_match(encodings[0])
        if match_error:
            return jsonify({"success": False, "error": match_error})

        student_id = int(match["student_id"])
        section_id = int(match["section_id"])
        today = date.today()
        now_time = datetime.now().time()

        db = get_db()

        cursor = db.cursor(buffered=True)
        cursor.execute(
            """
            SELECT is_locked
            FROM attendance_session
            WHERE section_id=%s AND attend_date=%s
            ORDER BY start_time DESC
            LIMIT 1
            """,
            (section_id, today.strftime("%Y-%m-%d")),
        )
        row = cursor.fetchone()
        cursor.close()

        if row and row[0] == 1:
            db.close()
            return jsonify(
                {
                    "success": False,
                    "error": "Attendance is locked for this section. Please contact your teacher.",
                }
            )

        status = "Present" if now_time <= LATE_TIME else "Late"

        cursor = db.cursor(buffered=True)
        cursor.execute(
            """
            SELECT id, attend_time, status
            FROM attendance
            WHERE student_id=%s AND attend_date=%s
            """,
            (student_id, today.strftime("%Y-%m-%d")),
        )
        already = cursor.fetchone()
        cursor.close()

        if already:
            cursor = db.cursor(buffered=True)
            cursor.execute(
                """
                SELECT s.name, s.roll_no, sec.section_name
                FROM students s
                JOIN sections sec ON s.section_id = sec.section_id
                WHERE s.id = %s
                """,
                (student_id,),
            )
            student = cursor.fetchone()
            cursor.close()
            db.close()

            return jsonify(
                {
                    "success": False,
                    "error": (
                        f"Attendance already marked for {student[0]} ({student[1]}) "
                        f"at {already[1]}. Status: {already[2]}"
                    ),
                }
            )

        cursor = db.cursor(buffered=True)
        cursor.execute(
            """
            INSERT INTO attendance
            (student_id, section_id, attend_date, attend_time, status)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                student_id,
                section_id,
                today.strftime("%Y-%m-%d"),
                now_time.strftime("%H:%M:%S"),
                status,
            ),
        )
        db.commit()
        cursor.close()

        cursor = db.cursor(buffered=True)
        cursor.execute(
            """
            SELECT s.name, s.roll_no, sec.section_name
            FROM students s
            JOIN sections sec ON s.section_id = sec.section_id
            WHERE s.id = %s
            """,
            (student_id,),
        )
        student = cursor.fetchone()
        cursor.close()
        db.close()

        return jsonify(
            {
                "success": True,
                "data": {
                    "name": student[0],
                    "roll_no": student[1],
                    "section": student[2],
                    "status": status,
                    "date": today.strftime("%Y-%m-%d"),
                    "time": now_time.strftime("%H:%M:%S"),
                },
            }
        )

    except Exception as e:
        print(f"Error in mark_attendance: {e}")
        return jsonify(
            {
                "success": False,
                "error": "An error occurred while processing attendance. Please try again.",
            }
        )


# ---------------- RELOAD ENCODINGS ----------------
@face_bp.route("/reload_encodings", methods=["POST"])
def reload_encodings():
    try:
        ids, sections, encodings = refresh_encodings_cache()
        return jsonify(
            {
                "success": True,
                "message": f"Reloaded {len(ids)} student encodings",
                "total_encodings": len(encodings),
                "sections": sections,
            }
        )
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to reload encodings: {e}"})


# ---------------- LEGACY ROUTE FOR BACKWARDS COMPATIBILITY ----------------
@face_bp.route("/mark_attendance_legacy", methods=["POST"])
def mark_attendance_legacy():
    """Legacy route for backwards compatibility."""
    try:
        ensure_encodings_loaded(force_reload=True)
        frame, camera_error = read_camera_frame()
        if frame is None:
            return render_template(
                "attendance_enhanced.html",
                status=camera_error or "Camera not working",
            )

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        encodings = face_recognition.face_encodings(rgb)

        if len(encodings) == 0:
            return render_template("attendance_enhanced.html", status="No face detected")

        if len(encodings) > 1:
            return render_template("attendance_enhanced.html", status="Multiple faces detected")

        match, match_error = find_best_match(encodings[0])
        if match_error:
            return render_template("attendance_enhanced.html", status=match_error)

        student_id = int(match["student_id"])
        section_id = int(match["section_id"])
        today = date.today()
        now_time = datetime.now().time()

        db = get_db()

        c1 = db.cursor(buffered=True)
        c1.execute(
            """
            SELECT is_locked
            FROM attendance_session
            WHERE section_id=%s AND attend_date=%s
            ORDER BY start_time DESC
            LIMIT 1
            """,
            (section_id, today),
        )
        row = c1.fetchone()
        c1.close()

        if row and row[0] == 1:
            db.close()
            return render_template("attendance_enhanced.html", status="Attendance is locked")

        status = "Present" if now_time <= LATE_TIME else "Late"

        c2 = db.cursor(buffered=True)
        c2.execute(
            """
            SELECT id
            FROM attendance
            WHERE student_id=%s AND attend_date=%s
            """,
            (student_id, today),
        )
        already = c2.fetchone()
        c2.close()

        if not already:
            c3 = db.cursor(buffered=True)
            c3.execute(
                """
                INSERT INTO attendance
                (student_id, section_id, attend_date, attend_time, status)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (student_id, section_id, today, now_time, status),
            )
            db.commit()
            c3.close()

        c4 = db.cursor(buffered=True)
        c4.execute(
            """
            SELECT s.name, s.roll_no, sec.section_name
            FROM students s
            JOIN sections sec ON s.section_id = sec.section_id
            WHERE s.id = %s
            """,
            (student_id,),
        )
        student = c4.fetchone()
        c4.close()

        db.close()

        return render_template(
            "attendance_enhanced.html",
            name=student[0],
            roll_no=student[1],
            section=student[2],
            status=status,
            date=today,
            time=now_time.strftime("%H:%M:%S"),
        )

    except Exception as e:
        print(f"Error in legacy attendance: {e}")
        return render_template("attendance_enhanced.html", status="An error occurred")
