"""Actualización completa, sin intervención (GitHub Actions o cualquier equipo con el repositorio clonado).

1. Si no hay base de trabajo, se reconstruye desde data/bd/ (lo versionado).
2. Cada conector trae lo nuevo desde su última recogida; uno que falla se anota y no para a los demás.
3. Se cargan las fichas IA versionadas en data/llm/.
4. Se procesa con reglas lo que ha cambiado (voto por partido, decisivas, fichas por reglas, relaciones,
   afinidades).
5. Con DEEPSEEK_API_KEY: fichas de los asuntos nuevos (resumen, tema y relaciones con otros países), con un
   límite por ejecución, y se vuelve a procesar lo que tocan.
6. Se regenera la web y se vuelve a trocear la base.
"""

from collections import defaultdict

from . import almacen, db, exportar_web
from .config import DB_PATH
from .llm import deepseek, fichas_io
from .procesar import procesar
from .recoger import avisos, recoger


def _sumar(a, b):
    for f, anios in b.items():
        a[f] |= set(anios)


def actualizar(fuentes=None, limite_fichas=300, ia=True, log=print):
    if not DB_PATH.exists() and (almacen.BD_DIR / "comun.sqlite").exists():
        log("Reconstruyendo la base de trabajo desde data/bd/…")
        almacen.unir(DB_PATH, log).close()
    con = db.connect()
    db.init(con)
    tocados = defaultdict(set)

    log("== Recogida")
    _sumar(tocados, recoger(con, fuentes=fuentes, log=log))

    log("== Fichas IA versionadas")
    _sumar(tocados, fichas_io.importar_todo(con, log))

    log("== Procesado con reglas")
    procesar(con, dict(tocados), log)

    if ia and deepseek.disponible():
        log(f"== IA: DeepSeek ({deepseek.modelo_por_defecto()})")
        try:
            nuevos = deepseek.generar_fichas(con, limite=limite_fichas, fuentes=fuentes, log=log)
            procesar(con, nuevos, log)
        except Exception as e:  # la IA no debe tirar la actualización: lo hecho ya está en data/llm
            log(f"  ! IA interrumpida: {type(e).__name__}: {e}")
            con.rollback()
    elif ia:
        log("== IA: sin DEEPSEEK_API_KEY; los asuntos nuevos quedan con la ficha por reglas.")

    log("== Web y base troceada")
    exportar_web.exportar(con, log)
    almacen.partir(con, log)
    pendientes = con.execute("""SELECT COUNT(*) FROM asunto a LEFT JOIN ficha fi ON fi.asunto_id=a.id
                                WHERE (fi.origen IS NULL OR fi.origen='reglas') AND a.fuente <> 'esp'
                                  AND a.tipo NOT IN ('procedimiento', 'nombramiento')""").fetchone()[0]
    log(f"Hecho. Asuntos que siguen sin ficha IA: {pendientes}")
    fallos = avisos(con)
    if fallos:
        log("Fuentes sin actualizar en esta ejecución:")
        for f, a in fallos.items():
            log(f"  {f}: {a['motivo']} ({a['detalle'][:160]}); últimos datos del {a.get('ultimos_datos')}")
            print(f"::warning title=Fuente sin actualizar: {f}::{a['detalle'][:200]}")
