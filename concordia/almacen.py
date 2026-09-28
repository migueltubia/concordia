"""Almacenamiento troceado: una SQLite por fuente y año, más una común.

La base de trabajo (data/concordia.sqlite) no se versiona: con el voto de cada congresista de EEUU
desde 2001 y el de cada Estado en la ONU desde 1946 pasa de 1 GB, y GitHub rechaza ficheros de más de
100 MB. Lo que se guarda en git es data/bd/:

- comun.sqlite: partidos de cada fuente.
- estado.json: marcas de la recogida incremental de cada fuente (texto, para ver los cambios en git).
- <fuente>/<año>.sqlite: todo lo de un año de una fuente (usa/2025.sqlite, onu/1986.sqlite...): asuntos
  votados ese año con su ficha, votaciones, voto por partido, relaciones entre países, afinidades y el
  voto nominal compacto: por cada votación, una cadena con el sentido de cada miembro de la plantilla
  del año (S sí, N no, A abstención, - no vota, . no estaba) y otra con su partido.

El año es la unidad natural: estable (un año cerrado no cambia) y la misma con la que se filtra en la
web, en todos los países (las legislaturas no coinciden entre países). Un asunto votado en dos años va
en los dos ficheros. `partir` solo reescribe los ficheros cuyo contenido cambia; `unir` reconstruye la
base de trabajo.
"""

import hashlib
import json
import sqlite3
from collections import defaultdict

from . import db
from .config import BD_DIR, DB_PATH

MANIFIESTO = BD_DIR / "manifiesto.json"
ESTADO = BD_DIR / "estado.json"
LIMITE_AVISO = 45_000_000  # GitHub avisa desde 50 MB por fichero y rechaza desde 100 MB

ESQUEMA_COMPACTO = """
CREATE TABLE plantilla(pos INTEGER PRIMARY KEY, miembro_id TEXT NOT NULL);
CREATE TABLE partido_idx(idx INTEGER PRIMARY KEY, codigo TEXT NOT NULL);
CREATE TABLE voto_compacto(votacion_id TEXT PRIMARY KEY, sentidos TEXT NOT NULL, partidos TEXT NOT NULL);
"""
LETRA = {"si": "S", "no": "N", "abstencion": "A", "no_vota": "-"}
SENTIDO = {v: k for k, v in LETRA.items()}

_VOT = "SELECT id FROM votacion WHERE fuente=:f AND anio=:a"
_ASU = f"SELECT DISTINCT asunto_id FROM votacion WHERE fuente=:f AND anio=:a"
TABLAS_ANIO = [
    ("asunto", f"id IN ({_ASU})"),
    ("ficha", f"asunto_id IN ({_ASU})"),
    ("votacion", "fuente=:f AND anio=:a"),
    ("voto_partido", f"votacion_id IN ({_VOT})"),
    ("relacion", "fuente=:f AND anio=:a"),
    ("afinidad", "fuente=:f AND anio=:a"),
    ("afinidad_onu", "anio=:a AND :f='onu'"),
    ("miembro", "id IN (SELECT DISTINCT vo.miembro_id FROM voto vo JOIN votacion v ON v.id=vo.votacion_id "
                "WHERE v.fuente=:f AND v.anio=:a)"),
]
TABLAS_COMUN = ["partido"]


def _columnas(con, tabla, esquema="main"):
    return [r[1] for r in con.execute(f"PRAGMA {esquema}.table_info({tabla})")]


def _pk(con, tabla):
    pk = [r[1] for r in sorted(con.execute(f"PRAGMA table_info({tabla})"), key=lambda r: r[5]) if r[5]]
    return ", ".join(pk) if pk else ", ".join(_columnas(con, tabla))


def _crear(ruta):
    if ruta.exists():
        ruta.unlink()
    con = sqlite3.connect(ruta)
    db.init(con, catalogos=False)
    for tabla in ("voto", "pais", "fuente", "camara", "tema", "tipo_relacion", "estado_fuente"):
        con.execute(f"DROP TABLE {tabla}")
    for (indice,) in con.execute("SELECT name FROM sqlite_master WHERE type='index' AND sql IS NOT NULL").fetchall():
        con.execute(f"DROP INDEX {indice}")
    con.executescript(ESQUEMA_COMPACTO)
    return con


