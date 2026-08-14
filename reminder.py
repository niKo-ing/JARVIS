#!/usr/bin/env python3
"""Automatic task reminder: voice + desktop + WhatsApp."""

import sys
import os
import subprocess
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.task_manager import _get_supabase

PIPER_MODEL = os.path.expanduser("~/.local/share/piper-voices/es_ES-davefx-medium.onnx")
SESSION = "whatsapp:+56856320402"


def get_tasks_today():
    sb = _get_supabase()
    if not sb:
        return []
    today = date.today().isoformat()
    data = sb.table("tasks").select("*").eq("completed", False).eq("due_date", today).order("priority").execute()
    return list(data.data)


def get_nearest_upcoming():
    sb = _get_supabase()
    if not sb:
        return None
    today = date.today().isoformat()
    data = sb.table("tasks").select("*").eq("completed", False).gt("due_date", today).order("due_date").limit(1).execute()
    return dict(data.data[0]) if data.data else None


def speak(text):
    try:
        proc = subprocess.Popen(
            ["piper-tts", "-m", PIPER_MODEL, "--output-raw"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
        )
        pa = subprocess.Popen(
            ["paplay", "--raw", "--rate=22050", "--channels=1", "--format=s16le"],
            stdin=proc.stdout, stderr=subprocess.DEVNULL
        )
        proc.stdin.write(text.encode())
        proc.stdin.close()
        proc.wait()
        pa.wait()
    except Exception as e:
        print(f"Voice error: {e}")


def notify_desktop(title, msg):
    subprocess.run(["notify-send", "-a", "Jarvis", title, msg])


def notify_whatsapp(msg):
    try:
        subprocess.run(
            ["openclaw", "chat", "--session", SESSION, "--message", msg, "--deliver",
             "--timeout-ms", "30000"],
            capture_output=True, timeout=35
        )
    except subprocess.TimeoutExpired:
        pass
    except Exception as e:
        print(f"WhatsApp error: {e}")


def main():
    tasks = get_tasks_today()

    if not tasks:
        nearest = get_nearest_upcoming()
        if nearest and nearest.get("due_date"):
            d = datetime.strptime(nearest["due_date"], "%Y-%m-%d").date()
            days = (d - date.today()).days
            if 0 < days <= 1:
                msg = f"Tarea para mañana: {nearest['title']}"
                notify_desktop("Jarvis - Recordatorio", msg)
        return

    urgent = [t for t in tasks if t.get("priority") == "alta"]

    if urgent:
        for t in urgent:
            msg = f"Tarea urgente: {t['title']}"
            speak(msg)
            notify_desktop("Jarvis - Urgente", msg)
            notify_whatsapp(f"Urgente: {t['title']}")

    if len(tasks) <= 3:
        titles = ", ".join(t["title"] for t in tasks)
        msg = f"Tareas de hoy: {titles}"
        speak(msg)
        notify_desktop("Jarvis - Tareas de hoy", msg)


if __name__ == "__main__":
    main()
