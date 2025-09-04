import sqlite3

try:
    conn = sqlite3.connect('database.db')
    cur = conn.cursor()
    
    # Check if BOD_Name table exists
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='BOD_Name'")
    table_exists = cur.fetchone() is not None
    print(f"BOD_Name table exists: {table_exists}")
    
    if table_exists:
        # Check table structure
        cur.execute("PRAGMA table_info(BOD_Name)")
        columns = cur.fetchall()
        print(f"BOD_Name table columns: {columns}")
        
        # Check data
        cur.execute("SELECT * FROM BOD_Name LIMIT 5")
        data = cur.fetchall()
        print(f"BOD_Name data: {data}")
        
        # Count rows
        cur.execute("SELECT COUNT(*) FROM BOD_Name")
        count = cur.fetchone()[0]
        print(f"BOD_Name row count: {count}")
    
    conn.close()
    
except Exception as e:
    print(f"Error: {e}")