def _esquema(con):
    return "\n".join(r[0] for r in con.execute("SELECT sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY name"))


def _copiar(origen, destino, tabla, where="1=1", args=None):
    cols = [c for c in _columnas(origen, tabla) if c in set(_columnas(destino, tabla))]
    lista = ", ".join(cols)
    filas = origen.execute(f"SELECT {lista} FROM {tabla} WHERE {where} ORDER BY {_pk(origen, tabla)}", args or {}).fetchall()
    destino.executemany(f"INSERT INTO {tabla} ({lista}) VALUES ({','.join('?' * len(cols))})", filas)
    return filas


def _huella(h, filas):
    for f in filas:
        h.update(repr(tuple(f)).encode())


def _compacto(con, fuente, anio):
    ids = [r[0] for r in con.execute(
        "SELECT DISTINCT vo.miembro_id FROM voto vo JOIN votacion v ON v.id=vo.votacion_id WHERE v.fuente=? AND v.anio=? ORDER BY 1",
        (fuente, anio))]
    pos = {m: i for i, m in enumerate(ids)}
    partidos = sorted({r[0] for r in con.execute(
        "SELECT DISTINCT vo.partido FROM voto vo JOIN votacion v ON v.id=vo.votacion_id WHERE v.fuente=? AND v.anio=?", (fuente, anio))})
    pidx = {p: i for i, p in enumerate(partidos)}
    sentidos = defaultdict(lambda: ["."] * len(ids))
    grupos = defaultdict(lambda: ["."] * len(ids))
    for vid, mid, partido, sentido in con.execute(
            "SELECT vo.votacion_id, vo.miembro_id, vo.partido, vo.sentido FROM voto vo JOIN votacion v ON v.id=vo.votacion_id "
            "WHERE v.fuente=? AND v.anio=?", (fuente, anio)):
        sentidos[vid][pos[mid]] = LETRA.get(sentido, "-")
        grupos[vid][pos[mid]] = chr(48 + pidx[partido])
    votos = [(vid, "".join(sentidos[vid]), "".join(grupos[vid])) for vid in sorted(sentidos)]
    return list(enumerate(ids)), list(enumerate(partidos)), votos


