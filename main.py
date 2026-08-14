import argparse
import asyncio
import re
import threading
import json
import os
import signal
import subprocess
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

import sounddevice as sd
from google import genai
from google.genai import types
from ui import JarvisUI
from core.wake_word import WakeWordDetector
from core.clap_detector import ClapDetector
from core.remote_bridge import RemoteBridge
from memory.memory_manager import (
    load_memory, update_memory, format_memory_for_prompt,
)

from actions.file_processor import file_processor
from actions.flight_finder     import flight_finder
from actions.open_app          import open_app
from actions.weather_report    import weather_action
from actions.send_message      import send_message
from actions.reminder          import reminder
from actions.computer_settings import computer_settings
from actions.screen_processor  import screen_process
from actions.youtube_video     import youtube_video
from actions.desktop           import desktop_control
from actions.browser_control   import browser_control
from actions.file_controller   import file_controller
from actions.code_helper       import code_helper
from actions.dev_agent         import dev_agent
from actions.web_search        import web_search as web_search_action
from actions.computer_control  import computer_control
from actions.game_updater      import game_updater
from actions.system_monitor    import SystemMonitor, get_system_status
from actions.gesture_camera    import gesture_camera_mode


def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


BASE_DIR        = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"
PROMPT_PATH     = BASE_DIR / "core" / "prompt.txt"
PID_PATH        = Path("/tmp/jarvis-markxxxix.pid")
LOCK_PATH       = Path("/tmp/jarvis-markxxxix.lock")
LIVE_MODEL          = "models/gemini-2.5-flash-native-audio-preview-12-2025"
CHANNELS            = 1
SEND_SAMPLE_RATE    = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE          = 1024

def _get_api_key() -> str:
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]


def _load_system_prompt() -> str:
    try:
        return PROMPT_PATH.read_text(encoding="utf-8")
    except Exception:
        return (
            "Eres JARVIS, el asistente de IA de Tony Stark. "
            "Sé conciso, directo y usa siempre las herramientas proporcionadas para completar tareas. "
            "Nunca simules ni adivines resultados — siempre llama a la herramienta adecuada."
        )

_CTRL_RE = re.compile(r"<ctrl\d+>", re.IGNORECASE)

def _clean_transcript(text: str) -> str:    
    text = _CTRL_RE.sub("", text)
    text = re.sub(r"[\x00-\x08\x0b-\x1f]", "", text)
    return text.strip()

OPCODE_BIN = os.path.expanduser("~/.opencode/bin/opencode")

