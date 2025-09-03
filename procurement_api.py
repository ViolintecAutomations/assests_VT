# Procurement System API Endpoints
from flask import Blueprint, request, jsonify, render_template, render_template_string
from datetime import datetime, timedelta
import json
import os
from werkzeug.utils import secure_filename
import pymysql
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import json
from DB_Connection import get_db_connection

Curr_Proj_Name = 'Assert_IT'
procurement_bp = Blueprint('procurement', __name__)

def get_db_connection():
    return pymysql.connect(
        host='localhost',
        user='root',
        password='Violin@12',
        database='CMS',
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )

def recalculate_total_amount(pr_id):
    conn = get_db_connection(Curr_Proj_Name)
    cur = conn.cursor()
    cur.execute('SELECT SUM(unit_cost * quantity_to_procure) as total FROM pr_items WHERE pr_id = %s', (pr_id,))
    result = cur.fetchone()
    total = result['total'] if result and result['total'] is not None else 0
    cur.execute('UPDATE purchase_requests SET total_amount = %s WHERE id = %s', (total, pr_id))
    conn.commit()
    cur.close()
    conn.close()

def recalculate_approved_total_amount(pr_id):
    """Recalculate total amount based on only approved items"""
    conn = get_db_connection(Curr_Proj_Name)
    cur = conn.cursor()
    
    # Calculate total from only approved items
    cur.execute('''
        SELECT SUM(pri.unit_cost * pri.quantity_to_procure) as total 
        FROM pr_items pri
        INNER JOIN item_approvals ia ON pri.id = ia.pr_item_id
        WHERE pri.pr_id = %s AND ia.status = 'approved'
    ''', (pr_id,))
    
    result = cur.fetchone()
    approved_total = result['total'] if result and result['total'] is not None else 0
    
    # Update the PR with the approved total
    cur.execute('UPDATE purchase_requests SET total_amount = %s WHERE id = %s', (approved_total, pr_id))
    conn.commit()
    cur.close()
    conn.close()
    
    return approved_total

# Vendor APIs
@procurement_bp.route('/api/vendors', methods=['GET'])
def get_vendors():
    """Get all vendors"""
    try:
        conn = get_db_connection(Curr_Proj_Name)
        cur = conn.cursor()
        cur.execute('SELECT id, name FROM vendors ORDER BY name')
        vendors = [{'id': row['id'], 'name': row['name']} for row in cur.fetchall()]
        cur.close()
        conn.close()
        return jsonify({'vendors': vendors})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@procurement_bp.route('/api/vendors', methods=['POST'])
def add_vendor():
    """Add a new vendor"""
    try:
        data = request.get_json()
        vendor_name = data.get('name', '').strip()
        
        if not vendor_name:
            return jsonify({'success': False, 'error': 'Vendor name is required'}), 400
        
        conn = get_db_connection(Curr_Proj_Name)
        cur = conn.cursor()
        
        # Check if vendor already exists
        cur.execute('SELECT id FROM vendors WHERE name = %s', (vendor_name,))
        existing = cur.fetchone()
        if existing:
            return jsonify({'success': False, 'error': 'Vendor already exists'}), 400
        
        # Add new vendor
        cur.execute('INSERT INTO vendors (name) VALUES (%s)', (vendor_name,))
        conn.commit()
        
        cur.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'name': vendor_name,
            'message': 'Vendor added successfully'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