def partir(con=None, log=print):
    """Genera data/bd/ desde la base de trabajo; solo reescribe los ficheros que cambian."""
    con = con or db.connect()
    BD_DIR.mkdir(parents=True, exist_ok=True)
    manifiesto = json.loads(MANIFIESTO.read_text(encoding="utf-8")) if MANIFIESTO.exists() else {}
    nuevo, cambios = {}, 0

    def escribir(nombre, rellenar):
        nonlocal cambios
        final = BD_DIR / f"{nombre}.sqlite"
        tmp = BD_DIR / f"{nombre}.sqlite.tmp"
        final.parent.mkdir(parents=True, exist_ok=True)
        destino = _crear(tmp)
        h = hashlib.sha256(_esquema(destino).encode())
        resumen = rellenar(destino, h)
        destino.commit()
        destino.execute("VACUUM")
        destino.close()
        huella = h.hexdigest()
        if manifiesto.get(nombre, {}).get("huella") == huella and final.exists():
            tmp.unlink()
        else:
            tmp.replace(final)
            cambios += 1
            log(f"  {nombre}.sqlite: actualizado ({final.stat().st_size / 1e6:.1f} MB)")
        nuevo[nombre] = {"huella": huella, **resumen, "bytes": final.stat().st_size}
        if final.stat().st_size > LIMITE_AVISO:
            log(f"  ! {nombre}.sqlite supera {LIMITE_AVISO / 1e6:.0f} MB: GitHub avisa desde 50 MB y rechaza más de 100 MB")

    def comun(destino, h):
        for t in TABLAS_COMUN:
            _huella(h, _copiar(con, destino, t))
        return {}

    escribir("comun", comun)
    for fuente, anio in con.execute("SELECT DISTINCT fuente, anio FROM votacion ORDER BY 1, 2").fetchall():
        def rellenar(destino, h, fuente=fuente, anio=anio):
            n = {}
            for t, where in TABLAS_ANIO:
                filas = _copiar(con, destino, t, where, {"f": fuente, "a": anio})
                _huella(h, filas)
                n[t] = len(filas)
            plantilla, partidos, votos = _compacto(con, fuente, anio)
            destino.executemany("INSERT INTO plantilla VALUES (?,?)", plantilla)
            destino.executemany("INSERT INTO partido_idx VALUES (?,?)", partidos)
            destino.executemany("INSERT INTO voto_compacto VALUES (?,?,?)", votos)
            for x in (plantilla, partidos, votos):
                _huella(h, x)
            return {"fuente": fuente, "anio": anio, "votaciones": n["votacion"], "asuntos": n["asunto"]}

        escribir(f"{fuente}/{anio}", rellenar)
    vigentes = {BD_DIR / f"{n}.sqlite" for n in nuevo}
    for viejo in BD_DIR.rglob("*.sqlite"):
        if viejo not in vigentes:
            viejo.unlink()
            log(f"  {viejo.relative_to(BD_DIR).as_posix()}: borrado")
    for carpeta in sorted((d for d in BD_DIR.rglob("*") if d.is_dir()), reverse=True):
        if not any(carpeta.iterdir()):
            carpeta.rmdir()
    MANIFIESTO.write_text(json.dumps(nuevo, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    estado = defaultdict(dict)
    for f, clave, valor in con.execute("SELECT fuente, clave, valor FROM estado_fuente ORDER BY 1, 2"):
        estado[f][clave] = json.loads(valor) if valor else None
    ESTADO.write_text(json.dumps(estado, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    total = sum(v["bytes"] for v in nuevo.values())
    log(f"Base troceada en {BD_DIR}: {len(nuevo)} ficheros ({cambios} actualizados), {total / 1e6:.1f} MB")


def unir(ruta=DB_PATH, log=print):
    """Reconstruye la base de trabajo desde data/bd/ (el voto nominal se expande a filas)."""
    if not (BD_DIR / "comun.sqlite").exists():
        raise SystemExit(f"No hay base troceada en {BD_DIR}")
    manifiesto = json.loads(MANIFIESTO.read_text(encoding="utf-8"))
    for sufijo in ("", "-wal", "-shm"):
        p = ruta.with_name(ruta.name + sufijo)
        if p.exists():
            p.unlink()
    con = db.connect(ruta)
    db.init(con)
    con.execute("ATTACH DATABASE ? AS c", (str(BD_DIR / "comun.sqlite"),))
    for t in TABLAS_COMUN:
        cols = ", ".join(c for c in _columnas(con, t, "c") if c in set(_columnas(con, t)))
        con.execute(f"INSERT OR REPLACE INTO main.{t} ({cols}) SELECT {cols} FROM c.{t}")
    con.commit()
    con.execute("DETACH DATABASE c")
    if ESTADO.exists():
        estado = json.loads(ESTADO.read_text(encoding="utf-8"))
        con.executemany("INSERT OR REPLACE INTO estado_fuente VALUES (?,?,?)",
                        [(f, k, json.dumps(v) if v is not None else None) for f, d in estado.items() for k, v in d.items()])
    for nombre in manifiesto:
        if nombre == "comun":
            continue
        con.execute("ATTACH DATABASE ? AS l", (str(BD_DIR / f"{nombre}.sqlite"),))
        for t, _ in TABLAS_ANIO:
            cols = ", ".join(c for c in _columnas(con, t, "l") if c in set(_columnas(con, t)))
            con.execute(f"INSERT OR IGNORE INTO main.{t} ({cols}) SELECT {cols} FROM l.{t}")
        plantilla = dict(con.execute("SELECT pos, miembro_id FROM l.plantilla"))
        partidos = dict(con.execute("SELECT idx, codigo FROM l.partido_idx"))
        filas = []
        for vid, sentidos, gs in con.execute("SELECT votacion_id, sentidos, partidos FROM l.voto_compacto").fetchall():
            for i, (s, g) in enumerate(zip(sentidos, gs)):
                if s != ".":
                    filas.append((vid, plantilla[i], partidos[ord(g) - 48], SENTIDO[s]))
        con.executemany("INSERT INTO voto VALUES (?,?,?,?)", filas)
        con.commit()
        con.execute("DETACH DATABASE l")
    n = con.execute("SELECT COUNT(*) FROM votacion").fetchone()[0]
    m = con.execute("SELECT COUNT(*) FROM voto").fetchone()[0]
    log(f"Base de trabajo reconstruida en {ruta}: {len(manifiesto) - 1} ficheros, {n} votaciones, {m} votos")
    return con
