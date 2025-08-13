-- Asset Management System Database Schema

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(100) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    name VARCHAR(100),
    role ENUM('admin', 'user') NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Assets table
CREATE TABLE IF NOT EXISTS assets (
    id INT AUTO_INCREMENT PRIMARY KEY,
    asset_number VARCHAR(100) UNIQUE NOT NULL,
    serial_number VARCHAR(100) UNIQUE NOT NULL,
    brand VARCHAR(100),
    model VARCHAR(100),
    invoice_number VARCHAR(100),
    ram VARCHAR(50),
    rom VARCHAR(50),
    status ENUM('available', 'assigned', 'maintenance', 'retired') DEFAULT 'available',
    purchase_date DATE,
    warranty_expiry DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Assignments table
CREATE TABLE IF NOT EXISTS assignments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    asset_id INT,
    user_id INT,
    unit VARCHAR(100),
    assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    returned_at TIMESTAMP NULL,
    FOREIGN KEY (asset_id) REFERENCES assets(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Requests table
CREATE TABLE IF NOT EXISTS requests (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT,
    asset_type VARCHAR(100),
    status ENUM('pending', 'approved', 'rejected', 'completed') DEFAULT 'pending',
    request_type ENUM('new', 'return', 'replacement'),
    details TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Documents table
CREATE TABLE IF NOT EXISTS documents (
    id INT AUTO_INCREMENT PRIMARY KEY,
    asset_id INT,
    doc_type ENUM('PO', 'PR', 'GRN', 'Invoice', 'DC'),
    file_path VARCHAR(255),
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (asset_id) REFERENCES assets(id)
);

-- Maintenance table
CREATE TABLE IF NOT EXISTS maintenance (
    id INT AUTO_INCREMENT PRIMARY KEY,
    asset_id INT,
    issue_details TEXT,
    status ENUM('open', 'in_progress', 'resolved') DEFAULT 'open',
    reported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP NULL,
    FOREIGN KEY (asset_id) REFERENCES assets(id)
);

-- Audit Logs table
CREATE TABLE IF NOT EXISTS audit_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT,
    action VARCHAR(255),
    details TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Notifications table
CREATE TABLE IF NOT EXISTS notifications (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT,
    message TEXT,
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Asset Types table
CREATE TABLE IF NOT EXISTS asset_types (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL
);

-- Purchase Requests table (updated)
CREATE TABLE IF NOT EXISTS purchase_requests (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT,
    asset_type VARCHAR(100),
    configuration VARCHAR(100), -- e.g., i3/i5/desktop
    department_allocation VARCHAR(255), -- e.g., BD-2, IT-2, PM-6
    requested_quantity INT,
    available_stock INT,
    shortfall_quantity INT, -- quantity to be procured if stock is insufficient
    status ENUM('pending', 'approved', 'rejected', 'completed') DEFAULT 'pending',
    approver_email VARCHAR(100),
    approval_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Purchase Orders table (updated)
CREATE TABLE IF NOT EXISTS purchase_orders (
    id INT AUTO_INCREMENT PRIMARY KEY,
    pr_id INT,
    po_number VARCHAR(100),
    po_date DATE,
    expected_delivery_date DATE,
    po_file_path VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (pr_id) REFERENCES purchase_requests(id)
);

-- Deliveries table (updated)
CREATE TABLE IF NOT EXISTS deliveries (
    id INT AUTO_INCREMENT PRIMARY KEY,
    po_id INT,
    delivery_date DATE,
    invoice_number VARCHAR(100),
    grn_number VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (po_id) REFERENCES purchase_orders(id)
);

-- Payment Tracking table (new)
CREATE TABLE IF NOT EXISTS payment_tracking (
    id INT AUTO_INCREMENT PRIMARY KEY,
    delivery_id INT,
    invoice_moved_to_finance BOOLEAN DEFAULT FALSE,
    payment_terms VARCHAR(100), -- e.g., NETT 30 days
    payment_reminder_21_sent BOOLEAN DEFAULT FALSE,
    payment_reminder_25_sent BOOLEAN DEFAULT FALSE,
    payment_given_date DATE,
    utr_number VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (delivery_id) REFERENCES deliveries(id)
);

-- Approvals table (new)
CREATE TABLE IF NOT EXISTS approvals (
    id INT AUTO_INCREMENT PRIMARY KEY,
    pr_id INT,
    approver_id INT,
    status ENUM('pending', 'approved', 'rejected') DEFAULT 'pending',
    comments TEXT,
    approved_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (pr_id) REFERENCES purchase_requests(id),
    FOREIGN KEY (approver_id) REFERENCES users(id)
);

-- Insert default admin and user
INSERT INTO users (email, password, name, role) VALUES
('admin@assetms.com', '$2b$12$w1Qw1Qw1Qw1Qw1Qw1Qw1QeQw1Qw1Qw1Qw1Qw1Qw1Qw1Qw1Qw1Qw1Q', 'Admin', 'admin'),
('user@assetms.com', '$2b$12$w1Qw1Qw1Qw1Qw1Qw1Qw1QeQw1Qw1Qw1Qw1Qw1Qw1Qw1Qw1Qw1Qw1Q', 'User', 'user');
-- Note: Replace the above password hashes with real bcrypt hashes for 'Admin@123' and 'User@123'. 