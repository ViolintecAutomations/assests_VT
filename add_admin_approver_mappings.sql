-- Add Admin-Approver Mappings table to existing database
CREATE TABLE IF NOT EXISTS admin_approver_mappings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    admin_id INT NOT NULL,
    approver_id INT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (admin_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (approver_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE KEY unique_admin_approver (admin_id, approver_id)
);
