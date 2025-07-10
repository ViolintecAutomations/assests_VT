from flask import Flask, render_template, redirect, url_for, request, flash, abort, send_from_directory, Response, jsonify
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_bootstrap import Bootstrap
from flask_wtf.csrf import CSRFProtect, CSRFError
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, DateField, SelectField, FileField
from wtforms.validators import DataRequired, Email
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
import os
from functools import wraps
import datetime
import csv
import pymysql

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = 'Violin@12'
app.config['MYSQL_DB'] = 'CMS'
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'

# --- File Upload Config ---
UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads')
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'doc', 'docx'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

login_manager = LoginManager(app)
login_manager.login_view = 'login'
Bootstrap(app)
CSRFProtect(app)

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('Admin access required.', 'danger')
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

class AssetForm(FlaskForm):
    serial_number = StringField('Serial Number', validators=[DataRequired()])
    brand = StringField('Brand', validators=[DataRequired()])
    model = StringField('Model', validators=[DataRequired()])
    purchase_date = DateField('Purchase Date', format='%Y-%m-%d')
    warranty_expiry = DateField('Warranty Expiry', format='%Y-%m-%d')
    asset_type = SelectField('Asset Type', choices=['Laptop', 'Mouse', 'System', 'Keyboard', 'Others'], validators=[DataRequired()])
    submit = SubmitField('Save')

class AssignAssetForm(FlaskForm):
    asset_id = SelectField('Asset', coerce=int, validators=[DataRequired()])
    user_id = SelectField('User', coerce=int, validators=[DataRequired()])
    submit = SubmitField('Assign')

# --- WTForm for Document Upload ---
class DocumentUploadForm(FlaskForm):
    asset = SelectField('Asset', coerce=int, validators=[DataRequired()])
    doc_type = SelectField('Document Type', choices=[('GRN', 'GRN'), ('PO', 'PO'), ('Invoice', 'Invoice'), ('DC', 'DC')], validators=[DataRequired()])
    file = FileField('File', validators=[DataRequired()])
    submit = SubmitField('Upload')

class UserRequestForm(FlaskForm):
    asset_type = StringField('Asset Type', validators=[DataRequired()])
    request_type = SelectField('Request Type', choices=[('new', 'New'), ('return', 'Return'), ('replacement', 'Replacement')], validators=[DataRequired()])
    details = StringField('Details')
    submit = SubmitField('Submit Request')

class UserForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password')
    role = SelectField('Role', choices=[('admin', 'Admin'), ('user', 'User')], validators=[DataRequired()])
    submit = SubmitField('Save')

# --- Asset Types ---
ASSET_TYPES = ['Laptop', 'Mouse', 'Keyboard', 'System', 'Others']

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
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT asset_type, COUNT(*) as count FROM assets GROUP BY asset_type')
    db_counts = {row['asset_type']: row['count'] for row in cur.fetchall()}
    asset_counts = []
    for t in ASSET_TYPES:
        asset_counts.append({'asset_type': t, 'count': db_counts.get(t, 0)})
    cur.close()
    conn.close()
    return render_template('dashboard.html', asset_counts=asset_counts)

