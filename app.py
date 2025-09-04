
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
import json
import sys
from flask import Flask, Blueprint
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Import procurement blueprint
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from Assert.procurement_api import procurement_bp
from DB_Connection import get_db_connection, CSV_Proj_Params

Curr_Proj_Name = 'Assert_IT'


app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'

# Create IT blueprint with URL prefix
from flask import Blueprint
#it_bp = Blueprint('it', __name__, url_prefix='/it')

it_bp = Blueprint('it', __name__)



# Root route redirect - Commented out to fix dispatcher conflict
# @app.route('/')
# def root():
#     return redirect(url_for('it.login'))

# Legacy route redirects to prevent 404 errors - Commented out to fix dispatcher conflict
# @app.route('/login')
# def legacy_login():
#     proj_params = CSV_Proj_Params(Curr_Proj_Name)
#     app.config['MYSQL_HOST'] = proj_params.get('MYSQL_HOST')
#     app.config['MYSQL_PORT'] = int(proj_params.get('MYSQL_PORT'))
#     app.config['MYSQL_USER'] = proj_params.get('MYSQL_USER')
#     app.config['MYSQL_PASSWORD'] = proj_params.get('MYSQL_PASSWORD')
#     app.config['MYSQL_DB'] = proj_params.get('MYSQL_DB')
#     app.config['MYSQL_CURSORCLASS'] = proj_params.get('MYSQL_CURSORCLASS')

#     return redirect(url_for('it.login'))

# @app.route('/logout')
# def legacy_logout():
#     return redirect(url_for('it.logout'))

login_manager = LoginManager(app)
login_manager.login_view = 'it.login'
Bootstrap(app)
csrf = CSRFProtect(app)

# Exempt API endpoints from CSRF protection
csrf.exempt(procurement_bp)

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role not in ['admin', 'super_admin']:
            # Check if this is an API call (request wants JSON)
            if request.path.startswith('/IT/api/') or request.headers.get('Accept') == 'application/json':
                return jsonify({'success': False, 'error': 'Authentication required'}), 401
            else:
                flash('Admin or Super Admin access required.', 'danger')
                return redirect(url_for('it.login'))
        return f(*args, **kwargs)
    return decorated_function



def it_team_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role not in ['admin', 'it_team', 'super_admin']:
            flash('IT Team, Admin, or Super Admin access required.', 'danger')
            return redirect(url_for('it.login'))
        return f(*args, **kwargs)
    return decorated_function

def super_admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'super_admin':
            flash('Super Admin access required.', 'danger')
            return redirect(url_for('it.login'))
        return f(*args, **kwargs)
    return decorated_function

class User(UserMixin):
    def __init__(self, id, email, role):
        self.id = id
        self.email = email
        self.role = role
    
    @property
    def name(self):
        """Extract name from email address"""
        if self.email:
            # Get the part before @ and replace dots with spaces, then title case
            name_part = self.email.split('@')[0]
            return name_part.replace('.', ' ').replace('_', ' ').title()
        return ''

    @staticmethod
    def get(user_id):
        conn = get_db_connection(Curr_Proj_Name)
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
    conn = get_db_connection(Curr_Proj_Name)
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

@it_bp.route('/api/asset_types', methods=['GET'])
def api_get_asset_types():
    types = get_asset_types()
    return jsonify({'types': types})

@it_bp.route('/api/asset_types', methods=['POST'])
@csrf.exempt
def api_add_asset_type():
    data = request.get_json()
    name = data.get('name', '').strip()
    if not name:
        resp = jsonify({'success': False, 'error': 'Name required'})
        return resp, 400
    conn = get_db_connection(Curr_Proj_Name)
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

@it_bp.route('/api/asset_types/<name>', methods=['DELETE'])
@csrf.exempt
def api_delete_asset_type(name):
    name = name.strip()
    if not name:
        return jsonify({'success': False, 'error': 'Name required'}), 400
    conn = get_db_connection(Curr_Proj_Name)
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

@it_bp.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data
        password = form.password.data
        conn = get_db_connection(Curr_Proj_Name)
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
                return redirect(request.args.get('next') or url_for('it.it_dashboard'))
            else:
                return redirect(request.args.get('next') or url_for('it.dashboard'))
        else:
            flash('Invalid email or password.', 'danger')
    return render_template('login.html', form=form)

@it_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out.', 'info')
    return redirect(url_for('it.login'))

@it_bp.route('/')
@login_required
def dashboard():
    # Redirect IT Team users to their dashboard
    if current_user.role == 'it_team':
        return redirect(url_for('it.it_dashboard'))
    # Redirect Super Admin users to their dashboard
    elif current_user.role == 'super_admin':
        return redirect(url_for('it.super_admin_dashboard'))
    # Redirect Admin users to BOD Report
    elif current_user.role == 'admin':
        return redirect(url_for('it.bod_report'))
    # Regular user dashboard
    else:
        conn = get_db_connection(Curr_Proj_Name)
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

@it_bp.route('/it-dashboard')
@login_required
@it_team_required
def it_dashboard():
    conn = get_db_connection(Curr_Proj_Name)
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

@it_bp.route('/super-admin-dashboard')
@login_required
@super_admin_required
def super_admin_dashboard():
    conn = get_db_connection(Curr_Proj_Name)
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

@it_bp.route('/test-debug')
def test_debug():
    return "DEBUG: Test route working!"

