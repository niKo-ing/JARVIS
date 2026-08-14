import subprocess
import sys

print("Instalando requisitos...")
subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], check=True)

print("Instalando navegadores Playwright...")
subprocess.run([sys.executable, "-m", "playwright", "install"], check=True)

print("\n✅ Configuración completa. Ejecuta 'python main.py' para iniciar JARVIS.")

