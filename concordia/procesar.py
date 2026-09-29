"""Procesado determinista (sin IA) de lo recogido, por fuente y año.

1. Voto por partido, totales y resultado de cada votación (si la fuente no los da).
2. Votación decisiva de cada asunto en cada cámara (la última votación final) y resultado del asunto.
3. Ficha por reglas de los asuntos que no tienen ficha de la IA: tema provisional y relaciones con
   otros países (relaciones.py), del título y de los países que la fuente asocia al asunto
   (asunto.extra["paises"]). Las de la IA nunca se tocan.
4. Relaciones dirigidas entre países (tabla relacion):
   - vía «ley»: lo que vota el parlamento de un país sobre otro (origen: el país de la cámara), en la
     votación decisiva del asunto;
   - vía «onu»: el voto de cada Estado en una resolución sobre otro. Votar sí a una resolución
     negativa para el país X es una relación negativa hacia X; votar no, positiva; la abstención no
     cuenta.
5. Afinidad entre partidos de cada fuente (por año y tema) y entre Estados en la Asamblea General.
"""

import json
from collections import Counter, defaultdict
from itertools import combinations

from . import relaciones as reglas
from .catalogos import ORIENTACION_DE
from .fuentes import FUENTES

TIPOS_CON_RELACION = ("ley", "resolucion", "mocion", "tratado", "otro")


def todos_los_anios(con, fuentes=None, anios=None):
    filtro = None
    if anios:
        filtro = set()
        for parte in anios.split(","):
            if "-" in parte:
                a, b = parte.split("-")
                filtro |= set(range(int(a), int(b) + 1))
            else:
                filtro.add(int(parte))
    tocados = defaultdict(set)
    for f, anio in con.execute("SELECT DISTINCT fuente, anio FROM votacion"):
        if (not fuentes or f in fuentes) and (not filtro or anio in filtro):
            tocados[f].add(anio)
    return dict(tocados)


def _en(anios):
    anios = sorted(anios)
    return f"({','.join(str(int(a)) for a in anios)})"


# ------------------------------------------------------------------ 1. votaciones

def votos_y_totales(con, fuente, anios):
    en = _en(anios)
    vs = f"SELECT id FROM votacion WHERE fuente=? AND anio IN {en}"
    con.execute(f"""DELETE FROM voto_partido WHERE votacion_id IN ({vs})
                    AND EXISTS (SELECT 1 FROM voto vo WHERE vo.votacion_id=voto_partido.votacion_id)""", (fuente,))
    con.execute(f"""INSERT INTO voto_partido
                    SELECT vo.votacion_id, vo.partido, SUM(vo.sentido='si'), SUM(vo.sentido='no'),
                           SUM(vo.sentido='abstencion'), SUM(vo.sentido='no_vota'), NULL
                    FROM voto vo JOIN votacion v ON v.id=vo.votacion_id
                    WHERE v.fuente=? AND v.anio IN {en} GROUP BY 1, 2""", (fuente,))
    # Posición del partido: la de al menos dos tercios de los que votan; si no, «dividido».
    con.execute(f"""UPDATE voto_partido SET sentido = CASE
                      WHEN si + no + abstencion = 0 THEN 'no_vota'
                      WHEN si * 3 >= 2 * (si + no + abstencion) THEN 'si'
                      WHEN no * 3 >= 2 * (si + no + abstencion) THEN 'no'
                      WHEN abstencion * 3 >= 2 * (si + no + abstencion) THEN 'abstencion'
                      ELSE 'dividido' END
                    WHERE votacion_id IN ({vs})""", (fuente,))
    con.execute(f"""UPDATE votacion SET
                      a_favor = (SELECT SUM(si) FROM voto_partido p WHERE p.votacion_id=votacion.id),
                      en_contra = (SELECT SUM(no) FROM voto_partido p WHERE p.votacion_id=votacion.id),
                      abstenciones = (SELECT SUM(abstencion) FROM voto_partido p WHERE p.votacion_id=votacion.id)
                    WHERE fuente=? AND anio IN {en} AND a_favor IS NULL""", (fuente,))
    con.execute(f"""UPDATE votacion SET no_votan = (SELECT SUM(no_vota) FROM voto_partido p WHERE p.votacion_id=votacion.id)
                    WHERE fuente=? AND anio IN {en} AND no_votan IS NULL""", (fuente,))
    con.execute(f"""UPDATE votacion SET resultado = CASE WHEN a_favor > en_contra THEN 'aprobada' ELSE 'rechazada' END
                    WHERE fuente=? AND anio IN {en} AND resultado IS NULL AND a_favor IS NOT NULL""", (fuente,))


