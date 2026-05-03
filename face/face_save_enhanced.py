import io
import os
import pickle
import random
import re
import secrets
import smtplib
import ssl
import time
from email.message import EmailMessage
from pathlib import Path

import cv2
import face_recognition
import mysql.connector
import numpy as np
from dotenv import load_dotenv
from PIL import Image
from flask import Blueprint, jsonify, render_template, request, session
from werkzeug.security import generate_password_hash

from database.mysql_connection import get_db
from face.camera_utils import read_camera_frame

BASE_DIR = Path(__file__).resolve().parents[1]
ENV_FILE = BASE_DIR / ".env"
load_dotenv(dotenv_path=ENV_FILE, override=True)

face_register_bp = Blueprint("face_register", __name__, template_folder="../templates")

# ---------------- CONFIG ----------------
DUPLICATE_TOLERANCE = 0.45
OTP_VALIDITY_SECONDS = 5 * 60
OTP_LENGTH = 6
OTP_MAX_ATTEMPTS = 5
COLLEGE_EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+-]+@axiscolleges\.in$", re.IGNORECASE)

# ---------------- TEMP REGISTRATION STATE ----------------
FACE_CAPTURE_STORE = {}
OTP_STORE = {}


# ---------------- LOAD ENCODINGS ----------------
def get_known_encodings():
    try:
        db = get_db()
        cursor = db.cursor(buffered=True)
        cursor.execute(
            """
            SELECT face_data
            FROM students
            WHERE face_data IS NOT NULL
            ORDER BY id
            """
        )
        rows = cursor.fetchall()
        cursor.close()
        db.close()
        return [pickle.loads(row[0]) for row in rows]
    except Exception as e:
        print(f"Error loading known encodings: {e}")
        return []


def has_duplicate_face(new_encoding):
    """Check whether the captured face is already registered."""
    known_encodings = get_known_encodings()
    if not known_encodings:
        return False

    distances = face_recognition.face_distance(known_encodings, new_encoding)
    if len(distances) == 0:
        return False

    return float(np.min(distances)) <= DUPLICATE_TOLERANCE


def normalize_email(email):
    return (email or "").strip().lower()


def is_valid_college_email(email):
    return bool(COLLEGE_EMAIL_PATTERN.fullmatch(normalize_email(email)))


def validate_password_strength(password):
    if len(password or "") < 8:
        return "Password must be at least 8 characters long."
    if not re.search(r"[A-Z]", password):
        return "Password must include at least one uppercase letter."
    if not re.search(r"[a-z]", password):
        return "Password must include at least one lowercase letter."
    if not re.search(r"\d", password):
        return "Password must include at least one number."
    if not re.search(r"[^A-Za-z0-9]", password):
        return "Password must include at least one special character."
    return None


def _get_client_token():
    client_token = session.get("registration_client_token")
    if not client_token:
        client_token = secrets.token_urlsafe(32)
        session["registration_client_token"] = client_token
    return client_token


def _store_face_data(face_data):
    FACE_CAPTURE_STORE[_get_client_token()] = face_data


def _get_face_data():
    return FACE_CAPTURE_STORE.get(_get_client_token())


def _clear_face_data():
    FACE_CAPTURE_STORE.pop(_get_client_token(), None)


def _cleanup_expired_otp_records():
    now = time.time()
    expired_tokens = [
        client_token
        for client_token, otp_record in OTP_STORE.items()
        if otp_record.get("expires_at", 0) <= now
    ]

    for client_token in expired_tokens:
        OTP_STORE.pop(client_token, None)


def _clear_otp_record():
    OTP_STORE.pop(_get_client_token(), None)


def _generate_otp():
    return f"{random.SystemRandom().randint(0, (10**OTP_LENGTH) - 1):0{OTP_LENGTH}d}"


def _get_smtp_config():
    smtp_host = os.getenv("SMTP_HOST", "").strip()
    smtp_port_value = os.getenv("SMTP_PORT", "587").strip() or "587"
    smtp_username = os.getenv("SMTP_USERNAME", "").strip()
    smtp_password = os.getenv("SMTP_PASSWORD", "").strip()
    smtp_from_email = os.getenv("SMTP_FROM_EMAIL", smtp_username).strip()
    smtp_from_name = os.getenv("SMTP_FROM_NAME", "NeoAttend").strip() or "NeoAttend"
    smtp_use_tls = os.getenv("SMTP_USE_TLS", "true").strip().lower() == "true"
    smtp_use_ssl = os.getenv("SMTP_USE_SSL", "false").strip().lower() == "true"

    try:
        smtp_port = int(smtp_port_value)
    except ValueError as exc:
        raise RuntimeError("SMTP_PORT must be a valid number.") from exc

    required_values = {
        "SMTP_HOST": smtp_host,
        "SMTP_PORT": str(smtp_port),
        "SMTP_USERNAME": smtp_username,
        "SMTP_PASSWORD": smtp_password,
        "SMTP_FROM_EMAIL": smtp_from_email,
    }
    missing_values = [key for key, value in required_values.items() if not value]

    if missing_values:
        raise RuntimeError(
            "Email service is not configured. Please set "
            + ", ".join(missing_values)
            + " in your .env file."
        )

    return {
        "host": smtp_host,
        "port": smtp_port,
        "username": smtp_username,
        "password": smtp_password,
        "from_email": smtp_from_email,
        "from_name": smtp_from_name,
        "use_tls": smtp_use_tls,
        "use_ssl": smtp_use_ssl,
    }


