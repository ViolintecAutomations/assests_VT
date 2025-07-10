import MySQLdb

# Database connection
db = MySQLdb.connect(
    host='localhost',
    user='root',
    passwd='Violin@12',
    db='CMS'
)

cursor = db.cursor()

print("Fixing documents table structure...")

# Add filename column if it doesn't exist
cursor.execute("SHOW COLUMNS FROM documents LIKE 'filename'")
if not cursor.fetchone():
    print("Adding filename column...")
    cursor.execute("ALTER TABLE documents ADD COLUMN filename VARCHAR(255) NOT NULL")
    db.commit()
    print("filename column added!")

# Add upload_date column if it doesn't exist
cursor.execute("SHOW COLUMNS FROM documents LIKE 'upload_date'")
if not cursor.fetchone():
    print("Adding upload_date column...")
    cursor.execute("ALTER TABLE documents ADD COLUMN upload_date DATETIME DEFAULT CURRENT_TIMESTAMP")
    db.commit()
    print("upload_date column added!")

# Show final table structure
print("\nFinal documents table structure:")
cursor.execute("DESCRIBE documents")
for row in cursor.fetchall():
    print(row)

cursor.close()
db.close()
print("\nDocuments table fixed!") 