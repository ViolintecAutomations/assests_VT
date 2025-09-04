-- Create Approvers table for specific approver list
CREATE TABLE IF NOT EXISTS approvers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert 4 specific approvers
INSERT INTO approvers (name, email) VALUES
('John Smith', 'john.smith@company.com'),
('Sarah Johnson', 'sarah.johnson@company.com'),
('Mike Davis', 'mike.davis@company.com'),
('Lisa Wilson', 'lisa.wilson@company.com');
