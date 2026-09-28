"""Recogida: ejecuta los conectores y guarda lo que devuelven en la base de trabajo.

Un conector que falla (web caída, cambio de formato, reto anti-robots) se anota en estado_fuente y no
para a los demás; la web lo avisa con la fecha de los últimos datos de esa fuente.
"""

import json
import time
import traceback
from datetime import datetime, timezone

from . import http_util
from .fuentes import FUENTES, modulo
from .fuentes.modelo import SENTIDOS


class Contexto:
    """Lo que recibe cada conector: marcas de la recogida anterior, descargas y dónde guardar."""

    def __init__(self, con, fuente, completo=False, log=print, desde=None, simular=False):
        self.con = con
        self.fuente = fuente
        self.completo = completo
        self.log = log
        self.desde = desde or fuente.desde
        self.simular = simular
        self.anios = set()        # años tocados: se recalculan sus agregados
        self.n_votaciones = 0
        self.n_asuntos = 0
        self.recogido = []        # en simulación, lo que se habría guardado
        self._partidos = set()

    # -------- marcas de la recogida incremental (estado_fuente)
    def marca(self, clave, defecto=None):
        r = self.con.execute("SELECT valor FROM estado_fuente WHERE fuente=? AND clave=?", (self.fuente.codigo, clave)).fetchone()
        return json.loads(r[0]) if r and r[0] is not None else defecto

    def poner_marca(self, clave, valor):
        if self.simular:
            return
        self.con.execute("INSERT OR REPLACE INTO estado_fuente VALUES (?,?,?)", (self.fuente.codigo, clave, json.dumps(valor)))
        self.con.commit()  # una marca vale aunque la fuente falle después (lo guardado ya está confirmado)

    def ultima_fecha(self):
        r = self.con.execute("SELECT MAX(fecha) FROM votacion WHERE fuente=?", (self.fuente.codigo,)).fetchone()
        return r[0]

    # -------- descargas
    def json(self, url, **kw):
        return http_util.json_url(url, **kw)

    def fetch(self, url, **kw):
        return http_util.fetch(url, **kw)

    def cache(self, url, nombre=None, caduca_horas=None, **kw):
        return http_util.en_cache(url, self.fuente.codigo, nombre, caduca_horas, **kw)

    # -------- guardar
    def partido(self, codigo, nombre=None, siglas=None, color=None):
        """Registra un partido que no está en el catálogo del conector (o le pone nombre y color)."""
        if self.simular or codigo in self.fuente.partidos or (codigo, color) in self._partidos:
            return
        self._partidos.add((codigo, color))
        self.con.execute(
            """INSERT INTO partido VALUES (?,?,?,?,?) ON CONFLICT(fuente, codigo) DO UPDATE SET
                 nombre=COALESCE(excluded.nombre, nombre), siglas=COALESCE(excluded.siglas, siglas),
                 color=COALESCE(excluded.color, color)""",
            (self.fuente.codigo, codigo, nombre or codigo, siglas or codigo, color))

    def guardar(self, asuntos, votaciones):
        if self.simular:
            self.recogido.append((list(asuntos), list(votaciones)))
            self.n_asuntos += len(asuntos)
            self.n_votaciones += len(votaciones)
            return
        guardar(self.con, self.fuente, asuntos, votaciones, self.anios)
        self.n_asuntos += len(asuntos)
        self.n_votaciones += len(votaciones)