def _codex(task: str, timeout: int = 300) -> str | None:
    """Ejecuta tareas de programación con Codex CLI usando login ChatGPT, si está disponible."""
    import shutil
    import tempfile

    codex_bin = shutil.which("codex")
    auth_file = Path.home() / ".codex" / "auth.json"
    if not codex_bin or not auth_file.exists():
        return None

    prompt = (
        "Eres el agente de programación pesado de JARVIS. "
        "Respeta exactamente la ubicación solicitada por el usuario. "
        "Si pide Descargas o Downloads, crea los archivos en ~/Descargas o ~/Downloads, no en el proyecto de JARVIS. "
        "Trabaja en el proyecto actual solo cuando el usuario lo pida o cuando la tarea sea sobre este código. "
        "Haz cambios mínimos y correctos, verifica lo que puedas y responde en español.\n\n"
        f"Tarea del usuario:\n{task}"
    )

    out_path = ""
    try:
        with tempfile.NamedTemporaryFile(prefix="jarvis-codex-", suffix=".txt", delete=False) as f:
            out_path = f.name

        proc = subprocess.run(
            [
                codex_bin,
                "exec",
                "--cd", str(BASE_DIR),
                "--sandbox", "danger-full-access",
                "--output-last-message", out_path,
                prompt,
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        message = ""
        try:
            message = Path(out_path).read_text(encoding="utf-8").strip()
        except Exception:
            pass

        if proc.returncode == 0:
            return message or proc.stdout.strip() or "Hecho."

        err = (proc.stderr or proc.stdout or "").strip()
        return None if err else f"Error Codex: {err}"
    except subprocess.TimeoutExpired:
        return None
    except Exception:
        return None
    finally:
        if out_path:
            try:
                Path(out_path).unlink(missing_ok=True)
            except Exception:
                pass

def _opencode(task: str, timeout: int = 120) -> str:
    """Ejecuta tarea de programación: Codex primero, luego OpenCode/Gemini como fallback."""
    from core.opencode_client import OpenCodeClient

    codex_result = _codex(task)
    if codex_result:
        return codex_result

    try:
        client = OpenCodeClient()
        client.ensure_session()
        return client.run(task)
    except Exception:
        pass

    api_key = _get_api_key()
    env = os.environ.copy()
    env["GOOGLE_GENERATIVE_AI_API_KEY"] = api_key
    cmd = [
        OPCODE_BIN, "run", task,
        "-m", "google/gemini-2.5-flash",
        "--dangerously-skip-permissions",
        "--pure",
        "--format", "json",
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            env=env,
        )
        if proc.returncode != 0:
            err = proc.stderr.strip()
            out = proc.stdout.strip()
            return f"Error: {err or out or 'unknown'}"
        fragments: list[str] = []
        for line in proc.stdout.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if ev.get("type") == "text":
                text = ev.get("part", {}).get("text", "")
                if text:
                    fragments.append(text)
            elif ev.get("type") == "error":
                msg = ev.get("part", {}).get("message", line)
                fragments.append(f"[ERROR] {msg}")
        if fragments:
            return "\n".join(fragments)
        return "Hecho."
    except subprocess.TimeoutExpired:
        return f"Error: la tarea excedió el límite de {timeout}s."
    except Exception as e:
        return f"Error al ejecutar opencode: {e}"

TOOL_DECLARATIONS = [
    {
        "name": "open_app",
        "description": (
            "Abre cualquier aplicación en el ordenador. "
            "Úsalo cuando el usuario pida abrir, lanzar o iniciar cualquier app, "
            "sitio web o programa. Siempre llama a esta herramienta — nunca digas solo que lo abriste."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "app_name": {
                    "type": "STRING",
                    "description": "Nombre exacto de la aplicación (ej. 'WhatsApp', 'Chrome', 'Spotify')"
                }
            },
            "required": ["app_name"]
        }
    },
    {
        "name": "web_search",
        "description": (
            "Busca en la web. Úsalo para CUALQUIER pregunta sobre hechos actuales, eventos, precios, "
            "o temas — siempre prefiere esto a adivinar. "
            "Modos: 'search' (predeterminado), 'news' (últimos titulares sobre un tema), "
            "'research' (respuesta profunda y completa), 'price' (consulta de precio de producto), "
            "'compare' (comparación lado a lado de artículos)."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query":  {"type": "STRING", "description": "Consulta o tema de búsqueda"},
                "mode":   {"type": "STRING", "description": "search | news | research | price | compare"},
                "items":  {"type": "ARRAY",  "items": {"type": "STRING"}, "description": "Artículos a comparar (modo compare)"},
                "aspect": {"type": "STRING", "description": "Aspecto de comparación: price | specs | reviews | features"},
            },
            "required": ["query"]
        }
    },
    {
        "name": "system_status",
        "description": (
            "Devuelve métricas del sistema en tiempo real: uso de CPU, RAM, carga de GPU, temperatura de CPU, "
            "tiempo de actividad y cantidad de procesos. Úsalo cuando el usuario pregunte sobre rendimiento del ordenador, "
            "temperatura, memoria o uso de recursos."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        }
    },
    {
        "name": "weather_report",
        "description": "Proporciona el informe meteorológico al usuario",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "city": {"type": "STRING", "description": "Nombre de la ciudad"}
            },
            "required": ["city"]
        }
    },
    {
        "name": "send_message",
        "description": "Envía un mensaje de texto vía WhatsApp, Telegram u otra plataforma de mensajería.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "receiver":     {"type": "STRING", "description": "Nombre del contacto destinatario"},
                "message_text": {"type": "STRING", "description": "El mensaje a enviar"},
                "platform":     {"type": "STRING", "description": "Plataforma: WhatsApp, Telegram, etc."}
            },
            "required": ["receiver", "message_text", "platform"]
        }
    },
    {
        "name": "reminder",
        "description": "Establece un recordatorio temporizado usando el Programador de Tareas.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "date":    {"type": "STRING", "description": "Fecha en formato YYYY-MM-DD"},
                "time":    {"type": "STRING", "description": "Hora en formato HH:MM (24h)"},
                "message": {"type": "STRING", "description": "Texto del mensaje de recordatorio"}
            },
            "required": ["date", "time", "message"]
        }
    },
    {
        "name": "youtube_video",
        "description": (
            "Controla YouTube. Úsalo para: reproducir videos, resumir el contenido de un video, "
            "obtener información de un video o mostrar videos en tendencia."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "play | summarize | get_info | trending (predeterminado: play)"},
                "query":  {"type": "STRING", "description": "Consulta de búsqueda para la acción play"},
                "save":   {"type": "BOOLEAN", "description": "Guardar resumen en Notepad (solo summarize)"},
                "region": {"type": "STRING", "description": "Código de país para tendencias, ej. TR, US"},
                "url":    {"type": "STRING", "description": "URL del video para la acción get_info"},
            },
            "required": []
        }
    },
    {
        "name": "screen_process",
        "description": (
            "Captura y analiza la pantalla o la imagen de la cámara web. "
            "DEBE llamarse cuando el usuario pregunte qué hay en pantalla, qué ves, "
            "analiza mi pantalla, mira la cámara, etc. "
            "NO lo uses para abrir modo cámara o widgets con gestos; para eso usa gesture_camera_mode. "
            "NO tienes capacidad visual sin esta herramienta. "
            "Después de llamar a esta herramienta, permanece en SILENCIO — el módulo de visión habla directamente."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "angle": {"type": "STRING", "description": "'screen' para capturar la pantalla, 'camera' para la cámara web. Predeterminado: 'screen'"},
                "text":  {"type": "STRING", "description": "La pregunta o instrucción sobre la imagen capturada"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "gesture_camera_mode",
        "description": (
            "Activa el modo cámara con reconocimiento de mano: abre widgets flotantes que el usuario puede mover "
            "haciendo pinza con los dedos. Si hace pinza y mueve rápido, cierra el widget. Úsalo cuando pida "
            "abrir/activar modo cámara, controlar widgets con la mano, pinza, gestos o reconocimiento de mano. "
            "Si el usuario pide agregar un widget específico, usa el parámetro widget."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "widget": {"type": "STRING", "description": "Opcional: tareas | notas | calendario | sistema | camara"},
            },
        },
    },
    {
        "name": "opencode",
        "description": (
            "Ejecuta tareas de programación en el ordenador usando Codex CLI primero y OpenCode/Gemini como respaldo. "
            "Ideal para: crear/editar archivos, instalar paquetes, ejecutar comandos, buscar/modificar código, "
            "automatizar tareas, debuggear, etc. Describe la tarea en lenguaje natural."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "task": {"type": "STRING", "description": "Descripción detallada de la tarea a realizar. Sé específico."}
            },
            "required": ["task"]
        }
    },
    {
        "name": "computer_settings",
        "description": (
            "Controla el ordenador: volumen, brillo, gestión de ventanas, atajos de teclado, "
            "escribir texto en pantalla, cerrar apps, pantalla completa, modo oscuro, WiFi, reiniciar, apagar, "
            "desplazamiento, gestión de pestañas, zoom, capturas de pantalla, bloquear pantalla, recargar página. "
            "Úsalo para CUALQUIER comando individual de control del ordenador."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "La acción a realizar"},
                "description": {"type": "STRING", "description": "Descripción en lenguaje natural de qué hacer"},
                "value":       {"type": "STRING", "description": "Valor opcional: nivel de volumen, texto a escribir, etc."}
            },
            "required": []
        }
    },
    {
        "name": "browser_control",
        "description": (
            "Controla cualquier navegador web. Úsalo para: abrir sitios web, buscar en la web, "
            "hacer clic en elementos, rellenar formularios, desplazarte, capturas de pantalla, navegación, cualquier tarea web. "
            "Pasa siempre el parámetro 'browser' cuando el usuario especifique un navegador (ej. 'abrir en Edge', "
            "'usa Firefox', 'abre Chrome'). Varios navegadores pueden ejecutarse simultáneamente."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "go_to | search | click | type | scroll | fill_form | smart_click | smart_type | get_text | get_url | press | new_tab | close_tab | screenshot | back | forward | reload | switch | list_browsers | close | close_all"},
                "browser":     {"type": "STRING", "description": "Navegador destino: chrome | edge | firefox | opera | operagx | brave | vivaldi | safari. Omite para usar el navegador activo actual."},
                "url":         {"type": "STRING", "description": "URL para la acción go_to / new_tab"},
                "query":       {"type": "STRING", "description": "Consulta de búsqueda para la acción search"},
                "engine":      {"type": "STRING", "description": "Buscador: google | bing | duckduckgo | yandex (predeterminado: google)"},
                "selector":    {"type": "STRING", "description": "Selector CSS para click/type"},
                "text":        {"type": "STRING", "description": "Texto para hacer clic o escribir"},
                "description": {"type": "STRING", "description": "Descripción del elemento para smart_click/smart_type"},
                "direction":   {"type": "STRING", "description": "up | down para desplazamiento"},
                "amount":      {"type": "INTEGER", "description": "Cantidad de desplazamiento en píxeles (predeterminado: 500)"},
                "key":         {"type": "STRING", "description": "Nombre de tecla para la acción press (ej. Enter, Escape, F5)"},
                "path":        {"type": "STRING", "description": "Ruta de guardado para la captura de pantalla"},
                "incognito":   {"type": "BOOLEAN", "description": "Abrir en modo privado/incógnito"},
                "clear_first": {"type": "BOOLEAN", "description": "Limpiar el campo antes de escribir (predeterminado: true)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "file_controller",
        "description": "Gestiona archivos y carpetas: listar, crear, eliminar, mover, copiar, renombrar, leer, escribir, buscar, uso del disco.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "list | create_file | create_folder | delete | move | copy | rename | read | write | find | largest | disk_usage | organize_desktop | info"},
                "path":        {"type": "STRING", "description": "Ruta de archivo/carpeta o acceso directo: desktop, downloads, documents, home"},
                "destination": {"type": "STRING", "description": "Ruta de destino para move/copy"},
                "new_name":    {"type": "STRING", "description": "Nuevo nombre para rename"},
                "content":     {"type": "STRING", "description": "Contenido para create_file/write"},
                "name":        {"type": "STRING", "description": "Nombre de archivo a buscar"},
                "extension":   {"type": "STRING", "description": "Extensión de archivo a buscar (ej. .pdf)"},
                "count":       {"type": "INTEGER", "description": "Número de resultados para largest"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "desktop_control",
        "description": "Controla el escritorio: fondo de pantalla, organizar, limpiar, listar, estadísticas.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "wallpaper | wallpaper_url | organize | clean | list | stats | task"},
                "path":   {"type": "STRING", "description": "Ruta de imagen para wallpaper"},
                "url":    {"type": "STRING", "description": "URL de imagen para wallpaper_url"},
                "mode":   {"type": "STRING", "description": "by_type o by_date para organize"},
                "task":   {"type": "STRING", "description": "Tarea de escritorio en lenguaje natural"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "code_helper",
        "description": "Escribe, edita, explica, ejecuta o compila archivos de código.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "write | edit | explain | run | build | auto (predeterminado: auto)"},
                "description": {"type": "STRING", "description": "Qué debería hacer el código o qué cambio hacer"},
                "language":    {"type": "STRING", "description": "Lenguaje de programación (predeterminado: python)"},
                "output_path": {"type": "STRING", "description": "Dónde guardar el archivo"},
                "file_path":   {"type": "STRING", "description": "Ruta al archivo existente para edit/explain/run/build"},
                "code":        {"type": "STRING", "description": "Cadena de código crudo para explain"},
                "args":        {"type": "STRING", "description": "Argumentos de CLI para run/build"},
                "timeout":     {"type": "INTEGER", "description": "Tiempo de espera de ejecución en segundos (predeterminado: 30)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "dev_agent",
        "description": "Construye proyectos completos de múltiples archivos desde cero: planifica, escribe archivos, instala dependencias, abre VSCode, ejecuta y corrige errores.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "description":  {"type": "STRING", "description": "Qué debería hacer el proyecto"},
                "language":     {"type": "STRING", "description": "Lenguaje de programación (predeterminado: python)"},
                "project_name": {"type": "STRING", "description": "Nombre opcional de la carpeta del proyecto"},
                "timeout":      {"type": "INTEGER", "description": "Tiempo de espera de ejecución en segundos (predeterminado: 30)"},
            },
            "required": ["description"]
        }
    },
    {
        "name": "computer_control",
        "description": "Control directo del ordenador: escribir, hacer clic, atajos de teclado, desplazarse, mover el ratón, capturas de pantalla, encontrar elementos en pantalla.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "type | smart_type | click | double_click | right_click | hotkey | press | scroll | move | copy | paste | screenshot | wait | clear_field | focus_window | screen_find | screen_click | random_data | user_data"},
                "text":        {"type": "STRING", "description": "Texto a escribir o pegar"},
                "x":           {"type": "INTEGER", "description": "Coordenada X"},
                "y":           {"type": "INTEGER", "description": "Coordenada Y"},
                "keys":        {"type": "STRING", "description": "Combinación de teclas ej. 'ctrl+c'"},
                "key":         {"type": "STRING", "description": "Tecla individual ej. 'enter'"},
                "direction":   {"type": "STRING", "description": "up | down | left | right"},
                "amount":      {"type": "INTEGER", "description": "Cantidad de desplazamiento (predeterminado: 3)"},
                "seconds":     {"type": "NUMBER",  "description": "Segundos a esperar"},
                "title":       {"type": "STRING",  "description": "Título de la ventana para focus_window"},
                "description": {"type": "STRING",  "description": "Descripción del elemento para screen_find/screen_click"},
                "type":        {"type": "STRING",  "description": "Tipo de dato para random_data"},
                "field":       {"type": "STRING",  "description": "Campo para user_data: name|email|city"},
                "clear_first": {"type": "BOOLEAN", "description": "Limpiar el campo antes de escribir (predeterminado: true)"},
                "path":        {"type": "STRING",  "description": "Ruta de guardado para la captura de pantalla"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "game_updater",
        "description": (
            "La ÚNICA herramienta para cualquier solicitud de Steam o Epic Games. "
            "Úsala para: instalar, descargar, actualizar juegos, listar juegos instalados, "
            "verificar estado de descarga, programar actualizaciones. "
            "Llámala SIEMPRE directamente para cualquier solicitud de Steam/Epic/juegos. "
            "NUNCA uses browser_control o web_search para Steam/Epic."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":    {"type": "STRING",  "description": "update | install | list | download_status | schedule | cancel_schedule | schedule_status (predeterminado: update)"},
                "platform":  {"type": "STRING",  "description": "steam | epic | both (predeterminado: both)"},
                "game_name": {"type": "STRING",  "description": "Nombre del juego (coincidencia parcial admitida)"},
                "app_id":    {"type": "STRING",  "description": "Steam AppID para install (opcional)"},
                "hour":      {"type": "INTEGER", "description": "Hora para actualización programada 0-23 (predeterminado: 3)"},
                "minute":    {"type": "INTEGER", "description": "Minuto para actualización programada 0-59 (predeterminado: 0)"},
                "shutdown_when_done": {"type": "BOOLEAN", "description": "Apagar el PC cuando termine la descarga"},
            },
            "required": []
        }
    },
    {
        "name": "flight_finder",
        "description": "Busca en Google Flights y dice las mejores opciones.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "origin":      {"type": "STRING",  "description": "Ciudad de salida o código de aeropuerto"},
                "destination": {"type": "STRING",  "description": "Ciudad de llegada o código de aeropuerto"},
                "date":        {"type": "STRING",  "description": "Fecha de salida (cualquier formato)"},
                "return_date": {"type": "STRING",  "description": "Fecha de regreso para viajes redondos"},
                "passengers":  {"type": "INTEGER", "description": "Número de pasajeros (predeterminado: 1)"},
                "cabin":       {"type": "STRING",  "description": "economy | premium | business | first"},
                "save":        {"type": "BOOLEAN", "description": "Guardar resultados en Notepad"},
            },
            "required": ["origin", "destination", "date"]
        }
    },
    {
        "name": "shutdown_jarvis",
        "description": (
            "Apaga el asistente por completo. "
            "Llama a esto cuando el usuario exprese intención de terminar la conversación, "
            "cerrar el asistente, despedirse o detener a Jarvis. "
            "El usuario puede decirlo en CUALQUIER idioma."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        }
    },
    {
    "name": "file_processor",
    "description": (
        "Procesa cualquier archivo que el usuario haya subido o soltado en la interfaz. "
        "Úsalo cuando el usuario se refiera a un archivo subido y quiera una acción sobre él. "
        "Soporta: imágenes (describe/ocr/resize/compress/convert), "
        "PDFs (summarize/extract_text/to_word), "
        "documentos Word y archivos de texto (summarize/fix/reformat/translate), "
        "CSV/Excel (analyze/stats/filter/sort/convert), "
        "JSON/XML (validate/format/analyze), "
        "archivos de código (explain/review/fix/optimize/run/document/test), "
        "audio (transcribe/trim/convert/info), "
        "video (trim/extract_audio/extract_frame/compress/transcribe/info), "
        "archivos comprimidos (list/extract), "
        "presentaciones (summarize/extract_text). "
        "Llama SIEMPRE a esta herramienta cuando se haya subido un archivo y el usuario dé una orden sobre él. "
        "Si la orden del usuario es ambigua, elige la acción más lógica para ese tipo de archivo."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "file_path": {
                "type": "STRING",
                "description": "Ruta completa al archivo subido. Déjalo vacío para usar el archivo actualmente subido."
            },
            "action": {
                "type": "STRING",
                "description": (
                    "Qué hacer con el archivo. Ejemplos por tipo:\n"
                    "image: describe | ocr | resize | compress | convert | info\n"
                    "pdf: summarize | extract_text | to_word | info\n"
                    "docx/txt: summarize | fix | reformat | translate_hint | word_count | to_bullet\n"
                    "csv/excel: analyze | stats | filter | sort | convert | info\n"
                    "json: validate | format | analyze | to_csv\n"
                    "code: explain | review | fix | optimize | run | document | test\n"
                    "audio: transcribe | trim | convert | info\n"
                    "video: trim | extract_audio | extract_frame | compress | transcribe | info | convert\n"
                    "archive: list | extract\n"
                    "pptx: summarize | extract_text | analyze"
                )
            },
            "instruction": {
                "type": "STRING",
                "description": "Instrucción en texto libre si la acción no lo cubre. Ej. 'traduce esto al turco', 'encuentra todas las direcciones de email'"
            },
            "format": {
                "type": "STRING",
                "description": "Formato destino para la conversión. Ej. 'mp3', 'pdf', 'csv', 'png'"
            },
            "width":     {"type": "INTEGER", "description": "Ancho destino para redimensionar imagen"},
            "height":    {"type": "INTEGER", "description": "Alto destino para redimensionar imagen"},
            "scale":     {"type": "NUMBER",  "description": "Factor de escala para redimensionar imagen (ej. 0.5)"},
            "quality":   {"type": "INTEGER", "description": "Calidad 1-100 para comprimir imagen/video"},
            "start":     {"type": "STRING",  "description": "Tiempo de inicio para recorte: segundos o HH:MM:SS"},
            "end":       {"type": "STRING",  "description": "Tiempo de fin para recorte: segundos o HH:MM:SS"},
            "timestamp": {"type": "STRING",  "description": "Marca de tiempo para extracción de fotograma de video HH:MM:SS"},
            "column":    {"type": "STRING",  "description": "Nombre de columna para filtro/orden CSV"},
            "value":     {"type": "STRING",  "description": "Valor de filtro para filtro CSV"},
            "condition": {"type": "STRING",  "description": "Condición de filtro: equals|contains|gt|lt"},
            "ascending": {"type": "BOOLEAN", "description": "Orden de clasificación para orden CSV (predeterminado: true)"},
            "save":      {"type": "BOOLEAN", "description": "Guardar resultado en archivo (predeterminado: true)"},
            "destination": {"type": "STRING", "description": "Carpeta de salida para extraer archivo comprimido"},
        },
        "required": []
    }
},
    {
        "name": "save_memory",
        "description": (
            "Guarda un hecho personal importante sobre el usuario en la memoria a largo plazo. "
            "Llama a esto en silencio siempre que el usuario revele algo que valga la pena recordar: "
            "nombre, edad, ciudad, trabajo, preferencias, hobbies, relaciones, proyectos o planes futuros. "
            "NO llames para: clima, recordatorios, búsquedas u órdenes de una sola vez. "
            "NO anuncies que estás guardando — solo llámalo en silencio. "
            "Los valores deben estar en inglés independientemente del idioma de la conversación."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "category": {
                    "type": "STRING",
                    "description": (
                        "identity — nombre, edad, cumpleaños, ciudad, trabajo, idioma, nacionalidad | "
                        "preferences — comida/color/música/película/juego/deporte favorito, hobbies | "
                        "projects — proyectos activos, metas, cosas que se están construyendo | "
                        "relationships — amigos, familia, pareja, colegas | "
                        "wishes — planes futuros, cosas por comprar, sueños de viaje | "
                        "notes — hábitos, horario, cualquier otra cosa que valga la pena recordar"
                    )
                },
                "key":   {"type": "STRING", "description": "Clave corta en snake_case (ej. name, favorite_food, sister_name)"},
                "value": {"type": "STRING", "description": "Valor conciso en inglés (ej. Alex, pizza, older sister)"},
            },
            "required": ["category", "key", "value"]
        }
    },
    {
        "name": "save_task",
        "description": "Guarda una tarea/pendiente con fecha, prioridad y descripción en Supabase.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "title":       {"type": "STRING", "description": "Título corto de la tarea"},
                "description": {"type": "STRING", "description": "Descripción o detalle de la tarea"},
                "due_date":    {"type": "STRING", "description": "Fecha en formato YYYY-MM-DD"},
                "priority":    {"type": "STRING", "description": "alta | media | baja (predeterminado: media)"},
            },
            "required": ["title"]
        }
    },
    {
        "name": "list_pending_tasks",
        "description": "Lista todas las tareas pendientes ordenadas por fecha más cercana.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "get_nearest_task",
        "description": "Obtiene la tarea pendiente con fecha más cercana al día de hoy.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "get_agenda",
        "description": "Obtiene agenda de hoy: tareas de hoy, próximos días y notas relacionadas con estudio desde Supabase.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "days": {"type": "INTEGER", "description": "Cantidad de días próximos a incluir. Predeterminado: 7"},
            },
        },
    },
    {
        "name": "complete_task",
        "description": "Marca una tarea como completada por su ID.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "task_id": {"type": "INTEGER", "description": "ID numérico de la tarea a completar"},
            },
            "required": ["task_id"]
        }
    },
    {
        "name": "save_note",
        "description": "Guarda una nota de texto en Supabase para que aparezca en la webapp.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "title":   {"type": "STRING", "description": "Título de la nota"},
                "content": {"type": "STRING", "description": "Contenido de la nota"},
            },
            "required": ["title", "content"]
        }
    },
    {
        "name": "list_notes",
        "description": "Lista las notas guardadas en Supabase.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "read_note",
        "description": "Lee una nota completa desde Supabase por su ID.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "note_id": {"type": "INTEGER", "description": "ID numérico de la nota"},
            },
            "required": ["note_id"]
        }
    },
    {
        "name": "search_notes",
        "description": "Busca texto dentro de las notas guardadas en Supabase.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {"type": "STRING", "description": "Texto a buscar en las notas"},
            },
            "required": ["query"]
        }
    },
]

