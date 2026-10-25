import os, sqlite3, uuid, secrets, hmac
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, flash, session, abort, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from classifier import classify_complaint, suggested_worker
from database import init_db, DB_PATH

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / 'static' / 'uploads'
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_IMAGES = {'png', 'jpg', 'jpeg', 'webp'}
ALLOWED_AUDIO = {'wav', 'mp3', 'm4a', 'ogg', 'webm'}
ALLOWED_EVIDENCE = {'png', 'jpg', 'jpeg', 'webp'}
STATUSES = ['Submitted', 'Assigned', 'In Progress', 'Pending Verification', 'Resolved', 'Rejected']
PRIORITIES = ['High', 'Medium', 'Normal']

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('DI04_SECRET_KEY', 'dev-only-change-this-secret-before-deployment')
app.config['MAX_CONTENT_LENGTH'] = 12 * 1024 * 1024
app.config['UPLOAD_FOLDER'] = str(UPLOAD_DIR)
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('COOKIE_SECURE', '0') == '1'
init_db()

def csrf_token():
    token = session.get('_csrf_token')
    if not token:
        token = secrets.token_urlsafe(32)
        session['_csrf_token'] = token
    return token

@app.before_request
def protect_post_requests():
    if request.method == 'POST':
        expected = session.get('_csrf_token', '')
        supplied = request.form.get('csrf_token', '')
        if not expected or not supplied or not hmac.compare_digest(expected, supplied):
            abort(400, description='Invalid or expired form token. Refresh the page and try again.')



def db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def now():
    return datetime.now().replace(microsecond=0)


def current_user():
    if 'user_id' not in session:
        return None
    with db() as con:
        return con.execute('SELECT id, name, email, role FROM users WHERE id=?', (session['user_id'],)).fetchone()


def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not current_user():
            flash('Please log in to continue.', 'warning')
            return redirect(url_for('login', next=request.path))
        return fn(*args, **kwargs)
    return wrapped


def roles_required(*roles):
    def deco(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            user = current_user()
            if not user:
                flash('Please log in to continue.', 'warning')
                return redirect(url_for('login'))
            if user['role'] not in roles:
                abort(403)
            return fn(*args, **kwargs)
        return wrapped
    return deco


def save_upload(file, allowed):
    if not file or not file.filename:
        return None
    filename = secure_filename(file.filename)
    if '.' not in filename or filename.rsplit('.', 1)[1].lower() not in allowed:
        raise ValueError('Unsupported file type.')
    ext = filename.rsplit('.', 1)[1].lower()
    new_name = f'{uuid.uuid4().hex}.{ext}'
    file.save(UPLOAD_DIR / new_name)
    return new_name


def audit(con, complaint_id, actor_id, action, details=''):
    con.execute('INSERT INTO history (complaint_id, actor_id, action, details, created_at) VALUES (?,?,?,?,?)',
                (complaint_id, actor_id, action, details[:500], now().isoformat(timespec='seconds')))


def complaint_row(con, complaint_id):
    return con.execute('''SELECT c.*, u.name AS citizen_name, w.name AS worker_name
                          FROM complaints c JOIN users u ON c.citizen_id=u.id
                          LEFT JOIN users w ON c.worker_id=w.id WHERE c.id=?''', (complaint_id,)).fetchone()


def is_overdue(c):
    return c['status'] not in ('Resolved', 'Rejected') and c['sla_due'] and c['sla_due'] < now().isoformat(timespec='seconds')


@app.context_processor
def inject_globals():
    return {'current_user': current_user(), 'is_overdue': is_overdue, 'app_name': 'Digital Amaravati | DI-04', 'csrf_token': csrf_token}


@app.route('/')
def index():
    with db() as con:
        stats = {
            'total': con.execute('SELECT COUNT(*) FROM complaints').fetchone()[0],
            'resolved': con.execute("SELECT COUNT(*) FROM complaints WHERE status='Resolved'").fetchone()[0],
            'open': con.execute("SELECT COUNT(*) FROM complaints WHERE status NOT IN ('Resolved','Rejected')").fetchone()[0],
            'overdue': con.execute("SELECT COUNT(*) FROM complaints WHERE status NOT IN ('Resolved','Rejected') AND sla_due < ?", (now().isoformat(timespec='seconds'),)).fetchone()[0],
        }
        recent = con.execute('''SELECT c.id,c.title,c.category,c.priority,c.status,c.created_at,c.location_text
                                FROM complaints c ORDER BY c.created_at DESC LIMIT 5''').fetchall()
    return render_template('index.html', stats=stats, recent=recent)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()[:100]
        email = request.form.get('email', '').strip().lower()[:254]
        password = request.form.get('password', '')
        if len(name) < 2 or '@' not in email or len(password) < 8:
            flash('Enter a valid name and email. Password must be at least 8 characters.', 'danger')
            return render_template('register.html')
        try:
            with db() as con:
                cur = con.execute('INSERT INTO users(name,email,password_hash,role,created_at) VALUES(?,?,? ,?,?)',
                                  (name, email, generate_password_hash(password), 'citizen', now().isoformat(timespec='seconds')))
                uid = cur.lastrowid
            session.clear(); session['user_id'] = uid
            flash('Account created. Welcome!', 'success')
            return redirect(url_for('citizen_dashboard'))
        except sqlite3.IntegrityError:
            flash('An account with that email already exists.', 'danger')
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        with db() as con:
            user = con.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
        if user and check_password_hash(user['password_hash'], password):
            session.clear(); session['user_id'] = user['id']
            flash('You are signed in.', 'success')
            if user['role'] == 'admin': return redirect(url_for('admin_dashboard'))
            if user['role'] == 'worker': return redirect(url_for('worker_dashboard'))
            return redirect(url_for('citizen_dashboard'))
        flash('Incorrect email or password.', 'danger')
    return render_template('login.html')


@app.route('/logout', methods=['POST'])
@login_required
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))