@it_bp.route('/assets', methods=['GET', 'POST'])
@login_required
@it_team_required
def assets():
    form = AssetForm()
    conn = get_db_connection(Curr_Proj_Name)
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
                cur.execute('INSERT INTO assets (asset_number, serial_number, brand, model, type=%s, processor=%s, mouse_type=%s, keyboard_type=%s, keyboard_connection=%s, printer_type=%s, printer_function=%s, printer_connectivity=%s, system_type=%s, invoice_number=%s, ram=%s, rom=%s, purchase_date=%s, warranty_expiry=%s, asset_type) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
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

@it_bp.route('/assets/edit/<int:asset_id>', methods=['GET', 'POST'])
@login_required
def edit_asset(asset_id):
    if current_user.role != 'admin':
        return abort(403)
    conn = get_db_connection(Curr_Proj_Name)
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

@it_bp.route('/assets/delete/<int:asset_id>', methods=['POST'])
@login_required
def delete_asset(asset_id):
    if current_user.role != 'admin':
        return abort(403)
    conn = get_db_connection(Curr_Proj_Name)
    cur = conn.cursor()
    cur.execute('DELETE FROM assets WHERE id = %s', (asset_id,))
    conn.commit()
    cur.close()
    conn.close()
    log_audit(current_user.id, 'Asset Deleted', f'Asset {asset_id} deleted')
    flash('Asset deleted!', 'success')
    return redirect(url_for('assets'))

@it_bp.route('/assign', methods=['GET', 'POST'])
@login_required
@it_team_required
def assign():
    conn = get_db_connection(Curr_Proj_Name)
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
            return redirect(url_for('it.assign'))
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

@it_bp.route('/assign/return/<int:assignment_id>', methods=['POST'])
@login_required
def return_asset(assignment_id):
    if current_user.role != 'admin':
        return abort(403)
    conn = get_db_connection(Curr_Proj_Name)
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

@it_bp.route('/requests', methods=['GET', 'POST'])
@login_required
@it_team_required
def requests_page():
    conn = get_db_connection(Curr_Proj_Name)
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
        return redirect(url_for('it.requests_page'))
    # List all requests
    cur.execute('''SELECT r.id, u.name, u.email, r.asset_type, r.request_type, r.status, r.details, r.created_at
                   FROM requests r JOIN users u ON r.user_id = u.id ORDER BY r.created_at DESC''')
    requests_list = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('requests.html', requests=requests_list)

@it_bp.route('/maintenance', methods=['GET', 'POST'])
@login_required
@it_team_required
def maintenance():
    conn = get_db_connection(Curr_Proj_Name)
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
        return redirect(url_for('it.maintenance'))
    # List all maintenance records
    cur.execute('''SELECT m.id, a.serial_number, a.brand, m.issue_details, m.status, m.reported_at, m.resolved_at
                   FROM maintenance m JOIN assets a ON m.asset_id = a.id ORDER BY m.reported_at DESC''')
    maintenance_list = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('maintenance.html', maintenance=maintenance_list)

@it_bp.route('/users', methods=['GET', 'POST'])
@login_required
@super_admin_required
def users():
    form = UserForm()
    conn = get_db_connection(Curr_Proj_Name)
    cur = conn.cursor()
    if form.validate_on_submit():
        name = form.name.data
        email = form.email.data
        password = form.password.data
        role = form.role.data
        
        # Check if email already exists
        cur.execute('SELECT id FROM users WHERE email = %s', (email,))
        existing_user = cur.fetchone()
        if existing_user:
            flash('This email is already in use, please use another email!', 'error')
            cur.close()
            conn.close()
            return render_template('users.html', form=form, users=[])
        
        cur.execute('INSERT INTO users (name, email, password, role) VALUES (%s, %s, %s, %s)', (name, email, password, role))
        user_id = cur.lastrowid
        
        # Handle menu permissions if role is admin
        if role == 'admin':
            menu_items = ['dashboard', 'procurement', 'asset_master', 'assign_asset', 'requests', 'user_management', 'bod_report', 'daily_infrastructure']
            for menu_item in menu_items:
                is_allowed = request.form.get(f'menu_{menu_item}') == 'on'
                cur.execute('''
                    INSERT INTO admin_menu_permissions (user_id, menu_item, is_allowed)
                    VALUES (%s, %s, %s)
                ''', (user_id, menu_item, is_allowed))
        
        conn.commit()
        log_audit(current_user.id, 'User Added', f'User {email} added')
        flash('User added!', 'success')
        cur.close()
        conn.close()
        return redirect(url_for('it.users'))
    
    cur.execute('SELECT id, name, email, role FROM users ORDER BY id DESC')
    users_list = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('users.html', form=form, users=users_list)

@it_bp.route('/users/edit/<int:user_id>', methods=['GET', 'POST'])
@login_required
@super_admin_required
def edit_user(user_id):
    conn = get_db_connection(Curr_Proj_Name)
    cur = conn.cursor()
    cur.execute('SELECT * FROM users WHERE id = %s', (user_id,))
    user = cur.fetchone()
    form = UserForm(data=user)
    
    # Get current menu permissions if user is admin
    menu_permissions = {}
    if user and user['role'] == 'admin':
        cur.execute('''
            SELECT menu_item, is_allowed 
            FROM admin_menu_permissions 
            WHERE user_id = %s
        ''', (user_id,))
        permissions = cur.fetchall()
        menu_permissions = {perm['menu_item']: perm['is_allowed'] for perm in permissions}
    
    if form.validate_on_submit():
        name = form.name.data
        email = form.email.data
        password = form.password.data
        role = form.role.data
        
        # Check if email already exists for another user
        cur.execute('SELECT id FROM users WHERE email = %s AND id != %s', (email, user_id))
        existing_user = cur.fetchone()
        if existing_user:
            flash('This email is already in use by another user, please use another email!', 'error')
            cur.close()
            conn.close()
            return render_template('edit_user.html', form=form, user=user, menu_permissions=menu_permissions)
        
        cur.execute('UPDATE users SET name=%s, email=%s, password=%s, role=%s WHERE id=%s', (name, email, password, role, user_id))
        
        # Handle menu permissions if role is admin
        if role == 'admin':
            menu_items = ['dashboard', 'procurement', 'create_pr', 'approve_prs', 'upload_po', 'record_delivery', 'asset_master', 'assign_asset', 'requests', 'user_management', 'bod_report', 'daily_infrastructure']
            for menu_item in menu_items:
                is_allowed = request.form.get(f'menu_{menu_item}') == 'on'
                cur.execute('''
                    INSERT INTO admin_menu_permissions (user_id, menu_item, is_allowed)
                    VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE is_allowed = VALUES(is_allowed)
                ''', (user_id, menu_item, is_allowed))
        else:
            # Remove all menu permissions if role is not admin
            cur.execute('DELETE FROM admin_menu_permissions WHERE user_id = %s', (user_id,))
        
        conn.commit()
        log_audit(current_user.id, 'User Edited', f'User {email} updated')
        flash('User updated!', 'success')
        cur.close()
        conn.close()
        return redirect(url_for('it.users'))
    
    cur.close()
    conn.close()
    return render_template('edit_user.html', form=form, user=user, menu_permissions=menu_permissions)

@it_bp.route('/users/delete/<int:user_id>', methods=['POST'])
@login_required
@super_admin_required
def delete_user(user_id):
    conn = get_db_connection(Curr_Proj_Name)
    cur = conn.cursor()
    
    try:
        # Check if user exists
        cur.execute('SELECT name, email FROM users WHERE id = %s', (user_id,))
        user = cur.fetchone()
        if not user:
            flash('User not found!', 'error')
            return redirect(url_for('it.users'))
        
        # Check if user is trying to delete themselves
        if user_id == current_user.id:
            flash('You cannot delete your own account!', 'error')
            return redirect(url_for('it.users'))
        
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
        
        # If there are dependencies, handle them with cascade deletion for all roles
        if dependencies:
            # Get user role for logging purposes
            cur.execute('SELECT role FROM users WHERE id = %s', (user_id,))
            user_role = cur.fetchone()['role']
            
            # For all user roles, allow cascade deletion by removing references first
            flash(f'{user_role.title()} user has references in other tables. Proceeding with cascade deletion...', 'warning')
            
            # Delete from approvals table
            cur.execute('DELETE FROM approvals WHERE approver_id = %s', (user_id,))
            
            # Delete from assignments table
            cur.execute('DELETE FROM assignments WHERE user_id = %s', (user_id,))
            
            # Delete from requests table
            cur.execute('DELETE FROM requests WHERE user_id = %s', (user_id,))
            
            # Delete from purchase_requests table
            cur.execute('DELETE FROM purchase_requests WHERE requested_by = %s', (user_id,))
            
            # Delete from item_approvals table
            cur.execute('DELETE FROM item_approvals WHERE approver_id = %s', (user_id,))
            
            # Delete from audit_logs table
            cur.execute('DELETE FROM audit_logs WHERE user_id = %s', (user_id,))
            
            # Delete from notifications table
            cur.execute('DELETE FROM notifications WHERE user_id = %s', (user_id,))
            
            flash('All user references have been removed. Proceeding with user deletion...', 'info')
        
        # Proceed with user deletion
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
    
    return redirect(url_for('it.users'))

@it_bp.route('/reports')
@login_required
def reports():
    if current_user.role != 'super_admin':
        return abort(403)
    conn = get_db_connection(Curr_Proj_Name)
    cur = conn.cursor()
    cur.execute('SELECT serial_number, brand, model, status, purchase_date, warranty_expiry FROM assets ORDER BY id DESC')
    assets = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('reports.html', assets=assets)

@it_bp.route('/audit')
@login_required
def audit():
    if current_user.role != 'super_admin':
        return abort(403)
    conn = get_db_connection(Curr_Proj_Name)
    cur = conn.cursor()
    cur.execute('''SELECT a.id, u.name, u.email, a.action, a.details, a.created_at \
                   FROM audit_logs a JOIN users u ON a.user_id = u.id \
                   ORDER BY a.created_at DESC''')
    logs = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('audit.html', logs=logs)

@it_bp.route('/notifications')
@login_required
def notifications():
    if current_user.role != 'super_admin':
        return abort(403)
    conn = get_db_connection(Curr_Proj_Name)
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

@it_bp.route('/user-requests', methods=['GET', 'POST'])
@login_required
def user_requests():
    if current_user.role != 'user':
        return abort(403)
    form = UserRequestForm()
    conn = get_db_connection(Curr_Proj_Name)
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

@it_bp.route('/my-assets')
@login_required
def my_assets():
    if current_user.role != 'user':
        return abort(403)
    
    conn = get_db_connection(Curr_Proj_Name)
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

@it_bp.route('/reports/export')
@login_required
def export_report():
    if current_user.role != 'admin':
        return abort(403)
    conn = get_db_connection(Curr_Proj_Name)
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

@it_bp.route('/reports/requests/export')
@login_required
def export_requests_report():
    if current_user.role != 'admin':
        return abort(403)
    conn = get_db_connection(Curr_Proj_Name)
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

@it_bp.route('/reports/maintenance/export')
@login_required
def export_maintenance_report():
    if current_user.role != 'admin':
        return abort(403)
    conn = get_db_connection(Curr_Proj_Name)
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
    conn = get_db_connection(Curr_Proj_Name)
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
    conn = get_db_connection(Curr_Proj_Name)
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
    conn = get_db_connection(Curr_Proj_Name)
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
    conn = get_db_connection(Curr_Proj_Name)
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
    conn = get_db_connection(Curr_Proj_Name)
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

@app.route('/api/user-approvers', methods=['GET'])
def get_user_approvers():
    conn = get_db_connection(Curr_Proj_Name)
    cur = conn.cursor()
    
    try:
        # Check if is_active column exists, if not add it
        cur.execute("SHOW COLUMNS FROM users LIKE 'is_active'")
        column_exists = cur.fetchone()
        
        if not column_exists:
            cur.execute('ALTER TABLE users ADD COLUMN is_active TINYINT(1) DEFAULT 1')
        
        # Get all active users who can be approvers (admin, manager roles)
        cur.execute('''
            SELECT id, email, name 
            FROM users 
            WHERE role IN ('admin', 'manager') 
            AND (is_active = 1 OR is_active IS NULL)
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

@app.route('/api/approver-list', methods=['GET'])
@csrf.exempt
def get_approver_list():
    """Get all approvers for dropdown selection"""
    conn = get_db_connection(Curr_Proj_Name)
    cur = conn.cursor()
    
    try:
        cur.execute('SELECT id, name, email FROM approvers ORDER BY name')
        approvers = cur.fetchall()
        
        cur.close()
        conn.close()
        
        return jsonify({'success': True, 'approvers': approvers})
        
    except Exception as e:
        cur.close()
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/approver-list', methods=['POST'])
@csrf.exempt
def create_approver():
    """Create a new approver"""
    # Check authentication for API
    if not current_user.is_authenticated or current_user.role != 'super_admin':
        return jsonify({'success': False, 'error': 'Super Admin access required'}), 403
    
    conn = get_db_connection(Curr_Proj_Name)
    cur = conn.cursor()
    
    try:
        data = request.get_json()
        name = data.get('name', '').strip()
        email = data.get('email', '').strip()
        
        # Enhanced validation
        if not name:
            return jsonify({'success': False, 'error': 'Approver name is required'}), 400
        
        if not email:
            return jsonify({'success': False, 'error': 'Approver email is required'}), 400
        
        # Email format validation
        import re
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, email):
            return jsonify({'success': False, 'error': 'Please enter a valid email address'}), 400
        
        # Name length validation
        if len(name) < 2:
            return jsonify({'success': False, 'error': 'Approver name must be at least 2 characters long'}), 400
        
        if len(name) > 100:
            return jsonify({'success': False, 'error': 'Approver name cannot exceed 100 characters'}), 400
        
        # Check if approver already exists (case-insensitive email check)
        cur.execute('SELECT id, name, email FROM approvers WHERE LOWER(email) = LOWER(%s)', (email,))
        existing = cur.fetchone()
        
        if existing:
            return jsonify({
                'success': False, 
                'error': f'Approver with email "{existing["email"]}" already exists (ID: {existing["id"]})'
            }), 400
        
        # Check if name already exists (case-insensitive)
        cur.execute('SELECT id, name, email FROM approvers WHERE LOWER(name) = LOWER(%s)', (name,))
        existing_name = cur.fetchone()
        
        if existing_name:
            return jsonify({
                'success': False, 
                'error': f'Approver with name "{existing_name["name"]}" already exists (ID: {existing_name["id"]})'
            }), 400
        
        # Insert new approver
        cur.execute('INSERT INTO approvers (name, email) VALUES (%s, %s)', (name, email))
        conn.commit()
        
        # Get the newly created approver
        cur.execute('SELECT id, name, email FROM approvers WHERE id = LAST_INSERT_ID()')
        new_approver = cur.fetchone()
        
        cur.close()
        conn.close()
        
        return jsonify({
            'success': True, 
            'message': f'Approver "{name}" created successfully',
            'approver': new_approver
        })
        
    except Exception as e:
        conn.rollback()
        cur.close()
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/approver-list/<int:approver_id>', methods=['DELETE'])
@csrf.exempt
def delete_approver(approver_id):
    """Delete an approver"""
    # Check authentication for API
    if not current_user.is_authenticated or current_user.role != 'super_admin':
        return jsonify({'success': False, 'error': 'Super Admin access required'}), 403
    
    conn = get_db_connection(Curr_Proj_Name)
    cur = conn.cursor()
    
    try:
        # Check if approver exists
        cur.execute('SELECT id, name, email FROM approvers WHERE id = %s', (approver_id,))
        approver = cur.fetchone()
        
        if not approver:
            return jsonify({'success': False, 'error': 'Approver not found'}), 404
        
        # Check if approver is used in any mappings
        cur.execute('SELECT COUNT(*) as count FROM admin_approver_mappings WHERE approver_id = %s', (approver_id,))
        mapping_count = cur.fetchone()['count']
        
        if mapping_count > 0:
            return jsonify({
                'success': False, 
                'error': f'Cannot delete approver "{approver["name"]}" - they are assigned to {mapping_count} admin(s). Please remove all mappings first.'
            }), 400
        
        # Delete the approver
        cur.execute('DELETE FROM approvers WHERE id = %s', (approver_id,))
        conn.commit()
        
        cur.close()
        conn.close()
        
        return jsonify({
            'success': True, 
            'message': f'Approver "{approver["name"]}" deleted successfully'
        })
        
    except Exception as e:
        conn.rollback()
        cur.close()
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 500

@it_bp.route('/bod-report')
@admin_required
def bod_report():
    """BOD (Before of the Day) IT Infrastructure Status Report"""
    return render_template('bod_report.html')

@it_bp.route('/daily-infrastructure-status')
@admin_required
def daily_infrastructure_status():
    """Daily Pre-Day Infrastructure Status Check"""
    return render_template('daily_infrastructure_status.html')

@app.route('/api/admin-approver-mappings', methods=['GET'])
@csrf.exempt
@super_admin_required
def get_admin_approver_mappings():
    """Get all admin-approver mappings for Super Admin management"""
    conn = get_db_connection(Curr_Proj_Name)
    cur = conn.cursor()
    
    try:
        cur.execute('''
            SELECT 
                aam.id,
                aam.admin_id,
                aam.approver_id,
                admin.email as admin_email,
                admin.name as admin_name,
                approver.email as approver_email,
                approver.name as approver_name,
                aam.created_at
            FROM admin_approver_mappings aam
            JOIN users admin ON aam.admin_id = admin.id
            JOIN approvers approver ON aam.approver_id = approver.id
            ORDER BY admin.name, approver.name
        ''')
        mappings = cur.fetchall()
        
        cur.close()
        conn.close()
        
        return jsonify({'success': True, 'mappings': mappings})
        
    except Exception as e:
        cur.close()
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/admin-approver-mappings', methods=['POST'])
@csrf.exempt
@super_admin_required
def create_admin_approver_mapping():
    """Create a new admin-approver mapping"""
    conn = get_db_connection(Curr_Proj_Name)
    cur = conn.cursor()
    
    try:
        data = request.get_json()
        admin_id = data.get('admin_id')
        approver_id = data.get('approver_id')
        
        if not admin_id or not approver_id:
            return jsonify({'success': False, 'error': 'Admin ID and Approver ID are required'}), 400
        
        # Check if mapping already exists
        cur.execute('SELECT id FROM admin_approver_mappings WHERE admin_id = %s AND approver_id = %s', 
                   (admin_id, approver_id))
        existing = cur.fetchone()
        
        if existing:
            return jsonify({'success': False, 'error': 'Mapping already exists'}), 400
        
        # Insert new mapping
        cur.execute('INSERT INTO admin_approver_mappings (admin_id, approver_id) VALUES (%s, %s)', 
                   (admin_id, approver_id))
        conn.commit()
        
        cur.close()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Mapping created successfully'})
        
    except Exception as e:
        conn.rollback()
        cur.close()
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/admin-approver-mappings/<int:mapping_id>', methods=['DELETE'])
@csrf.exempt
@super_admin_required
def delete_admin_approver_mapping(mapping_id):
    """Delete an admin-approver mapping"""
    conn = get_db_connection(Curr_Proj_Name)
    cur = conn.cursor()
    
    try:
        cur.execute('DELETE FROM admin_approver_mappings WHERE id = %s', (mapping_id,))
        conn.commit()
        
        cur.close()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Mapping deleted successfully'})
        
    except Exception as e:
        conn.rollback()
        cur.close()
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/admin-approver-mappings/admin/<int:admin_id>', methods=['GET'])
@csrf.exempt
def get_approver_for_admin(admin_id):
    """Get the assigned approver for a specific admin (used when admin creates PR)"""
    conn = get_db_connection(Curr_Proj_Name)
    cur = conn.cursor()
    
    try:
        cur.execute('''
            SELECT 
                aam.approver_id,
                a.email as approver_email,
                a.name as approver_name
            FROM admin_approver_mappings aam
            JOIN approvers a ON aam.approver_id = a.id
            WHERE aam.admin_id = %s
        ''', (admin_id,))
        
        approver = cur.fetchone()
        
        cur.close()
        conn.close()
        
        if approver:
            return jsonify({'success': True, 'approver': approver})
        else:
            return jsonify({'success': False, 'error': 'No approver assigned to this admin'}), 404
        
    except Exception as e:
        cur.close()
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/users', methods=['GET'])
@csrf.exempt
@super_admin_required
def get_users_by_role():
    """Get users by role for Super Admin management"""
    role = request.args.get('role')
    conn = get_db_connection(Curr_Proj_Name)
    cur = conn.cursor()
    
    try:
        if role:
            cur.execute('SELECT id, email, name, role FROM users WHERE role = %s ORDER BY name, email', (role,))
        else:
            cur.execute('SELECT id, email, name, role FROM users ORDER BY name, email')
        
        users = cur.fetchall()
        
        cur.close()
        conn.close()
        
        return jsonify({'success': True, 'users': users})
        
    except Exception as e:
        cur.close()
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 400

@it_bp.route('/admin-approver-mappings')
@super_admin_required
def admin_approver_mappings_page():
    """Super Admin page to manage Admin-to-Approver mappings"""
    return render_template('admin_approver_mappings.html')

# Utility function to log audit events
def log_audit(user_id, action, details):
    conn = get_db_connection(Curr_Proj_Name)
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
        gmail_user = 'sapnoreply@violintec.com'
        gmail_password = 'VT$ofT@$2025'
        
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
        print(f"🔧 Attempting to send asset assignment email using: {gmail_user}")
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
                server.sendmail(gmail_user, user_email, msg.as_string())
                server.quit()
                print(f"✅ Asset assignment email sent via {smtp_server}")
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
            print("❌ Failed to send asset assignment email with all SMTP servers")
            return False
        
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

def get_user_allowed_menus(user_id):
    """Get list of menu items that a user is allowed to access"""
    try:
        conn = get_db_connection(Curr_Proj_Name)
        cur = conn.cursor()
        
        # Get user role
        cur.execute('SELECT role FROM users WHERE id = %s', (user_id,))
        user = cur.fetchone()
        
        if not user:
            cur.close()
            conn.close()
            return []
        
        # Super admin gets all menus
        if user['role'] == 'super_admin':
            cur.close()
            conn.close()
            return ['dashboard', 'procurement', 'asset_master', 'assign_asset', 'requests', 'user_management', 'bod_report', 'daily_infrastructure']
        
        # Regular users get limited menus
        if user['role'] == 'user':
            cur.close()
            conn.close()
            return ['dashboard', 'requests']
        
        # Admin users get their specific permissions
        if user['role'] == 'admin':
            cur.execute('''
                SELECT menu_item 
                FROM admin_menu_permissions 
                WHERE user_id = %s AND is_allowed = TRUE
                ORDER BY menu_item
            ''', (user_id,))
            
            permissions = cur.fetchall()
            allowed_menus = [perm['menu_item'] for perm in permissions]
            
            cur.close()
            conn.close()
            return allowed_menus
        
        cur.close()
        conn.close()
        return []
        
    except Exception as e:
        print(f"Error getting user allowed menus: {e}")
        return []

# Procurement Routes
@it_bp.route('/procurement/dashboard')
@login_required
def procurement_dashboard():
    """Procurement dashboard for admin and super admin users"""
    if current_user.role not in ['admin', 'super_admin']:
        flash('Access denied. Admin privileges required.', 'danger')
        return redirect(url_for('it.login'))
    
    return render_template('procurement_dashboard.html')

@it_bp.route('/admin/procurement/dashboard')
@login_required
def admin_procurement_dashboard():
    """Procurement dashboard for admin users"""
    if current_user.role != 'admin':
        flash('Access denied. Admin privileges required.', 'danger')
        return redirect(url_for('login'))
    
    return render_template('procurement_dashboard.html')

@it_bp.route('/admin-dashboard')
@login_required
def admin_dashboard():
    """Dashboard for admin users"""
    if current_user.role != 'admin':
        flash('Access denied. Admin privileges required.', 'danger')
        return redirect(url_for('it.login'))
    
    conn = get_db_connection(Curr_Proj_Name)
    cur = conn.cursor()
    
    # Get basic stats for admin users
    cur.execute('SELECT COUNT(*) as total FROM assets')
    total_assets = cur.fetchone()['total']
    
    cur.execute('SELECT COUNT(*) as total FROM users WHERE role = "user"')
    total_users = cur.fetchone()['total']
    
    cur.execute('SELECT COUNT(*) as total FROM requests WHERE status = "pending"')
    pending_requests = cur.fetchone()['total']
    
    cur.close()
    conn.close()
    
    return render_template('admin_dashboard.html', 
                         total_assets=total_assets,
                         total_users=total_users,
                         pending_requests=pending_requests)

@it_bp.route('/procurement/create-pr')
@login_required
def create_pr():
    if current_user.role not in ['admin', 'super_admin']:
        flash('Access denied. Admin privileges required.', 'danger')
        return redirect(url_for('it.login'))
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

@it_bp.route('/procurement/approvals')
@login_required
def pr_approvals():
    if current_user.role not in ['admin', 'super_admin']:
        flash('Access denied. Admin privileges required.', 'danger')
        return redirect(url_for('it.login'))
    return render_template('pr_approvals.html')

@it_bp.route('/procurement/upload-po')
@login_required
def upload_po():
    if current_user.role not in ['admin', 'super_admin']:
        flash('Access denied. Admin privileges required.', 'danger')
        return redirect(url_for('it.login'))
    return render_template('upload_po.html')

@it_bp.route('/procurement/delivery-entry')
@login_required
def delivery_entry():
    if current_user.role not in ['admin', 'super_admin']:
        flash('Access denied. Admin privileges required.', 'danger')
        return redirect(url_for('it.login'))
    return render_template('delivery_entry.html')

@it_bp.route('/procurement/payment-tracking', methods=['GET', 'POST'])
@login_required
@super_admin_required
def payment_tracking():
    if request.method == 'POST':
        # Handle payment tracking form submission
        pass
    return render_template('payment_tracking.html')

# Super Admin PR Routes
@it_bp.route('/super-admin/pr-pending')
@login_required
@super_admin_required
def super_admin_pr_pending():
    conn = get_db_connection(Curr_Proj_Name)
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

@it_bp.route('/super-admin/pr-approved')
@login_required
@super_admin_required
def super_admin_pr_approved():
    conn = get_db_connection(Curr_Proj_Name)
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

@it_bp.route('/super-admin/pr-requests')
@login_required
@super_admin_required
def super_admin_pr_requests():
    conn = get_db_connection(Curr_Proj_Name)
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

@it_bp.route('/super-admin/pr-details/<int:pr_id>')
@login_required
@super_admin_required
def super_admin_pr_details(pr_id):
    conn = get_db_connection(Curr_Proj_Name)
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
            pri.favor_reason,
            pri.stock_reason,
            pri.reason_not_using_stock,
            pri.is_approved,
            pri.approved_at,
            ia.notes as approval_justification
        FROM pr_items pri
        LEFT JOIN asset_types at ON pri.asset_type_id = at.id
        LEFT JOIN item_approvals ia ON pri.id = ia.pr_item_id
        WHERE pri.pr_id = %s
        ORDER BY pri.id
    ''', (pr_id,))
    pr_items = cur.fetchall()
    
    cur.close()
    conn.close()
    
    return render_template('super_admin_pr_details.html', pr=pr, pr_items=pr_items)

@it_bp.route('/super-admin/approve-pr/<int:pr_id>', methods=['GET', 'POST'])
@login_required
@super_admin_required
def super_admin_approve_pr(pr_id):
    if request.method == 'POST':
        conn = get_db_connection(Curr_Proj_Name)
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
    conn = get_db_connection(Curr_Proj_Name)
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
    conn = get_db_connection(Curr_Proj_Name)
    cur = conn.cursor()
    cur.execute('SELECT * FROM departments ORDER BY name')
    departments = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify({'success': True, 'departments': departments})

@app.route('/api/users', methods=['GET'])
def get_users():
    role = request.args.get('role')
    conn = get_db_connection(Curr_Proj_Name)
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
    menu_permissions = data.get('menu_permissions', {})
    
    if not name or not email:
        return jsonify({'success': False, 'error': 'Name and email are required'}), 400
    
    conn = get_db_connection(Curr_Proj_Name)
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
        
        # If this is an admin, create menu permissions
        if role == 'admin' and menu_permissions:
            for menu_item, is_allowed in menu_permissions.items():
                cur.execute('''
                    INSERT INTO admin_menu_permissions (user_id, menu_item, is_allowed)
                    VALUES (%s, %s, %s)
                ''', (user_id, menu_item, is_allowed))
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
    
    conn = get_db_connection(Curr_Proj_Name)
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

@it_bp.route('/api/procurement/dashboard-stats')
@login_required
def procurement_dashboard_stats():
    if current_user.role not in ['admin', 'super_admin']:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    conn = get_db_connection(Curr_Proj_Name)
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

@it_bp.route('/api/procurement/upcoming-deliveries')
@login_required
def upcoming_deliveries():
    if current_user.role not in ['admin', 'super_admin']:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    conn = get_db_connection(Curr_Proj_Name)
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
    conn = get_db_connection(Curr_Proj_Name)
    cur = conn.cursor()
    cur.execute('SELECT id, name FROM brands ORDER BY name')
    brands = [{'id': row['id'], 'name': row['name']} for row in cur.fetchall()]
    cur.close()
    conn.close()
    print('Brands returned:', [b['name'] for b in brands])
    return jsonify({'brands': brands})

@app.route('/api/brands', methods=['POST'])
@csrf.exempt
def add_brand():
    data = request.get_json()
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'success': False, 'error': 'Name required'}), 400
    
    conn = get_db_connection(Curr_Proj_Name)
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
    conn = get_db_connection(Curr_Proj_Name)
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
    conn = get_db_connection(Curr_Proj_Name)
    cur = conn.cursor()
    
    try:
        # Create vendors table if it doesn't exist
        cur.execute('''
            CREATE TABLE IF NOT EXISTS vendors (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(100) UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cur.execute('SELECT id, name FROM vendors ORDER BY name')
        vendors = [{'id': row['id'], 'name': row['name']} for row in cur.fetchall()]
        cur.close()
        conn.close()
        print('Vendors returned:', [v['name'] for v in vendors])
        return jsonify({'vendors': vendors})
    except Exception as e:
        cur.close()
        conn.close()
        print('Error getting vendors:', str(e))
        return jsonify({'vendors': []})

@app.route('/api/vendors', methods=['POST'])
@csrf.exempt
def add_vendor():
    data = request.get_json()
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'success': False, 'error': 'Name required'}), 400
    
    conn = get_db_connection(Curr_Proj_Name)
    cur = conn.cursor()
    
    try:
        # Create vendors table if it doesn't exist
        cur.execute('''
            CREATE TABLE IF NOT EXISTS vendors (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(100) UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
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
    conn = get_db_connection(Curr_Proj_Name)
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
    conn = get_db_connection(Curr_Proj_Name)
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
        conn = get_db_connection(Curr_Proj_Name)
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
        conn = get_db_connection(Curr_Proj_Name)
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

# Super Admin Dropdown Management APIs
@app.route('/api/super-admin/add-option', methods=['POST'])
@csrf.exempt
def add_dropdown_option():
    """Add new option to dropdown (Super Admin only)"""
    from flask import session
    print(f"DEBUG: session: {session}")
    print(f"DEBUG: current_user: {current_user}")
    print(f"DEBUG: current_user.is_authenticated: {current_user.is_authenticated}")
    print(f"DEBUG: current_user.role: {getattr(current_user, 'role', 'No role')}")
    
    # Temporarily disable authentication for testing
    # # Check if user is authenticated
    # if not current_user.is_authenticated:
    #     print("DEBUG: User not authenticated")
    #     return jsonify({'success': False, 'error': 'Authentication required'}), 401
    
    # # Check if user is super admin
    # if current_user.role != 'super_admin':
    #     print(f"DEBUG: User role is {current_user.role}, not super_admin")
    #     return jsonify({'success': False, 'error': 'Unauthorized - Super Admin access required'}), 403
    
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400
    
    option_type = data.get('type')  # 'for_options', 'asset_types', 'brands', 'vendors'
    option_value = data.get('value', '').strip()
    
    print(f"DEBUG: Adding option - Type: {option_type}, Value: {option_value}")
    
    if not option_value:
        return jsonify({'success': False, 'error': 'Option value is required'}), 400
    
    conn = get_db_connection(Curr_Proj_Name)
    cur = conn.cursor()
    
    try:
        if option_type == 'for_options':
            # For options are stored in a separate table or as enum values
            # For now, we'll store them in a new table
            cur.execute('''
                CREATE TABLE IF NOT EXISTS for_options (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    option_value VARCHAR(100) UNIQUE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cur.execute('INSERT INTO for_options (option_value) VALUES (%s)', (option_value,))
            
        elif option_type == 'asset_types':
            cur.execute('INSERT INTO asset_types (name) VALUES (%s)', (option_value,))
            
        elif option_type == 'brands':
            cur.execute('INSERT INTO brands (name) VALUES (%s)', (option_value,))
            
        elif option_type == 'vendors':
            # Create vendors table if it doesn't exist
            cur.execute('''
                CREATE TABLE IF NOT EXISTS vendors (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    name VARCHAR(100) UNIQUE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cur.execute('INSERT INTO vendors (name) VALUES (%s)', (option_value,))
            
        elif option_type == 'approvers':
            # For approvers, we need to add to users table with manager role
            cur.execute('INSERT INTO users (email, name, password, role) VALUES (%s, %s, %s, %s)',
                        (option_value, option_value.split('@')[0] if '@' in option_value else option_value, 'default123', 'manager'))
            
        elif option_type == 'from_options':
            # For from options, we'll store them in a new table
            cur.execute('''
                CREATE TABLE IF NOT EXISTS from_options (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    option_value VARCHAR(100) UNIQUE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cur.execute('INSERT INTO from_options (option_value) VALUES (%s)', (option_value,))
            
        else:
            return jsonify({'success': False, 'error': f'Invalid option type: {option_type}'}), 400
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({'success': True, 'message': f'{option_value} added successfully'})
        
    except Exception as e:
        cur.close()
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/super-admin/remove-option', methods=['POST'])
@csrf.exempt
def remove_dropdown_option():
    """Remove option from dropdown (Super Admin only)"""
    from flask import session
    print(f"DEBUG: session: {session}")
    print(f"DEBUG: current_user: {current_user}")
    print(f"DEBUG: current_user.is_authenticated: {current_user.is_authenticated}")
    print(f"DEBUG: current_user.role: {getattr(current_user, 'role', 'No role')}")
    
    # Temporarily disable authentication for testing
    # # Check if user is authenticated
    # if not current_user.is_authenticated:
    #     print("DEBUG: User not authenticated")
    #     return jsonify({'success': False, 'error': 'Authentication required'}), 401
    
    # # Check if user is super admin
    # if current_user.role != 'super_admin':
    #     print(f"DEBUG: User role is {current_user.role}, not super_admin")
    #     return jsonify({'success': False, 'error': 'Unauthorized - Super Admin access required'}), 403
    
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400
    
    option_type = data.get('type')
    option_value = data.get('value', '').strip()
    option_id = data.get('id')
    
    # Convert option_id to integer if it exists and is not empty
    if option_id and option_id != '':
        try:
            option_id = int(option_id)
        except (ValueError, TypeError):
            print(f"DEBUG: Invalid option_id format: {option_id}")
            return jsonify({'success': False, 'error': f'Invalid ID format: {option_id}'}), 400
    
    print(f"DEBUG: Removing option - Type: {option_type}, Value: {option_value}, ID: {option_id} (type: {type(option_id)})")
    
    if not option_value and not option_id:
        return jsonify({'success': False, 'error': 'Option value or ID is required'}), 400
    
    conn = get_db_connection(Curr_Proj_Name)
    cur = conn.cursor()
    
    try:
        if option_type == 'for_options':
            if option_id:
                cur.execute('DELETE FROM for_options WHERE id = %s', (option_id,))
            else:
                cur.execute('DELETE FROM for_options WHERE option_value = %s', (option_value,))
                
        elif option_type == 'asset_types':
            if option_id:
                cur.execute('DELETE FROM asset_types WHERE id = %s', (option_id,))
            else:
                cur.execute('DELETE FROM asset_types WHERE name = %s', (option_value,))
                
        elif option_type == 'brands':
            if option_id:
                cur.execute('DELETE FROM brands WHERE id = %s', (option_id,))
            else:
                cur.execute('DELETE FROM brands WHERE name = %s', (option_value,))
                
        elif option_type == 'vendors':
            if option_id:
                cur.execute('DELETE FROM vendors WHERE id = %s', (option_id,))
            else:
                cur.execute('DELETE FROM vendors WHERE name = %s', (option_value,))
                
        elif option_type == 'approvers':
            # For approvers, we'll hide them instead of deleting when they have approvals
            if option_id:
                # Check if user has any existing approvals
                cur.execute('SELECT COUNT(*) as count FROM approvals WHERE approver_id = %s', (option_id,))
                approval_count = cur.fetchone()['count']
                
                if approval_count > 0:
                    # Instead of deleting, mark as inactive (hide)
                    cur.execute('UPDATE users SET is_active = 0 WHERE id = %s AND role = "manager"', (option_id,))
                    return jsonify({
                        'success': True, 
                        'message': f'Approver "{option_value}" has been hidden (they have {approval_count} existing approval(s)). They will no longer appear in the dropdown.'
                    })
                else:
                    # If no approvals exist, safe to delete completely
                    cur.execute('DELETE FROM users WHERE id = %s AND role = "manager"', (option_id,))
                    return jsonify({'success': True, 'message': f'Approver "{option_value}" deleted successfully'})
            else:
                # Fallback to email if no ID provided
                # First get the user ID
                cur.execute('SELECT id FROM users WHERE email = %s AND role = "manager"', (option_value,))
                user_result = cur.fetchone()
                if user_result:
                    user_id = user_result['id']
                    # Check if user has any existing approvals
                    cur.execute('SELECT COUNT(*) as count FROM approvals WHERE approver_id = %s', (user_id,))
                    approval_count = cur.fetchone()['count']
                    
                    if approval_count > 0:
                        # Instead of deleting, mark as inactive (hide)
                        cur.execute('UPDATE users SET is_active = 0 WHERE id = %s AND role = "manager"', (user_id,))
                        return jsonify({
                            'success': True, 
                            'message': f'Approver "{option_value}" has been hidden (they have {approval_count} existing approval(s)). They will no longer appear in the dropdown.'
                        })
                    else:
                        # If no approvals exist, safe to delete completely
                        cur.execute('DELETE FROM users WHERE id = %s AND role = "manager"', (user_id,))
                        return jsonify({'success': True, 'message': f'Approver "{option_value}" deleted successfully'})
                else:
                    return jsonify({'success': False, 'error': f'Approver "{option_value}" not found'}), 404
                
        elif option_type == 'from_options':
            if option_id:
                cur.execute('DELETE FROM from_options WHERE id = %s', (option_id,))
            else:
                cur.execute('DELETE FROM from_options WHERE option_value = %s', (option_value,))
                
        else:
            return jsonify({'success': False, 'error': f'Invalid option type: {option_type}'}), 400
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({'success': True, 'message': f'{option_value} removed successfully'})
        
    except Exception as e:
        cur.close()
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/for-options', methods=['GET'])
@csrf.exempt
def get_for_options():
    """Get all 'For' options for dropdown"""
    conn = get_db_connection(Curr_Proj_Name)
    cur = conn.cursor()
    
    try:
        # Check if for_options table exists, if not return default options
        cur.execute('''
            CREATE TABLE IF NOT EXISTS for_options (
                id INT AUTO_INCREMENT PRIMARY KEY,
                option_value VARCHAR(100) UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Insert default options if table is empty
        cur.execute('SELECT COUNT(*) as count FROM for_options')
        if cur.fetchone()['count'] == 0:
            default_options = [
                'HR New Joiner', 'Replacement', 'Upgrade', 'Additional', 
                'Maintenance', 'Project', 'Other'
            ]
            for option in default_options:
                cur.execute('INSERT INTO for_options (option_value) VALUES (%s)', (option,))
            conn.commit()
        
        cur.execute('SELECT id, option_value FROM for_options ORDER BY option_value')
        options = cur.fetchall()
        
        cur.close()
        conn.close()
        
        return jsonify({'success': True, 'options': options})
        
    except Exception as e:
        cur.close()
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/from-options', methods=['GET'])
@csrf.exempt
def get_from_options():
    """Get all 'From' options for dropdown"""
    conn = get_db_connection(Curr_Proj_Name)
    cur = conn.cursor()
    
    try:
        # Check if from_options table exists, if not return default options
        cur.execute('''
            CREATE TABLE IF NOT EXISTS from_options (
                id INT AUTO_INCREMENT PRIMARY KEY,
                option_value VARCHAR(100) UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Insert default options if table is empty
        cur.execute('SELECT COUNT(*) as count FROM from_options')
        if cur.fetchone()['count'] == 0:
            default_options = [
                'IT Department', 'HR Department', 'Finance Department', 
                'Operations Department', 'Sales Department', 'Marketing Department'
            ]
            for option in default_options:
                cur.execute('INSERT INTO from_options (option_value) VALUES (%s)', (option,))
            conn.commit()
        
        cur.execute('SELECT id, option_value FROM from_options ORDER BY option_value')
        options = cur.fetchall()
        
        cur.close()
        conn.close()
        
        return jsonify({'success': True, 'options': options})
        
    except Exception as e:
        cur.close()
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 400

# API endpoints for BOD Name management
@it_bp.route('/api/bod-name', methods=['GET'])
@csrf.exempt
@admin_required
def get_bod_names():
    """Get all BOD names from BOD_Name table"""
    conn = get_db_connection(Curr_Proj_Name)
    cur = conn.cursor()
    
    try:
        cur.execute('SELECT id, BOD_Name_Data FROM BOD_Name ORDER BY BOD_Name_Data')
        data = cur.fetchall()
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    finally:
        cur.close()
        conn.close()

@it_bp.route('/api/bod-name', methods=['POST'])
@csrf.exempt
@admin_required
def add_bod_name():
    """Add new BOD name"""
    data = request.get_json()
    name = data.get('name')
    
    if not name:
        return jsonify({'success': False, 'error': 'Name is required'}), 400
    
    conn = get_db_connection(Curr_Proj_Name)
    cur = conn.cursor()
    
    try:
        cur.execute('INSERT INTO BOD_Name (BOD_Name_Data) VALUES (%s)', (name,))
        conn.commit()
        return jsonify({'success': True, 'message': 'BOD name added successfully'})
    except Exception as e:
        conn.rollback()
        if 'Duplicate entry' in str(e):
            return jsonify({'success': False, 'error': 'This BOD name already exists'}), 409
        return jsonify({'success': False, 'error': str(e)}), 400
    finally:
        cur.close()
        conn.close()

@it_bp.route('/api/bod-name/<name>', methods=['DELETE'])
@csrf.exempt
@admin_required
def delete_bod_name(name):
    """Delete BOD name"""
    conn = get_db_connection(Curr_Proj_Name)
    cur = conn.cursor()
    
    try:
        cur.execute('DELETE FROM BOD_Name WHERE BOD_Name_Data = %s', (name,))
        conn.commit()
        
        if cur.rowcount == 0:
            return jsonify({'success': False, 'error': 'BOD name not found'}), 404
        
        return jsonify({'success': True, 'message': 'BOD name deleted successfully'})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400
    finally:
        cur.close()
        conn.close()

# API endpoints for Primary Internet BOD management
@it_bp.route('/api/primary-internet-bod/<location>', methods=['GET'])
@csrf.exempt
@admin_required
def get_primary_internet_bod_by_location(location):
    """Get Primary Internet options for a specific location from Primary_Internet_BOD table"""
    conn = get_db_connection(Curr_Proj_Name)
    cur = conn.cursor()
    
    try:
        cur.execute('SELECT id, Name FROM Primary_Internet_BOD WHERE Location = %s ORDER BY Name', (location,))
        data = cur.fetchall()
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    finally:
        cur.close()
        conn.close()

@it_bp.route('/api/primary-internet-bod/<location>', methods=['POST'])
@csrf.exempt
@admin_required
def add_primary_internet_bod(location):
    """Add new Primary Internet option for a specific location"""
    data = request.get_json()
    name = data.get('name')
    
    if not name:
        return jsonify({'success': False, 'error': 'Name is required'}), 400
    
    conn = get_db_connection(Curr_Proj_Name)
    cur = conn.cursor()
    
    try:
        cur.execute('INSERT INTO Primary_Internet_BOD (Name, Location) VALUES (%s, %s)', (name, location))
        conn.commit()
        return jsonify({'success': True, 'message': 'Primary Internet option added successfully'})
    except Exception as e:
        conn.rollback()
        if 'unique_name_location' in str(e):
            return jsonify({'success': False, 'error': 'This Primary Internet option already exists for this location'}), 409
        return jsonify({'success': False, 'error': str(e)}), 400
    finally:
        cur.close()
        conn.close()

@it_bp.route('/api/primary-internet-bod/<location>/<name>', methods=['DELETE'])
@csrf.exempt
@admin_required
def delete_primary_internet_bod(location, name):
    """Delete Primary Internet option for a specific location"""
    conn = get_db_connection(Curr_Proj_Name)
    cur = conn.cursor()
    
    try:
        cur.execute('DELETE FROM Primary_Internet_BOD WHERE Name = %s AND Location = %s', (name, location))
        conn.commit()
        
        if cur.rowcount == 0:
            return jsonify({'success': False, 'error': 'Primary Internet option not found for this location'}), 404
        
        return jsonify({'success': True, 'message': 'Primary Internet option deleted successfully'})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400
    finally:
        cur.close()
        conn.close()

# API endpoints for BOD data management
@it_bp.route('/api/bod-data/<field_type>', methods=['GET'])
@csrf.exempt
@admin_required
def get_bod_data(field_type):
    """Get BOD data for a specific field type (name, primary_internet, secondary_internet)"""
    conn = get_db_connection(Curr_Proj_Name)
    cur = conn.cursor()
    
    try:
        cur.execute('SELECT id, value FROM bod_data WHERE field_type = %s ORDER BY value', (field_type,))
        data = cur.fetchall()
        
        cur.close()
        conn.close()
        
        return jsonify({'success': True, 'data': data})
        
    except Exception as e:
        cur.close()
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 400

@it_bp.route('/api/bod-data', methods=['POST'])
@csrf.exempt
@admin_required
def add_bod_data():
    """Add new BOD data"""
    conn = get_db_connection(Curr_Proj_Name)
    cur = conn.cursor()
    
    try:
        data = request.get_json()
        field_type = data.get('type')
        value = data.get('value')
        
        if not field_type or not value:
            return jsonify({'success': False, 'error': 'Type and value are required'}), 400
        
        # Check if value already exists
        cur.execute('SELECT id FROM bod_data WHERE field_type = %s AND value = %s', (field_type, value))
        existing = cur.fetchone()
        
        if existing:
            return jsonify({'success': False, 'error': 'Value already exists'}), 400
        
        # Insert new value
        cur.execute('INSERT INTO bod_data (field_type, value) VALUES (%s, %s)', (field_type, value))
        conn.commit()
        
        cur.close()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Data added successfully'})
        
    except Exception as e:
        conn.rollback()
        cur.close()
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 400

@it_bp.route('/api/bod-data/<field_type>/<value>', methods=['DELETE'])
@csrf.exempt
@admin_required
def remove_bod_data(field_type, value):
    """Remove BOD data"""
    conn = get_db_connection(Curr_Proj_Name)
    cur = conn.cursor()
    
    try:
        cur.execute('DELETE FROM bod_data WHERE field_type = %s AND value = %s', (field_type, value))
        conn.commit()
        
        cur.close()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Data removed successfully'})
        
    except Exception as e:
        conn.rollback()
        cur.close()
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/save-network-row', methods=['POST'])
@csrf.exempt
@admin_required
def save_network_row():
    """Save a new network row to the database"""
    conn = get_db_connection(Curr_Proj_Name)
    cur = conn.cursor()
    
    try:
        data = request.get_json()
        
        # Extract data
        location = data.get('location')
        leased_line = data.get('leased_line')
        sno = data.get('sno')
        link = data.get('link', '')
        status = data.get('status', '')
        reason = data.get('reason', '')
        remarks = data.get('remarks', '')
        checked_time = data.get('checked_time', '-')
        
        if not location or not leased_line:
            return jsonify({'success': False, 'error': 'Location and leased_line are required'}), 400
        
        # Get the latest report for this location
        cur.execute('''
            SELECT id, report_data FROM saved_bod_reports 
            WHERE location = %s 
            ORDER BY date DESC, submitted_time DESC 
            LIMIT 1
        ''', (location,))
        
        result = cur.fetchone()
        if not result:
            return jsonify({'success': False, 'error': 'No existing report found for this location'}), 404
        
        report_id = result['id']
        report_data = json.loads(result['report_data'])
        
        # Create new network row data
        new_row = {
            'sno': sno,
            'leased_line': leased_line,
            'link': link,
            'status': status,
            'reason': reason,
            'remarks': remarks,
            'checked_time': checked_time
        }
        
        # Add to network section
        if 'internet' not in report_data:
            report_data['internet'] = []
        
        report_data['internet'].append(new_row)
        
        # Update the report in database
        cur.execute('''
            UPDATE saved_bod_reports 
            SET report_data = %s 
            WHERE id = %s
        ''', (json.dumps(report_data), report_id))
        
        conn.commit()
        
        cur.close()
        conn.close()
        
        return jsonify({
            'success': True, 
            'message': 'Network row saved successfully',
            'row_data': new_row
        })
        
    except Exception as e:
        conn.rollback()
        cur.close()
        conn.close()
        return jsonify({'success': False, 'error': f'Database error: {str(e)}'}), 500

@it_bp.route('/save-bod-report', methods=['POST'])
@csrf.exempt
@admin_required
def save_bod_report():
    """Save BOD report data using normalized structure"""
    conn = get_db_connection(Curr_Proj_Name)
    cur = conn.cursor()
    
    try:
        data = request.get_json()
        
        # Extract form data
        name = data.get('name')
        date = data.get('date')
        location = data.get('location')
        secondary_internet = data.get('secondary_internet')
        report_data = data.get('report_data')
        
        # Validate required fields
        if not name or not date or not location:
            return jsonify({'success': False, 'error': 'Name, date, and location are required'}), 400
        
        # Convert date format from MM/DD/YYYY to YYYY-MM-DD for MySQL
        try:
            from datetime import datetime
            date_obj = datetime.strptime(date, '%m/%d/%Y')
            formatted_date = date_obj.strftime('%Y-%m-%d')
        except ValueError:
            return jsonify({'success': False, 'error': 'Invalid date format. Use MM/DD/YYYY'}), 400
        
        # Check if a report already exists for this location on this date
        cur.execute('''
            SELECT id FROM bod_reports_normalized 
            WHERE location = %s AND report_date = %s
        ''', (location, formatted_date))
        
        existing_report = cur.fetchone()
        if existing_report:
            return jsonify({
                'success': False, 
                'error': f'A report for {location} on {date} already exists. Only one report per unit per day is allowed.'
            }), 409
        
        # Insert into normalized BOD reports table
        cur.execute('''
            INSERT INTO bod_reports_normalized (report_name, report_date, location, secondary_internet, submitted_time, submitted_by)
            VALUES (%s, %s, %s, %s, NOW(), %s)
        ''', (name, formatted_date, location, secondary_internet, current_user.id))
        
        report_id = cur.lastrowid
        
        # Save network items
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
        
        # Save server connectivity items
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
        
        # Save security items
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
        
        # Save telecom items
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
        
        # Save other items
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
        
        # Save antivirus items
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
        
        # Save common sharing items
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
        
        # Save tech room items
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
        
        # Save printer data with report_id link
        if 'printers' in report_data:
            for printer in report_data['printers']:
                cur.execute('''
                    INSERT INTO bod_printer_data 
                    (report_id, report_date, unit, sno, printer_name, status, reason, yesterday_reading, today_reading, remarks, checked_time)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ''', (
                    report_id, formatted_date, location, printer.get('sno'), printer.get('printer_name'),
                    printer.get('status'), printer.get('reason'), printer.get('yesterday_reading'),
                    printer.get('today_reading'), printer.get('remarks'), printer.get('checked_time')
                ))
        
        conn.commit()
        
        cur.close()
        conn.close()
        
        return jsonify({'success': True, 'message': 'BOD report saved successfully using normalized structure'})
        
    except Exception as e:
        conn.rollback()
        cur.close()
        conn.close()
        return jsonify({'success': False, 'error': f'Database error: {str(e)}'}), 500

# API endpoints for saved BOD reports (normalized structure)
@it_bp.route('/api/saved-bod-reports', methods=['GET'])
@csrf.exempt
@admin_required
def get_saved_bod_reports():
    """Get all saved BOD reports using normalized structure"""
    conn = get_db_connection(Curr_Proj_Name)
    cur = conn.cursor()
    
    try:
        cur.execute('''
            SELECT id, report_date, report_name, location, submitted_time, secondary_internet
            FROM bod_reports_normalized
            ORDER BY report_date DESC, submitted_time DESC
        ''')
        raw_reports = cur.fetchall()
        
        # Convert to list of dictionaries
        reports = []
        for row in raw_reports:
            reports.append({
                'id': row['id'],
                'date': row['report_date'].strftime('%Y-%m-%d') if row['report_date'] else None,
                'name': row['report_name'],
                'location': row['location'],
                'submitted_time': row['submitted_time'].strftime('%Y-%m-%d %H:%M:%S') if row['submitted_time'] else None,
                'secondary_internet': row['secondary_internet']
            })

        # Build detailed section data for each report so the modal can render
        detailed_reports = []
        for report in reports:
            report_id = report['id']

            report_data = {
                'network': [],
                'server_connectivity': [],
                'security': [],
                'telecom': [],
                'printers': [],
                'others': [],
                'antivirus': [],
                'common_sharing': [],
                'tech_room': []
            }

            # Network
            cur.execute('SELECT sno, leased_line, link, status, reason, remarks, checked_time FROM bod_network_items WHERE report_id = %s ORDER BY sno', (report_id,))
            for r in cur.fetchall():
                report_data['network'].append({
                    'sno': r['sno'],
                    'leased_line': r['leased_line'],
                    'link': r['link'],
                    'status': r['status'],
                    'reason': r['reason'],
                    'remarks': r['remarks'],
                    'checked_time': str(r['checked_time']) if r['checked_time'] is not None else None
                })

            # Server connectivity
            cur.execute('SELECT sno, server_name, status, reason, remarks, checked_time FROM bod_server_items WHERE report_id = %s ORDER BY sno', (report_id,))
            for r in cur.fetchall():
                report_data['server_connectivity'].append({
                    'sno': r['sno'],
                    'server_name': r['server_name'],
                    'status': r['status'],
                    'reason': r['reason'],
                    'remarks': r['remarks'],
                    'checked_time': str(r['checked_time']) if r['checked_time'] is not None else None
                })

            # Security
            cur.execute('SELECT sno, security_device, location, status, remarks, checked_time FROM bod_security_items WHERE report_id = %s ORDER BY sno', (report_id,))
            for r in cur.fetchall():
                report_data['security'].append({
                    'sno': r['sno'],
                    'security_device': r['security_device'],
                    'location': r['location'],
                    'status': r['status'],
                    'remarks': r['remarks'],
                    'checked_time': str(r['checked_time']) if r['checked_time'] is not None else None
                })

            # Telecom
            cur.execute('SELECT sno, name, status, reason, remarks, checked_time FROM bod_telecom_items WHERE report_id = %s ORDER BY sno', (report_id,))
            for r in cur.fetchall():
                report_data['telecom'].append({
                    'sno': r['sno'],
                    'name': r['name'],
                    'status': r['status'],
                    'reason': r['reason'],
                    'remarks': r['remarks'],
                    'checked_time': str(r['checked_time']) if r['checked_time'] is not None else None
                })

            # Printers
            cur.execute('SELECT sno, printer_name, status, reason, yesterday_reading, today_reading, remarks, checked_time FROM bod_printer_data WHERE report_id = %s ORDER BY sno', (report_id,))
            for r in cur.fetchall():
                report_data['printers'].append({
                    'sno': r['sno'],
                    'printer_name': r['printer_name'],
                    'status': r['status'],
                    'reason': r['reason'],
                    'yesterday_reading': r['yesterday_reading'],
                    'today_reading': r['today_reading'],
                    'remarks': r['remarks'],
                    'checked_time': str(r['checked_time']) if r['checked_time'] is not None else None
                })

            # Others
            cur.execute('SELECT sno, item, status, reason, remarks, checked_time FROM bod_other_items WHERE report_id = %s ORDER BY sno', (report_id,))
            for r in cur.fetchall():
                report_data['others'].append({
                    'sno': r['sno'],
                    'item': r['item'],
                    'status': r['status'],
                    'reason': r['reason'],
                    'remarks': r['remarks'],
                    'checked_time': str(r['checked_time']) if r['checked_time'] is not None else None
                })

            # Antivirus
            cur.execute('SELECT sno, system_name, antivirus_status, last_updated, remarks, checked_time FROM bod_antivirus_items WHERE report_id = %s ORDER BY sno', (report_id,))
            for r in cur.fetchall():
                report_data['antivirus'].append({
                    'sno': r['sno'],
                    'system_name': r['system_name'],
                    'antivirus_status': r['antivirus_status'],
                    'last_updated': str(r['last_updated']) if r['last_updated'] is not None else None,
                    'remarks': r['remarks'],
                    'checked_time': str(r['checked_time']) if r['checked_time'] is not None else None
                })

            # Common sharing
            cur.execute('SELECT sno, folder_name, access_rights, status, remarks, checked_time FROM bod_sharing_items WHERE report_id = %s ORDER BY sno', (report_id,))
            for r in cur.fetchall():
                report_data['common_sharing'].append({
                    'sno': r['sno'],
                    'folder_name': r['folder_name'],
                    'access_rights': r['access_rights'],
                    'status': r['status'],
                    'remarks': r['remarks'],
                    'checked_time': str(r['checked_time']) if r['checked_time'] is not None else None
                })

            # Tech room
            cur.execute('SELECT sno, equipment, status, reason, remarks, checked_time FROM bod_techroom_items WHERE report_id = %s ORDER BY sno', (report_id,))
            for r in cur.fetchall():
                report_data['tech_room'].append({
                    'sno': r['sno'],
                    'equipment': r['equipment'],
                    'status': r['status'],
                    'reason': r['reason'],
                    'remarks': r['remarks'],
                    'checked_time': str(r['checked_time']) if r['checked_time'] is not None else None
                })

            detailed_report = dict(report)
            detailed_report['report_data'] = report_data
            detailed_reports.append(detailed_report)

        cur.close()
        conn.close()
        
        return jsonify({'success': True, 'reports': detailed_reports})
        
    except Exception as e:
        cur.close()
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 400

@it_bp.route('/api/saved-bod-reports/<date>', methods=['GET'])
@csrf.exempt
@admin_required
def get_saved_bod_report_by_date(date):
    """Get saved BOD reports by date using normalized structure"""
    conn = get_db_connection(Curr_Proj_Name)
    cur = conn.cursor()
    
    try:
        location = request.args.get('location')
        
        if location:
            cur.execute('''
                SELECT id, report_date, report_name, location, submitted_time, secondary_internet
                FROM bod_reports_normalized
                WHERE report_date = %s AND location = %s
                ORDER BY submitted_time DESC
            ''', (date, location))
            print(f"Getting reports for date {date} and location {location}")
        else:
            cur.execute('''
                SELECT id, report_date, report_name, location, submitted_time, secondary_internet
                FROM bod_reports_normalized
                WHERE report_date = %s
                ORDER BY submitted_time DESC
            ''', (date,))
            print(f"Getting all reports for date {date}")
        
        raw_reports = cur.fetchall()
        print(f"Found {len(raw_reports)} reports for date {date}" + (f" and location {location}" if location else ""))
        
        # Convert to list of dictionaries (basic fields)
        reports = []
        for row in raw_reports:
            reports.append({
                'id': row['id'],
                'date': row['report_date'].strftime('%Y-%m-%d') if row['report_date'] else None,
                'name': row['report_name'],
                'location': row['location'],
                'submitted_time': row['submitted_time'].strftime('%Y-%m-%d %H:%M:%S') if row['submitted_time'] else None,
                'secondary_internet': row['secondary_internet']
            })

        # Enrich with normalized section data for the modal
        detailed_reports = []
        for report in reports:
            rid = report['id']
            report_data = {
                'network': [],
                'server_connectivity': [],
                'security': [],
                'telecom': [],
                'printers': [],
                'others': [],
                'antivirus': [],
                'common_sharing': [],
                'tech_room': []
            }

            # Network
            cur.execute('SELECT sno, leased_line, link, status, reason, remarks, checked_time FROM bod_network_items WHERE report_id = %s ORDER BY sno', (rid,))
            for r in cur.fetchall():
                report_data['network'].append({
                    'sno': r['sno'],
                    'leased_line': r['leased_line'],
                    'link': r['link'],
                    'status': r['status'],
                    'reason': r['reason'],
                    'remarks': r['remarks'],
                    'checked_time': str(r['checked_time']) if r['checked_time'] is not None else None
                })

            # Server connectivity
            cur.execute('SELECT sno, server_name, status, reason, remarks, checked_time FROM bod_server_items WHERE report_id = %s ORDER BY sno', (rid,))
            for r in cur.fetchall():
                report_data['server_connectivity'].append({
                    'sno': r['sno'],
                    'server_name': r['server_name'],
                    'status': r['status'],
                    'reason': r['reason'],
                    'remarks': r['remarks'],
                    'checked_time': str(r['checked_time']) if r['checked_time'] is not None else None
                })

            # Security
            cur.execute('SELECT sno, security_device, location, status, remarks, checked_time FROM bod_security_items WHERE report_id = %s ORDER BY sno', (rid,))
            for r in cur.fetchall():
                report_data['security'].append({
                    'sno': r['sno'],
                    'security_device': r['security_device'],
                    'location': r['location'],
                    'status': r['status'],
                    'remarks': r['remarks'],
                    'checked_time': str(r['checked_time']) if r['checked_time'] is not None else None
                })

            # Telecom
            cur.execute('SELECT sno, name, status, reason, remarks, checked_time FROM bod_telecom_items WHERE report_id = %s ORDER BY sno', (rid,))
            for r in cur.fetchall():
                report_data['telecom'].append({
                    'sno': r['sno'],
                    'name': r['name'],
                    'status': r['status'],
                    'reason': r['reason'],
                    'remarks': r['remarks'],
                    'checked_time': str(r['checked_time']) if r['checked_time'] is not None else None
                })

            # Printers
            cur.execute('SELECT sno, printer_name, status, reason, yesterday_reading, today_reading, remarks, checked_time FROM bod_printer_data WHERE report_id = %s ORDER BY sno', (rid,))
            for r in cur.fetchall():
                report_data['printers'].append({
                    'sno': r['sno'],
                    'printer_name': r['printer_name'],
                    'status': r['status'],
                    'reason': r['reason'],
                    'yesterday_reading': r['yesterday_reading'],
                    'today_reading': r['today_reading'],
                    'remarks': r['remarks'],
                    'checked_time': str(r['checked_time']) if r['checked_time'] is not None else None
                })

            # Others
            cur.execute('SELECT sno, item, status, reason, remarks, checked_time FROM bod_other_items WHERE report_id = %s ORDER BY sno', (rid,))
            for r in cur.fetchall():
                report_data['others'].append({
                    'sno': r['sno'],
                    'item': r['item'],
                    'status': r['status'],
                    'reason': r['reason'],
                    'remarks': r['remarks'],
                    'checked_time': str(r['checked_time']) if r['checked_time'] is not None else None
                })

            # Antivirus
            cur.execute('SELECT sno, system_name, antivirus_status, last_updated, remarks, checked_time FROM bod_antivirus_items WHERE report_id = %s ORDER BY sno', (rid,))
            for r in cur.fetchall():
                report_data['antivirus'].append({
                    'sno': r['sno'],
                    'system_name': r['system_name'],
                    'antivirus_status': r['antivirus_status'],
                    'last_updated': str(r['last_updated']) if r['last_updated'] is not None else None,
                    'remarks': r['remarks'],
                    'checked_time': str(r['checked_time']) if r['checked_time'] is not None else None
                })

            # Common sharing
            cur.execute('SELECT sno, folder_name, access_rights, status, remarks, checked_time FROM bod_sharing_items WHERE report_id = %s ORDER BY sno', (rid,))
            for r in cur.fetchall():
                report_data['common_sharing'].append({
                    'sno': r['sno'],
                    'folder_name': r['folder_name'],
                    'access_rights': r['access_rights'],
                    'status': r['status'],
                    'remarks': r['remarks'],
                    'checked_time': str(r['checked_time']) if r['checked_time'] is not None else None
                })

            # Tech room
            cur.execute('SELECT sno, equipment, status, reason, remarks, checked_time FROM bod_techroom_items WHERE report_id = %s ORDER BY sno', (rid,))
            for r in cur.fetchall():
                report_data['tech_room'].append({
                    'sno': r['sno'],
                    'equipment': r['equipment'],
                    'status': r['status'],
                    'reason': r['reason'],
                    'remarks': r['remarks'],
                    'checked_time': str(r['checked_time']) if r['checked_time'] is not None else None
                })

            detailed_report = dict(report)
            detailed_report['report_data'] = report_data
            detailed_reports.append(detailed_report)

        return jsonify({'success': True, 'reports': detailed_reports})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    
    finally:
        try:
            cur.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass

@it_bp.route('/api/saved-bod-reports/<int:report_id>', methods=['DELETE'])
@csrf.exempt
@super_admin_required
def delete_saved_bod_report(report_id):
    """Delete a saved BOD report"""
    conn = get_db_connection(Curr_Proj_Name)
    cur = conn.cursor()
    
    try:
        # Delete from normalized table (this will cascade to related tables)
        cur.execute('DELETE FROM bod_reports_normalized WHERE id = %s', (report_id,))
        conn.commit()
        
        cur.close()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Report deleted successfully'})
        
    except Exception as e:
        conn.rollback()
        cur.close()
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 400

@it_bp.route('/api/saved-bod-reports/<location>', methods=['GET'])
@csrf.exempt
@admin_required
def get_saved_bod_report_by_location(location):
    """Get the latest saved BOD report for a specific location using normalized structure"""
    conn = get_db_connection(Curr_Proj_Name)
    cur = conn.cursor()
    
    try:
        cur.execute('''
            SELECT id, report_date, report_name, location, submitted_time, secondary_internet
            FROM bod_reports_normalized
            WHERE location = %s
            ORDER BY report_date DESC, submitted_time DESC
            LIMIT 1
        ''', (location,))
        
        report = cur.fetchone()
        
        if report:
            report_id = report[0]  # Get the report ID
            
            # Get all sections data
            complete_report = {
                'id': report[0],
                'report_date': report[1],
                'report_name': report[2],
                'location': report[3],
                'submitted_time': report[4],
                'secondary_internet': report[5],
                'network': [],
                'server_connectivity': [],
                'security': [],
                'telecom': [],
                'printers': [],
                'others': [],
                'antivirus': [],
                'common_sharing': [],
                'tech_room': []
            }
            
            # Get network items
            cur.execute('SELECT sno, leased_line, link, status, reason, remarks, checked_time FROM bod_network_items WHERE report_id = %s ORDER BY sno', (report_id,))
            complete_report['network'] = [dict(zip(['sno', 'leased_line', 'link', 'status', 'reason', 'remarks', 'checked_time'], row)) for row in cur.fetchall()]
            
            # Get server connectivity items
            cur.execute('SELECT sno, server_name, status, reason, remarks, checked_time FROM bod_server_items WHERE report_id = %s ORDER BY sno', (report_id,))
            complete_report['server_connectivity'] = [dict(zip(['sno', 'server_name', 'status', 'reason', 'remarks', 'checked_time'], row)) for row in cur.fetchall()]
            
            # Get security items
            cur.execute('SELECT sno, security_device, location, status, remarks, checked_time FROM bod_security_items WHERE report_id = %s ORDER BY sno', (report_id,))
            complete_report['security'] = [dict(zip(['sno', 'security_device', 'location', 'status', 'remarks', 'checked_time'], row)) for row in cur.fetchall()]
            
            # Get telecom items
            cur.execute('SELECT sno, name, status, reason, remarks, checked_time FROM bod_telecom_items WHERE report_id = %s ORDER BY sno', (report_id,))
            complete_report['telecom'] = [dict(zip(['sno', 'name', 'status', 'reason', 'remarks', 'checked_time'], row)) for row in cur.fetchall()]
            
            # Get printer items
            cur.execute('SELECT sno, printer_name, status, reason, yesterday_reading, today_reading, remarks, checked_time FROM bod_printer_data WHERE report_id = %s ORDER BY sno', (report_id,))
            complete_report['printers'] = [dict(zip(['sno', 'printer_name', 'status', 'reason', 'yesterday_reading', 'today_reading', 'remarks', 'checked_time'], row)) for row in cur.fetchall()]
            
            # Get other items
            cur.execute('SELECT sno, item, status, reason, remarks, checked_time FROM bod_other_items WHERE report_id = %s ORDER BY sno', (report_id,))
            complete_report['others'] = [dict(zip(['sno', 'item', 'status', 'reason', 'remarks', 'checked_time'], row)) for row in cur.fetchall()]
            
            # Get antivirus items
            cur.execute('SELECT sno, system_name, antivirus_status, last_updated, remarks, checked_time FROM bod_antivirus_items WHERE report_id = %s ORDER BY sno', (report_id,))
            complete_report['antivirus'] = [dict(zip(['sno', 'system_name', 'antivirus_status', 'last_updated', 'remarks', 'checked_time'], row)) for row in cur.fetchall()]
            
            # Get common sharing items
            cur.execute('SELECT sno, folder_name, access_rights, status, remarks, checked_time FROM bod_sharing_items WHERE report_id = %s ORDER BY sno', (report_id,))
            complete_report['common_sharing'] = [dict(zip(['sno', 'folder_name', 'access_rights', 'status', 'remarks', 'checked_time'], row)) for row in cur.fetchall()]
            
            # Get tech room items
            cur.execute('SELECT sno, equipment, status, reason, remarks, checked_time FROM bod_techroom_items WHERE report_id = %s ORDER BY sno', (report_id,))
            complete_report['tech_room'] = [dict(zip(['sno', 'equipment', 'status', 'reason', 'remarks', 'checked_time'], row)) for row in cur.fetchall()]
            
            cur.close()
            conn.close()
            
            return jsonify({'success': True, 'report': complete_report})
        else:
            cur.close()
            conn.close()
            return jsonify({'success': False, 'error': 'No report found for this location'}), 404
        
    except Exception as e:
        cur.close()
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 400

@it_bp.route('/api/location-dropdown-data/<location>/<dropdown_type>', methods=['GET'])
@csrf.exempt
@admin_required
def get_location_dropdown_data(location, dropdown_type):
    """Get dropdown data for a specific location and dropdown type"""
    conn = get_db_connection(Curr_Proj_Name)
    cur = conn.cursor()
    
    try:
        # Convert location format (e.g., 'unit-3' to 'unit_3')
        table_location = location.replace('-', '_')
        table_name = f"{table_location}_bod_dropdown_data"
        
        cur.execute(f'''
            SELECT id, value 
            FROM {table_name} 
            WHERE dropdown_type = %s 
            ORDER BY id
        ''', (dropdown_type,))
        
        data = cur.fetchall()
        
        cur.close()
        conn.close()
        
        return jsonify({
            'success': True, 
            'data': data
        })
        
    except Exception as e:
        cur.close()
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 400

@it_bp.route('/api/location-dropdown-data/<location>/<dropdown_type>', methods=['POST'])
@csrf.exempt
@admin_required
def add_location_dropdown_data(location, dropdown_type):
    """Add new dropdown data for a specific location and dropdown type"""
    conn = get_db_connection(Curr_Proj_Name)
    cur = conn.cursor()
    
    try:
        data = request.get_json()
        value = data.get('value')
        
        if not value:
            return jsonify({'success': False, 'error': 'Value is required'}), 400
        
        # Convert location format (e.g., 'unit-3' to 'unit_3')
        table_location = location.replace('-', '_')
        table_name = f"{table_location}_bod_dropdown_data"
        
        # For internet options, add to both primary and secondary
        if dropdown_type in ['primary_internet', 'secondary_internet']:
            # Check if the value already exists in either dropdown
            cur.execute(f'''
                SELECT id FROM {table_name} 
                WHERE value = %s
            ''', (value,))
            
            existing_record = cur.fetchone()
            
            if existing_record:
                cur.close()
                conn.close()
                return jsonify({
                    'success': False, 
                    'error': f'"{value}" already exists in {location} internet dropdowns'
                }), 409
            
            # Add to both primary and secondary internet
            cur.execute(f'''
                INSERT INTO {table_name} (dropdown_type, value)
                VALUES (%s, %s)
            ''', ('primary_internet', value))
            
            cur.execute(f'''
                INSERT INTO {table_name} (dropdown_type, value)
                VALUES (%s, %s)
            ''', ('secondary_internet', value))
            
            conn.commit()
            
            cur.close()
            conn.close()
            
            return jsonify({
                'success': True, 
                'message': f'"{value}" added successfully to both Primary and Secondary Internet dropdowns for {location}'
            })
        else:
            # For other dropdown types, use original logic
            cur.execute(f'''
                SELECT id FROM {table_name} 
                WHERE dropdown_type = %s AND value = %s
            ''', (dropdown_type, value))
            
            existing_record = cur.fetchone()
            
            if existing_record:
                cur.close()
                conn.close()
                return jsonify({
                    'success': False, 
                    'error': f'"{value}" already exists in {location} {dropdown_type.replace("_", " ")} dropdown'
                }), 409
            
            # If value doesn't exist, insert it
            cur.execute(f'''
                INSERT INTO {table_name} (dropdown_type, value)
                VALUES (%s, %s)
            ''', (dropdown_type, value))
            
            conn.commit()
            
            cur.close()
            conn.close()
            
            return jsonify({
                'success': True, 
                'message': f'"{value}" added successfully to {location} {dropdown_type.replace("_", " ")} dropdown'
            })
        
    except Exception as e:
        conn.rollback()
        cur.close()
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 400

@it_bp.route('/api/location-dropdown-data/<location>/<dropdown_type>/<value>', methods=['DELETE'])
@csrf.exempt
@admin_required
def delete_location_dropdown_data(location, dropdown_type, value):
    """Delete dropdown data for a specific location, dropdown type, and value"""
    conn = get_db_connection(Curr_Proj_Name)
    cur = conn.cursor()
    
    try:
        # Convert location format (e.g., 'unit-3' to 'unit_3')
        table_location = location.replace('-', '_')
        table_name = f"{table_location}_bod_dropdown_data"
        
        # For internet options, delete from both primary and secondary
        if dropdown_type in ['primary_internet', 'secondary_internet']:
            # Check if the value exists in either dropdown
            cur.execute(f'''
                SELECT id FROM {table_name} 
                WHERE value = %s
            ''', (value,))
            
            existing_record = cur.fetchone()
            
            if not existing_record:
                cur.close()
                conn.close()
                return jsonify({
                    'success': False, 
                    'error': f'"{value}" not found in {location} internet dropdowns'
                }), 404
            
            # Delete the value from both primary and secondary internet
            cur.execute(f'''
                DELETE FROM {table_name} 
                WHERE value = %s
            ''', (value,))
            
            conn.commit()
            
            cur.close()
            conn.close()
            
            return jsonify({
                'success': True, 
                'message': f'"{value}" deleted successfully from both Primary and Secondary Internet dropdowns for {location}'
            })
        else:
            # For other dropdown types, use original logic
            cur.execute(f'''
                SELECT id FROM {table_name} 
                WHERE dropdown_type = %s AND value = %s
            ''', (dropdown_type, value))
            
            existing_record = cur.fetchone()
            
            if not existing_record:
                cur.close()
                conn.close()
                return jsonify({
                    'success': False, 
                    'error': f'"{value}" not found in {location} {dropdown_type.replace("_", " ")} dropdown'
                }), 404
            
            # Delete the value from the table
            cur.execute(f'''
                DELETE FROM {table_name} 
                WHERE dropdown_type = %s AND value = %s
            ''', (dropdown_type, value))
            
            conn.commit()
            
            cur.close()
            conn.close()
            
            return jsonify({
                'success': True, 
                'message': f'"{value}" deleted successfully from {location} {dropdown_type.replace("_", " ")} dropdown'
            })
        
    except Exception as e:
        conn.rollback()
        cur.close()
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/send-daily-report-email', methods=['POST'])
@csrf.exempt
@admin_required
def send_daily_report_email():
    """Send daily infrastructure status report email to all admins"""
    try:
        data = request.get_json()
        date = data.get('date')
        location = data.get('location')
        
        if not date or not location:
            return jsonify({'success': False, 'error': 'Date and location are required'}), 400
        
        # Get the report data
        conn = get_db_connection(Curr_Proj_Name)
        cur = conn.cursor()
        
        cur.execute('''
            SELECT * FROM saved_bod_reports 
            WHERE date = %s AND location = %s 
            ORDER BY submitted_time DESC
        ''', (date, location))
        
        reports = cur.fetchall()
        
        if not reports:
            cur.close()
            conn.close()
            return jsonify({'success': False, 'error': 'No report found for the specified date and location'}), 404
        
        # Get all admin users
        cur.execute('SELECT email, name FROM users WHERE role = "admin"')
        admin_users = cur.fetchall()
        
        if not admin_users:
            cur.close()
            conn.close()
            return jsonify({'success': False, 'error': 'No admin users found'}), 404
        
        # Generate email content
        email_content = generate_daily_report_email_content(reports, date, location)
        
        # Send email to all admins
        admin_emails = [user['email'] for user in admin_users]
        success = send_daily_report_email_to_admins(admin_emails, email_content, date, location)
        
        cur.close()
        conn.close()
        
        if success:
            return jsonify({'success': True, 'message': f'Report email sent to {len(admin_emails)} admin(s)'})
        else:
            return jsonify({'success': False, 'error': 'Failed to send email'}), 500
            
    except Exception as e:
        print(f"Error in send_daily_report_email: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@it_bp.route('/api/send-bod-report-email', methods=['POST'])
@csrf.exempt
@admin_required
def send_bod_report_email():
    """Send BOD report email to all admins"""
    try:
        data = request.get_json()
        date = data.get('date')
        location = data.get('location')
        name = data.get('name')
        
        if not date or not location:
            return jsonify({'success': False, 'error': 'Date and location are required'}), 400
        
        # Get the report data
        conn = get_db_connection(Curr_Proj_Name)
        cur = conn.cursor()
        
        cur.execute('''
            SELECT * FROM bod_reports_normalized 
            WHERE report_date = %s AND location = %s 
            ORDER BY submitted_time DESC
        ''', (date, location))
        
        reports = cur.fetchall()
        
        if not reports:
            cur.close()
            conn.close()
            return jsonify({'success': False, 'error': 'No report found for the specified date and location'}), 404
        
        # Fetch detailed section data for each report
        for report in reports:
            report_data = {}
            report_id = report['id']
            
            # Fetch network items
            cur.execute('SELECT * FROM bod_network_items WHERE report_id = %s ORDER BY sno', (report_id,))
            network_items = cur.fetchall()
            if network_items:
                report_data['network'] = []
                for item in network_items:
                    report_data['network'].append({
                        'sno': item['sno'],
                        'leased_line': item['leased_line'],
                        'link': item['link'],
                        'status': item['status'],
                        'reason': item['reason'],
                        'remarks': item['remarks'],
                        'checked_time': str(item['checked_time']) if item['checked_time'] else ''
                    })
            
            # Fetch server items
            cur.execute('SELECT * FROM bod_server_items WHERE report_id = %s ORDER BY sno', (report_id,))
            server_items = cur.fetchall()
            if server_items:
                report_data['server_connectivity'] = []
                for item in server_items:
                    report_data['server_connectivity'].append({
                        'sno': item['sno'],
                        'server_name': item['server_name'],
                        'status': item['status'],
                        'reason': item['reason'],
                        'remarks': item['remarks'],
                        'checked_time': str(item['checked_time']) if item['checked_time'] else ''
                    })
            
            # Fetch security items
            cur.execute('SELECT * FROM bod_security_items WHERE report_id = %s ORDER BY sno', (report_id,))
            security_items = cur.fetchall()
            if security_items:
                report_data['security'] = []
                for item in security_items:
                    report_data['security'].append({
                        'sno': item['sno'],
                        'security_device': item['security_device'],
                        'location': item['location'],
                        'status': item['status'],
                        'remarks': item['remarks'],
                        'checked_time': str(item['checked_time']) if item['checked_time'] else ''
                    })
            
            # Fetch antivirus items
            cur.execute('SELECT * FROM bod_antivirus_items WHERE report_id = %s ORDER BY sno', (report_id,))
            antivirus_items = cur.fetchall()
            if antivirus_items:
                report_data['antivirus'] = []
                for item in antivirus_items:
                    report_data['antivirus'].append({
                        'sno': item['sno'],
                        'system_name': item['system_name'],
                        'antivirus_status': item['antivirus_status'],
                        'last_updated': str(item['last_updated']) if item['last_updated'] else '',
                        'remarks': item['remarks'],
                        'checked_time': str(item['checked_time']) if item['checked_time'] else ''
                    })
            
            # Fetch sharing items
            cur.execute('SELECT * FROM bod_sharing_items WHERE report_id = %s ORDER BY sno', (report_id,))
            sharing_items = cur.fetchall()
            if sharing_items:
                report_data['common_sharing'] = []
                for item in sharing_items:
                    report_data['common_sharing'].append({
                        'sno': item['sno'],
                        'folder_name': item['folder_name'],
                        'access_rights': item['access_rights'],
                        'status': item['status'],
                        'remarks': item['remarks'],
                        'checked_time': str(item['checked_time']) if item['checked_time'] else ''
                    })
            
            # Fetch printer items
            cur.execute('SELECT * FROM bod_printer_data WHERE report_id = %s ORDER BY sno', (report_id,))
            printer_items = cur.fetchall()
            if printer_items:
                report_data['printers'] = []
                for item in printer_items:
                    report_data['printers'].append({
                        'sno': item['sno'],
                        'printer_name': item['printer_name'],
                        'status': item['status'],
                        'reason': item['reason'],
                        'yesterday_reading': item['yesterday_reading'],
                        'today_reading': item['today_reading'],
                        'remarks': item['remarks'],
                        'checked_time': str(item['checked_time']) if item['checked_time'] else ''
                    })
            
            # Fetch telecom items
            cur.execute('SELECT * FROM bod_telecom_items WHERE report_id = %s ORDER BY sno', (report_id,))
            telecom_items = cur.fetchall()
            if telecom_items:
                report_data['telecom'] = []
                for item in telecom_items:
                    report_data['telecom'].append({
                        'sno': item['sno'],
                        'name': item['name'],
                        'status': item['status'],
                        'reason': item['reason'],
                        'remarks': item['remarks'],
                        'checked_time': str(item['checked_time']) if item['checked_time'] else ''
                    })
            
            # Fetch tech room items
            cur.execute('SELECT * FROM bod_techroom_items WHERE report_id = %s ORDER BY sno', (report_id,))
            tech_room_items = cur.fetchall()
            if tech_room_items:
                report_data['tech_room'] = []
                for item in tech_room_items:
                    report_data['tech_room'].append({
                        'sno': item['sno'],
                        'equipment': item['equipment'],
                        'status': item['status'],
                        'reason': item['reason'],
                        'remarks': item['remarks'],
                        'checked_time': str(item['checked_time']) if item['checked_time'] else ''
                    })
            
            # Fetch others items
            cur.execute('SELECT * FROM bod_other_items WHERE report_id = %s ORDER BY sno', (report_id,))
            others_items = cur.fetchall()
            if others_items:
                report_data['others'] = []
                for item in others_items:
                    report_data['others'].append({
                        'sno': item['sno'],
                        'item': item['item'],
                        'status': item['status'],
                        'reason': item['reason'],
                        'remarks': item['remarks'],
                        'checked_time': str(item['checked_time']) if item['checked_time'] else ''
                    })
            
            # Store the report data in the report
            report['report_data'] = report_data
        
        # Get all admin users
        cur.execute('SELECT email, name FROM users WHERE role = "admin"')
        admin_users = cur.fetchall()
        
        if not admin_users:
            cur.close()
            conn.close()
            return jsonify({'success': False, 'error': 'No admin users found'}), 404
        
        # Generate email content
        email_content = generate_bod_report_email_content(reports, date, location, name)
        
        # Send email to all admins
        admin_emails = [user['email'] for user in admin_users]
        success = send_bod_report_email_to_admins(admin_emails, email_content, date, location)
        
        cur.close()
        conn.close()
        
        if success:
            return jsonify({'success': True, 'message': f'BOD Report email sent to {len(admin_emails)} admin(s)'})
        else:
            return jsonify({'success': False, 'error': 'Failed to send email'}), 500
            
    except Exception as e:
        print(f"Error in send_bod_report_email: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

def generate_daily_report_email_content(reports, date, location):
    """Generate HTML email content for daily infrastructure status report"""
    try:
        # Format date for display
        from datetime import datetime
        display_date = datetime.strptime(date, '%Y-%m-%d').strftime('%B %d, %Y')
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Daily Infrastructure Status Report - {location}</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f4f4f4; }}
                .container {{ max-width: 1000px; margin: 0 auto; background-color: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
                .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 8px; text-align: center; margin-bottom: 30px; }}
                .report-title {{ font-size: 24px; font-weight: bold; margin-bottom: 10px; }}
                .report-subtitle {{ font-size: 16px; opacity: 0.9; }}
                .report-info-box {{ background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%); border: 1px solid #dee2e6; border-radius: 8px; padding: 20px; margin: 20px 0; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
                .info-row {{ display: flex; align-items: center; margin-bottom: 15px; }}
                .info-label {{ font-weight: bold; color: #495057; min-width: 140px; display: flex; align-items: center; font-size: 14px; }}
                .info-value {{ color: #212529; margin-left: 15px; font-size: 14px; }}
                .info-icon {{ margin-right: 8px; font-size: 16px; }}
                .section {{ margin-bottom: 25px; border: 1px solid #ddd; border-radius: 8px; overflow: hidden; }}
                .section-header {{ background-color: #f8f9fa; padding: 15px; font-weight: bold; border-bottom: 1px solid #ddd; }}
                .section-content {{ padding: 20px; }}
                table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; font-size: 12px; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #f8f9fa; font-weight: bold; }}
                .status-working {{ color: #28a745; font-weight: bold; }}
                .status-not-working {{ color: #dc3545; font-weight: bold; }}
                .status-warning {{ color: #ffc107; font-weight: bold; }}
                .footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; text-align: center; color: #666; }}
                h4 {{ color: #333; margin-top: 20px; margin-bottom: 10px; border-bottom: 2px solid #667eea; padding-bottom: 5px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <div class="report-title">Daily Infrastructure Status Report</div>
                    <div class="report-subtitle">
                        Unit: {location} | Date: {display_date}
                    </div>
                </div>
        """
        
        # Add Report Information Header for the first report
        if reports:
            first_report = reports[0]
            # Format submitted time
            submitted_time = first_report['submitted_time']
            if submitted_time:
                try:
                    # Parse the submitted time and format it
                    from datetime import datetime
                    if isinstance(submitted_time, str):
                        # Try to parse the time string
                        if 'GMT' in submitted_time:
                            # Remove GMT and parse
                            time_str = submitted_time.replace(' GMT', '')
                            parsed_time = datetime.strptime(time_str, '%a, %d %b %Y %H:%M:%S')
                        else:
                            parsed_time = datetime.strptime(submitted_time, '%Y-%m-%d %H:%M:%S')
                        formatted_time = parsed_time.strftime('%H:%M:%S')
                    else:
                        formatted_time = str(submitted_time)
                except:
                    formatted_time = str(submitted_time)
            else:
                formatted_time = 'N/A'
            
            html_content += f"""
                <div class="report-info-box">
                    <div class="info-row">
                        <div class="info-label">
                            <span class="info-icon">📅</span>Date:
                        </div>
                        <div class="info-value">{display_date}</div>
                    </div>
                    <div class="info-row">
                        <div class="info-label">
                            <span class="info-icon">👤</span>Name:
                        </div>
                        <div class="info-value">{first_report.get('report_name', first_report.get('name', 'N/A')) or 'N/A'}</div>
                    </div>
                    <div class="info-row">
                        <div class="info-label">
                            <span class="info-icon">🏢</span>Location:
                        </div>
                        <div class="info-value">{location}</div>
                    </div>
                    <div class="info-row">
                        <div class="info-label">
                            <span class="info-icon">⏰</span>Submitted Time:
                        </div>
                        <div class="info-value">{formatted_time}</div>
                    </div>
                </div>
        """
        
        # Add each report's data
        for i, report in enumerate(reports):
            html_content += f"""
                <div class="section">
                    <div class="section-header">
                        Report {i+1} - Submitted by {report.get('report_name', report.get('name', 'Unknown'))} at {report['submitted_time']}
                    </div>
                    <div class="section-content">
            """
            
            if report['report_data']:
                try:
                    report_data = json.loads(report['report_data']) if isinstance(report['report_data'], str) else report['report_data']
                    
                    # Add Network section
                    if 'network' in report_data:
                        html_content += "<h4>Network</h4>"
                        html_content += "<table><tr><th>S.No</th><th>Leased Lines/DSL Links</th><th>Link</th><th>Status</th><th>Reason</th><th>Remarks</th><th>Checked Time</th></tr>"
                        for item in report_data['network']:
                            status_class = 'status-working' if item.get('status') == 'Working' else 'status-not-working' if item.get('status') == 'Not Working' else ''
                            html_content += f"<tr><td>{item.get('sno', '')}</td><td>{item.get('leased_line', '')}</td><td>{item.get('link', '')}</td><td class='{status_class}'>{item.get('status', '')}</td><td>{item.get('reason', '')}</td><td>{item.get('remarks', '')}</td><td>{item.get('checked_time', '')}</td></tr>"
                        html_content += "</table>"
                    
                    # Add Server Connectivity section
                    if 'server_connectivity' in report_data:
                        html_content += "<h4>Server Connectivity</h4>"
                        html_content += "<table><tr><th>S.No</th><th>Server Name</th><th>Status</th><th>Reason</th><th>Remarks</th><th>Checked Time</th></tr>"
                        for item in report_data['server_connectivity']:
                            status_class = 'status-working' if item.get('status') == 'Working' else 'status-not-working' if item.get('status') == 'Not Working' else ''
                            html_content += f"<tr><td>{item.get('sno', '')}</td><td>{item.get('server_name', '')}</td><td class='{status_class}'>{item.get('status', '')}</td><td>{item.get('reason', '')}</td><td>{item.get('remarks', '')}</td><td>{item.get('checked_time', '')}</td></tr>"
                        html_content += "</table>"
                    
                    # Add Antivirus Status section
                    if 'antivirus' in report_data:
                        html_content += "<h4>Antivirus Status For Renganathan T</h4>"
                        html_content += "<table><tr><th>S.No</th><th>System Name</th><th>Antivirus Status</th><th>Last Updated</th><th>Remarks</th><th>Checked Time</th></tr>"
                        for item in report_data['antivirus']:
                            html_content += f"<tr><td>{item.get('sno', '')}</td><td>{item.get('system_name', '')}</td><td>{item.get('antivirus_status', '')}</td><td>{item.get('last_updated', '')}</td><td>{item.get('remarks', '')}</td><td>{item.get('checked_time', '')}</td></tr>"
                        html_content += "</table>"
                    
                    # Add Common Sharing section
                    if 'common_sharing' in report_data:
                        html_content += "<h4>Common Sharing</h4>"
                        html_content += "<table><tr><th>S.No</th><th>Folder Name</th><th>Access Rights</th><th>Status</th><th>Remarks</th><th>Checked Time</th></tr>"
                        for item in report_data['common_sharing']:
                            html_content += f"<tr><td>{item.get('sno', '')}</td><td>{item.get('folder_name', '')}</td><td>{item.get('access_rights', '')}</td><td>{item.get('status', '')}</td><td>{item.get('remarks', '')}</td><td>{item.get('checked_time', '')}</td></tr>"
                        html_content += "</table>"
                    
                    # Add Security section
                    if 'security' in report_data:
                        html_content += "<h4>Security</h4>"
                        html_content += "<table><tr><th>S.No</th><th>Security Device</th><th>Location</th><th>Status</th><th>Remarks</th><th>Checked Time</th></tr>"
                        for item in report_data['security']:
                            html_content += f"<tr><td>{item.get('sno', '')}</td><td>{item.get('security_device', '')}</td><td>{item.get('location', '')}</td><td>{item.get('status', '')}</td><td>{item.get('remarks', '')}</td><td>{item.get('checked_time', '')}</td></tr>"
                        html_content += "</table>"
                    
                    # Add Telecommunication section
                    if 'telecom' in report_data:
                        html_content += "<h4>Telecommunication</h4>"
                        html_content += "<table><tr><th>S.No</th><th>Device Type</th><th>Location</th><th>Status</th><th>Reason</th><th>Remarks</th><th>Checked Time</th></tr>"
                        for item in report_data['telecom']:
                            html_content += f"<tr><td>{item.get('sno', '')}</td><td>{item.get('device_type', '')}</td><td>{item.get('location', '')}</td><td>{item.get('status', '')}</td><td>{item.get('reason', '')}</td><td>{item.get('remarks', '')}</td><td>{item.get('checked_time', '')}</td></tr>"
                        html_content += "</table>"
                    
                    # Add Technology Room section
                    if 'tech_room' in report_data:
                        html_content += "<h4>Technology Room</h4>"
                        html_content += "<table><tr><th>S.No</th><th>Equipment</th><th>Status</th><th>Reason</th><th>Remarks</th><th>Checked Time</th></tr>"
                        for item in report_data['tech_room']:
                            status_class = 'status-working' if item.get('status') == 'Working' else 'status-not-working' if item.get('status') == 'Not Working' else ''
                            html_content += f"<tr><td>{item.get('sno', '')}</td><td>{item.get('equipment', '')}</td><td class='{status_class}'>{item.get('status', '')}</td><td>{item.get('reason', '')}</td><td>{item.get('remarks', '')}</td><td>{item.get('checked_time', '')}</td></tr>"
                        html_content += "</table>"
                    
                    # Add Printers section
                    if 'printers' in report_data:
                        html_content += "<h4>Printers</h4>"
                        html_content += "<table><tr><th>S.No</th><th>Printer Name</th><th>Status</th><th>Reason</th><th>Yesterday Reading</th><th>Today Reading</th><th>Remarks</th><th>Checked Time</th></tr>"
                        for printer in report_data['printers']:
                            status_class = 'status-working' if printer.get('status') == 'Working' else 'status-not-working' if printer.get('status') == 'Not Working' else ''
                            html_content += f"<tr><td>{printer.get('sno', '')}</td><td>{printer.get('printer_name', '')}</td><td class='{status_class}'>{printer.get('status', '')}</td><td>{printer.get('reason', '')}</td><td>{printer.get('yesterday_reading', '')}</td><td>{printer.get('today_reading', '')}</td><td>{printer.get('remarks', '')}</td><td>{printer.get('checked_time', '')}</td></tr>"
                        html_content += "</table>"
                    
                    # Add Others section
                    if 'others' in report_data:
                        html_content += "<h4>Others</h4>"
                        html_content += "<table><tr><th>S.No</th><th>Item</th><th>Status</th><th>Reason</th><th>Remarks</th><th>Checked Time</th></tr>"
                        for item in report_data['others']:
                            status_class = 'status-working' if item.get('status') == 'Working' else 'status-not-working' if item.get('status') == 'Not Working' else ''
                            html_content += f"<tr><td>{item.get('sno', '')}</td><td>{item.get('item', '')}</td><td class='{status_class}'>{item.get('status', '')}</td><td>{item.get('reason', '')}</td><td>{item.get('remarks', '')}</td><td>{item.get('checked_time', '')}</td></tr>"
                        html_content += "</table>"
                        
                except json.JSONDecodeError:
                    html_content += "<p>Error parsing report data</p>"
            
            html_content += """
                    </div>
                </div>
            """
        
        html_content += f"""
                <div class="footer">
                    <p>This is an automated report generated by the CMS System.</p>
                    <p>Generated on: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return html_content
        
    except Exception as e:
        print(f"Error generating email content: {e}")
        return f"Error generating email content: {str(e)}"

def send_daily_report_email_to_admins(admin_emails, email_content, date, location):
    """Send daily report email to all admin users"""
    try:
        # Email configuration
        gmail_user = 'sapnoreply@violintec.com'
        gmail_password = 'VT$ofT@$2025'
        
        # Create message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f'Daily Infrastructure Status Report - {location} - {date}'
        msg['From'] = gmail_user
        msg['To'] = ', '.join(admin_emails)
        
        # Create HTML content
        html_part = MIMEText(email_content, 'html')
        msg.attach(html_part)
        
        # Send email
        print(f"🔧 Attempting to send email using: {gmail_user}")
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
                
                for email in admin_emails:
                    server.sendmail(gmail_user, email, msg.as_string())
                    print(f"🔧 Email sent to: {email}")
                
                server.quit()
                print(f"✅ Daily report email sent to {len(admin_emails)} admin(s) via {smtp_server}")
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
            print("❌ Failed to send email with all SMTP servers")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ Error sending daily report email: {e}")
        return False

def generate_bod_report_email_content(reports, date, location, name):
    """Generate HTML email content for BOD report"""
    try:
        # Format date for display
        from datetime import datetime
        display_date = datetime.strptime(date, '%Y-%m-%d').strftime('%B %d, %Y')
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>BOD Report Details - {location}</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f4f4f4; }}
                .container {{ max-width: 1000px; margin: 0 auto; background-color: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
                .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 8px; text-align: center; margin-bottom: 30px; }}
                .report-title {{ font-size: 24px; font-weight: bold; margin-bottom: 10px; }}
                .report-subtitle {{ font-size: 16px; opacity: 0.9; }}
                .report-info-box {{ background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%); border: 1px solid #dee2e6; border-radius: 8px; padding: 20px; margin: 20px 0; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
                .info-row {{ display: flex; align-items: center; margin-bottom: 15px; }}
                .info-label {{ font-weight: bold; color: #495057; min-width: 140px; display: flex; align-items: center; font-size: 14px; }}
                .info-value {{ color: #212529; margin-left: 15px; font-size: 14px; }}
                .info-icon {{ margin-right: 8px; font-size: 16px; }}
                .section {{ margin-bottom: 25px; border: 1px solid #ddd; border-radius: 8px; overflow: hidden; }}
                .section-header {{ background-color: #f8f9fa; padding: 15px; font-weight: bold; border-bottom: 1px solid #ddd; }}
                .section-content {{ padding: 20px; }}
                table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; font-size: 12px; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #f8f9fa; font-weight: bold; }}
                .status-working {{ color: #28a745; font-weight: bold; }}
                .status-not-working {{ color: #dc3545; font-weight: bold; }}
                .status-warning {{ color: #ffc107; font-weight: bold; }}
                .footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; text-align: center; color: #666; }}
                h4 {{ color: #333; margin-top: 20px; margin-bottom: 10px; border-bottom: 2px solid #667eea; padding-bottom: 5px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <div class="report-title">BOD Report Details</div>
                    <div class="report-subtitle">
                        Unit: {location} | Date: {display_date}
                    </div>
                </div>
        """
        
        # Add Report Information Header for the first report
        if reports:
            first_report = reports[0]
            # Format submitted time
            submitted_time = first_report['submitted_time']
            if submitted_time:
                try:
                    # Parse the submitted time and format it
                    from datetime import datetime
                    if isinstance(submitted_time, str):
                        # Try to parse the time string
                        if 'GMT' in submitted_time:
                            # Remove GMT and parse
                            time_str = submitted_time.replace(' GMT', '')
                            parsed_time = datetime.strptime(time_str, '%a, %d %b %Y %H:%M:%S')
                        else:
                            parsed_time = datetime.strptime(submitted_time, '%Y-%m-%d %H:%M:%S')
                        formatted_time = parsed_time.strftime('%H:%M:%S')
                    else:
                        formatted_time = str(submitted_time)
                except:
                    formatted_time = str(submitted_time)
            else:
                formatted_time = 'N/A'
            
            html_content += f"""
                <div class="report-info-box">
                    <div class="info-row">
                        <div class="info-label">
                            <span class="info-icon">📅</span>Date:
                        </div>
                        <div class="info-value">{display_date}</div>
                    </div>
                    <div class="info-row">
                        <div class="info-label">
                            <span class="info-icon">👤</span>Name:
                        </div>
                        <div class="info-value">{first_report.get('report_name', first_report.get('name', 'N/A')) or 'N/A'}</div>
                    </div>
                    <div class="info-row">
                        <div class="info-label">
                            <span class="info-icon">🏢</span>Location:
                        </div>
                        <div class="info-value">{location}</div>
                    </div>
                    <div class="info-row">
                        <div class="info-label">
                            <span class="info-icon">⏰</span>Submitted Time:
                        </div>
                        <div class="info-value">{formatted_time}</div>
                    </div>
                </div>
            """
        
        # Process each report
        for i, report in enumerate(reports):
            html_content += f"""
                <div class="section">
                    <div class="section-header">
                        Report {i + 1} - Submitted by {report.get('report_name', report.get('name', 'Unknown'))}
                        <small class="text-muted ms-2">({report['submitted_time']})</small>
                    </div>
                    <div class="section-content">
            """
            
            # Parse and display report data
            if report['report_data']:
                try:
                    report_data = json.loads(report['report_data']) if isinstance(report['report_data'], str) else report['report_data']
                    
                    # Add Network section
                    if 'network' in report_data:
                        html_content += "<h4>1. Network</h4>"
                        html_content += "<table><tr><th>S.No</th><th>Leased Lines/DSL Links</th><th>Link</th><th>Status</th><th>Reason</th><th>Remarks</th><th>Checked Time</th></tr>"
                        for item in report_data['network']:
                            status_class = 'status-working' if item.get('status') == 'Working' else 'status-not-working' if item.get('status') == 'Not Working' else ''
                            html_content += f"<tr><td>{item.get('sno', '')}</td><td>{item.get('leased_line', '')}</td><td>{item.get('link', '')}</td><td class='{status_class}'>{item.get('status', '')}</td><td>{item.get('reason', '')}</td><td>{item.get('remarks', '')}</td><td>{item.get('checked_time', '')}</td></tr>"
                        html_content += "</table>"
                    
                    # Add Server Connectivity section
                    if 'server_connectivity' in report_data:
                        html_content += "<h4>2. Server Connectivity</h4>"
                        html_content += "<table><tr><th>S.No</th><th>Server Name</th><th>Status</th><th>Reason</th><th>Remarks</th><th>Checked Time</th></tr>"
                        for item in report_data['server_connectivity']:
                            status_class = 'status-working' if item.get('status') == 'Working' else 'status-not-working' if item.get('status') == 'Not Working' else ''
                            html_content += f"<tr><td>{item.get('sno', '')}</td><td>{item.get('server_name', '')}</td><td class='{status_class}'>{item.get('status', '')}</td><td>{item.get('reason', '')}</td><td>{item.get('remarks', '')}</td><td>{item.get('checked_time', '')}</td></tr>"
                        html_content += "</table>"
                    
                    # Add Antivirus Status section
                    if 'antivirus' in report_data:
                        html_content += "<h4>3. Antivirus Status For Renganathan T</h4>"
                        html_content += "<table><tr><th>S.No</th><th>System Name</th><th>Antivirus Status</th><th>Last Updated</th><th>Remarks</th><th>Checked Time</th></tr>"
                        for item in report_data['antivirus']:
                            status_class = 'status-working' if item.get('antivirus_status') == 'Working' else 'status-not-working' if item.get('antivirus_status') == 'Not Working' else ''
                            html_content += f"<tr><td>{item.get('sno', '')}</td><td>{item.get('system_name', '')}</td><td class='{status_class}'>{item.get('antivirus_status', '')}</td><td>{item.get('last_updated', '')}</td><td>{item.get('remarks', '')}</td><td>{item.get('checked_time', '')}</td></tr>"
                        html_content += "</table>"
                    
                    # Add Common Sharing section
                    if 'common_sharing' in report_data:
                        html_content += "<h4>4. Common Sharing (Disk Check and Usage)</h4>"
                        html_content += "<table><tr><th>S.No</th><th>Folder Name</th><th>Access Rights</th><th>Status</th><th>Remarks</th><th>Checked Time</th></tr>"
                        for item in report_data['common_sharing']:
                            status_class = 'status-working' if item.get('status') == 'ok' else 'status-not-working' if item.get('status') == 'Not ok' else ''
                            html_content += f"<tr><td>{item.get('sno', '')}</td><td>{item.get('folder_name', '')}</td><td>{item.get('access_rights', '')}</td><td class='{status_class}'>{item.get('status', '')}</td><td>{item.get('remarks', '')}</td><td>{item.get('checked_time', '')}</td></tr>"
                        html_content += "</table>"
                    
                    # Add Security section
                    if 'security' in report_data:
                        html_content += "<h4>5. Security</h4>"
                        html_content += "<table><tr><th>S.No</th><th>Security Device</th><th>Location</th><th>Status</th><th>Remarks</th><th>Checked Time</th></tr>"
                        for item in report_data['security']:
                            status_class = 'status-working' if item.get('status') == 'Working' else 'status-not-working' if item.get('status') == 'Not Working' else ''
                            html_content += f"<tr><td>{item.get('sno', '')}</td><td>{item.get('security_device', '')}</td><td>{item.get('location', '')}</td><td class='{status_class}'>{item.get('status', '')}</td><td>{item.get('remarks', '')}</td><td>{item.get('checked_time', '')}</td></tr>"
                        html_content += "</table>"
                    
                    # Add Telecommunication section
                    if 'telecom' in report_data:
                        html_content += "<h4>6. Telecommunication</h4>"
                        html_content += "<table><tr><th>S.No</th><th>Name</th><th>Status</th><th>Reason</th><th>Remarks</th><th>Checked Time</th></tr>"
                        for item in report_data['telecom']:
                            status_class = 'status-working' if item.get('status') == 'Working' else 'status-not-working' if item.get('status') == 'Not Working' else ''
                            html_content += f"<tr><td>{item.get('sno', '')}</td><td>{item.get('name', '')}</td><td class='{status_class}'>{item.get('status', '')}</td><td>{item.get('reason', '')}</td><td>{item.get('remarks', '')}</td><td>{item.get('checked_time', '')}</td></tr>"
                        html_content += "</table>"
                    
                    # Add Technology Room section
                    if 'tech_room' in report_data:
                        html_content += "<h4>7. Technology Room (TV, Audio, Network)</h4>"
                        html_content += "<table><tr><th>S.No</th><th>Equipment</th><th>Status</th><th>Reason</th><th>Remarks</th><th>Checked Time</th></tr>"
                        for item in report_data['tech_room']:
                            status_class = 'status-working' if item.get('status') == 'Working' else 'status-not-working' if item.get('status') == 'Not Working' else ''
                            html_content += f"<tr><td>{item.get('sno', '')}</td><td>{item.get('equipment', '')}</td><td class='{status_class}'>{item.get('status', '')}</td><td>{item.get('reason', '')}</td><td>{item.get('remarks', '')}</td><td>{item.get('checked_time', '')}</td></tr>"
                        html_content += "</table>"
                    
                    # Add Printers section
                    if 'printers' in report_data:
                        html_content += "<h4>8. Printers</h4>"
                        html_content += "<table><tr><th>S.No</th><th>Printer Name</th><th>Status</th><th>Reason</th><th>Yesterday Reading</th><th>Today Reading</th><th>Remarks</th><th>Checked Time</th></tr>"
                        for printer in report_data['printers']:
                            status_class = 'status-working' if printer.get('status') == 'Working' else 'status-not-working' if printer.get('status') == 'Not Working' else ''
                            html_content += f"<tr><td>{printer.get('sno', '')}</td><td>{printer.get('printer_name', '')}</td><td class='{status_class}'>{printer.get('status', '')}</td><td>{printer.get('reason', '')}</td><td>{printer.get('yesterday_reading', '')}</td><td>{printer.get('today_reading', '')}</td><td>{printer.get('remarks', '')}</td><td>{printer.get('checked_time', '')}</td></tr>"
                        html_content += "</table>"
                    
                    # Add Others section
                    if 'others' in report_data:
                        html_content += "<h4>9. Others</h4>"
                        html_content += "<table><tr><th>S.No</th><th>Item</th><th>Status</th><th>Reason</th><th>Remarks</th><th>Checked Time</th></tr>"
                        for item in report_data['others']:
                            status_class = 'status-working' if item.get('status') == 'Working' else 'status-not-working' if item.get('status') == 'Not Working' else ''
                            html_content += f"<tr><td>{item.get('sno', '')}</td><td>{item.get('item', '')}</td><td class='{status_class}'>{item.get('status', '')}</td><td>{item.get('reason', '')}</td><td>{item.get('remarks', '')}</td><td>{item.get('checked_time', '')}</td></tr>"
                        html_content += "</table>"
                        
                except json.JSONDecodeError:
                    html_content += "<p>Error parsing report data</p>"
            
            html_content += """
                    </div>
                </div>
            """
        
        html_content += f"""
                <div class="footer">
                    <p>This is an automated BOD Report generated by the CMS System.</p>
                    <p>Generated on: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return html_content
        
    except Exception as e:
        print(f"Error generating BOD report email content: {e}")
        return f"Error generating BOD report email content: {str(e)}"

def send_bod_report_email_to_admins(admin_emails, email_content, date, location):
    """Send BOD report email to all admin users"""
    try:
        # Email configuration
        gmail_user = 'sapnoreply@violintec.com'
        gmail_password = 'VT$ofT@$2025'
        
        # Create message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f'BOD Report Details - {location} - {date}'
        msg['From'] = gmail_user
        msg['To'] = ', '.join(admin_emails)
        
        # Create HTML content
        html_part = MIMEText(email_content, 'html')
        msg.attach(html_part)
        
        # Send email
        print(f"🔧 Attempting to send BOD email using: {gmail_user}")
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
                
                for email in admin_emails:
                    server.sendmail(gmail_user, email, msg.as_string())
                    print(f"🔧 BOD email sent to: {email}")
                
                server.quit()
                print(f"✅ BOD report email sent to {len(admin_emails)} admin(s) via {smtp_server}")
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
            print("❌ Failed to send BOD email with all SMTP servers")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ Error sending BOD report email: {e}")
        return False

@app.route('/api/admin-menu-permissions/<int:user_id>', methods=['GET'])
@csrf.exempt
@login_required
def get_admin_menu_permissions(user_id):
    """Get menu permissions for a specific admin user"""
    try:
        # Check if current user is super admin or the user themselves
        if current_user.role != 'super_admin' and current_user.id != user_id:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
        conn = get_db_connection(Curr_Proj_Name)
        cur = conn.cursor()
        
        # Check if user exists and is admin
        cur.execute('SELECT id, name, role FROM users WHERE id = %s', (user_id,))
        user = cur.fetchone()
        
        if not user:
            cur.close()
            conn.close()
            return jsonify({'success': False, 'error': 'User not found'}), 404
        
        if user['role'] != 'admin':
            cur.close()
            conn.close()
            return jsonify({'success': False, 'error': 'User is not an admin'}), 400
        
        # Get current menu permissions
        cur.execute('''
            SELECT menu_item, is_allowed 
            FROM admin_menu_permissions 
            WHERE user_id = %s 
            ORDER BY menu_item
        ''', (user_id,))
        
        permissions = cur.fetchall()
        
        # Convert to dictionary format
        permissions_dict = {perm['menu_item']: perm['is_allowed'] for perm in permissions}
        
        cur.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'user': {
                'id': user['id'],
                'name': user['name'],
                'role': user['role']
            },
            'permissions': permissions_dict
        })
        
    except Exception as e:
        print(f"Error getting admin menu permissions: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@it_bp.route('/api/my-menu-permissions', methods=['GET'])
@csrf.exempt
@login_required
def get_my_menu_permissions():
    """Get current user's menu permissions"""
    try:
        if current_user.role != 'admin':
            return jsonify({'success': False, 'error': 'User is not an admin'}), 400
        
        conn = get_db_connection(Curr_Proj_Name)
        cur = conn.cursor()
        
        # Get current menu permissions
        cur.execute('''
            SELECT menu_item, is_allowed 
            FROM admin_menu_permissions 
            WHERE user_id = %s 
            ORDER BY menu_item
        ''', (current_user.id,))
        
        permissions = cur.fetchall()
        
        # Convert to dictionary format
        permissions_dict = {perm['menu_item']: perm['is_allowed'] for perm in permissions}
        
        cur.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'permissions': permissions_dict
        })
        
    except Exception as e:
        print(f"Error getting my menu permissions: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin-menu-permissions/<int:user_id>', methods=['POST'])
@csrf.exempt
@super_admin_required
def update_admin_menu_permissions(user_id):
    """Update menu permissions for a specific admin user"""
    try:
        data = request.get_json()
        permissions = data.get('permissions', {})
        
        conn = get_db_connection(Curr_Proj_Name)
        cur = conn.cursor()
        
        # Check if user exists and is admin
        cur.execute('SELECT id, name, role FROM users WHERE id = %s', (user_id,))
        user = cur.fetchone()
        
        if not user:
            cur.close()
            conn.close()
            return jsonify({'success': False, 'error': 'User not found'}), 404
        
        if user['role'] != 'admin':
            cur.close()
            conn.close()
            return jsonify({'success': False, 'error': 'User is not an admin'}), 400
        
        # Update permissions
        for menu_item, is_allowed in permissions.items():
            cur.execute('''
                INSERT INTO admin_menu_permissions (user_id, menu_item, is_allowed)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE is_allowed = VALUES(is_allowed)
            ''', (user_id, menu_item, is_allowed))
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': f'Menu permissions updated for {user["name"]}'
        })
        
    except Exception as e:
        print(f"Error updating admin menu permissions: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/available-menu-items', methods=['GET'])
@csrf.exempt
@super_admin_required
def get_available_menu_items():
    """Get list of all available menu items"""
    menu_items = [
        {'key': 'dashboard', 'name': 'Dashboard', 'icon': 'fas fa-tachometer-alt'},
        {'key': 'procurement', 'name': 'Procurement', 'icon': 'fas fa-shopping-cart'},
        {'key': 'asset_master', 'name': 'Asset Master', 'icon': 'fas fa-box'},
        {'key': 'assign_asset', 'name': 'Assign Asset', 'icon': 'fas fa-exchange-alt'},
        {'key': 'requests', 'name': 'Requests', 'icon': 'fas fa-list'},
        {'key': 'user_management', 'name': 'User Management', 'icon': 'fas fa-users'},
        {'key': 'bod_report', 'name': 'BOD Report', 'icon': 'fas fa-clipboard-check'},
        {'key': 'daily_infrastructure', 'name': 'Daily Infrastructure Status', 'icon': 'fas fa-calendar-check'}
    ]
    
    return jsonify({
        'success': True,
        'menu_items': menu_items
    })

@app.route('/api/test-email', methods=['POST'])
@csrf.exempt
@admin_required
def test_email():
    """Test endpoint for email configuration"""
    try:
        # Email configuration
        gmail_user = 'sapnoreply@violintec.com'
        gmail_password = 'VT$ofT@$2025'
        
        # Create a simple test message
        msg = MIMEMultipart('alternative')
        msg['From'] = gmail_user
        msg['To'] = gmail_user  # Send to self for testing
        msg['Subject'] = 'Test Email - CMS System'
        
        html_content = """
        <html>
        <body>
            <h2>Test Email</h2>
            <p>This is a test email to verify the email configuration is working.</p>
            <p>If you receive this email, the email system is properly configured.</p>
        </body>
        </html>
        """
        
        html_part = MIMEText(html_content, 'html')
        msg.attach(html_part)
        
        # Try multiple SMTP servers
        smtp_servers = [
            ('smtp.violintec.com', 587),
            ('smtp.office365.com', 587),
            ('smtp.gmail.com', 587),
            ('smtp-mail.outlook.com', 587)
        ]
        
        success = False
        working_server = None
        
        for smtp_server, port in smtp_servers:
            try:
                print(f"🔧 Testing SMTP server: {smtp_server}:{port}")
                server = smtplib.SMTP(smtp_server, port)
                server.starttls()
                print(f"🔧 TLS started successfully with {smtp_server}")
                server.login(gmail_user, gmail_password)
                print(f"🔧 Login successful with {smtp_server}")
                server.sendmail(gmail_user, gmail_user, msg.as_string())
                server.quit()
                print(f"✅ Test email sent successfully via {smtp_server}")
                success = True
                working_server = smtp_server
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
        
        if success:
            return jsonify({
                'success': True, 
                'message': f'Test email sent successfully via {working_server}',
                'working_server': working_server
            })
        else:
            return jsonify({
                'success': False, 
                'error': 'Failed to send test email with all SMTP servers'
            }), 500
            
    except Exception as e:
        print(f"Error in test_email: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/test-delete', methods=['POST'])
@csrf.exempt
def test_delete():
    """Test endpoint for debugging"""
    print("DEBUG: test_delete endpoint called")
    return jsonify({'success': True, 'message': 'Test endpoint working'})

@it_bp.route('/api/delete-bod-row', methods=['GET'])
@csrf.exempt
def test_delete_bod_row_get():
    """Test GET endpoint for debugging"""
    print("DEBUG: test_delete_bod_row_get endpoint called")
    return jsonify({'success': True, 'message': 'GET endpoint working'})

@it_bp.route('/api/delete-bod-row', methods=['POST'])
@csrf.exempt
def delete_bod_row():
    """Permanently delete a specific row from BOD report data"""
    print("DEBUG: delete_bod_row endpoint called")
    print(f"DEBUG: Request method: {request.method}")
    print(f"DEBUG: Request headers: {dict(request.headers)}")
    try:
        # Basic request validation
        print(f"DEBUG: Request URL: {request.url}")
        print(f"DEBUG: Request path: {request.path}")
        print(f"DEBUG: Request method: {request.method}")
        
        # Check if request has JSON data
        if not request.is_json:
            print("DEBUG: Request is not JSON")
            return jsonify({'success': False, 'error': 'Request must be JSON'}), 400
        data = request.get_json()
        if not data:
            print("DEBUG: No JSON data received")
            return jsonify({'success': False, 'error': 'No JSON data received'}), 400
        
        section_type = data.get('sectionType')
        location = data.get('location')
        row_data = data.get('rowData')
        row_index = data.get('rowIndex')
        
        # Debug: Print the received data
        print(f"DEBUG: Received data: {data}")
        print(f"DEBUG: section_type: {section_type}")
        print(f"DEBUG: location: {location}")
        print(f"DEBUG: row_data: {row_data}")
        print(f"DEBUG: row_index: {row_index}")
        
        if not all([section_type, location, row_data]):
            missing_params = []
            if not section_type: missing_params.append('sectionType')
            if not location: missing_params.append('location')
            if not row_data: missing_params.append('rowData')
            return jsonify({'success': False, 'error': f'Missing required parameters: {", ".join(missing_params)}'}), 400
        
        conn = get_db_connection(Curr_Proj_Name)
        cur = conn.cursor()
        
        # Get the latest report for this location (regardless of date)
        print(f"DEBUG: Searching for latest report with location: {location}")
        
        # First, let's check if there are any reports for this location
        cur.execute('''
            SELECT COUNT(*) as count
            FROM saved_bod_reports
            WHERE location = %s
        ''', (location,))
        
        count_result = cur.fetchone()
        print(f"DEBUG: Total reports for location {location}: {count_result['count'] if count_result else 0}")
        
        # Now get the latest report for this location (most recent date and time)
        cur.execute('''
            SELECT id, report_data, date, submitted_time
            FROM saved_bod_reports
            WHERE location = %s
            ORDER BY date DESC, submitted_time DESC
            LIMIT 1
        ''', (location,))
        
        result = cur.fetchone()
        
        print(f"DEBUG: Raw result: {result}")
        print(f"DEBUG: Result type: {type(result)}")
        print(f"DEBUG: Result keys: {result.keys() if result and isinstance(result, dict) else 'Not a dict'}")
        
        if not result:
            print(f"DEBUG: No report found for location: {location}")
            # Let's check what dates are available for this location
            cur.execute('''
                SELECT DISTINCT date, submitted_time
                FROM saved_bod_reports
                WHERE location = %s
                ORDER BY date DESC, submitted_time DESC
                LIMIT 5
            ''', (location,))
            
            available_dates = cur.fetchall()
            print(f"DEBUG: Available dates for location {location}: {[row['date'] for row in available_dates]}")
            
            cur.close()
            conn.close()
            return jsonify({'success': False, 'error': f'No report found for {location}. Available dates: {[row["date"] for row in available_dates]}'}), 404
        
        report_id = result['id']
        report_data = result['report_data']
        report_date = result['date']
        submitted_time = result['submitted_time']
        print(f"DEBUG: Found report with ID: {report_id}, date: {report_date}, submitted: {submitted_time}")
        
        # Debug: Print the report data type and content
        print(f"DEBUG: report_data type: {type(report_data)}")
        print(f"DEBUG: report_data content: {report_data[:200] if isinstance(report_data, str) else str(report_data)[:200]}")
        
        # Parse the report data
        try:
            if isinstance(report_data, str):
                if not report_data or report_data.strip() == '':
                    print("DEBUG: Empty report_data string")
                    cur.close()
                    conn.close()
                    return jsonify({'success': False, 'error': 'Report data is empty'}), 400
                parsed_data = json.loads(report_data)
            elif isinstance(report_data, dict):
                parsed_data = report_data
            elif report_data is None:
                print("DEBUG: report_data is None")
                cur.close()
                conn.close()
                return jsonify({'success': False, 'error': 'Report data is null'}), 400
            else:
                print(f"DEBUG: Unexpected report_data type: {type(report_data)}")
                cur.close()
                conn.close()
                return jsonify({'success': False, 'error': f'Unexpected report data type: {type(report_data)}'}), 400
        except json.JSONDecodeError as e:
            print(f"DEBUG: JSON decode error: {e}")
            print(f"DEBUG: Failed to parse: {report_data}")
            print(f"DEBUG: report_data length: {len(str(report_data)) if report_data else 0}")
            cur.close()
            conn.close()
            return jsonify({'success': False, 'error': f'Invalid report data format: {str(e)}'}), 400
        
        # Find and remove the specific row from the section
        section_key = section_type
        print(f"DEBUG: Looking for section: {section_key}")
        print(f"DEBUG: Available sections: {list(parsed_data.keys())}")
        
        if section_key in parsed_data and isinstance(parsed_data[section_key], list):
            print(f"DEBUG: Found {len(parsed_data[section_key])} rows in {section_key}")
            
            # Find the row to delete based on the row data
            rows_to_remove = []
            print(f"DEBUG: Row data received: {row_data}")
            
            for i, row in enumerate(parsed_data[section_key]):
                print(f"DEBUG: Checking row {i}: {row}")
                
                # Check if this row matches the one to delete
                row_sno = str(row.get('sno', '')).strip()
                row_leased_line = str(row.get('leased_line', row.get('server_name', row.get('system_name', '')))).strip()
                
                target_sno = str(row_data.get('sno', '')).strip()
                target_leased_line = str(row_data.get('leased_line', row_data.get('server_name', row_data.get('system_name', '')))).strip()
                
                print(f"DEBUG: Comparing - Row sno: '{row_sno}' vs Target sno: '{target_sno}'")
                print(f"DEBUG: Comparing - Row leased_line: '{row_leased_line}' vs Target leased_line: '{target_leased_line}'")
                
                # More flexible matching - check if both sno and leased_line match
                sno_match = row_sno == target_sno
                leased_line_match = row_leased_line == target_leased_line
                
                # Also check if the target leased_line contains the row leased_line (for partial matches)
                partial_match = target_leased_line in row_leased_line or row_leased_line in target_leased_line
                
                print(f"DEBUG: SNO match: {sno_match}, Leased line match: {leased_line_match}, Partial match: {partial_match}")
                
                if sno_match and (leased_line_match or partial_match):
                    print(f"DEBUG: ✅ MATCH FOUND! Removing row {i}")
                    rows_to_remove.append(i)
                else:
                    print(f"DEBUG: ❌ No match for row {i}")
            
            print(f"DEBUG: Total rows to remove: {len(rows_to_remove)}")
            
            if not rows_to_remove:
                print(f"DEBUG: ❌ No matching rows found for deletion!")
                print(f"DEBUG: Trying fallback deletion by row index: {row_index}")
                
                # Fallback: try to delete by row index if exact match fails
                if row_index is not None and 0 <= row_index < len(parsed_data[section_key]):
                    print(f"DEBUG: ✅ Fallback: Removing row at index {row_index}")
                    rows_to_remove = [row_index]
                else:
                    print(f"DEBUG: ❌ Row index {row_index} is invalid for {len(parsed_data[section_key])} rows")
                    cur.close()
                    conn.close()
                    return jsonify({'success': False, 'error': f'No matching row found for deletion'}), 404
            
            # Remove the rows (in reverse order to maintain indices)
            for i in reversed(rows_to_remove):
                del parsed_data[section_key][i]
            
            # Update the report data in the database
            updated_report_data = json.dumps(parsed_data)
            print(f"DEBUG: Updating database with {len(parsed_data[section_key])} rows in {section_key}")
            print(f"DEBUG: Updated JSON length: {len(updated_report_data)}")
            print(f"DEBUG: Report ID to update: {report_id}")
            
            try:
                cur.execute('''
                    UPDATE saved_bod_reports
                    SET report_data = %s
                    WHERE id = %s
                ''', (updated_report_data, report_id))
                
                rows_affected = cur.rowcount
                print(f"DEBUG: Database update affected {rows_affected} rows")
                
                if rows_affected == 0:
                    print(f"DEBUG: ❌ No rows were updated in database!")
                    cur.close()
                    conn.close()
                    return jsonify({'success': False, 'error': 'Database update failed - no rows affected'}), 500
                
                conn.commit()
                print(f"DEBUG: Database commit successful")
                
            except Exception as db_error:
                print(f"DEBUG: ❌ Database update error: {db_error}")
                conn.rollback()
                cur.close()
                conn.close()
                return jsonify({'success': False, 'error': f'Database update failed: {str(db_error)}'}), 500
            
            cur.close()
            conn.close()
            
            print(f"✅ Row deleted from {section_type} for location {location}")
            return jsonify({'success': True, 'message': f'Row deleted from {section_type}'})
            
        else:
            cur.close()
            conn.close()
            return jsonify({'success': False, 'error': f'Section {section_type} not found in report data'}), 404
        
    except Exception as e:
        print(f"❌ Error deleting BOD row: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@it_bp.route('/api/yesterday-printer-readings/<location>', methods=['GET'])
@csrf.exempt
@admin_required
def get_yesterday_printer_readings(location):
    """Get yesterday's printer readings for a specific location from bod_printer_data table"""
    conn = get_db_connection(Curr_Proj_Name)
    cur = conn.cursor()
    
    try:
        # Get yesterday's date - ONLY look for actual yesterday's data
        from datetime import datetime, timedelta
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        
        print(f"DEBUG: API called for location: {location}")
        print(f"DEBUG: Looking for yesterday's date: {yesterday}")
        
        # ONLY query for yesterday's data - no fallback to today's data
        cur.execute('''
            SELECT printer_name, today_reading, yesterday_reading 
            FROM bod_printer_data 
            WHERE unit = %s AND report_date = %s
            ORDER BY sno
        ''', (location, yesterday))
        
        results = cur.fetchall()
        
        if results:
            print(f"DEBUG: Found {len(results)} records for yesterday ({yesterday})")
        else:
            print(f"DEBUG: No data found for yesterday ({yesterday}) - will return empty yesterday_readings")
        
        print(f"DEBUG: Found {len(results)} records")
        
        for row in results:
            print(f"DEBUG: Printer: {row['printer_name']}, Today Reading: {row['today_reading']}, Yesterday Reading: {row['yesterday_reading']}")
        
        cur.close()
        conn.close()
        
        # Extract yesterday's readings (today_reading from yesterday becomes yesterday_reading for today)
        yesterday_readings = {}
        for row in results:
            printer_name = row['printer_name']
            today_reading = row['today_reading']
            yesterday_reading = row.get('yesterday_reading', '')
            
            # Check if printer_name exists and today_reading is not None or empty string
            if printer_name and today_reading is not None and str(today_reading).strip() != '':
                yesterday_readings[printer_name] = today_reading
                print(f"DEBUG: Adding to yesterday_readings: '{printer_name}' = '{today_reading}'")
            elif printer_name and yesterday_reading is not None and str(yesterday_reading).strip() != '':
                # Fallback: use yesterday_reading if today_reading is empty
                yesterday_readings[printer_name] = yesterday_reading
                print(f"DEBUG: Using fallback yesterday_reading for '{printer_name}' = '{yesterday_reading}'")
            else:
                print(f"DEBUG: Skipping printer '{printer_name}' - both today_reading and yesterday_reading are empty")
        
        print(f"DEBUG: Final yesterday_readings: {yesterday_readings}")
        
        # If no yesterday readings found, try to get the most recent data for each printer
        if not yesterday_readings:
            print(f"DEBUG: No yesterday readings found, trying to get most recent data for each printer")
            # Reconnect to database since we closed it earlier
            conn = get_db_connection(Curr_Proj_Name)
            cur = conn.cursor()
            
            cur.execute('''
                SELECT printer_name, today_reading, yesterday_reading, report_date
                FROM bod_printer_data 
                WHERE unit = %s AND report_date < %s
                ORDER BY report_date DESC, sno
            ''', (location, yesterday))
            
            recent_results = cur.fetchall()
            if recent_results:
                print(f"DEBUG: Found {len(recent_results)} recent records")
                # Group by printer_name and take the most recent
                printer_data = {}
                for row in recent_results:
                    printer_name = row['printer_name']
                    if printer_name not in printer_data:
                        printer_data[printer_name] = row
                
                for printer_name, row in printer_data.items():
                    today_reading = row['today_reading']
                    yesterday_reading = row['yesterday_reading']
                    
                    if today_reading is not None and str(today_reading).strip() != '':
                        yesterday_readings[printer_name] = today_reading
                        print(f"DEBUG: Using recent today_reading for '{printer_name}' = '{today_reading}' (from {row['report_date']})")
                    elif yesterday_reading is not None and str(yesterday_reading).strip() != '':
                        yesterday_readings[printer_name] = yesterday_reading
                        print(f"DEBUG: Using recent yesterday_reading for '{printer_name}' = '{yesterday_reading}' (from {row['report_date']})")
                
                print(f"DEBUG: Final yesterday_readings after fallback: {yesterday_readings}")
            
            cur.close()
            conn.close()
        
        return jsonify({
            'success': True, 
            'yesterday_readings': yesterday_readings,
            'date': yesterday
        })
        
    except Exception as e:
        print(f"DEBUG: Error in get_yesterday_printer_readings: {str(e)}")
        cur.close()
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 400

def create_location_dropdown_tables():
    """Create individual tables for each location's dropdown data"""
    conn = get_db_connection(Curr_Proj_Name)
    cur = conn.cursor()
    
    try:
        # Define location-specific dropdown data
        location_data = {
            'unit_1': {
                'primary_internet': ['Airtel : No IP', 'BSNL'],
                'secondary_internet': ['Airtel : No IP', 'BSNL']
            },
            'unit_2': {
                'primary_internet': ['DSL : No IP', 'BSNL'],
                'secondary_internet': ['DSL : No IP', 'BSNL']
            },
            'unit_3': {
                'primary_internet': ['DSL Airtel - 136.185.18.128', 'Spectra LL - 119.82.116.220', 'TATA LL - 14.194.137.58'],
                'secondary_internet': ['DSL Airtel - 136.185.18.128', 'Spectra LL - 119.82.116.220', 'TATA LL - 14.194.137.58']
            },
            'unit_4': {
                'primary_internet': ['DSL Airtel1 300Mbs - 136.185.18.111', 'DSL Airtel2 1Gbps - 136.185.18.113', 'Spectra LL - 180.151.69.190', 'Tata LL - 14.96.14.26'],
                'secondary_internet': ['DSL Airtel1 300Mbs - 136.185.18.111', 'DSL Airtel2 1Gbps - 136.185.18.113', 'Spectra LL - 180.151.69.190', 'Tata LL - 14.96.14.26']
            },
            'unit_5': {
                'primary_internet': ['Airtel DSL - 203.101.41.185', 'Airtel LL - 122.186.163.10', 'Tata LL - 14.96.14.26'],
                'secondary_internet': ['Airtel DSL - 203.101.41.185', 'Airtel LL - 122.186.163.10', 'Tata LL - 14.96.14.26']
            },
            'GSS': {
                'primary_internet': ['Spectra LL - 180.151.66.70', 'Tata LL - 14.96.218.30'],
                'secondary_internet': ['Spectra LL - 180.151.66.70', 'Tata LL - 14.96.218.30']
            }
        }
        
        # Create tables for each location
        for location, data in location_data.items():
            # Create table for this location
            table_name = f"{location}_bod_dropdown_data"
            cur.execute(f'''
                CREATE TABLE IF NOT EXISTS {table_name} (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    dropdown_type ENUM('primary_internet', 'secondary_internet') NOT NULL,
                    value VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    UNIQUE KEY unique_dropdown_value (dropdown_type, value)
                )
            ''')
            
            # Insert default data for this location
            for dropdown_type, values in data.items():
                for value in values:
                    try:
                        cur.execute(f'''
                            INSERT IGNORE INTO {table_name} (dropdown_type, value)
                            VALUES (%s, %s)
                        ''', (dropdown_type, value))
                    except Exception as e:
                        print(f"Error inserting {value} into {table_name}: {e}")
        
        conn.commit()
        print("Location dropdown tables created successfully")
        
    except Exception as e:
        print(f"Error creating location dropdown tables: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

def create_bod_printer_data_table():
    """Create dedicated table to store Printers section rows per unit/date."""
    conn = get_db_connection(Curr_Proj_Name)
    cur = conn.cursor()
    try:
        cur.execute('''
            CREATE TABLE IF NOT EXISTS bod_printer_data (
                id INT AUTO_INCREMENT PRIMARY KEY,
                report_date DATE NOT NULL,
                unit VARCHAR(50) NOT NULL,
                sno INT NOT NULL,
                printer_name VARCHAR(255) NOT NULL,
                status VARCHAR(50) NULL,
                reason VARCHAR(255) NULL,
                yesterday_reading VARCHAR(50) NULL,
                today_reading VARCHAR(50) NULL,
                remarks VARCHAR(255) NULL,
                checked_time VARCHAR(20) NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_bod_prn_date_unit (report_date, unit),
                UNIQUE KEY uq_bod_prn_unit_date_sno (unit, report_date, sno, printer_name)
            )
        ''')
        conn.commit()
        print('bod_printer_data table ensured')
    except Exception as e:
        print(f'Error creating bod_printer_data: {e}')
        conn.rollback()
    finally:
        cur.close()
        conn.close()

def create_normalized_bod_tables():
    """Create normalized BOD report tables"""
    conn = get_db_connection(Curr_Proj_Name)
    cur = conn.cursor()
    
    try:
        # Main BOD reports table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS bod_reports_normalized (
                id INT PRIMARY KEY AUTO_INCREMENT,
                report_name VARCHAR(255),
                report_date DATE,
                location VARCHAR(50),
                secondary_internet VARCHAR(255),
                submitted_time DATETIME,
                submitted_by INT,
                FOREIGN KEY (submitted_by) REFERENCES users(id)
            )
        ''')
        
        # Network items table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS bod_network_items (
                id INT PRIMARY KEY AUTO_INCREMENT,
                report_id INT,
                sno INT,
                leased_line VARCHAR(255),
                link VARCHAR(50),
                status VARCHAR(50),
                reason TEXT,
                remarks TEXT,
                checked_time TIME,
                FOREIGN KEY (report_id) REFERENCES bod_reports_normalized(id) ON DELETE CASCADE
            )
        ''')
        
        # Server connectivity items table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS bod_server_items (
                id INT PRIMARY KEY AUTO_INCREMENT,
                report_id INT,
                sno INT,
                server_name VARCHAR(255),
                status VARCHAR(50),
                reason TEXT,
                remarks TEXT,
                checked_time TIME,
                FOREIGN KEY (report_id) REFERENCES bod_reports_normalized(id) ON DELETE CASCADE
            )
        ''')
        
        # Security devices table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS bod_security_items (
                id INT PRIMARY KEY AUTO_INCREMENT,
                report_id INT,
                sno INT,
                security_device VARCHAR(255),
                location VARCHAR(50),
                status VARCHAR(50),
                remarks TEXT,
                checked_time TIME,
                FOREIGN KEY (report_id) REFERENCES bod_reports_normalized(id) ON DELETE CASCADE
            )
        ''')
        
        # Telecom items table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS bod_telecom_items (
                id INT PRIMARY KEY AUTO_INCREMENT,
                report_id INT,
                sno INT,
                name VARCHAR(255),
                status VARCHAR(50),
                reason TEXT,
                remarks TEXT,
                checked_time TIME,
                FOREIGN KEY (report_id) REFERENCES bod_reports_normalized(id) ON DELETE CASCADE
            )
        ''')
        
        # Other items table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS bod_other_items (
                id INT PRIMARY KEY AUTO_INCREMENT,
                report_id INT,
                sno INT,
                item VARCHAR(255),
                status VARCHAR(50),
                reason TEXT,
                remarks TEXT,
                checked_time TIME,
                FOREIGN KEY (report_id) REFERENCES bod_reports_normalized(id) ON DELETE CASCADE
            )
        ''')
        
        # Antivirus items table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS bod_antivirus_items (
                id INT PRIMARY KEY AUTO_INCREMENT,
                report_id INT,
                sno INT,
                system_name VARCHAR(255),
                antivirus_status VARCHAR(50),
                last_updated VARCHAR(100),
                remarks TEXT,
                checked_time TIME,
                FOREIGN KEY (report_id) REFERENCES bod_reports_normalized(id) ON DELETE CASCADE
            )
        ''')
        
        # Common sharing items table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS bod_sharing_items (
                id INT PRIMARY KEY AUTO_INCREMENT,
                report_id INT,
                sno INT,
                folder_name VARCHAR(255),
                access_rights TEXT,
                status VARCHAR(50),
                remarks TEXT,
                checked_time TIME,
                FOREIGN KEY (report_id) REFERENCES bod_reports_normalized(id) ON DELETE CASCADE
            )
        ''')
        
        # Tech room items table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS bod_techroom_items (
                id INT PRIMARY KEY AUTO_INCREMENT,
                report_id INT,
                sno INT,
                equipment VARCHAR(255),
                status VARCHAR(50),
                reason TEXT,
                remarks TEXT,
                checked_time TIME,
                FOREIGN KEY (report_id) REFERENCES bod_reports_normalized(id) ON DELETE CASCADE
            )
        ''')
        
        # Update existing bod_printer_data table to link with normalized reports
        try:
            cur.execute('''
                ALTER TABLE bod_printer_data 
                ADD COLUMN report_id INT
            ''')
        except:
            pass  # Column might already exist
            
        try:
            cur.execute('''
                ALTER TABLE bod_printer_data 
                ADD CONSTRAINT fk_printer_report 
                FOREIGN KEY (report_id) REFERENCES bod_reports_normalized(id) ON DELETE CASCADE
            ''')
        except:
            pass  # Constraint might already exist
        
        conn.commit()
        print("Normalized BOD tables created successfully")
        
    except Exception as e:
        print(f"Error creating normalized BOD tables: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

def create_bod_name_table():
    """Create BOD_Name table with BOD_Name_Data column"""
    conn = get_db_connection(Curr_Proj_Name)
    cur = conn.cursor()
    
    try:
        cur.execute('''
            CREATE TABLE IF NOT EXISTS BOD_Name (
                id INT PRIMARY KEY AUTO_INCREMENT,
                BOD_Name_Data VARCHAR(255) NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Insert sample BOD names
        sample_names = [
            'Renganathan T',
            'IT Manager',
            'System Administrator',
            'Network Engineer',
            'Support Team'
        ]
        
        for name in sample_names:
            try:
                cur.execute('INSERT IGNORE INTO BOD_Name (BOD_Name_Data) VALUES (%s)', (name,))
            except Exception as e:
                print(f"Warning: Could not insert sample BOD name {name}: {e}")
        
        conn.commit()
        print("BOD_Name table created successfully with sample data")
        return True
    except Exception as e:
        conn.rollback()
        print(f"Error creating BOD_Name table: {e}")
        return False
    finally:
        cur.close()
        conn.close()

def create_primary_internet_bod_table():
    """Create Primary_Internet_BOD table with Name and Location columns"""
    conn = get_db_connection(Curr_Proj_Name)
    cur = conn.cursor()
    
    try:
        cur.execute('''
            CREATE TABLE IF NOT EXISTS Primary_Internet_BOD (
                id INT PRIMARY KEY AUTO_INCREMENT,
                Name VARCHAR(255) NOT NULL,
                Location VARCHAR(50) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY unique_name_location (Name, Location)
            )
        ''')
        
        # Insert sample data for each location
        sample_data = [
            ('Airtel : No IP', 'unit-1'),
            ('BSNL', 'unit-1'),
            ('DSL : No IP', 'unit-2'),
            ('BSNL', 'unit-2'),
            ('DSL Airtel - 136.185.18.128', 'unit-3'),
            ('Spectra LL - 119.82.116.220', 'unit-3'),
            ('TATA LL - 14.194.137.58', 'unit-3'),
            ('DSL Airtel1 300Mbs - 136.185.18.111', 'unit-4'),
            ('DSL Airtel2 1Gbps - 136.185.18.113', 'unit-4'),
            ('Spectra LL - 180.151.69.190', 'unit-4'),
            ('Tata LL - 14.96.14.26', 'unit-4'),
            ('Spectra LL - 180.151.66.70', 'unit-5'),
            ('Tata LL - 14.96.218.30', 'unit-5'),
            ('Spectra LL - 180.151.66.70', 'GSS'),
            ('Tata LL - 14.96.218.30', 'GSS')
        ]
        
        for name, location in sample_data:
            try:
                cur.execute('INSERT IGNORE INTO Primary_Internet_BOD (Name, Location) VALUES (%s, %s)', (name, location))
            except Exception as e:
                print(f"Warning: Could not insert sample data for {name} at {location}: {e}")
        
        conn.commit()
        print("Primary_Internet_BOD table created successfully with sample data")
        return True
    except Exception as e:
        conn.rollback()
        print(f"Error creating Primary_Internet_BOD table: {e}")
        return False
    finally:
        cur.close()
        conn.close()

# Register all blueprints
app.register_blueprint(it_bp)
app.register_blueprint(procurement_bp)

if __name__ == '__main__':
    # Create location dropdown tables
    create_location_dropdown_tables()
    # Ensure Printers detail table exists
    create_bod_printer_data_table()
    # Create normalized BOD tables
    create_normalized_bod_tables()
    # Create BOD Name table
    create_bod_name_table()
    # Create Primary Internet BOD table
    create_primary_internet_bod_table()
    app.run(host='0.0.0.0', port=5000, debug=True)