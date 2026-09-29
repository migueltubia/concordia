"""Exporta los datos para la web, que se abre sin servidor (file://) o en GitHub Pages.

Igual que en Escrutinio, la base va en SQLite comprimida con gzip y en base64 dentro de ficheros .js que
la página carga con <script> (los navegadores no dejan leer ficheros locales con fetch); en el navegador,
sql.js la abre en memoria. Va troceada para que solo se descargue lo que se mira:

- datos/comun.js: países, fuentes, cámaras, temas, partidos, la cobertura de cada fuente por año y cuántos
  eurodiputados tiene cada país cada año (para saber sin descargar el Parlamento Europeo quién tiene).
- datos/<fuente>/<año>.js: lo de un año de una fuente (votaciones, voto por partido, voto nominal compacto,
  asuntos, fichas, afinidad entre partidos). Es lo que usan las vistas de país.
- datos/mundo/<año>.js: la capa del mapa: relaciones entre países de ese año (de todas las fuentes), con
  el título y el resumen de cada asunto, y la afinidad entre Estados en la ONU.
- datos/indice.js: la lista de ficheros con su huella, y los avisos de fuentes que no se pudieron actualizar.

Solo se reescriben los ficheros cuyo contenido cambia.
"""

import base64
import gzip
import hashlib
import json
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from . import paises
from .config import WEB_DIR
from .recoger import avisos

