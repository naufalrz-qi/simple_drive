import os
import json
import shutil
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote
from flask import (
    Flask, request, jsonify, send_from_directory, abort,
    render_template, redirect, url_for, session
)
from werkzeug.utils import secure_filename
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from functools import wraps
from models import db, User

BASE_DIR = Path(__file__).parent
UPLOAD_DIR = (BASE_DIR / os.getenv("UPLOAD_DIR", "uploads")).resolve()
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

exts = os.getenv("ALLOWED_EXTENSIONS", "")
ALLOWED_EXT = {e.strip().lower() for e in exts.split(',') if e.strip()}

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'default_secret_key_change_me')
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{BASE_DIR / 'data' / 'db.sqlite3'}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Ensure data directory exists
(BASE_DIR / 'data').mkdir(parents=True, exist_ok=True)

db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# Create default admin if not exists
with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', role='admin')
        admin.set_password('admin123')
        admin.generate_api_key()
        db.session.add(admin)
        db.session.commit()
        print(f"Default admin created. API Key: {admin.api_key}")

# ---------------------- Auth Decorator -------------------- #
def require_auth(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 1. Check API Key
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            api_key = auth_header.split(' ')[1]
            user = User.query.filter_by(api_key=api_key).first()
            if user:
                return f(*args, **kwargs)
        
        # 2. Check Session
        if current_user.is_authenticated:
            return f(*args, **kwargs)
            
        # If API request (JSON) return 401
        if request.is_json or request.path.startswith('/items') or request.path.startswith('/folders') or request.path.startswith('/operate') or request.path.startswith('/upload'):
            abort(401, description="Unauthorized")
            
        # Otherwise redirect to login
        return redirect(url_for('login'))
    return decorated_function

def require_admin(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            abort(403, description="Admin access required")
        return f(*args, **kwargs)
    return decorated_function

# app.config["MAX_CONTENT_LENGTH"] = int(os.getenv("MAX_CONTENT_LENGTH", 200 * 1024 * 1024))

# ---------------------- Helpers --------------------------- #

def norm(rel: str) -> Path:
    """Normalize relative path inside uploads; prevent traversal"""
    rel_path = Path(rel).as_posix().lstrip('/')
    safe = (UPLOAD_DIR / rel_path).resolve()
    if not str(safe).startswith(str(UPLOAD_DIR)):
        abort(400, description="Invalid path")
    return safe


def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)

# ---------------------- Error Handlers -------------------- #

@app.errorhandler(400)
@app.errorhandler(401)
@app.errorhandler(403)
@app.errorhandler(404)
def json_error(e):
    return jsonify(error=str(e.description)), e.code

# ---------------------- API Routes ------------------------ #

@app.post('/folders')
@require_auth
def create_folder():
    data = request.get_json(force=True, silent=True) or {}
    name = secure_filename(data.get('name', ''))
    parent = data.get('path', '')
    if not name:
        abort(400, description='Folder name required')
    target = norm(Path(parent) / name)
    ensure_dir(target)
    return jsonify(message='Folder created', path=str(target.relative_to(UPLOAD_DIR)))


@app.get('/items')
@require_auth
def list_items():
    rel = unquote(request.args.get('path', '').lstrip('/'))
    folder = norm(rel)
    ensure_dir(folder)
    items = []
    for p in folder.iterdir():
        stat = p.stat()
        items.append({
            'name': p.name,
            'is_folder': p.is_dir(),
            'size': stat.st_size,
            'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
            'path': str(p.relative_to(UPLOAD_DIR))
        })
    items.sort(key=lambda x: (not x['is_folder'], x['name'].lower()))
    return jsonify(items)


@app.post('/operate')   
@require_auth
def operate():
    data = request.get_json(force=True, silent=True) or {}
    src = norm(data.get('src', ''))
    dest = norm(data.get('dest', ''))
    op = data.get('op')
    if op not in {'copy', 'cut'}:
        abort(400, description='op must be copy|cut')
    if not src.exists() or not dest.is_dir():
        abort(404, description='Source or destination missing')
    target = dest / src.name
    if op == 'copy':
        if src.is_dir():
            shutil.copytree(src, target, dirs_exist_ok=True)
        else:
            shutil.copy2(src, target)
    else:
        shutil.move(src, target)
    return jsonify(message=f'{op} done', path=str(target.relative_to(UPLOAD_DIR)))


@app.post('/rename')
@require_auth
def rename():
    data = request.get_json(force=True, silent=True) or {}
    src = norm(data.get('src', ''))
    new_name = secure_filename(data.get('name', ''))
    if not new_name:
        abort(400, description='New name required')
    if not src.exists():
        abort(404, description='Source not found')
    target = src.parent / new_name
    if target.exists():
        abort(400, description='Name already exists')
    src.rename(target)
    return jsonify(message='renamed', path=str(target.relative_to(UPLOAD_DIR)))

@app.post('/upload')
@require_auth
def upload():
    # Ambil semua file (bisa banyak)
    files = request.files.getlist('file')
    if not files:
        abort(400, description='file field missing')

    folder = norm(request.form.get('path', ''))
    ensure_dir(folder)

    def unique_filename(folder: Path, name: str) -> str:
        base, ext = os.path.splitext(name)
        candidate = secure_filename(base) + ext
        i = 1
        while (folder / candidate).exists():
            candidate = f"{secure_filename(base)} ({i}){ext}"
            i += 1
        return candidate

    saved = []
    skipped = []
    errors = []

    for file in files:
        if not file or not file.filename:
            skipped.append({'filename': '', 'reason': 'empty filename'})
            continue

        fname = file.filename
        ext = fname.rsplit('.', 1)[-1].lower() if '.' in fname else ''
        if ALLOWED_EXT and ext not in ALLOWED_EXT:
            skipped.append({'filename': fname, 'reason': 'type forbidden'})
            continue

        safe_name = unique_filename(folder, fname)
        save_path = folder / safe_name
        try:
            file.save(save_path)
            saved.append(str(save_path.relative_to(UPLOAD_DIR)))
        except Exception as exc:
            errors.append({'filename': fname, 'error': str(exc)})

    if not saved and (errors or skipped):
        # tidak ada file berhasil
        return jsonify(message='no files saved', saved=saved, skipped=skipped, errors=errors), 400

    status_code = 201 if saved else 200
    return jsonify(message='uploaded', saved=saved, skipped=skipped, errors=errors), status_code



@app.get('/download/<path:rel>')
@require_auth
def download(rel):
    p = norm(rel)
    if not p.exists() or p.is_dir():
        abort(404, description='file missing')
    return send_from_directory(p.parent, p.name, as_attachment=True)


@app.delete('/items')
@require_auth
def delete():
    p = norm(request.args.get('path', ''))
    if not p.exists():
        abort(404, description='not found')
    if p.is_dir():
        shutil.rmtree(p)
    else:
        p.unlink()
    return jsonify(message='deleted')

# ---------------------- Auth Routes ----------------------- #

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main'))
        
    if request.method == 'POST':
        data = request.form
        username = data.get('username')
        password = data.get('password')
        
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('main'))
        else:
            return render_template('login.html', error="Invalid username or password")
            
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/api/change-password', methods=['POST'])
@login_required
def change_password():
    data = request.json
    if not data or not data.get('old_password') or not data.get('new_password'):
        abort(400, description="Old and new password required")
        
    if not current_user.check_password(data['old_password']):
        abort(400, description="Incorrect old password")
        
    current_user.set_password(data['new_password'])
    db.session.commit()
    return jsonify({'message': 'Password changed successfully'})

