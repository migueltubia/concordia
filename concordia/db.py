"""Base de trabajo (data/concordia.sqlite): todo junto y con el voto en filas.

No se versiona: se reconstruye con `python -m concordia unir` desde data/bd/, que va troceada por
fuente y año (almacen.py).
"""

import sqlite3

from .config import DATA_DIR, DB_PATH

SCHEMA = """
-- Países y territorios (catálogo de concordia/datos/paises.json).
CREATE TABLE IF NOT EXISTS pais(
  iso3 TEXT PRIMARY KEY, iso2 TEXT, num TEXT, nombre TEXT NOT NULL, nombre_en TEXT, region TEXT, subregion TEXT,
  lat REAL, lon REAL, sucesor TEXT, en_mapa INTEGER
);

-- Fuentes de votaciones: un parlamento nacional (con una o dos cámaras) o un organismo internacional.
CREATE TABLE IF NOT EXISTS fuente(
  codigo TEXT PRIMARY KEY, pais TEXT, nombre TEXT NOT NULL, corto TEXT, tipo TEXT, detalle TEXT, web TEXT,
  licencia TEXT, desde INTEGER, notas TEXT, orden INTEGER
);
CREATE TABLE IF NOT EXISTS camara(
  codigo TEXT PRIMARY KEY, fuente TEXT NOT NULL, nombre TEXT NOT NULL, corto TEXT, escanos INTEGER
);
CREATE TABLE IF NOT EXISTS tema(codigo TEXT PRIMARY KEY, nombre TEXT NOT NULL, subtemas TEXT);
CREATE TABLE IF NOT EXISTS tipo_relacion(codigo TEXT PRIMARY KEY, nombre TEXT NOT NULL);

-- Partidos o grupos de cada fuente. En la ONU, los «grupos» son las regiones.
CREATE TABLE IF NOT EXISTS partido(
  fuente TEXT NOT NULL, codigo TEXT NOT NULL, nombre TEXT, siglas TEXT, color TEXT,
  PRIMARY KEY(fuente, codigo)
);

-- Legisladores (en la ONU, los Estados: el id es el ISO3).
CREATE TABLE IF NOT EXISTS miembro(
  id TEXT PRIMARY KEY, fuente TEXT NOT NULL, nombre TEXT NOT NULL, extra TEXT
);

-- Lo que se vota: un proyecto de ley, una resolución, una moción... Una fila por fuente.
CREATE TABLE IF NOT EXISTS asunto(
  id TEXT PRIMARY KEY, fuente TEXT NOT NULL, codigo TEXT, titulo TEXT NOT NULL, tipo TEXT, fecha TEXT,
  autor TEXT, url TEXT, resultado TEXT, extra TEXT
);
CREATE INDEX IF NOT EXISTS ix_asunto_fuente ON asunto(fuente, fecha);

CREATE TABLE IF NOT EXISTS votacion(
  id TEXT PRIMARY KEY, fuente TEXT NOT NULL, camara TEXT, asunto_id TEXT, fecha TEXT NOT NULL, anio INTEGER NOT NULL,
  numero INTEGER, texto TEXT, tipo TEXT, a_favor INTEGER, en_contra INTEGER, abstenciones INTEGER, no_votan INTEGER,
  mayoria TEXT, resultado TEXT, decisiva INTEGER NOT NULL DEFAULT 0, importante INTEGER NOT NULL DEFAULT 0, url TEXT
);
CREATE INDEX IF NOT EXISTS ix_votacion_anio ON votacion(fuente, anio);
CREATE INDEX IF NOT EXISTS ix_votacion_asunto ON votacion(asunto_id);

-- El partido va en cada voto: es el que tenía el legislador en esa votación.
CREATE TABLE IF NOT EXISTS voto(
  votacion_id TEXT NOT NULL, miembro_id TEXT NOT NULL, partido TEXT NOT NULL, sentido TEXT NOT NULL,
  PRIMARY KEY(votacion_id, miembro_id)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS ix_voto_miembro ON voto(miembro_id);

-- Agregado por partido de cada votación (de `voto`, o tal cual lo publica la fuente).
CREATE TABLE IF NOT EXISTS voto_partido(
  votacion_id TEXT NOT NULL, partido TEXT NOT NULL, si INTEGER NOT NULL, no INTEGER NOT NULL,
  abstencion INTEGER NOT NULL, no_vota INTEGER NOT NULL, sentido TEXT,
  PRIMARY KEY(votacion_id, partido)
) WITHOUT ROWID;

-- Ficha de cada asunto: resumen, tema y relaciones con otros países. Salida de la IA, de reglas o de
-- Escrutinio, siempre con su origen.
CREATE TABLE IF NOT EXISTS ficha(
  asunto_id TEXT PRIMARY KEY, resumen TEXT, tema_principal TEXT, temas_secundarios TEXT, etiquetas TEXT,
  relaciones TEXT, relaciones_origen TEXT, confianza REAL, origen TEXT, version TEXT, creado TEXT
);

-- Relaciones dirigidas entre países (derivadas de fichas y votos): origen -> destino con orientación
-- +1 (positiva), -1 (negativa) o 0 (neutra). via: 'ley' (lo que vota el parlamento de origen) u 'onu'
-- (el voto del país de origen en una resolución sobre el de destino).
CREATE TABLE IF NOT EXISTS relacion(
  asunto_id TEXT NOT NULL, votacion_id TEXT, fuente TEXT NOT NULL, origen TEXT NOT NULL, destino TEXT NOT NULL,
  orientacion INTEGER NOT NULL, tipo TEXT, tema TEXT, anio INTEGER NOT NULL, fecha TEXT, via TEXT NOT NULL,
  aprobado INTEGER, metodo TEXT
);
CREATE INDEX IF NOT EXISTS ix_relacion_anio ON relacion(anio);

-- Coincidencia de voto entre Estados en la Asamblea General de la ONU (votaciones finales).
-- suma: 1 si votan igual, 0,5 si uno se abstiene y el otro no, 0 si votan lo contrario.
CREATE TABLE IF NOT EXISTS afinidad_onu(
  anio INTEGER NOT NULL, a TEXT NOT NULL, b TEXT NOT NULL, suma REAL NOT NULL, total INTEGER NOT NULL,
  PRIMARY KEY(anio, a, b)
) WITHOUT ROWID;

-- Coincidencia entre partidos de una misma fuente, por año y tema ('' = todos).
CREATE TABLE IF NOT EXISTS afinidad(
  fuente TEXT NOT NULL, anio INTEGER NOT NULL, tema TEXT NOT NULL, a TEXT NOT NULL, b TEXT NOT NULL,
  coinciden INTEGER NOT NULL, total INTEGER NOT NULL,
  PRIMARY KEY(fuente, anio, tema, a, b)
) WITHOUT ROWID;

-- Estado de la recogida de cada fuente (marcas para la recogida incremental y últimos errores).
CREATE TABLE IF NOT EXISTS estado_fuente(
  fuente TEXT NOT NULL, clave TEXT NOT NULL, valor TEXT,
  PRIMARY KEY(fuente, clave)
);
"""