ESQUEMA = """
CREATE TABLE meta(clave TEXT PRIMARY KEY, valor TEXT);
CREATE TABLE pais(iso3 TEXT PRIMARY KEY, iso2 TEXT, nombre TEXT, region TEXT, subregion TEXT, lat REAL, lon REAL,
  sucesor TEXT, en_mapa INTEGER, onu_desde INTEGER, onu_hasta INTEGER, organismo INTEGER);
CREATE TABLE delegacion(fuente TEXT, anio INTEGER, pais TEXT, miembros INTEGER, PRIMARY KEY(fuente, anio, pais));
CREATE TABLE fuente(codigo TEXT PRIMARY KEY, pais TEXT, nombre TEXT, corto TEXT, tipo TEXT, detalle TEXT, web TEXT,
  licencia TEXT, desde INTEGER, notas TEXT, orden INTEGER, anio_min INTEGER, anio_max INTEGER, votaciones INTEGER);
CREATE TABLE camara(codigo TEXT PRIMARY KEY, fuente TEXT, nombre TEXT, corto TEXT, escanos INTEGER);
CREATE TABLE tema(codigo TEXT PRIMARY KEY, nombre TEXT, subtemas TEXT);
CREATE TABLE tipo_relacion(codigo TEXT PRIMARY KEY, nombre TEXT);
CREATE TABLE partido(fuente TEXT, codigo TEXT, nombre TEXT, siglas TEXT, color TEXT, PRIMARY KEY(fuente, codigo));
CREATE TABLE cobertura(fuente TEXT, anio INTEGER, votaciones INTEGER, asuntos INTEGER, fichas_ia INTEGER,
  relaciones INTEGER, PRIMARY KEY(fuente, anio));
CREATE TABLE asunto(id TEXT PRIMARY KEY, fuente TEXT, codigo TEXT, titulo TEXT, tipo TEXT, fecha TEXT, autor TEXT,
  url TEXT, resultado TEXT);
CREATE TABLE ficha(asunto_id TEXT PRIMARY KEY, resumen TEXT, tema_principal TEXT, temas_secundarios TEXT,
  etiquetas TEXT, relaciones TEXT, relaciones_origen TEXT, confianza REAL, origen TEXT);
CREATE TABLE votacion(id TEXT PRIMARY KEY, fuente TEXT, camara TEXT, asunto_id TEXT, fecha TEXT, anio INTEGER,
  numero INTEGER, texto TEXT, tipo TEXT, a_favor INTEGER, en_contra INTEGER, abstenciones INTEGER, no_votan INTEGER,
  mayoria TEXT, resultado TEXT, decisiva INTEGER, importante INTEGER, url TEXT);
CREATE INDEX ix_votacion ON votacion(fuente, anio, fecha);
CREATE INDEX ix_votacion_asunto ON votacion(asunto_id);
CREATE TABLE voto_partido(votacion_id TEXT, partido TEXT, si INTEGER, no INTEGER, abstencion INTEGER, no_vota INTEGER,
  sentido TEXT, PRIMARY KEY(votacion_id, partido)) WITHOUT ROWID;
CREATE TABLE miembro(id TEXT PRIMARY KEY, nombre TEXT);
CREATE TABLE plantilla(fuente TEXT, anio INTEGER, pos INTEGER, miembro_id TEXT, PRIMARY KEY(fuente, anio, pos));
CREATE INDEX ix_plantilla_miembro ON plantilla(miembro_id);
CREATE TABLE partido_idx(fuente TEXT, anio INTEGER, idx INTEGER, codigo TEXT, PRIMARY KEY(fuente, anio, idx));
CREATE TABLE voto_nominal(votacion_id TEXT PRIMARY KEY, sentidos TEXT, partidos TEXT);
CREATE TABLE afinidad(fuente TEXT, anio INTEGER, tema TEXT, a TEXT, b TEXT, coinciden INTEGER, total INTEGER,
  PRIMARY KEY(fuente, anio, tema, a, b)) WITHOUT ROWID;
CREATE TABLE relacion(asunto_id TEXT, fuente TEXT, origen TEXT, destino TEXT, orientacion INTEGER, tipo TEXT,
  tema TEXT, anio INTEGER, fecha TEXT, via TEXT, aprobado INTEGER, metodo TEXT);
CREATE INDEX ix_relacion ON relacion(anio, origen, destino);
CREATE INDEX ix_relacion_destino ON relacion(destino, anio);
CREATE TABLE asunto_mundo(id TEXT PRIMARY KEY, fuente TEXT, fecha TEXT, titulo TEXT, codigo TEXT, tipo TEXT, url TEXT,
  resumen TEXT, tema TEXT, resultado TEXT, anio INTEGER, relaciones TEXT);
CREATE TABLE afinidad_onu(anio INTEGER, a TEXT, b TEXT, suma REAL, total INTEGER, PRIMARY KEY(anio, a, b)) WITHOUT ROWID;
"""
TABLAS_COMUN = ("meta", "pais", "fuente", "camara", "tema", "tipo_relacion", "partido", "cobertura", "delegacion")
# Fuentes cuyos miembros son de varios países, con el país en el id («eup:ESP:257043»).
PLURINACIONALES = ("eup",)
_VOT = "votacion_id IN (SELECT id FROM votacion WHERE fuente=:f AND anio=:a)"
TABLAS_FUENTE = (
    ("asunto", "id IN (SELECT asunto_id FROM votacion WHERE fuente=:f AND anio=:a)"),
    ("ficha", "asunto_id IN (SELECT asunto_id FROM votacion WHERE fuente=:f AND anio=:a)"),
    ("votacion", "fuente=:f AND anio=:a"),
    ("voto_partido", _VOT),
    ("miembro", "id IN (SELECT miembro_id FROM plantilla WHERE fuente=:f AND anio=:a)"),
    ("plantilla", "fuente=:f AND anio=:a"),
    ("partido_idx", "fuente=:f AND anio=:a"),
    ("voto_nominal", _VOT),
    ("afinidad", "fuente=:f AND anio=:a"),
)
TABLAS_MUNDO = (
    ("relacion", "anio=:a"),
    ("asunto_mundo", "anio=:a"),
    ("afinidad_onu", "anio=:a"),
)
_SIN_INDICES = "\n".join(l for l in ESQUEMA.splitlines() if not l.startswith("CREATE INDEX"))
DATOS_DIR = WEB_DIR / "datos"
INDICE = DATOS_DIR / "indice.js"


