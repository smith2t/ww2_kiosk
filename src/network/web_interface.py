import asyncio
import json
import logging
import os
import shutil
import threading
from pathlib import Path
from typing import Optional

from flask import Flask, render_template_string, request, redirect, url_for, flash, jsonify
from werkzeug.utils import secure_filename

logger = logging.getLogger(__name__)


class WebInterface:
    def __init__(self, settings):
        self.settings = settings
        self.app = Flask(__name__)
        self.app.secret_key = 'ww2-kiosk-secret-key'  # TODO: Make this configurable
        self.setup_routes()
        self.media_dir = Path(settings.media.pictures_dir)
        self.video_dir = Path(settings.media.videos_dir)
        self.button_mappings_file = Path(settings.config.button_mappings_file)

        # Ensure directories exist
        self.media_dir.mkdir(parents=True, exist_ok=True)
        self.video_dir.mkdir(parents=True, exist_ok=True)

    def setup_routes(self):
        """Setup Flask routes"""

        @self.app.route('/')
        def index():
            return render_template_string(INDEX_TEMPLATE)

        @self.app.route('/media')
        def media():
            # Get media files
            media_files = []
            video_files = []

            if self.media_dir.exists():
                for ext in ['*.jpg', '*.jpeg', '*.png', '*.bmp', '*.gif', '*.pdf', '*.pptx', '*.ppt']:
                    media_files.extend(self.media_dir.glob(ext))
                    media_files.extend(self.media_dir.glob(ext.upper()))

            if self.video_dir.exists():
                for ext in ['*.mp4', '*.avi', '*.mkv', '*.mov']:
                    video_files.extend(self.video_dir.glob(ext))
                    video_files.extend(self.video_dir.glob(ext.upper()))

            return render_template_string(
                MEDIA_TEMPLATE,
                media_files=media_files,
                video_files=video_files
            )

        @self.app.route('/upload', methods=['GET', 'POST'])
        def upload():
            if request.method == 'POST':
                upload_type = request.form.get('upload_type', 'media')
                files = request.files.getlist('file')
                files = [f for f in files if f and f.filename]

                if not files:
                    flash('No files selected')
                    return redirect(request.url)

                target_dir = self.media_dir if upload_type == 'media' else self.video_dir
                saved, skipped = [], []

                for f in files:
                    # Folder uploads preserve relative paths in filename
                    # (e.g. "vacation/img.jpg") — flatten to basename so the
                    # kiosk's flat-dir scanner finds the file.
                    base = f.filename.rsplit('/', 1)[-1].rsplit('\\', 1)[-1]
                    if not self._allowed_file(base, upload_type):
                        skipped.append(base)
                        continue
                    safe = secure_filename(base)
                    f.save(str(target_dir / safe))
                    saved.append(safe)

                if saved:
                    flash(f'Uploaded {len(saved)} file(s): {", ".join(saved[:5])}'
                          + (f' and {len(saved) - 5} more' if len(saved) > 5 else ''))
                if skipped:
                    flash(f'Skipped {len(skipped)} file(s) with invalid type: '
                          + ", ".join(skipped[:3])
                          + (f' and {len(skipped) - 3} more' if len(skipped) > 3 else ''))

                return redirect(url_for('media'))

            return render_template_string(UPLOAD_TEMPLATE)

        @self.app.route('/buttons', methods=['GET', 'POST'])
        def buttons():
            mappings = self._load_button_mappings()

            if request.method == 'POST':
                button_id = request.form.get('button_id', '').strip()
                if button_id not in {'1', '2', '3', '4'}:
                    flash(f'Invalid button id: {button_id}')
                    return redirect(url_for('buttons'))

                # Optional uploaded video for this button
                uploaded = request.files.get('video')
                selected_existing = request.form.get('existing', '').strip()
                target_filename = None

                if uploaded and uploaded.filename:
                    base = uploaded.filename.rsplit('/', 1)[-1].rsplit('\\', 1)[-1]
                    if not self._allowed_file(base, 'video'):
                        flash(f'Button {button_id}: invalid video type ({base})')
                        return redirect(url_for('buttons'))
                    target_filename = secure_filename(base)
                    uploaded.save(str(self.video_dir / target_filename))
                    flash(f'Button {button_id}: uploaded {target_filename}')
                elif selected_existing:
                    target_filename = selected_existing
                else:
                    flash(f'Button {button_id}: no video provided')
                    return redirect(url_for('buttons'))

                mappings[button_id] = target_filename
                self._save_button_mappings(mappings)
                flash(f'Button {button_id} → {target_filename}')
                return redirect(url_for('buttons'))

            # GET: build the page
            existing_videos = sorted([p.name for ext in ('*.mp4', '*.avi', '*.mkv', '*.mov')
                                      for p in self.video_dir.glob(ext)])
            buttons_data = []
            for bid in ('1', '2', '3', '4'):
                current = mappings.get(bid)
                file_exists = bool(current and (self.video_dir / current).exists())
                buttons_data.append({
                    'id': bid,
                    'current': current,
                    'file_exists': file_exists,
                })
            return render_template_string(BUTTONS_TEMPLATE,
                                          buttons_data=buttons_data,
                                          existing_videos=existing_videos)

        @self.app.route('/delete/<file_type>/<filename>')
        def delete_file(file_type, filename):
            try:
                if file_type == 'media':
                    file_path = self.media_dir / filename
                elif file_type == 'video':
                    file_path = self.video_dir / filename
                else:
                    flash('Invalid file type')
                    return redirect(url_for('media'))

                if file_path.exists():
                    file_path.unlink()
                    flash(f'File {filename} deleted successfully!')
                else:
                    flash(f'File {filename} not found')
            except Exception as e:
                flash(f'Error deleting file: {e}')

            return redirect(url_for('media'))

        @self.app.route('/api/status')
        def api_status():
            """API endpoint for kiosk status"""
            return jsonify({
                'status': 'running',
                'media_count': len(list(self.media_dir.glob('*'))),
                'video_count': len(list(self.video_dir.glob('*'))),
                'uptime': '24h'  # TODO: Calculate actual uptime
            })

    def _load_button_mappings(self) -> dict:
        if not self.button_mappings_file.exists():
            return {}
        try:
            with open(self.button_mappings_file) as f:
                return json.load(f).get('mappings', {})
        except Exception as e:
            logger.error(f"Failed to load button mappings: {e}")
            return {}

    def _save_button_mappings(self, mappings: dict) -> None:
        try:
            self.button_mappings_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.button_mappings_file, 'w') as f:
                json.dump({'mappings': mappings}, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save button mappings: {e}")

    def _allowed_file(self, filename: str, upload_type: str) -> bool:
        """Check if file extension is allowed"""
        allowed_extensions = {
            'media': {'jpg', 'jpeg', 'png', 'bmp', 'gif', 'pdf', 'pptx', 'ppt'},
            'video': {'mp4', 'avi', 'mkv', 'mov'}
        }

        if '.' not in filename:
            return False

        ext = filename.rsplit('.', 1)[1].lower()
        return ext in allowed_extensions.get(upload_type, set())

    async def start(self, host='0.0.0.0', port=8080):
        """Start the web interface in a background thread.

        Flask's app.run() is blocking; running it directly in an asyncio task
        would freeze the event loop and prevent the slideshow from starting.
        """
        logger.info(f"Starting web interface on {host}:{port}")

        def _run():
            try:
                self.app.run(host=host, port=port, debug=False,
                             threaded=True, use_reloader=False)
            except Exception as e:
                logger.error(f"Web interface error: {e}")

        threading.Thread(target=_run, daemon=True, name="flask-web").start()

    async def stop(self):
        """Stop the web interface"""
        logger.info("Stopping web interface")
        # Flask doesn't have a clean shutdown method, so we'll handle this at the process level


# HTML Templates
INDEX_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>WW2 Kiosk Management</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }
        .container { max-width: 800px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        h1 { color: #333; text-align: center; }
        .nav-menu { text-align: center; margin: 20px 0; }
        .nav-menu a { display: inline-block; margin: 0 10px; padding: 10px 20px; background: #007bff; color: white; text-decoration: none; border-radius: 4px; }
        .nav-menu a:hover { background: #0056b3; }
        .status-card { background: #e8f5e8; padding: 15px; border-radius: 4px; margin: 10px 0; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎖️ WW2 Kiosk Management</h1>

        <div class="status-card">
            <h3>System Status</h3>
            <p>Kiosk is running normally</p>
            <p>Ready to display content</p>
        </div>

        <div class="nav-menu">
            <a href="{{ url_for('media') }}">📁 Manage Media</a>
            <a href="{{ url_for('upload') }}">⬆️ Upload Files</a>
            <a href="{{ url_for('buttons') }}">🎛️ Configure Buttons</a>
        </div>

        <div style="text-align: center; margin-top: 30px; color: #666;">
            <p>Access this interface to manage your kiosk content</p>
            <p>Upload images, PDFs, PowerPoint files, and videos</p>
        </div>
    </div>
</body>
</html>
'''

MEDIA_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Media Management - WW2 Kiosk</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }
        .container { max-width: 1000px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        h1 { color: #333; text-align: center; }
        .nav-menu { text-align: center; margin: 20px 0; }
        .nav-menu a { display: inline-block; margin: 0 10px; padding: 10px 20px; background: #007bff; color: white; text-decoration: none; border-radius: 4px; }
        .nav-menu a:hover { background: #0056b3; }
        .file-section { margin: 20px 0; }
        .file-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 15px; margin: 15px 0; }
        .file-item { background: #f8f9fa; padding: 10px; border-radius: 4px; border: 1px solid #dee2e6; }
        .file-name { font-weight: bold; margin-bottom: 5px; word-break: break-word; }
        .file-actions { margin-top: 5px; }
        .delete-btn { background: #dc3545; color: white; border: none; padding: 5px 10px; border-radius: 3px; cursor: pointer; }
        .delete-btn:hover { background: #c82333; }
        .flash-messages { margin: 20px 0; }
        .flash-message { padding: 10px; border-radius: 4px; margin: 5px 0; }
        .flash-success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
        .flash-error { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
    </style>
</head>
<body>
    <div class="container">
        <h1>📁 Media Management</h1>

        <div class="nav-menu">
            <a href="{{ url_for('index') }}">🏠 Home</a>
            <a href="{{ url_for('upload') }}">⬆️ Upload Files</a>
        </div>

        {% with messages = get_flashed_messages() %}
        {% if messages %}
        <div class="flash-messages">
            {% for message in messages %}
            <div class="flash-message flash-success">{{ message }}</div>
            {% endfor %}
        </div>
        {% endif %}
        {% endwith %}

        <div class="file-section">
            <h2>📷 Slideshow Media ({{ media_files|length }} files)</h2>
            <p>Images, PDFs, and PowerPoint files for slideshow</p>
            {% if media_files %}
            <div class="file-list">
                {% for file in media_files %}
                <div class="file-item">
                    <div class="file-name">{{ file.name }}</div>
                    <small>{{ "%.1f"|format(file.stat().st_size / 1024 / 1024) }} MB</small>
                    <div class="file-actions">
                        <button class="delete-btn" onclick="if(confirm('Delete {{ file.name }}?')) window.location.href='{{ url_for('delete_file', file_type='media', filename=file.name) }}'">🗑️ Delete</button>
                    </div>
                </div>
                {% endfor %}
            </div>
            {% else %}
            <p>No media files found. Upload some images, PDFs, or PowerPoint files!</p>
            {% endif %}
        </div>

        <div class="file-section">
            <h2>🎬 Video Files ({{ video_files|length }} files)</h2>
            <p>Videos triggered by control panel buttons</p>
            {% if video_files %}
            <div class="file-list">
                {% for file in video_files %}
                <div class="file-item">
                    <div class="file-name">{{ file.name }}</div>
                    <small>{{ "%.1f"|format(file.stat().st_size / 1024 / 1024) }} MB</small>
                    <div class="file-actions">
                        <button class="delete-btn" onclick="if(confirm('Delete {{ file.name }}?')) window.location.href='{{ url_for('delete_file', file_type='video', filename=file.name) }}'">🗑️ Delete</button>
                    </div>
                </div>
                {% endfor %}
            </div>
            {% else %}
            <p>No video files found. Upload some videos!</p>
            {% endif %}
        </div>
    </div>
</body>
</html>
'''

UPLOAD_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Upload Files - WW2 Kiosk</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }
        .container { max-width: 600px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        h1 { color: #333; text-align: center; }
        .nav-menu { text-align: center; margin: 20px 0; }
        .nav-menu a { display: inline-block; margin: 0 10px; padding: 10px 20px; background: #007bff; color: white; text-decoration: none; border-radius: 4px; }
        .nav-menu a:hover { background: #0056b3; }
        .upload-form { margin: 30px 0; }
        .form-group { margin: 15px 0; }
        label { display: block; margin-bottom: 5px; font-weight: bold; }
        select, input[type="file"] { width: 100%; padding: 10px; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box; }
        .upload-btn { background: #28a745; color: white; padding: 12px 24px; border: none; border-radius: 4px; cursor: pointer; font-size: 16px; width: 100%; }
        .upload-btn:hover { background: #218838; }
        .file-types { background: #f8f9fa; padding: 15px; border-radius: 4px; margin: 15px 0; }
        .flash-messages { margin: 20px 0; }
        .flash-message { padding: 10px; border-radius: 4px; margin: 5px 0; }
        .flash-success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
        .flash-error { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
    </style>
</head>
<body>
    <div class="container">
        <h1>⬆️ Upload Files</h1>

        <div class="nav-menu">
            <a href="{{ url_for('index') }}">🏠 Home</a>
            <a href="{{ url_for('media') }}">📁 Manage Media</a>
        </div>

        {% with messages = get_flashed_messages() %}
        {% if messages %}
        <div class="flash-messages">
            {% for message in messages %}
            <div class="flash-message flash-success">{{ message }}</div>
            {% endfor %}
        </div>
        {% endif %}
        {% endwith %}

        <form method="post" enctype="multipart/form-data" class="upload-form">
            <div class="form-group">
                <label for="upload_type">File Type:</label>
                <select name="upload_type" id="upload_type" onchange="updateFileTypes()">
                    <option value="media">Slideshow Media (Images, PDFs, PowerPoint)</option>
                    <option value="video">Button Videos (MP4, AVI, etc.)</option>
                </select>
            </div>

            <div class="form-group">
                <label for="file">Choose Files:</label>
                <input type="file" name="file" id="file" multiple required>
                <label style="font-weight: normal; margin-top: 8px;">
                    <input type="checkbox" id="folder_mode" onchange="toggleFolderMode()">
                    Upload entire folder instead (Chrome / Edge / Safari)
                </label>
            </div>

            <div class="file-types" id="file-types">
                <strong>Supported formats:</strong><br>
                <span id="supported-formats">Images: JPG, PNG, GIF, BMP<br>Documents: PDF, PowerPoint (.pptx, .ppt)</span>
            </div>

            <button type="submit" class="upload-btn">📤 Upload Files</button>
        </form>
    </div>

    <script>
        function updateFileTypes() {
            const uploadType = document.getElementById('upload_type').value;
            const formatsSpan = document.getElementById('supported-formats');

            if (uploadType === 'media') {
                formatsSpan.innerHTML = 'Images: JPG, PNG, GIF, BMP<br>Documents: PDF, PowerPoint (.pptx, .ppt)';
            } else {
                formatsSpan.innerHTML = 'Videos: MP4, AVI, MKV, MOV';
            }
        }

        function toggleFolderMode() {
            const fileInput = document.getElementById('file');
            const folderMode = document.getElementById('folder_mode').checked;
            if (folderMode) {
                fileInput.setAttribute('webkitdirectory', '');
                fileInput.setAttribute('directory', '');
            } else {
                fileInput.removeAttribute('webkitdirectory');
                fileInput.removeAttribute('directory');
            }
        }
    </script>
</body>
</html>
'''

BUTTONS_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Configure Buttons - WW2 Kiosk</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }
        .container { max-width: 900px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        h1 { color: #333; text-align: center; }
        .nav-menu { text-align: center; margin: 20px 0; }
        .nav-menu a { display: inline-block; margin: 0 10px; padding: 10px 20px; background: #007bff; color: white; text-decoration: none; border-radius: 4px; }
        .nav-menu a:hover { background: #0056b3; }
        .button-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(380px, 1fr)); gap: 20px; margin-top: 20px; }
        .button-card { border: 2px solid #ddd; border-radius: 8px; padding: 20px; background: #fafafa; }
        .button-card h2 { margin-top: 0; color: #007bff; }
        .current-mapping { padding: 10px; border-radius: 4px; margin-bottom: 15px; font-family: monospace; }
        .ok { background: #d4edda; color: #155724; }
        .missing { background: #fff3cd; color: #856404; }
        .none { background: #e2e3e5; color: #383d41; }
        .form-row { margin: 12px 0; }
        label { display: block; font-weight: bold; margin-bottom: 4px; }
        select, input[type="file"] { width: 100%; padding: 8px; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box; }
        .save-btn { background: #28a745; color: white; padding: 10px 16px; border: none; border-radius: 4px; cursor: pointer; font-size: 14px; width: 100%; margin-top: 10px; }
        .save-btn:hover { background: #218838; }
        .or { text-align: center; color: #999; margin: 8px 0; font-size: 12px; }
        .flash-messages { margin: 20px 0; }
        .flash-message { padding: 10px; border-radius: 4px; margin: 5px 0; background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎛️ Configure Buttons</h1>

        <div class="nav-menu">
            <a href="{{ url_for('index') }}">🏠 Home</a>
            <a href="{{ url_for('media') }}">📁 Manage Media</a>
            <a href="{{ url_for('upload') }}">⬆️ Upload Files</a>
        </div>

        {% with messages = get_flashed_messages() %}
        {% if messages %}
        <div class="flash-messages">
            {% for message in messages %}
            <div class="flash-message">{{ message }}</div>
            {% endfor %}
        </div>
        {% endif %}
        {% endwith %}

        <p style="text-align: center; color: #666;">
            For each button, pick an existing video <em>or</em> upload a new one.
            Saving applies the change immediately — next press of that button plays the chosen video.
        </p>

        <div class="button-grid">
            {% for b in buttons_data %}
            <div class="button-card">
                <h2>Button {{ b.id }}</h2>

                {% if b.current and b.file_exists %}
                <div class="current-mapping ok">▶ {{ b.current }}</div>
                {% elif b.current %}
                <div class="current-mapping missing">⚠ {{ b.current }} (file missing)</div>
                {% else %}
                <div class="current-mapping none">— no video assigned —</div>
                {% endif %}

                <form method="post" enctype="multipart/form-data">
                    <input type="hidden" name="button_id" value="{{ b.id }}">

                    <div class="form-row">
                        <label for="existing_{{ b.id }}">Pick an existing video:</label>
                        <select name="existing" id="existing_{{ b.id }}">
                            <option value="">-- none / use upload below --</option>
                            {% for v in existing_videos %}
                            <option value="{{ v }}" {% if v == b.current %}selected{% endif %}>{{ v }}</option>
                            {% endfor %}
                        </select>
                    </div>

                    <div class="or">— or —</div>

                    <div class="form-row">
                        <label for="video_{{ b.id }}">Upload a new video:</label>
                        <input type="file" name="video" id="video_{{ b.id }}" accept=".mp4,.avi,.mkv,.mov">
                    </div>

                    <button type="submit" class="save-btn">💾 Save Button {{ b.id }}</button>
                </form>
            </div>
            {% endfor %}
        </div>
    </div>
</body>
</html>
'''
