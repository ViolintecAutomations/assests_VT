#!/usr/bin/env python3
import pymysql

def setup_approvers():
    """Set up the approvers table and insert 4 specific approvers"""
    
    # Database connection
    conn = pymysql.connect(
        host='localhost',
        user='root',
        password='Violin@12',
        database='CMS',
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )
    
    cur = conn.cursor()
    
    try:
        # Create approvers table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS approvers (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                email VARCHAR(100) UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Insert 4 specific approvers
        approvers = [
            ('John Smith', 'john.smith@company.com'),
            ('Sarah Johnson', 'sarah.johnson@company.com'),
            ('Mike Davis', 'mike.davis@company.com'),
            ('Lisa Wilson', 'lisa.wilson@company.com')
        ]
        
        for name, email in approvers:
            try:
                cur.execute('INSERT INTO approvers (name, email) VALUES (%s, %s)', (name, email))
                print(f"✓ Added approver: {name} ({email})")
            except pymysql.err.IntegrityError:
                print(f"⚠ Approver already exists: {name} ({email})")
        
        conn.commit()
        print("\n✅ Approvers setup completed successfully!")
        
        # Show current approvers
        cur.execute('SELECT * FROM approvers ORDER BY name')
        current_approvers = cur.fetchall()
        print(f"\n📋 Current approvers in database:")
        for approver in current_approvers:
            print(f"  - {approver['name']} ({approver['email']})")
        
    except Exception as e:
        print(f"❌ Error setting up approvers: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    setup_approvers()
