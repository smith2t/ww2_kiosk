import asyncio
import json
import logging
import os
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Optional

from flask import Flask, render_template, render_template_string, request, redirect, url_for, flash, jsonify
from werkzeug.utils import secure_filename

from media.thumbnailer import ensure_thumbnail

logger = logging.getLogger(__name__)


class WebInterface:
    def __init__(self, settings, store=None, controller=None):
        self.settings = settings
        self.store = store
        self.controller = controller
        self.app = Flask(__name__, template_folder="templates")
        self.app.secret_key = 'ww2-kiosk-secret-key'  # TODO: Make this configurable
        # Allow up to 5 GB per request (large video bundles); werkzeug's default
        # silently rejects over-size multipart bodies with HTTP 400.
        self.app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024 * 1024

        @self.app.errorhandler(413)
        def too_large(e):
            flash('Upload too large (5 GB max). Try fewer files at once.')
            return redirect(url_for('upload'))

        @self.app.errorhandler(400)
        def bad_request(e):
            flash(f'Upload failed (HTTP 400): {e.description or "malformed request"}. '
                  'Often caused by a network drop mid-upload — try fewer/smaller '
                  'files or use a wired connection.')
            return redirect(url_for('upload'))

        self.media_dir = Path(settings.media.pictures_dir)
        self.video_dir = Path(settings.media.videos_dir)
        self.button_mappings_file = Path(settings.config.button_mappings_file)
        self.categories_file = self.button_mappings_file.parent / "categories.json"

        # Ensure directories exist
        self.media_dir.mkdir(parents=True, exist_ok=True)
        self.video_dir.mkdir(parents=True, exist_ok=True)

        self.setup_routes()

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
                saved, skipped, converted, failed_convert = [], [], [], []

                for f in files:
                    # Folder uploads preserve relative paths in filename
                    # (e.g. "vacation/img.jpg") — flatten to basename so the
                    # kiosk's flat-dir scanner finds the file.
                    base = f.filename.rsplit('/', 1)[-1].rsplit('\\', 1)[-1]
                    if not self._allowed_file(base, upload_type):
                        skipped.append(base)
                        continue
                    safe = secure_filename(base)
                    saved_path = target_dir / safe
                    f.save(str(saved_path))

                    # PPTX/PPT can't be played natively — convert to PDF on
                    # upload so they flow through the PDF pipeline. The
                    # original is removed; the picker sees only the PDF.
                    if safe.lower().rsplit('.', 1)[-1] in ('pptx', 'ppt'):
                        pdf_path = self._convert_pptx_to_pdf(saved_path)
                        if pdf_path is not None:
                            try:
                                saved_path.unlink()
                            except OSError:
                                pass
                            converted.append(pdf_path.name)
                            # Pre-generate the thumbnail so the catalog editor shows it immediately.
                            # Failure is non-fatal — the editor falls back to a placeholder.
                            try:
                                ensure_thumbnail(pdf_path)
                            except Exception as e:
                                logger.warning(f"thumbnail pre-generation failed for {pdf_path}: {e}")
                        else:
                            failed_convert.append(safe)
                    else:
                        saved.append(safe)
                        # Pre-generate the thumbnail so the catalog editor shows it immediately.
                        # Failure is non-fatal — the editor falls back to a placeholder.
                        try:
                            ensure_thumbnail(saved_path)
                        except Exception as e:
                            logger.warning(f"thumbnail pre-generation failed for {saved_path}: {e}")

                if saved:
                    flash(f'Uploaded {len(saved)} file(s): {", ".join(saved[:5])}'
                          + (f' and {len(saved) - 5} more' if len(saved) > 5 else ''))
                if converted:
                    flash(f'Converted PPTX → PDF: {", ".join(converted[:5])}'
                          + (f' and {len(converted) - 5} more' if len(converted) > 5 else ''))
                if failed_convert:
                    flash(f'PPTX conversion failed for: {", ".join(failed_convert)}. '
                          'Check that LibreOffice is installed (soffice in PATH).')
                if skipped:
                    flash(f'Skipped {len(skipped)} file(s) with invalid type: '
                          + ", ".join(skipped[:3])
                          + (f' and {len(skipped) - 3} more' if len(skipped) > 3 else ''))

                return redirect(url_for('media'))

            return render_template_string(UPLOAD_TEMPLATE)

        @self.app.route('/settings', methods=['GET', 'POST'])
        def settings_page():
            from config.settings import Settings as _S
            try:
                import yaml as _yaml
            except ImportError:
                flash('PyYAML not installed — cannot edit settings.')
                return redirect(url_for('index'))

            cfg_path = Path(self.settings.config.config_file)

            if request.method == 'POST':
                try:
                    new_values = {
                        'slideshow_interval': int(request.form.get('slideshow_interval', 10)),
                        'menu_timeout_sec':   int(request.form.get('menu_timeout_sec', 30)),
                        'countdown_sec':      int(request.form.get('countdown_sec', 3)),
                        'pdf_page_duration':  int(request.form.get('pdf_page_duration', 8)),
                        'shuffle_slideshow':  request.form.get('shuffle_slideshow') == 'on',
                    }
                except ValueError:
                    flash('Settings must be whole numbers.')
                    return redirect(url_for('settings_page'))

                # Merge into existing config.yaml, leaving everything else untouched.
                cfg = {}
                if cfg_path.exists():
                    try:
                        with open(cfg_path) as f:
                            cfg = _yaml.safe_load(f) or {}
                    except Exception as e:
                        logger.error(f"Reading {cfg_path} failed: {e}")
                cfg.setdefault('display', {})
                for k, v in new_values.items():
                    cfg['display'][k] = v
                try:
                    cfg_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(cfg_path, 'w') as f:
                        _yaml.safe_dump(cfg, f, sort_keys=False)
                    # Apply live to the running kiosk: same Settings object is
                    # used by display_controller / main, so reload picks them up.
                    self.settings.reload()
                    flash('Settings saved (applied live, no restart needed).')
                except Exception as e:
                    logger.error(f"Saving {cfg_path} failed: {e}")
                    flash(f'Save failed: {e}')

                # AP credentials are stored in NetworkManager, not config.yaml.
                # Blank password field means "keep existing"; SSID is always
                # required.
                self._apply_ap_credentials(
                    request.form.get('ap_ssid', '').strip(),
                    request.form.get('ap_password', ''),
                )

                return redirect(url_for('settings_page'))

            # GET: render the form pre-populated with current values.
            d = self.settings.display
            return render_template_string(
                SETTINGS_TEMPLATE,
                values={
                    'slideshow_interval': getattr(d, 'slideshow_interval', 10),
                    'menu_timeout_sec':   getattr(d, 'menu_timeout_sec', 30),
                    'countdown_sec':      getattr(d, 'countdown_sec', 3),
                    'pdf_page_duration':  getattr(d, 'pdf_page_duration', 8),
                    'shuffle_slideshow':  getattr(d, 'shuffle_slideshow', True),
                    'ap_ssid':            self._read_ap_ssid(),
                },
            )

        # Both legacy routes are superseded by the v2 drill-down editor at
        # /settings/catalog. They redirect there so old bookmarks still work
        # and — critically — so the old v1 save path can't overwrite the v2
        # tree with the now-absent "categories" key.
        @self.app.route('/buttons')
        def buttons_legacy():
            return redirect('/settings/catalog')

        @self.app.route('/categories', methods=['GET', 'POST'])
        def categories():
            return redirect('/settings/catalog')

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

        @self.app.route('/settings/catalog')
        def settings_catalog_root():
            slots = []
            colors = {"1": "blue", "2": "green", "3": "yellow", "4": "red"}
            for slot_id in ("1", "2", "3", "4"):
                slots.append((slot_id, self.store.get_root_slot(slot_id),
                              colors[slot_id]))
            return render_template("catalog_root.html", slots=slots)

        @self.app.route("/settings/catalog/<path:catalog_path>")
        def settings_catalog_view(catalog_path):
            from flask import render_template, abort
            from input.category_store import parse_path, format_path
            from media.thumbnailer import ensure_thumbnail
            try:
                path = parse_path(catalog_path)
            except ValueError:
                abort(404)
            node = self.store.resolve(path)
            if node is None:
                abort(404)

            breadcrumbs = []
            for i in range(1, len(path) + 1):
                ancestor = self.store.resolve(path[:i])
                label = ancestor.title if ancestor else f"slot {path[0]}"
                link = (f"/settings/catalog/{format_path(path[:i])}"
                        if i < len(path) else None)
                breadcrumbs.append((label, link))

            child_paths = []
            for i, child in enumerate(getattr(node, 'children', []) or []):
                child_paths.append(format_path(path + [i]))
                if child.kind.value in ("video", "pdf"):
                    full = self._resolve_media_path(child.file)
                    if full:
                        ensure_thumbnail(full)
                        child.thumb_url = f"/thumb/{child.file}"
                    else:
                        child.thumb_url = None
                elif child.kind.value == "pictureset" and child.files:
                    child.thumb_url = f"/pictureset-thumb/{format_path(path + [i])}"
                else:
                    child.thumb_url = None

            files = self._media_file_lists()
            return render_template(
                "catalog_view.html",
                node=node,
                path_str=format_path(path),
                breadcrumbs=breadcrumbs,
                child_paths=child_paths,
                can_add_subcategory=(len(path) < 2),
                video_files=files["videos"],
                pdf_files=files["pdfs"],
                picture_files=files["pictures"],
                all_files=files["all"],
                zip=zip,
            )

        @self.app.route("/settings/catalog/<path:catalog_path>/save", methods=["POST"])
        def settings_catalog_save(catalog_path):
            from flask import request, redirect, abort
            from input.category_store import parse_path, Node, NodeKind, format_path
            try:
                path = parse_path(catalog_path)
            except ValueError:
                abort(400)
            node = self.store.resolve(path)
            if node is None:
                abort(404)

            new_title = request.form.get("title", node.title)
            if node.kind in (NodeKind.VIDEO, NodeKind.PDF):
                new = Node(kind=node.kind, title=new_title,
                           file=request.form.get("file", node.file))
            elif node.kind is NodeKind.PICTURESET:
                files = [l.strip() for l in
                         request.form.get("files", "").splitlines() if l.strip()]
                captions = request.form.get("captions", "").splitlines()
                while len(captions) < len(files):
                    captions.append("")
                captions = captions[:len(files)]
                interval = int(request.form.get("interval_sec", node.interval_sec))
                new = Node(kind=node.kind, title=new_title, files=files,
                           captions=captions, interval_sec=interval)
            elif node.kind is NodeKind.CATEGORY:
                new = Node(kind=node.kind, title=new_title, children=node.children)
            else:
                abort(400)

            try:
                self.store.replace_node(path, new)
            except ValueError as e:
                return f"Save rejected: {e}", 400
            return redirect(f"/settings/catalog/{format_path(path)}")


        @self.app.route("/settings/catalog/<path:catalog_path>/add-child", methods=["POST"])
        def settings_catalog_add_child(catalog_path):
            from flask import request, redirect, abort
            from input.category_store import parse_path, Node, NodeKind, format_path
            try:
                path = parse_path(catalog_path)
            except ValueError:
                abort(400)
            kind = request.form.get("kind")
            title = request.form.get("title", "")
            file = request.form.get("file", "")
            try:
                k = NodeKind(kind)
            except ValueError:
                return f"unknown kind: {kind}", 400
            if k is NodeKind.CATEGORY:
                new = Node(kind=k, title=title, children=[])
            elif k in (NodeKind.VIDEO, NodeKind.PDF):
                new = Node(kind=k, title=title, file=file)
            elif k is NodeKind.PICTURESET:
                if not file:
                    return ("Picture-sets must be created via the dedicated form "
                            "(no files set yet)."), 400
                new = Node(kind=k, title=title, files=[file],
                           captions=[""], interval_sec=6)
            else:
                return f"unknown kind: {kind}", 400
            try:
                self.store.add_child(path, new)
            except ValueError as e:
                return f"Add rejected: {e}", 400
            return redirect(f"/settings/catalog/{format_path(path)}")


        @self.app.route("/settings/catalog/<path:catalog_path>/reorder", methods=["POST"])
        def settings_catalog_reorder(catalog_path):
            from flask import request, abort
            from input.category_store import parse_path
            try:
                path = parse_path(catalog_path)
            except ValueError:
                abort(400)
            order = (request.get_json(silent=True) or {}).get("order")
            if not isinstance(order, list):
                return "order must be a list", 400
            try:
                self.store.reorder_children(path, [int(i) for i in order])
            except ValueError as e:
                return f"Reorder rejected: {e}", 400
            return "", 204


        @self.app.route("/settings/catalog/<path:catalog_path>/delete", methods=["POST"])
        def settings_catalog_delete(catalog_path):
            from flask import redirect, abort
            from input.category_store import parse_path, format_path
            try:
                path = parse_path(catalog_path)
            except ValueError:
                abort(400)
            try:
                self.store.delete_node(path)
            except ValueError as e:
                return f"Delete rejected: {e}", 400
            parent_path = path[:-1]
            return redirect("/settings/catalog" if not parent_path
                            else f"/settings/catalog/{format_path(parent_path)}")


        @self.app.route("/thumb/<path:basename>")
        def serve_thumb(basename):
            from flask import send_file, abort
            from media.thumbnailer import ensure_thumbnail
            full = self._resolve_media_path(basename)
            if full is None:
                abort(404)
            thumb = ensure_thumbnail(full)
            if thumb is None or not thumb.exists():
                abort(404)
            return send_file(thumb, mimetype="image/png")

        @self.app.route("/pictureset-thumb/<path:catalog_path>")
        def serve_pictureset_thumb(catalog_path):
            from flask import send_file, abort
            from pathlib import Path
            from input.category_store import parse_path, NodeKind
            from media.thumbnailer import compose_pictureset_thumbnail, _cache_dir
            import hashlib
            try:
                path = parse_path(catalog_path)
            except ValueError:
                abort(404)
            node = self.store.resolve(path)
            if node is None or node.kind is not NodeKind.PICTURESET:
                abort(404)
            pics_dir = Path(self.settings.media.pictures_dir)
            file_paths = [pics_dir / f for f in node.files]
            key = hashlib.sha1(("|".join(node.files)).encode("utf-8")).hexdigest()
            out = _cache_dir(pics_dir / "x") / f"pictureset-{key}.png"
            if not out.exists():
                if compose_pictureset_thumbnail(file_paths, out) is None:
                    abort(500)
            return send_file(out, mimetype="image/png")

        @self.app.route('/api/status')
        def api_status():
            """API endpoint for kiosk status"""
            return jsonify({
                'status': 'running',
                'media_count': len(list(self.media_dir.glob('*'))),
                'video_count': len(list(self.video_dir.glob('*'))),
                'uptime': '24h'  # TODO: Calculate actual uptime
            })

    def _resolve_media_path(self, basename):
        from pathlib import Path
        for d in (self.settings.media.videos_dir,
                  self.settings.media.pictures_dir):
            p = Path(d) / basename
            if p.exists():
                return p
        return None

    def _media_file_lists(self) -> dict:
        """Sorted basenames of media on disk, split by kind, for the catalog
        editor's file pickers. videos come from videos_dir; PDFs/images from
        pictures_dir (PDFs may also live in videos_dir)."""
        from pathlib import Path
        vdir = Path(self.settings.media.videos_dir)
        pdir = Path(self.settings.media.pictures_dir)
        video_exts = {'.mp4', '.avi', '.mkv', '.mov', '.webm'}
        image_exts = {'.jpg', '.jpeg', '.png', '.bmp', '.gif'}

        def names(d, exts):
            if not d.exists():
                return []
            return sorted(p.name for p in d.iterdir()
                          if p.is_file() and p.suffix.lower() in exts)

        videos = names(vdir, video_exts)
        pdfs = sorted(set(names(vdir, {'.pdf'}) + names(pdir, {'.pdf'})))
        pictures = names(pdir, image_exts)
        return {
            "videos": videos,
            "pdfs": pdfs,
            "pictures": pictures,
            "all": sorted(set(videos + pdfs + pictures)),
        }

    def _load_button_data(self) -> dict:
        """Return both mappings and descriptions; gracefully handles old files
        that lack the descriptions section."""
        if not self.button_mappings_file.exists():
            return {'mappings': {}, 'descriptions': {}}
        try:
            with open(self.button_mappings_file) as f:
                data = json.load(f)
            return {
                'mappings': data.get('mappings', {}) or {},
                'descriptions': data.get('descriptions', {}) or {},
            }
        except Exception as e:
            logger.error(f"Failed to load button mappings: {e}")
            return {'mappings': {}, 'descriptions': {}}

    def _save_button_data(self, mappings: dict, descriptions: dict) -> None:
        try:
            self.button_mappings_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.button_mappings_file, 'w') as f:
                json.dump({'mappings': mappings,
                           'descriptions': descriptions},
                          f, indent=2)
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

    _AP_PROFILE = "ww2-kiosk-ap"

    def _read_ap_ssid(self) -> str:
        """Read the current AP SSID from NetworkManager. Returns "" if the
        profile doesn't exist (fresh image / AP fallback not installed)."""
        try:
            result = subprocess.run(
                ['nmcli', '-t', '-g', '802-11-wireless.ssid',
                 'c', 'show', self._AP_PROFILE],
                capture_output=True, text=True, timeout=5,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return ""
        if result.returncode != 0:
            return ""
        return result.stdout.strip()

    def _apply_ap_credentials(self, new_ssid: str, new_psk: str) -> None:
        """Update the NM AP profile's SSID and/or PSK. Blank PSK is treated
        as "leave unchanged". New values take effect next time the AP
        activates — this does not bounce the AP, so an admin currently
        connected via AP stays connected on the old credentials until they
        reconnect."""
        if not new_ssid:
            flash('AP SSID is required.')
            return

        if len(new_ssid) > 32:
            flash('AP SSID must be 32 characters or fewer.')
            return

        if new_psk and not (8 <= len(new_psk) <= 63):
            flash('AP password must be 8–63 characters (WPA2 requirement).')
            return

        current_ssid = self._read_ap_ssid()
        changes = []

        if new_ssid != current_ssid and current_ssid != "":
            ok = self._nmcli_modify('802-11-wireless.ssid', new_ssid)
            if ok:
                changes.append(f'SSID → {new_ssid}')
            else:
                flash('Failed to update AP SSID — check journalctl for nmcli errors.')
                return
        elif current_ssid == "":
            flash('AP profile not found on this kiosk — run install_ap_fallback.sh first.')
            return

        if new_psk:
            ok = self._nmcli_modify('wifi-sec.psk', new_psk)
            if ok:
                changes.append('password updated')
            else:
                flash('Failed to update AP password — check journalctl for nmcli errors.')
                return

        if changes:
            flash(f'AP credentials saved ({", ".join(changes)}). Changes apply on next AP activation.')

    def _nmcli_modify(self, key: str, value: str) -> bool:
        """Run `sudo nmcli c modify <profile> <key> <value>` for the AP profile.
        Requires the sysadmin sudoers entry in /etc/sudoers.d/ww2-kiosk-nmcli."""
        try:
            result = subprocess.run(
                ['sudo', '-n', 'nmcli', 'c', 'modify', self._AP_PROFILE, key, value],
                capture_output=True, text=True, timeout=10,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            logger.error(f"nmcli modify {key} failed: {e}")
            return False
        if result.returncode != 0:
            logger.error(f"nmcli modify {key} returned {result.returncode}: {result.stderr.strip()}")
            return False
        return True

    def _convert_pptx_to_pdf(self, pptx_path: Path) -> Optional[Path]:
        """Convert a PowerPoint file to PDF using LibreOffice headless.

        Returns the resulting PDF path on success (in the same directory as
        the source), or None if conversion fails. soffice is slow (10–30s
        per deck) so callers should expect the upload request to block.
        """
        out_dir = pptx_path.parent
        try:
            result = subprocess.run(
                ['soffice', '--headless', '--convert-to', 'pdf',
                 '--outdir', str(out_dir), str(pptx_path)],
                capture_output=True, text=True, timeout=120,
            )
        except FileNotFoundError:
            logger.error("soffice (LibreOffice) not found in PATH — install libreoffice-impress")
            return None
        except subprocess.TimeoutExpired:
            logger.error(f"soffice timed out converting {pptx_path.name}")
            return None

        if result.returncode != 0:
            logger.error(f"soffice failed on {pptx_path.name}: {result.stderr.strip()}")
            return None

        pdf_path = out_dir / (pptx_path.stem + '.pdf')
        if not pdf_path.exists():
            logger.error(f"soffice returned success but {pdf_path.name} not found")
            return None

        logger.info(f"Converted {pptx_path.name} -> {pdf_path.name}")
        return pdf_path

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
            <a href="/settings/catalog">🎛️ Configure Categories</a>
            <a href="{{ url_for('settings_page') }}">⚙️ Settings</a>
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
                    <option value="media">Pictures & Documents (images for slideshow, PDFs/PowerPoint for category items)</option>
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
                <div id="conversion-note" style="margin-top:8px; padding:8px 10px; background:#fff4cc; border:1px solid #e6c200; border-radius:4px; color:#5c4a00; font-size:13px;">
                    ⚠️ <strong>PowerPoint (.pptx / .ppt) files are auto-converted to PDF on upload.</strong>
                    Conversion takes about 10–30 seconds per deck — the upload page will appear
                    to hang while LibreOffice runs. The original .pptx is removed; only the resulting
                    .pdf appears in the category picker.
                </div>
            </div>

            <button type="submit" class="upload-btn">📤 Upload Files</button>
        </form>
    </div>

    <script>
        function updateFileTypes() {
            const uploadType = document.getElementById('upload_type').value;
            const formatsSpan = document.getElementById('supported-formats');
            const note = document.getElementById('conversion-note');

            if (uploadType === 'media') {
                formatsSpan.innerHTML = 'Images: JPG, PNG, GIF, BMP<br>Documents: PDF, PowerPoint (.pptx, .ppt)';
                note.style.display = '';
            } else {
                formatsSpan.innerHTML = 'Videos: MP4, AVI, MKV, MOV';
                note.style.display = 'none';
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
        .button-card h2 { margin-top: 0; }
        .button-card.btn-Blue   { border-color: #2563eb; }
        .button-card.btn-Blue   h2 { color: #2563eb; }
        .button-card.btn-Green  { border-color: #16a34a; }
        .button-card.btn-Green  h2 { color: #16a34a; }
        .button-card.btn-Yellow { border-color: #ca8a04; }
        .button-card.btn-Yellow h2 { color: #ca8a04; }
        .button-card.btn-Red    { border-color: #dc2626; }
        .button-card.btn-Red    h2 { color: #dc2626; }
        textarea { width: 100%; padding: 8px; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box; font-family: inherit; resize: vertical; }
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
            <div class="button-card btn-{{ b.color }}">
                <h2>Button {{ b.id }} — {{ b.color }}</h2>

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

                    <div class="form-row">
                        <label for="description_{{ b.id }}">Description (shown on the menu screen):</label>
                        <textarea name="description" id="description_{{ b.id }}" rows="2"
                                  placeholder="e.g. Battle of Midway, June 1942">{{ b.description }}</textarea>
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




SETTINGS_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Settings - WW2 Kiosk</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }
        .container { max-width: 760px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        h1 { color: #333; text-align: center; }
        .nav-menu { text-align: center; margin: 20px 0; }
        .nav-menu a { display: inline-block; margin: 0 10px; padding: 10px 20px; background: #007bff; color: white; text-decoration: none; border-radius: 4px; }
        .nav-menu a:hover { background: #0056b3; }
        .help { color: #555; font-size: 14px; text-align: center; margin: 8px 0 18px; }
        form { display: grid; gap: 14px; margin-top: 12px; }
        .row { display: grid; grid-template-columns: 1fr 120px; gap: 14px; align-items: center; padding: 10px 14px; background: #fafafa; border: 1px solid #eee; border-radius: 6px; }
        .row .label { font-weight: bold; }
        .row .desc { color: #555; font-size: 13px; margin-top: 2px; }
        input[type="number"] { width: 100%; padding: 8px; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box; font: inherit; text-align: right; }
        input[type="checkbox"] { transform: scale(1.4); margin-right: 8px; }
        .save-btn { background: #16a34a; color: white; padding: 12px 20px; border: none; border-radius: 4px; cursor: pointer; font-size: 15px; font-weight: bold; }
        .save-btn:hover { background: #166534; }
        .flash-messages { margin: 20px 0; }
        .flash-message { padding: 10px; border-radius: 4px; margin: 5px 0; background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
    </style>
</head>
<body>
    <div class="container">
        <h1>⚙️ Settings</h1>
        <div class="nav-menu">
            <a href="{{ url_for('index') }}">🏠 Home</a>
            <a href="{{ url_for('media') }}">📁 Manage Media</a>
            <a href="{{ url_for('upload') }}">⬆️ Upload Files</a>
            <a href="/settings/catalog">🎛️ Configure Categories</a>
        </div>

        <p class="help">Changes are applied to the running kiosk immediately —
            no restart needed.</p>

        {% with messages = get_flashed_messages() %}
        {% if messages %}
        <div class="flash-messages">
            {% for m in messages %}<div class="flash-message">{{ m }}</div>{% endfor %}
        </div>
        {% endif %}{% endwith %}

        <form method="post">
            <div class="row">
                <div>
                    <div class="label">Slideshow interval</div>
                    <div class="desc">Seconds each picture is shown in the attract loop.</div>
                </div>
                <input type="number" name="slideshow_interval" min="1" max="600"
                       value="{{ values.slideshow_interval }}">
            </div>

            <div class="row">
                <div>
                    <div class="label">Menu inactivity timeout</div>
                    <div class="desc">Seconds before the menu returns to the slideshow with no input.</div>
                </div>
                <input type="number" name="menu_timeout_sec" min="5" max="600"
                       value="{{ values.menu_timeout_sec }}">
            </div>

            <div class="row">
                <div>
                    <div class="label">Countdown before playback</div>
                    <div class="desc">Seconds the LED counts down (3, 2, 1) before a video or PDF starts. Set to 0 to skip.</div>
                </div>
                <input type="number" name="countdown_sec" min="0" max="10"
                       value="{{ values.countdown_sec }}">
            </div>

            <div class="row">
                <div>
                    <div class="label">PDF page duration</div>
                    <div class="desc">Seconds each PDF page is displayed before auto-advancing.</div>
                </div>
                <input type="number" name="pdf_page_duration" min="2" max="120"
                       value="{{ values.pdf_page_duration }}">
            </div>

            <div class="row">
                <div>
                    <div class="label">Shuffle slideshow</div>
                    <div class="desc">If on, slides cycle in random order instead of file-name order.</div>
                </div>
                <div>
                    <label><input type="checkbox" name="shuffle_slideshow"
                           {% if values.shuffle_slideshow %}checked{% endif %}> on</label>
                </div>
            </div>

            <h2 style="margin-top:30px; color:#333; border-bottom:1px solid #ddd; padding-bottom:6px;">📶 WiFi Access Point</h2>
            <p class="help">Used when home WiFi is unavailable for 90 s, or whenever
                an admin connects locally to manage the kiosk. Changes take effect
                on the next AP activation — connected clients keep the old credentials
                until they reconnect.</p>

            <div class="row">
                <div>
                    <div class="label">AP network name (SSID)</div>
                    <div class="desc">Up to 32 characters. Shown on phone/laptop WiFi lists.</div>
                </div>
                <input type="text" name="ap_ssid" maxlength="32" required
                       value="{{ values.ap_ssid }}"
                       style="width:100%; padding:8px; border:1px solid #ccc; border-radius:4px; box-sizing:border-box; font:inherit; text-align:right;">
            </div>

            <div class="row">
                <div>
                    <div class="label">AP password</div>
                    <div class="desc">8–63 characters (WPA2). Leave blank to keep the current password.</div>
                </div>
                <input type="password" name="ap_password" minlength="8" maxlength="63"
                       autocomplete="new-password" placeholder="(unchanged)"
                       style="width:100%; padding:8px; border:1px solid #ccc; border-radius:4px; box-sizing:border-box; font:inherit; text-align:right;">
            </div>

            <button type="submit" class="save-btn">💾 Save settings</button>
        </form>
    </div>
</body>
</html>
'''