# Purchase Request APIs
@procurement_bp.route('/api/purchase_requests', methods=['POST'])
def create_purchase_request():
    """Create a new purchase request"""
    try:
        data = request.get_json()
        print(f"DEBUG: Received data: {data}")  # Debug log
        
        # Validate required fields
        if not data:
            return jsonify({'success': False, 'error': 'No data received'}), 400
        
        if 'requested_by' not in data:
            return jsonify({'success': False, 'error': 'requested_by is required'}), 400
        
        if 'items' not in data or not data['items']:
            return jsonify({'success': False, 'error': 'At least one item is required'}), 400
        
        # Generate PR number
        pr_number = f"PR{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        conn = get_db_connection(Curr_Proj_Name)
        cur = conn.cursor()
        
        # Create PR
        cur.execute('''
            INSERT INTO purchase_requests (pr_number, requested_by, justification, from_field, for_field, total_amount)
            VALUES (%s, %s, %s, %s, %s, %s)
        ''', (pr_number, data['requested_by'], data.get('justification', ''), 
              data.get('from_field', ''), data.get('for_field', ''), 0))
        
        pr_id = cur.lastrowid
        print(f"DEBUG: Created PR with ID: {pr_id}")  # Debug log
        
        # Add PR items
        for i, item in enumerate(data['items']):
            print(f"DEBUG: Processing item {i}: {item}")  # Debug log
            
            # Validate item fields
            if 'asset_type_id' not in item:
                return jsonify({'success': False, 'error': f'asset_type_id is required for item {i}'}), 400
            
            if 'unit_cost' not in item:
                return jsonify({'success': False, 'error': f'unit_cost is required for item {i}'}), 400
            
            if 'quantity_required' not in item:
                return jsonify({'success': False, 'error': f'quantity_required is required for item {i}'}), 400
            
            # Use stock_available from frontend data instead of recalculating from database
            stock_available = int(item.get('stock_available', 0) or 0)
            quantity_required = int(item['quantity_required'])
            
            # New logic: If quantity required <= stock available, procure the full quantity required
            # Otherwise, procure the difference
            if quantity_required <= stock_available:
                quantity_to_procure = quantity_required
            else:
                quantity_to_procure = quantity_required - stock_available
            
            cur.execute('''
                INSERT INTO pr_items (pr_id, asset_type_id, brand, vendor, configuration, unit_cost, 
                                    quantity_required, department_split, stock_available, quantity_to_procure, favor, favor_reason, reason_not_using_stock)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (pr_id, item['asset_type_id'], item.get('brand', ''), item.get('vendor', ''), 
                  item.get('configuration', ''), item['unit_cost'], item['quantity_required'], 
                  json.dumps(item.get('department_split', {})), stock_available, quantity_to_procure, 
                  item.get('favor', 'No'), item.get('favor_reason', ''), item.get('stock_reason', '')))
            
            print(f"DEBUG: Inserted item {i} with stock_available={stock_available}, quantity_to_procure={quantity_to_procure}")  # Debug log
        
        # Find approver by email
        approver_email = data.get('approver_email')
        approver_id = 1  # Default to admin
        if approver_email:
            cur.execute('SELECT id FROM users WHERE email = %s', (approver_email,))
            approver_result = cur.fetchone()
            if approver_result:
                approver_id = approver_result['id']
        
        # Ensure we have a valid approver
        cur.execute('SELECT id FROM users WHERE id = %s', (approver_id,))
        approver_check = cur.fetchone()
        if not approver_check:
            # Fallback to first admin user
            cur.execute('SELECT id FROM users WHERE role = "admin" LIMIT 1')
            admin_user = cur.fetchone()
            if admin_user:
                approver_id = admin_user['id']
            else:
                # Last resort: use the first user
                cur.execute('SELECT id FROM users LIMIT 1')
                first_user = cur.fetchone()
                if first_user:
                    approver_id = first_user['id']
        
        # Create approval record (always create one)
        cur.execute('''
            INSERT INTO approvals (pr_id, approver_id, status)
            VALUES (%s, %s, 'pending')
        ''', (pr_id, approver_id))
        
        print(f"DEBUG: Created approval record for PR {pr_number} with approver_id {approver_id}")  # Debug log
        
        conn.commit()
        cur.close()
        conn.close()
        
        recalculate_total_amount(pr_id)
        
        # Send approval email (implement email function)
        try:
            send_approval_email(pr_id)
        except Exception as e:
            print(f"Warning: Could not send approval email: {e}")
        
        to_email = data.get('approver_email')
        # Guarantee pr_id is set for the email
        email_data = dict(data)
        email_data['pr_id'] = pr_id
        print(f"Sending PR email with pr_id: {email_data['pr_id']}")  # DEBUG
        print(f"Email data: {email_data}")  # DEBUG
        print(f"Asset types in PR: {[item.get('asset_type_name', 'Unknown') for item in email_data.get('items', [])]}")  # DEBUG
        
        try:
            send_pr_email(to_email, email_data)
            print(f"✅ Email sent successfully for PR {pr_id}")
        except Exception as e:
            print(f"❌ Error sending email for PR {pr_id}: {e}")
            import traceback
            traceback.print_exc()
        
        return jsonify({
            'success': True,
            'pr_id': pr_id,
            'pr_number': pr_number,
            'message': 'Purchase request created successfully'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@procurement_bp.route('/api/purchase_requests', methods=['GET'])
def get_purchase_requests():
    """Get all purchase requests with approver info, with optional status and limit filters"""
    try:
        status = request.args.get('status')
        limit = request.args.get('limit', type=int)
        conn = get_db_connection(Curr_Proj_Name)
        cur = conn.cursor()
        
        # Use a subquery to get the latest approval record for each PR
        sql = '''
            SELECT 
                pr.*,
                u.name as requester_name, 
                d.name as department_name,
                a.approver_id, 
                au.name as approver_name, 
                au.email as approver_email,
                   COALESCE(a.status, pr.status) as status,
                   a.approval_date as approval_date_from_approvals,
                   a.notes as approval_notes,
                   GROUP_CONCAT(DISTINCT at.name SEPARATOR ', ') as asset_types,
                   GROUP_CONCAT(DISTINCT pri.configuration SEPARATOR ', ') as configurations
            FROM purchase_requests pr
            LEFT JOIN users u ON pr.requested_by = u.id
            LEFT JOIN departments d ON u.department_id = d.id
            LEFT JOIN (
                SELECT t1.* FROM approvals t1
                INNER JOIN (
                    SELECT pr_id, MAX(approval_date) as max_date
                    FROM approvals
                    GROUP BY pr_id
                ) t2 ON t1.pr_id = t2.pr_id AND (t1.approval_date = t2.max_date OR t1.id = (
                    SELECT MAX(id) FROM approvals t3 WHERE t3.pr_id = t1.pr_id
                ))
            ) a ON a.pr_id = pr.id
            LEFT JOIN users au ON a.approver_id = au.id
            LEFT JOIN pr_items pri ON pr.id = pri.pr_id
            LEFT JOIN asset_types at ON pri.asset_type_id = at.id
        '''
        
        params = []
        where_clause = ''
        
        # Only filter by status if status is provided and not empty
        if status:
            where_clause = ' WHERE COALESCE(a.status, pr.status) = %s'
            params.append(status)
        
        sql += where_clause + ' GROUP BY pr.id, pr.pr_number, pr.justification, pr.total_amount, pr.status, pr.created_at, pr.updated_at, pr.requested_by, u.name, d.name, a.approver_id, au.name, au.email, a.status, a.approval_date, a.notes ORDER BY pr.created_at DESC'
        
        if limit:
            sql += ' LIMIT %s'
            params.append(limit)
        
        print(f"DEBUG: Executing SQL: {sql}")  # Debug log
        print(f"DEBUG: Parameters: {params}")   # Debug log
        
        cur.execute(sql, tuple(params))
        prs = cur.fetchall()
        
        print(f"DEBUG: Found {len(prs)} purchase requests")  # Debug log
        if not prs:
            print("DEBUG: No purchase requests found in the database.")
        else:
            for pr in prs:
                print(f"DEBUG: PR: {pr.get('pr_number')} | Status: {pr.get('status')} | Approver: {pr.get('approver_name')} | Approval Date: {pr.get('approval_date_from_approvals')}")
        
        # Convert datetime objects to strings for JSON serialization
        for pr in prs:
            if pr.get('created_at'):
                pr['created_at'] = pr['created_at'].isoformat() if hasattr(pr['created_at'], 'isoformat') else str(pr['created_at'])
            if pr.get('updated_at'):
                pr['updated_at'] = pr['updated_at'].isoformat() if hasattr(pr['updated_at'], 'isoformat') else str(pr['updated_at'])
            if pr.get('approval_date_from_approvals'):
                pr['approval_date_from_approvals'] = pr['approval_date_from_approvals'].isoformat() if hasattr(pr['approval_date_from_approvals'], 'isoformat') else str(pr['approval_date_from_approvals'])
        
        cur.close()
        conn.close()
        
        return jsonify({'success': True, 'requests': prs})
    except Exception as e:
        print('ERROR in get_purchase_requests:', e)
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 400

@procurement_bp.route('/api/purchase_requests/<int:pr_id>', methods=['GET'])
def get_purchase_request(pr_id):
    """Get specific purchase request with items"""
    try:
        conn = get_db_connection(Curr_Proj_Name)
        cur = conn.cursor()
        
        # Get PR details
        cur.execute('''
            SELECT pr.*, u.name as requester_name, d.name as department_name
            FROM purchase_requests pr
            JOIN users u ON pr.requested_by = u.id
            LEFT JOIN departments d ON u.department_id = d.id
            WHERE pr.id = %s
        ''', (pr_id,))
        pr = cur.fetchone()
        
        if not pr:
            return jsonify({'success': False, 'error': 'PR not found'}), 404
        
        # Check if this is for delivery entry (from delivery page)
        is_delivery_entry = request.args.get('delivery_entry', 'false').lower() == 'true'
        
        if is_delivery_entry:
            # For delivery entry, get all items with approval status
            cur.execute('''
                SELECT pri.*, at.name as asset_type_name, COALESCE(ia.status, 'pending') as approval_status
                FROM pr_items pri
                JOIN asset_types at ON pri.asset_type_id = at.id
                LEFT JOIN item_approvals ia ON pri.id = ia.pr_item_id
                WHERE pri.pr_id = %s
            ''', (pr_id,))
        else:
            # For other pages, only show approved items
            cur.execute('''
                SELECT pri.*, at.name as asset_type_name, ia.status as approval_status
                FROM pr_items pri
                JOIN asset_types at ON pri.asset_type_id = at.id
                INNER JOIN item_approvals ia ON pri.id = ia.pr_item_id
                WHERE pri.pr_id = %s
                AND ia.status = 'approved'
            ''', (pr_id,))
        
        items = cur.fetchall()
        
        # Debug logging for items
        print(f"DEBUG: Retrieved {len(items)} items for PR {pr_id} (delivery_entry: {is_delivery_entry})")
        for i, item in enumerate(items):
            print(f"DEBUG: Item {i}: {item}")
            print(f"DEBUG: Item {i} keys: {list(item.keys())}")
            print(f"DEBUG: Item {i} preferred: '{item.get('preferred', 'NOT_FOUND')}'")
        
        # Get approval status
        cur.execute('''
            SELECT a.*, u.name as approver_name
            FROM approvals a
            JOIN users u ON a.approver_id = u.id
            WHERE a.pr_id = %s
        ''', (pr_id,))
        approval = cur.fetchone()
        approval_status = approval['status'] if approval and 'status' in approval else None
        cur.close()
        conn.close()
        return jsonify({
            'success': True,
            'purchase_request': pr,
            'items': items,
            'approval': approval,
            'approval_status': approval_status
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@procurement_bp.route('/api/purchase_requests/<int:pr_id>/approve', methods=['POST'])
def approve_purchase_request(pr_id):
    """Approve a purchase request with approver_id or approver name/email"""
    try:
        data = request.get_json()
        status = data.get('status', 'approved')
        notes = data.get('notes', '')
        approver_id = data.get('approver_id')
        approver = data.get('approver', '').strip()
        
        print(f"DEBUG: Approving PR {pr_id} with status: {status}")  # Debug log
        
        conn = get_db_connection(Curr_Proj_Name)
        cur = conn.cursor()
        
        # First, check if PR exists
        cur.execute('SELECT id FROM purchase_requests WHERE id = %s', (pr_id,))
        pr = cur.fetchone()
        if not pr:
            cur.close()
            conn.close()
            return jsonify({'success': False, 'error': 'Purchase request not found'}), 404
        
        # Handle approver identification
        if approver_id:
            # Use the provided user id
            cur.execute('SELECT id, name FROM users WHERE id = %s', (approver_id,))
            user = cur.fetchone()
            if not user:
                cur.close()
                conn.close()
                return jsonify({'success': False, 'error': 'Approver not found'}), 400
            approver_id = user['id']
        else:
            # If no approver provided, try to find a default approver
            if not approver:
                # Try to find any user with manager role
                cur.execute('SELECT id, name FROM users WHERE role = "manager" LIMIT 1')
                user = cur.fetchone()
                if user:
                    approver_id = user['id']
                    approver = user['name']
                else:
                    # Create a default approver if none exists
                    default_approver_name = "System Approver"
                    cur.execute('INSERT INTO users (name, email, password, role) VALUES (%s, %s, %s, %s)', 
                               (default_approver_name, 'system@company.com', '', 'manager'))
                    conn.commit()
                    approver_id = cur.lastrowid
                    approver = default_approver_name
            else:
                # Fallback: find or create by email/name
                cur.execute('SELECT id FROM users WHERE email = %s', (approver,))
                user = cur.fetchone()
                if not user:
                    cur.execute('SELECT id FROM users WHERE name = %s', (approver,))
                    user = cur.fetchone()
                if not user:
                    # Create a new user if not found
                    cur.execute('INSERT INTO users (name, email, password, role) VALUES (%s, %s, %s, %s)', 
                               (approver, approver, '', 'manager'))
                    conn.commit()
                    approver_id = cur.lastrowid
                else:
                    approver_id = user['id']
        
        # Check if approval record exists
        cur.execute('SELECT id FROM approvals WHERE pr_id = %s', (pr_id,))
        existing_approval = cur.fetchone()
        
        if existing_approval:
            # Update existing approval
            cur.execute('''
                UPDATE approvals 
                SET status = %s, approval_date = NOW(), notes = %s, approver_id = %s
                WHERE pr_id = %s
            ''', (status, notes, approver_id, pr_id))
            print(f"DEBUG: Updated existing approval for PR {pr_id}")  # Debug log
        else:
            # Create new approval record
            cur.execute('''
                INSERT INTO approvals (pr_id, approver_id, status, approval_date, notes)
                VALUES (%s, %s, %s, NOW(), %s)
            ''', (pr_id, approver_id, status, notes))
            print(f"DEBUG: Created new approval for PR {pr_id}")  # Debug log
        
        # Update PR status
        pr_status = 'approved' if status == 'approved' else 'rejected'
        cur.execute('''
            UPDATE purchase_requests 
            SET status = %s, updated_at = NOW()
            WHERE id = %s
        ''', (pr_status, pr_id))
        
        conn.commit()
        cur.close()
        conn.close()
        
        print(f"DEBUG: Successfully approved PR {pr_id} with status: {status}")  # Debug log
        
        # Send notification
        try:
            send_approval_notification(pr_id, status)
        except Exception as e:
            print(f"Warning: Could not send approval notification: {e}")
        
        return jsonify({'success': True, 'message': f'Purchase request {status} successfully'})
    except Exception as e:
        print(f"ERROR in approve_purchase_request: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 400

# Item-level approval API
@procurement_bp.route('/api/purchase_requests/<int:pr_id>/approve_items', methods=['POST'])
def approve_purchase_request_items(pr_id):
    """Approve specific items in a purchase request"""
    try:
        data = request.get_json()
        approved_items = data.get('approved_items', [])  # List of item IDs to approve
        rejected_items = data.get('rejected_items', [])  # List of item IDs to reject
        approval_justifications = data.get('approval_justifications', {})  # Justifications for approved items
        notes = data.get('notes', '')
        approver_id = data.get('approver_id')
        approver = data.get('approver', '').strip()
        
        print(f"DEBUG: Approving items for PR {pr_id}")  # Debug log
        print(f"DEBUG: Approved items: {approved_items}")  # Debug log
        print(f"DEBUG: Rejected items: {rejected_items}")  # Debug log
        
        conn = get_db_connection(Curr_Proj_Name)
        cur = conn.cursor()
        
        # First, check if PR exists
        cur.execute('SELECT id FROM purchase_requests WHERE id = %s', (pr_id,))
        pr = cur.fetchone()
        if not pr:
            cur.close()
            conn.close()
            return jsonify({'success': False, 'error': 'Purchase request not found'}), 404
        
        # Handle approver identification
        if approver_id:
            # Use the provided user id
            cur.execute('SELECT id, name FROM users WHERE id = %s', (approver_id,))
            user = cur.fetchone()
            if not user:
                cur.close()
                conn.close()
                return jsonify({'success': False, 'error': 'Approver not found'}), 400
            approver_id = user['id']
        else:
            # If no approver provided, try to find a default approver
            if not approver:
                # Try to find any user with manager role
                cur.execute('SELECT id, name FROM users WHERE role = "manager" LIMIT 1')
                user = cur.fetchone()
                if user:
                    approver_id = user['id']
                    approver = user['name']
                else:
                    # Create a default approver if none exists
                    default_approver_name = "System Approver"
                    cur.execute('INSERT INTO users (name, email, password, role) VALUES (%s, %s, %s, %s)', 
                               (default_approver_name, 'system@company.com', '', 'manager'))
                    conn.commit()
                    approver_id = cur.lastrowid
                    approver = default_approver_name
            else:
                # Fallback: find or create by email/name
                cur.execute('SELECT id FROM users WHERE email = %s', (approver,))
                user = cur.fetchone()
                if not user:
                    cur.execute('SELECT id FROM users WHERE name = %s', (approver,))
                    user = cur.fetchone()
                if not user:
                    # Create a new user if not found
                    cur.execute('INSERT INTO users (name, email, password, role) VALUES (%s, %s, %s, %s)', 
                               (approver, approver, '', 'manager'))
                    conn.commit()
                    approver_id = cur.lastrowid
                else:
                    approver_id = user['id']
        
        # Process approved items
        for item_id in approved_items:
            # Get justification for this item if it exists
            item_justification = approval_justifications.get(str(item_id), '')
            combined_notes = notes
            if item_justification:
                combined_notes = item_justification
            
            # Update the is_approved field in pr_items table
            cur.execute('''
                UPDATE pr_items 
                SET is_approved = 1, approved_at = NOW()
                WHERE id = %s
            ''', (item_id,))
            
            # Check if item approval record exists
            cur.execute('SELECT id FROM item_approvals WHERE pr_item_id = %s', (item_id,))
            existing_approval = cur.fetchone()
            
            if existing_approval:
                # Update existing approval
                cur.execute('''
                    UPDATE item_approvals 
                    SET status = 'approved', approval_date = NOW(), notes = %s, approver_id = %s
                    WHERE pr_item_id = %s
                ''', (combined_notes, approver_id, item_id))
            else:
                # Create new approval record
                cur.execute('''
                    INSERT INTO item_approvals (pr_item_id, approver_id, status, approval_date, notes)
                    VALUES (%s, %s, 'approved', NOW(), %s)
                ''', (item_id, approver_id, combined_notes))
        
        # Process rejected items
        for item_id in rejected_items:
            # Update the is_approved field in pr_items table
            cur.execute('''
                UPDATE pr_items 
                SET is_approved = 0, approved_at = NULL
                WHERE id = %s
            ''', (item_id,))
            
            # Check if item approval record exists
            cur.execute('SELECT id FROM item_approvals WHERE pr_item_id = %s', (item_id,))
            existing_approval = cur.fetchone()
            
            if existing_approval:
                # Update existing approval
                cur.execute('''
                    UPDATE item_approvals 
                    SET status = 'rejected', approval_date = NOW(), notes = %s, approver_id = %s
                    WHERE pr_item_id = %s
                ''', (notes, approver_id, item_id))
            else:
                # Create new approval record
                cur.execute('''
                    INSERT INTO item_approvals (pr_item_id, approver_id, status, approval_date, notes)
                    VALUES (%s, %s, 'rejected', NOW(), %s)
                ''', (item_id, approver_id, notes))
        
        # Check overall PR status based on item approvals
        cur.execute('''
            SELECT COUNT(*) as total_items,
                   SUM(CASE WHEN ia.status = 'approved' THEN 1 ELSE 0 END) as approved_items,
                   SUM(CASE WHEN ia.status = 'rejected' THEN 1 ELSE 0 END) as rejected_items
            FROM pr_items pi
            LEFT JOIN item_approvals ia ON pi.id = ia.pr_item_id
            WHERE pi.pr_id = %s
        ''', (pr_id,))
        status_result = cur.fetchone()
        
        # Determine overall PR status
        if status_result['approved_items'] > 0 and status_result['rejected_items'] == 0:
            pr_status = 'approved'
        elif status_result['rejected_items'] > 0 and status_result['approved_items'] == 0:
            pr_status = 'rejected'
        elif status_result['approved_items'] > 0 and status_result['rejected_items'] > 0:
            pr_status = 'approved'  # If any items are approved, mark as approved
        else:
            pr_status = 'pending'
        
        # Update PR status
        cur.execute('''
            UPDATE purchase_requests 
            SET status = %s, updated_at = NOW()
            WHERE id = %s
        ''', (pr_status, pr_id))
        
        # Update approval status in approvals table
        cur.execute('''
            UPDATE approvals 
            SET status = %s, approval_date = NOW()
            WHERE pr_id = %s
        ''', (pr_status, pr_id))
        
        conn.commit()
        cur.close()
        conn.close()
        
        # Recalculate total amount based on approved items only
        approved_total = recalculate_approved_total_amount(pr_id)
        print(f"DEBUG: Updated PR {pr_id} total amount to ₹{approved_total} (approved items only)")
        
        print(f"DEBUG: Successfully processed item approvals for PR {pr_id}")  # Debug log
        
        # Send notification
        try:
            send_approval_notification(pr_id, pr_status)
        except Exception as e:
            print(f"Warning: Could not send approval notification: {e}")
        
        return jsonify({
            'success': True, 
            'message': f'Item approvals processed successfully. PR status: {pr_status}',
            'pr_status': pr_status
        })
    except Exception as e:
        print(f"ERROR in approve_purchase_request_items: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 400

# Stock Check API
@procurement_bp.route('/api/stock_check', methods=['GET'])
def check_stock():
    """Check available stock for a type only (dynamically from assets table, status = 'available')"""
    try:
        asset_type_id = request.args.get('asset_type_id')
        
        if not asset_type_id:
            return jsonify({'success': False, 'error': 'asset_type_id is required'}), 400
        
        # Validate that asset_type_id is a valid integer
        try:
            asset_type_id = int(asset_type_id)
        except (ValueError, TypeError):
            return jsonify({'success': False, 'error': 'asset_type_id must be a valid number'}), 400
        
        conn = get_db_connection(Curr_Proj_Name)
        cur = conn.cursor()
        
        # Get asset type name from id
        cur.execute('SELECT name FROM asset_types WHERE id = %s', (asset_type_id,))
        row = cur.fetchone()
        
        if not row:
            cur.close()
            conn.close()
            return jsonify({'success': False, 'error': f'Asset type with ID {asset_type_id} not found'}), 400
        
        asset_type_name = row['name']
        
        # Count available assets of this type
        cur.execute('SELECT COUNT(*) as available_count FROM assets WHERE asset_type = %s AND status = "available"', (asset_type_name,))
        result = cur.fetchone()
        
        available_count = result['available_count'] if result else 0
        
        cur.close()
        conn.close()
        
        return jsonify({'success': True, 'stock_available': available_count})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

# Purchase Order APIs
@procurement_bp.route('/api/purchase_orders', methods=['POST'])
def create_purchase_order():
    """Create a purchase order with file upload"""
    try:
        # Handle form data and file
        pr_id = request.form.get('pr_id')
        po_number = request.form.get('po_number')
        po_date = request.form.get('po_date')
        expected_delivery_date = request.form.get('expected_delivery_date')
        vendor_name = request.form.get('vendor_name')
        po_file = request.files.get('po_file')
        if not (pr_id and po_number and po_date and expected_delivery_date and vendor_name and po_file):
            return jsonify({'success': False, 'error': 'All fields are required'}), 400
        # Save file
        filename = secure_filename(po_file.filename)
        upload_folder = os.path.join(os.getcwd(), 'uploads')
        if not os.path.exists(upload_folder):
            os.makedirs(upload_folder)
        file_path = os.path.join(upload_folder, filename)
        po_file.save(file_path)
        # Insert PO into DB
        conn = get_db_connection(Curr_Proj_Name)
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO purchase_orders (pr_id, po_number, po_date, expected_delivery_date, po_file_path, vendor_name)
            VALUES (%s, %s, %s, %s, %s, %s)
        ''', (pr_id, po_number, po_date, expected_delivery_date, file_path, vendor_name))
        po_id = cur.lastrowid
        # Update PR status
        cur.execute('''
            UPDATE purchase_requests 
            SET status = 'po_created', updated_at = NOW()
            WHERE id = %s
        ''', (pr_id,))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({'success': True, 'po_id': po_id, 'message': 'Purchase order uploaded successfully'})
    except Exception as e:
        print('ERROR in create_purchase_order:', e)
        return jsonify({'success': False, 'error': str(e)}), 400

