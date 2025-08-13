-- IT Procurement and Asset Management System Database Schema

-- Users and Departments
CREATE TABLE IF NOT EXISTS departments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(100) NOT NULL UNIQUE,
    department_id INT,
    role ENUM('user', 'manager', 'admin') DEFAULT 'user',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (department_id) REFERENCES departments(id)
);

-- Asset Types (already exists, but adding for completeness)
CREATE TABLE IF NOT EXISTS asset_types (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL
);

-- Stock Management
CREATE TABLE IF NOT EXISTS stock (
    id INT AUTO_INCREMENT PRIMARY KEY,
    asset_type_id INT NOT NULL,
    configuration VARCHAR(200) NOT NULL,
    quantity_available INT DEFAULT 0,
    unit_cost DECIMAL(10,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (asset_type_id) REFERENCES asset_types(id),
    UNIQUE KEY unique_stock (asset_type_id, configuration)
);

-- Purchase Requests
CREATE TABLE IF NOT EXISTS purchase_requests (
    id INT AUTO_INCREMENT PRIMARY KEY,
    pr_number VARCHAR(50) UNIQUE NOT NULL,
    requested_by INT NOT NULL,
    request_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status ENUM('pending', 'approved', 'rejected', 'po_created', 'delivered', 'closed') DEFAULT 'pending',
    justification TEXT,
    total_amount DECIMAL(12,2) DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (requested_by) REFERENCES users(id)
);

-- PR Items (individual items within a PR)
CREATE TABLE IF NOT EXISTS pr_items (
    id INT AUTO_INCREMENT PRIMARY KEY,
    pr_id INT NOT NULL,
    asset_type_id INT NOT NULL,
    configuration VARCHAR(200) NOT NULL,
    unit_cost DECIMAL(10,2) NOT NULL,
    quantity_required INT NOT NULL,
    department_split JSON, -- Store as JSON: {"BD": 2, "IT": 2, "PM": 6}
    stock_available INT DEFAULT 0,
    quantity_to_procure INT DEFAULT 0,
    favor ENUM('Yes', 'No') DEFAULT 'No', -- FAVOR dropdown field
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (pr_id) REFERENCES purchase_requests(id),
    FOREIGN KEY (asset_type_id) REFERENCES asset_types(id)
);

-- Approvals
CREATE TABLE IF NOT EXISTS approvals (
    id INT AUTO_INCREMENT PRIMARY KEY,
    pr_id INT NOT NULL,
    asset_type_id INT,
    configuration VARCHAR(200),
    approver_id INT NOT NULL,
    status ENUM('pending', 'approved', 'rejected') DEFAULT 'pending',
    approval_date TIMESTAMP NULL,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (pr_id) REFERENCES purchase_requests(id),
    FOREIGN KEY (approver_id) REFERENCES users(id),
    FOREIGN KEY (asset_type_id) REFERENCES asset_types(id)
);

-- Purchase Orders
CREATE TABLE IF NOT EXISTS purchase_orders (
    id INT AUTO_INCREMENT PRIMARY KEY,
    pr_id INT NOT NULL,
    po_number VARCHAR(50) UNIQUE NOT NULL,
    po_date DATE NOT NULL,
    expected_delivery_date DATE NOT NULL,
    po_file_path VARCHAR(255),
    status ENUM('created', 'delivered', 'closed') DEFAULT 'created',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (pr_id) REFERENCES purchase_requests(id)
);

-- Deliveries
CREATE TABLE IF NOT EXISTS deliveries (
    id INT AUTO_INCREMENT PRIMARY KEY,
    po_id INT NOT NULL,
    delivery_date DATE NOT NULL,
    quantity_received INT NOT NULL,
    invoice_number VARCHAR(100),
    grn_number VARCHAR(100),
    invoice_to_finance BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (po_id) REFERENCES purchase_orders(id)
);

-- Invoices and Payment Tracking
CREATE TABLE IF NOT EXISTS invoices (
    id INT AUTO_INCREMENT PRIMARY KEY,
    delivery_id INT NOT NULL,
    invoice_number VARCHAR(100) UNIQUE NOT NULL,
    invoice_date DATE NOT NULL,
    payment_due_date DATE NOT NULL,
    payment_given_date DATE NULL,
    utr_number VARCHAR(100),
    amount DECIMAL(12,2) NOT NULL,
    status ENUM('pending', 'paid', 'overdue') DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (delivery_id) REFERENCES deliveries(id)
);

-- Assets (enhanced for procurement tracking)
CREATE TABLE IF NOT EXISTS assets (
    id INT AUTO_INCREMENT PRIMARY KEY,
    asset_number VARCHAR(50) UNIQUE NOT NULL,
    asset_type_id INT NOT NULL,
    configuration VARCHAR(200) NOT NULL,
    serial_number VARCHAR(100),
    status ENUM('available', 'assigned', 'maintenance', 'retired') DEFAULT 'available',
    assigned_to INT NULL,
    assigned_date DATE NULL,
    purchase_order_id INT NULL,
    delivery_id INT NULL,
    date_registered DATE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (asset_type_id) REFERENCES asset_types(id),
    FOREIGN KEY (assigned_to) REFERENCES users(id),
    FOREIGN KEY (purchase_order_id) REFERENCES purchase_orders(id),
    FOREIGN KEY (delivery_id) REFERENCES deliveries(id)
);

-- Insert default departments
INSERT IGNORE INTO departments (name) VALUES 
('IT'), ('BD'), ('PM'), ('HR'), ('Finance'), ('Operations');

-- Insert default asset types (if not exists)
INSERT IGNORE INTO asset_types (name) VALUES 
('Laptop'), ('Mouse'), ('Keyboard'), ('System'), ('Others');

-- Create indexes for better performance
CREATE INDEX idx_pr_status ON purchase_requests(status);
CREATE INDEX idx_pr_requested_by ON purchase_requests(requested_by);
CREATE INDEX idx_po_pr_id ON purchase_orders(pr_id);
CREATE INDEX idx_delivery_po_id ON deliveries(po_id);
CREATE INDEX idx_invoice_delivery_id ON invoices(delivery_id);
CREATE INDEX idx_assets_po_id ON assets(purchase_order_id);
CREATE INDEX idx_assets_status ON assets(status); 