# ------------------------------------------------------------------ 2. decisivas y resultado

def decisivas(con, fuente, anios):
    en = _en(anios)
    asuntos = [r[0] for r in con.execute(f"SELECT DISTINCT asunto_id FROM votacion WHERE fuente=? AND anio IN {en}", (fuente,))]
    if not FUENTES[fuente].decisiva_propia:
        porc = defaultdict(list)
        for i in range(0, len(asuntos), 500):
            trozo = asuntos[i:i + 500]
            for vid, aid, camara, tipo, fecha, numero in con.execute(
                    f"SELECT id, asunto_id, camara, tipo, fecha, numero FROM votacion WHERE asunto_id IN ({','.join('?' * len(trozo))})", trozo):
                porc[(aid, camara)].append((fecha, numero or 0, vid, tipo))
        marcar = []
        for vs in porc.values():
            vs.sort()
            finales = [v for v in vs if v[3] == "final"]
            if not finales:
                finales = [v for v in vs if v[3] not in ("procedimiento", "enmienda", "parcial")]
            if finales:
                marcar.append(finales[-1][2])
        con.execute("UPDATE votacion SET decisiva=0 WHERE asunto_id IN (SELECT DISTINCT asunto_id FROM votacion "
                    f"WHERE fuente=? AND anio IN {en})", (fuente,))
        con.executemany("UPDATE votacion SET decisiva=1 WHERE id=?", [(v,) for v in marcar])
    con.execute(f"""UPDATE asunto SET resultado = (
                      SELECT CASE WHEN MAX(v.resultado='aprobada') = 1 THEN 'aprobado'
                                  WHEN COUNT(*) > 0 THEN 'rechazado' END
                      FROM votacion v WHERE v.asunto_id=asunto.id AND v.decisiva=1)
                    WHERE id IN (SELECT DISTINCT asunto_id FROM votacion WHERE fuente=? AND anio IN {en})""", (fuente,))


# ------------------------------------------------------------------ 3. fichas por reglas

def fichas_reglas(con, fuente, anios):
    f = FUENTES[fuente]
    en = _en(anios)
    filas = con.execute(f"""SELECT a.id, a.titulo, a.tipo, a.extra, fi.origen, fi.relaciones_origen,
                                   (SELECT group_concat(DISTINCT v.texto) FROM votacion v WHERE v.asunto_id=a.id AND v.decisiva=1) AS texto
                            FROM asunto a LEFT JOIN ficha fi ON fi.asunto_id=a.id
                            WHERE a.id IN (SELECT DISTINCT asunto_id FROM votacion WHERE fuente=? AND anio IN {en})""",
                        (fuente,)).fetchall()
    nuevas, rels = [], []
    for aid, titulo, tipo, extra, origen, rel_origen, texto in filas:
        extra = json.loads(extra) if extra else {}
        if tipo in TIPOS_CON_RELACION:
            texto_regla = texto if f.codigo == "onu" and texto and texto != titulo else None
            rs = reglas.relaciones(titulo, f.idioma, origen=f.pais, es_onu=f.codigo == "onu", texto=texto_regla,
                                   paises_fuente=extra.get("paises"))
        else:
            rs = []
        if origen is None:
            nuevas.append((aid, reglas.tema(titulo, f.idioma, extra), json.dumps(rs, ensure_ascii=False)))
        elif origen == "reglas" or rel_origen in (None, "reglas"):
            rels.append((json.dumps(rs, ensure_ascii=False), reglas.tema(titulo, f.idioma, extra), origen == "reglas", aid))
    con.executemany("""INSERT INTO ficha(asunto_id, tema_principal, temas_secundarios, etiquetas, relaciones,
                         relaciones_origen, origen, version) VALUES (?,?,'[]','[]',?,'reglas','reglas','reglas-v1')""", nuevas)
    con.executemany("""UPDATE ficha SET relaciones=?1, relaciones_origen='reglas',
                         tema_principal=CASE WHEN ?3 THEN ?2 ELSE tema_principal END WHERE asunto_id=?4""", rels)
    return len(nuevas)


# ------------------------------------------------------------------ 4. relaciones entre países

