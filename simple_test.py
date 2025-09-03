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

def check_printer_data():
    conn = get_db_connection('Assert_IT')
    cur = conn.cursor()
    
    try:
        # Check total count
        cur.execute("SELECT COUNT(*) FROM bod_printer_data")
        count = cur.fetchone()[0]
        print(f"Total printer records: {count}")
        
        if count > 0:
            # Check recent data
            cur.execute("SELECT unit, report_date, printer_name, today_reading FROM bod_printer_data ORDER BY report_date DESC LIMIT 10")
            recent = cur.fetchall()
            print(f"Recent records: {len(recent)}")
            for row in recent:
                print(f"  {row['unit']} - {row['report_date']} - {row['printer_name']} - {row['today_reading']}")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    check_printer_data()