@app.route('/citizen')
@login_required
@roles_required('citizen')
def citizen_dashboard():
    user = current_user()
    with db() as con:
        complaints = con.execute('SELECT * FROM complaints WHERE citizen_id=? ORDER BY created_at DESC', (user['id'],)).fetchall()
    return render_template('citizen.html', complaints=complaints)


@app.route('/complaint/new', methods=['GET', 'POST'])
@login_required
@roles_required('citizen')
def new_complaint():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()[:160]
        description = request.form.get('description', '').strip()[:5000]
        location_text = request.form.get('location_text', '').strip()[:250]
        lat_raw = request.form.get('latitude', '').strip()
        lon_raw = request.form.get('longitude', '').strip()
        voice_text = request.form.get('voice_text', '').strip()[:5000]
        full_text = (description + ' ' + voice_text).strip()
        if len(title) < 4 or len(full_text) < 10 or len(location_text) < 2:
            flash('Enter a title, a useful description (at least 10 characters), and location.', 'danger')
            return render_template('new_complaint.html')
        try:
            lat = float(lat_raw) if lat_raw else None
            lon = float(lon_raw) if lon_raw else None
            if lat is not None and not -90 <= lat <= 90: raise ValueError
            if lon is not None and not -180 <= lon <= 180: raise ValueError
        except ValueError:
            flash('Latitude must be between -90 and 90 and longitude between -180 and 180.', 'danger')
            return render_template('new_complaint.html')
        try:
            image = save_upload(request.files.get('photo'), ALLOWED_IMAGES)
            audio = save_upload(request.files.get('audio'), ALLOWED_AUDIO)
        except ValueError as exc:
            flash(str(exc), 'danger')
            return render_template('new_complaint.html')
        category, priority = classify_complaint(full_text)
        worker_team = suggested_worker(category)
        sla_hours = 8 if priority == 'High' else 24 if priority == 'Medium' else 72
        created = now()
        due = created + timedelta(hours=sla_hours)
        with db() as con:
            cur = con.execute('''INSERT INTO complaints
                (citizen_id,title,description,voice_text,category,priority,status,location_text,latitude,longitude,
                 photo_filename,audio_filename,assigned_team,created_at,updated_at,sla_due)
                VALUES(?,?,?,?,?,?, 'Submitted', ?,?,?,?,?,?,?,?,?)''',
                (current_user()['id'], title, description, voice_text, category, priority, location_text, lat, lon,
                 image, audio, worker_team, created.isoformat(timespec='seconds'), created.isoformat(timespec='seconds'), due.isoformat(timespec='seconds')))
            cid = cur.lastrowid
            audit(con, cid, current_user()['id'], 'Complaint submitted', f'Category: {category}; priority: {priority}; suggested team: {worker_team}')
        flash(f'Complaint #{cid} submitted. Category: {category}; priority: {priority}.', 'success')
        return redirect(url_for('complaint_detail', complaint_id=cid))
    return render_template('new_complaint.html')


