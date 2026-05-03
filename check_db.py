import mysql.connector

# Connect to database
conn = mysql.connector.connect(
    host="localhost",
    user="root",
    password="#@wj$12#atul",
    database="neoattend"
)
cursor = conn.cursor()

# Check if there are any students with face data
cursor.execute("SELECT COUNT(*) FROM students WHERE face_data IS NOT NULL")
face_count = cursor.fetchone()[0]
print(f"Students with face data: {face_count}")

# Check total students
cursor.execute("SELECT COUNT(*) FROM students")
total_students = cursor.fetchone()[0]
print(f"Total students: {total_students}")

# Show student details
cursor.execute("SELECT id, name, roll_no, section_id, face_data IS NOT NULL FROM students")
students = cursor.fetchall()
print("\nStudent Details:")
for student in students:
    print(f"ID: {student[0]}, Name: {student[1]}, Roll: {student[2]}, Section: {student[3]}, Has Face: {student[4]}")

cursor.close()
conn.close()
