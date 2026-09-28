import argparse
import sys
import time

from . import db


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def _lista(valor):
    return [x.strip() for x in valor.split(",") if x.strip()] if valor else None


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    p = argparse.ArgumentParser(prog="concordia", description="Votaciones parlamentarias del mundo y relaciones entre países")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("actualizar", help="Actualización completa (lo que ejecuta GitHub Actions)")
    s.add_argument("--fuente", help="Solo estas fuentes, separadas por comas (onu, usa, gbr, pol, esp)")
    s.add_argument("--limite-fichas", type=int, default=300, help="Máximo de fichas IA nuevas por ejecución")
    s.add_argument("--sin-ia", action="store_true", help="No llamar a la IA aunque haya clave")

    sub.add_parser("unir", help="Reconstruye la base de trabajo desde data/bd/ (una SQLite por fuente y año)")
    sub.add_parser("partir", help="Guarda la base de trabajo troceada por fuente y año en data/bd/")
    sub.add_parser("init", help="Crea la base de trabajo y carga los catálogos")

    s = sub.add_parser("recoger", help="Ejecuta los conectores (lo nuevo desde la última recogida)")
    s.add_argument("--fuente", help="Fuentes separadas por comas")
    s.add_argument("--completo", action="store_true", help="Recorre todo el periodo, no solo lo nuevo")

    s = sub.add_parser("probar", help="Prueba un conector sin tocar la base")
    s.add_argument("fuente")
    s.add_argument("--desde", type=int, help="Primer año")

    s = sub.add_parser("procesar", help="Recalcula resultados, voto por partido, fichas por reglas, relaciones y afinidades")
    s.add_argument("--todo", action="store_true", help="Todos los años (por defecto, todos también si no se indica --anios)")
    s.add_argument("--fuente")
    s.add_argument("--anios", help="Años separados por comas o rango 2020-2026")

    s = sub.add_parser("fichas-deepseek", help="Fichas IA (resumen, tema y relaciones con otros países) con DeepSeek")
    s.add_argument("--limite", type=int, default=300)
    s.add_argument("--fuente")

    s = sub.add_parser("fichas-exportar", help="Deja en data/llm/pendientes/ los asuntos sin ficha, para otro LLM o agente")
    s.add_argument("--limite", type=int, default=500)
    s.add_argument("--fuente")

    s = sub.add_parser("fichas-importar", help="Importa fichas IA desde ficheros JSONL")
    s.add_argument("ficheros", nargs="+")
    s.add_argument("--modelo", help="Modelo que generó las fichas (si las líneas no traen «_modelo»)")

    sub.add_parser("web", help="Exporta los datos para la web (web/index.html, sin servidor)")
    sub.add_parser("estado", help="Resumen de lo que hay en la base de trabajo")

    a = p.parse_args(argv)

    if a.cmd == "actualizar":
        from .actualizar import actualizar

        actualizar(fuentes=_lista(a.fuente), limite_fichas=a.limite_fichas, ia=not a.sin_ia, log=log)
        return
    if a.cmd == "unir":
        from .almacen import unir

        unir(log=log).close()
        return
    if a.cmd == "probar":
        from .probar import probar

        sys.exit(0 if probar(a.fuente, desde=a.desde, log=log) else 1)

    con = db.connect()
    db.init(con)
    if a.cmd == "init":
        log("Base de trabajo lista")
    elif a.cmd == "recoger":
        from .procesar import procesar
        from .recoger import recoger

        tocados = recoger(con, fuentes=_lista(a.fuente), completo=a.completo, log=log)
        procesar(con, tocados, log=log)
    elif a.cmd == "procesar":
        from .procesar import procesar, todos_los_anios

        tocados = todos_los_anios(con, _lista(a.fuente), a.anios)
        procesar(con, tocados, log=log)
    elif a.cmd == "partir":
        from .almacen import partir

        partir(con, log=log)
    elif a.cmd == "fichas-deepseek":
        from .llm import deepseek
        from .procesar import procesar

        if not deepseek.disponible():
            sys.exit("Falta DEEPSEEK_API_KEY (en el entorno o en .env)")
        tocados = deepseek.generar_fichas(con, limite=a.limite, fuentes=_lista(a.fuente), log=log)
        procesar(con, tocados, log=log)
    elif a.cmd == "fichas-exportar":
        from .llm import fichas_io

        fichas_io.exportar(con, limite=a.limite, fuentes=_lista(a.fuente), log=log)
    elif a.cmd == "fichas-importar":
        from .llm import fichas_io
        from .procesar import procesar

        tocados = fichas_io.importar(con, a.ficheros, modelo=a.modelo, log=log)
        procesar(con, tocados, log=log)
    elif a.cmd == "web":
        from .exportar_web import exportar

        exportar(con, log=log)
    elif a.cmd == "estado":
        from .procesar import estado

        estado(con, log=print)


if __name__ == "__main__":
    main()