@app.route('/complaint/<int:complaint_id>')
@login_required
def complaint_detail(complaint_id):
    user = current_user()
    with db() as con:
        c = complaint_row(con, complaint_id)
        if not c: abort(404)
        if user['role'] == 'citizen' and c['citizen_id'] != user['id']: abort(403)
        if user['role'] == 'worker' and c['worker_id'] != user['id'] and user['role'] != 'admin': abort(403)
        history = con.execute('''SELECT h.*,u.name AS actor_name FROM history h LEFT JOIN users u ON h.actor_id=u.id
                                 WHERE h.complaint_id=? ORDER BY h.created_at DESC''', (complaint_id,)).fetchall()
    return render_template('complaint_detail.html', c=c, history=history)


@app.route('/admin')
@login_required
@roles_required('admin')
def admin_dashboard():
    q = request.args.get('q', '').strip()[:100]
    status = request.args.get('status', '').strip()
    category = request.args.get('category', '').strip()
    sql = '''SELECT c.*,u.name AS citizen_name,w.name AS worker_name FROM complaints c
             JOIN users u ON c.citizen_id=u.id LEFT JOIN users w ON c.worker_id=w.id WHERE 1=1'''
    params = []
    if q:
        sql += ' AND (c.title LIKE ? OR c.description LIKE ? OR c.location_text LIKE ? OR u.name LIKE ?)'
        params += [f'%{q}%'] * 4
    if status in STATUSES:
        sql += ' AND c.status=?'; params.append(status)
    if category:
        sql += ' AND c.category=?'; params.append(category)
    sql += ' ORDER BY CASE c.priority WHEN \'High\' THEN 0 WHEN \'Medium\' THEN 1 ELSE 2 END, c.created_at DESC'
    with db() as con:
        complaints = con.execute(sql, params).fetchall()
        workers = con.execute("SELECT id,name,email FROM users WHERE role='worker' ORDER BY name").fetchall()
        categories = [r[0] for r in con.execute('SELECT DISTINCT category FROM complaints ORDER BY category').fetchall()]
        stats = {'total': con.execute('SELECT COUNT(*) FROM complaints').fetchone()[0],
                 'open': con.execute("SELECT COUNT(*) FROM complaints WHERE status NOT IN ('Resolved','Rejected')").fetchone()[0],
                 'resolved': con.execute("SELECT COUNT(*) FROM complaints WHERE status='Resolved'").fetchone()[0],
                 'overdue': con.execute("SELECT COUNT(*) FROM complaints WHERE status NOT IN ('Resolved','Rejected') AND sla_due < ?", (now().isoformat(timespec='seconds'),)).fetchone()[0]}
    return render_template('admin.html', complaints=complaints, workers=workers, stats=stats, statuses=STATUSES, categories=categories, q=q, status_filter=status, category_filter=category)