def construir(con, destino, log=print):
    web = sqlite3.connect(destino)
    web.executescript(ESQUEMA)

    def copiar(tabla, sql, args=()):
        filas = con.execute(sql, args).fetchall()
        if filas:
            web.executemany(f"INSERT OR IGNORE INTO {tabla} VALUES ({','.join('?' * len(filas[0]))})", [tuple(f) for f in filas])
        return len(filas)

    organismos = [p["iso3"] for p in paises.todos() if p.get("organismo")]
    copiar("pais", f"""SELECT p.iso3, p.iso2, p.nombre, p.region, p.subregion, p.lat, p.lon, p.sucesor, p.en_mapa,
                              (SELECT MIN(v.anio) FROM voto vo JOIN votacion v ON v.id=vo.votacion_id WHERE vo.miembro_id=p.iso3 AND v.fuente='onu'),
                              (SELECT MAX(v.anio) FROM voto vo JOIN votacion v ON v.id=vo.votacion_id WHERE vo.miembro_id=p.iso3 AND v.fuente='onu'),
                              CASE WHEN p.iso3 IN ({','.join('?' * len(organismos))}) THEN 1 END
                       FROM pais p""", organismos)
    # Cuántos miembros de cada país tiene cada año una fuente plurinacional (los eurodiputados de cada Estado).
    for f in PLURINACIONALES:
        copiar("delegacion", """SELECT v.fuente, v.anio, substr(vo.miembro_id, length(v.fuente) + 2, 3), COUNT(DISTINCT vo.miembro_id)
                                FROM voto vo JOIN votacion v ON v.id=vo.votacion_id WHERE v.fuente=? GROUP BY 1, 2, 3""", (f,))
    copiar("fuente", """SELECT f.codigo, f.pais, f.nombre, f.corto, f.tipo, f.detalle, f.web, f.licencia, f.desde, f.notas, f.orden,
                                MIN(v.anio), MAX(v.anio), COUNT(v.id)
                         FROM fuente f LEFT JOIN votacion v ON v.fuente=f.codigo GROUP BY f.codigo""")
    copiar("camara", "SELECT codigo, fuente, nombre, corto, escanos FROM camara")
    copiar("tema", "SELECT codigo, nombre, subtemas FROM tema")
    copiar("tipo_relacion", "SELECT codigo, nombre FROM tipo_relacion")
    copiar("partido", "SELECT fuente, codigo, nombre, siglas, color FROM partido")
    copiar("cobertura", """SELECT v.fuente, v.anio, COUNT(*), COUNT(DISTINCT v.asunto_id),
                                   (SELECT COUNT(DISTINCT fi.asunto_id) FROM ficha fi JOIN votacion x ON x.asunto_id=fi.asunto_id
                                    WHERE x.fuente=v.fuente AND x.anio=v.anio AND fi.origen NOT IN ('reglas', 'escrutinio:reglas')),
                                   (SELECT COUNT(*) FROM relacion r WHERE r.fuente=v.fuente AND r.anio=v.anio)
                            FROM votacion v GROUP BY v.fuente, v.anio""")
    n = copiar("votacion", """SELECT id, fuente, camara, asunto_id, fecha, anio, numero, texto, tipo, a_favor, en_contra,
                                     abstenciones, no_votan, mayoria, resultado, decisiva, importante, url FROM votacion""")
    log(f"  votaciones: {n}")
    copiar("asunto", "SELECT id, fuente, codigo, titulo, tipo, fecha, autor, url, resultado FROM asunto")
    copiar("ficha", """SELECT asunto_id, resumen, tema_principal, temas_secundarios, etiquetas, relaciones, relaciones_origen,
                              confianza, origen FROM ficha""")
    copiar("voto_partido", "SELECT votacion_id, partido, si, no, abstencion, no_vota, sentido FROM voto_partido")
    copiar("afinidad", "SELECT fuente, anio, tema, a, b, coinciden, total FROM afinidad")
    copiar("relacion", "SELECT asunto_id, fuente, origen, destino, orientacion, tipo, tema, anio, fecha, via, aprobado, metodo FROM relacion")
    copiar("asunto_mundo", """SELECT a.id, a.fuente, a.fecha, a.titulo, a.codigo, a.tipo, a.url, fi.resumen, fi.tema_principal,
                                     a.resultado, r.anio, fi.relaciones
                              FROM (SELECT DISTINCT asunto_id, anio FROM relacion) r JOIN asunto a ON a.id=r.asunto_id
                              LEFT JOIN ficha fi ON fi.asunto_id=a.id""")
    copiar("afinidad_onu", "SELECT anio, a, b, ROUND(suma, 1), total FROM afinidad_onu")

    # Voto nominal compacto: plantilla por fuente y año, una cadena de sentidos y otra de partidos por votación.
    from .almacen import _compacto

    for fuente, anio in con.execute("SELECT DISTINCT fuente, anio FROM votacion ORDER BY 1, 2").fetchall():
        plantilla, partidos, votos = _compacto(con, fuente, anio)
        web.executemany("INSERT INTO plantilla VALUES (?,?,?,?)", [(fuente, anio, p, m) for p, m in plantilla])
        web.executemany("INSERT INTO partido_idx VALUES (?,?,?,?)", [(fuente, anio, i, c) for i, c in partidos])
        web.executemany("INSERT INTO voto_nominal VALUES (?,?,?)", votos)
    copiar("miembro", "SELECT id, nombre FROM miembro")
    web.executemany("INSERT INTO meta VALUES (?,?)", [("votos", str(con.execute("SELECT COUNT(*) FROM voto").fetchone()[0]))])
    web.commit()
    web.close()


