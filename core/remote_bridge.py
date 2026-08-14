"""Puente entre Jarvis en el PC y el centro de control móvil en Supabase."""

import json
import os
import platform
from datetime import datetime, timezone
from pathlib import Path

import psutil
from supabase import Client, create_client

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "api_keys.json"


def _client() -> Client | None:
    try:
        config = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        url = config.get("supabase_url")
        key = config.get("supabase_key")
        return create_client(url, key) if url and key else None
    except Exception:
        return None


class RemoteBridge:
    def __init__(self):
        self.client = _client()

    @property
    def enabled(self) -> bool:
        return self.client is not None

    def heartbeat(self, state: str = "idle", current_command: str | None = None) -> None:
        if not self.client:
            return
        memory = psutil.virtual_memory()
        payload = {
            "state": state,
            "hostname": platform.node(),
            "cpu_percent": round(psutil.cpu_percent(interval=None), 1),
            "ram_percent": round(memory.percent, 1),
            "current_command": current_command,
            "last_seen": datetime.now(timezone.utc).isoformat(),
        }
        existing = (
            self.client.table("notes").select("id")
            .eq("title", "__JARVIS_STATUS__").limit(1).execute()
        )
        row = {"title": "__JARVIS_STATUS__", "content": json.dumps(payload)}
        if existing.data:
            self.client.table("notes").update(row).eq("id", existing.data[0]["id"]).execute()
        else:
            self.client.table("notes").insert(row).execute()

    def claim_next(self) -> dict | None:
        if not self.client:
            return None
        result = (
            self.client.table("tasks")
            .select("*")
            .like("title", "[JARVIS_CMD] %")
            .eq("completed", False)
            .order("created_at")
            .limit(1)
            .execute()
        )
        if not result.data:
            return None
        row = dict(result.data[0])
        try:
            metadata = json.loads(row.get("description") or "{}")
        except json.JSONDecodeError:
            metadata = {}
        if metadata.get("status", "pending") != "pending":
            return None
        command = {
            "id": row["id"],
            "command": row["title"].removeprefix("[JARVIS_CMD] ").strip(),
            "approved": bool(metadata.get("approved")),
        }
        metadata.update({
            "status": "running",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "error": None,
        })
        claimed = (
            self.client.table("tasks")
            .update({"description": json.dumps(metadata)})
            .eq("id", row["id"])
            .eq("completed", False)
            .execute()
        )
        return command if claimed.data else None

    def finish(self, command_id: int, result: str = "") -> None:
        if self.client:
            self.client.table("tasks").update({
                "completed": True,
                "description": json.dumps({
                    "status": "completed",
                    "result": result[:4000],
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                }),
            }).eq("id", command_id).execute()

    def fail(self, command_id: int, error: str) -> None:
        if self.client:
            self.client.table("tasks").update({
                "completed": True,
                "description": json.dumps({
                    "status": "error",
                    "error": str(error)[:1000],
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                }),
            }).eq("id", command_id).execute()