@app.route('/admin/assign/<int:complaint_id>', methods=['POST'])
@login_required
@roles_required('admin')
def assign_complaint(complaint_id):
    worker_id_raw = request.form.get('worker_id', '').strip()
    with db() as con:
        c = con.execute('SELECT * FROM complaints WHERE id=?', (complaint_id,)).fetchone()
        if not c: abort(404)
        worker = None
        if worker_id_raw:
            worker = con.execute("SELECT id,name FROM users WHERE id=? AND role='worker'", (worker_id_raw,)).fetchone()
            if not worker:
                flash('Select a valid field-worker account.', 'danger'); return redirect(url_for('admin_dashboard'))
        status_new = 'Assigned' if worker else 'Submitted'
        con.execute('UPDATE complaints SET worker_id=?, status=?, updated_at=? WHERE id=?',
                    (worker['id'] if worker else None, status_new, now().isoformat(timespec='seconds'), complaint_id))
        audit(con, complaint_id, current_user()['id'], 'Crew assignment changed', worker['name'] if worker else 'Assignment cleared')
    flash(f'Complaint #{complaint_id} assignment updated.', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/status/<int:complaint_id>', methods=['POST'])
@login_required
@roles_required('admin')
def admin_status(complaint_id):
    status = request.form.get('status', '')
    if status not in STATUSES:
        flash('Invalid status.', 'danger'); return redirect(url_for('admin_dashboard'))
    with db() as con:
        c = con.execute('SELECT id, evidence_filename FROM complaints WHERE id=?', (complaint_id,)).fetchone()
        if not c: abort(404)
        if status == 'Resolved' and not c['evidence_filename']:
            flash('Resolution evidence is required before a complaint can be marked Resolved.', 'warning')
            return redirect(url_for('admin_dashboard'))
        con.execute('UPDATE complaints SET status=?, updated_at=? WHERE id=?', (status, now().isoformat(timespec='seconds'), complaint_id))
        audit(con, complaint_id, current_user()['id'], 'Status changed', status)
    flash(f'Complaint #{complaint_id} status updated.', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/worker')
@login_required
@roles_required('worker')
def worker_dashboard():
    user = current_user()
    with db() as con:
        complaints = con.execute('''SELECT c.*,u.name AS citizen_name FROM complaints c JOIN users u ON c.citizen_id=u.id
            WHERE c.worker_id=? ORDER BY CASE c.priority WHEN 'High' THEN 0 WHEN 'Medium' THEN 1 ELSE 2 END, c.created_at DESC''', (user['id'],)).fetchall()
    return render_template('worker.html', complaints=complaints)


@app.route('/worker/update/<int:complaint_id>', methods=['POST'])
@login_required
@roles_required('worker')
def worker_update(complaint_id):
    user = current_user()
    status = request.form.get('status', '')
    if status not in ('In Progress', 'Pending Verification'):
        flash('Workers may set In Progress or Pending Verification only.', 'danger')
        return redirect(url_for('worker_dashboard'))
    try:
        evidence = save_upload(request.files.get('evidence'), ALLOWED_EVIDENCE)
    except ValueError as exc:
        flash(str(exc), 'danger'); return redirect(url_for('worker_dashboard'))
    if status == 'Pending Verification' and not evidence:
        flash('Upload a resolution photo before requesting closure.', 'danger')
        return redirect(url_for('worker_dashboard'))
    with db() as con:
        c = con.execute('SELECT id FROM complaints WHERE id=? AND worker_id=?', (complaint_id, user['id'])).fetchone()
        if not c: abort(404)
        con.execute('UPDATE complaints SET status=?, evidence_filename=COALESCE(?, evidence_filename), updated_at=? WHERE id=?',
                    (status, evidence, now().isoformat(timespec='seconds'), complaint_id))
        audit(con, complaint_id, user['id'], 'Field work updated', f'{status}' + ('; evidence uploaded' if evidence else ''))
    flash('Work update saved.', 'success')
    return redirect(url_for('worker_dashboard'))


@app.route('/admin/verify/<int:complaint_id>', methods=['POST'])
@login_required
@roles_required('admin')
def verify_resolution(complaint_id):
    decision = request.form.get('decision', '')
    if decision not in ('approve', 'reject'):
        flash('Invalid verification choice.', 'danger'); return redirect(url_for('admin_dashboard'))
    with db() as con:
        c = con.execute('SELECT * FROM complaints WHERE id=?', (complaint_id,)).fetchone()
        if not c: abort(404)
        if c['status'] != 'Pending Verification' or not c['evidence_filename']:
            flash('This complaint is not awaiting verification with evidence.', 'warning')
            return redirect(url_for('admin_dashboard'))
        new_status = 'Resolved' if decision == 'approve' else 'In Progress'
        con.execute('UPDATE complaints SET status=?, updated_at=? WHERE id=?', (new_status, now().isoformat(timespec='seconds'), complaint_id))
        audit(con, complaint_id, current_user()['id'], 'Resolution ' + ('approved' if decision == 'approve' else 'returned for rework'), new_status)
    flash(f'Complaint #{complaint_id}: {new_status}.', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/scorecard')
def scorecard():
    with db() as con:
        total = con.execute('SELECT COUNT(*) FROM complaints').fetchone()[0]
        resolved = con.execute("SELECT COUNT(*) FROM complaints WHERE status='Resolved'").fetchone()[0]
        open_count = con.execute("SELECT COUNT(*) FROM complaints WHERE status NOT IN ('Resolved','Rejected')").fetchone()[0]
        overdue = con.execute("SELECT COUNT(*) FROM complaints WHERE status NOT IN ('Resolved','Rejected') AND sla_due < ?", (now().isoformat(timespec='seconds'),)).fetchone()[0]
        categories = con.execute('SELECT category,COUNT(*) AS count FROM complaints GROUP BY category ORDER BY count DESC').fetchall()
        statuses = con.execute('SELECT status,COUNT(*) AS count FROM complaints GROUP BY status ORDER BY status').fetchall()
        avg = con.execute("SELECT AVG((julianday(updated_at)-julianday(created_at))*24) FROM complaints WHERE status='Resolved'").fetchone()[0]
    return render_template('scorecard.html', total=total, resolved=resolved, open_count=open_count, overdue=overdue, categories=categories, statuses=statuses, avg_hours=round(avg, 1) if avg is not None else None)


@app.route('/uploads/<path:filename>')
@login_required
def uploaded_file(filename):
    # Only serve files attached to a complaint the signed-in user may access.
    user = current_user()
    with db() as con:
        c = con.execute('''SELECT * FROM complaints WHERE photo_filename=? OR audio_filename=? OR evidence_filename=?''',
                        (filename, filename, filename)).fetchone()
    if not c:
        abort(404)
    if user['role'] == 'citizen' and c['citizen_id'] != user['id']:
        abort(403)
    if user['role'] == 'worker' and c['worker_id'] != user['id']:
        abort(403)
    return send_from_directory(UPLOAD_DIR, filename, as_attachment=False, download_name=filename)


@app.route('/health')
def health():
    try:
        with db() as con: con.execute('SELECT 1').fetchone()
        return {'status': 'ok', 'database': 'connected'}, 200
    except sqlite3.Error:
        return {'status': 'error', 'database': 'unavailable'}, 503


@app.errorhandler(400)
def bad_request(error):
    return render_template('error.html', code=400, message='The form could not be verified. Refresh the page and submit again.'), 400


@app.errorhandler(403)
def forbidden(error):
    return render_template('error.html', code=403, message='You do not have permission to access this page.'), 403


@app.errorhandler(404)
def not_found(error):
    return render_template('error.html', code=404, message='The requested page or complaint was not found.'), 404


@app.errorhandler(413)
def too_large(error):
    return render_template('error.html', code=413, message='Upload too large. The total request limit is 12 MB.'), 413


if __name__ == '__main__':
    # Development only; use a production WSGI server and HTTPS for deployment.
    app.run(debug=os.environ.get('FLASK_DEBUG', '1') == '1')
