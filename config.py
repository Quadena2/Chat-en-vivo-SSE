"""
Configuracion central de la aplicacion.

Todos los valores se leen de variables de entorno. Para no depender de librerias
externas (solo Flask + Redis) el archivo ".env" se carga con un lector propio
escrito con la libreria estandar de Python (os / pathlib).

Prioridad de los valores:
    1. Variables de entorno reales del sistema operativo (ej. $env:REDIS_HOST="...")
    2. Valores escritos en el archivo .env
    3. Valores por defecto definidos en esta clase
"""
import os
from pathlib import Path

RUTA_ENV = Path(__file__).resolve().parent / ".env"


# Lee un archivo .env con formato CLAVE=VALOR y lo carga en os.environ
# - Ignora lineas vacias y comentarios (#)
# - Quita comillas simples o dobles alrededor del valor
# - No sobreescribe variables que ya existen en el sistema (os.environ.setdefault)
def cargar_archivo_env(ruta: Path = RUTA_ENV) -> None:
    if not ruta.exists():
        return

    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue

        clave, valor = linea.split("=", 1)
        clave = clave.strip()
        valor = valor.strip().strip('"').strip("'")
        os.environ.setdefault(clave, valor)


# Convierte textos como "1", "true", "si", "on" en un booleano
def _leer_bool(nombre: str, por_defecto: bool = False) -> bool:
    valor = os.getenv(nombre)
    if valor is None:
        return por_defecto
    return valor.strip().lower() in ("1", "true", "si", "sí", "yes", "on")


# Se carga el .env apenas se importa este modulo, antes de leer la clase
cargar_archivo_env()


class Configuracion:
    SECRET_KEY = os.getenv("SECRET_KEY", "clave-secreta-redis")

    # Servidor web de Flask
    FLASK_HOST = os.getenv("FLASK_HOST", "127.0.0.1")
    FLASK_PORT = int(os.getenv("FLASK_PORT", 5000))
    FLASK_DEBUG = _leer_bool("FLASK_DEBUG", True)

    # Conexion hacia redis en docker
    REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
    REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
    REDIS_DB = int(os.getenv("REDIS_DB", 0))
    # Si en el .env queda vacio (REDIS_PASSWORD=) se convierte en None
    REDIS_PASSWORD = os.getenv("REDIS_PASSWORD") or None

    # Limite de mensajes guardados en el historia por cada sala (LTRIM)
    MAX_MENSAJES_HISTORIAL = int(os.getenv("MAX_MENSAJES_HISTORIAL", 100))

    # Cantidad de mensajes que se muestran al abrir una sala (LRANGE)
    MENSAJES_POR_PAGINA = int(os.getenv("MENSAJES_POR_PAGINA", 50))

    # Presencia en tiempo real:
    # Cada conexion SSE renueva su "latido" en Redis cada INTERVALO_LATIDO_SEGUNDOS.
    # Si una conexion no renueva su latido en PRESENCIA_TTL_SEGUNDOS se considera
    # muerta (ej. Flask se reinicio o se corto la red) y se borra de la sala.
    INTERVALO_LATIDO_SEGUNDOS = int(os.getenv("INTERVALO_LATIDO_SEGUNDOS", 5))
    PRESENCIA_TTL_SEGUNDOS = int(os.getenv("PRESENCIA_TTL_SEGUNDOS", 15))