def relaciones_pais(con, fuente, anios):
    f = FUENTES[fuente]
    en = _en(anios)
    con.execute(f"DELETE FROM relacion WHERE fuente=? AND anio IN {en}", (fuente,))
    if f.pais:
        # Una arista por asunto y país: en la última votación decisiva del asunto (aprobado si alguna cámara
        # lo aprobó en su votación decisiva).
        filas = con.execute(f"""
            SELECT a.id, fi.relaciones, fi.relaciones_origen, fi.tema_principal, v.id, v.fecha, v.anio,
                   (SELECT MAX(x.resultado='aprobada') FROM votacion x WHERE x.asunto_id=a.id AND x.decisiva=1)
            FROM asunto a JOIN ficha fi ON fi.asunto_id=a.id
            JOIN votacion v ON v.id = (SELECT x.id FROM votacion x WHERE x.asunto_id=a.id AND x.decisiva=1
                                       ORDER BY x.fecha DESC, x.numero DESC LIMIT 1)
            WHERE a.fuente=? AND v.anio IN {en} AND a.tipo IN {TIPOS_CON_RELACION}
              AND fi.relaciones IS NOT NULL AND fi.relaciones <> '[]'""", (fuente,)).fetchall()
        aristas = []
        for aid, rels, metodo, tema, vid, fecha, anio, aprobado in filas:
            for r in json.loads(rels):
                if r.get("pais") and r["pais"] != f.pais:
                    aristas.append((aid, vid, fuente, f.pais, r["pais"], ORIENTACION_DE.get(r.get("orientacion"), 0),
                                    r.get("tipo"), tema, anio, fecha, "ley", aprobado, metodo))
        con.executemany("INSERT INTO relacion VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", aristas)
        return len(aristas)
    # ONU: cada Estado que vota una resolución sobre otro.
    filas = con.execute(f"""
        SELECT v.id, a.id, fi.relaciones, fi.relaciones_origen, fi.tema_principal, v.fecha, v.anio, v.resultado
        FROM votacion v JOIN asunto a ON a.id=v.asunto_id JOIN ficha fi ON fi.asunto_id=a.id
        WHERE v.fuente=? AND v.anio IN {en} AND v.tipo='final' AND fi.relaciones IS NOT NULL AND fi.relaciones <> '[]'""",
                        (fuente,)).fetchall()
    n = 0
    for vid, aid, rels, metodo, tema, fecha, anio, res in filas:
        destinos = [(r["pais"], ORIENTACION_DE.get(r.get("orientacion"), 0), r.get("tipo")) for r in json.loads(rels)
                    if r.get("pais") and ORIENTACION_DE.get(r.get("orientacion"), 0)]
        if not destinos:
            continue
        aristas = []
        for miembro, sentido in con.execute("SELECT miembro_id, sentido FROM voto WHERE votacion_id=? AND sentido IN ('si','no')", (vid,)):
            signo = 1 if sentido == "si" else -1
            for destino, orientacion, tipo in destinos:
                if miembro != destino:
                    aristas.append((aid, vid, fuente, miembro, destino, orientacion * signo, tipo, tema, anio, fecha, "onu",
                                    int(res == "aprobada"), metodo))
        con.executemany("INSERT INTO relacion VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", aristas)
        n += len(aristas)
    return n


# ------------------------------------------------------------------ 5. afinidades

def afinidad_partidos(con, fuente, anios):
    con.execute(f"DELETE FROM afinidad WHERE fuente=? AND anio IN {_en(anios)}", (fuente,))
    if fuente == "onu":
        return
    for anio in anios:
        cuenta = defaultdict(lambda: [0, 0])
        por_votacion = defaultdict(dict)
        tema_de = {}
        for vid, partido, sentido, tema in con.execute(
                """SELECT p.votacion_id, p.partido, p.sentido, fi.tema_principal FROM voto_partido p
                   JOIN votacion v ON v.id=p.votacion_id LEFT JOIN ficha fi ON fi.asunto_id=v.asunto_id
                   WHERE v.fuente=? AND v.anio=? AND v.tipo <> 'procedimiento' AND p.sentido IN ('si','no','abstencion')""",
                (fuente, anio)):
            por_votacion[vid][partido] = sentido
            tema_de[vid] = tema
        for vid, ps in por_votacion.items():
            for a, b in combinations(sorted(ps), 2):
                igual = int(ps[a] == ps[b])
                for t in ("", tema_de[vid]) if tema_de[vid] else ("",):
                    c = cuenta[(t, a, b)]
                    c[0] += igual
                    c[1] += 1
        con.executemany("INSERT INTO afinidad VALUES (?,?,?,?,?,?,?)",
                        [(fuente, anio, t, a, b, c[0], c[1]) for (t, a, b), c in cuenta.items()])


