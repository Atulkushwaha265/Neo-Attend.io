from database.mysql_connection import get_db

# Clean up duplicate sections
db = get_db()
cursor = db.cursor(buffered=True)

print("🧹 Cleaning up duplicate sections...")

# Disable foreign key checks temporarily
cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
print("🔓 Disabled foreign key checks")

# Delete all sections first
cursor.execute("DELETE FROM sections")
print("❌ Deleted all existing sections")

# Insert fresh sections
cursor.execute("""
INSERT INTO sections (section_name) VALUES ('A'), ('B'), ('C')
""")
print("✅ Inserted fresh sections: A, B, C")

# Re-enable foreign key checks
cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
print("🔒 Re-enabled foreign key checks")

db.commit()
cursor.close()
db.close()

print("🎉 Sections cleanup completed!")

# Verify
db = get_db()
cursor = db.cursor(buffered=True)
cursor.execute("SELECT section_id, section_name FROM sections ORDER BY section_id")
sections = cursor.fetchall()
print("\n📋 Current sections:")
for section in sections:
    print(f'ID: {section[0]}, Name: {section[1]}')
cursor.close()
db.close()
