import pymysql
import sys

def setup_admin_permissions():
    try:
        # Connect to database
        conn = pymysql.connect(
            host='localhost',
            user='root',
            password='Violin@12',
            database='CMS',
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )
        
        cur = conn.cursor()
        
        # Create admin_menu_permissions table
        print("Creating admin_menu_permissions table...")
        cur.execute('''
            CREATE TABLE IF NOT EXISTS admin_menu_permissions (
                id INT PRIMARY KEY AUTO_INCREMENT,
                user_id INT NOT NULL,
                menu_item VARCHAR(50) NOT NULL,
                is_allowed BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                UNIQUE KEY unique_user_menu (user_id, menu_item)
            )
        ''')
        
        # Insert default menu items for existing admin users
        print("Setting up default permissions for existing admin users...")
        
        # Get all admin users
        cur.execute('SELECT id FROM users WHERE role = "admin"')
        admin_users = cur.fetchall()
        
        menu_items = ['dashboard', 'procurement', 'asset_master', 'assign_asset', 'requests', 'user_management', 'bod_report', 'daily_infrastructure']
        
        for user in admin_users:
            user_id = user['id']
            for menu_item in menu_items:
                try:
                    cur.execute('''
                        INSERT INTO admin_menu_permissions (user_id, menu_item, is_allowed)
                        VALUES (%s, %s, %s)
                        ON DUPLICATE KEY UPDATE is_allowed = VALUES(is_allowed)
                    ''', (user_id, menu_item, True))
                except Exception as e:
                    print(f"Error inserting permission for user {user_id}, menu {menu_item}: {e}")
        
        conn.commit()
        print(f"✅ Successfully set up admin permissions for {len(admin_users)} admin users")
        
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Error setting up admin permissions: {e}")
        sys.exit(1)

if __name__ == "__main__":
    setup_admin_permissions()

