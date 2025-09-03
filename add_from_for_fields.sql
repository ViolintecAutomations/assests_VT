-- Migration script to add from_field and for_field columns to purchase_requests table
-- Run this script to update existing database

-- Add from_field column if it doesn't exist
ALTER TABLE purchase_requests 
ADD COLUMN IF NOT EXISTS from_field VARCHAR(255) AFTER justification;

-- Add for_field column if it doesn't exist  
ALTER TABLE purchase_requests 
ADD COLUMN IF NOT EXISTS for_field VARCHAR(255) AFTER from_field;

-- Update existing records to have default values if needed
UPDATE purchase_requests 
SET from_field = 'Not specified', for_field = 'Not specified' 
WHERE from_field IS NULL OR for_field IS NULL;