def send_email_message(recipient_email, subject, body):
    smtp_config = _get_smtp_config()

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"{smtp_config['from_name']} <{smtp_config['from_email']}>"
    message["To"] = recipient_email
    message.set_content(body)

    ssl_context = ssl.create_default_context()

    if smtp_config["use_ssl"]:
        with smtplib.SMTP_SSL(
            smtp_config["host"],
            smtp_config["port"],
            context=ssl_context,
        ) as smtp_server:
            smtp_server.login(smtp_config["username"], smtp_config["password"])
            smtp_server.send_message(message)
        return

    with smtplib.SMTP(smtp_config["host"], smtp_config["port"]) as smtp_server:
        smtp_server.ehlo()
        if smtp_config["use_tls"]:
            smtp_server.starttls(context=ssl_context)
            smtp_server.ehlo()
        smtp_server.login(smtp_config["username"], smtp_config["password"])
        smtp_server.send_message(message)


def send_otp_email(email, otp_code):
    send_email_message(
        recipient_email=email,
        subject="NeoAttend Email Verification OTP",
        body=(
            "Hello,\n\n"
            f"Your NeoAttend OTP for email verification is: {otp_code}\n\n"
            "This OTP will expire in 5 minutes.\n\n"
            "If you did not request this OTP, you can ignore this email.\n\n"
            "NeoAttend Team"
        ),
    )


def send_registration_confirmation_email(email, student_name, roll_no):
    send_email_message(
        recipient_email=email,
        subject="NeoAttend Registration Successful",
        body=(
            "Hello,\n\n"
            "You have been successfully registered in NeoAttend.\n\n"
            f"Student Name: {student_name}\n"
            f"Roll Number: {roll_no}\n\n"
            "You can now log in using your college email or roll number.\n\n"
            "NeoAttend Team"
        ),
    )


def _get_otp_record_for_email(email):
    _cleanup_expired_otp_records()

    otp_record = OTP_STORE.get(_get_client_token())
    if not otp_record:
        return None, "Please send an OTP to your college email first."

    if otp_record.get("email") != email:
        return None, "Please send a fresh OTP for the current college email."

    if otp_record.get("expires_at", 0) <= time.time():
        _clear_otp_record()
        return None, "OTP has expired. Please send a new OTP."

    return otp_record, None


def _is_email_verified(email):
    otp_record, otp_error = _get_otp_record_for_email(email)
    if otp_error:
        return False, otp_error

    if not otp_record.get("verified"):
        return False, "Please verify the OTP sent to your college email before registering."

    return True, None


# ---------------- REGISTER PAGE ----------------
@face_register_bp.route("/student/register")
def register_page():
    return render_template("register_enhanced.html")


@face_register_bp.route("/student/send-otp", methods=["POST"])
def send_registration_otp():
    _cleanup_expired_otp_records()
    email = normalize_email(request.form.get("email", ""))

    if not email:
        return jsonify({"success": False, "error": "Please enter your college email first."})

    if not is_valid_college_email(email):
        return jsonify(
            {
                "success": False,
                "error": "Only college email IDs ending with @axiscolleges.in are allowed.",
            }
        )

    db = get_db()
    cursor = db.cursor(buffered=True)

    try:
        cursor.execute(
            """
            SELECT id
            FROM students
            WHERE email = %s
            LIMIT 1
            """,
            (email,),
        )
        if cursor.fetchone():
            return jsonify(
                {
                    "success": False,
                    "error": "This college email is already registered.",
                }
            )
    finally:
        cursor.close()
        db.close()

    otp_code = _generate_otp()
    OTP_STORE[_get_client_token()] = {
        "email": email,
        "otp": otp_code,
        "verified": False,
        "expires_at": time.time() + OTP_VALIDITY_SECONDS,
        "attempts": 0,
    }

    try:
        send_otp_email(email, otp_code)
    except Exception as exc:
        _clear_otp_record()
        print(f"Error sending OTP email: {exc}")
        return jsonify(
            {
                "success": False,
                "error": f"OTP email could not be sent. {exc}",
            }
        )

    return jsonify(
        {
            "success": True,
            "message": "OTP sent successfully to your college email.",
            "expires_in": OTP_VALIDITY_SECONDS,
        }
    )