@app.route('/assets', methods=['GET', 'POST'])
@login_required
@admin_required
def assets():
    form = AssetForm()
    conn = get_db_connection()
    cur = conn.cursor()
    if form.validate_on_submit():
        serial_number = form.serial_number.data
        brand = form.brand.data
        model = form.model.data
        purchase_date = form.purchase_date.data
        warranty_expiry = form.warranty_expiry.data
        asset_type = form.asset_type.data
        asset_id = request.form.get('asset_id')
        # Check for duplicate serial number (for add or edit)
        if asset_id:
            cur.execute('SELECT id FROM assets WHERE serial_number = %s AND id != %s', (serial_number, asset_id))
        else:
            cur.execute('SELECT id FROM assets WHERE serial_number = %s', (serial_number,))
        existing = cur.fetchone()
        if existing:
            flash('Serial number already exists. Please use a unique serial number.', 'danger')
            return redirect(url_for('assets'))
        try:
            if asset_id:
                cur.execute('UPDATE assets SET serial_number=%s, brand=%s, model=%s, purchase_date=%s, warranty_expiry=%s, asset_type=%s WHERE id=%s',
                            (serial_number, brand, model, purchase_date, warranty_expiry, asset_type, asset_id))
                flash('Asset updated successfully.', 'success')
            else:
                cur.execute('INSERT INTO assets (serial_number, brand, model, purchase_date, warranty_expiry, asset_type) VALUES (%s, %s, %s, %s, %s, %s)',
                            (serial_number, brand, model, purchase_date, warranty_expiry, asset_type))
                flash('Asset added successfully.', 'success')
            conn.commit()
        except Exception as e:
            flash('Error saving asset: {}'.format(str(e)), 'danger')
            conn.rollback()
        return redirect(url_for('assets'))
    cur.execute('SELECT * FROM assets ORDER BY id DESC')
    assets_list = cur.fetchall()
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
    form = AssetForm(data=asset)
    if form.validate_on_submit():
        cur.execute('UPDATE assets SET serial_number=%s, brand=%s, model=%s, purchase_date=%s, warranty_expiry=%s, asset_type=%s WHERE id=%s',
                    (form.serial_number.data, form.brand.data, form.model.data, form.purchase_date.data, form.warranty_expiry.data, form.asset_type.data, asset_id))
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
    print('[DEBUG] Delete route hit for asset_id:', asset_id)
    print('[DEBUG] request.form:', request.form)
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
def assign():
    if current_user.role != 'admin':
        return abort(403)
    conn = get_db_connection()
    cur = conn.cursor()
    # Get available assets
    cur.execute("SELECT id, serial_number, brand, model, asset_type FROM assets WHERE status = 'available'")
    assets = cur.fetchall()
    asset_choices = [(a['id'], f"{a['serial_number']} ({a['asset_type']}, {a['brand']} {a['model']})") for a in assets]
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
            cur.execute('INSERT INTO assignments (asset_id, user_id, assigned_date) VALUES (%s, %s, NOW())', (form.asset_id.data, form.user_id.data))
            cur.execute('UPDATE assets SET status = %s WHERE id = %s', ('assigned', form.asset_id.data))
            conn.commit()
            log_audit(current_user.id, 'Asset Assigned', f"Asset {selected_asset['serial_number']} assigned to {selected_user['name']}")
            flash('Asset assigned successfully!', 'success')
            return redirect(url_for('assign'))
        else:
            flash('Invalid asset or user selected.', 'danger')
    # Assignment history
    cur.execute('''SELECT a.id, assets.serial_number, assets.brand, assets.model, users.name, users.email, a.assigned_at, a.returned_at FROM assignments a
                   JOIN assets ON a.asset_id = assets.id
                   JOIN users ON a.user_id = users.id
                   ORDER BY a.assigned_at DESC''')
    assignments = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('assign.html', form=form, assignments=assignments)

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

@app.route('/upload', methods=['GET', 'POST'])
@login_required
@admin_required
def upload_document():
    # Fetch assets for dropdown
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT id, serial_number, brand, model FROM assets')
    assets = cur.fetchall()
    cur.close()
    conn.close()
    form = DocumentUploadForm()
    form.asset.choices = [(a['id'], f"{a['serial_number']} {a['brand']} {a['model']}") for a in assets]

    if form.validate_on_submit():
        file = form.file.data
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute('INSERT INTO documents (asset_id, doc_type, filename, uploaded_by) VALUES (%s, %s, %s, %s)',
                        (form.asset.data, form.doc_type.data, filename, current_user.id))
            conn.commit()
            log_audit(current_user.id, 'Document Uploaded', f'Document uploaded for asset {assets[form.asset.data - 1]["serial_number"]}')
            cur.close()
            conn.close()
            flash('Document uploaded!', 'success')
            return redirect(url_for('upload_document'))

    # List uploaded documents
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''SELECT d.id, d.doc_type, d.filename, d.uploaded_at, a.serial_number, a.brand, a.model
                   FROM documents d JOIN assets a ON d.asset_id = a.id
                   ORDER BY d.uploaded_at DESC''')
    docs = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('upload.html', form=form, documents=docs)

@app.route('/uploads/<filename>')
@login_required
@admin_required
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/requests', methods=['GET', 'POST'])
@login_required
@admin_required
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
@admin_required
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
    cur.execute('''SELECT m.id, a.serial_number, a.brand, a.model, m.issue_details, m.status, m.reported_at, m.resolved_at
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
    cur.execute('DELETE FROM users WHERE id = %s', (user_id,))
    conn.commit()
    cur.close()
    conn.close()
    log_audit(current_user.id, 'User Deleted', f'User {user_id} deleted')
    flash('User deleted!', 'info')
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
    types = ['Laptop', 'Mouse', 'Keyboard', 'System', 'Others']
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

# Utility function to log audit events
def log_audit(user_id, action, details):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('INSERT INTO audit_logs (user_id, action, details, created_at) VALUES (%s, %s, %s, %s)',
                (user_id, action, details, datetime.datetime.now()))
    conn.commit()
    cur.close()
    conn.close()

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

if __name__ == '__main__':
    app.run(debug=True) 