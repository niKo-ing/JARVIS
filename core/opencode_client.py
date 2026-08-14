import json
import os
import time
import urllib.request
import urllib.error


class OpenCodeClient:
    """HTTP client for opencode server (persistent daemon).

    Manages a session so conversation context is maintained between calls.
    Auto-starts the server if not running, and creates/finds the "jarvis" session.
    """

    BASE_URL = "http://127.0.0.1:4096"
    SESSION_FILE = os.path.expanduser("~/.config/opencode/jarvis_session.json")

    def __init__(self):
        self._session_id = self._load_session_id()

    # ── Helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _load_session_id() -> str | None:
        try:
            with open(OpenCodeClient.SESSION_FILE) as f:
                return json.load(f).get("session_id")
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            return None

    @staticmethod
    def _save_session_id(session_id: str):
        os.makedirs(os.path.dirname(OpenCodeClient.SESSION_FILE), exist_ok=True)
        with open(OpenCodeClient.SESSION_FILE, "w") as f:
            json.dump({"session_id": session_id}, f)

    @staticmethod
    def _request(method: str, path: str, body: dict | None = None) -> dict | list | None:
        url = f"{OpenCodeClient.BASE_URL}{path}"
        data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                text = resp.read().decode()
                if text:
                    return json.loads(text)
                return None
        except urllib.error.HTTPError as e:
            body_text = e.read().decode() if e.fp else ""
            return {"error": f"HTTP {e.code}: {body_text or e.reason}"}
        except (urllib.error.URLError, ConnectionRefusedError, TimeoutError) as e:
            return {"error": f"Conexión rehusada: {e}"}

    # ── Session management ─────────────────────────────────────────────────

    def ensure_session(self):
        """Find or create the 'jarvis' session, store its ID."""
        if self._session_id:
            info = self._request("GET", f"/session/{self._session_id}")
            if isinstance(info, dict) and "id" in info:
                return self._session_id
            self._session_id = None

        sessions = self._request("GET", "/session")
        if isinstance(sessions, list):
            for s in sessions:
                if s.get("title") == "jarvis":
                    self._session_id = s["id"]
                    self._save_session_id(self._session_id)
                    return self._session_id

        result = self._request("POST", "/session", {"title": "jarvis"})
        if isinstance(result, dict) and "id" in result:
            self._session_id = result["id"]
            self._save_session_id(self._session_id)
            return self._session_id

        raise RuntimeError(f"No se pudo crear sesión: {result}")

    # ── Execute ────────────────────────────────────────────────────────────

    def run(self, task: str) -> str:
        """Send a task to the opencode daemon and return the text response.

        Maintains conversation context via the persistent session.
        """
        if not self._session_id:
            raise RuntimeError("Llamar a ensure_session() primero")

        result = self._request("POST", f"/session/{self._session_id}/message", {
            "parts": [{"type": "text", "text": task}],
        })
        if isinstance(result, dict) and "parts" in result:
            texts: list[str] = []
            for part in result["parts"]:
                if isinstance(part, dict) and part.get("type") == "text":
                    t = part.get("text", "").strip()
                    if t:
                        texts.append(t)
            return "\n".join(texts) if texts else "Hecho."
        if isinstance(result, dict) and "error" in result:
            return f"Error: {result['error']}"
        return str(result)