@face_register_bp.route("/student/verify-otp", methods=["POST"])
def verify_registration_otp():
    email = normalize_email(request.form.get("email", ""))
    otp_code = request.form.get("otp", "").strip()

    if not email:
        return jsonify({"success": False, "error": "Please enter your college email first."})

    if not otp_code:
        return jsonify({"success": False, "error": "Please enter the OTP sent to your email."})

    if not re.fullmatch(r"\d{6}", otp_code):
        return jsonify({"success": False, "error": "Please enter a valid 6-digit OTP."})

    otp_record, otp_error = _get_otp_record_for_email(email)
    if otp_error:
        return jsonify({"success": False, "error": otp_error})

    if otp_record["attempts"] >= OTP_MAX_ATTEMPTS:
        _clear_otp_record()
        return jsonify(
            {
                "success": False,
                "error": "Too many incorrect OTP attempts. Please send a new OTP.",
            }
        )

    if otp_record["otp"] != otp_code:
        otp_record["attempts"] += 1
        remaining_attempts = OTP_MAX_ATTEMPTS - otp_record["attempts"]
        if remaining_attempts <= 0:
            _clear_otp_record()
            return jsonify(
                {
                    "success": False,
                    "error": "Too many incorrect OTP attempts. Please send a new OTP.",
                }
            )

        return jsonify(
            {
                "success": False,
                "error": f"Incorrect OTP. {remaining_attempts} attempt(s) remaining.",
            }
        )

    otp_record["verified"] = True

    return jsonify(
        {
            "success": True,
            "message": "College email verified successfully.",
            "expires_in": max(0, int(otp_record["expires_at"] - time.time())),
        }
    )


# ---------------- CAPTURE FACE ----------------
@face_register_bp.route("/capture_face", methods=["POST"])
def capture_face():
    try:
        if "image" not in request.files:
            return jsonify({"success": False, "error": "No image provided"})

        file = request.files["image"]
        if file.filename == "":
            return jsonify({"success": False, "error": "No image selected"})

        image_bytes = file.read()
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
                    "error": "Multiple faces detected. Please capture only one student at a time.",
                }
            )

        new_encoding = encodings[0]
        if has_duplicate_face(new_encoding):
            return jsonify(
                {
                    "success": False,
                    "error": "This face is already registered in the system.",
                }
            )

        _store_face_data(pickle.dumps(new_encoding))

        return jsonify(
            {
                "success": True,
                "message": "Face captured successfully. You can now register the student.",
            }
        )

    except Exception as e:
        print(f"Error in capture_face: {e}")
        return jsonify(
            {
                "success": False,
                "error": "An error occurred while capturing face. Please try again.",
            }
        )


