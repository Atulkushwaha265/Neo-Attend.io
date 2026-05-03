from functools import wraps
from flask import session, redirect, url_for, flash

def role_required(*allowed_roles):
    """Decorator to ensure user has required role"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Check if user is logged in
            if 'teacher_id' not in session:
                flash('Please login to access this page', 'error')
                return redirect(url_for('teacher.login'))
            
            # Check if user has required role
            user_role = session.get('role')
            if user_role not in allowed_roles:
                flash('You do not have permission to access this page', 'error')
                return redirect(url_for('teacher.login'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def admin_required(f):
    """Decorator specifically for admin routes"""
    return role_required('admin')(f)

def teacher_required(f):
    """Decorator specifically for teacher routes"""
    return role_required('teacher', 'admin')(f)  # Admin can also access teacher routes