@procurement_bp.route('/api/purchase_orders', methods=['GET'])
def get_purchase_orders():
    """Get all purchase orders, with optional status filter.

    Special status values:
    - 'open': POs where total delivered < total to procure (includes newly created and partially delivered)
    - any other value: matches exact po.status
    """
    try:
        status = request.args.get('status')
        conn = get_db_connection(Curr_Proj_Name)
        cur = conn.cursor()

        if status == 'open':
            # Return only POs that are not fully delivered. Use assets count as received fallback for schema compatibility.
            sql = '''
                SELECT po.*, pr.pr_number, pr.justification, pr.total_amount, pr.requested_by,
                       (
                         SELECT COUNT(*) FROM assets a WHERE a.purchase_order_id = po.id
                       ) AS total_received,
                       (
                         SELECT COALESCE(SUM(COALESCE(pri.quantity_to_procure, 0)), 0)
                         FROM pr_items pri
                         LEFT JOIN item_approvals ia ON ia.pr_item_id = pri.id
                         WHERE pri.pr_id = po.pr_id AND (ia.status = 'approved' OR pri.is_approved = 1)
                       ) AS total_to_procure
                FROM purchase_orders po
                JOIN purchase_requests pr ON po.pr_id = pr.id
                ORDER BY po.created_at DESC
            '''
            cur.execute(sql)
            rows = cur.fetchall()
            # Filter rows in Python to avoid DB dependency on HAVING expressions
            pos = [r for r in rows if (r.get('total_to_procure', 0) == 0) or (r.get('total_received', 0) < r.get('total_to_procure', 0))]
        else:
            sql = '''
                SELECT po.*, pr.pr_number, pr.justification, pr.total_amount, pr.requested_by
                FROM purchase_orders po
                JOIN purchase_requests pr ON po.pr_id = pr.id
            '''
            params = []
            if status:
                sql += ' WHERE po.status = %s'
                params.append(status)
            sql += ' ORDER BY po.created_at DESC'
            cur.execute(sql, tuple(params))
            pos = cur.fetchall()

        cur.close()
        conn.close()
        return jsonify({'success': True, 'purchase_orders': pos})
    except Exception as e:
        print('ERROR in get_purchase_orders:', e)
        return jsonify({'success': False, 'error': str(e)}), 400

@procurement_bp.route('/api/purchase_orders/<int:po_id>', methods=['GET'])
def get_purchase_order_details(po_id):
    """Get detailed information about a specific purchase order including quantity summaries"""
    try:
        conn = get_db_connection(Curr_Proj_Name)
        cur = conn.cursor()
        
        # Get PO details with PR information
        cur.execute('''
            SELECT po.*, pr.pr_number, pr.justification, pr.total_amount,
                   u.name as requester_name
            FROM purchase_orders po
            JOIN purchase_requests pr ON po.pr_id = pr.id
            LEFT JOIN users u ON pr.requested_by = u.id
            WHERE po.id = %s
        ''', (po_id,))
        
        po_data = cur.fetchone()
        if not po_data:
            cur.close()
            conn.close()
            return jsonify({'success': False, 'error': 'Purchase order not found'}), 404
        
        # Get PR details
        pr_id = po_data['pr_id']
        cur.execute('''
            SELECT pr.*, u.name as requester_name
            FROM purchase_requests pr
            LEFT JOIN users u ON pr.requested_by = u.id
            WHERE pr.id = %s
        ''', (pr_id,))
        
        pr_data = cur.fetchone()
        
        # Compute quantity totals with robust fallbacks
        total_to_procure = 0
        total_received = 0
        try:
            # Preferred: only approved items
            cur.execute('''
                SELECT COALESCE(SUM(COALESCE(pri.quantity_to_procure, 0)), 0) AS total_to_procure
                FROM pr_items pri
                LEFT JOIN item_approvals ia ON ia.pr_item_id = pri.id
                WHERE pri.pr_id = %s AND (ia.status = 'approved' OR pri.is_approved = 1)
            ''', (pr_id,))
            totals_row = cur.fetchone() or {'total_to_procure': 0}
            total_to_procure = totals_row['total_to_procure']
        except Exception as e:
            # Fallback: sum of quantity_to_procure without approval filter
            print('WARN get_purchase_order_details totals (approved) failed; falling back:', e)
            try:
                cur.execute('''
                    SELECT COALESCE(SUM(COALESCE(quantity_to_procure, 0)), 0) AS total_to_procure
                    FROM pr_items
                    WHERE pr_id = %s
                ''', (pr_id,))
                totals_row = cur.fetchone() or {'total_to_procure': 0}
                total_to_procure = totals_row['total_to_procure']
            except Exception as e2:
                print('WARN get_purchase_order_details fallback totals failed:', e2)
                total_to_procure = 0

        try:
            # Use assets created for this PO as a proxy for received count
            cur.execute('''
                SELECT COUNT(*) AS total_received
                FROM assets a
                WHERE a.purchase_order_id = %s
            ''', (po_id,))
            received_row = cur.fetchone() or {'total_received': 0}
            total_received = received_row['total_received']
        except Exception as e:
            print('WARN get_purchase_order_details received sum failed:', e)
            total_received = 0

        resp = jsonify({
            'success': True,
            'purchase_order': po_data,
            'purchase_request': pr_data,
            'totals': {
                'total_to_procure': total_to_procure,
                'total_received': total_received,
                'pending': max(0, (total_to_procure or 0) - (total_received or 0))
            }
        })
        cur.close()
        conn.close()
        return resp
        
    except Exception as e:
        print('ERROR in get_purchase_order_details:', e)
        return jsonify({'success': False, 'error': str(e)}), 400

# Delivery APIs
@procurement_bp.route('/api/deliveries', methods=['POST'])
def create_delivery():
    """Create a delivery record"""
    try:
        data = request.get_json()
        
        conn = get_db_connection(Curr_Proj_Name)
        cur = conn.cursor()
        
        # Insert delivery using schema-aware column detection
        delivery_number = f"DEL{datetime.now().strftime('%Y%m%d%H%M%S')}"
        delivery_columns = _get_table_columns(cur, 'deliveries')
        col_vals = []
        cols = []
        def add(col, val):
            if col in delivery_columns:
                cols.append(col)
                col_vals.append(val)
        add('delivery_number', delivery_number)
        add('po_id', data['po_id'])
        add('delivery_date', data['delivery_date'])
        add('quantity_received', data.get('quantity_received'))
        add('invoice_number', data.get('invoice_number', ''))
        add('grn_number', data.get('grn_number', ''))
        add('invoice_to_finance', data.get('invoice_to_finance', False))
        # Some schemas require received_by (NOT NULL). Default to 1 if not using auth context
        add('received_by', 1)
        if not cols:
            # Fallback to minimal
            cols = ['po_id', 'delivery_date']
            col_vals = [data['po_id'], data['delivery_date']]
        placeholders = ', '.join(['%s'] * len(col_vals))
        sql = f"INSERT INTO deliveries ({', '.join(cols)}) VALUES ({placeholders})"
        cur.execute(sql, tuple(col_vals))
        delivery_id = cur.lastrowid
        
        # Generate asset numbers for received items
        generate_asset_numbers(delivery_id, data['quantity_received'], data['po_id'])
        
        # Update PO/PR status based on delivered totals
        _update_po_and_pr_status(cur, data['po_id'])
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'delivery_id': delivery_id,
            'message': 'Delivery recorded successfully'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@procurement_bp.route('/api/deliveries/create-with-assets', methods=['POST'])
