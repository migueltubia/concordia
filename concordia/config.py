import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
DB_PATH = DATA_DIR / "concordia.sqlite"
BD_DIR = DATA_DIR / "bd"
LLM_DIR = DATA_DIR / "llm"
WEB_DIR = ROOT / "web"
DATOS_PAQUETE = Path(__file__).resolve().parent / "datos"

# Solo ASCII: algunas webs (la API de los Comunes) rechazan con 403 una cabecera con tildes.
USER_AGENT = "concordia/0.1 (+https://github.com/migueltubia/concordia)"


def _cargar_env(ruta=ROOT / ".env"):
    """Carga en el entorno las variables de un fichero .env (CLAVE=valor, una por línea) que no estén ya.

    Es donde va la clave de DeepSeek al actualizar desde un equipo (copiar .env.ejemplo); en GitHub
    Actions llegan como secretos y variables del repositorio, que tienen prioridad. El fichero está en
    .gitignore.
    """
    try:
        lineas = ruta.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return
    for linea in lineas:
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        clave = clave.strip().removeprefix("export ").strip()
        valor = valor.strip()
        if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'":
            valor = valor[1:-1]
        if clave and valor:
            os.environ.setdefault(clave, valor)


_cargar_env()