# --- Plugin system ---


class JarvisLive:

    def __init__(self, ui: JarvisUI, ptt_mode=False, wake_word=False):
        self.ui             = ui
        self.ptt_mode       = ptt_mode
        self.ptt_active     = False
        self.session        = None
        self.audio_in_queue = None
        self.out_queue      = None
        self._loop          = None
        self._is_speaking   = False
        self._speaking_lock = threading.Lock()
        self.ui.on_text_command  = self._on_text_command
        self._turn_done_event: asyncio.Event | None = None
        self._audio_interrupted = threading.Event()
        self._briefing_sent = False          # morning briefing fires once per process
        self._speaking_ended_at = 0.0
        self._sys_monitor   = SystemMonitor()  # persistent cooldown state
        self._remote_bridge = RemoteBridge()
        self._remote_command = None
        self._clap_detector = ClapDetector()
        self._wake_mode     = wake_word
        self._wake_word     = None
        self._wake_count    = 0  # avoid re-triggering during brief state changes
        if wake_word:
            self._init_wake_word()
            self.ui._on_interaction_idle = self._on_ui_interaction_idle

    def _init_wake_word(self):
        try:
            cfg_path = Path(__file__).resolve().parent / "config" / "api_keys.json"
            if not cfg_path.exists():
                print("[WakeWord] No config encontrado")
                return
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            key = cfg.get("porcupine_access_key", "")
            if not key:
                print("[WakeWord] Falta 'porcupine_access_key' en config/api_keys.json")
                return
            self._wake_word = WakeWordDetector(
                access_key=key,
                on_wake=self._on_wake_detected,
            )
            self._wake_word.start()
            print("[WakeWord] Activado — di 'Jarvis' para hablar")
        except Exception as e:
            print(f"[WakeWord] Error: {e}")

    def _on_wake_detected(self):
        """Se llama desde el hilo de sounddevice al detectar 'Jarvis'."""
        if not self._wake_mode:
            return  # ya activo
        self._wake_mode = False
        self._wake_word.pause()
        # Mostrar overlay (thread-safe via pyqtSignal)
        self.ui.set_state("PENSANDO")

    def _on_ui_interaction_idle(self):
        """Se llama desde el hilo principal de Qt cuando el overlay se oculta por inactividad."""
        self._wake_mode = True
        self._wake_count = 0
        if self._wake_word:
            self._wake_word.resume()
            print("[WakeWord] Reposo — di 'Jarvis' para activarme")

    def _resume_wake_word(self):
        """Reanuda la detección de wake word (llamar desde el hilo principal)."""
        if self._wake_word and self._wake_mode:
            self._wake_word.resume()
            # No restart if paused — it stays alive

    def _on_text_command(self, text: str):
        if not self._loop or not self.session:
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns={"parts": [{"text": text}]},
                turn_complete=True
            ),
            self._loop
        )

    def set_speaking(self, value: bool):
        with self._speaking_lock:
            self._is_speaking = value
        if value:
            self.ui.set_state("HABLANDO")
        elif not self.ui.muted:
            self.ui.set_state("ESCUCHANDO")
            self._speaking_ended_at = time.time()

    def interrupt_audio(self):
        """Detiene la reproducción de audio en curso (llamado desde hilo de visión)."""
        self._audio_interrupted.set()
        if self._loop:
            asyncio.run_coroutine_threadsafe(
                self._clear_audio_queue(), self._loop
            )
        with self._speaking_lock:
            self._is_speaking = False
        self.ui.set_state("ESCUCHANDO")
        self.ui.write_log("SIST: Audio interrumpido.")

    async def _clear_audio_queue(self):
        while not self.audio_in_queue.empty():
            try:
                self.audio_in_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    def speak(self, text: str):
        if not self._loop or not self.session:
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns={"parts": [{"text": text}]},
                turn_complete=True
            ),
            self._loop
        )

    def speak_error(self, tool_name: str, error: str):
        short = str(error)[:120]
        self.ui.write_log(f"ERR: {tool_name} — {short}")
        self.ui.notify(f"{tool_name} encontró un error", "error")
        self.speak(f"Señor, {tool_name} encontró un error. {short}")

    async def _welcome_sequence(self):
        if getattr(self, '_welcome_running', False):
            return
        self._welcome_running = True
        try:
            self._clap_detector.reset()
            self.ui.show_startup_overlay()

            while not self.out_queue.empty():
                try:
                    self.out_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

            self.set_speaking(True)
            self.speak("Es un honor tenerlo de vuelta, señor. Bienvenido a casa.")
            threading.Thread(target=self._play_welcome_music, daemon=True).start()
            threading.Thread(target=self._open_terminal, daemon=True).start()
        finally:
            self._welcome_running = False

        async def _unstick():
            await asyncio.sleep(4)
            with self._speaking_lock:
                if self._is_speaking:
                    self._is_speaking = False
            self._speaking_ended_at = time.time()
            self.ui.set_state("ESCUCHANDO")
        asyncio.create_task(_unstick())

    @staticmethod
    def _play_welcome_music():
        import shutil, time
        if shutil.which("playerctl") and shutil.which("spotify"):
            try:
                subprocess.Popen(
                    ["spotify"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                for _ in range(30):
                    time.sleep(0.5)
                    r = subprocess.run(
                        ["playerctl", "-l"], capture_output=True, text=True, timeout=5,
                    )
                    if "spotify" in r.stdout.lower():
                        break
                subprocess.run(
                    ["playerctl", "--player=spotify", "open",
                     "spotify:track:08mG3Y1vljYA6bvDt4Wqkj"],
                    timeout=10,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                return
            except Exception:
                pass
        if shutil.which("mpv"):
            try:
                subprocess.Popen(
                    ["mpv", "--no-video", "--volume=45",
                     "ytdl://ytsearch:AC DC Back in Black"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            except Exception:
                pass

    @staticmethod
    def _open_terminal():
        import shutil
        for term in ("alacritty", "kitty", "foot", "ghostty"):
            if shutil.which(term):
                try:
                    subprocess.Popen([term], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except Exception:
                    pass
                return

    def _build_config(self) -> types.LiveConnectConfig:
        from datetime import datetime

        memory     = load_memory()
        mem_str    = format_memory_for_prompt(memory)
        sys_prompt = _load_system_prompt()

        now      = datetime.now()
        time_str = now.strftime("%A, %B %d, %Y — %I:%M %p")
        time_ctx = (
            f"[FECHA Y HORA ACTUAL]\n"
            f"Ahora mismo es: {time_str}\n"
            f"Usa esto para calcular horas exactas para recordatorios.\n\n"
        )

        parts = [time_ctx]
        if mem_str:
            parts.append(mem_str)
        parts.append(sys_prompt)

        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            output_audio_transcription={},
            input_audio_transcription={},
            system_instruction="\n".join(parts),
            tools=[{"function_declarations": TOOL_DECLARATIONS}],
            session_resumption=types.SessionResumptionConfig(),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name="Charon"
                    )
                )
            ),
        )

    async def _execute_tool(self, fc) -> types.FunctionResponse:
        name = fc.name
        args = dict(fc.args or {})

        print(f"[JARVIS] 🔧 {name}  {args}")
        self.ui.set_state("PENSANDO")

        if name == "save_memory":
            category = args.get("category", "notes")
            key      = args.get("key", "")
            value    = args.get("value", "")
            if key and value:
                update_memory({category: {key: {"value": value}}})
                print(f"[Memory] 💾 save_memory: {category}/{key} = {value}")
            if not self.ui.muted:
                self.ui.set_state("ESCUCHANDO")
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": "ok", "silent": True}
            )

        tool_labels = {
            "open_app": "Abriendo aplicación",
            "web_search": "Buscando en la web",
            "weather_report": "Consultando el clima",
            "screen_process": "Analizando la pantalla",
            "file_processor": "Procesando el archivo",
            "computer_settings": "Aplicando el ajuste",
            "browser_control": "Controlando el navegador",
            "desktop_control": "Ejecutando la acción",
            "save_task": "Guardando la tarea",
            "save_note": "Guardando la nota",
        }
        action_label = tool_labels.get(name, "Ejecutando una acción")
        self.ui.set_state("PROCESANDO")
        self.ui.set_action(f"{action_label}…")
        self.ui.write_log(f"Sistema: {action_label}…")

        loop   = asyncio.get_event_loop()
        result = "Hecho."

        try:
            if name == "open_app":
                r = await loop.run_in_executor(None, lambda: open_app(parameters=args, response=None, player=self.ui))
                result = r or f"Abierto {args.get('app_name')}."

            elif name == "weather_report":
                r = await loop.run_in_executor(None, lambda: weather_action(parameters=args, player=self.ui))
                result = r or "Clima entregado."

            elif name == "browser_control":
                r = await loop.run_in_executor(None, lambda: browser_control(parameters=args, player=self.ui))
                result = r or "Hecho."

            elif name == "file_controller":
                r = await loop.run_in_executor(None, lambda: file_controller(parameters=args, player=self.ui))
                result = r or "Hecho."

            elif name == "send_message":
                r = await loop.run_in_executor(None, lambda: send_message(parameters=args, response=None, player=self.ui, session_memory=None))
                result = r or f"Mensaje enviado a {args.get('receiver')}."

            elif name == "reminder":
                r = await loop.run_in_executor(None, lambda: reminder(parameters=args, response=None, player=self.ui))
                result = r or "Recordatorio establecido."

            elif name == "youtube_video":
                r = await loop.run_in_executor(None, lambda: youtube_video(parameters=args, response=None, player=self.ui))
                result = r or "Hecho."

            elif name == "screen_process":
                threading.Thread(
                    target=screen_process,
                    kwargs={"parameters": args, "response": None,
                            "player": self.ui, "session_memory": None},
                    daemon=True
                ).start()
                result = "Módulo de visión activado. Permanece en completo silencio — el módulo de visión hablará directamente."

            elif name == "gesture_camera_mode":
                r = await loop.run_in_executor(None, lambda: gesture_camera_mode(parameters=args, player=self.ui))
                result = r or "Modo cámara activado."

            elif name == "computer_settings":
                r = await loop.run_in_executor(None, lambda: computer_settings(parameters=args, response=None, player=self.ui))
                result = r or "Hecho."

            elif name == "opencode":
                task = args.get("task", "")
                self.speak("Ejecutando tarea con OpenCode...")
                r = await loop.run_in_executor(None, lambda: _opencode(task))
                result = r

            elif name == "desktop_control":
                r = await loop.run_in_executor(None, lambda: desktop_control(parameters=args, player=self.ui))
                result = r or "Hecho."

            elif name == "code_helper":
                r = await loop.run_in_executor(None, lambda: code_helper(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Hecho."

            elif name == "dev_agent":
                r = await loop.run_in_executor(None, lambda: dev_agent(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Hecho."

            elif name == "web_search":
                r = await loop.run_in_executor(None, lambda: web_search_action(parameters=args, player=self.ui))
                result = r or "Hecho."
                # Reflejar resultados sustanciales al panel de contenido en pantalla
                if r and len(r) > 120:
                    mode  = args.get("mode", "search").upper()
                    query = args.get("query") or ", ".join(args.get("items", []))
                    label = f"{mode} — {query[:38]}" if query else mode
                    self.ui.show_content(label, r)
            elif name == "file_processor":
                if not args.get("file_path") and self.ui.current_file:
                    args["file_path"] = self.ui.current_file
                r = await loop.run_in_executor(
                    None,
                    lambda: file_processor(parameters=args, player=self.ui, speak=self.speak)
                )
                result = r or "Hecho."

            elif name == "computer_control":
                r = await loop.run_in_executor(None, lambda: computer_control(parameters=args, player=self.ui))
                result = r or "Hecho."

            elif name == "game_updater":
                r = await loop.run_in_executor(None, lambda: game_updater(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Hecho."

            elif name == "flight_finder":
                r = await loop.run_in_executor(None, lambda: flight_finder(parameters=args, player=self.ui))
                result = r or "Hecho."

            elif name == "system_status":
                r = await loop.run_in_executor(None, get_system_status)
                result = str(r)

            elif name == "shutdown_jarvis":
                self.ui.write_log("SYS: Apagado solicitado.")
                self.speak("Adiós, señor.")
                def _shutdown():
                    import time, os
                    time.sleep(1)
                    os._exit(0)
                threading.Thread(target=_shutdown, daemon=True).start()

            elif name == "save_task":
                from core.task_manager import save_task as _save
                r = await loop.run_in_executor(None, lambda: _save(**args))
                result = str(r)

            elif name == "list_pending_tasks":
                from core.task_manager import list_pending_tasks
                r = await loop.run_in_executor(None, list_pending_tasks)
                result = str(r)

            elif name == "get_nearest_task":
                from core.task_manager import get_nearest_task
                r = await loop.run_in_executor(None, get_nearest_task)
                result = str(r)

            elif name == "get_agenda":
                from core.task_manager import get_agenda
                r = await loop.run_in_executor(None, lambda: get_agenda(args.get("days", 7)))
                result = str(r)

            elif name == "complete_task":
                from core.task_manager import complete_task
                r = await loop.run_in_executor(None, complete_task, args["task_id"])
                result = r

            elif name == "save_note":
                from core.notes_manager import save_note
                r = await loop.run_in_executor(None, save_note, args["title"], args["content"])
                result = r

            elif name == "list_notes":
                from core.notes_manager import list_notes
                r = await loop.run_in_executor(None, list_notes)
                result = str(r)

            elif name == "read_note":
                from core.notes_manager import read_note
                r = await loop.run_in_executor(None, read_note, args["note_id"])
                result = str(r)

            elif name == "search_notes":
                from core.notes_manager import search_notes
                r = await loop.run_in_executor(None, search_notes, args["query"])
                result = str(r)

            else:
                result = f"Herramienta desconocida: {name}"

        except Exception as e:
            result = f"Herramienta '{name}' falló: {e}"
            traceback.print_exc()
            self.speak_error(name, e)

        if not self.ui.muted:
            self.ui.set_state("ESCUCHANDO")

        print(f"[JARVIS] 📤 {name} → {str(result)[:80]}")
        if not str(result).lower().startswith("error"):
            self.ui.write_log(f"Sistema: {action_label} · completado")
            self.ui.notify(f"{action_label} · completado", "success")
        return types.FunctionResponse(
            id=fc.id, name=name,
            response={"result": result}
        )

    async def _send_realtime(self):
        while True:
            msg = await self.out_queue.get()
            await self.session.send_realtime_input(media=msg)

    async def _listen_audio(self):
        print("[JARVIS] 🎤 Mic started")
        loop = asyncio.get_event_loop()

        def callback(indata, frames, time_info, status):
            with self._speaking_lock:
                jarvis_speaking = self._is_speaking
            if jarvis_speaking or self.ui.muted:
                return
            # Cooldown para evitar eco: no enviar mic recién después de hablar
            if time.time() - self._speaking_ended_at < 0.3:
                return
            if self.ptt_mode and not self.ptt_active:
                return
            # En modo wake word, solo envía audio si el wake word fue detectado
            if self._wake_mode and not self.ptt_active:
                return
            try:
                self._clap_detector.process(indata[:, 0])
            except Exception:
                pass
            data = indata.tobytes()
            loop.call_soon_threadsafe(
                self.out_queue.put_nowait,
                {"data": data, "mime_type": "audio/pcm"}
            )

        try:
            with sd.InputStream(
                samplerate=SEND_SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=CHUNK_SIZE,
                callback=callback,
            ):
                print("[JARVIS] 🎤 Mic stream open")
                while True:
                    await asyncio.sleep(0.1)
        except Exception as e:
            print(f"[JARVIS] ❌ Mic: {e}")
            raise

    async def _receive_audio(self):
        print("[JARVIS] 👂 Recv started")
        out_buf, in_buf = [], []

        try:
            while True:
                async for response in self.session.receive():

                    if response.data:
                        if self._turn_done_event and self._turn_done_event.is_set():
                            self._turn_done_event.clear()
                        self.audio_in_queue.put_nowait(response.data)

                    if response.server_content:
                        sc = response.server_content

                        if sc.output_transcription and sc.output_transcription.text:
                            txt = _clean_transcript(sc.output_transcription.text)
                            if txt:
                                out_buf.append(txt)

                        if sc.input_transcription and sc.input_transcription.text:
                            txt = _clean_transcript(sc.input_transcription.text)
                            if txt:
                                in_buf.append(txt)

                        if sc.turn_complete:
                            if self._turn_done_event:
                                self._turn_done_event.set()

                            full_in = " ".join(in_buf).strip()
                            if full_in:
                                self.ui.write_log(f"Tú: {full_in}")
                            in_buf = []

                            full_out = " ".join(out_buf).strip()
                            if full_out:
                                self.ui.write_log(f"Jarvis: {full_out}")
                            if self._remote_command:
                                command_id = self._remote_command["id"]
                                result_text = full_out or "Orden procesada por Jarvis."
                                try:
                                    await asyncio.to_thread(
                                        self._remote_bridge.finish, command_id, result_text
                                    )
                                except Exception as e:
                                    print(f"[Remote] No se pudo cerrar la orden: {e}")
                                self._remote_command = None
                            out_buf = []

                    if response.tool_call:
                        fn_responses = []
                        for fc in response.tool_call.function_calls:
                            print(f"[JARVIS] 📞 {fc.name}")
                            fr = await self._execute_tool(fc)
                            fn_responses.append(fr)
                        await self.session.send_tool_response(
                            function_responses=fn_responses
                        )
        except Exception as e:
            print(f"[JARVIS] ❌ Recv: {e}")
            traceback.print_exc()
            raise

    async def _play_audio(self):
        """Play raw PCM audio from Gemini."""
        print("[JARVIS] 🔊 Play started")
        stream = sd.RawOutputStream(
            samplerate=RECEIVE_SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=CHUNK_SIZE,
        )
        stream.start()
        try:
            while True:
                if self._audio_interrupted.is_set():
                    self._audio_interrupted.clear()
                    self.set_speaking(False)
                    stream.stop()
                    stream.close()
                    stream = None
                    continue
                try:
                    chunk = await asyncio.wait_for(
                        self.audio_in_queue.get(),
                        timeout=0.1
                    )
                except asyncio.TimeoutError:
                    if (
                        self._turn_done_event
                        and self._turn_done_event.is_set()
                        and self.audio_in_queue.empty()
                    ):
                        self.set_speaking(False)
                        self._turn_done_event.clear()
                    continue
                if stream is None:
                    stream = sd.RawOutputStream(
                        samplerate=RECEIVE_SAMPLE_RATE,
                        channels=CHANNELS,
                        dtype="int16",
                        blocksize=CHUNK_SIZE,
                    )
                    stream.start()
                self.set_speaking(True)
                await asyncio.to_thread(stream.write, chunk)
        except Exception as e:
            print(f"[JARVIS] ❌ Play: {e}")
            raise
        finally:
            if stream:
                stream.stop()
                stream.close()

    # ── Morning briefing ────────────────────────────────────────────────────────

    async def _send_startup_briefing(self) -> None:
        """Saludo corto tipo Jarvis al iniciar."""
        await asyncio.sleep(0.3)
        if not self.session:
            return

        memory   = load_memory()
        identity = memory.get("identity", {})
        prefs    = memory.get("preferences", {})
        name     = identity.get("name", {}).get("value", "") if isinstance(identity.get("name"), dict) else ""
        style    = prefs.get("address_style", {}).get("value", "") if isinstance(prefs.get("address_style"), dict) else ""

        lines = [
            "[INSTRUCCIÓN] Saluda al usuario con UNA sola oración corta tipo Jarvis.",
            "Ejemplos: 'Bienvenido a casa, señor.'  o  'Buenos días, señor.'  o  'A su servicio, señor.'",
            "- NO menciones la hora, el tiempo, noticias ni nada más.",
            "- NO llames a ninguna herramienta.",
            "- Responde siempre en español.",
        ]
        if style:
            lines.append(f"- Dirígete al usuario como '{style}'.")
        elif name:
            lines.append(f"- Dirígete al usuario como {name}.")

        await self.session.send_client_content(
            turns={"parts": [{"text": '\n'.join(lines)}]},
            turn_complete=True,
        )
        self.ui.write_log("SYS: Saludo de inicio enviado.")
        # Esperar a que termine la reproducción del saludo antes de
        # permitir que el micrófono envíe audio, evitando eco
        # que Gemini interpretaría como un segundo turno.
        if self._turn_done_event:
            await self._turn_done_event.wait()

    # ── System monitor ──────────────────────────────────────────────────────────

    async def _run_system_monitor(self) -> None:
        """Tarea de fondo: alertas de voz cuando las métricas superan los umbrales."""
        while True:
            await asyncio.sleep(10)
            alert = await asyncio.to_thread(self._sys_monitor.check)
            if alert and self.session:
                try:
                    await self.session.send_client_content(
                        turns={"parts": [{"text": alert}]},
                        turn_complete=True,
                    )
                except Exception as e:
                    print(f"[Monitor] ⚠️ Could not send alert: {e}")

    async def _process_remote_commands(self) -> None:
        """Publica el estado del PC y consume órdenes creadas desde la PWA."""
        dangerous = re.compile(
            r"\b(apaga|apagar|reinicia|reiniciar|borra|borrar|elimina|eliminar|"
            r"envía|enviar mensaje)\b", re.IGNORECASE,
        )
        while True:
            try:
                with self._speaking_lock:
                    speaking = self._is_speaking
                state = "speaking" if speaking else ("listening" if self.session else "offline")
                current = self._remote_command["command"] if self._remote_command else None
                await asyncio.to_thread(self._remote_bridge.heartbeat, state, current)

                if self.session and not self._remote_command:
                    command = await asyncio.to_thread(self._remote_bridge.claim_next)
                    if command:
                        if dangerous.search(command["command"]) and not command.get("approved"):
                            await asyncio.to_thread(
                                self._remote_bridge.fail,
                                command["id"],
                                "La orden requiere confirmación desde el teléfono.",
                            )
                        else:
                            self._remote_command = command
                            prompt = (
                                "[ORDEN REMOTA AUTORIZADA DESDE EL IPHONE]\n"
                                f"{command['command']}\n"
                                "Ejecuta la orden con las herramientas disponibles y reporta el resultado."
                            )
                            await self.session.send_client_content(
                                turns={"parts": [{"text": prompt}]},
                                turn_complete=True,
                            )
                            self.ui.write_log(f"[iPhone]: {command['command']}")
            except Exception as e:
                print(f"[Remote] Puente temporalmente no disponible: {e}")
            await asyncio.sleep(5)

    # ── main loop ───────────────────────────────────────────────────────────

    async def run(self):
        self._loop = asyncio.get_event_loop()
        self._clap_detector.set_callback(
            lambda: asyncio.run_coroutine_threadsafe(
                self._welcome_sequence(), self._loop
            )
        )

        client = genai.Client(
            api_key=_get_api_key(),
            http_options={"api_version": "v1beta"}
        )

        if self._remote_bridge.enabled:
            asyncio.create_task(self._process_remote_commands())
            print("[Remote] Supabase conectado — control desde iPhone activo.")
        else:
            print("[Remote] Desactivado: Supabase no configurado.")

        while True:
            try:
                print("[JARVIS] Conectando...")
                self.ui.set_state("PENSANDO")
                config = self._build_config()

                async with (
                    client.aio.live.connect(model=LIVE_MODEL, config=config) as session,
                    asyncio.TaskGroup() as tg,
                ):
                    self.session          = session
                    self.audio_in_queue   = asyncio.Queue()
                    self.out_queue        = asyncio.Queue(maxsize=200)
                    self._turn_done_event = asyncio.Event()

                    print("[JARVIS] Conectado.")
                    self.ui.set_state("ESCUCHANDO")
                    self.ui.write_log("SYS: JARVIS en línea.")

                    tg.create_task(self._send_realtime())
                    tg.create_task(self._listen_audio())
                    tg.create_task(self._receive_audio())
                    tg.create_task(self._play_audio())
                    tg.create_task(self._run_system_monitor())

                    # Briefing matutino — se ejecuta una vez por inicio del proceso
                    if not self._briefing_sent:
                        self._briefing_sent = True
                        tg.create_task(self._send_startup_briefing())

            except Exception as e:
                print(f"[JARVIS] Error: {e}")
                traceback.print_exc()
            finally:
                self.session = None

            self.set_speaking(False)
            self.ui.set_state("DURMIENDO")

            print("[JARVIS] Reconectando en 3s...")
            await asyncio.sleep(3)

def main():
    import fcntl

    lock_fd = open(LOCK_PATH, "w")
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        PID_PATH.write_text(str(os.getpid()), encoding="utf-8")
    except BlockingIOError:
        try:
            pid = int(PID_PATH.read_text(encoding="utf-8").strip())
            os.kill(pid, signal.SIGUSR2)
        except Exception:
            pass
        return

    parser = argparse.ArgumentParser(description="JARVIS — Asistente de voz")
    parser.add_argument("--background", action="store_true",
                        help="Iniciar minimizado en segundo plano")
    parser.add_argument("--compact", action="store_true",
                        help="Modo compacto: solo el círculo HUD en la esquina")
    parser.add_argument("--ptt", action="store_true",
                        help="Modo pulsar para hablar (push-to-talk)")
    parser.add_argument("--wake", action="store_true",
                        help="Activar detección de voz 'Jarvis' (requiere porcupine_access_key en config)")
    args = parser.parse_args()

    # ── Señales externas (via pkill) ─────────────────────────────────────
    # SIGUSR1 = toggle PTT on/off (SUPER+SHIFT+Z)
    # SIGUSR2 = mostrar instancia existente (SUPER+SHIFT+J)
    ptt_signal = threading.Event()
    restore_signal = threading.Event()

    def _handle_sigusr1(signum, frame):
        ptt_signal.set()

    def _handle_sigusr2(signum, frame):
        restore_signal.set()

    signal.signal(signal.SIGUSR1, _handle_sigusr1)
    signal.signal(signal.SIGUSR2, _handle_sigusr2)

    # ── UI ──────────────────────────────────────────────────────────────
    ui = JarvisUI("face.png", background=args.background, compact=args.compact)

    def runner():
        ui.wait_for_api_key()
        jarvis = JarvisLive(ui, ptt_mode=args.ptt, wake_word=args.wake)

        # Wire audio interrupt (visión silencia la voz principal)
        ui._on_audio_interrupt = jarvis.interrupt_audio
        ui._win._stop_current_cb = jarvis.interrupt_audio

        # Wire PTT callbacks
        win = ui._win
        def _ptt_press():
            jarvis.ptt_active = True
            ui.set_ptt_active(True)
        def _ptt_release():
            jarvis.ptt_active = False
            ui.set_ptt_active(False)
        win._ptt_pressed_cb = _ptt_press
        win._ptt_released_cb = _ptt_release
        win._ptt_toggled_cb = lambda enabled: setattr(jarvis, 'ptt_mode', enabled)
        if ui._compact:
            ui._compact._ptt_toggled_cb = win._ptt_toggled_cb

        # ── Señales externas ────────────────────────────────────────────────
        # SIGUSR1 (toggle): conmuta PTT on/off (SUPER+SHIFT+Z, jarvis-toggle)

        def _signal_watcher():
            while True:
                if restore_signal.wait(timeout=0.1):
                    restore_signal.clear()
                    ui.restore_from_hotkey()

                if not ptt_signal.is_set():
                    continue
                ptt_signal.clear()
                if jarvis.ptt_mode:
                    jarvis.ptt_active = not jarvis.ptt_active
                    ui.set_ptt_active(jarvis.ptt_active)

        threading.Thread(target=_signal_watcher, daemon=True).start()

        try:
            asyncio.run(jarvis.run())
        except KeyboardInterrupt:
            print("\n🔴 Apagando...")

    threading.Thread(target=runner, daemon=True).start()
    ui.root.mainloop()

if __name__ == "__main__":
    main()