@app.route('/api/users', methods=['GET'])
@require_admin
def get_users():
    users = User.query.all()
    return jsonify([{
        'id': u.id, 'username': u.username, 'role': u.role, 'api_key': u.api_key
    } for u in users])

@app.route('/api/users', methods=['POST'])
@require_admin
def create_user():
    data = request.json
    if not data or not data.get('username') or not data.get('password'):
        abort(400, description="Username and password required")
        
    if User.query.filter_by(username=data['username']).first():
        abort(400, description="Username already exists")
        
    user = User(username=data['username'], role=data.get('role', 'user'))
    user.set_password(data['password'])
    user.generate_api_key()
    
    db.session.add(user)
    db.session.commit()
    return jsonify({'message': 'User created', 'id': user.id}), 201

@app.route('/api/users/<int:user_id>', methods=['DELETE'])
@require_admin
def delete_user(user_id):
    if user_id == current_user.id:
        abort(400, description="Cannot delete yourself")
    user = db.session.get(User, user_id)
    if not user:
        abort(404, description="User not found")
    db.session.delete(user)
    db.session.commit()
    return jsonify({'message': 'User deleted'})

# ---------------------- Frontend -------------------------- #

@app.route('/')
@login_required
def main():
    return render_template('index.html', user=current_user)

# ---------------------- Run ------------------------------- #
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 80)))
