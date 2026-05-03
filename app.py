import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, redirect, render_template, session, url_for
from database.mysql_connection import ensure_dashboard_tables, ensure_student_auth_columns

BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"
load_dotenv(dotenv_path=ENV_FILE, override=True)

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "neoattend_secret_key")

try:
    ensure_student_auth_columns()
except Exception as e:
    print(f"Student auth schema check warning: {e}")

try:
    ensure_dashboard_tables()
except Exception as e:
    print(f"Dashboard schema check warning: {e}")

@app.route("/")
def home():
    # Check if user is already logged in
    if 'teacher_id' in session:
        role = session.get('role', '')
        
        # Smart role-based redirection
        if role == 'admin':
            return redirect(url_for('admin.admin_dashboard'))
        elif role == 'teacher':
            return redirect(url_for('teacher.teacher_dashboard'))
    
    
    elif 'student_id' in session:
        # Student is logged in
        return redirect(url_for('student.student_dashboard'))
    
    # Show login selection page for non-logged users
    return render_template("login_selection.html")

from face.face_save_enhanced import face_register_bp
from face.face_match_enhanced import face_bp
from teacher.routes import teacher_bp
from admin.routes import admin_bp
from student.routes import student_bp

app.register_blueprint(face_register_bp)
app.register_blueprint(face_bp)
app.register_blueprint(teacher_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(student_bp)

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)