VALOR = {"si": "S", "abstencion": "A", "no": "N"}
PUNTOS = {("S", "S"): 1.0, ("A", "A"): 1.0, ("N", "N"): 1.0, ("S", "A"): 0.5, ("A", "S"): 0.5, ("N", "A"): 0.5,
          ("A", "N"): 0.5, ("S", "N"): 0.0, ("N", "S"): 0.0}


def afinidad_onu(con, anios):
    """Coincidencia entre cada par de Estados en las votaciones finales de cada año."""
    con.execute(f"DELETE FROM afinidad_onu WHERE anio IN {_en(anios)}")
    for anio in anios:
        votaciones = [r[0] for r in con.execute("SELECT id FROM votacion WHERE fuente='onu' AND anio=? AND tipo='final' ORDER BY id", (anio,))]
        if not votaciones:
            continue
        pos = {v: i for i, v in enumerate(votaciones)}
        cadenas = defaultdict(lambda: ["-"] * len(votaciones))
        for vid, miembro, sentido in con.execute(
                "SELECT vo.votacion_id, vo.miembro_id, vo.sentido FROM voto vo JOIN votacion v ON v.id=vo.votacion_id "
                "WHERE v.fuente='onu' AND v.anio=? AND v.tipo='final'", (anio,)):
            if sentido in VALOR:
                cadenas[miembro][pos[vid]] = VALOR[sentido]
        estados = sorted(cadenas)
        texto = {e: "".join(cadenas[e]) for e in estados}
        filas = []
        for a, b in combinations(estados, 2):
            c = Counter(zip(texto[a], texto[b]))
            total = sum(n for par, n in c.items() if par in PUNTOS)
            if total:
                filas.append((anio, a, b, sum(PUNTOS[par] * n for par, n in c.items() if par in PUNTOS), total))
        con.executemany("INSERT INTO afinidad_onu VALUES (?,?,?,?,?)", filas)


# ------------------------------------------------------------------ todo

def limpiar_huerfanos(con, fuente):
    """Asuntos que se han quedado sin votaciones (un conector que reagrupa) y sus fichas y relaciones."""
    huerfanos = [r[0] for r in con.execute(
        "SELECT id FROM asunto WHERE fuente=? AND id NOT IN (SELECT DISTINCT asunto_id FROM votacion WHERE fuente=?)", (fuente, fuente))]
    for i in range(0, len(huerfanos), 500):
        trozo = huerfanos[i:i + 500]
        m = ",".join("?" * len(trozo))
        for tabla, col in (("relacion", "asunto_id"), ("ficha", "asunto_id"), ("asunto", "id")):
            con.execute(f"DELETE FROM {tabla} WHERE {col} IN ({m})", trozo)
    return len(huerfanos)


def procesar(con, tocados, log=print):
    if not tocados:
        log("Nada que procesar")
        return
    for fuente, anios in tocados.items():
        if not anios:
            continue
        if (n := limpiar_huerfanos(con, fuente)):
            log(f"  {fuente}: {n} asuntos sin votaciones eliminados")
        anios = sorted(anios)
        log(f"Procesando {fuente}: {len(anios)} años ({anios[0]}–{anios[-1]})")
        for i in range(0, len(anios), 8):
            trozo = anios[i:i + 8]
            votos_y_totales(con, fuente, trozo)
            decisivas(con, fuente, trozo)
            nuevas = fichas_reglas(con, fuente, trozo)
            n = relaciones_pais(con, fuente, trozo)
            afinidad_partidos(con, fuente, trozo)
            if fuente == "onu":
                afinidad_onu(con, trozo)
            con.commit()
            log(f"  {trozo[0]}–{trozo[-1]}: {nuevas} fichas por reglas nuevas, {n} relaciones")
    con.commit()


def estado(con, log=print):
    for f, n, a, d, h in con.execute("""SELECT fuente, COUNT(*), COUNT(DISTINCT asunto_id), MIN(fecha), MAX(fecha)
                                         FROM votacion GROUP BY fuente ORDER BY fuente"""):
        fichas = dict(con.execute("""SELECT COALESCE(fi.origen, 'sin ficha'), COUNT(*) FROM asunto a
                                     LEFT JOIN ficha fi ON fi.asunto_id=a.id WHERE a.fuente=? GROUP BY 1""", (f,)).fetchall())
        rel = con.execute("SELECT COUNT(*) FROM relacion WHERE fuente=?", (f,)).fetchone()[0]
        log(f"{f:4} {n:7} votaciones · {a:6} asuntos · {d} a {h} · relaciones {rel} · fichas {fichas}")
    log(f"Votos nominales: {con.execute('SELECT COUNT(*) FROM voto').fetchone()[0]}")