def create_delivery_with_assets():
    """Create a delivery record and automatically create assets"""
    try:
        data = request.get_json()
        
        conn = get_db_connection(Curr_Proj_Name)
        cur = conn.cursor()
        
        # Get PO and PR details
        cur.execute('''
            SELECT po.*, pr.pr_number, pr.requested_by
            FROM purchase_orders po
            JOIN purchase_requests pr ON po.pr_id = pr.id
            WHERE po.id = %s
        ''', (data['po_id'],))
        
        po_details = cur.fetchone()
        if not po_details:
            return jsonify({'success': False, 'error': 'Purchase Order not found'}), 404
        
        # Get PR items for asset creation (check item approvals)
        cur.execute('''
            SELECT pri.*, at.name as asset_type_name, at.id as asset_type_id,
                   COALESCE(ia.status, 'pending') as approval_status
            FROM pr_items pri
            JOIN asset_types at ON pri.asset_type_id = at.id
            LEFT JOIN item_approvals ia ON pri.id = ia.pr_item_id
            WHERE pri.pr_id = %s AND (ia.status = 'approved' OR pri.is_approved = 1)
        ''', (po_details['pr_id'],))
        
        pr_items = cur.fetchall()
        if not pr_items:
            return jsonify({'success': False, 'error': 'No approved items found for this PR'}), 404
        
        # Create delivery record using schema-aware column detection
        delivery_number = f"DEL{datetime.now().strftime('%Y%m%d%H%M%S')}"
        delivery_columns = _get_table_columns(cur, 'deliveries')
        d_cols = []
        d_vals = []
        def addd(col, val):
            if col in delivery_columns:
                d_cols.append(col)
                d_vals.append(val)
        addd('delivery_number', delivery_number)
        addd('po_id', data['po_id'])
        addd('delivery_date', data['delivery_date'])
        addd('quantity_received', data.get('quantity_received'))
        addd('invoice_number', data.get('invoice_number', ''))
        addd('grn_number', data.get('grn_number', ''))
        addd('invoice_to_finance', data.get('invoice_to_finance', False))
        # Some schemas require received_by
        addd('received_by', 1)
        if not d_cols:
            d_cols = ['po_id', 'delivery_date']
            d_vals = [data['po_id'], data['delivery_date']]
        placeholders = ', '.join(['%s'] * len(d_vals))
        sql = f"INSERT INTO deliveries ({', '.join(d_cols)}) VALUES ({placeholders})"
        cur.execute(sql, tuple(d_vals))
        delivery_id = cur.lastrowid
        
        
        # Create assets based on PR items
        created_assets = []
        quantity_per_item = data['quantity_received'] // len(pr_items) if len(pr_items) > 0 else 0  # Distribute quantity across items
        
        for i, item in enumerate(pr_items):
            # Calculate quantity for this item
            if i == len(pr_items) - 1:
                # Last item gets remaining quantity
                item_quantity = data['quantity_received'] - (quantity_per_item * i)
            else:
                item_quantity = quantity_per_item
            
            if item_quantity <= 0:
                continue
            
            # Parse configuration for asset details
            config = item.get('configuration', '')
            
            # Parse configuration string (format: "processor: Intel i5, ram: 16GB, rom: 128GB SSD")
            processor = ''
            ram = ''
            rom = ''
            mouse_type = ''
            keyboard_type = ''
            keyboard_connection = ''
            printer_type = ''
            printer_function = ''
            printer_connectivity = ''
            system_type = ''
            
            if config:
                # Parse configuration string
                config_parts = config.split(', ')
                for part in config_parts:
                    if ':' in part:
                        key, value = part.split(':', 1)
                        key = key.strip().lower()
                        value = value.strip()
                        
                        if key == 'processor':
                            processor = value
                        elif key == 'ram':
                            ram = value
                        elif key == 'rom':
                            rom = value
                        elif key == 'mouse-type':
                            mouse_type = value
                        elif key == 'keyboard-type':
                            keyboard_type = value
                        elif key == 'keyboard-connection':
                            keyboard_connection = value
                        elif key == 'printer-type':
                            printer_type = value
                        elif key == 'printer-function':
                            printer_function = value
                        elif key == 'printer-connectivity':
                            printer_connectivity = value
                        elif key == 'system-type':
                            system_type = value
            
            # Create assets for this item
            for j in range(item_quantity):
                # Generate unique asset number
                asset_number = f"AST{datetime.now().strftime('%Y%m%d%H%M%S')}{len(created_assets)+1:03d}"
                
                # Determine type details based on asset type
                type_details = ''
                if item['asset_type_name'].lower() == 'laptop':
                    type_details = f"CPU: {processor}, RAM: {ram}, Storage: {rom}"
                elif item['asset_type_name'].lower() == 'mouse':
                    type_details = f"Type: {mouse_type}"
                elif item['asset_type_name'].lower() == 'keyboard':
                    type_details = f"Type: {keyboard_type}, Connection: {keyboard_connection}"
                elif item['asset_type_name'].lower() == 'printer':
                    type_details = f"Type: {printer_type}, Function: {printer_function}, Connectivity: {printer_connectivity}"
                elif item['asset_type_name'].lower() in ['system', 'systems']:
                    type_details = f"Type: {system_type}"
                
                # Determine existing asset columns to build a compatible insert
                assets_columns = _get_table_columns(cur, 'assets')
                assets_cols_info = _get_table_columns_info(cur, 'assets')
                # Build column list and values based on existing schema
                columns = []
                values = []
                def add(col, val):
                    if col in assets_columns:
                        columns.append(col)
                        values.append(val)

                # Required/common fields
                add('asset_number', asset_number)
                # Serial number: only set if column exists and is NOT NULL
                if 'serial_number' in assets_columns:
                    col_info = assets_cols_info.get('serial_number', {})
                    is_nullable = (str(col_info.get('Null', '')).upper() == 'YES')
                    if not is_nullable:
                        # DB requires a value: use a temporary placeholder; user can overwrite later
                        add('serial_number', asset_number)
                add('brand', item.get('brand', ''))
                add('invoice_number', data.get('invoice_number', ''))
                add('ram', ram)
                add('rom', rom)
                add('status', 'available')
                add('purchase_date', data['delivery_date'])
                add('warranty_expiry', None)
                # Cross-schema optional fields
                add('asset_type', item['asset_type_name'])
                add('model', type_details)
                add('processor', processor)
                add('mouse_type', mouse_type)
                add('keyboard_type', keyboard_type)
                add('keyboard_connection', keyboard_connection)
                add('printer_type', printer_type)
                add('printer_function', printer_function)
                add('printer_connectivity', printer_connectivity)
                add('system_type', system_type)
                add('purchase_order_id', data['po_id'])

                # Fallback safety: ensure at least asset_number present
                if not columns:
                    columns = ['asset_number']
                    values = [asset_number]

                sql = f"INSERT INTO assets ({', '.join(columns)}) VALUES ({', '.join(['%s'] * len(values))})"
                cur.execute(sql, tuple(values))
                
                # Add to created assets list
                created_asset_id = cur.lastrowid
                created_assets.append({
                    'id': created_asset_id,
                    'asset_number': asset_number,
                    'asset_type': item['asset_type_name'],
                    'brand': item.get('brand', ''),
                    'vendor': po_details.get('vendor_name', ''),
                    'invoice_number': data.get('invoice_number', ''),
                    'processor': processor,
                    'ram': ram,
                    'rom': rom,
                    'type_details': type_details,
                    'status': 'Available',
                    'serial_number': ''
                })
        
        # Update PO/PR status based on delivered totals
        _update_po_and_pr_status(cur, data['po_id'])
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'delivery_id': delivery_id,
            'assets': created_assets,
            'message': f'Delivery recorded and {len(created_assets)} assets created successfully'
        })
        
    except Exception as e:
        print(f"Error creating delivery with assets: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

# Invoice and Payment APIs
@procurement_bp.route('/api/invoices', methods=['POST'])
def create_invoice():
    """Create an invoice record"""
    try:
        data = request.get_json()
        
        # Calculate payment due date (NETT 30)
        invoice_date = datetime.strptime(data['invoice_date'], '%Y-%m-%d')
        payment_due_date = invoice_date + timedelta(days=30)
        
        conn = get_db_connection(Curr_Proj_Name)
        cur = conn.cursor()
        
        cur.execute('''
            INSERT INTO invoices (delivery_id, invoice_number, invoice_date, 
                                payment_due_date, amount)
            VALUES (%s, %s, %s, %s, %s)
        ''', (data['delivery_id'], data['invoice_number'], data['invoice_date'],
              payment_due_date.strftime('%Y-%m-%d'), data['amount']))
        
        invoice_id = cur.lastrowid
        conn.commit()
        cur.close()
        conn.close()
        
        # Schedule payment reminders
        schedule_payment_reminders(invoice_id, payment_due_date)
        
        return jsonify({
            'success': True,
            'invoice_id': invoice_id,
            'message': 'Invoice created successfully'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@procurement_bp.route('/api/invoices/<int:invoice_id>/payment', methods=['PUT'])
def update_payment(invoice_id):
    """Update payment information"""
    try:
        data = request.get_json()
        
        conn = get_db_connection(Curr_Proj_Name)
        cur = conn.cursor()
        
        cur.execute('''
            UPDATE invoices 
            SET payment_given_date = %s, utr_number = %s, status = 'paid', updated_at = NOW()
            WHERE id = %s
        ''', (data['payment_given_date'], data.get('utr_number', ''), invoice_id))
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': 'Payment information updated successfully'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@procurement_bp.route('/api/invoices', methods=['GET'])
def get_invoices():
    """Get all invoices"""
    try:
        conn = get_db_connection(Curr_Proj_Name)
        cur = conn.cursor()
        
        cur.execute('''
            SELECT i.*, d.delivery_date, po.po_number
            FROM invoices i
            JOIN deliveries d ON i.delivery_id = d.id
            JOIN purchase_orders po ON d.po_id = po.id
            ORDER BY i.created_at DESC
        ''')
        
        invoices = cur.fetchall()
        cur.close()
        conn.close()
        
        return jsonify({'success': True, 'invoices': invoices})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

# Asset Registration API
@procurement_bp.route('/api/assets/register', methods=['POST'])
def register_assets():
    """Register new assets from delivery"""
    data = request.get_json()
    # Legacy endpoint is no-op because assets are created in create-with-assets
    return jsonify({'success': True, 'asset_numbers': [], 'message': 'Assets already created during delivery'})


# Update asset fields (e.g., serial_number, warranty_expiry)
@procurement_bp.route('/api/assets/<int:asset_id>', methods=['PATCH'])
def update_asset_fields(asset_id: int):
    try:
        data = request.get_json() or {}
        serial_number = data.get('serial_number')
        warranty_expiry = data.get('warranty_expiry')  # Expected format YYYY-MM-DD
        
        conn = get_db_connection(Curr_Proj_Name)
        cur = conn.cursor()
        
        assets_columns = _get_table_columns(cur, 'assets')
        if not assets_columns:
            cur.close()
            conn.close()
            return jsonify({'success': False, 'error': 'Assets table not found'}), 400

        updates = []
        params = []

        # Validate and set serial_number
        if serial_number is not None and 'serial_number' in assets_columns:
            # Enforce non-empty if column is NOT NULL
            cols_info = _get_table_columns_info(cur, 'assets')
            is_nullable = (str(cols_info.get('serial_number', {}).get('Null', '')).upper() == 'YES')
            if not is_nullable and (serial_number is None or str(serial_number).strip() == ''):
                cur.close()
                conn.close()
                return jsonify({'success': False, 'error': 'Serial number cannot be empty'}), 400
            # Unique check if possible
            try:
                cur.execute('SELECT id FROM assets WHERE serial_number = %s AND id != %s', (serial_number, asset_id))
                existing = cur.fetchone()
                if existing:
                    cur.close()
                    conn.close()
                    return jsonify({'success': False, 'error': 'Serial number already exists'}), 400
            except Exception:
                pass
            updates.append('serial_number = %s')
            params.append(serial_number)

        # Validate and set warranty_expiry
        if warranty_expiry is not None and 'warranty_expiry' in assets_columns:
            # Allow empty to clear
            if str(warranty_expiry).strip() == '':
                updates.append('warranty_expiry = %s')
                params.append(None)
            else:
                # Basic format check
                try:
                    datetime.strptime(warranty_expiry, '%Y-%m-%d')
                except Exception:
                    cur.close()
                    conn.close()
                    return jsonify({'success': False, 'error': 'Invalid date format. Use YYYY-MM-DD'}), 400
                updates.append('warranty_expiry = %s')
                params.append(warranty_expiry)

        if not updates:
            cur.close()
            conn.close()
            return jsonify({'success': False, 'error': 'No updatable fields provided'}), 400

        sql = f"UPDATE assets SET {', '.join(updates)} WHERE id = %s"
        params.append(asset_id)
        cur.execute(sql, tuple(params))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

# Helper functions (to be implemented)
def send_approval_email(pr_id):
    """Send approval email to manager"""
    # Implement email sending logic
    pass

def send_approval_notification(pr_id, status):
    """Send notification email to requester"""
    # Implement email sending logic
    pass

def schedule_delivery_reminder(po_id, expected_date):
    """Schedule delivery reminder"""
    # Implement reminder scheduling logic
    pass

def schedule_payment_reminders(invoice_id, due_date):
    """Schedule payment reminders (Day 21 and 25)"""
    # Implement reminder scheduling logic
    pass

def generate_asset_numbers(delivery_id, quantity, po_id):
    """Generate asset numbers for received items"""
    # This is handled in the register_assets API
    pass 

# --- Helper: update PO and PR status based on delivered vs to-procure ---
def _update_po_and_pr_status(cur, po_id: int) -> None:
    """Set PO.status to 'delivered' only when fully delivered; otherwise 'partially_delivered'.
    Mirror status to PR: 'delivered' when fully delivered else 'partially_delivered'.
    """
    # Find PR for this PO
    cur.execute('SELECT pr_id FROM purchase_orders WHERE id = %s', (po_id,))
    row = cur.fetchone()
    if not row:
        return
    pr_id = row['pr_id']

    # Total to procure
    cur.execute('''
        SELECT COALESCE(SUM(COALESCE(pri.quantity_to_procure, 0)), 0) AS total_to_procure
        FROM pr_items pri
        LEFT JOIN item_approvals ia ON ia.pr_item_id = pri.id
        WHERE pri.pr_id = %s AND (ia.status = 'approved' OR pri.is_approved = 1)
    ''', (pr_id,))
    total_to_procure = (cur.fetchone() or {}).get('total_to_procure', 0)

    # Total received
    # Use assets count as received proxy to avoid schema mismatches
    cur.execute('SELECT COUNT(*) AS total_received FROM assets WHERE purchase_order_id = %s', (po_id,))
    total_received = (cur.fetchone() or {}).get('total_received', 0)

    if total_to_procure <= 0:
        # No quantity to procure; keep as created/open
        _set_status_with_fallback(cur, 'purchase_orders', 'id', po_id, 'created', 'created')
        _set_status_with_fallback(cur, 'purchase_requests', 'id', pr_id, 'po_created', 'pending')
        return

    if total_received >= total_to_procure:
        _set_status_with_fallback(cur, 'purchase_orders', 'id', po_id, 'delivered', 'delivered')
        _set_status_with_fallback(cur, 'purchase_requests', 'id', pr_id, 'delivered', 'delivered')
    else:
        # Partial delivery: fall back to existing allowed values
        _set_status_with_fallback(cur, 'purchase_orders', 'id', po_id, 'partially_delivered', 'created')
        _set_status_with_fallback(cur, 'purchase_requests', 'id', pr_id, 'partially_delivered', 'po_created')


def _get_table_columns(cur, table_name: str):
    try:
        cur.execute(f"SHOW COLUMNS FROM {table_name}")
        rows = cur.fetchall() or []
        return set([r['Field'] if isinstance(r, dict) else r[0] for r in rows])
    except Exception:
        return set()


def _get_table_columns_info(cur, table_name: str):
    try:
        table_escaped = table_name.replace('`', '``')
        cur.execute(f"SHOW COLUMNS FROM `{table_escaped}`")
        rows = cur.fetchall() or []
        info = {}
        for r in rows:
            if isinstance(r, dict):
                info[r['Field']] = r
            else:
                # Fallback tuple order: Field, Type, Null, Key, Default, Extra
                info[r[0]] = {
                    'Field': r[0], 'Type': r[1], 'Null': r[2], 'Key': r[3], 'Default': r[4], 'Extra': r[5]
                }
        return info
    except Exception:
        return {}

def _get_enum_values(cur, table_name: str, column_name: str):
    try:
        # Note: identifiers cannot be parameterized; use cautious interpolation
        table_escaped = table_name.replace('`', '``')
        col_escaped = column_name.replace('`', '``')
        sql = f"SHOW COLUMNS FROM `{table_escaped}` LIKE '{col_escaped}'"
        cur.execute(sql)
        row = cur.fetchone()
        if not row:
            return set()
        type_def = row.get('Type') if isinstance(row, dict) else row[1]
        if type_def and type_def.lower().startswith('enum('):
            values = type_def[type_def.find('(')+1:type_def.rfind(')')]
            parts = []
            for p in values.split(','):
                p = p.strip()
                if p.startswith("'") and p.endswith("'"):
                    p = p[1:-1]
                parts.append(p)
            return set(parts)
        return set()
    except Exception:
        return set()


def _set_status_with_fallback(cur, table: str, id_col: str, id_val: int, desired: str, fallback: str):
    allowed = _get_enum_values(cur, table, 'status')
    # Try desired, else fallback, else the first allowed, else skip
    if not allowed:
        value = desired
    else:
        if desired in allowed:
            value = desired
        elif fallback in allowed:
            value = fallback
        else:
            # pick a safe default
            value = next(iter(allowed))
    sql = f"UPDATE `{table}` SET status = %s"
    # Add updated_at when column exists
    cols = _get_table_columns(cur, table)
    if 'updated_at' in cols:
        sql += ", updated_at = NOW()"
    sql += f" WHERE `{id_col}` = %s"
    cur.execute(sql, (value, id_val))

SERVER_URL = 'http://localhost:5000'

def send_pr_email(to_email, pr_data):
    try:
        print(f"DEBUG: Starting send_pr_email for PR {pr_data.get('pr_id')}")  # DEBUG
        print(f"DEBUG: To email: {to_email}")  # DEBUG
        print(f"DEBUG: Asset types: {[item.get('asset_type_name', 'Unknown') for item in pr_data.get('items', [])]}")  # DEBUG
        
        gmail_user = 'sapnoreply@violintec.com'
        gmail_password = 'VT$ofT@$2025'

        msg = MIMEMultipart()
        msg['From'] = gmail_user
        msg['To'] = to_email
        msg['Subject'] = f"Official Purchase Request Submission"

        pr_id = pr_data.get('pr_id')
        approve_url = f"{SERVER_URL}/approve_pr/{pr_id}"
        reject_url = f"{SERVER_URL}/reject_pr/{pr_id}"

        # Build the HTML body
        items_html = ''
        total_amount = 0
                
        # Determine which headers to show based on asset types in the request
        asset_types_in_request = set()
        for item in pr_data['items']:
            asset_type = item.get('asset_type_name', '').lower()
            asset_types_in_request.add(asset_type)
        
        # Create dynamic headers based on asset types
        headers = ['Asset Type']
        
        # Add configuration headers based on asset types present
        if any(at in ['laptop', 'system'] for at in asset_types_in_request):
            headers.extend(['Processor', 'RAM', 'ROM'])
        if 'mouse' in asset_types_in_request:
            headers.append('Type')
        if 'keyboard' in asset_types_in_request:
            headers.extend(['Type', 'Connection'])
        if 'printer' in asset_types_in_request:
            headers.extend(['Type', 'Function', 'Connectivity'])
        if 'others' in asset_types_in_request:
            headers.append('Description')
        
        # Add common headers
        headers.extend(['Brand', 'Stock Available', 'Quantity', 'Quantity to Procure', 'Unit Cost', 'Total Amount', 'Vendor Name', 'Ression', 'FAVOR'])
        
        # Create header row
        header_html = '<th style="padding:8px 12px;border:1px solid #ccc;">Approve?</th>'
        for header in headers:
            header_html += f"<th style='padding:8px 12px;border:1px solid #ccc;'>{header}</th>"
        
        for item in pr_data['items']:
            unit_cost = float(item.get('unit_cost', 0) or 0)
            quantity = int(item.get('quantity_required', 0) or 0)
            item_total = float(item.get('total_amount', 0) or (unit_cost * int(item.get('quantity_to_procure', 0) or 0)))
            total_amount += item_total
                    
            # Get individual configuration fields
            additional_fields = item.get('additional_fields', {})
            processor = additional_fields.get('processor', '')
            ram = additional_fields.get('ram', '')
            rom = additional_fields.get('rom', '')
            mouse_type = additional_fields.get('mouse-type', '')
            keyboard_type = additional_fields.get('keyboard-type', '')
            keyboard_connection = additional_fields.get('keyboard-connection', '')
            printer_type = additional_fields.get('printer-type', '')
            printer_function = additional_fields.get('printer-function', '')
            printer_connectivity = additional_fields.get('printer-connectivity', '')
            description = additional_fields.get('description', '')
    
            
            # Determine which configuration fields to show based on asset type
            asset_type = item.get('asset_type_name', '').lower()
            config_values = []
            
            if asset_type in ['laptop', 'system']:
                config_values = [processor, ram, rom]
            elif asset_type == 'mouse':
                config_values = [mouse_type]
            elif asset_type == 'keyboard':
                config_values = [keyboard_type, keyboard_connection]
            elif asset_type == 'printer':
                config_values = [printer_type, printer_function, printer_connectivity]
            elif asset_type == 'others':
                config_values = [description]
            else:
                config_values = [item.get('configuration', '')]
            
            # Create separate columns for each configuration field
            config_columns = ''
            for value in config_values:
                config_columns += f"<td style='padding:6px 12px;border:1px solid #ccc'>{value}</td>"
            
            items_html += f"""
            <tr>
                <td style='padding:6px 12px;border:1px solid #ccc'>
                    <input type="checkbox" name="approved_items" value="{item.get('id', '')}" style="transform: scale(1.2);">
                </td>
                <td style='padding:6px 12px;border:1px solid #ccc'>{item.get('asset_type_name', item.get('asset_type_id'))}</td>
                {config_columns}
                <td style='padding:6px 12px;border:1px solid #ccc'>{item.get('brand', '')}</td>
                <td style='padding:6px 12px;border:1px solid #ccc'>{item.get('stock_available', '')}</td>
                <td style='padding:6px 12px;border:1px solid #ccc'>{quantity}</td>
                <td style='padding:6px 12px;border:1px solid #ccc'>{item.get('quantity_to_procure', '')}</td>
                <td style='padding:6px 12px;border:1px solid #ccc'>{unit_cost:.2f}</td>
                <td style='padding:6px 12px;border:1px solid #ccc'>{item_total:.2f}</td>
                <td style='padding:6px 12px;border:1px solid #ccc'>{item.get('vendor', '')}</td>
                <td style='padding:6px 12px;border:1px solid #ccc'>{item.get('ression', '')}</td>
                <td style='padding:6px 12px;border:1px solid #ccc'>{item.get('favor', 'No')}</td>
            </tr>
            """

        # Email HTML with simple black and white theme
        html_content = f'''
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Purchase Request Submission</title>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    margin: 0;
                    padding: 0;
                    background-color: #ffffff;
                    color: #000000;
                }}
                .email-container {{
                    max-width: 800px;
                    margin: 0 auto;
                    background-color: #ffffff;
                }}
                .header {{
                    background-color: #000000;
                    color: #ffffff;
                    padding: 20px;
                    text-align: center;
                }}
                .header h1 {{
                    margin: 0;
                    font-size: 24px;
                    font-weight: bold;
                }}
                .content {{
                    padding: 20px;
                    background-color: #ffffff;
                }}
                .greeting {{
                    margin-bottom: 20px;
                    font-size: 16px;
                }}
                .summary-box {{
                    background-color: #f5f5f5;
                    border: 1px solid #dddddd;
                    padding: 15px;
                    margin-bottom: 20px;
                }}
                .summary-item {{
                    margin-bottom: 10px;
                    padding-bottom: 10px;
                    border-bottom: 1px solid #dddddd;
                }}
                .summary-item:last-child {{
                    border-bottom: none;
                    margin-bottom: 0;
                }}
                .summary-label {{
                    font-weight: bold;
                    color: #000000;
                }}
                .summary-value {{
                    color: #333333;
                }}
                .status-pending {{
                    background-color: #fff3cd;
                    color: #856404;
                    padding: 5px 10px;
                    border-radius: 3px;
                    display: inline-block;
                }}
                .table-container {{
                    margin: 20px 0;
                    overflow-x: auto;
                }}
                .data-table {{
                    width: 100%;
                    border-collapse: collapse;
                    background-color: #ffffff;
                }}
                .data-table th {{
                    background-color: #666666;
                    color: #ffffff;
                    padding: 12px 8px;
                    text-align: left;
                    border: 1px solid #cccccc;
                }}
                .data-table td {{
                    padding: 6px 12px;
                    border: 1px solid #cccccc;
                    max-width: 120px;
                    overflow: hidden;
                    text-overflow: ellipsis;
                    white-space: nowrap;
                }}
                .action-buttons {{
                    margin-top: 20px;
                    text-align: center;
                }}
                .btn {{
                    display: inline-block;
                    padding: 10px 20px;
                    margin: 0 10px;
                    text-decoration: none;
                    border-radius: 5px;
                    font-weight: bold;
                }}
                .btn-approve {{
                    background-color: #28a745;
                    color: #ffffff;
                }}
                .btn-reject {{
                    background-color: #dc3545;
                    color: #ffffff;
                }}
            </style>
        </head>
        <body>
            <div class="email-container">
                <div class="header">
                    <h1>Purchase Request Submission</h1>
                </div>
                <div class="content">
                    <div class="greeting">
                        <p>Dear Approver,</p>
                        <p>A new Purchase Request (PR) has been submitted for your review and approval. Please find the details below:</p>
                    </div>
                    
                    <div class="summary-box">
                        <div class="summary-item">
                            <span class="summary-label">Justification:</span>
                            <span class="summary-value">{pr_data.get('justification', '')}</span>
                        </div>
                        <div class="summary-item">
                            <span class="summary-label">Status:</span>
                            <span class="status-pending">PENDING APPROVAL</span>
                        </div>
                    </div>
                    
                    <div class="table-container">
                        <table class="data-table">
          <thead>
                                <tr>
                                    {header_html}
            </tr>
          </thead>
          <tbody>
            {items_html}
          </tbody>
        </table>
        </div>
                    
                    <div class="action-buttons">
                        <p style="margin-bottom: 15px; color: #666; font-size: 14px;">
                            <strong>Instructions:</strong> Check the boxes for items you want to approve, then click "Review Items" to proceed with selective approval.
                        </p>
                        <a href="{approve_url}" class="btn btn-approve">Review Items</a>
                        <a href="{reject_url}" class="btn btn-reject">Reject All</a>
      </div>
    </div>
            </div>
        </body>
        </html>
        '''

        msg.attach(MIMEText(html_content, 'html'))

        # Send email
        try:
            print(f"🔧 Attempting to send PR email using: {gmail_user}")
            # Try multiple SMTP servers for business domains
            smtp_servers = [
                ('smtp.violintec.com', 587),
                ('smtp.office365.com', 587),
                ('smtp.gmail.com', 587),
                ('smtp-mail.outlook.com', 587)
            ]
            
            success = False
            for smtp_server, port in smtp_servers:
                try:
                    print(f"🔧 Trying SMTP server: {smtp_server}:{port}")
                    server = smtplib.SMTP(smtp_server, port)
                    server.starttls()
                    print(f"🔧 TLS started successfully with {smtp_server}")
                    server.login(gmail_user, gmail_password)
                    print(f"🔧 Login successful with {smtp_server}")
                    text = msg.as_string()
                    server.sendmail(gmail_user, to_email, text)
                    server.quit()
                    print(f"✅ PR email sent via {smtp_server}")
                    success = True
                    break
                    
                except smtplib.SMTPAuthenticationError as e:
                    print(f"❌ SMTP Authentication Error with {smtp_server}: {e}")
                    continue
                except smtplib.SMTPException as e:
                    print(f"❌ SMTP Error with {smtp_server}: {e}")
                    continue
                except Exception as e:
                    print(f"❌ Error with {smtp_server}: {e}")
                    continue
            
            if not success:
                print("❌ Failed to send PR email with all SMTP servers")
                raise Exception("Failed to send email with all SMTP servers")
                
        except Exception as e:
            print(f"❌ Error sending PR email: {e}")
            raise
        
        print(f"DEBUG: Email sent successfully to {to_email}")  # DEBUG
        
    except Exception as e:
        print(f"ERROR in send_pr_email: {e}")
        raise

@procurement_bp.route('/pr_approval_response', methods=['GET'])
def pr_approval_response():
    """Handle approval/rejection from email link"""
    pr_id = request.args.get('pr_id')
    decision = request.args.get('decision')
    print(f"DEBUG: pr_approval_response called with pr_id: {pr_id}, decision: {decision}")
    try:
        pr_id_int = int(pr_id)
    except Exception as e:
        print(f"ERROR: Invalid pr_id in pr_approval_response: {pr_id}, Error: {e}")
        return render_template_string('<h2>Invalid PR ID.</h2>'), 400
    if not pr_id or decision not in ['approved', 'not_approved']:
        print(f"ERROR: Invalid approval link parameters: pr_id={pr_id}, decision={decision}")
        return render_template_string('<h2>Invalid approval link.</h2>'), 400
    conn = get_db_connection(Curr_Proj_Name)
    cur = conn.cursor()
    try:
        print(f"DEBUG: Looking for PR with id: {pr_id}")
        cur.execute('''
            SELECT u.email, pr.justification, pr.pr_number
            FROM purchase_requests pr
            JOIN users u ON pr.requested_by = u.id
            WHERE pr.id = %s
        ''', (pr_id,))
        pr_row = cur.fetchone()
        print(f"DEBUG: PR query result: {pr_row}")
        if not pr_row:
            cur.close()
            conn.close()
            print(f"ERROR: PR not found for id: {pr_id}")
            return render_template_string('<h2>PR not found.</h2>'), 404
        # Update approval and PR status
        status = 'approved' if decision == 'approved' else 'rejected'
        print(f"DEBUG: Updating approval status for pr_id {pr_id} to {status}")
        cur.execute('UPDATE approvals SET status = %s, approval_date = NOW() WHERE pr_id = %s', (status, pr_id))
        cur.execute('UPDATE purchase_requests SET status = %s WHERE id = %s', (status, pr_id))
        
        # Direct approval - approve all items that are pending
        print(f"DEBUG: Email approval for PR {pr_id} - directly approving pending items")
        
        # Get all pending items for this PR
        cur.execute('''
            SELECT pri.id as pr_item_id
            FROM pr_items pri
            LEFT JOIN item_approvals ia ON pri.id = ia.pr_item_id
            WHERE pri.pr_id = %s
            AND (ia.status IS NULL OR ia.status = 'pending')
        ''', (pr_id,))
        pending_items = cur.fetchall()
        
        # Get approver ID (use the first approver found)
        cur.execute('SELECT approver_id FROM approvals WHERE pr_id = %s LIMIT 1', (pr_id,))
        approver_result = cur.fetchone()
        approver_id = approver_result['approver_id'] if approver_result else 1
        
        # Create item approvals for pending items
        for item in pending_items:
            cur.execute('''
                INSERT INTO item_approvals (pr_item_id, approver_id, status, approval_date, notes)
                VALUES (%s, %s, 'approved', NOW(), 'Approved via email')
                ON DUPLICATE KEY UPDATE status = 'approved', approval_date = NOW()
            ''', (item['pr_item_id'], approver_id))
        
        print(f"DEBUG: Created item approvals for {len(pending_items)} pending items in PR {pr_id}")
        
        # Recalculate total amount based on approved items only
        approved_total = recalculate_approved_total_amount(pr_id)
        print(f"DEBUG: Updated PR {pr_id} total amount to ₹{approved_total} (approved items only)")
        
        conn.commit()
        print(f"DEBUG: Database committed for pr_id {pr_id}")
        cur.close()
        conn.close()
        
        # Show success message
        if decision == 'approved':
            html = f"""
            <div style='font-family:Arial,sans-serif;max-width:600px;margin:auto;'>
              <h2 style='background:#4CAF50;color:#fff;padding:16px 24px;border-radius:6px 6px 0 0;'>Purchase Request Approved</h2>
              <div style='background:#f9f9f9;padding:24px;border-radius:0 0 6px 6px;'>
                <p style='font-size:16px;'>Purchase Request <b>{pr_row['pr_number']}</b> has been <b>Approved</b>.</p>
                <p style='font-size:15px;'>Justification: {pr_row['justification']}</p>
                <p style='font-size:14px;margin-top:20px;'>✅ All pending items have been approved.</p>
                <p style='font-size:14px;color:#888;margin-top:24px;'>This is an automated message from the Procurement System.</p>
              </div>
            </div>
            """
        else:
            html = f"""
            <div style='font-family:Arial,sans-serif;max-width:600px;margin:auto;'>
              <h2 style='background:#f44336;color:#fff;padding:16px 24px;border-radius:6px 6px 0 0;'>Purchase Request Rejected</h2>
              <div style='background:#f9f9f9;padding:24px;border-radius:0 0 6px 6px;'>
                <p style='font-size:16px;'>Purchase Request <b>{pr_row['pr_number']}</b> has been <b>Rejected</b>.</p>
                <p style='font-size:15px;'>Justification: {pr_row['justification']}</p>
                <p style='font-size:14px;color:#888;margin-top:24px;'>This is an automated message from the Procurement System.</p>
              </div>
            </div>
            """
        return render_template_string(html)
    except Exception as e:
        conn.rollback()
        cur.close()
        conn.close()
        print('ERROR in pr_approval_response:', e)
        return render_template_string(f'<h2>Error: {str(e)}</h2>'), 500

@procurement_bp.route('/api/users', methods=['POST'])
def add_user():
    data = request.get_json()
    name = data.get('name', '').strip()
    email = data.get('email', '').strip()
    role = data.get('role', 'manager')
    password = data.get('password', '')
    if not email:
        return jsonify({'success': False, 'error': 'Email required'}), 400
    try:
        conn = get_db_connection(Curr_Proj_Name)
        cur = conn.cursor()
        # Check if user exists
        cur.execute('SELECT id FROM users WHERE email = %s', (email,))
        user = cur.fetchone()
        if user:
            cur.close()
            conn.close()
            return jsonify({'success': True, 'user_id': user['id']})
        # Insert new user
        cur.execute('INSERT INTO users (name, email, password, role) VALUES (%s, %s, %s, %s)', (name or email, email, password, role))
        user_id = cur.lastrowid
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({'success': True, 'user_id': user_id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400 

@procurement_bp.route('/api/send_pr_email', methods=['POST'])
def api_send_pr_email():
    try:
        data = request.get_json()
        to_email = data.get('approver_email')
        if not to_email:
            return jsonify({'success': False, 'error': 'No approver email provided'}), 400
        result = send_pr_email(to_email, data)
        if result:
            return jsonify({'success': True, 'message': 'PR email sent'})
        else:
            return jsonify({'success': False, 'error': 'Failed to send email'}), 500
    except Exception as e:
        print('Error in /api/send_pr_email:', e)
        return jsonify({'success': False, 'error': str(e)}), 400 

# Debug endpoint to check approval status
@procurement_bp.route('/api/debug/approvals', methods=['GET'])
def debug_approvals():
    """Debug endpoint to check approval status for all PRs"""
    try:
        conn = get_db_connection(Curr_Proj_Name)
        cur = conn.cursor()
        
        # Get all PRs with their approval status
        cur.execute('''
            SELECT 
                pr.id,
                pr.pr_number,
                pr.status as pr_status,
                pr.created_at,
                a.id as approval_id,
                a.status as approval_status,
                a.approval_date,
                a.approver_id,
                u.name as approver_name
            FROM purchase_requests pr
            LEFT JOIN approvals a ON pr.id = a.pr_id
            LEFT JOIN users u ON a.approver_id = u.id
            ORDER BY pr.created_at DESC
        ''')
        
        results = cur.fetchall()
        
        # Convert datetime objects
        for row in results:
            if row.get('created_at'):
                row['created_at'] = row['created_at'].isoformat() if hasattr(row['created_at'], 'isoformat') else str(row['created_at'])
            if row.get('approval_date'):
                row['approval_date'] = row['approval_date'].isoformat() if hasattr(row['approval_date'], 'isoformat') else str(row['approval_date'])
        
        cur.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'total_prs': len(results),
            'prs_with_approvals': len([r for r in results if r['approval_id']]),
            'prs_without_approvals': len([r for r in results if not r['approval_id']]),
            'data': results
        })
        
    except Exception as e:
        print(f"ERROR in debug_approvals: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 400 

# Function to create missing approval records
@procurement_bp.route('/api/fix/missing-approvals', methods=['POST'])
def fix_missing_approvals():
    """Create missing approval records for PRs that don't have them"""
    try:
        conn = get_db_connection(Curr_Proj_Name)
        cur = conn.cursor()
        
        # Find PRs without approval records
        cur.execute('''
            SELECT pr.id, pr.pr_number, pr.requested_by
            FROM purchase_requests pr
            LEFT JOIN approvals a ON pr.id = a.pr_id
            WHERE a.id IS NULL
        ''')
        
        missing_approvals = cur.fetchall()
        created_count = 0
        
        for pr in missing_approvals:
            # Get default approver (admin user)
            cur.execute('SELECT id FROM users WHERE role = "admin" LIMIT 1')
            admin_user = cur.fetchone()
            approver_id = admin_user['id'] if admin_user else 1
            
            # Create approval record
            cur.execute('''
                INSERT INTO approvals (pr_id, approver_id, status)
                VALUES (%s, %s, 'pending')
            ''', (pr['id'], approver_id))
            
            created_count += 1
            print(f"Created approval record for PR {pr['pr_number']}")
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': f'Created {created_count} missing approval records',
            'created_count': created_count
        })
        
    except Exception as e:
        print(f"ERROR in fix_missing_approvals: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 400 

@procurement_bp.route('/api/approval_list', methods=['GET'])
def api_approval_list():
    """Return only approved PRs for the Approvals screen, with cleanup of duplicate pending entries"""
    try:
        status = request.args.get('status')
        
        # Perform cleanup to remove duplicate pending entries
        cleanup_result = cleanup_mixed_status_prs()
        deleted_count = cleanup_result[0]
        deleted_items_count = cleanup_result[1]
        deleted_approvals_count = cleanup_result[2]
        
        conn = get_db_connection(Curr_Proj_Name)
        cur = conn.cursor()
        
        # Modified query to show only approved PRs and exclude pending duplicates
        sql = '''
            SELECT 
                a.id as approval_id,
                pr.id as pr_id,
                pr.pr_number,
                u.name as requester_name,
                pr.justification,
                pr.total_amount,
                a.status,
                au.name as approver_name,
                au.email as approver_email,
                a.approval_date,
                GROUP_CONCAT(DISTINCT at.name SEPARATOR ', ') as asset_types,
                GROUP_CONCAT(DISTINCT pri.configuration SEPARATOR ', ') as configurations,
                GROUP_CONCAT(DISTINCT po.po_number SEPARATOR ', ') as po_numbers,
                GROUP_CONCAT(DISTINCT po.po_date SEPARATOR ', ') as po_dates,
                GROUP_CONCAT(DISTINCT po.vendor_name SEPARATOR ', ') as vendor_names,
                GROUP_CONCAT(DISTINCT po.expected_delivery_date SEPARATOR ', ') as expected_delivery_dates,
                GROUP_CONCAT(DISTINCT po.po_file_path SEPARATOR ', ') as po_file_paths,
                (
                    SELECT SUM(pri2.unit_cost * pri2.quantity_to_procure)
                    FROM pr_items pri2
                    WHERE pri2.pr_id = pr.id AND pri2.is_approved = 1
                ) as pr_total_amount
            FROM approvals a
            LEFT JOIN purchase_requests pr ON a.pr_id = pr.id
            LEFT JOIN users u ON pr.requested_by = u.id
            LEFT JOIN users au ON a.approver_id = au.id
            LEFT JOIN pr_items pri ON pr.id = pri.pr_id
            LEFT JOIN asset_types at ON pri.asset_type_id = at.id
            LEFT JOIN purchase_orders po ON pr.id = po.pr_id
            WHERE a.status IN ('approved', 'delivered')
        '''
        params = []
        
        # If specific status filter is requested, apply it
        if status:
            if status == 'approved':
                sql += ' AND a.status IN ("approved", "delivered")'
            elif status == 'pending':
                # Don't show pending items - they should be cleaned up
                sql += ' AND 1=0'  # This will return no results
            elif status == 'rejected':
                sql += ' AND a.status = "rejected"'
        
        sql += ' GROUP BY pr.id, a.id ORDER BY pr.created_at DESC, a.approval_date DESC, a.id DESC'
        cur.execute(sql, tuple(params))
        approvals = cur.fetchall()
        
        for row in approvals:
            if row.get('approval_date'):
                row['approval_date'] = row['approval_date'].isoformat() if hasattr(row['approval_date'], 'isoformat') else str(row['approval_date'])
            # Ensure total amounts are numeric
            if row.get('total_amount'):
                row['total_amount'] = float(row['total_amount'])
            if row.get('pr_total_amount'):
                row['pr_total_amount'] = float(row['pr_total_amount'])
        
        cur.close()
        conn.close()
        
        return jsonify({
            'success': True, 
            'approvals': approvals,
            'cleanup_info': {
                'deleted_pending_approvals': deleted_count,
                'deleted_pending_items': deleted_items_count,
                'deleted_pending_approvals_table': deleted_approvals_count
            }
        })
    except Exception as e:
        print('ERROR in api_approval_list:', e)
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 400 

# Approval routes for email links
@procurement_bp.route('/approve_pr/<int:pr_id>', methods=['GET'])
def approve_pr_page(pr_id):
    """Page to approve a purchase request via email link"""
    try:
        conn = get_db_connection(Curr_Proj_Name)
        cur = conn.cursor()
        
        # Get PR details
        cur.execute('''
            SELECT pr.*, u.name as requester_name, u.email as requester_email
            FROM purchase_requests pr
            LEFT JOIN users u ON pr.requested_by = u.id
            WHERE pr.id = %s
        ''', (pr_id,))
        pr_data = cur.fetchone()
        
        if not pr_data:
            cur.close()
            conn.close()
            return "Purchase Request not found", 404
        
        # Get PR items for the approval page - show only pending items
        cur.execute('''
            SELECT pri.*, at.name as asset_type_name, ia.status as item_approval_status
            FROM pr_items pri
            LEFT JOIN asset_types at ON pri.asset_type_id = at.id
            LEFT JOIN item_approvals ia ON pri.id = ia.pr_item_id
            WHERE pri.pr_id = %s
            AND (ia.status IS NULL OR ia.status = 'pending')
        ''', (pr_id,))
        pr_items = cur.fetchall()
        
        # Prepare data for the HTML template
        item_data_for_html = []
        for item in pr_items:
            # Use stored values from database to match email display
            unit_cost = float(item.get('unit_cost', 0) or 0)
            quantity_required = int(item.get('quantity_required', 0) or 0)
            stock_available = int(item.get('stock_available', 0) or 0)
            quantity_to_procure = int(item.get('quantity_to_procure', 0) or 0)
            
            # Calculate total based on stored quantity_to_procure to match email
            total_amount = unit_cost * quantity_to_procure
            
            item_data_for_html.append({
                'id': item['id'],
                'asset_type_name': item['asset_type_name'] or 'Unknown',
                'configuration': item.get('configuration', ''),
                'brand': item.get('brand', ''),
                'vendor': item.get('vendor', ''),
                'quantity_required': quantity_required,
                'stock_available': stock_available,
                'quantity_to_procure': quantity_to_procure,
                'unit_cost': unit_cost,
                'total_amount': total_amount,
                'vendor_name': item.get('vendor', ''),
                'ression': item.get('ression', ''),
                'favor': item.get('favor', 'No'),
                'item_approval_status': item.get('item_approval_status') or 'Pending'
            })
        
        cur.close()
        conn.close()
        
        # Generate items HTML
        items_html = ''
        for i, item in enumerate(item_data_for_html, 1):
            # Calculate system recommendation based on total amount
            total_amount_value = float(item['total_amount'])
            asset_type_name = item['asset_type_name'].lower()
            
            system_recommendation = ''
            system_recommendation_reason = ''
            
            if asset_type_name == 'laptop':
                if total_amount_value > 80000:
                    system_recommendation = 'High Cost'
                    system_recommendation_reason = 'Consider lower-cost alternatives'
                elif total_amount_value > 50000:
                    system_recommendation = 'Moderate Cost'
                    system_recommendation_reason = 'Within acceptable range'
                else:
                    system_recommendation = 'Good Value'
                    system_recommendation_reason = 'Cost-effective option'
            elif asset_type_name == 'mouse':
                if total_amount_value > 2000:
                    system_recommendation = 'High Cost'
                    system_recommendation_reason = 'Consider standard mouse options'
                else:
                    system_recommendation = 'Good Value'
                    system_recommendation_reason = 'Reasonable price'
            else:
                if total_amount_value > 10000:
                    system_recommendation = 'Review Required'
                    system_recommendation_reason = 'Verify cost justification'
                else:
                    system_recommendation = 'Standard'
                    system_recommendation_reason = 'Typical cost range'
            
            # Determine if checkbox should be checked based on favor status
            is_checked = 'checked' if item['favor'] == 'Yes' else ''
            
            items_html += f'''
                <tr>
                    <td class="checkbox-cell">
                        <input type="checkbox" id="item-{item['id']}-checkbox" name="approved_items" value="{item['id']}" {is_checked} onchange="toggleApprovalJustification({item['id']})">
                    </td>
                    <td>{i}</td>
                    <td>{item['asset_type_name']}</td>
                    <td>{item['brand']}</td>
                    <td>{item['vendor']}</td>
                    <td>{item['configuration']}</td>
                    <td>{item['quantity_required']}</td>
                    <td>{item['stock_available']}</td>
                    <td>{item['quantity_to_procure']}</td>
                    <td>₹{item['unit_cost']}</td>
                    <td>₹{item['total_amount']}</td>
                    <td>
                        <span class="badge bg-{('warning' if 'High' in system_recommendation else 'success' if 'Good' in system_recommendation else 'info')}">
                            {system_recommendation}
                        </span>
                        <br><small class="text-muted">{system_recommendation_reason}</small>
                    </td>
                    <td>
                        <span class="badge bg-{('success' if item['favor'] == 'Yes' else 'danger' if item['favor'] == 'No' else 'secondary')}">
                            {item['favor'] or 'Not Selected'}
                        </span>
                    </td>
                    <td><small class="text-muted">{item.get('favor_reason', 'N/A')}</small></td>
                    <td>
                        <div id="justification-{item['id']}" style="display: {'block' if item['favor'] == 'No' and is_checked else 'none'};">
                            <textarea class="form-control form-control-sm" 
                                      name="approval_justification_{item['id']}" 
                                      placeholder="Why do you want to approve this item despite it being marked as 'Not Recommended'?"
                                      rows="2"
                                      style="font-size: 0.8rem;"></textarea>
                        </div>
                    </td>
                </tr>
            '''
        
        return f'''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Approve Purchase Request</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
            <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.7.2/font/bootstrap-icons.css" rel="stylesheet">
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .container {{ max-width: 1400px; margin: 0 auto; }}
                .header {{ background: #4CAF50; color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0; }}
                .content {{ padding: 20px; border: 1px solid #ddd; border-radius: 0 0 8px 8px; }}
                .btn {{ padding: 10px 20px; margin: 10px; border: none; border-radius: 4px; cursor: pointer; }}
                .btn-approve {{ background: #4CAF50; color: white; }}
                .btn-reject {{ background: #f44336; color: white; }}
                .btn-cancel {{ background: #808080; color: white; }}
                .table-responsive {{ margin-top: 20px; }}
                .table th {{ background-color: #343a40; color: white; }}
                .checkbox-cell {{ text-align: center; }}
                .alert-info {{ background-color: #d1ecf1; border-color: #bee5eb; color: #0c5460; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1><i class="bi bi-check-circle"></i> Approve Purchase Request</h1>
                </div>
                <div class="content">
                    <div class="row mb-4">
                        <div class="col-md-6">
                            <h4><i class="bi bi-file-text"></i> PR #{pr_data['pr_number']}</h4>
                            <p><strong>Requested by:</strong> {pr_data['requester_name']}</p>
                            <p><strong>Justification:</strong> {pr_data['justification']}</p>
                        </div>
                        <div class="col-md-6">
                            <p><strong>Total Amount:</strong> ₹{pr_data['total_amount']}</p>
                            <p><strong>Status:</strong> <span class="badge bg-warning">{pr_data['status']}</span></p>
                        </div>
                    </div>
                    
                    <div class="alert alert-info">
                        <i class="bi bi-info-circle"></i>
                        <strong>Review Items:</strong> Check the boxes for items you want to approve, leave unchecked to reject.
                    </div>
                    
                    <form id="approvalForm">
                        <div class="table-responsive">
                            <table class="table table-striped table-hover">
                                <thead class="table-dark">
                                    <tr>
                                        <th class="checkbox-cell">Approve?</th>
                                        <th>#</th>
                                        <th>Asset Type</th>
                                        <th>Brand</th>
                                        <th>Vendor</th>
                                        <th>Configuration</th>
                                        <th>Quantity Required</th>
                                        <th>Stock Available</th>
                                        <th>Quantity to Procure</th>
                                        <th>Unit Cost</th>
                                        <th>Total Amount</th>
                                        <th>System Recommended</th>
                                        <th>Recommended</th>
                                        <th>Reason</th>
                                        <th>Approval Justification</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {items_html}
                                </tbody>
                            </table>
                        </div>
                         
                        <div class="text-center mt-4">
                            <button type="button" onclick="submitApprovals()" class="btn btn-approve">
                                <i class="bi bi-check-circle"></i> Submit Approvals
                            </button>
                            <button type="button" onclick="window.close()" class="btn btn-cancel">
                                <i class="bi bi-x-circle"></i> Cancel
                            </button>
                        </div>
                    </form>
                </div>
            </div>
            
            <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
            <script>
                function toggleApprovalJustification(itemId) {{
                    const checkbox = document.getElementById(`item-${{itemId}}-checkbox`);
                    const justificationDiv = document.getElementById(`justification-${{itemId}}`);
                    const textarea = justificationDiv.querySelector('textarea');
                    
                    // Check if this item was originally marked as 'No' (Not Recommended)
                    const row = checkbox.closest('tr');
                    const recommendedCell = row.querySelector('td:nth-child(13)'); // Recommended column
                    const recommendedText = recommendedCell.textContent.trim();
                    
                    if (checkbox.checked && recommendedText.includes('No')) {{
                        // Show justification field for items marked as 'No' but being approved
                        justificationDiv.style.display = 'block';
                        textarea.required = true;
                    }} else {{
                        // Hide justification field
                        justificationDiv.style.display = 'none';
                        textarea.required = false;
                        textarea.value = '';
                    }}
                }}
                
                function submitApprovals() {{
                    const checkboxes = document.querySelectorAll('input[name="approved_items"]:checked');
                    const allCheckboxes = document.querySelectorAll('input[name="approved_items"]');
                    
                    // Validate required justifications
                    let missingJustifications = [];
                    checkboxes.forEach(checkbox => {{
                        const itemId = checkbox.value;
                        const justificationDiv = document.getElementById(`justification-${{itemId}}`);
                        const textarea = justificationDiv.querySelector('textarea');
                        
                        if (justificationDiv.style.display === 'block' && !textarea.value.trim()) {{
                            missingJustifications.push(itemId);
                        }}
                    }});
                    
                    if (missingJustifications.length > 0) {{
                        alert('Please provide justification for items marked as "Not Recommended" that you want to approve.');
                        return;
                    }}
                    
                    const approvedItems = Array.from(checkboxes).map(cb => parseInt(cb.value));
                    const rejectedItems = Array.from(allCheckboxes)
                        .filter(cb => !cb.checked)
                        .map(cb => parseInt(cb.value));
                    
                    // Collect approval justifications
                    const approvalJustifications = {{}};
                    checkboxes.forEach(checkbox => {{
                        const itemId = checkbox.value;
                        const justificationDiv = document.getElementById(`justification-${{itemId}}`);
                        const textarea = justificationDiv.querySelector('textarea');
                        
                        if (justificationDiv.style.display === 'block' && textarea.value.trim()) {{
                            approvalJustifications[itemId] = textarea.value.trim();
                        }}
                    }});
                    
                    fetch(`/api/purchase_requests/{pr_id}/approve_items`, {{
                        method: 'POST',
                        headers: {{
                            'Content-Type': 'application/json',
                        }},
                        body: JSON.stringify({{
                            approved_items: approvedItems,
                            rejected_items: rejectedItems,
                            approval_justifications: approvalJustifications
                        }})
                    }})
                    .then(response => response.json())
                    .then(data => {{
                        if (data.success) {{
                            alert('Item approvals submitted successfully! PR Status: ' + data.pr_status);
                            window.close();
                        }} else {{
                            alert('Error: ' + data.error);
                        }}
                    }})
                    .catch(error => {{
                        console.error('Error:', error);
                        alert('Error submitting approvals');
                    }});
                }}
            </script>
        </body>
        </html>
        '''
    except Exception as e:
        print(f"ERROR in approve_pr_page: {e}")
        import traceback
        traceback.print_exc()
        return f"Error: {str(e)}", 500

@procurement_bp.route('/reject_pr/<int:pr_id>', methods=['GET'])
def reject_pr_page(pr_id):
    """Simple reject page"""
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Reject Purchase Request</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; }}
            .container {{ max-width: 600px; margin: 0 auto; }}
            .header {{ background: #f44336; color: white; padding: 20px; text-align: center; }}
            .content {{ padding: 20px; border: 1px solid #ddd; }}
            .btn {{ padding: 10px 20px; margin: 10px; border: none; border-radius: 4px; cursor: pointer; }}
            .btn-approve {{ background: #4CAF50; color: white; }}
            .btn-reject {{ background: #f44336; color: white; }}
            .btn-cancel {{ background: #808080; color: white; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Reject Purchase Request</h1>
            </div>
            <div class="content">
                <h2>PR #{pr_id}</h2>
                <p>Are you sure you want to reject this purchase request?</p>
                
                <div style="text-align: center; margin-top: 30px;">
                    <button class="btn btn-approve" onclick="approvePR({pr_id})">Approve Instead</button>
                    <button class="btn btn-reject" onclick="rejectPR({pr_id})">Confirm Reject</button>
                    <button class="btn btn-cancel" onclick="window.close()">Cancel</button>
                </div>
            </div>
        </div>
        
        <script>
            function approvePR(prId) {{
                window.location.href = `/approve_pr/${{prId}}`;
            }}
            
            function rejectPR(prId) {{
                fetch(`/api/purchase_requests/${{prId}}/approve`, {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json',
                    }},
                    body: JSON.stringify({{
                        status: 'rejected'
                    }})
                }})
                .then(response => response.json())
                .then(data => {{
                    if (data.success) {{
                        alert('Purchase Request rejected successfully!');
                        window.close();
                    }} else {{
                        alert('Error: ' + data.error);
                    }}
                }})
                .catch(error => {{
                    console.error('Error:', error);
                    alert('Error rejecting purchase request');
                }});
            }}
        </script>
    </body>
    </html>
    """

@procurement_bp.route('/pr_details/<int:pr_id>', methods=['GET'])
def pr_details_page(pr_id):
    """Display detailed view of a specific PR"""
    try:
        print(f"DEBUG: Loading PR details for PR ID: {pr_id}")
        conn = get_db_connection(Curr_Proj_Name)
        cur = conn.cursor()
        
        # Get PR details with approved total amount
        cur.execute('''
            SELECT pr.*, u.name as requester_name, u.email as requester_email,
                   (
                       SELECT SUM(pri2.unit_cost * pri2.quantity_to_procure)
                       FROM pr_items pri2
                       WHERE pri2.pr_id = pr.id AND pri2.is_approved = 1
                   ) as approved_total_amount
            FROM purchase_requests pr
            LEFT JOIN users u ON pr.requested_by = u.id
            WHERE pr.id = %s
        ''', (pr_id,))
        pr_data = cur.fetchone()
        
        if not pr_data:
            print(f"DEBUG: PR {pr_id} not found")
            return "PR not found", 404
        
        print(f"DEBUG: Found PR data: {pr_data}")
        
        # Get PR items - only show approved items (bring additional fields if stored)
        cur.execute('''
            SELECT pri.*, at.name as asset_type_name, ia.status as approval_status, ia.notes as approval_justification
            FROM pr_items pri
            LEFT JOIN asset_types at ON pri.asset_type_id = at.id
            INNER JOIN item_approvals ia ON pri.id = ia.pr_item_id
            WHERE pri.pr_id = %s AND ia.status = 'approved'
        ''', (pr_id,))
        pr_items = cur.fetchall() or []
        # Compose configuration for systems/laptops if empty using additional_fields JSON if present
        for it in pr_items:
            cfg = (it.get('configuration') or '').strip()
            if not cfg:
                add = it.get('additional_fields')
                try:
                    if isinstance(add, str):
                        add = json.loads(add)
                except Exception:
                    add = None
                processor = (add or {}).get('processor') or it.get('processor') or ''
                ram = (add or {}).get('ram') or it.get('ram') or ''
                rom = (add or {}).get('rom') or it.get('rom') or ''
                system_type = (add or {}).get('system-type') or (add or {}).get('system_type') or it.get('system_type') or ''
                parts = []
                if processor: parts.append(f"processor: {processor}")
                if ram: parts.append(f"ram: {ram}")
                if rom: parts.append(f"rom: {rom}")
                if system_type: parts.append(f"type: {system_type}")
                if parts:
                    it['configuration'] = ', '.join(parts)
        print(f"DEBUG: Found {len(pr_items)} PR items")
        
        # Get approval details - get the latest approved approval
        cur.execute('''
            SELECT a.*, u.name as approver_name, u.email as approver_email
            FROM approvals a
            LEFT JOIN users u ON a.approver_id = u.id
            WHERE a.pr_id = %s AND a.status = 'approved'
            ORDER BY a.approval_date DESC
            LIMIT 1
        ''', (pr_id,))
        approval_data = cur.fetchone()
        print(f"DEBUG: Approval data: {approval_data}")
        
        # If no approved approval found, get any approval for status display
        if not approval_data:
            cur.execute('''
                SELECT a.*, u.name as approver_name, u.email as approver_email
                FROM approvals a
                LEFT JOIN users u ON a.approver_id = u.id
                WHERE a.pr_id = %s
                ORDER BY a.approval_date DESC
                LIMIT 1
            ''', (pr_id,))
            approval_data = cur.fetchone()
            print(f"DEBUG: Fallback approval data: {approval_data}")
        
        # Get PO details if exists
        cur.execute('''
            SELECT * FROM purchase_orders WHERE pr_id = %s
        ''', (pr_id,))
        po_data = cur.fetchone()
        print(f"DEBUG: PO data: {po_data}")
        
        cur.close()
        conn.close()
        
        return render_template('pr_details.html', 
                             pr=pr_data, 
                             items=pr_items, 
                             approval=approval_data,
                             po=po_data)
    except Exception as e:
        print(f"ERROR in pr_details_page: {e}")
        import traceback
        traceback.print_exc()
        return "Error loading PR details", 500 

# Search Approved PRs API
@procurement_bp.route('/api/search_approved_prs', methods=['GET'])
def search_approved_prs():
    """Search approved PRs for dropdown with search functionality"""
    try:
        search_term = request.args.get('search', '').strip()
        
        conn = get_db_connection(Curr_Proj_Name)
        cur = conn.cursor()
        
        # Build the query to get approved PRs with search functionality
        query = '''
            SELECT DISTINCT pr.id as pr_id, pr.pr_number, pr.created_at, u.name as requester_name
            FROM purchase_requests pr
            LEFT JOIN users u ON pr.requested_by = u.id
            LEFT JOIN approvals a ON pr.id = a.pr_id
            WHERE pr.status = 'approved' 
            AND a.status = 'approved'
        '''
        params = []
        
        # Add search functionality
        if search_term:
            query += ''' AND (pr.pr_number LIKE %s OR u.name LIKE %s)'''
            params.extend([f'%{search_term}%', f'%{search_term}%'])
        
        query += ''' ORDER BY pr.created_at DESC LIMIT 50'''
        
        cur.execute(query, params)
        results = cur.fetchall()
        
        cur.close()
        conn.close()
        
        # Format results for dropdown
        prs = []
        for row in results:
            prs.append({
                'pr_id': row['pr_id'],
                'pr_number': row['pr_number'],
                'requester_name': row['requester_name'],
                'created_at': row['created_at'].strftime('%Y-%m-%d') if row['created_at'] else ''
            })
        
        return jsonify({'success': True, 'prs': prs})
    except Exception as e:
        print(f"ERROR in search_approved_prs: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400 

# Get PR details by PR number for upload PO form
@procurement_bp.route('/api/purchase_requests/by_number/<pr_number>', methods=['GET'])
def get_purchase_request_by_number(pr_number):
    """Get PR details by PR number for upload PO form"""
    try:
        conn = get_db_connection(Curr_Proj_Name)
        cur = conn.cursor()
        
        # Get PR details
        cur.execute('''
            SELECT pr.*, u.name as requester_name, u.email as requester_email
            FROM purchase_requests pr
            LEFT JOIN users u ON pr.requested_by = u.id
            WHERE pr.pr_number = %s
        ''', (pr_number,))
        pr_data = cur.fetchone()
        
        if not pr_data:
            cur.close()
            conn.close()
            return jsonify({'success': False, 'error': 'PR not found'}), 404
        
        # Get PR items with approval status
        cur.execute('''
            SELECT pri.*, at.name as asset_type_name, 
                   COALESCE(ia.status, 'NO_APPROVAL') as approval_status
            FROM pr_items pri
            LEFT JOIN asset_types at ON pri.asset_type_id = at.id
            LEFT JOIN item_approvals ia ON pri.id = ia.pr_item_id
            WHERE pri.pr_id = %s
        ''', (pr_data['id'],))
        pr_items = cur.fetchall()
        
        # Get approval details
        cur.execute('''
            SELECT a.*, u.name as approver_name
            FROM approvals a
            LEFT JOIN users u ON a.approver_id = u.id
            WHERE a.pr_id = %s
        ''', (pr_data['id'],))
        approval_data = cur.fetchone()
        
        cur.close()
        conn.close()
        
        # Format the response
        response_data = {
            'success': True,
            'purchase_request': {
                'id': pr_data['id'],
                'pr_number': pr_data['pr_number'],
                'status': pr_data['status'],
                'total_amount': float(pr_data['total_amount']) if pr_data['total_amount'] else 0,
                'created_at': pr_data['created_at'].strftime('%Y-%m-%d') if pr_data['created_at'] else '',
                'requester_name': pr_data['requester_name'],
                'requester_email': pr_data['requester_email'],
                'justification': pr_data.get('justification', '')
            },
            'items': []
        }
        
        # Add items
        for item in pr_items:
            response_data['items'].append({
                'id': item['id'],
                'asset_type_name': item['asset_type_name'],
                'configuration': item['configuration'],
                'quantity_required': item['quantity_required'],
                'quantity_to_procure': item['quantity_to_procure'],
                'unit_cost': float(item['unit_cost']) if item['unit_cost'] else 0,
                'total_cost': float(item['quantity_to_procure'] * item['unit_cost']) if item['quantity_to_procure'] and item['unit_cost'] else 0,
                'brand': item['brand'],
                'vendor': item['vendor'],
                'favor': item['favor'],
                'approval_status': item['approval_status']
            })
        
        # Add approval info
        if approval_data:
            response_data['approval'] = {
                'status': approval_data['status'],
                'approver_name': approval_data['approver_name'],
                'approval_date': approval_data['approval_date'].strftime('%Y-%m-%d') if approval_data['approval_date'] else ''
            }
        
        return jsonify(response_data)
        
    except Exception as e:
        print(f"ERROR in get_purchase_request_by_number: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@procurement_bp.route('/api/approved_items', methods=['GET'])
def api_approved_items():
    """Return only the approved items for the Approvals screen with cleanup logic"""
    try:
        status = request.args.get('status', 'approved')
        
        # Perform cleanup
        cleanup_result = cleanup_mixed_status_prs()
        deleted_count = cleanup_result[0]
        deleted_items_count = cleanup_result[1]
        deleted_approvals_count = cleanup_result[2]
        
        conn = get_db_connection(Curr_Proj_Name)
        cur = conn.cursor()
        
        # Now get approved items with total amounts
        sql = '''
            SELECT 
                ia.id as item_approval_id,
                pri.id as pr_item_id,
                pr.id as pr_id,
                pr.pr_number,
                u.name as requester_name,
                pr.justification,
                at.name as asset_type_name,
                pri.configuration,
                pri.brand,
                pri.vendor,
                pri.quantity_required,
                pri.quantity_to_procure,
                pri.unit_cost,
                (pri.unit_cost * pri.quantity_to_procure) as total_amount,
                pri.favor,
                pri.ression,
                ia.status as item_status,
                au.name as approver_name,
                au.email as approver_email,
                ia.approval_date,
                ia.notes,
                (
                    SELECT SUM(pri2.unit_cost * pri2.quantity_to_procure)
                    FROM pr_items pri2
                    WHERE pri2.pr_id = pr.id AND pri2.is_approved = 1
                ) as pr_total_amount
            FROM item_approvals ia
            LEFT JOIN pr_items pri ON ia.pr_item_id = pri.id
            LEFT JOIN purchase_requests pr ON pri.pr_id = pr.id
            LEFT JOIN users u ON pr.requested_by = u.id
            LEFT JOIN users au ON ia.approver_id = au.id
            LEFT JOIN asset_types at ON pri.asset_type_id = at.id
            WHERE ia.status = 'approved'
            ORDER BY ia.approval_date DESC, pr.created_at DESC, ia.id DESC
        '''
        
        cur.execute(sql)
        approved_items = cur.fetchall()
        
        for row in approved_items:
            if row.get('approval_date'):
                row['approval_date'] = row['approval_date'].isoformat() if hasattr(row['approval_date'], 'isoformat') else str(row['approval_date'])
            # Ensure total amounts are numeric
            if row.get('total_amount'):
                row['total_amount'] = float(row['total_amount'])
            if row.get('pr_total_amount'):
                row['pr_total_amount'] = float(row['pr_total_amount'])
        
        cur.close()
        conn.close()
        return jsonify({
            'success': True, 
            'approved_items': approved_items,
            'cleanup_info': {
                'deleted_pending_approvals': deleted_count,
                'deleted_pending_items': deleted_items_count,
                'deleted_pending_approvals_table': deleted_approvals_count
            }
        })
    except Exception as e:
        print('ERROR in api_approved_items:', e)
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 400

def cleanup_mixed_status_prs():
    """Clean up pending rows for PRs that have approved items and remove duplicate pending entries"""
    conn = get_db_connection(Curr_Proj_Name)
    cur = conn.cursor()
    
    try:
        # Get PRs that have approved items
        cur.execute('''
            SELECT DISTINCT pr.id
            FROM purchase_requests pr
            INNER JOIN pr_items pri ON pr.id = pri.pr_id
            WHERE pri.is_approved = 1
        ''')
        approved_pr_ids = [row['id'] for row in cur.fetchall()]
        
        deleted_count = 0
        deleted_items_count = 0
        deleted_approvals_count = 0
        
        if approved_pr_ids:
            # Delete pending item approvals for these PRs
            placeholders = ','.join(['%s'] * len(approved_pr_ids))
            cleanup_sql = f'''
                DELETE ia FROM item_approvals ia
                INNER JOIN pr_items pri ON ia.pr_item_id = pri.id
                WHERE pri.pr_id IN ({placeholders}) AND ia.status = 'pending'
            '''
            cur.execute(cleanup_sql, approved_pr_ids)
            deleted_count = cur.rowcount
            
            # Delete pending items for these PRs
            cleanup_items_sql = f'''
                DELETE pri FROM pr_items pri
                WHERE pri.pr_id IN ({placeholders}) AND (pri.is_approved IS NULL OR pri.is_approved = 0)
            '''
            cur.execute(cleanup_items_sql, approved_pr_ids)
            deleted_items_count = cur.rowcount
            
            # Delete pending approvals from approvals table for these PRs
            cleanup_approvals_sql = f'''
                DELETE FROM approvals 
                WHERE pr_id IN ({placeholders}) AND status = 'pending'
            '''
            cur.execute(cleanup_approvals_sql, approved_pr_ids)
            deleted_approvals_count = cur.rowcount
            
            print(f"Cleanup: Deleted {deleted_count} pending item approvals, {deleted_items_count} pending items, and {deleted_approvals_count} pending approvals for PRs with approved items")
        
        # Additional cleanup: Remove duplicate pending entries for all PRs
        # Keep only the most recent approval for each PR
        cur.execute('''
            DELETE a1 FROM approvals a1
            INNER JOIN approvals a2 ON a1.pr_id = a2.pr_id 
            WHERE a1.status = 'pending' 
            AND a2.status = 'pending'
            AND a1.id < a2.id
        ''')
        duplicate_pending_deleted = cur.rowcount
        
        # Remove orphaned pending item approvals
        cur.execute('''
            DELETE ia FROM item_approvals ia
            LEFT JOIN approvals a ON ia.pr_item_id IN (
                SELECT pri.id FROM pr_items pri 
                WHERE pri.pr_id = a.pr_id
            )
            WHERE ia.status = 'pending' 
            AND a.id IS NULL
        ''')
        orphaned_approvals_deleted = cur.rowcount
        
        if duplicate_pending_deleted > 0 or orphaned_approvals_deleted > 0:
            print(f"Additional cleanup: Deleted {duplicate_pending_deleted} duplicate pending approvals and {orphaned_approvals_deleted} orphaned item approvals")
        
        conn.commit()
        return deleted_count, deleted_items_count, deleted_approvals_count
        
    except Exception as e:
        print(f"Error in cleanup: {e}")
        conn.rollback()
        return 0, 0, 0
    finally:
        cur.close()
        conn.close()

# Super Admin Item Approval API
@procurement_bp.route('/api/super-admin/approve-items', methods=['POST'])
def super_admin_approve_items():
    """Super Admin can approve/reject individual PR items with justification"""
    try:
        data = request.get_json()
        pr_id = data.get('pr_id')
        items = data.get('items', [])
        status = data.get('status')  # 'approved' or 'rejected'
        
        if not pr_id or not items or status not in ['approved', 'rejected']:
            return jsonify({'success': False, 'error': 'Invalid request data'}), 400
        
        conn = get_db_connection(Curr_Proj_Name)
        cur = conn.cursor()
        
        # Get current user (Super Admin)
        from flask_login import current_user
        approver_id = current_user.id if current_user.is_authenticated else 1
        
        # Get list of approved item IDs for permanent deletion logic
        approved_item_ids = [item_data.get('item_id') for item_data in items if item_data.get('item_id')]
        
        # Process each item
        for item_data in items:
            item_id = item_data.get('item_id')
            justification = item_data.get('justification', '')
            
            if not item_id:
                continue
            
            # Update item approval status
            cur.execute('''
                UPDATE pr_items 
                SET is_approved = %s, approved_at = NOW()
                WHERE id = %s AND pr_id = %s
            ''', (1 if status == 'approved' else 0, item_id, pr_id))
            
            # Create or update approval record for this item
            cur.execute('''
                INSERT INTO item_approvals (pr_item_id, approver_id, status, approval_date, notes)
                VALUES (%s, %s, %s, NOW(), %s)
                ON DUPLICATE KEY UPDATE 
                status = VALUES(status), 
                approval_date = VALUES(approval_date), 
                notes = VALUES(notes)
            ''', (item_id, approver_id, status, justification))
        
        # If status is 'approved', permanently delete all unapproved items
        if status == 'approved' and approved_item_ids:
            # Delete unapproved items from pr_items table
            approved_ids_str = ','.join(map(str, approved_item_ids))
            cur.execute(f'''
                DELETE FROM pr_items 
                WHERE pr_id = %s AND id NOT IN ({approved_ids_str})
            ''', (pr_id,))
            
            # Delete corresponding item_approvals records for deleted items
            cur.execute(f'''
                DELETE ia FROM item_approvals ia
                LEFT JOIN pr_items pri ON ia.pr_item_id = pri.id
                WHERE pri.id IS NULL
            ''')
            
            print(f"Permanently deleted unapproved items for PR {pr_id}. Kept only approved items: {approved_item_ids}")
        
        # Check if all items are approved
        cur.execute('''
            SELECT COUNT(*) as total_items, 
                   SUM(CASE WHEN is_approved = 1 THEN 1 ELSE 0 END) as approved_items
            FROM pr_items 
            WHERE pr_id = %s
        ''', (pr_id,))
        
        item_stats = cur.fetchone()
        total_items = item_stats['total_items']
        approved_items = item_stats['approved_items']
        
        # Update PR status based on item approvals
        if approved_items == total_items:
            # All items approved - approve the PR
            cur.execute('UPDATE purchase_requests SET status = "approved" WHERE id = %s', (pr_id,))
            
            # Create PR-level approval record
            cur.execute('''
                INSERT INTO approvals (pr_id, approver_id, status, approval_date, notes)
                VALUES (%s, %s, %s, NOW(), %s)
                ON DUPLICATE KEY UPDATE 
                status = VALUES(status), 
                approval_date = VALUES(approval_date), 
                notes = VALUES(notes)
            ''', (pr_id, approver_id, 'approved', f'All {approved_items} items approved by Super Admin'))
            
        elif approved_items == 0:
            # No items approved - reject the PR
            cur.execute('UPDATE purchase_requests SET status = "rejected" WHERE id = %s', (pr_id,))
            
            # Create PR-level rejection record
            cur.execute('''
                INSERT INTO approvals (pr_id, approver_id, status, approval_date, notes)
                VALUES (%s, %s, %s, NOW(), %s)
                ON DUPLICATE KEY UPDATE 
                status = VALUES(status), 
                approval_date = VALUES(approval_date), 
                notes = VALUES(notes)
            ''', (pr_id, approver_id, 'rejected', f'All {total_items} items rejected by Super Admin'))
        
        else:
            # Partial approval - keep PR as pending but update notes
            cur.execute('''
                INSERT INTO approvals (pr_id, approver_id, status, approval_date, notes)
                VALUES (%s, %s, %s, NOW(), %s)
                ON DUPLICATE KEY UPDATE 
                notes = VALUES(notes)
            ''', (pr_id, approver_id, 'pending', f'Partial approval: {approved_items}/{total_items} items approved by Super Admin'))
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({
            'success': True, 
            'message': f'Processed {len(items)} items. {approved_items}/{total_items} items approved.',
            'total_items': total_items,
            'approved_items': approved_items
        })
        
    except Exception as e:
        print('ERROR in super_admin_approve_items:', e)
        return jsonify({'success': False, 'error': str(e)}), 400