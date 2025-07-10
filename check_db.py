import MySQLdb

DB_HOST = 'localhost'
DB_USER = 'root'
DB_PASS = 'Violin@12'
DB_NAME = 'CMS'

required_tables = [
    'users', 'assets', 'assignments', 'requests', 'documents', 'maintenance', 'audit_logs', 'notifications'
]

conn = MySQLdb.connect(host=DB_HOST, user=DB_USER, passwd=DB_PASS, db=DB_NAME)
cursor = conn.cursor()

# Check tables
cursor.execute("SHOW TABLES;")
tables = set(row[0] for row in cursor.fetchall())
missing = [t for t in required_tables if t not in tables]
if missing:
    print(f"Missing tables: {missing}")
else:
    print("All required tables exist.")

# Check default users
cursor.execute("SELECT email, role FROM users WHERE email IN ('admin@assetms.com', 'user@assetms.com')")
users = cursor.fetchall()
if users:
    print("Default users found:", users)
else:
    print("Default users NOT found.")

# Check if documents table exists
cursor.execute("SHOW TABLES LIKE 'documents'")
if not cursor.fetchone():
    print("Documents table does not exist. Creating it...")
    cursor.execute("""
        CREATE TABLE documents (
            id INT AUTO_INCREMENT PRIMARY KEY,
            asset_id INT,
            filename VARCHAR(255) NOT NULL,
            filetype VARCHAR(50),
            upload_date DATETIME DEFAULT CURRENT_TIMESTAMP,
            uploaded_by INT,
            doc_type VARCHAR(50),
            FOREIGN KEY (asset_id) REFERENCES assets(id),
            FOREIGN KEY (uploaded_by) REFERENCES users(id)
        )
    """)
    conn.commit()
    print("Documents table created successfully!")
else:
    print("Documents table exists. Checking columns...")
    
    # Check for filename column
    cursor.execute("SHOW COLUMNS FROM documents LIKE 'filename'")
    if not cursor.fetchone():
        print("Adding filename column...")
        cursor.execute("ALTER TABLE documents ADD COLUMN filename VARCHAR(255) NOT NULL")
        conn.commit()
        print("filename column added!")
    
    # Check for upload_date column
    cursor.execute("SHOW COLUMNS FROM documents LIKE 'upload_date'")
    if not cursor.fetchone():
        print("Adding upload_date column...")
        cursor.execute("ALTER TABLE documents ADD COLUMN upload_date DATETIME DEFAULT CURRENT_TIMESTAMP")
        conn.commit()
        print("upload_date column added!")

# Show final table structure
print("\nFinal documents table structure:")
cursor.execute("DESCRIBE documents")
for row in cursor.fetchall():
    print(row)

cursor.close()
conn.close()
print("\nDatabase check completed!") 