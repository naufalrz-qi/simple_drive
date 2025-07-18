# """
# Simple File Storage API with Web Dashboard using Flask and JSON file as DB.
# Features:
# - Upload file (POST /upload)
# - List files (GET /files)
# - Download file (GET /files/<id>)
# - Delete file (DELETE /files/<id>)
# - Web Dashboard (GET /)

# Quickstart:
# 1. pip install flask python-dotenv
# 2. python app.py
# 3. Open http://localhost:5000
# """

# import os
# import json
# import uuid
# from datetime import datetime
# from pathlib import Path
# from flask import Flask, request, jsonify, send_from_directory, abort, render_template
# from werkzeug.utils import secure_filename

# # ---------------------- Configuration ---------------------- #
# UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "uploads"))
# DB_PATH = Path(os.getenv("DB_PATH", "db.json"))

# # Handle allowed extensions env var properly
# exts = os.getenv("ALLOWED_EXTENSIONS", "")
# ALLOWED_EXTENSIONS = set(exts.split(",")) if exts.strip() else set()

# UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# app = Flask(__name__)
# # app.config["MAX_CONTENT_LENGTH"] = int(os.getenv("MAX_CONTENT_LENGTH", 5000 * 1024 * 1024))  # 50MB default

# # ---------------------- Utility Functions ------------------ #

# def load_db():
#     if not DB_PATH.exists():
#         return {}
#     content = DB_PATH.read_text(encoding="utf-8").strip()
#     if not content:
#         return {}
#     try:
#         return json.loads(content)
#     except json.JSONDecodeError:
#         return {}


# def save_db(data):
#     DB_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


# def allowed_file(filename: str) -> bool:
#     if not ALLOWED_EXTENSIONS:
#         return True  # no restrictions
#     return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

# # ---------------------- Routes ----------------------------- #

# @app.route("/upload", methods=["POST"])
# def upload_file():
#     if "file" not in request.files:
#         return jsonify({"error": "No file part"}), 400

#     file = request.files["file"]
#     if file.filename == "":
#         return jsonify({"error": "No selected file"}), 400

#     if not allowed_file(file.filename):
#         return jsonify({"error": "File type not allowed"}), 400

#     fid = str(uuid.uuid4())
#     original_name = secure_filename(file.filename)
#     stored_name = f"{fid}_{original_name}"
#     filepath = UPLOAD_DIR / stored_name
#     file.save(filepath)

#     db = load_db()
#     db[fid] = {
#         "id": fid,
#         "original_name": original_name,
#         "stored_name": stored_name,
#         "size": filepath.stat().st_size,
#         "mimetype": file.mimetype,
#         "uploaded_at": datetime.utcnow().isoformat() + "Z",
#     }
#     save_db(db)
#     return jsonify(db[fid]), 201


# @app.route("/files", methods=["GET"])
# def list_files():
#     db = load_db()
#     return jsonify(list(db.values()))


# @app.route("/files/<fid>", methods=["GET"])
# def download_file(fid):
#     db = load_db()
#     meta = db.get(fid)
#     if not meta:
#         abort(404, description="File not found")
#     return send_from_directory(UPLOAD_DIR, meta["stored_name"], as_attachment=True, download_name=meta["original_name"])


# @app.route("/files/<fid>", methods=["DELETE"])
# def delete_file(fid):
#     db = load_db()
#     meta = db.pop(fid, None)
#     if not meta:
#         abort(404, description="File not found")
#     (UPLOAD_DIR / meta["stored_name"]).unlink(missing_ok=True)
#     save_db(db)
#     return jsonify({"message": "Deleted", "id": fid})

# @app.route("/")
# def dashboard():
#     return render_template("index.html")

# # ---------------------- Entry Point ------------------------ #
# if __name__ == "__main__":
#     app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
"""
Simple Drive‑like Storage API + Web UI (Flask + vanilla JS)
[FIXED 2025‑07‑15]
-----------------------------------------------------------
Patch notes:
1. All error responses now return JSON `{error: ...}` to prevent front‑end JSON.parse errors.
2. `norm()` path validation fixed for Windows paths.
3. `/items` now accepts empty `path` param and returns root listing correctly.
4. Added global error handler for 400 & 404 returning JSON.
"""

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
    if 'file' not in request.files:
        abort(400, description='file field missing')
    file = request.files['file']
    folder = norm(request.form.get('path', ''))
    ensure_dir(folder)
    if not file.filename:
        abort(400, description='empty filename')
    if ALLOWED_EXT and file.filename.rsplit('.', 1)[-1].lower() not in ALLOWED_EXT:
        abort(400, description='type forbidden')
    fname = secure_filename(file.filename)
    save_path = folder / fname
    file.save(save_path)
    return jsonify(message='uploaded', path=str(save_path.relative_to(UPLOAD_DIR))), 201


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
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