def guardar(con, fuente, asuntos, votaciones, anios=None):
    f = fuente.codigo
    con.executemany(
        """INSERT INTO asunto(id, fuente, codigo, titulo, tipo, fecha, autor, url, extra) VALUES (?,?,?,?,?,?,?,?,?)
           ON CONFLICT(id) DO UPDATE SET codigo=COALESCE(excluded.codigo, codigo), titulo=excluded.titulo,
             tipo=excluded.tipo, fecha=MIN(COALESCE(fecha, excluded.fecha), COALESCE(excluded.fecha, fecha)),
             autor=COALESCE(excluded.autor, autor), url=COALESCE(excluded.url, url), extra=COALESCE(excluded.extra, extra)""",
        [(a.id, f, a.codigo, a.titulo, a.tipo, a.fecha, a.autor, a.url,
          json.dumps(a.extra, ensure_ascii=False) if a.extra else None) for a in asuntos],
    )
    miembros = {}
    for v in votaciones:
        anio = int(v.fecha[:4])
        if anios is not None:
            anios.add(anio)
        con.execute(
            """INSERT OR REPLACE INTO votacion(id, fuente, camara, asunto_id, fecha, anio, numero, texto, tipo, a_favor,
                 en_contra, abstenciones, no_votan, mayoria, resultado, decisiva, importante, url)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (v.id, f, v.camara, v.asunto_id, v.fecha, anio, v.numero, v.texto, v.tipo, v.a_favor, v.en_contra,
             v.abstenciones, v.no_votan, v.mayoria, v.resultado, v.decisiva or 0, v.importante, v.url),
        )
        con.execute("DELETE FROM voto WHERE votacion_id=?", (v.id,))
        con.execute("DELETE FROM voto_partido WHERE votacion_id=?", (v.id,))
        if v.votos:
            filas = []
            for mid, nombre, partido, sentido in v.votos:
                if sentido not in SENTIDOS:
                    raise ValueError(f"{v.id}: sentido desconocido {sentido!r}")
                filas.append((v.id, mid, partido or "?", sentido))
                if nombre:
                    miembros[mid] = nombre
            con.executemany("INSERT OR REPLACE INTO voto VALUES (?,?,?,?)", filas)
        elif v.por_partido:
            con.executemany("INSERT INTO voto_partido VALUES (?,?,?,?,?,?,NULL)",
                            [(v.id, p, *n) for p, n in v.por_partido.items()])
    con.executemany("INSERT INTO miembro(id, fuente, nombre) VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET nombre=excluded.nombre",
                    [(m, f, n) for m, n in miembros.items()])
    # Partidos que no estaban en el catálogo del conector: con su código como nombre, hasta que se añadan.
    nuevos = {m[2] or "?" for v in votaciones for m in (v.votos or [])} | {p for v in votaciones for p in (v.por_partido or {})}
    con.executemany("INSERT OR IGNORE INTO partido(fuente, codigo, nombre, siglas) VALUES (?,?,?,?)",
                    [(f, p, p, p) for p in sorted(nuevos)])
    con.commit()


def recoger(con, fuentes=None, completo=False, log=print):
    """Ejecuta los conectores. Devuelve {fuente: años tocados}."""
    tocados = {}
    for codigo, fuente in FUENTES.items():
        if fuentes and codigo not in fuentes:
            continue
        if not fuente.activa and not fuentes:
            continue
        ctx = Contexto(con, fuente, completo=completo, log=log)
        inicio = time.time()
        log(f"-- {fuente.nombre} ({codigo})")
        try:
            modulo(codigo).recoger(ctx)
            ctx.poner_marca("ultimo_ok", _ahora())
            ctx.poner_marca("error", None)
            log(f"   {ctx.n_votaciones} votaciones y {ctx.n_asuntos} asuntos en {time.time() - inicio:.0f} s")
        except Exception as e:  # una fuente caída no para a las demás
            con.rollback()
            motivo = "bloqueada" if isinstance(e, http_util.Bloqueada) else "error"
            ctx.poner_marca("error", {"motivo": motivo, "detalle": f"{type(e).__name__}: {e}"[:300], "fecha": _ahora()})
            log(f"   ! {fuente.corto}: {type(e).__name__}: {e}")
            if motivo == "error":
                log("   " + traceback.format_exc().strip().splitlines()[-3])
        con.commit()
        if ctx.anios:
            tocados[codigo] = ctx.anios
    return tocados


def _ahora():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def avisos(con):
    """Fuentes que fallaron en su última recogida: {fuente: {motivo, detalle, fecha, ultimos_datos}}."""
    salida = {}
    for f, valor in con.execute("SELECT fuente, valor FROM estado_fuente WHERE clave='error'"):
        e = json.loads(valor) if valor else None
        if e:
            ultimo = con.execute("SELECT MAX(fecha) FROM votacion WHERE fuente=?", (f,)).fetchone()[0]
            salida[f] = {**e, "ultimos_datos": ultimo}
    return salida
