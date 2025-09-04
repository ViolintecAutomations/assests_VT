import pymysql
import csv
import os
from datetime import datetime, timedelta

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

def test_printer_readings():
    """Test the printer readings functionality"""
    conn = get_db_connection('Assert_IT')
    cur = conn.cursor()
    
    try:
        # Check if bod_printer_data table exists
        cur.execute("SHOW TABLES LIKE 'bod_printer_data'")
        table_exists = cur.fetchone() is not None
        print(f"bod_printer_data table exists: {table_exists}")
        
        if table_exists:
            # Check table structure
            cur.execute("DESCRIBE bod_printer_data")
            columns = cur.fetchall()
            print(f"Table columns: {columns}")
            
            # Check if there's any data
            cur.execute("SELECT COUNT(*) FROM bod_printer_data")
            total_count = cur.fetchone()[0]
            print(f"Total records in bod_printer_data: {total_count}")
            
            if total_count > 0:
                # Show sample data
                cur.execute("SELECT * FROM bod_printer_data LIMIT 5")
                sample_data = cur.fetchall()
                print(f"Sample data: {sample_data}")
                
                # Check data for specific locations
                locations = ['unit-1', 'unit-2', 'unit-3', 'unit-4', 'unit-5', 'GSS']
                for location in locations:
                    cur.execute("SELECT COUNT(*) FROM bod_printer_data WHERE unit = %s", (location,))
                    count = cur.fetchone()[0]
                    print(f"Records for {location}: {count}")
                    
                    if count > 0:
                        cur.execute("SELECT * FROM bod_printer_data WHERE unit = %s ORDER BY report_date DESC LIMIT 3", (location,))
                        location_data = cur.fetchall()
                        print(f"Recent data for {location}: {location_data}")
            
            # Check yesterday's data specifically
            yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
            print(f"\nChecking for yesterday's data: {yesterday}")
            
            cur.execute("SELECT COUNT(*) FROM bod_printer_data WHERE report_date = %s", (yesterday,))
            yesterday_count = cur.fetchone()[0]
            print(f"Records for yesterday ({yesterday}): {yesterday_count}")
            
            if yesterday_count > 0:
                cur.execute("SELECT * FROM bod_printer_data WHERE report_date = %s", (yesterday,))
                yesterday_data = cur.fetchall()
                print(f"Yesterday's data: {yesterday_data}")
            
            # Check for any recent data (last 7 days)
            week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
            cur.execute("SELECT COUNT(*) FROM bod_printer_data WHERE report_date >= %s", (week_ago,))
            recent_count = cur.fetchone()[0]
            print(f"Records for last 7 days: {recent_count}")
            
            if recent_count > 0:
                cur.execute("SELECT unit, report_date, COUNT(*) FROM bod_printer_data WHERE report_date >= %s GROUP BY unit, report_date ORDER BY report_date DESC", (week_ago,))
                recent_data = cur.fetchall()
                print(f"Recent data summary: {recent_data}")
        
        # Check if there are any printer names in the saved BOD reports
        cur.execute("SHOW TABLES LIKE 'saved_bod_reports'")
        saved_reports_exists = cur.fetchone() is not None
        print(f"\nsaved_bod_reports table exists: {saved_reports_exists}")
        
        if saved_reports_exists:
            cur.execute("SELECT COUNT(*) FROM saved_bod_reports")
            saved_count = cur.fetchone()[0]
            print(f"Total saved BOD reports: {saved_count}")
            
            if saved_count > 0:
                # Check if any reports contain printer data
                cur.execute("SELECT id, date, location, report_data FROM saved_bod_reports WHERE report_data LIKE '%printers%' LIMIT 3")
                printer_reports = cur.fetchall()
                print(f"Reports with printer data: {len(printer_reports)}")
                
                for report in printer_reports:
                    print(f"Report ID: {report['id']}, Date: {report['date']}, Location: {report['location']}")
                    # Check if report_data contains printer information
                    if 'printers' in str(report['report_data']):
                        print("  Contains printer data")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    test_printer_readings()
