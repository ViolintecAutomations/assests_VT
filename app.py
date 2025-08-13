from flask import Flask, render_template, redirect, url_for, request, flash, abort, Response, jsonify
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_bootstrap import Bootstrap
from flask_wtf.csrf import CSRFProtect, CSRFError
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, DateField, SelectField
from wtforms.validators import DataRequired, Email
from werkzeug.security import check_password_hash, generate_password_hash
import os
from functools import wraps
import datetime
import csv
import pymysql
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Import procurement blueprint
from procurement_api import procurement_bp

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = 'Violin@12'
app.config['MYSQL_DB'] = 'CMS'
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'

login_manager = LoginManager(app)
login_manager.login_view = 'login'
Bootstrap(app)
csrf = CSRFProtect(app)

# Exempt API endpoints from CSRF protection
csrf.exempt(procurement_bp)

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('Admin access required.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def it_team_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role not in ['admin', 'it_team']:
            flash('IT Team access required.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def super_admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'super_admin':
            flash('Super Admin access required.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

class User(UserMixin):
    def __init__(self, id, email, role):
        self.id = id
        self.email = email
        self.role = role

    @staticmethod
    def get(user_id):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT * FROM users WHERE id = %s', (user_id,))
        user = cur.fetchone()
        cur.close()
        conn.close()
        if user:
            return User(user['id'], user['email'], user['role'])
        return None

@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id)

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

def get_asset_types(names_only=False):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT id, name FROM asset_types ORDER BY name')
    types = [{'id': row['id'], 'name': row['name']} for row in cur.fetchall()]
    cur.close()
    conn.close()
    preferred_order = ['Laptop', 'System', 'Mouse', 'Keyboard', 'Printer', 'Camera']
    preferred_types = [t for t in types if t['name'] in preferred_order]
    other_types = [t for t in types if t['name'] not in preferred_order]
    preferred_types.sort(key=lambda x: preferred_order.index(x['name']) if x['name'] in preferred_order else 999)
    other_types.sort(key=lambda x: x['name'])
    all_types = preferred_types + other_types
    if names_only:
        return [t['name'] for t in all_types]
    return all_types

@app.route('/api/asset_types', methods=['GET'])
def api_get_asset_types():
    types = get_asset_types()
    return jsonify({'types': types})

@app.route('/api/asset_types', methods=['POST'])
@csrf.exempt
def api_add_asset_type():
    data = request.get_json()
    name = data.get('name', '').strip()
    if not name:
        resp = jsonify({'success': False, 'error': 'Name required'})
        return resp, 400
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute('INSERT INTO asset_types (name) VALUES (%s)', (name,))
        conn.commit()
    except Exception as e:
        resp = jsonify({'success': False, 'error': str(e)})
        cur.close()
        conn.close()
        return resp, 400
    cur.close()
    conn.close()
    resp = jsonify({'success': True, 'name': name})
    return resp

@app.route('/api/asset_types/<name>', methods=['DELETE'])
@csrf.exempt
def api_delete_asset_type(name):
    name = name.strip()
    if not name:
        return jsonify({'success': False, 'error': 'Name required'}), 400
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute('DELETE FROM asset_types WHERE name = %s', (name,))
        conn.commit()
    except Exception as e:
        cur.close()
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 400
    cur.close()
    conn.close()
    return jsonify({'success': True, 'name': name})

class AssetForm(FlaskForm):
    asset_number = StringField('Asset Number', validators=[DataRequired()])
    serial_number = StringField('Serial Number', validators=[DataRequired()])
    brand = StringField('Brand', validators=[DataRequired()])

    type = StringField('Type')  # New field for mouse/keyboard type
    processor = StringField('Processor')  # For laptops
    mouse_type = StringField('Mouse Type')  # For mice
    keyboard_type = StringField('Keyboard Type')  # For keyboards
    keyboard_connection = StringField('Keyboard Connection')  # For keyboards
    printer_type = StringField('Printer Type')  # For printers
    printer_function = StringField('Printer Function')  # For printers
    printer_connectivity = StringField('Printer Connectivity')  # For printers
    system_type = StringField('System Type')  # For systems
    invoice_number = StringField('Invoice Number')
    ram = StringField('RAM')
    rom = StringField('ROM')
    purchase_date = DateField('Purchase Date', format='%Y-%m-%d')
    warranty_expiry = DateField('Warranty Expiry', format='%Y-%m-%d')
    asset_type = StringField('Asset Type', validators=[DataRequired()])
    submit = SubmitField('Save')

class AssignAssetForm(FlaskForm):
    asset_id = SelectField('Asset', coerce=int, validators=[DataRequired()])
    user_id = SelectField('User', coerce=int, validators=[DataRequired()])
    unit = StringField('Unit', validators=[DataRequired()])
    submit = SubmitField('Assign')

class UserRequestForm(FlaskForm):
    asset_type = StringField('Asset Type', validators=[DataRequired()])
    request_type = SelectField('Request Type', choices=[('new', 'New'), ('return', 'Return'), ('replacement', 'Replacement')], validators=[DataRequired()])
    details = StringField('Details')
    submit = SubmitField('Submit Request')

class UserForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password')
    role = SelectField('Role', choices=[('admin', 'Admin'), ('it_team', 'IT Team'), ('user', 'User'), ('super_admin', 'Super Admin')], validators=[DataRequired()])
    submit = SubmitField('Save')

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data
        password = form.password.data
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT * FROM users WHERE email = %s', (email,))
        user = cur.fetchone()
        cur.close()
        conn.close()
        if user and user['password'] == password:
            user_obj = User(user['id'], user['email'], user['role'])
            login_user(user_obj)
            flash('Logged in successfully!', 'success')
            
            # Redirect based on user role
            if user['role'] == 'it_team':
                return redirect(request.args.get('next') or url_for('it_dashboard'))
            else:
                return redirect(request.args.get('next') or url_for('dashboard'))
        else:
            flash('Invalid email or password.', 'danger')
    return render_template('login.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/')
@login_required
def dashboard():
    # Redirect IT Team users to their dashboard
    if current_user.role == 'it_team':
        return redirect(url_for('it_dashboard'))
    # Redirect Super Admin users to their dashboard
    elif current_user.role == 'super_admin':
        return redirect(url_for('super_admin_dashboard'))
    # Regular admin and user dashboard
    else:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Get asset counts
        cur.execute('SELECT COUNT(*) as total FROM assets')
        total_assets = cur.fetchone()['total']
        
        cur.execute('SELECT COUNT(*) as assigned FROM assets WHERE status = "assigned"')
        assigned_assets = cur.fetchone()['assigned']
        
        cur.execute('SELECT COUNT(*) as available FROM assets WHERE status = "available"')
        available_assets = cur.fetchone()['available']
        
        cur.execute('SELECT COUNT(*) as maintenance FROM assets WHERE status = "maintenance"')
        maintenance_assets = cur.fetchone()['maintenance']
        
        # Get recent assignments - using the correct table name
        cur.execute('''
            SELECT a.*, assets.serial_number, assets.brand, assets.asset_type, users.name as user_name
            FROM assignments a
            JOIN assets ON a.asset_id = assets.id
            JOIN users ON a.user_id = users.id
            WHERE a.returned_at IS NULL
            ORDER BY a.assigned_at DESC
            LIMIT 5
        ''')
        recent_assignments = cur.fetchall()
        
        cur.close()
        conn.close()
        
        return render_template('dashboard.html', 
                             total_assets=total_assets,
                             assigned_assets=assigned_assets,
                             available_assets=available_assets,
                             maintenance_assets=maintenance_assets,
                             recent_assignments=recent_assignments)

@app.route('/it-dashboard')
@login_required
@it_team_required
def it_dashboard():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Get asset counts
    cur.execute('SELECT COUNT(*) as total FROM assets')
    total_assets = cur.fetchone()['total']
    
    cur.execute('SELECT COUNT(*) as assigned FROM assets WHERE status = "assigned"')
    assigned_assets = cur.fetchone()['assigned']
    
    cur.execute('SELECT COUNT(*) as available FROM assets WHERE status = "available"')
    available_assets = cur.fetchone()['available']
    
    cur.execute('SELECT COUNT(*) as maintenance FROM assets WHERE status = "maintenance"')
    maintenance_assets = cur.fetchone()['maintenance']
    
    # Get recent assignments - using the correct table name
    cur.execute('''
        SELECT a.*, assets.serial_number, assets.brand, assets.asset_type, users.name as user_name
        FROM assignments a
        JOIN assets ON a.asset_id = assets.id
        JOIN users ON a.user_id = users.id
        WHERE a.returned_at IS NULL
        ORDER BY a.assigned_at DESC
        LIMIT 5
    ''')
    recent_assignments = cur.fetchall()
    
    # Get pending requests - using the correct table name
    cur.execute('''
        SELECT ur.*, users.name as user_name
        FROM user_requests ur
        JOIN users ON ur.user_id = users.id
        WHERE ur.status = 'pending'
        ORDER BY ur.created_at DESC
        LIMIT 5
    ''')
    pending_requests = cur.fetchall()
    
    cur.close()
    conn.close()
    
    return render_template('it_dashboard.html', 
                         total_assets=total_assets,
                         assigned_assets=assigned_assets,
                         available_assets=available_assets,
                         maintenance_assets=maintenance_assets,
                         recent_assignments=recent_assignments,
                         pending_requests=pending_requests)

@app.route('/super-admin-dashboard')
@login_required
@super_admin_required
def super_admin_dashboard():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Get PR counts
    cur.execute('SELECT COUNT(*) as pending FROM purchase_requests WHERE status = "pending"')
    pr_pending = cur.fetchone()['pending']
    
    cur.execute('SELECT COUNT(*) as approved FROM purchase_requests WHERE status = "approved"')
    pr_approved = cur.fetchone()['approved']
    
    cur.execute('SELECT COUNT(*) as total FROM purchase_requests')
    pr_total = cur.fetchone()['total']
    
    # Get recent PRs
    cur.execute('''
        SELECT pr.*, u.name as requester_name
        FROM purchase_requests pr
        JOIN users u ON pr.requested_by = u.id
        ORDER BY pr.created_at DESC
        LIMIT 5
    ''')
    recent_prs = cur.fetchall()
    
    cur.close()
    conn.close()
    
    return render_template('super_admin_dashboard.html', 
                         pr_pending=pr_pending,
                         pr_approved=pr_approved,
                         pr_total=pr_total,
                         recent_prs=recent_prs)

@app.route('/test-debug')
def test_debug():
    return "DEBUG: Test route working!"

@app.route('/assets', methods=['GET', 'POST'])
@login_required
@it_team_required
def assets():
    form = AssetForm()
    conn = get_db_connection()
    cur = conn.cursor()
    if form.validate_on_submit():
        asset_number = form.asset_number.data
        serial_number = form.serial_number.data
        brand = form.brand.data
        model = ''  # Model field removed
        type_value = request.form.get('type')  # Get type from form
        processor = request.form.get('processor')  # Get processor from form
        mouse_type = request.form.get('mouse_type')  # Get mouse type from form
        keyboard_type = request.form.get('keyboard_type')  # Get keyboard type from form
        printer_type = request.form.get('printer_type')  # Get printer type from form
        system_type = request.form.get('system_type')  # Get system type from form
        keyboard_connection = request.form.get('keyboard_connection')  # Get keyboard connection from form
        printer_function = request.form.get('printer_function')  # Get printer function from form
        printer_connectivity = request.form.get('printer_connectivity')  # Get printer connectivity from form
        invoice_number = form.invoice_number.data
        ram = request.form.get('ram')
        rom = request.form.get('rom')
        purchase_date = form.purchase_date.data
        warranty_expiry = form.warranty_expiry.data
        asset_type = request.form.get('asset_type')  # Get from button selection
        asset_id = request.form.get('asset_id')
        
        # Set the asset_type in the form for validation
        form.asset_type.data = asset_type
        
        # Validate required fields
        if not asset_type:
            flash('Please select an asset type.', 'danger')
            return redirect(url_for('assets'))
            
        # Check for duplicate asset number (for add or edit)
        if asset_id:
            cur.execute('SELECT id FROM assets WHERE asset_number = %s AND id != %s', (asset_number, asset_id))
        else:
            cur.execute('SELECT id FROM assets WHERE asset_number = %s', (asset_number,))
        existing_asset = cur.fetchone()
        if existing_asset:
            flash('Asset number already exists. Please use a unique asset number.', 'danger')
            return redirect(url_for('assets'))
            
        # Check for duplicate serial number (for add or edit)
        if asset_id:
            cur.execute('SELECT id FROM assets WHERE serial_number = %s AND id != %s', (serial_number, asset_id))
        else:
            cur.execute('SELECT id FROM assets WHERE serial_number = %s', (serial_number,))
        existing_serial = cur.fetchone()
        if existing_serial:
            flash('Serial number already exists. Please use a unique serial number.', 'danger')
            return redirect(url_for('assets'))
        try:
            if asset_id:
                cur.execute('UPDATE assets SET asset_number=%s, serial_number=%s, brand=%s, model=%s, type=%s, processor=%s, mouse_type=%s, keyboard_type=%s, keyboard_connection=%s, printer_type=%s, printer_function=%s, printer_connectivity=%s, system_type=%s, invoice_number=%s, ram=%s, rom=%s, purchase_date=%s, warranty_expiry=%s, asset_type=%s WHERE id=%s',
                            (asset_number, serial_number, brand, model, type_value, processor, mouse_type, keyboard_type, keyboard_connection, printer_type, printer_function, printer_connectivity, system_type, invoice_number, ram, rom, purchase_date, warranty_expiry, asset_type, asset_id))
                flash('Asset updated successfully.', 'success')
            else:
                cur.execute('INSERT INTO assets (asset_number, serial_number, brand, model, type, processor, mouse_type, keyboard_type, keyboard_connection, printer_type, printer_function, printer_connectivity, system_type, invoice_number, ram, rom, purchase_date, warranty_expiry, asset_type) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
                            (asset_number, serial_number, brand, model, type_value, processor, mouse_type, keyboard_type, keyboard_connection, printer_type, printer_function, printer_connectivity, system_type, invoice_number, ram, rom, purchase_date, warranty_expiry, asset_type))
                flash('Asset added successfully.', 'success')
            conn.commit()
        except Exception as e:
            flash('Error saving asset: {}'.format(str(e)), 'danger')
            conn.rollback()
        return redirect(url_for('assets'))
    cur.execute('SELECT * FROM assets ORDER BY id DESC')
    assets_list = cur.fetchall()
    
    # Convert to list of dictionaries for template access
    columns = [desc[0] for desc in cur.description]
    
    # Create a new list with proper dictionary conversion
    converted_assets = []
    for row in assets_list:
        # Check if row is already a dictionary
        if isinstance(row, dict):
            converted_assets.append(row)
        else:
            # Convert tuple to dictionary
            asset_dict = {}
            for i, column in enumerate(columns):
                asset_dict[column] = row[i]
            converted_assets.append(asset_dict)
    
    assets_list = converted_assets
    
    cur.close()
    conn.close()
    return render_template('assets.html', assets=assets_list, form=form)

@app.route('/assets/edit/<int:asset_id>', methods=['GET', 'POST'])
@login_required
def edit_asset(asset_id):
    if current_user.role != 'admin':
        return abort(403)
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT * FROM assets WHERE id = %s', (asset_id,))
    asset = cur.fetchone()
    # Convert to dictionary for template access
    if asset:
        columns = [desc[0] for desc in cur.description]
        asset = dict(zip(columns, asset))
    form = AssetForm(data=asset)
    if form.validate_on_submit():
        asset_type = request.form.get('asset_type')  # Get from button selection
        if not asset_type:
            flash('Please select an asset type.', 'danger')
            return redirect(url_for('edit_asset', asset_id=asset_id))
        
        # Set the asset_type in the form for validation
        form.asset_type.data = asset_type
            
        type_value = request.form.get('type')  # Get type from form
        processor = request.form.get('processor')  # Get processor from form
        mouse_type = request.form.get('mouse_type')  # Get mouse type from form
        keyboard_type = request.form.get('keyboard_type')  # Get keyboard type from form
        printer_type = request.form.get('printer_type')  # Get printer type from form
        system_type = request.form.get('system_type')  # Get system type from form
        keyboard_connection = request.form.get('keyboard_connection')  # Get keyboard connection from form
        printer_function = request.form.get('printer_function')  # Get printer function from form
        printer_connectivity = request.form.get('printer_connectivity')  # Get printer connectivity from form
        cur.execute('UPDATE assets SET asset_number=%s, serial_number=%s, brand=%s, model=%s, type=%s, processor=%s, mouse_type=%s, keyboard_type=%s, keyboard_connection=%s, printer_type=%s, printer_function=%s, printer_connectivity=%s, system_type=%s, invoice_number=%s, ram=%s, rom=%s, purchase_date=%s, warranty_expiry=%s, asset_type=%s WHERE id=%s',
                    (form.asset_number.data, form.serial_number.data, form.brand.data, '', type_value, processor, mouse_type, keyboard_type, keyboard_connection, printer_type, printer_function, printer_connectivity, system_type, form.invoice_number.data, request.form.get('ram'), request.form.get('rom'), form.purchase_date.data, form.warranty_expiry.data, asset_type, asset_id))
        conn.commit()
        log_audit(current_user.id, 'Asset Edited', f'Asset {form.serial_number.data} updated')
        flash('Asset updated!', 'success')
        cur.close()
        conn.close()
        return redirect(url_for('assets'))
    cur.close()
    conn.close()
    return render_template('edit_asset.html', form=form, asset=asset)

@app.route('/assets/delete/<int:asset_id>', methods=['POST'])
@login_required
def delete_asset(asset_id):
    if current_user.role != 'admin':
        return abort(403)
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('DELETE FROM assets WHERE id = %s', (asset_id,))
    conn.commit()
    cur.close()
    conn.close()
    log_audit(current_user.id, 'Asset Deleted', f'Asset {asset_id} deleted')
    flash('Asset deleted!', 'success')
    return redirect(url_for('assets'))

@app.route('/assign', methods=['GET', 'POST'])
@login_required
@it_team_required
def assign():
    conn = get_db_connection()
    cur = conn.cursor()
    # Get available assets with detailed information
    cur.execute("SELECT id, serial_number, brand, asset_type, ram, rom, processor, mouse_type, keyboard_type, keyboard_connection, printer_type, printer_function, printer_connectivity, system_type FROM assets WHERE status = 'available'")
    assets = cur.fetchall()
    
    # Create detailed asset choices based on asset type
    asset_choices = []
    for a in assets:
        if a['asset_type'] and a['asset_type'].lower() == 'laptop':
            # For laptops, include processor, RAM, ROM
            details = []
            if a['processor']:
                details.append(f"CPU: {a['processor']}")
            if a['ram']:
                details.append(f"RAM: {a['ram']}")
            if a['rom']:
                details.append(f"Storage: {a['rom']}")
            
            detail_str = f" - {', '.join(details)}" if details else ""
            asset_choices.append((a['id'], f"{a['serial_number']} ({a['asset_type']}, {a['brand']}){detail_str}"))
        
        elif a['asset_type'] and a['asset_type'].lower() == 'mouse':
            # For mice, include mouse type
            detail_str = f" - Type: {a['mouse_type']}" if a['mouse_type'] else ""
            asset_choices.append((a['id'], f"{a['serial_number']} ({a['asset_type']}, {a['brand']}){detail_str}"))
        
        elif a['asset_type'] and a['asset_type'].lower() == 'keyboard':
            # For keyboards, include keyboard type and connection
            details = []
            if a['keyboard_type']:
                details.append(f"Type: {a['keyboard_type']}")
            if a['keyboard_connection']:
                details.append(f"Connection: {a['keyboard_connection']}")
            
            detail_str = f" - {', '.join(details)}" if details else ""
            asset_choices.append((a['id'], f"{a['serial_number']} ({a['asset_type']}, {a['brand']}){detail_str}"))
        
        elif a['asset_type'] and a['asset_type'].lower() == 'printer':
            # For printers, include printer type, function, and connectivity
            details = []
            if a['printer_type']:
                details.append(f"Type: {a['printer_type']}")
            if a['printer_function']:
                details.append(f"Function: {a['printer_function']}")
            if a['printer_connectivity']:
                details.append(f"Connectivity: {a['printer_connectivity']}")
            
            detail_str = f" - {', '.join(details)}" if details else ""
            asset_choices.append((a['id'], f"{a['serial_number']} ({a['asset_type']}, {a['brand']}){detail_str}"))
        
        elif a['asset_type'] and a['asset_type'].lower() in ['system', 'systems']:
            # For systems, include system type
            detail_str = f" - Type: {a['system_type']}" if a['system_type'] else ""
            asset_choices.append((a['id'], f"{a['serial_number']} ({a['asset_type']}, {a['brand']}){detail_str}"))
        
        else:
            # For other asset types, use basic format
            asset_choices.append((a['id'], f"{a['serial_number']} ({a['asset_type']}, {a['brand']})"))
    # Get users
    cur.execute("SELECT id, name, email FROM users WHERE role = 'user'")
    users = cur.fetchall()
    user_choices = [(u['id'], f"{u['name']} ({u['email']})") for u in users]
    form = AssignAssetForm()
    form.asset_id.choices = asset_choices
    form.user_id.choices = user_choices
    if form.validate_on_submit():
        # Build lookup dictionaries for assets and users
        asset_dict = {a['id']: a for a in assets}
        user_dict = {u['id']: u for u in users}
        selected_asset = asset_dict.get(form.asset_id.data)
        selected_user = user_dict.get(form.user_id.data)
        if selected_asset and selected_user:
            # Assign asset to user
            cur.execute('INSERT INTO assignments (asset_id, user_id, unit, assigned_at) VALUES (%s, %s, %s, NOW())', (form.asset_id.data, form.user_id.data, form.unit.data))
            cur.execute('UPDATE assets SET status = %s WHERE id = %s', ('assigned', form.asset_id.data))
            conn.commit()
            
            # Send email notification to the user
            try:
                # Get complete asset details for email
                cur.execute('''SELECT a.*, DATE_FORMAT(a.purchase_date, '%Y-%m-%d') as purchase_date_str, 
                                     DATE_FORMAT(a.warranty_expiry, '%Y-%m-%d') as warranty_expiry_str
                              FROM assets a WHERE a.id = %s''', (form.asset_id.data,))
                asset_details = cur.fetchone()
                
                if asset_details:
                    # Prepare asset data for email
                    asset_data = {
                        'asset_type': asset_details['asset_type'],
                        'serial_number': asset_details['serial_number'],
                        'brand': asset_details['brand'],
                        'asset_number': asset_details.get('asset_number'),
                        'invoice_number': asset_details.get('invoice_number'),
                        'purchase_date': asset_details.get('purchase_date_str'),
                        'warranty_expiry': asset_details.get('warranty_expiry_str'),
                        'processor': asset_details.get('processor'),
                        'ram': asset_details.get('ram'),
                        'rom': asset_details.get('rom'),
                        'mouse_type': asset_details.get('mouse_type'),
                        'keyboard_type': asset_details.get('keyboard_type'),
                        'keyboard_connection': asset_details.get('keyboard_connection'),
                        'printer_type': asset_details.get('printer_type'),
                        'printer_function': asset_details.get('printer_function'),
                        'printer_connectivity': asset_details.get('printer_connectivity'),
                        'system_type': asset_details.get('system_type')
                    }
                    
                    # Send email
                    email_sent = send_asset_assignment_email(
                        user_email=selected_user['email'],
                        user_name=selected_user['name'],
                        asset_data=asset_data,
                        assigned_by=current_user.email,
                        unit=form.unit.data
                    )
                    
                    if email_sent:
                        flash('Asset assigned successfully! Email notification sent to user.', 'success')
                    else:
                        flash('Asset assigned successfully! Email notification failed.', 'warning')
                else:
                    flash('Asset assigned successfully!', 'success')
                    
            except Exception as e:
                print(f"Error sending email notification: {e}")
                flash('Asset assigned successfully! Email notification failed.', 'warning')
            
            log_audit(current_user.id, 'Asset Assigned', f"Asset {selected_asset['serial_number']} assigned to {selected_user['name']} in unit {form.unit.data}")
            return redirect(url_for('assign'))
        else:
            flash('Invalid asset or user selected.', 'danger')
    # Get asset types from database
    cur.execute("SELECT name FROM asset_types ORDER BY name")
    asset_types = cur.fetchall()
    
    # Assignment history
    cur.execute('''SELECT a.id, assets.serial_number, assets.brand, assets.asset_type, users.name as user_name, users.email as user_email, a.unit, a.assigned_at, a.returned_at FROM assignments a
                   JOIN assets ON a.asset_id = assets.id
                   JOIN users ON a.user_id = users.id
                   WHERE a.returned_at IS NULL
                   ORDER BY a.assigned_at DESC''')
    assignments = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('assign.html', form=form, assignments=assignments, asset_types=asset_types)

@app.route('/assign/return/<int:assignment_id>', methods=['POST'])
@login_required
def return_asset(assignment_id):
    if current_user.role != 'admin':
        return abort(403)
    conn = get_db_connection()
    cur = conn.cursor()
    # Get assignment
    cur.execute('SELECT asset_id FROM assignments WHERE id = %s', (assignment_id,))
    assignment = cur.fetchone()
    if assignment:
        cur.execute('UPDATE assignments SET returned_at = NOW() WHERE id = %s', (assignment_id,))
        cur.execute("UPDATE assets SET status = 'available' WHERE id = %s", (assignment['asset_id'],))
        conn.commit()
        flash('Asset marked as returned.', 'info')
    cur.close()
    conn.close()
    return redirect(url_for('assign'))

@app.route('/requests', methods=['GET', 'POST'])
@login_required
@it_team_required
def requests_page():
    conn = get_db_connection()
    cur = conn.cursor()
    # Handle actions
    if request.method == 'POST':
        action = request.form.get('action')
        req_id = request.form.get('request_id')
        if action in ['approve', 'reject', 'complete'] and req_id:
            if action == 'approve':
                cur.execute("UPDATE requests SET status = 'approved' WHERE id = %s", (req_id,))
            elif action == 'reject':
                cur.execute("UPDATE requests SET status = 'rejected' WHERE id = %s", (req_id,))
            elif action == 'complete':
                cur.execute("UPDATE requests SET status = 'completed' WHERE id = %s", (req_id,))
            conn.commit()
            flash(f'Request {action}d.', 'success')
        return redirect(url_for('requests_page'))
    # List all requests
    cur.execute('''SELECT r.id, u.name, u.email, r.asset_type, r.request_type, r.status, r.details, r.created_at
                   FROM requests r JOIN users u ON r.user_id = u.id ORDER BY r.created_at DESC''')
    requests_list = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('requests.html', requests=requests_list)

@app.route('/maintenance', methods=['GET', 'POST'])
@login_required
@it_team_required
def maintenance():
    conn = get_db_connection()
    cur = conn.cursor()
    # Handle status update
    if request.method == 'POST':
        maint_id = request.form.get('maint_id')
        new_status = request.form.get('status')
        if maint_id and new_status in ['open', 'in_progress', 'resolved']:
            if new_status == 'resolved':
                cur.execute('UPDATE maintenance SET status=%s, resolved_at=NOW() WHERE id=%s', (new_status, maint_id))
            else:
                cur.execute('UPDATE maintenance SET status=%s WHERE id=%s', (new_status, maint_id))
            conn.commit()
            flash('Maintenance status updated.', 'success')
        return redirect(url_for('maintenance'))
    # List all maintenance records
    cur.execute('''SELECT m.id, a.serial_number, a.brand, m.issue_details, m.status, m.reported_at, m.resolved_at
                   FROM maintenance m JOIN assets a ON m.asset_id = a.id ORDER BY m.reported_at DESC''')
    maintenance_list = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('maintenance.html', maintenance=maintenance_list)

@app.route('/users', methods=['GET', 'POST'])
@login_required
@admin_required
def users():
    form = UserForm()
    conn = get_db_connection()
    cur = conn.cursor()
    if form.validate_on_submit():
        name = form.name.data
        email = form.email.data
        password = form.password.data
        role = form.role.data
        cur.execute('INSERT INTO users (name, email, password, role) VALUES (%s, %s, %s, %s)', (name, email, password, role))
        conn.commit()
        log_audit(current_user.id, 'User Added', f'User {email} added')
        flash('User added!', 'success')
        return redirect(url_for('users'))
    cur.execute('SELECT id, name, email, role FROM users ORDER BY id DESC')
    users_list = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('users.html', form=form, users=users_list)

@app.route('/users/edit/<int:user_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(user_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT * FROM users WHERE id = %s', (user_id,))
    user = cur.fetchone()
    form = UserForm(data=user)
    if form.validate_on_submit():
        name = form.name.data
        email = form.email.data
        password = form.password.data
        role = form.role.data
        cur.execute('UPDATE users SET name=%s, email=%s, password=%s, role=%s WHERE id=%s', (name, email, password, role, user_id))
        conn.commit()
        log_audit(current_user.id, 'User Edited', f'User {email} updated')
        flash('User updated!', 'success')
        cur.close()
        conn.close()
        return redirect(url_for('users'))
    cur.close()
    conn.close()
    return render_template('edit_user.html', form=form, user=user)

@app.route('/users/delete/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Check if user exists
        cur.execute('SELECT name, email FROM users WHERE id = %s', (user_id,))
        user = cur.fetchone()
        if not user:
            flash('User not found!', 'error')
            return redirect(url_for('users'))
        
        # Check if user is trying to delete themselves
        if user_id == current_user.id:
            flash('You cannot delete your own account!', 'error')
            return redirect(url_for('users'))
        
        # Check for foreign key dependencies
        dependencies = []
        
        # Check approvals table
        cur.execute('SELECT COUNT(*) as count FROM approvals WHERE approver_id = %s', (user_id,))
        approval_count = cur.fetchone()['count']
        if approval_count > 0:
            dependencies.append(f'Approvals ({approval_count} records)')
        
        # Check assignments table
        cur.execute('SELECT COUNT(*) as count FROM assignments WHERE user_id = %s', (user_id,))
        assignment_count = cur.fetchone()['count']
        if assignment_count > 0:
            dependencies.append(f'Asset Assignments ({assignment_count} records)')
        
        # Check requests table
        cur.execute('SELECT COUNT(*) as count FROM requests WHERE user_id = %s', (user_id,))
        request_count = cur.fetchone()['count']
        if request_count > 0:
            dependencies.append(f'Asset Requests ({request_count} records)')
        
        # Check purchase_requests table
        cur.execute('SELECT COUNT(*) as count FROM purchase_requests WHERE requested_by = %s', (user_id,))
        pr_count = cur.fetchone()['count']
        if pr_count > 0:
            dependencies.append(f'Purchase Requests ({pr_count} records)')
        
        # Check item_approvals table
        cur.execute('SELECT COUNT(*) as count FROM item_approvals WHERE approver_id = %s', (user_id,))
        item_approval_count = cur.fetchone()['count']
        if item_approval_count > 0:
            dependencies.append(f'Item Approvals ({item_approval_count} records)')
        
        # Check audit_logs table
        cur.execute('SELECT COUNT(*) as count FROM audit_logs WHERE user_id = %s', (user_id,))
        audit_count = cur.fetchone()['count']
        if audit_count > 0:
            dependencies.append(f'Audit Logs ({audit_count} records)')
        
        # Check notifications table
        cur.execute('SELECT COUNT(*) as count FROM notifications WHERE user_id = %s', (user_id,))
        notification_count = cur.fetchone()['count']
        if notification_count > 0:
            dependencies.append(f'Notifications ({notification_count} records)')
        
        # If there are dependencies, show error
        if dependencies:
            dependency_list = ', '.join(dependencies)
            flash(f'Cannot delete user. User is referenced in: {dependency_list}. Please remove these references first.', 'error')
            return redirect(url_for('users'))
        
        # If no dependencies, proceed with deletion
        cur.execute('DELETE FROM users WHERE id = %s', (user_id,))
        conn.commit()
        
        log_audit(current_user.id, 'User Deleted', f'User {user["name"]} ({user["email"]}) deleted')
        flash('User deleted successfully!', 'success')
        
    except Exception as e:
        conn.rollback()
        flash(f'Error deleting user: {str(e)}', 'error')
        log_audit(current_user.id, 'User Delete Error', f'Failed to delete user {user_id}: {str(e)}')
    
    finally:
        cur.close()
        conn.close()
    
    return redirect(url_for('users'))

@app.route('/reports')
@login_required
def reports():
    if current_user.role != 'admin':
        return abort(403)
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT serial_number, brand, model, status, purchase_date, warranty_expiry FROM assets ORDER BY id DESC')
    assets = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('reports.html', assets=assets)

@app.route('/audit')
@login_required
def audit():
    if current_user.role != 'admin':
        return abort(403)
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''SELECT a.id, u.name, u.email, a.action, a.details, a.created_at \
                   FROM audit_logs a JOIN users u ON a.user_id = u.id \
                   ORDER BY a.created_at DESC''')
    logs = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('audit.html', logs=logs)

@app.route('/notifications')
@login_required
def notifications():
    if current_user.role != 'admin':
        return abort(403)
    conn = get_db_connection()
    cur = conn.cursor()
    notifications = []
    # Warranty expiry in next 30 days
    cur.execute("SELECT serial_number, brand, model, warranty_expiry FROM assets WHERE warranty_expiry IS NOT NULL AND warranty_expiry <= DATE_ADD(CURDATE(), INTERVAL 30 DAY) AND warranty_expiry >= CURDATE()")
    expiring = cur.fetchall()
    for asset in expiring:
        notifications.append(f"Warranty expiring soon: {asset['serial_number']} {asset['brand']} {asset['model']} (Expiry: {asset['warranty_expiry']})")
    # Low stock (if quantity column exists)
    try:
        cur.execute("SELECT serial_number, brand, model, quantity FROM assets WHERE quantity IS NOT NULL AND quantity <= 2")
        low_stock = cur.fetchall()
        for asset in low_stock:
            notifications.append(f"Low stock: {asset['serial_number']} {asset['brand']} {asset['model']} (Qty: {asset['quantity']})")
    except Exception:
        pass  # If no quantity column, skip
    # Pending approvals (requests table)
    cur.execute("SELECT COUNT(*) as pending FROM requests WHERE status = 'pending'")
    pending = cur.fetchone()
    if pending and pending['pending'] > 0:
        notifications.append(f"Pending approvals: {pending['pending']} requests awaiting action.")
    cur.close()
    conn.close()
    return render_template('notifications.html', notifications=notifications)

@app.route('/user-requests', methods=['GET', 'POST'])
@login_required
def user_requests():
    if current_user.role != 'user':
        return abort(403)
    form = UserRequestForm()
    conn = get_db_connection()
    cur = conn.cursor()
    if form.validate_on_submit():
        asset_type = form.asset_type.data
        request_type = form.request_type.data
        details = form.details.data
        cur.execute('INSERT INTO requests (user_id, asset_type, request_type, details) VALUES (%s, %s, %s, %s)',
                    (current_user.id, asset_type, request_type, details))
        conn.commit()
        flash('Request submitted!', 'success')
    cur.execute('SELECT * FROM requests WHERE user_id = %s ORDER BY created_at DESC', (current_user.id,))
    requests_list = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('user_requests.html', form=form, requests=requests_list)

@app.route('/my-assets')
@login_required
def my_assets():
    if current_user.role != 'user':
        return abort(403)
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Get user's assigned assets details
    cur.execute('''SELECT a.id, a.asset_number, a.serial_number, a.brand, a.asset_type, a.ram, a.rom, 
                          a.processor, a.mouse_type, a.keyboard_type, a.keyboard_connection,
                          a.printer_type, a.printer_function, a.printer_connectivity, a.system_type,
                          a.invoice_number, a.purchase_date, a.warranty_expiry, a.status,
                          ass.unit, ass.assigned_at
                   FROM assignments ass
                   JOIN assets a ON ass.asset_id = a.id
                   WHERE ass.user_id = %s AND ass.returned_at IS NULL
                   ORDER BY ass.assigned_at DESC''', (current_user.id,))
    user_assets = cur.fetchall()
    
    # Get asset counts for overview
    cur.execute('''SELECT a.asset_type, COUNT(*) as count 
                   FROM assignments ass
                   JOIN assets a ON ass.asset_id = a.id
                   WHERE ass.user_id = %s AND ass.returned_at IS NULL
                   GROUP BY a.asset_type''', (current_user.id,))
    db_counts = {row['asset_type']: row['count'] for row in cur.fetchall()}
    asset_counts = []
    for t in get_asset_types(names_only=True):
        asset_counts.append({'asset_type': t, 'count': db_counts.get(t, 0)})
    
    cur.close()
    conn.close()
    
    return render_template('my_assets.html', user_assets=user_assets, asset_counts=asset_counts)

@app.route('/reports/export')
@login_required
def export_report():
    if current_user.role != 'admin':
        return abort(403)
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT serial_number, brand, model, status, purchase_date, warranty_expiry FROM assets ORDER BY id DESC')
    assets = cur.fetchall()
    cur.close()
    conn.close()
    def generate():
        data = [
            ['Serial Number', 'Brand', 'Model', 'Status', 'Purchase Date', 'Warranty Expiry']
        ]
        for asset in assets:
            data.append([
                asset['serial_number'], asset['brand'], asset['model'], asset['status'], asset['purchase_date'], asset['warranty_expiry']
            ])
        for row in data:
            yield ','.join(str(x) for x in row) + '\n'
    return Response(generate(), mimetype='text/csv', headers={'Content-Disposition': 'attachment;filename=asset_report.csv'})

@app.route('/reports/requests/export')
@login_required
def export_requests_report():
    if current_user.role != 'admin':
        return abort(403)
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''SELECT r.id, u.name as user_name, a.serial_number, r.asset_type, r.request_type, r.status, r.created_at
                   FROM requests r
                   JOIN users u ON r.user_id = u.id
                   LEFT JOIN assets a ON r.asset_type = a.asset_type
                   ORDER BY r.created_at DESC''')
    requests_list = cur.fetchall()
    cur.close()
    conn.close()
    def generate():
        data = [['Request ID', 'User', 'Asset Type', 'Request Type', 'Status', 'Created At']]
        for req in requests_list:
            data.append([
                req['id'], req['user_name'], req['asset_type'], req['request_type'], req['status'], req['created_at']
            ])
        for row in data:
            yield ','.join(str(x) for x in row) + '\n'
    return Response(generate(), mimetype='text/csv', headers={'Content-Disposition': 'attachment;filename=requests_report.csv'})

@app.route('/reports/maintenance/export')
@login_required
def export_maintenance_report():
    if current_user.role != 'admin':
        return abort(403)
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''SELECT m.id, a.serial_number, m.issue, m.status, m.created_at, m.completed_at
                   FROM maintenance m
                   JOIN assets a ON m.asset_id = a.id
                   ORDER BY m.created_at DESC''')
    maintenance_list = cur.fetchall()
    cur.close()
    conn.close()
    def generate():
        data = [['Maintenance ID', 'Asset', 'Issue', 'Status', 'Created At', 'Completed At']]
        for m in maintenance_list:
            data.append([
                m['id'], m['serial_number'], m['issue'], m['status'], m['created_at'], m['completed_at']
            ])
        for row in data:
            yield ','.join(str(x) for x in row) + '\n'
    return Response(generate(), mimetype='text/csv', headers={'Content-Disposition': 'attachment;filename=maintenance_report.csv'})

@app.route('/api/asset_counts')
def api_asset_counts():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT asset_type, COUNT(*) as total
        FROM assets
        GROUP BY asset_type
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    # Ensure all types are present, even if zero
    types = get_asset_types()
    counts = {t.lower(): 0 for t in types}
    for row in rows:
        t = row['asset_type']
        if t in types:
            counts[t.lower()] = row['total']
        else:
            counts['others'] += row['total']
    return jsonify(counts)

@app.route('/api/assigned_laptops')
def api_assigned_laptops():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(*) as assigned_laptops
        FROM assignments a
        JOIN assets s ON a.asset_id = s.id
        WHERE s.asset_type = 'Laptop'
    """)
    row = cur.fetchone()
    cur.close()
    conn.close()
    return jsonify({'assigned_laptops': row['assigned_laptops'] if row else 0})

@app.route('/api/assigned_assets')
def api_assigned_assets():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT s.asset_type, COUNT(*) as assigned_count
        FROM assignments a
        JOIN assets s ON a.asset_id = s.id
        WHERE s.asset_type IN ('Laptop', 'Mouse', 'System', 'Keyboard')
        GROUP BY s.asset_type
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    
    # Initialize with zeros
    assigned = {'laptop': 0, 'mouse': 0, 'system': 0, 'keyboard': 0}
    for row in rows:
        asset_type = row['asset_type'].lower()
        if asset_type in assigned:
            assigned[asset_type] = row['assigned_count']
    
    return jsonify(assigned)

@app.route('/api/available_assets')
def api_available_assets():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT asset_type, COUNT(*) as available_count
        FROM assets
        WHERE status = 'available' AND asset_type IN ('Laptop', 'Mouse', 'System', 'Keyboard')
        GROUP BY asset_type
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    
    # Initialize with zeros
    available = {'laptop': 0, 'mouse': 0, 'system': 0, 'keyboard': 0}
    for row in rows:
        asset_type = row['asset_type'].lower()
        if asset_type in available:
            available[asset_type] = row['available_count']
    
    return jsonify(available)

@app.route('/api/total_assets')
def api_total_assets():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT asset_type, COUNT(*) as total_count
        FROM assets
        WHERE asset_type IN ('Laptop', 'Mouse', 'Keyboard', 'System')
        GROUP BY asset_type
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    result = {t: 0 for t in ['Laptop', 'Mouse', 'Keyboard', 'System']}
    for row in rows:
        result[row['asset_type']] = row['total_count']
    return jsonify(result)

@app.route('/api/approvers', methods=['GET'])
def get_approvers():
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Get all users who can be approvers (admin, manager roles)
        cur.execute('''
            SELECT id, email, name 
            FROM users 
            WHERE role IN ('admin', 'manager') 
            ORDER BY name, email
        ''')
        approvers = cur.fetchall()
        
        cur.close()
        conn.close()
        
        return jsonify({'success': True, 'approvers': approvers})
        
    except Exception as e:
        cur.close()
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 400

# Utility function to log audit events
def log_audit(user_id, action, details):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('INSERT INTO audit_logs (user_id, action, details, created_at) VALUES (%s, %s, %s, %s)',
                (user_id, action, details, datetime.datetime.now()))
    conn.commit()
    cur.close()
    conn.close()

def send_asset_assignment_email(user_email, user_name, asset_data, assigned_by, unit):
    """
    Send professional email notification when an asset is assigned to a user
    """
    try:
        # Email configuration
        gmail_user = 'harishrajangam48@gmail.com'
        gmail_password = 'wqjd gjjc ulbw pbxc'
        
        # Create message
        msg = MIMEMultipart('alternative')
        msg['From'] = gmail_user
        msg['To'] = user_email
        msg['Subject'] = f"Asset Assignment Notification - {asset_data['asset_type']} ({asset_data['serial_number']})"
        
        # Get current date
        current_date = datetime.datetime.now().strftime("%B %d, %Y")
        
        # Build asset specifications based on asset type
        specifications = []
        if asset_data['asset_type'].lower() == 'laptop':
            if asset_data.get('processor'):
                specifications.append(f"Processor: {asset_data['processor']}")
            if asset_data.get('ram'):
                specifications.append(f"RAM: {asset_data['ram']}")
            if asset_data.get('rom'):
                specifications.append(f"Storage: {asset_data['rom']}")
        elif asset_data['asset_type'].lower() == 'mouse':
            if asset_data.get('mouse_type'):
                specifications.append(f"Type: {asset_data['mouse_type']}")
        elif asset_data['asset_type'].lower() == 'keyboard':
            if asset_data.get('keyboard_type'):
                specifications.append(f"Type: {asset_data['keyboard_type']}")
            if asset_data.get('keyboard_connection'):
                specifications.append(f"Connection: {asset_data['keyboard_connection']}")
        elif asset_data['asset_type'].lower() == 'printer':
            if asset_data.get('printer_type'):
                specifications.append(f"Type: {asset_data['printer_type']}")
            if asset_data.get('printer_function'):
                specifications.append(f"Function: {asset_data['printer_function']}")
            if asset_data.get('printer_connectivity'):
                specifications.append(f"Connectivity: {asset_data['printer_connectivity']}")
        elif asset_data['asset_type'].lower() in ['system', 'systems']:
            if asset_data.get('system_type'):
                specifications.append(f"Type: {asset_data['system_type']}")
        
        specs_html = '<br>'.join(specifications) if specifications else 'Standard specifications'
        
        # HTML Email Content
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Asset Assignment Notification</title>
            <style>
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                    background-color: #f8f9fa;
                }}
                .email-container {{
                    background-color: #ffffff;
                    border-radius: 10px;
                    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
                    overflow: hidden;
                }}
                .header {{
                    background: linear-gradient(135deg, #1c4b79 0%, #0a3d71 100%);
                    color: white;
                    padding: 30px;
                    text-align: center;
                }}
                .header h1 {{
                    margin: 0;
                    font-size: 24px;
                    font-weight: 600;
                }}
                .content {{
                    padding: 30px;
                }}
                .greeting {{
                    font-size: 18px;
                    margin-bottom: 20px;
                    color: #2c3e50;
                }}
                .asset-details {{
                    background-color: #f8f9fa;
                    border-radius: 8px;
                    padding: 20px;
                    margin: 20px 0;
                    border-left: 4px solid #1c4b79;
                }}
                .asset-details h3 {{
                    margin-top: 0;
                    color: #1c4b79;
                    font-size: 18px;
                }}
                .detail-row {{
                    display: flex;
                    justify-content: space-between;
                    margin-bottom: 10px;
                    padding: 8px 0;
                    border-bottom: 1px solid #e9ecef;
                }}
                .detail-row:last-child {{
                    border-bottom: none;
                }}
                .detail-label {{
                    font-weight: 600;
                    color: #495057;
                    min-width: 120px;
                }}
                .detail-value {{
                    color: #6c757d;
                    text-align: right;
                }}
                .specifications {{
                    background-color: #e3f2fd;
                    border-radius: 6px;
                    padding: 15px;
                    margin: 15px 0;
                }}
                .footer {{
                    background-color: #f8f9fa;
                    padding: 20px;
                    text-align: center;
                    color: #6c757d;
                    font-size: 14px;
                }}
                .contact-info {{
                    margin-top: 15px;
                    padding-top: 15px;
                    border-top: 1px solid #dee2e6;
                }}
                .badge {{
                    display: inline-block;
                    padding: 4px 8px;
                    border-radius: 4px;
                    font-size: 12px;
                    font-weight: 600;
                    text-transform: uppercase;
                }}
                .badge-primary {{
                    background-color: #1c4b79;
                    color: white;
                }}
                .badge-success {{
                    background-color: #28a745;
                    color: white;
                }}
            </style>
        </head>
        <body>
            <div class="email-container">
                <div class="header">
                    <h1>🎯 Asset Assignment Notification</h1>
                    <p style="margin: 10px 0 0 0; opacity: 0.9;">VT Asset Management System</p>
                </div>
                
                <div class="content">
                    <div class="greeting">
                        Dear <strong>{user_name}</strong>,
                    </div>
                    
                    <p>We are pleased to inform you that an asset has been assigned to you. Please find the details below:</p>
                    
                    <div class="asset-details">
                        <h3>📦 Asset Information</h3>
                        
                        <div class="detail-row">
                            <span class="detail-label">Asset Type:</span>
                            <span class="detail-value">
                                <span class="badge badge-primary">{asset_data['asset_type']}</span>
                            </span>
                        </div>
                        
                        <div class="detail-row">
                            <span class="detail-label">Serial Number:</span>
                            <span class="detail-value"><strong>{asset_data['serial_number']}</strong></span>
                        </div>
                        
                        <div class="detail-row">
                            <span class="detail-label">Brand:</span>
                            <span class="detail-value">{asset_data['brand']}</span>
                        </div>
                        
                        <div class="detail-row">
                            <span class="detail-label">Asset Number:</span>
                            <span class="detail-value">{asset_data.get('asset_number', 'N/A')}</span>
                        </div>
                        
                        <div class="detail-row">
                            <span class="detail-label">Invoice Number:</span>
                            <span class="detail-value">{asset_data.get('invoice_number', 'N/A')}</span>
                        </div>
                        
                        <div class="detail-row">
                            <span class="detail-label">Purchase Date:</span>
                            <span class="detail-value">{asset_data.get('purchase_date', 'N/A')}</span>
                        </div>
                        
                        <div class="detail-row">
                            <span class="detail-label">Warranty Expiry:</span>
                            <span class="detail-value">
                                {f"<span class='badge badge-success'>{asset_data['warranty_expiry']}</span>" if asset_data.get('warranty_expiry') else 'N/A'}
                            </span>
                        </div>
                        
                        <div class="detail-row">
                            <span class="detail-label">Unit/Department:</span>
                            <span class="detail-value"><strong>{unit}</strong></span>
                        </div>
                        
                        <div class="detail-row">
                            <span class="detail-label">Assigned By:</span>
                            <span class="detail-value">{assigned_by}</span>
                        </div>
                        
                        <div class="detail-row">
                            <span class="detail-label">Assignment Date:</span>
                            <span class="detail-value">{current_date}</span>
                        </div>
                    </div>
                    
                    <div class="specifications">
                        <h4 style="margin-top: 0; color: #1c4b79;">🔧 Technical Specifications</h4>
                        {specs_html}
                    </div>
                    
                    <div style="background-color: #fff3cd; border: 1px solid #ffeaa7; border-radius: 6px; padding: 15px; margin: 20px 0;">
                        <h4 style="margin-top: 0; color: #856404;">📋 Important Notes</h4>
                        <ul style="margin: 0; padding-left: 20px;">
                            <li>Please take good care of the assigned asset</li>
                            <li>Report any issues or malfunctions immediately to the IT team</li>
                            <li>Do not transfer this asset to other users without authorization</li>
                            <li>Return the asset when requested or upon leaving the organization</li>
                        </ul>
                    </div>
                    
                    <p style="text-align: center; margin-top: 30px;">
                        <strong>Thank you for your cooperation!</strong>
                    </p>
                </div>
                
                <div class="footer">
                    <p>This is an automated notification from the VT Asset Management System.</p>
                    <div class="contact-info">
                        <p><strong>For support:</strong> Contact your IT team or system administrator</p>
                        <p><strong>System:</strong> VT Asset Management System</p>
                        <p><strong>Date:</strong> {current_date}</p>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Plain text version
        text_content = f"""
Asset Assignment Notification

Dear {user_name},

We are pleased to inform you that an asset has been assigned to you.

ASSET DETAILS:
- Asset Type: {asset_data['asset_type']}
- Serial Number: {asset_data['serial_number']}
- Brand: {asset_data['brand']}
- Asset Number: {asset_data.get('asset_number', 'N/A')}
- Invoice Number: {asset_data.get('invoice_number', 'N/A')}
- Purchase Date: {asset_data.get('purchase_date', 'N/A')}
- Warranty Expiry: {asset_data.get('warranty_expiry', 'N/A')}
- Unit/Department: {unit}
- Assigned By: {assigned_by}
- Assignment Date: {current_date}

TECHNICAL SPECIFICATIONS:
{specs_html}

IMPORTANT NOTES:
- Please take good care of the assigned asset
- Report any issues or malfunctions immediately to the IT team
- Do not transfer this asset to other users without authorization
- Return the asset when requested or upon leaving the organization

Thank you for your cooperation!

---
This is an automated notification from the VT Asset Management System.
For support: Contact your IT team or system administrator
Date: {current_date}
        """
        
        # Attach both HTML and text versions
        msg.attach(MIMEText(text_content, 'plain'))
        msg.attach(MIMEText(html_content, 'html'))
        
        # Send email
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(gmail_user, gmail_password)
        server.sendmail(gmail_user, user_email, msg.as_string())
        server.quit()
        
        print(f"✅ Asset assignment email sent successfully to {user_email}")
        return True
        
    except Exception as e:
        print(f"❌ Error sending asset assignment email: {e}")
        return False

@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    flash('Session expired or invalid CSRF token. Please try again.', 'danger')
    return redirect(request.referrer or url_for('assets'))

# Utility function to get a pymysql connection
def get_db_connection():
    return pymysql.connect(
        host=app.config['MYSQL_HOST'],
        user=app.config['MYSQL_USER'],
        password=app.config['MYSQL_PASSWORD'],
        db=app.config['MYSQL_DB'],
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False
    )

# Register procurement blueprint
app.register_blueprint(procurement_bp)

# Procurement Routes
@app.route('/procurement/dashboard')
def procurement_dashboard():
    return render_template('procurement_dashboard.html')

@app.route('/procurement/create-pr')
@login_required
def create_pr():
    pr_id = request.args.get('pr_id')
    approval_status = None
    if pr_id:
        import requests
        try:
            resp = requests.get(f'http://localhost:5000/api/purchase_requests/{pr_id}')
            if resp.ok:
                data = resp.json()
                approval_status = data.get('approval_status')
        except Exception as e:
            approval_status = None
    return render_template('create_pr.html', approval_status=approval_status, user_role=current_user.role)

@app.route('/procurement/approvals')
def pr_approvals():
    return render_template('pr_approvals.html')

@app.route('/procurement/upload-po')
def upload_po():
    return render_template('upload_po.html')

@app.route('/procurement/delivery-entry')
def delivery_entry():
    return render_template('delivery_entry.html')

@app.route('/procurement/payment-tracking', methods=['GET', 'POST'])
def payment_tracking():
    if request.method == 'POST':
        # Handle payment tracking form submission
        pass
    return render_template('payment_tracking.html')

# Super Admin PR Routes
@app.route('/super-admin/pr-pending')
@login_required
@super_admin_required
def super_admin_pr_pending():
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute('''
        SELECT pr.*, u.name as requester_name, d.name as department_name
        FROM purchase_requests pr
        JOIN users u ON pr.requested_by = u.id
        LEFT JOIN departments d ON u.department_id = d.id
        WHERE pr.status = 'pending'
        ORDER BY pr.created_at DESC
    ''')
    pending_prs = cur.fetchall()
    
    cur.close()
    conn.close()
    
    return render_template('super_admin_pr_pending.html', pending_prs=pending_prs)

@app.route('/super-admin/pr-approved')
@login_required
@super_admin_required
def super_admin_pr_approved():
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute('''
        SELECT pr.*, u.name as requester_name, d.name as department_name
        FROM purchase_requests pr
        JOIN users u ON pr.requested_by = u.id
        LEFT JOIN departments d ON u.department_id = d.id
        WHERE pr.status = 'approved'
        ORDER BY pr.created_at DESC
    ''')
    approved_prs = cur.fetchall()
    
    cur.close()
    conn.close()
    
    return render_template('super_admin_pr_approved.html', approved_prs=approved_prs)

@app.route('/super-admin/pr-requests')
@login_required
@super_admin_required
def super_admin_pr_requests():
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute('''
        SELECT pr.*, u.name as requester_name, d.name as department_name
        FROM purchase_requests pr
        JOIN users u ON pr.requested_by = u.id
        LEFT JOIN departments d ON u.department_id = d.id
        ORDER BY pr.created_at DESC
    ''')
    all_prs = cur.fetchall()
    
    cur.close()
    conn.close()
    
    return render_template('super_admin_pr_requests.html', all_prs=all_prs)

@app.route('/super-admin/pr-details/<int:pr_id>')
@login_required
@super_admin_required
def super_admin_pr_details(pr_id):
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Get PR details with approver information
    cur.execute('''
        SELECT pr.*, u.name as requester_name, d.name as department_name, pr.for_field, 
               au.email as approver_email, au.name as approver_name
        FROM purchase_requests pr
        JOIN users u ON pr.requested_by = u.id
        LEFT JOIN departments d ON u.department_id = d.id
        LEFT JOIN approvals a ON pr.id = a.pr_id
        LEFT JOIN users au ON a.approver_id = au.id
        WHERE pr.id = %s
        ORDER BY a.approval_date DESC
        LIMIT 1
    ''', (pr_id,))
    pr = cur.fetchone()
    
    if not pr:
        flash('Purchase Request not found.', 'danger')
        return redirect(url_for('super_admin_dashboard'))
    
    # Get PR items with all required fields and recalculate quantity_to_procure with new logic
    cur.execute('''
        SELECT 
            pri.*,
            at.name as asset_type_name,
            pri.brand,
            pri.vendor,
            pri.configuration,
            pri.quantity_required,
            pri.stock_available,
            CASE 
                WHEN pri.quantity_required <= pri.stock_available THEN pri.quantity_required
                ELSE pri.quantity_required - pri.stock_available
            END as quantity_to_procure,
            pri.unit_cost,
            (pri.unit_cost * CASE 
                WHEN pri.quantity_required <= pri.stock_available THEN pri.quantity_required
                ELSE pri.quantity_required - pri.stock_available
            END) as total_amount,
            pri.favor,
            pri.favor_reason
        FROM pr_items pri
        LEFT JOIN asset_types at ON pri.asset_type_id = at.id
        WHERE pri.pr_id = %s
        ORDER BY pri.id
    ''', (pr_id,))
    pr_items = cur.fetchall()
    
    cur.close()
    conn.close()
    
    return render_template('super_admin_pr_details.html', pr=pr, pr_items=pr_items)

@app.route('/super-admin/approve-pr/<int:pr_id>', methods=['GET', 'POST'])
@login_required
@super_admin_required
def super_admin_approve_pr(pr_id):
    if request.method == 'POST':
        conn = get_db_connection()
        cur = conn.cursor()
        
        try:
            # Update PR status to approved
            cur.execute('UPDATE purchase_requests SET status = "approved" WHERE id = %s', (pr_id,))
            
            # Create approval record
            cur.execute('''
                INSERT INTO approvals (pr_id, approver_id, status, approval_date, notes)
                VALUES (%s, %s, %s, NOW(), %s)
            ''', (pr_id, current_user.id, 'approved', request.form.get('notes', '')))
            
            conn.commit()
            flash('Purchase Request approved successfully!', 'success')
            
        except Exception as e:
            conn.rollback()
            flash(f'Error approving PR: {str(e)}', 'danger')
        finally:
            cur.close()
            conn.close()
        
        return redirect(url_for('super_admin_pr_details', pr_id=pr_id))
    
    # GET request - show approval form
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute('''
        SELECT pr.*, u.name as requester_name, d.name as department_name
        FROM purchase_requests pr
        JOIN users u ON pr.requested_by = u.id
        LEFT JOIN departments d ON u.department_id = d.id
        WHERE pr.id = %s
    ''', (pr_id,))
    pr = cur.fetchone()
    
    if not pr:
        flash('Purchase Request not found.', 'danger')
        return redirect(url_for('super_admin_dashboard'))
    
    cur.execute('''
        SELECT pri.*, at.name as asset_type_name
        FROM pr_items pri
        LEFT JOIN asset_types at ON pri.asset_type_id = at.id
        WHERE pri.pr_id = %s
    ''', (pr_id,))
    pr_items = cur.fetchall()
    
    cur.close()
    conn.close()
    
    return render_template('super_admin_approve_pr.html', pr=pr, pr_items=pr_items)

# Additional API endpoints for procurement
@app.route('/api/departments', methods=['GET'])
def get_departments():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT * FROM departments ORDER BY name')
    departments = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify({'success': True, 'departments': departments})

@app.route('/api/users', methods=['GET'])
def get_users():
    role = request.args.get('role')
    conn = get_db_connection()
    cur = conn.cursor()
    
    if role:
        cur.execute('SELECT * FROM users WHERE role = %s ORDER BY name', (role,))
    else:
        cur.execute('SELECT * FROM users ORDER BY name')
    
    users = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify({'success': True, 'users': users})

@app.route('/api/users', methods=['POST'])
@csrf.exempt
def create_user():
    data = request.get_json()
    name = data.get('name', '').strip()
    email = data.get('email', '').strip()
    role = data.get('role', 'user')
    password = data.get('password', 'default123')
    
    if not name or not email:
        return jsonify({'success': False, 'error': 'Name and email are required'}), 400
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Check if email already exists
        cur.execute('SELECT id FROM users WHERE email = %s', (email,))
        if cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'success': False, 'error': 'Email already exists'}), 400
        
        # Create new user
        cur.execute('INSERT INTO users (name, email, password, role) VALUES (%s, %s, %s, %s)',
                    (name, email, password, role))
        conn.commit()
        
        # Get the created user
        user_id = cur.lastrowid
        cur.execute('SELECT id, name, email, role FROM users WHERE id = %s', (user_id,))
        user = cur.fetchone()
        
        # If this is a manager/approver, create an entry in approvals table
        if role == 'manager':
            # Create a default approval entry (this will be linked to PRs when they are created)
            cur.execute('INSERT INTO approvals (approver_id, status) VALUES (%s, %s)',
                        (user_id, 'pending'))
            conn.commit()
        
        cur.close()
        conn.close()
        
        return jsonify({'success': True, 'user': user})
        
    except Exception as e:
        cur.close()
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/add_approver', methods=['POST'])
@csrf.exempt
def add_approver():
    data = request.get_json()
    email = data.get('email', '').strip()
    
    if not email:
        return jsonify({'success': False, 'error': 'Email is required'}), 400
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Check if user with this email already exists
        cur.execute('SELECT id FROM users WHERE email = %s', (email,))
        existing_user = cur.fetchone()
        
        if existing_user:
            # User exists, use their ID
            approver_id = existing_user['id']
        else:
            # Create new user with the email
            cur.execute('INSERT INTO users (email, name, password, role) VALUES (%s, %s, %s, %s)',
                        (email, email.split('@')[0], 'default123', 'manager'))
            conn.commit()
            approver_id = cur.lastrowid
        
        # Add entry to approvals table
        cur.execute('INSERT INTO approvals (approver_id, status) VALUES (%s, %s)',
                    (approver_id, 'pending'))
        conn.commit()
        
        cur.close()
        conn.close()
        
        return jsonify({
            'success': True, 
            'approver_id': approver_id,
            'email': email
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/procurement/dashboard-stats')
def procurement_dashboard_stats():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Count pending PRs
    cur.execute("SELECT COUNT(*) as count FROM purchase_requests WHERE status = 'pending'")
    pending_prs = cur.fetchone()['count']
    
    # Count approved PRs
    cur.execute("SELECT COUNT(*) as count FROM purchase_requests WHERE status = 'approved'")
    approved_prs = cur.fetchone()['count']
    
    # Count pending deliveries
    cur.execute("SELECT COUNT(*) as count FROM purchase_orders WHERE status = 'created'")
    pending_deliveries = cur.fetchone()['count']
    
    # Count overdue payments
    cur.execute("SELECT COUNT(*) as count FROM invoices WHERE status = 'overdue'")
    overdue_payments = cur.fetchone()['count']
    
    cur.close()
    conn.close()
    
    return jsonify({
        'success': True,
        'stats': {
            'pending_prs': pending_prs,
            'approved_prs': approved_prs,
            'pending_deliveries': pending_deliveries,
            'overdue_payments': overdue_payments
        }
    })

@app.route('/api/procurement/upcoming-deliveries')
def upcoming_deliveries():
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute('''
        SELECT po.*, pr.pr_number
        FROM purchase_orders po
        JOIN purchase_requests pr ON po.pr_id = pr.id
        WHERE po.status = 'created' AND po.expected_delivery_date >= CURDATE()
        ORDER BY po.expected_delivery_date
        LIMIT 5
    ''')
    
    deliveries = cur.fetchall()
    cur.close()
    conn.close()
    
    return jsonify({'success': True, 'deliveries': deliveries})

# --- Brands API ---
@app.route('/api/brands')
def get_brands():
    print('API /api/brands called')
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT id, name FROM brands ORDER BY name')
    brands = [{'id': row['id'], 'name': row['name']} for row in cur.fetchall()]
    cur.close()
    conn.close()
    print('Brands returned:', [b['name'] for b in brands])
    return jsonify({'brands': [b['name'] for b in brands]})

@app.route('/api/brands', methods=['POST'])
@csrf.exempt
def add_brand():
    data = request.get_json()
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'success': False, 'error': 'Name required'}), 400
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Check if brand already exists in brands table
        cur.execute('SELECT id FROM brands WHERE name = %s', (name,))
        existing_brand = cur.fetchone()
        
        if existing_brand:
            # Brand already exists, return success but don't insert
            cur.close()
            conn.close()
            return jsonify({'success': True, 'name': name, 'message': 'Brand already exists'})
        
        # Insert new brand into brands table
        cur.execute('INSERT INTO brands (name, created_at) VALUES (%s, NOW())', (name,))
        conn.commit()
        
        cur.close()
        conn.close()
        return jsonify({'success': True, 'name': name, 'message': 'Brand added successfully'})
        
    except Exception as e:
        cur.close()
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/brands/<name>', methods=['DELETE'])
@csrf.exempt
def delete_brand(name):
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Check if brand exists
        cur.execute('SELECT id FROM brands WHERE name = %s', (name,))
        brand = cur.fetchone()
        
        if not brand:
            cur.close()
            conn.close()
            return jsonify({'success': False, 'error': 'Brand not found'}), 404
        
        # Check if brand is used in assets table
        cur.execute('SELECT COUNT(*) as count FROM assets WHERE brand = %s', (name,))
        usage_count = cur.fetchone()['count']
        
        if usage_count > 0:
            cur.close()
            conn.close()
            return jsonify({'success': False, 'error': f'Cannot delete brand. It is used by {usage_count} asset(s).'}), 400
        
        # Delete brand from brands table
        cur.execute('DELETE FROM brands WHERE name = %s', (name,))
        conn.commit()
        
        cur.close()
        conn.close()
        return jsonify({'success': True, 'message': 'Brand deleted successfully'})
        
    except Exception as e:
        cur.close()
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/vendors')
def get_vendors():
    print('API /api/vendors called')
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT id, name FROM vendors ORDER BY name')
    vendors = [{'id': row['id'], 'name': row['name']} for row in cur.fetchall()]
    cur.close()
    conn.close()
    print('Vendors returned:', [v['name'] for v in vendors])
    return jsonify({'vendors': [v['name'] for v in vendors]})

@app.route('/api/vendors', methods=['POST'])
@csrf.exempt
def add_vendor():
    data = request.get_json()
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'success': False, 'error': 'Name required'}), 400
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Check if vendor already exists in vendors table
        cur.execute('SELECT id FROM vendors WHERE name = %s', (name,))
        existing_vendor = cur.fetchone()
        
        if existing_vendor:
            # Vendor already exists, return success but don't insert
            cur.close()
            conn.close()
            return jsonify({'success': True, 'name': name, 'message': 'Vendor already exists'})
        
        # Insert new vendor into vendors table
        cur.execute('INSERT INTO vendors (name, created_at) VALUES (%s, NOW())', (name,))
        conn.commit()
        
        cur.close()
        conn.close()
        return jsonify({'success': True, 'name': name, 'message': 'Vendor added successfully'})
        
    except Exception as e:
        cur.close()
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/vendors/<name>', methods=['DELETE'])
@csrf.exempt
def delete_vendor(name):
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Check if vendor exists
        cur.execute('SELECT id FROM vendors WHERE name = %s', (name,))
        vendor = cur.fetchone()
        
        if not vendor:
            cur.close()
            conn.close()
            return jsonify({'success': False, 'error': 'Vendor not found'}), 404
        
        # Check if vendor is used in purchase requests
        cur.execute('SELECT COUNT(*) as count FROM pr_items WHERE vendor = %s', (name,))
        usage_count = cur.fetchone()['count']
        
        if usage_count > 0:
            cur.close()
            conn.close()
            return jsonify({'success': False, 'error': f'Cannot delete vendor. It is used by {usage_count} purchase request item(s).'}), 400
        
        # Delete vendor from vendors table
        cur.execute('DELETE FROM vendors WHERE name = %s', (name,))
        conn.commit()
        
        cur.close()
        conn.close()
        return jsonify({'success': True, 'message': 'Vendor deleted successfully'})
        
    except Exception as e:
        cur.close()
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/debug_assets_brands')
def debug_assets_brands():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT * FROM assets')
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify({'assets': rows})

@app.route('/api/assets/by_type/<asset_type>', methods=['GET'])
@login_required
def get_assets_by_type(asset_type):
    """Get available assets filtered by asset type"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Get available assets with detailed information, filtered by asset type
        if asset_type.lower() == 'all':
            cur.execute("""
                SELECT id, serial_number, brand, asset_type, ram, rom, processor, 
                       mouse_type, keyboard_type, keyboard_connection, printer_type, 
                       printer_function, printer_connectivity, system_type 
                FROM assets 
                WHERE status = 'available'
            """)
        else:
            cur.execute("""
                SELECT id, serial_number, brand, asset_type, ram, rom, processor, 
                       mouse_type, keyboard_type, keyboard_connection, printer_type, 
                       printer_function, printer_connectivity, system_type 
                FROM assets 
                WHERE status = 'available' AND LOWER(asset_type) = %s
            """, (asset_type.lower(),))
        
        assets = cur.fetchall()
        
        # Create detailed asset choices based on asset type
        asset_choices = []
        for a in assets:
            if a['asset_type'] and a['asset_type'].lower() == 'laptop':
                # For laptops, include processor, RAM, ROM
                details = []
                if a['processor']:
                    details.append(f"CPU: {a['processor']}")
                if a['ram']:
                    details.append(f"RAM: {a['ram']}")
                if a['rom']:
                    details.append(f"Storage: {a['rom']}")
                
                detail_str = f" - {', '.join(details)}" if details else ""
                asset_choices.append({
                    'id': a['id'],
                    'text': f"{a['serial_number']} ({a['asset_type']}, {a['brand']}){detail_str}"
                })
            
            elif a['asset_type'] and a['asset_type'].lower() == 'mouse':
                # For mice, include mouse type
                detail_str = f" - Type: {a['mouse_type']}" if a['mouse_type'] else ""
                asset_choices.append({
                    'id': a['id'],
                    'text': f"{a['serial_number']} ({a['asset_type']}, {a['brand']}){detail_str}"
                })
            
            elif a['asset_type'] and a['asset_type'].lower() == 'keyboard':
                # For keyboards, include keyboard type and connection
                details = []
                if a['keyboard_type']:
                    details.append(f"Type: {a['keyboard_type']}")
                if a['keyboard_connection']:
                    details.append(f"Connection: {a['keyboard_connection']}")
                
                detail_str = f" - {', '.join(details)}" if details else ""
                asset_choices.append({
                    'id': a['id'],
                    'text': f"{a['serial_number']} ({a['asset_type']}, {a['brand']}){detail_str}"
                })
            
            elif a['asset_type'] and a['asset_type'].lower() == 'printer':
                # For printers, include printer type, function, and connectivity
                details = []
                if a['printer_type']:
                    details.append(f"Type: {a['printer_type']}")
                if a['printer_function']:
                    details.append(f"Function: {a['printer_function']}")
                if a['printer_connectivity']:
                    details.append(f"Connectivity: {a['printer_connectivity']}")
                
                detail_str = f" - {', '.join(details)}" if details else ""
                asset_choices.append({
                    'id': a['id'],
                    'text': f"{a['serial_number']} ({a['asset_type']}, {a['brand']}){detail_str}"
                })
            
            elif a['asset_type'] and a['asset_type'].lower() in ['system', 'systems']:
                # For systems, include system type
                detail_str = f" - Type: {a['system_type']}" if a['system_type'] else ""
                asset_choices.append({
                    'id': a['id'],
                    'text': f"{a['serial_number']} ({a['asset_type']}, {a['brand']}){detail_str}"
                })
            
            else:
                # For other asset types, use basic format
                asset_choices.append({
                    'id': a['id'],
                    'text': f"{a['serial_number']} ({a['asset_type']}, {a['brand']})"
                })
        
        cur.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'assets': asset_choices
        })
        
    except Exception as e:
        print(f"ERROR in get_assets_by_type: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/debug_asset_types')
def debug_asset_types():
    """Debug endpoint to check asset types in database"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Get all asset types
        cur.execute("SELECT DISTINCT asset_type, COUNT(*) as count FROM assets WHERE status = 'available' GROUP BY asset_type")
        asset_types = cur.fetchall()
        
        # Get sample assets
        cur.execute("SELECT id, serial_number, brand, asset_type FROM assets WHERE status = 'available' LIMIT 10")
        sample_assets = cur.fetchall()
        
        cur.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'asset_types': asset_types,
            'sample_assets': sample_assets
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)