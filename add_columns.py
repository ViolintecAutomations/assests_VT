import pymysql

# Database configuration
config = {
    'host': 'localhost',
    'user': 'root',
    'password': 'Violin@12',
    'db': 'CMS',
    'cursorclass': pymysql.cursors.DictCursor,
    'autocommit': True
}

def add_columns():
    try:
        conn = pymysql.connect(**config)
        cur = conn.cursor()
        
        # Add from_field column if it doesn't exist
        try:
            cur.execute("ALTER TABLE purchase_requests ADD COLUMN from_field VARCHAR(255) AFTER justification")
            print("Added from_field column")
        except Exception as e:
            if "Duplicate column name" in str(e):
                print("from_field column already exists")
            else:
                print(f"Error adding from_field: {e}")
        
        # Add for_field column if it doesn't exist
        try:
            cur.execute("ALTER TABLE purchase_requests ADD COLUMN for_field VARCHAR(255) AFTER from_field")
            print("Added for_field column")
        except Exception as e:
            if "Duplicate column name" in str(e):
                print("for_field column already exists")
            else:
                print(f"Error adding for_field: {e}")
        
        # Update existing records to have default values
        cur.execute("UPDATE purchase_requests SET from_field = 'Not specified' WHERE from_field IS NULL")
        cur.execute("UPDATE purchase_requests SET for_field = 'Not specified' WHERE for_field IS NULL")
        print("Updated existing records with default values")
        
        cur.close()
        conn.close()
        print("Database migration completed successfully!")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    add_columns()






