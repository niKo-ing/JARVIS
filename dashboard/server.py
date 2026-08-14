"""
dashboard/server.py — JARVIS Local HTTP Dashboard

Plain HTTP on port 8000 (no SSL warnings, no firewall issues).
Security at the application layer: AES-256-CBC with session-key-derived key.
CryptoJS is auto-downloaded once and served locally — no CDN needed after that.

Install deps:  pip install fastapi "uvicorn[standard]" cryptography
"""

import asyncio
import base64
import hashlib
import re
import secrets
import socket
import string
import time
from pathlib import Path

_DEPS_OK = False
try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
    from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
    import uvicorn
    _DEPS_OK = True
except ImportError:
    pass

# python-multipart is required for file uploads — optional dependency
_UPLOAD_OK = False
try:
    from fastapi import UploadFile, File as FastAPIFile
    _UPLOAD_OK = True
except Exception:
    pass

BASE_DIR    = Path(__file__).resolve().parent.parent
STATIC_DIR  = Path(__file__).parent / "static"
PORT        = 8000
MAX_UPLOAD_MB = 500

TASKS_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
<title>JARVIS — Tareas y Notas</title>
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  body{background:#0a0c14;color:#dde3ed;font-family:-apple-system,sans-serif;padding:16px;max-width:600px;margin:0 auto}
  h1{font-size:20px;margin:12px 0 16px;color:#00e676;text-align:center}
  h2{font-size:14px;color:#8892a4;margin:16px 0 8px;text-transform:uppercase;letter-spacing:1px}
  .card{background:#11141f;border-radius:10px;padding:14px;margin-bottom:12px;border:1px solid #1e2333}
  .task-title{font-size:15px;font-weight:600}
  .task-desc{font-size:13px;color:#8892a4;margin-top:4px}
  .task-meta{font-size:11px;color:#5e6a7e;margin-top:6px;display:flex;gap:8px}
  .priority-alta{color:#f87171;font-weight:600}
  .priority-media{color:#fbbf24}
  .priority-baja{color:#6ee7b7}
  .badge{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600}
  .badge-alta{background:#2a000a;color:#f87171;border:1px solid #f87171}
  .badge-media{background:#1a1a00;color:#fbbf24;border:1px solid #fbbf24}
  .badge-baja{background:#001a0a;color:#6ee7b7;border:1px solid #6ee7b7}
  .btn{background:#00e676;color:#000;border:none;border-radius:6px;padding:8px 16px;font-size:13px;font-weight:600;cursor:pointer}
  .btn-sm{padding:4px 10px;font-size:11px}
  .btn-outline{background:transparent;border:1px solid #1e2333;color:#8892a4}
  .btn-outline:hover{border-color:#00e676;color:#00e676}
  .btn-red{background:#f87171;color:#000}
  input,textarea,.input{background:#0a0c14;border:1px solid #1e2333;border-radius:6px;padding:10px;color:#dde3ed;font-size:14px;width:100%;margin-bottom:8px}
  input:focus,textarea:focus{outline:none;border-color:#00e676}
  textarea{resize:vertical;min-height:60px;font-family:inherit}
  .flex{display:flex;gap:8px;flex-wrap:wrap}
  .flex-between{display:flex;justify-content:space-between;align-items:center}
  .mt-8{margin-top:8px}
  .mb-8{margin-bottom:8px}
  .note-item{padding:8px 0;border-bottom:1px solid #1e2333;font-size:13px;cursor:pointer}
  .note-item:last-child{border:none}
  .note-preview{color:#8892a4;font-size:12px;margin-top:2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .tab{display:inline-block;padding:8px 20px;cursor:pointer;border-radius:6px 6px 0 0;font-size:13px;color:#5e6a7e}
  .tab.active{background:#11141f;color:#00e676;font-weight:600}
  .tab-bar{margin-bottom:12px;border-bottom:1px solid #1e2333}
  .error{color:#f87171;font-size:13px;text-align:center;margin:20px 0}
  .center{text-align:center}
  .empty{color:#5e6a7e;font-size:13px;text-align:center;margin:20px 0}
</style>
</head>
<body>
<div class="tab-bar">
  <span class="tab active" onclick="switchTab('tasks')" id="tab-tasks">📋 Tareas</span>
  <span class="tab" onclick="switchTab('notes')" id="tab-notes">📝 Notas</span>
</div>

<div id="view-tasks">
  <div class="flex-between mb-8">
    <h2 style="margin:0">Pendientes</h2>
    <button class="btn btn-sm" onclick="showAddTask()">+ Nueva</button>
  </div>
  <div id="add-task-form" style="display:none" class="card">
    <input id="task-title" placeholder="Título de la tarea">
    <textarea id="task-desc" placeholder="Descripción (opcional)"></textarea>
    <div class="flex">
      <input type="date" id="task-date" style="flex:1">
      <select id="task-priority" class="input" style="flex:0 0 100px">
        <option value="alta">Alta</option>
        <option value="media" selected>Media</option>
        <option value="baja">Baja</option>
      </select>
    </div>
    <div class="flex mt-8">
      <button class="btn btn-sm" onclick="addTask()">Guardar</button>
      <button class="btn btn-sm btn-outline" onclick="hideAddTask()">Cancelar</button>
    </div>
  </div>
  <div id="task-list"></div>
</div>

<div id="view-notes" style="display:none">
  <div class="flex-between mb-8">
    <h2 style="margin:0">Notas</h2>
    <button class="btn btn-sm" onclick="showAddNote()">+ Nueva</button>
  </div>
  <div id="add-note-form" style="display:none" class="card">
    <input id="note-title" placeholder="Título de la nota">
    <textarea id="note-content" placeholder="Contenido de la nota" style="min-height:100px"></textarea>
    <div class="flex mt-8">
      <button class="btn btn-sm" onclick="addNote()">Guardar</button>
      <button class="btn btn-sm btn-outline" onclick="hideAddNote()">Cancelar</button>
    </div>
  </div>
  <input id="note-search" placeholder="🔍 Buscar en notas..." oninput="searchNotes(this.value)">
  <div id="note-list"></div>
</div>

<div id="note-detail" style="display:none" class="card">
  <div class="flex-between"><h2 id="detail-title"></h2><button class="btn btn-sm btn-outline" onclick="closeDetail()">✕</button></div>
  <pre id="detail-content" style="font-size:13px;margin-top:8px;white-space:pre-wrap;color:#8892a4"></pre>
</div>

<div id="login-msg" class="error" style="display:none">Conectando a JARVIS...</div>

<script>
let token = sessionStorage.getItem('jarvis_token') || '';
let key = sessionStorage.getItem('jarvis_key') || '';
let deviceToken = localStorage.getItem('jarvis_device_token') || '';

async function api(method, path, body) {
  const opts = {method, headers:{'Authorization':'Bearer '+token}};
  if (body) {opts.headers['Content-Type']='application/json'; opts.body=JSON.stringify(body);}
  const r = await fetch('/api'+path, opts);
  if (r.status===401) {document.getElementById('login-msg').style.display='block'; return null;}
  return r.json();
}

function switchTab(tab) {
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
  document.getElementById('tab-'+tab).classList.add('active');
  document.getElementById('view-tasks').style.display = tab==='tasks' ? 'block' : 'none';
  document.getElementById('view-notes').style.display = tab==='notes' ? 'block' : 'none';
  if (tab==='tasks') loadTasks();
  else loadNotes();
}

function showAddTask(){document.getElementById('add-task-form').style.display='block'}
function hideAddTask(){document.getElementById('add-task-form').style.display='none'}
function showAddNote(){document.getElementById('add-note-form').style.display='block'}
function hideAddNote(){document.getElementById('add-note-form').style.display='none'}

async function addTask() {
  const title = document.getElementById('task-title').value.trim();
  if (!title) return;
  await api('POST', '/tasks', {title, description: document.getElementById('task-desc').value.trim(),
    due_date: document.getElementById('task-date').value, priority: document.getElementById('task-priority').value});
  document.getElementById('task-title').value=''; document.getElementById('task-desc').value='';
  hideAddTask(); loadTasks();
}

async function loadTasks() {
  const d = await api('GET', '/tasks');
  const el = document.getElementById('task-list');
  if (!d || !d.tasks) {el.innerHTML='<div class="error">Sin conexión</div>'; return;}
  if (!d.tasks.length) {el.innerHTML='<div class="empty">✨ No hay tareas pendientes</div>'; return;}
  el.innerHTML = d.tasks.map(t=>'<div class="card"><div class="flex-between"><span class="task-title">'+esc(t.title)+'</span><span class="badge badge-'+t.priority+'">'+t.priority+'</span></div>'+
    (t.description ? '<div class="task-desc">'+esc(t.description)+'</div>' : '')+
    '<div class="task-meta flex-between">'+
    (t.due_date ? '<span>📅 '+t.due_date+'</span>' : '<span></span>')+
    '<button class="btn btn-sm btn-outline" onclick="completeTask('+t.id+')">✓ Listo</button></div></div>').join('');
}

async function completeTask(id) {
  await api('POST', '/tasks/'+id+'/complete');
  loadTasks();
}

async function addNote() {
  const title = document.getElementById('note-title').value.trim();
  const content = document.getElementById('note-content').value.trim();
  if (!title||!content) return;
  await api('POST', '/notes', {title, content});
  document.getElementById('note-title').value=''; document.getElementById('note-content').value='';
  hideAddNote(); loadNotes();
}

async function loadNotes() {
  const d = await api('GET', '/notes');
  const el = document.getElementById('note-list');
  if (!d || !d.notes) {el.innerHTML='<div class="error">Sin conexión</div>'; return;}
  if (!d.notes.length) {el.innerHTML='<div class="empty">📝 Sin notas aún</div>'; return;}
  el.innerHTML = d.notes.map(f=>'<div class="note-item" onclick="openNote(\''+f+'\')">📄 '+esc(f.replace(/_/g,' ').replace(/\\.*/,''))+'</div>').join('');
}

async function openNote(file) {
  const d = await api('GET', '/notes/'+encodeURIComponent(file));
  if (!d) return;
  document.getElementById('detail-title').textContent = file.replace(/_/g,' ').replace(/\\.*/,'');
  document.getElementById('detail-content').textContent = d.content || '';
  document.getElementById('note-detail').style.display = 'block';
  document.getElementById('view-notes').style.display = 'none';
}

function closeDetail() {
  document.getElementById('note-detail').style.display = 'none';
  document.getElementById('view-notes').style.display = 'block';
}

let searchTimer;
async function searchNotes(q) {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(async () => {
    if (!q) {loadNotes(); return;}
    const d = await api('GET', '/notes/search/'+encodeURIComponent(q));
    const el = document.getElementById('note-list');
    if (!d||!d.results) return;
    if (!d.results.length) {el.innerHTML='<div class="empty">Sin resultados</div>'; return;}
    el.innerHTML = d.results.map(r=>'<div class="note-item" onclick="openNote(\''+r.file+'\')">📄 '+esc(r.file.replace(/_/g,' ').replace(/\\.*/,''))+
      '<div class="note-preview">'+esc(r.snippet)+'</div></div>').join('');
  }, 300);
}

function esc(s){const d=document.createElement('div');d.appendChild(document.createTextNode(s));return d.innerHTML;}

// Auto-login check
(async () => {
  if (!token) {
    document.getElementById('login-msg').style.display='block';
    document.getElementById('login-msg').textContent = 'Escanea el código QR en JARVIS o inicia sesión primero.';
    return;
  }
  const d = await api('GET', '/tasks');
  if (d) {document.getElementById('login-msg').style.display='none'; loadTasks();}
})();
</script>
</body>
</html>"""


def _make_uploads_dir() -> Path:
    """Return (and create) the cross-platform uploads folder."""
    for candidate in [
        Path.home() / "Downloads" / "JARVIS Uploads",
        Path.home() / "Documents" / "JARVIS Uploads",
        BASE_DIR / "uploads",
    ]:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate
        except Exception:
            pass
    return BASE_DIR / "uploads"


UPLOADS_DIR = _make_uploads_dir()

def _get_gemini_key() -> str | None:
    try:
        import json as _json
        with open(BASE_DIR / "config" / "api_keys.json", "r", encoding="utf-8") as f:
            return _json.load(f).get("gemini_api_key")
    except Exception:
        return None

_KEY_CHARS = [c for c in (string.ascii_uppercase + string.digits)
              if c not in ('O', 'I', 'L', '0', '1')]

# ── AES-256-CBC ───────────────────────────────────────────────────────────────
_AES_SALT = b'JARVIS-DASHBOARD-v1'


def _derive_key(session_key: str) -> bytes:
    """SHA-256(sessionKey‖salt) → 32-byte AES-256 key (microseconds, no PBKDF2 needed)."""
    return hashlib.sha256(session_key.encode('utf-8') + _AES_SALT).digest()


def _decrypt_cbc(aes_key: bytes, enc_b64: str) -> str:
    """Decrypt base64(IV[16] ‖ ciphertext) with AES-256-CBC + PKCS7."""
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives import padding as sym_pad
    raw      = base64.b64decode(enc_b64)
    iv, ct   = raw[:16], raw[16:]
    dec      = Cipher(algorithms.AES(aes_key), modes.CBC(iv)).decryptor()
    padded   = dec.update(ct) + dec.finalize()
    unpadder = sym_pad.PKCS7(128).unpadder()
    return (unpadder.update(padded) + unpadder.finalize()).decode('utf-8')


# ── CryptoJS (auto-download once, served locally) ─────────────────────────────
_CRYPTOJS_CDN  = ("https://cdnjs.cloudflare.com/ajax/libs/"
                  "crypto-js/4.2.0/crypto-js.min.js")
_CRYPTOJS_FILE = STATIC_DIR / "crypto-js.min.js"


def _ensure_network_access(port: int) -> None:
    """Cross-platform, best-effort: open port in the OS firewall for LAN access.

    Runs in a background thread — never blocks uvicorn startup.

    Windows : writes a .bat file, runs it elevated via Windows ShellExecuteW
              (native UAC dialog, guaranteed to appear). One-time setup.
    macOS   : osascript admin dialog if the Application Firewall is on.
    Linux   : pkexec GUI → sudo -n → prints manual command as fallback.
    """
    import sys, subprocess, os, tempfile, threading

    # ── Windows ──────────────────────────────────────────────────────────────
    if sys.platform == "win32":
        import ctypes, time

        port_rule = f"JARVIS Dashboard Port {port}"
        prog_rule  = "JARVIS Dashboard Python"
        py_exe     = sys.executable

        def _netsh_rule_exists(name: str) -> bool:
            try:
                r = subprocess.run(
                    ["netsh", "advfirewall", "firewall", "show", "rule", f"name={name}"],
                    capture_output=True, text=True, timeout=5,
                )
                return r.returncode == 0 and "No rules match" not in r.stdout
            except Exception:
                return False

        def _network_is_public() -> bool:
            try:
                r = subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-Command",
                     "(Get-NetConnectionProfile | "
                     "Where-Object {$_.NetworkCategory -eq 'Public'} | "
                     "Measure-Object).Count"],
                    capture_output=True, text=True, timeout=6,
                )
                return r.stdout.strip() not in ("", "0")
            except Exception:
                return False

        need_port    = not _netsh_rule_exists(port_rule)
        need_prog    = not _netsh_rule_exists(prog_rule)
        need_private = _network_is_public()

        if not need_port and not need_prog and not need_private:
            return  # already fully configured

        # Build a .bat file — netsh + powershell, runs fast when elevated
        bat_lines = ["@echo off"]
        if need_private:
            bat_lines.append(
                'powershell -NoProfile -NonInteractive -Command "'
                'Get-NetConnectionProfile | '
                "Where-Object {$_.NetworkCategory -eq 'Public'} | "
                'Set-NetConnectionProfile -NetworkCategory Private"'
            )
        if need_port:
            bat_lines.append(
                f'netsh advfirewall firewall add rule '
                f'name="{port_rule}" protocol=TCP dir=in '
                f'localport={port} action=allow'
            )
        if need_prog:
            bat_lines.append(
                f'netsh advfirewall firewall add rule '
                f'name="{prog_rule}" dir=in action=allow '
                f'program="{py_exe}" enable=yes'
            )

        bat_body = "\r\n".join(bat_lines) + "\r\n"
        fd, bat_path = tempfile.mkstemp(suffix=".bat", prefix="jarvis_fw_")
        try:
            os.write(fd, bat_body.encode("mbcs"))   # Windows cmd.exe expects ANSI
            os.close(fd)
        except Exception:
            try:
                os.close(fd)
            except Exception:
                pass
            return

        # ── Try running directly (succeeds when already admin) ────────────────
        try:
            r = subprocess.run(
                [bat_path], capture_output=True, timeout=8, shell=True
            )
            if r.returncode == 0:
                print(f"[Dashboard] Cortafuegos configurado para puerto {port}.")
                try:
                    os.unlink(bat_path)
                except Exception:
                    pass
                return
        except Exception:
            pass

        # ── ShellExecuteW: native UAC elevation (most reliable on Windows) ────
        # ShellExecuteW with verb "runas" always shows the UAC dialog regardless
        # of UAC level settings. Non-blocking — uvicorn is already running.
        print("[Dashboard] Configuración de red única requerida.")
        print("[Dashboard] >>> Aparecerá un diálogo de seguridad de Windows — haz clic en 'Sí' <<<")
        try:
            ret = ctypes.windll.shell32.ShellExecuteW(
                None,       # hwnd  (no parent window)
                "runas",    # verb  (request elevation)
                bat_path,   # file  (our .bat)
                None,       # params
                None,       # working dir
                0,          # SW_HIDE (run without a visible cmd window)
            )
            if int(ret) > 32:
                # ShellExecuteW returns immediately; bat finishes in ~1 second.
                # Sleep briefly so the rules are in place before the first retry.
                time.sleep(2)
                print(f"[Dashboard] Configuración de red completa — puerto {port} está abierto.")
                print("[Dashboard] Actualiza el navegador de tu teléfono para conectarte.")
            else:
                print("[Dashboard] La configuración no fue permitida.")
                print("[Dashboard] Las conexiones del teléfono pueden fallar hasta que JARVIS se ejecute como Administrador.")
        except Exception as e:
            print(f"[Dashboard] Error de configuración del cortafuegos: {e}")
        finally:
            # Cleanup after the bat has had time to run
            def _cleanup(path: str) -> None:
                time.sleep(5)
                try:
                    os.unlink(path)
                except Exception:
                    pass
            threading.Thread(target=_cleanup, args=(bat_path,), daemon=True).start()
        return

    # ── macOS ─────────────────────────────────────────────────────────────────
    if sys.platform == "darwin":
        fw_ctl = "/usr/libexec/ApplicationFirewall/socketfilterfw"
        try:
            r = subprocess.run(
                [fw_ctl, "--getglobalstate"], capture_output=True, text=True, timeout=5,
            )
            if "disabled" in r.stdout.lower():
                return  # firewall off — nothing to do

            py = sys.executable
            listed = subprocess.run(
                [fw_ctl, "--listapps"], capture_output=True, text=True, timeout=5,
            )
            if py in listed.stdout:
                return  # already allowed

            print("[Dashboard] Configuración de red única — ingresa tu contraseña en el diálogo de macOS.")
            subprocess.run(
                ["osascript", "-e",
                 f'do shell script "{fw_ctl} --add {py} && {fw_ctl} --unblockapp {py}"'
                 f' with administrator privileges'],
                timeout=60,
            )
        except Exception:
            pass  # macOS firewall is off by default — silent failure is fine
        return

    # ── Linux ─────────────────────────────────────────────────────────────────
    def _privileged(cmd: list[str]) -> bool:
        for prefix in (["pkexec"], ["sudo", "-n"]):
            try:
                r = subprocess.run(prefix + cmd, capture_output=True, timeout=30)
                if r.returncode == 0:
                    return True
            except Exception:
                pass
        return False

    try:  # ufw
        r = subprocess.run(["ufw", "status"], capture_output=True, text=True, timeout=5)
        if "active" in r.stdout.lower():
            if _privileged(["ufw", "allow", f"{port}/tcp"]):
                print(f"[Dashboard] ufw: puerto {port} permitido.")
            else:
                print(f"[Dashboard] Ejecuta manualmente:  sudo ufw allow {port}/tcp")
            return
    except FileNotFoundError:
        pass

    try:  # firewalld
        r = subprocess.run(
            ["firewall-cmd", "--state"], capture_output=True, text=True, timeout=5,
        )
        if "running" in r.stdout.lower():
            ok = (_privileged(["firewall-cmd", "--add-port", f"{port}/tcp", "--permanent"])
                  and _privileged(["firewall-cmd", "--reload"]))
            if ok:
                print(f"[Dashboard] firewalld: puerto {port} permitido.")
            else:
                print(f"[Dashboard] Ejecuta manualmente:  sudo firewall-cmd --add-port={port}/tcp --permanent && sudo firewall-cmd --reload")
            return
    except FileNotFoundError:
        pass

    try:  # iptables (not persistent but works until reboot)
        r = subprocess.run(["iptables", "-L", "INPUT", "-n"], capture_output=True, timeout=5)
        if r.returncode == 0:
            if _privileged(["iptables", "-A", "INPUT", "-p", "tcp", "--dport", str(port), "-j", "ACCEPT"]):
                print(f"[Dashboard] iptables: puerto {port} abierto.")
            else:
                print(f"[Dashboard] Ejecuta manualmente:  sudo iptables -A INPUT -p tcp --dport {port} -j ACCEPT")
    except FileNotFoundError:
        pass  # no iptables means firewall is probably off — nothing to do


def _ensure_crypto_js() -> None:
    if _CRYPTOJS_FILE.exists():
        return
    try:
        import urllib.request
        print("[Dashboard] Descargando CryptoJS (configuración única)…")
        urllib.request.urlretrieve(_CRYPTOJS_CDN, str(_CRYPTOJS_FILE))
        print("[Dashboard] CryptoJS en caché — se servirá localmente de ahora en adelante.")
    except Exception as e:
        print(f"[Dashboard] Descarga de CryptoJS falló: {e}")
        print("[Dashboard] El cifrado usará la carga CDN en el cliente como alternativa.")


_ensure_crypto_js()


# ── helpers ───────────────────────────────────────────────────────────────────

def _local_ip() -> str:
    """Return the best LAN-facing IPv4 address, no internet required."""
    # Method 1: route trick (fast, works when internet is available)
    for probe in ("8.8.8.8", "1.1.1.1", "192.168.1.1"):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.5)
            s.connect((probe, 80))
            ip = s.getsockname()[0]
            s.close()
            if not ip.startswith("127."):
                return ip
        except Exception:
            pass

    # Method 2: hostname resolution (works offline on most systems)
    try:
        ip = socket.gethostbyname(socket.gethostname())
        if not ip.startswith("127."):
            return ip
    except Exception:
        pass

    # Method 3: enumerate all interfaces (fully offline, no external deps)
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127.") and not ip.startswith("169.254."):
                return ip
    except Exception:
        pass

    return "127.0.0.1"


def _read(name: str) -> str:
    return (STATIC_DIR / name).read_text(encoding="utf-8")


# ── DashboardServer ───────────────────────────────────────────────────────────

class DashboardServer:

    def __init__(self):
        self._ip                          = _local_ip()
        self._tokens: set[str]            = set()
        self._token_keys: dict[str, str]  = {}   # auth_token → session_key
        self._aes_cache:  dict[str, bytes]= {}   # session_key → AES bytes
        self._clients: set[WebSocket]     = set()
        self._history: list[dict]         = []
        self._command_queue               = asyncio.Queue()
        self._wake_callback               = None
        self._connect_callback            = None
        self._pending_keys: dict[str, float] = {}
        self._device_sessions: dict[str, dict] = {}  # device_token → {session_key}
        self._phone_audio_queue: asyncio.Queue    = asyncio.Queue(maxsize=200)
        self._uploads_dir                 = UPLOADS_DIR
        self._login_html                  = _read("login.html")
        self._app_html                    = _read("app.html")
        self.app                          = self._build_app()

    # ── one-time key management ───────────────────────────────────────────

    def new_key(self, expiry_secs: int = 600) -> str:
        now = time.time()
        self._pending_keys = {k: v for k, v in self._pending_keys.items() if v > now}
        key = ''.join(secrets.choice(_KEY_CHARS) for _ in range(6))
        self._pending_keys[key] = now + expiry_secs
        return key

    @staticmethod
    def _ssl_enabled() -> bool:
        certs = BASE_DIR / "config" / "certs"
        return (certs / "jarvis.key").exists() and (certs / "jarvis.crt").exists()

    def get_url(self) -> str:
        proto = "https" if self._ssl_enabled() else "http"
        return f"{proto}://{self._ip}:{PORT}"

    def get_manual_url(self) -> str:
        """URL for manual browser entry. When HTTPS active, points to alias port (also HTTPS)."""
        if self._ssl_enabled():
            return f"{self._ip}:{PORT + 1}"
        return f"{self._ip}:{PORT}"

    def _aes_key(self, session_key: str) -> bytes:
        if session_key not in self._aes_cache:
            self._aes_cache[session_key] = _derive_key(session_key)
        return self._aes_cache[session_key]

    def _decrypt(self, token: str, enc_b64: str) -> str | None:
        sk = self._token_keys.get(token)
        if not sk:
            return None
        try:
            return _decrypt_cbc(self._aes_key(sk), enc_b64)
        except Exception:
            return None

    # ── callbacks ────────────────────────────────────────────────────────

    def set_wake_callback(self, fn) -> None:
        self._wake_callback = fn

    def set_connect_callback(self, fn) -> None:
        self._connect_callback = fn

    # ── broadcast ────────────────────────────────────────────────────────

    async def broadcast(self, msg: dict) -> None:
        self._history.append(msg)
        if len(self._history) > 300:
            self._history = self._history[-300:]
        dead: set[WebSocket] = set()
        for ws in list(self._clients):
            try:
                await ws.send_json(msg)
            except Exception:
                dead.add(ws)
        self._clients -= dead

    # ── FastAPI app ───────────────────────────────────────────────────────

    def _build_app(self) -> "FastAPI":
        app = FastAPI(docs_url=None, redoc_url=None)

        def _auth(req: Request) -> bool:
            tok = req.headers.get("authorization", "").removeprefix("Bearer ").strip()
            return bool(tok) and tok in self._tokens

        # serve CryptoJS from local cache, fallback to CDN redirect
        @app.get("/static/crypto.js")
        async def serve_crypto():
            if _CRYPTOJS_FILE.exists():
                return FileResponse(str(_CRYPTOJS_FILE),
                                    media_type="application/javascript")
            from fastapi.responses import RedirectResponse
            return RedirectResponse(_CRYPTOJS_CDN)

        @app.get("/login", response_class=HTMLResponse)
        async def login_page():
            return HTMLResponse(self._login_html)

        @app.get("/", response_class=HTMLResponse)
        async def index():
            html = (self._app_html
                    .replace("__IP__", self._ip)
                    .replace("__PORT__", str(PORT)))
            return HTMLResponse(html)

        @app.get("/tasks", response_class=HTMLResponse)
        async def tasks_page():
            return HTMLResponse(TASKS_HTML)

        @app.post("/login")
        async def login(req: Request):
            body    = await req.json()
            entered = str(body.get("pin", "")).strip().upper()
            now     = time.time()
            if entered in self._pending_keys and self._pending_keys[entered] > now:
                del self._pending_keys[entered]          # one-time use
                tok = secrets.token_urlsafe(32)
                self._tokens.add(tok)
                self._token_keys[tok] = entered
                self._aes_key(entered)                   # pre-derive & cache
                if self._connect_callback:
                    self._connect_callback()
                asyncio.create_task(self.broadcast(
                    {"type": "sys", "text": "Conexión remota establecida."}
                ))
                # Bearer token in response body — no cookies needed (works on any browser/HTTP)
                return JSONResponse({"ok": True, "token": tok})
            return JSONResponse({"ok": False, "error": "Clave inválida o expirada"},
                                status_code=401)

        @app.get("/auto-login")
        async def auto_login(key: str = ""):
            """QR code target — validates one-time key, creates session, redirects phone."""
            now = time.time()
            if not key or key not in self._pending_keys or self._pending_keys[key] <= now:
                return HTMLResponse("""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width">
<style>
  body{background:#07090f;color:#dde3ed;font-family:sans-serif;
       display:flex;align-items:center;justify-content:center;height:100vh;margin:0;text-align:center}
  h2{color:#f87171;margin-bottom:12px}p{color:#5e6a7e;font-size:14px}
</style></head>
<body><div><h2>Enlace Expirado</h2>
<p>Presiona <strong style="color:#dde3ed">Control Remoto</strong> en JARVIS para obtener un nuevo código QR.</p>
</div></body></html>""")

            del self._pending_keys[key]
            tok     = secrets.token_urlsafe(32)
            dev_tok = secrets.token_urlsafe(32)
            self._tokens.add(tok)
            self._token_keys[tok] = key
            self._aes_key(key)
            self._device_sessions[dev_tok] = {"session_key": key}

            if self._connect_callback:
                self._connect_callback()
            asyncio.create_task(self.broadcast(
                {"type": "sys", "text": "Conexión remota establecida mediante código QR."}
            ))

            return HTMLResponse(f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width">
<style>
  body{{background:#07090f;color:#dde3ed;font-family:sans-serif;
       display:flex;align-items:center;justify-content:center;height:100vh;margin:0;text-align:center}}
  p{{color:#5e6a7e;font-size:14px}}
</style></head>
<body>
<script>
  sessionStorage.setItem('jarvis_token','{tok}');
  sessionStorage.setItem('jarvis_key','{key}');
  localStorage.setItem('jarvis_device_token','{dev_tok}');
  setTimeout(function(){{location.replace('/')}},400);
</script>
<p>Conectando a JARVIS…</p>
</body></html>""")

        @app.post("/api/device-login")
        async def device_login_ep(req: Request):
            """Return a fresh auth token for a previously paired device token."""
            try:
                body = await req.json()
            except Exception:
                return JSONResponse({"ok": False}, status_code=400)
            dev_tok = (body.get("device_token") or "").strip()
            if not dev_tok or dev_tok not in self._device_sessions:
                return JSONResponse({"ok": False}, status_code=401)
            session_key = self._device_sessions[dev_tok]["session_key"]
            tok = secrets.token_urlsafe(32)
            self._tokens.add(tok)
            self._token_keys[tok] = session_key
            self._aes_key(session_key)
            if self._connect_callback:
                self._connect_callback()
            asyncio.create_task(self.broadcast(
                {"type": "sys", "text": "Dispositivo conocido reconectado automáticamente."}
            ))
            return JSONResponse({"ok": True, "token": tok, "key": session_key})

        @app.post("/api/revoke-devices")
        async def revoke_devices(req: Request):
            """Invalidate all persistent device tokens (admin action)."""
            if not _auth(req):
                return JSONResponse({"error": "No autorizado"}, status_code=401)
            count = len(self._device_sessions)
            self._device_sessions.clear()
            return JSONResponse({"ok": True, "revoked": count})

        @app.post("/api/command")
        async def command(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "No autorizado"}, status_code=401)
            body  = await req.json()
            token = req.headers.get("authorization", "").removeprefix("Bearer ").strip()
            enc   = body.get("enc", "")
            if enc:
                text = self._decrypt(token, enc)
                if text is None:
                    return JSONResponse({"error": "Descifrado fallido"}, status_code=400)
            else:
                text = (body.get("text") or "").strip()
            if text:
                await self._command_queue.put(text)
                if self._wake_callback:
                    self._wake_callback()
            return JSONResponse({"ok": True})

        @app.post("/api/wake")
        async def wake_ep(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "No autorizado"}, status_code=401)
            if self._wake_callback:
                self._wake_callback()
            return JSONResponse({"ok": True})

        # ── Phone mic real-time audio → Gemini Live ──────────────────────────

        @app.websocket("/ws/phone-audio")
        async def phone_audio_ws(websocket: WebSocket, token: str = ""):
            tok = token.strip()
            if not tok or tok not in self._tokens:
                await websocket.close(code=4001)
                return
            await websocket.accept()
            asyncio.create_task(self.broadcast(
                {"type": "sys", "text": "Micrófono del teléfono activo."}
            ))
            try:
                while True:
                    data = await websocket.receive_bytes()
                    try:
                        self._phone_audio_queue.put_nowait(
                            {"data": data, "mime_type": "audio/pcm"}
                        )
                    except asyncio.QueueFull:
                        pass  # drop frame rather than block
            except WebSocketDisconnect:
                pass
            finally:
                asyncio.create_task(self.broadcast(
                    {"type": "sys", "text": "Micrófono del teléfono detenido."}
                ))

        # ── File sharing ──────────────────────────────────────────────────────

        def _safe_filename(raw: str) -> str:
            name = Path(raw).name                          # strip path components
            name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name).strip(". ")
            return name or "upload"

        if _UPLOAD_OK:
            @app.post("/api/upload")
            async def upload_file(req: Request, file: UploadFile = FastAPIFile(...)):
                if not _auth(req):
                    return JSONResponse({"error": "No autorizado"}, status_code=401)

                safe = _safe_filename(file.filename or "upload")
                dest = self._uploads_dir / safe
                stem, suffix = Path(safe).stem, Path(safe).suffix
                counter = 1
                while dest.exists():
                    dest = self._uploads_dir / f"{stem}_{counter}{suffix}"
                    counter += 1

                size = 0
                max_bytes = MAX_UPLOAD_MB * 1024 * 1024
                try:
                    with open(dest, "wb") as fout:
                        while True:
                            chunk = await file.read(65536)
                            if not chunk:
                                break
                            size += len(chunk)
                            if size > max_bytes:
                                fout.close()
                                dest.unlink(missing_ok=True)
                                return JSONResponse(
                                    {"error": f"Archivo demasiado grande (máx. {MAX_UPLOAD_MB} MB)"},
                                    status_code=413,
                                )
                            fout.write(chunk)
                except Exception as exc:
                    try:
                        dest.unlink(missing_ok=True)
                    except Exception:
                        pass
                    return JSONResponse({"error": str(exc)}, status_code=500)

                asyncio.create_task(self.broadcast({
                    "type": "file_received",
                    "name": dest.name,
                    "size": size,
                    "saved_to": str(self._uploads_dir),
                }))
                return JSONResponse({"ok": True, "name": dest.name, "size": size})
        else:
            @app.post("/api/upload")
            async def upload_unavailable(req: Request):
                return JSONResponse(
                    {"error": "Subida de archivos requiere: pip install python-multipart"},
                    status_code=503,
                )

        @app.get("/api/files")
        async def list_files(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "No autorizado"}, status_code=401)
            files = []
            try:
                for f in sorted(
                    (p for p in self._uploads_dir.iterdir() if p.is_file()),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                ):
                    files.append({"name": f.name, "size": f.stat().st_size})
            except Exception:
                pass
            return JSONResponse({"files": files})

        @app.get("/uploads/{filename}")
        async def download_file(filename: str, token: str = ""):
            # Auth via query param — browser <a download> can't send custom headers
            tok = token.strip()
            if not tok or tok not in self._tokens:
                return JSONResponse({"error": "No autorizado"}, status_code=401)
            safe = re.sub(r'[/\\]', '', filename)
            path = self._uploads_dir / safe
            if not path.exists() or not path.is_file():
                return JSONResponse({"error": "No encontrado"}, status_code=404)
            return FileResponse(str(path), filename=safe)

        @app.websocket("/ws")
        async def ws_ep(websocket: WebSocket, token: str = ""):
            tok = token.strip()
            if not tok or tok not in self._tokens:
                await websocket.close(code=4001)
                return
            await websocket.accept()
            self._clients.add(websocket)
            for entry in self._history[-50:]:
                try:
                    await websocket.send_json(entry)
                except Exception:
                    break
            try:
                while True:
                    data = await websocket.receive_json()
                    if data.get("type") == "command":
                        enc = data.get("enc", "")
                        t   = self._decrypt(tok, enc) if enc else (data.get("text") or "").strip()
                        if t:
                            await self._command_queue.put(t)
                            if self._wake_callback:
                                self._wake_callback()
            except WebSocketDisconnect:
                pass
            finally:
                self._clients.discard(websocket)

        # ── Tareas y notas API ───────────────────────────────────────────────

        @app.get("/api/tasks")
        async def list_tasks(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "No autorizado"}, status_code=401)
            from core.task_manager import list_pending_tasks
            r = list_pending_tasks()
            return JSONResponse({"tasks": r if isinstance(r, list) else []})

        @app.get("/api/tasks/nearest")
        async def nearest_task(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "No autorizado"}, status_code=401)
            from core.task_manager import get_nearest_task
            r = get_nearest_task()
            if isinstance(r, dict):
                return JSONResponse(r)
            return JSONResponse({"error": r}, status_code=404)

        @app.post("/api/tasks")
        async def create_task(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "No autorizado"}, status_code=401)
            body = await req.json()
            from core.task_manager import save_task
            r = save_task(body.get("title", ""), body.get("description", ""),
                          body.get("due_date"), body.get("priority", "media"))
            return JSONResponse({"result": r})

        @app.post("/api/tasks/{task_id}/complete")
        async def complete_task_ep(req: Request, task_id: int):
            if not _auth(req):
                return JSONResponse({"error": "No autorizado"}, status_code=401)
            from core.task_manager import complete_task
            r = complete_task(task_id)
            return JSONResponse({"result": r})

        @app.get("/api/notes")
        async def list_notes_ep(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "No autorizado"}, status_code=401)
            from core.notes_manager import list_notes
            r = list_notes()
            return JSONResponse({"notes": r})

        @app.get("/api/notes/{filename}")
        async def read_note_ep(req: Request, filename: str):
            if not _auth(req):
                return JSONResponse({"error": "No autorizado"}, status_code=401)
            from core.notes_manager import read_note
            r = read_note(filename)
            return JSONResponse({"content": r})

        @app.post("/api/notes")
        async def create_note(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "No autorizado"}, status_code=401)
            body = await req.json()
            from core.notes_manager import save_note
            r = save_note(body.get("title", ""), body.get("content", ""))
            return JSONResponse({"result": r})

        @app.get("/api/notes/search/{query}")
        async def search_notes_ep(req: Request, query: str):
            if not _auth(req):
                return JSONResponse({"error": "No autorizado"}, status_code=401)
            from core.notes_manager import search_notes
            r = search_notes(query)
            return JSONResponse({"results": r})

        return app

    # ── serve ─────────────────────────────────────────────────────────────

    async def _serve_alias(self) -> None:
        """Second HTTPS server on PORT+1 sharing the same app and in-memory state.
        Chrome HTTPS-upgrades any bare IP:PORT the user types, so this port also needs TLS.
        User types IP:8001 → Chrome tries https → self-signed cert warning → accept once → done."""
        ssl_key  = BASE_DIR / "config" / "certs" / "jarvis.key"
        ssl_cert = BASE_DIR / "config" / "certs" / "jarvis.crt"
        asyncio.get_event_loop().run_in_executor(None, _ensure_network_access, PORT + 1)
        cfg = uvicorn.Config(
            self.app, host="0.0.0.0", port=PORT + 1, log_level="warning",
            ssl_keyfile=str(ssl_key), ssl_certfile=str(ssl_cert),
        )
        print(f"[Dashboard] Entrada manual:  {self._ip}:{PORT + 1}  (escribe en el navegador, acepta el certificado una vez)")
        await uvicorn.Server(cfg).serve()

    async def serve(self) -> None:
        if not _DEPS_OK:
            print("[Dashboard] fastapi/uvicorn no instalado — dashboard deshabilitado.")
            print("[Dashboard] Ejecuta:  pip install fastapi 'uvicorn[standard]' cryptography")
            return

        # Firewall setup runs in a thread — uvicorn starts immediately,
        # no waiting for UAC dialogs or subprocess timeouts.
        asyncio.get_event_loop().run_in_executor(None, _ensure_network_access, PORT)

        use_ssl  = self._ssl_enabled()
        ssl_key  = BASE_DIR / "config" / "certs" / "jarvis.key"
        ssl_cert = BASE_DIR / "config" / "certs" / "jarvis.crt"

        if use_ssl:
            asyncio.create_task(self._serve_alias())

        cfg = uvicorn.Config(
            self.app, host="0.0.0.0", port=PORT, log_level="warning",
            **({"ssl_keyfile": str(ssl_key), "ssl_certfile": str(ssl_cert)} if use_ssl else {}),
        )

        proto = "https" if use_ssl else "http"
        print(f"[Dashboard] {proto}://{self._ip}:{PORT}")
        print("[Dashboard] Presiona 'Control Remoto' en la interfaz de JARVIS para obtener el código QR.")
        await uvicorn.Server(cfg).serve()