def _trocear(completa, tmp):
    """Parte la SQLite web en comun, <fuente>/<año> y mundo/<año>. Devuelve [(nombre, info, ruta, huella)]."""
    web = sqlite3.connect(completa)
    trozos = []

    def trozo(nombre, esquema, tablas, args, info):
        ruta = tmp / f"{nombre.replace('/', '__')}.sqlite"
        web.execute("ATTACH DATABASE ? AS d", (str(ruta),))
        web.executescript(esquema.replace("CREATE TABLE ", "CREATE TABLE d.").replace("CREATE INDEX ", "CREATE INDEX d."))
        h = hashlib.sha256(esquema.encode())
        for tabla, where in tablas:
            pk = ", ".join(r[1] for r in sorted(web.execute(f"PRAGMA table_info({tabla})"), key=lambda r: r[5]) if r[5]) or "rowid"
            for fila in web.execute(f"SELECT * FROM main.{tabla} WHERE {where} ORDER BY {pk}", args):
                h.update(repr(fila).encode())
            web.execute(f"INSERT INTO d.{tabla} SELECT * FROM main.{tabla} WHERE {where} ORDER BY {pk}", args)
        web.commit()
        web.execute("DETACH DATABASE d")
        d = sqlite3.connect(ruta)
        d.execute("VACUUM")
        d.close()
        trozos.append((nombre, info, ruta, h.hexdigest()[:16]))

    trozo("comun", ESQUEMA, [(t, "1=1") for t in TABLAS_COMUN], {}, {"tipo": "comun"})
    for fuente, anio in web.execute("SELECT DISTINCT fuente, anio FROM votacion ORDER BY 1, 2").fetchall():
        trozo(f"{fuente}/{anio}", _SIN_INDICES, TABLAS_FUENTE, {"f": fuente, "a": anio}, {"tipo": "fuente", "fuente": fuente, "anio": anio})
    for (anio,) in web.execute("SELECT anio FROM relacion UNION SELECT anio FROM afinidad_onu ORDER BY 1").fetchall():
        trozo(f"mundo/{anio}", _SIN_INDICES, TABLAS_MUNDO, {"a": anio}, {"tipo": "mundo", "anio": anio})
    web.close()
    return trozos


def _leer_indice():
    if not INDICE.exists():
        return {}
    texto = INDICE.read_text(encoding="utf-8")
    return json.loads(texto[texto.index("{"):texto.rindex("}") + 1])


def exportar(con, log=print):
    log("Construyendo la base de datos para la web…")
    DATOS_DIR.mkdir(parents=True, exist_ok=True)
    previo = _leer_indice()
    anterior = {f["nombre"]: f for f in previo.get("ficheros", [])}
    ficheros, cambios = [], 0
    with tempfile.TemporaryDirectory() as tmp:
        completa = Path(tmp) / "concordia-web.sqlite"
        construir(con, completa, log)
        for nombre, info, ruta, huella in _trocear(completa, Path(tmp)):
            js = DATOS_DIR / f"{nombre}.js"
            js.parent.mkdir(parents=True, exist_ok=True)
            if not (anterior.get(nombre, {}).get("huella") == huella and js.exists()):
                comprimido = gzip.compress(ruta.read_bytes(), 9, mtime=0)
                js.write_text(
                    "// Generado por `python -m concordia web`. SQLite comprimida con gzip, en base64.\n"
                    f"(window.CONCORDIA_DATOS = window.CONCORDIA_DATOS || {{}})[\"{nombre}\"] =\n"
                    f"\"{base64.b64encode(comprimido).decode()}\";\n", encoding="ascii")
                cambios += 1
            ficheros.append({"nombre": nombre, **info, "huella": huella, "bytes": js.stat().st_size})
    vigentes = {DATOS_DIR / f"{f['nombre']}.js" for f in ficheros} | {INDICE}
    for viejo in DATOS_DIR.rglob("*.js"):
        if viejo not in vigentes:
            viejo.unlink()
    for carpeta in sorted((d for d in DATOS_DIR.rglob("*") if d.is_dir()), reverse=True):
        if not any(carpeta.iterdir()):
            carpeta.rmdir()
    generado = previo.get("generado") if not cambios and previo.get("ficheros") == ficheros else None
    indice = {"generado": generado or datetime.now(timezone.utc).isoformat(timespec="seconds"), "ficheros": ficheros,
              "avisos": avisos(con)}
    INDICE.write_text(
        "// Generado por `python -m concordia web`. Ficheros de datos que carga la web.\n"
        f"window.CONCORDIA_INDICE = {json.dumps(indice, indent=1, ensure_ascii=False)};\n", encoding="utf-8")
    total = sum(f["bytes"] for f in ficheros)
    log(f"Web: {len(ficheros)} ficheros de datos, {total / 1e6:.1f} MB ({cambios} actualizados) -> {DATOS_DIR}")
