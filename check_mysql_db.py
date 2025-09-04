import pymysql
import csv
import os

def CSV_Proj_Params(proj_name):
    CSV_File_Name = 'All_Projects.csv'
    base_path = os.path.dirname(os.path.dirname(__file__))
    csv_path = os.path.join(base_path, CSV_File_Name)
    config = {}
    try:
        with open(csv_path, mode='r', newline='') as file:
            reader = csv.DictReader(file)
            for row in reader:
                if row['Project_Name'] == proj_name:
                    config = {
                        'MYSQL_HOST': row['MYSQL_HOST'],
                        'MYSQL_PORT': int(row['MYSQL_PORT']),
                        'MYSQL_USER': row['MYSQL_USER'],
                        'MYSQL_PASSWORD': row['MYSQL_PASSWORD'],
                        'MYSQL_DB': row['MYSQL_DB'],
                        'MYSQL_CURSORCLASS': row['MYSQL_CURSORCLASS']
                    }
                    break
    except Exception as e:
        print(f"Error loading DB config: {e}")
    return config

def get_db_connection(proj_name, auto_commit=True):
    proj_params = CSV_Proj_Params(proj_name)
    conn = pymysql.connect(
        host=proj_params.get('MYSQL_HOST'),
        port=int(proj_params.get('MYSQL_PORT')),
        user=proj_params.get('MYSQL_USER'),
        password=proj_params.get('MYSQL_PASSWORD'),
        database=proj_params.get('MYSQL_DB'),
        cursorclass=getattr(pymysql.cursors, proj_params.get('MYSQL_CURSORCLASS')),
        autocommit=auto_commit
    )
    return conn

def create_bod_name_table():
    """Create BOD_Name table with BOD_Name_Data column"""
    conn = get_db_connection('Assert_IT')
    cur = conn.cursor()
    
    try:
        cur.execute('''
            CREATE TABLE IF NOT EXISTS BOD_Name (
                id INT PRIMARY KEY AUTO_INCREMENT,
                BOD_Name_Data VARCHAR(255) NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Insert sample BOD names
        sample_names = [
            'Renganathan T',
            'IT Manager',
            'System Administrator',
            'Network Engineer',
            'Support Team'
        ]
        
        for name in sample_names:
            try:
                cur.execute('INSERT IGNORE INTO BOD_Name (BOD_Name_Data) VALUES (%s)', (name,))
            except Exception as e:
                print(f"Warning: Could not insert sample BOD name {name}: {e}")
        
        conn.commit()
        print("BOD_Name table created successfully with sample data")
        return True
    except Exception as e:
        conn.rollback()
        print(f"Error creating BOD_Name table: {e}")
        return False
    finally:
        cur.close()
        conn.close()

def check_bod_name_table():
    """Check if BOD_Name table exists and has data"""
    conn = get_db_connection('Assert_IT')
    cur = conn.cursor()
    
    try:
        # Check if table exists
        cur.execute("SHOW TABLES LIKE 'BOD_Name'")
        table_exists = cur.fetchone() is not None
        print(f"BOD_Name table exists: {table_exists}")
        
        if table_exists:
            # Check table structure
            cur.execute("DESCRIBE BOD_Name")
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
        else:
            print("Creating BOD_Name table...")
            create_bod_name_table()
            check_bod_name_table()
    
    except Exception as e:
        print(f"Error: {e}")
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    check_bod_name_table()
