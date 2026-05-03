import mysql.connector

conn = mysql.connector.connect(
    host="localhost",
    user="root",
    password="#@wj$12#atul",
    database="neoattend"
)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS students (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255),
    encoding LONGBLOB
)
""")

conn.commit()
conn.close()

print("✅ Database and table ready in MySQL")
