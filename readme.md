# JARVIS

Asistente personal de IA con voz, visión, memoria persistente, control del sistema y una aplicación web complementaria. El proyecto integra Gemini, automatización de escritorio y herramientas locales en una interfaz unificada.

## Funciones principales

- Conversación por voz en tiempo real y entrada por teclado.
- Apertura de aplicaciones, gestión de archivos y automatización del escritorio.
- Procesamiento de pantalla y control opcional mediante gestos.
- Memoria, notas, recordatorios y tareas persistentes.
- Búsqueda web, clima, videos y monitorización del sistema.
- Panel web instalable para consultar y controlar JARVIS a distancia.

## Requisitos

- Python 3.11 o 3.12.
- Micrófono para las funciones de voz.
- Una clave de API de Gemini.
- Node.js y npm para desarrollar la aplicación web.

## Instalación

```bash
git clone https://github.com/niKo-ing/JARVIS.git
cd JARVIS
python -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
python main.py
```

La configuración local se guarda en `config/api_keys.json`. Este archivo, junto con certificados, memoria personal, notas y otros datos de ejecución, está excluido del repositorio.

## Aplicación web

```bash
cd webapp
npm install
npm run dev
```

Consulta [webapp/README.md](webapp/README.md) y [webapp/supabase.sql](webapp/supabase.sql) para configurar el panel y su base de datos.

## Seguridad

No publiques claves API, certificados privados, archivos `.env`, memoria ni notas personales. Si una credencial estuvo alguna vez expuesta en un repositorio, revócala y genera una nueva.

## Autoría y licencia

Esta versión ha sido ampliamente modificada y ampliada por [niKo-ing](https://github.com/niKo-ing). Contiene material derivado de **MARK XLVII**, de FatihMakes, utilizado bajo la licencia [Creative Commons Attribution-NonCommercial 4.0 International](https://creativecommons.org/licenses/by-nc/4.0/). Los cambios no cuentan con el respaldo del autor original.

El uso de los componentes derivados está limitado a fines no comerciales y requiere conservar la atribución. Consulta [NOTICE.md](NOTICE.md) para más detalles.

