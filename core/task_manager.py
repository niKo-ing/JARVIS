import json
import os
from datetime import date, timedelta

from supabase import create_client, Client

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "api_keys.json")


def _get_supabase() -> Client | None:
    try:
        cfg = json.load(open(_CONFIG_PATH))
        url = cfg.get("supabase_url")
        key = cfg.get("supabase_key")
        if url and key:
            return create_client(url, key)
    except Exception:
        return None


def save_task(title: str, description: str = "", due_date: str | None = None,
              priority: str = "media") -> dict | str:
    sb = _get_supabase()
    if not sb:
        return "Error: Supabase no configurado"
    try:
        row = {"title": title, "description": description, "priority": priority}
        if due_date:
            row["due_date"] = due_date
        data = sb.table("tasks").insert(row).execute()
        return {"id": data.data[0]["id"], **row}
    except Exception as e:
        return f"Error al guardar tarea: {e}"


def list_pending_tasks() -> list | str:
    sb = _get_supabase()
    if not sb:
        return "Error: Supabase no configurado"
    try:
        data = sb.table("tasks").select("*").eq("completed", False).not_.like(
            "title", "[JARVIS_CMD] %"
        ).order("due_date").execute()
        return list(data.data)
    except Exception as e:
        return f"Error al listar tareas: {e}"


def get_nearest_task() -> dict | str:
    sb = _get_supabase()
    if not sb:
        return "Error: Supabase no configurado"
    try:
        today = date.today().isoformat()
        data = sb.table("tasks").select("*").eq("completed", False).not_.like(
            "title", "[JARVIS_CMD] %"
        ).gte("due_date", today).order("due_date").limit(1).execute()
        if data.data:
            return dict(data.data[0])
        return "No tienes tareas pendientes con fecha."
    except Exception as e:
        return f"Error: {e}"


def complete_task(task_id: int) -> str:
    sb = _get_supabase()
    if not sb:
        return "Error: Supabase no configurado"
    try:
        sb.table("tasks").update({"completed": True}).eq("id", task_id).execute()
        return f"Tarea {task_id} marcada como completada."
    except Exception as e:
        return f"Error: {e}"


def get_agenda(days: int = 7) -> dict | str:
    """Resumen de tareas de hoy, próximos días y notas relacionadas con estudio."""
    sb = _get_supabase()
    if not sb:
        return "Error: Supabase no configurado"
    try:
        today = date.today()
        end = today + timedelta(days=days)

        today_tasks = (
            sb.table("tasks")
            .select("*")
            .eq("completed", False)
            .not_.like("title", "[JARVIS_CMD] %")
            .eq("due_date", today.isoformat())
            .order("priority")
            .execute()
        ).data

        upcoming_tasks = (
            sb.table("tasks")
            .select("*")
            .eq("completed", False)
            .not_.like("title", "[JARVIS_CMD] %")
            .gt("due_date", today.isoformat())
            .lte("due_date", end.isoformat())
            .order("due_date")
            .execute()
        ).data

        try:
            study_notes = (
                sb.table("notes")
                .select("id,title,content,created_at")
                .or_("title.ilike.%estudi%,content.ilike.%estudi%")
                .order("created_at", desc=True)
                .limit(5)
                .execute()
            ).data
        except Exception:
            study_notes = []

        return {
            "date": today.isoformat(),
            "today_tasks": today_tasks,
            "upcoming_tasks": upcoming_tasks,
            "study_notes": [
                {
                    "id": n.get("id"),
                    "title": n.get("title"),
                    "snippet": (n.get("content") or "").replace("\n", " ")[:220],
                    "created_at": n.get("created_at"),
                }
                for n in study_notes
            ],
        }
    except Exception as e:
        return f"Error al obtener agenda: {e}"
