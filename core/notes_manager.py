import json
import os

from supabase import Client, create_client

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "api_keys.json")


def _get_supabase() -> Client | None:
    try:
        with open(_CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
        url = cfg.get("supabase_url")
        key = cfg.get("supabase_key")
        if url and key:
            return create_client(url, key)
    except Exception:
        return None


def _snippet(text: str, size: int = 220) -> str:
    text = (text or "").replace("\n", " ").strip()
    return text[:size] + ("..." if len(text) > size else "")


def save_note(title: str, content: str) -> str:
    sb = _get_supabase()
    if not sb:
        return "Error: Supabase no configurado"
    try:
        data = sb.table("notes").insert({
            "title": title.strip(),
            "content": content.strip(),
        }).execute()
        note = data.data[0]
        return f"Nota guardada en Supabase: {note['title']} (id {note['id']})."
    except Exception as e:
        return f"Error al guardar nota: {e}"


def read_note(note_id: int | str) -> dict | str:
    sb = _get_supabase()
    if not sb:
        return "Error: Supabase no configurado"
    try:
        data = sb.table("notes").select("*").eq("id", int(note_id)).limit(1).execute()
        if not data.data:
            return f"Nota no encontrada: {note_id}"
        return dict(data.data[0])
    except Exception as e:
        return f"Error al leer nota: {e}"


def list_notes(limit: int = 20) -> list[dict] | str:
    sb = _get_supabase()
    if not sb:
        return "Error: Supabase no configurado"
    try:
        data = (
            sb.table("notes")
            .select("id,title,content,created_at,updated_at")
            .neq("title", "__JARVIS_STATUS__")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return [
            {
                "id": n.get("id"),
                "title": n.get("title"),
                "snippet": _snippet(n.get("content", "")),
                "created_at": n.get("created_at"),
                "updated_at": n.get("updated_at"),
            }
            for n in data.data
        ]
    except Exception as e:
        return f"Error al listar notas: {e}"


def search_notes(query: str) -> list[dict] | str:
    sb = _get_supabase()
    if not sb:
        return "Error: Supabase no configurado"
    try:
        q = query.strip()
        data = (
            sb.table("notes")
            .select("id,title,content,created_at,updated_at")
            .neq("title", "__JARVIS_STATUS__")
            .or_(f"title.ilike.%{q}%,content.ilike.%{q}%")
            .order("created_at", desc=True)
            .limit(20)
            .execute()
        )
        return [
            {
                "id": n.get("id"),
                "title": n.get("title"),
                "snippet": _snippet(n.get("content", "")),
                "created_at": n.get("created_at"),
                "updated_at": n.get("updated_at"),
            }
            for n in data.data
        ]
    except Exception as e:
        return f"Error al buscar notas: {e}"