def connect(path=DB_PATH):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=900)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    return con


def init(con, catalogos=True):
    con.executescript(SCHEMA)
    if catalogos:
        cargar_catalogos(con)
    con.commit()


def cargar_catalogos(con):
    from . import catalogos, paises
    from .fuentes import FUENTES

    con.execute("DELETE FROM pais")
    con.executemany(
        "INSERT INTO pais VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        [(p["iso3"], p["iso2"], p["num"], p["nombre"], p["nombre_en"], p["region"], p["subregion"], p["lat"], p["lon"],
          p["sucesor"], p["en_mapa"]) for p in paises.todos()],
    )
    con.execute("DELETE FROM tema")
    con.executemany("INSERT INTO tema VALUES (?,?,?)", catalogos.TEMAS)
    con.execute("DELETE FROM tipo_relacion")
    con.executemany("INSERT INTO tipo_relacion VALUES (?,?)", catalogos.TIPOS_RELACION.items())
    con.execute("DELETE FROM fuente")
    con.execute("DELETE FROM camara")
    for orden, f in enumerate(FUENTES.values()):
        con.execute("INSERT INTO fuente VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (f.codigo, f.pais, f.nombre, f.corto, f.tipo, f.detalle, f.web, f.licencia, f.desde, f.notas, orden))
        con.executemany("INSERT INTO camara VALUES (?,?,?,?,?)",
                        [(c, f.codigo, n, corto, e) for c, (n, corto, e) in f.camaras.items()])
        con.executemany("INSERT OR IGNORE INTO partido VALUES (?,?,?,?,?)",
                        [(f.codigo, c, n, s, col) for c, (n, s, col) in f.partidos.items()])
