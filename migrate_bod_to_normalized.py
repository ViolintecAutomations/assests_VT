#!/usr/bin/env python3
"""
Migration script to convert existing JSON BOD report data to normalized structure
"""

import mysql.connector
import json
from datetime import datetime
import sys

# Database configuration
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '',
    'database': 'it_asset_management',
    'charset': 'utf8mb4',
    'autocommit': False
}

def migrate_bod_data():
    """Migrate existing JSON BOD data to normalized structure"""
    
    try:
        # Connect to database
        conn = mysql.connector.connect(**DB_CONFIG)
        cur = conn.cursor()
        
        print("Starting BOD data migration to normalized structure...")
        
        # Get all existing JSON reports
        cur.execute('''
            SELECT id, name, date, location, secondary_internet, report_data, submitted_time
            FROM saved_bod_reports
            ORDER BY date DESC, submitted_time DESC
        ''')
        
        existing_reports = cur.fetchall()
        print(f"Found {len(existing_reports)} existing reports to migrate")
        
        migrated_count = 0
        skipped_count = 0
        
        for report in existing_reports:
            old_id, name, date, location, secondary_internet, report_data_json, submitted_time = report
            
            try:
                # Parse JSON data
                report_data = json.loads(report_data_json) if report_data_json else {}
                
                # Check if already migrated
                cur.execute('''
                    SELECT id FROM bod_reports_normalized 
                    WHERE report_name = %s AND report_date = %s AND location = %s
                ''', (name, date, location))
                
                if cur.fetchone():
                    print(f"Skipping already migrated report: {name} - {date} - {location}")
                    skipped_count += 1
                    continue
                
                # Insert into normalized BOD reports table
                cur.execute('''
                    INSERT INTO bod_reports_normalized 
                    (report_name, report_date, location, secondary_internet, submitted_time, submitted_by)
                    VALUES (%s, %s, %s, %s, %s, 1)
                ''', (name, date, location, secondary_internet, submitted_time))
                
                report_id = cur.lastrowid
                
                # Migrate network items
                if 'network' in report_data:
                    for item in report_data['network']:
                        cur.execute('''
                            INSERT INTO bod_network_items 
                            (report_id, sno, leased_line, link, status, reason, remarks, checked_time)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ''', (
                            report_id, item.get('sno'), item.get('leased_line'), item.get('link'),
                            item.get('status'), item.get('reason'), item.get('remarks'), item.get('checked_time')
                        ))
                
                # Migrate server connectivity items
                if 'server_connectivity' in report_data:
                    for item in report_data['server_connectivity']:
                        cur.execute('''
                            INSERT INTO bod_server_items 
                            (report_id, sno, server_name, status, reason, remarks, checked_time)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ''', (
                            report_id, item.get('sno'), item.get('server_name'),
                            item.get('status'), item.get('reason'), item.get('remarks'), item.get('checked_time')
                        ))
                
                # Migrate security items
                if 'security' in report_data:
                    for item in report_data['security']:
                        cur.execute('''
                            INSERT INTO bod_security_items 
                            (report_id, sno, security_device, location, status, remarks, checked_time)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ''', (
                            report_id, item.get('sno'), item.get('security_device'), item.get('location'),
                            item.get('status'), item.get('remarks'), item.get('checked_time')
                        ))
                
                # Migrate telecom items
                if 'telecom' in report_data:
                    for item in report_data['telecom']:
                        cur.execute('''
                            INSERT INTO bod_telecom_items 
                            (report_id, sno, name, status, reason, remarks, checked_time)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ''', (
                            report_id, item.get('sno'), item.get('name'),
                            item.get('status'), item.get('reason'), item.get('remarks'), item.get('checked_time')
                        ))
                
                # Migrate other items
                if 'others' in report_data:
                    for item in report_data['others']:
                        cur.execute('''
                            INSERT INTO bod_other_items 
                            (report_id, sno, item, status, reason, remarks, checked_time)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ''', (
                            report_id, item.get('sno'), item.get('item'),
                            item.get('status'), item.get('reason'), item.get('remarks'), item.get('checked_time')
                        ))
                
                # Migrate antivirus items
                if 'antivirus' in report_data:
                    for item in report_data['antivirus']:
                        cur.execute('''
                            INSERT INTO bod_antivirus_items 
                            (report_id, sno, system_name, antivirus_status, last_updated, remarks, checked_time)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ''', (
                            report_id, item.get('sno'), item.get('system_name'), item.get('antivirus_status'),
                            item.get('last_updated'), item.get('remarks'), item.get('checked_time')
                        ))
                
                # Migrate common sharing items
                if 'common_sharing' in report_data:
                    for item in report_data['common_sharing']:
                        cur.execute('''
                            INSERT INTO bod_sharing_items 
                            (report_id, sno, folder_name, access_rights, status, remarks, checked_time)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ''', (
                            report_id, item.get('sno'), item.get('folder_name'), item.get('access_rights'),
                            item.get('status'), item.get('remarks'), item.get('checked_time')
                        ))
                
                # Migrate tech room items
                if 'tech_room' in report_data:
                    for item in report_data['tech_room']:
                        cur.execute('''
                            INSERT INTO bod_techroom_items 
                            (report_id, sno, equipment, status, reason, remarks, checked_time)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ''', (
                            report_id, item.get('sno'), item.get('equipment'),
                            item.get('status'), item.get('reason'), item.get('remarks'), item.get('checked_time')
                        ))
                
                # Update existing printer data to link with new report
                cur.execute('''
                    UPDATE bod_printer_data 
                    SET report_id = %s 
                    WHERE report_date = %s AND unit = %s
                ''', (report_id, date, location))
                
                migrated_count += 1
                print(f"Migrated report: {name} - {date} - {location}")
                
            except Exception as e:
                print(f"Error migrating report {name} - {date} - {location}: {e}")
                conn.rollback()
                continue
        
        conn.commit()
        cur.close()
        conn.close()
        
        print(f"\nMigration completed!")
        print(f"Successfully migrated: {migrated_count} reports")
        print(f"Skipped (already migrated): {skipped_count} reports")
        print(f"Total processed: {len(existing_reports)} reports")
        
    except Exception as e:
        print(f"Migration failed: {e}")
        sys.exit(1)

if __name__ == '__main__':
    migrate_bod_data()