# ---------------- SAVE STUDENT ----------------
@face_register_bp.route("/student/save", methods=["POST"])
def register_student():
    try:
        face_data = _get_face_data()
        if face_data is None:
            return jsonify(
                {
                    "success": False,
                    "error": "Please capture face first before registering the student.",
                }
            )

        name = request.form.get("name", "").strip()
        email = normalize_email(request.form.get("email", ""))
        roll_no = request.form.get("roll_no", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        section_id = request.form.get("section_id", "").strip()

        if not name or not email or not roll_no or not password or not confirm_password or not section_id:
            return jsonify(
                {
                    "success": False,
                    "error": "All fields are required. Please fill in all the information.",
                }
            )

        if not is_valid_college_email(email):
            return jsonify(
                {
                    "success": False,
                    "error": "Only college email IDs ending with @axiscolleges.in are allowed.",
                }
            )

        password_error = validate_password_strength(password)
        if password_error:
            return jsonify({"success": False, "error": password_error})

        if password != confirm_password:
            return jsonify({"success": False, "error": "Passwords do not match."})

        email_verified, verification_error = _is_email_verified(email)
        if not email_verified:
            return jsonify({"success": False, "error": verification_error})

        try:
            section_id = int(section_id)
            if section_id not in [1, 2, 3]:
                return jsonify({"success": False, "error": "Invalid section selected."})
        except ValueError:
            return jsonify({"success": False, "error": "Invalid section selected."})

        db = get_db()
        cursor = db.cursor(buffered=True)

        try:
            cursor.execute(
                """
                SELECT id
                FROM students
                WHERE roll_no = %s OR email = %s
                LIMIT 1
                """,
                (roll_no, email),
            )
            if cursor.fetchone():
                return jsonify(
                    {
                        "success": False,
                        "error": "This roll number or college email is already registered.",
                    }
                )

            hashed_password = generate_password_hash(password)
            cursor.execute(
                """
                INSERT INTO students (name, email, password, roll_no, section_id, face_data)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (name, email, hashed_password, roll_no, section_id, face_data),
            )
            db.commit()

            # Refresh the matcher cache so the new student is recognized immediately.
            try:
                from face.face_match_enhanced import refresh_encodings_cache

                refresh_encodings_cache()
            except Exception as cache_error:
                print(f"Warning: could not refresh face cache after registration: {cache_error}")

            email_warning = None
            try:
                send_registration_confirmation_email(email, name, roll_no)
            except Exception as email_error:
                email_warning = f"Registration succeeded, but the confirmation email could not be sent: {email_error}"
                print(f"Warning: confirmation email could not be sent: {email_error}")

            _clear_face_data()
            _clear_otp_record()

            return jsonify(
                {
                    "success": True,
                    "message": "Student registered successfully.",
                    "warning": email_warning,
                }
            )

        except mysql.connector.IntegrityError as e:
            if "Duplicate entry" in str(e):
                if "roll_no" in str(e):
                    return jsonify(
                        {
                            "success": False,
                            "error": "This roll number is already registered in this section.",
                        }
                    )
                return jsonify({"success": False, "error": "Duplicate entry detected."})

            return jsonify({"success": False, "error": f"Database error: {e}"})
        except Exception as e:
            return jsonify({"success": False, "error": f"Database error: {e}"})
        finally:
            cursor.close()
            db.close()

    except Exception as e:
        print(f"Error in register_student: {e}")
        return jsonify(
            {
                "success": False,
                "error": "An error occurred while registering student. Please try again.",
            }
        )


# ---------------- LEGACY ROUTES FOR BACKWARDS COMPATIBILITY ----------------
@face_register_bp.route("/capture_face_legacy", methods=["POST"])
def capture_face_legacy():
    """Legacy route for backwards compatibility."""
    try:
        frame, camera_error = read_camera_frame()
        if frame is None:
            return render_template(
                "register_enhanced.html",
                face_ready=False,
                face_msg=camera_error or "Camera not working",
                reg_msg="",
            )

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        encodings = face_recognition.face_encodings(rgb)

        if len(encodings) == 0:
            return render_template(
                "register_enhanced.html",
                face_ready=False,
                face_msg="No face detected",
                reg_msg="",
            )

        if len(encodings) > 1:
            return render_template(
                "register_enhanced.html",
                face_ready=False,
                face_msg="Multiple faces detected",
                reg_msg="",
            )

        new_encoding = encodings[0]
        if has_duplicate_face(new_encoding):
            return render_template(
                "register_enhanced.html",
                face_ready=False,
                face_msg="This face is already registered",
                reg_msg="",
            )

        _store_face_data(pickle.dumps(new_encoding))

        return render_template(
            "register_enhanced.html",
            face_ready=True,
            face_msg="Face successfully captured",
            reg_msg="",
        )

    except Exception as e:
        print(f"Error in legacy capture: {e}")
        return render_template(
            "register_enhanced.html",
            face_ready=False,
            face_msg="Error capturing face",
            reg_msg="",
        )


@face_register_bp.route("/student/save_legacy", methods=["POST"])
def register_student_legacy():
    """Legacy route for backwards compatibility."""
    face_data = _get_face_data()

    if face_data is None:
        return render_template(
            "register_enhanced.html",
            face_ready=False,
            face_msg="Please capture face first",
            reg_msg="",
        )

    name = request.form["name"].strip()
    roll_no = request.form["roll_no"].strip()
    section_id = request.form["section_id"]

    if not name or not roll_no or not section_id:
        return render_template(
            "register_enhanced.html",
            face_ready=True,
            face_msg="",
            reg_msg="All fields required",
        )

    try:
        db = get_db()
        cursor = db.cursor(buffered=True)
        cursor.execute(
            """
            INSERT INTO students (name, roll_no, section_id, face_data)
            VALUES (%s, %s, %s, %s)
            """,
            (name, roll_no, section_id, face_data),
        )
        db.commit()

        try:
            from face.face_match_enhanced import refresh_encodings_cache

            refresh_encodings_cache()
        except Exception as cache_error:
            print(f"Warning: could not refresh face cache after legacy registration: {cache_error}")

        _clear_face_data()

        return render_template(
            "register_enhanced.html",
            face_ready=False,
            face_msg="",
            reg_msg="Student registered successfully",
        )

    except Exception as e:
        return render_template(
            "register_enhanced.html",
            face_ready=False,
            face_msg="",
            reg_msg=f"Database error: {e}",
        )
    finally:
        cursor.close()
        db.close()
