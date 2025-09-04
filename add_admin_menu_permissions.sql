-- Create table for admin menu permissions
CREATE TABLE IF NOT EXISTS admin_menu_permissions (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    menu_item VARCHAR(50) NOT NULL,
    is_allowed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE KEY unique_user_menu (user_id, menu_item)
);

-- Insert default menu items for existing admin users
INSERT INTO admin_menu_permissions (user_id, menu_item, is_allowed) 
SELECT u.id, 'dashboard', TRUE FROM users u WHERE u.role = 'admin'
ON DUPLICATE KEY UPDATE is_allowed = TRUE;

INSERT INTO admin_menu_permissions (user_id, menu_item, is_allowed) 
SELECT u.id, 'procurement', TRUE FROM users u WHERE u.role = 'admin'
ON DUPLICATE KEY UPDATE is_allowed = TRUE;

INSERT INTO admin_menu_permissions (user_id, menu_item, is_allowed) 
SELECT u.id, 'asset_master', TRUE FROM users u WHERE u.role = 'admin'
ON DUPLICATE KEY UPDATE is_allowed = TRUE;

INSERT INTO admin_menu_permissions (user_id, menu_item, is_allowed) 
SELECT u.id, 'assign_asset', TRUE FROM users u WHERE u.role = 'admin'
ON DUPLICATE KEY UPDATE is_allowed = TRUE;

INSERT INTO admin_menu_permissions (user_id, menu_item, is_allowed) 
SELECT u.id, 'requests', TRUE FROM users u WHERE u.role = 'admin'
ON DUPLICATE KEY UPDATE is_allowed = TRUE;

INSERT INTO admin_menu_permissions (user_id, menu_item, is_allowed) 
SELECT u.id, 'user_management', TRUE FROM users u WHERE u.role = 'admin'
ON DUPLICATE KEY UPDATE is_allowed = TRUE;

INSERT INTO admin_menu_permissions (user_id, menu_item, is_allowed) 
SELECT u.id, 'bod_report', TRUE FROM users u WHERE u.role = 'admin'
ON DUPLICATE KEY UPDATE is_allowed = TRUE;

INSERT INTO admin_menu_permissions (user_id, menu_item, is_allowed) 
SELECT u.id, 'daily_infrastructure', TRUE FROM users u WHERE u.role = 'admin'
ON DUPLICATE KEY UPDATE is_allowed = TRUE;

