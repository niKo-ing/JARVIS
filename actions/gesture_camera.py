from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def gesture_camera_mode(parameters: dict | None = None, player=None) -> str:
    parameters = parameters or {}
    base = Path(__file__).resolve().parent.parent
    script = base / "tools" / "gesture_camera_mode.py"
    python = base / "venv" / "bin" / "python3"
    if not python.exists():
        python = Path(sys.executable)

    cmd = [str(python), str(script)]
    widget = (parameters.get("widget") or "").strip().lower()
    if widget:
        cmd += ["--add-widget", widget]

    subprocess.Popen(
        cmd,
        cwd=str(base),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    if widget:
        return f"Widget de {widget} agregado al modo cámara."
    return "Modo cámara activado. Use pinza para mover widgets, movimiento rápido con pinza para cerrarlos, Escape para salir."
