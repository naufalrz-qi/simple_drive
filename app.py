import os
import json
import shutil
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote
from flask import (
    Flask, request, jsonify, send_from_directory, abort,
    render_template
)
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).parent
UPLOAD_DIR = (BASE_DIR / os.getenv("UPLOAD_DIR", "uploads")).resolve()
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

exts = os.getenv("ALLOWED_EXTENSIONS", "")
ALLOWED_EXT = {e.strip().lower() for e in exts.split(',') if e.strip()}

app = Flask(__name__)
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
@app.errorhandler(404)
def json_error(e):
    return jsonify(error=str(e.description)), e.code

# ---------------------- API Routes ------------------------ #

@app.post('/folders')
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


@app.post('/upload')
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
def download(rel):
    p = norm(rel)
    if not p.exists() or p.is_dir():
        abort(404, description='file missing')
    return send_from_directory(p.parent, p.name, as_attachment=True)


@app.delete('/items')
def delete():
    p = norm(request.args.get('path', ''))
    if not p.exists():
        abort(404, description='not found')
    if p.is_dir():
        shutil.rmtree(p)
    else:
        p.unlink()
    return jsonify(message='deleted')

# ---------------------- Frontend -------------------------- #

@app.route('/')
def main():
    return render_template('index.html')

# ---------------------- Run ------------------------------- #
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 80)))
