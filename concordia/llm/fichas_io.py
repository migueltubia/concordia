"""Fichas IA: qué falta, cómo se guardan y cómo se importan o exportan.

La fuente de verdad son los JSONL de data/llm/ (una línea por ficha, con el modelo que la hizo), que se
versionan: la base se puede reconstruir sin volver a llamar a la IA.

- data/llm/fichas/<fuente>/<AAAA-MM>.jsonl: fichas completas (resumen, tema, etiquetas, relaciones).
- data/llm/relaciones/<fuente>/<AAAA-MM>.jsonl: solo relaciones, para asuntos que ya tienen resumen y tema
  de otra parte (las fichas de Escrutinio en España).
"""

import glob
import json
from collections import defaultdict
from datetime import datetime, timezone

from .. import paises
from ..config import LLM_DIR
from ..fuentes import FUENTES
from .prompt import VERSION_PROMPT, instrucciones_fichas, instrucciones_relaciones, validar, validar_relaciones

FICHAS_DIR = LLM_DIR / "fichas"
RELACIONES_DIR = LLM_DIR / "relaciones"
PENDIENTES_DIR = LLM_DIR / "pendientes"
# Lo que no necesita ficha: el procedimiento de la cámara y los nombramientos.
SIN_FICHA = ("procedimiento", "nombramiento")


def _ahora():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _origen_de(fuente):
    return FUENTES[fuente].pais


def _item(r, fuente):
    f = FUENTES[fuente]
    item = {"id": r["id"], "pais_camara": paises.nombre(f.pais) if f.pais else "Asamblea General de la ONU",
            "camara": f.nombre, "fecha": r["fecha"], "tipo": r["tipo"], "titulo": r["titulo"]}
    if r["codigo"]:
        item["codigo"] = r["codigo"]
    if r["votado"] and r["votado"] != r["titulo"]:
        item["votado"] = r["votado"][:300]
    extra = json.loads(r["extra"]) if r["extra"] else {}
    if extra.get("etiqueta") and extra["etiqueta"].lower() not in r["titulo"].lower():
        item["etiqueta"] = extra["etiqueta"]
    return item


_CONSULTA = """
    SELECT a.id, a.fuente, a.titulo, a.tipo, a.fecha, a.codigo, a.extra, fi.resumen, fi.tema_principal,
           (SELECT v.texto FROM votacion v WHERE v.asunto_id=a.id AND v.decisiva=1 LIMIT 1) AS votado
    FROM asunto a LEFT JOIN ficha fi ON fi.asunto_id=a.id
    WHERE {cond} AND a.tipo NOT IN ('procedimiento', 'nombramiento') {fuentes}
    ORDER BY substr(a.fecha, 1, 4) DESC, a.fuente, a.fecha DESC LIMIT ?"""


def items_pendientes(con, limite=300, fuentes=None):
    """Asuntos sin ficha de IA (ni de Escrutinio), los más recientes primero y repartidos entre fuentes."""
    f_sql = f"AND a.fuente IN ({','.join('?' * len(fuentes))})" if fuentes else ""
    cond = "(fi.origen IS NULL OR fi.origen = 'reglas') AND a.fuente <> 'esp'"
    filas = con.execute(_CONSULTA.format(cond=cond, fuentes=f_sql), (*(fuentes or []), limite)).fetchall()
    return [_item(r, r["fuente"]) for r in filas]


def items_relaciones(con, limite=300, fuentes=None):
    """Asuntos con resumen de otra parte (Escrutinio) cuyas relaciones solo han visto las reglas.

    Solo los que pueden tener relaciones: las reglas han visto un país o el tema es exterior o defensa.
    """
    f_sql = f"AND a.fuente IN ({','.join('?' * len(fuentes))})" if fuentes else ""
    cond = ("fi.origen LIKE 'escrutinio%' AND COALESCE(fi.relaciones_origen, 'reglas') = 'reglas' "
            "AND (fi.relaciones <> '[]' OR fi.tema_principal IN ('EXT', 'DEF', 'MIG'))")
    filas = con.execute(_CONSULTA.format(cond=cond, fuentes=f_sql), (*(fuentes or []), limite)).fetchall()
    salida = []
    for r in filas:
        item = _item(r, r["fuente"])
        if r["resumen"]:
            item["resumen"] = r["resumen"]
        salida.append(item)
    return salida


def _fuente_de(asunto_id):
    return asunto_id.split(":", 1)[0].split("-")[0]


def guardar_fichas(con, fichas, modelo):
    """Guarda fichas completas ya validadas. Devuelve los años tocados por fuente."""
    filas = []
    for f in fichas:
        filas.append((f["id"], f["resumen"].strip(), f["tema_principal"], json.dumps(f["temas_secundarios"], ensure_ascii=False),
                      json.dumps(f["etiquetas"], ensure_ascii=False), json.dumps(f["relaciones"], ensure_ascii=False), modelo,
                      f.get("confianza"), modelo, f.get("_version") or VERSION_PROMPT, f.get("_creado") or _ahora()))
    con.executemany(
        """INSERT INTO ficha(asunto_id, resumen, tema_principal, temas_secundarios, etiquetas, relaciones, relaciones_origen,
             confianza, origen, version, creado)
           SELECT ?,?,?,?,?,?,?,?,?,?,? WHERE EXISTS (SELECT 1 FROM asunto WHERE id=?1)
           ON CONFLICT(asunto_id) DO UPDATE SET resumen=excluded.resumen, tema_principal=excluded.tema_principal,
             temas_secundarios=excluded.temas_secundarios, etiquetas=excluded.etiquetas, relaciones=excluded.relaciones,
             relaciones_origen=excluded.relaciones_origen, confianza=excluded.confianza, origen=excluded.origen,
             version=excluded.version, creado=excluded.creado""", filas)
    return anios_de(con, [f["id"] for f in fichas])


def guardar_relaciones(con, lista, modelo):
    con.executemany("UPDATE ficha SET relaciones=?, relaciones_origen=? WHERE asunto_id=?",
                    [(json.dumps(r["relaciones"], ensure_ascii=False), modelo, r["id"]) for r in lista])
    return anios_de(con, [r["id"] for r in lista])


def anios_de(con, ids):
    tocados = defaultdict(set)
    for i in range(0, len(ids), 500):
        trozo = ids[i:i + 500]
        for f, a in con.execute(f"SELECT DISTINCT fuente, anio FROM votacion WHERE asunto_id IN ({','.join('?' * len(trozo))})", trozo):
            tocados[f].add(a)
    return tocados


def anotar(carpeta, fuente, lineas):
    """Añade las fichas al JSONL del mes de su fuente (lo que se versiona)."""
    ruta = carpeta / fuente / f"{datetime.now(timezone.utc):%Y-%m}.jsonl"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "a", encoding="utf-8") as fh:
        for l in lineas:
            fh.write(json.dumps(l, ensure_ascii=False) + "\n")


def importar_todo(con, log=print):
    """Carga todas las fichas y relaciones versionadas en data/llm/. Devuelve los años tocados."""
    tocados = defaultdict(set)
    n = 0
    for carpeta, completa in ((FICHAS_DIR, True), (RELACIONES_DIR, False)):
        ultima = {}  # si un asunto se repite, vale la última línea (los ficheros van por mes)
        for ruta in sorted(carpeta.glob("*/*.jsonl"), key=lambda r: (r.stem, r.parent.name)):
            for linea in ruta.read_text(encoding="utf-8").splitlines():
                if linea.strip():
                    d = json.loads(linea)
                    ultima[d["id"]] = d
        por_modelo = defaultdict(list)
        for d in ultima.values():
            por_modelo[d.get("_modelo") or "desconocido"].append(d)
        for modelo, lista in por_modelo.items():
            for fuente, trozo in _por_fuente(lista).items():
                # Solo si cambia algo: comparar con lo guardado evita reprocesar todos los años cada vez.
                nuevas = [d for d in trozo if _distinta(con, d, modelo, completa)]
                if not nuevas:
                    continue
                t = guardar_fichas(con, nuevas, modelo) if completa else guardar_relaciones(con, nuevas, modelo)
                for f, anios in t.items():
                    tocados[f] |= anios
                n += len(nuevas)
    con.commit()
    log(f"Fichas IA versionadas: {n} nuevas o cambiadas")
    return dict(tocados)


def _por_fuente(lista):
    d = defaultdict(list)
    for x in lista:
        d[_fuente_de(x["id"])].append(x)
    return d


def _distinta(con, d, modelo, completa):
    r = con.execute("SELECT origen, relaciones_origen, relaciones, resumen FROM ficha WHERE asunto_id=?", (d["id"],)).fetchone()
    if not r:
        return completa and con.execute("SELECT 1 FROM asunto WHERE id=?", (d["id"],)).fetchone() is not None
    if completa:
        return r["origen"] != modelo or r["resumen"] != d.get("resumen")
    return r["relaciones_origen"] != modelo or r["relaciones"] != json.dumps(d["relaciones"], ensure_ascii=False)


def exportar(con, limite=500, fuentes=None, log=print):
    """Deja los pendientes en data/llm/pendientes/ con sus instrucciones, para otro LLM, servicio o persona."""
    PENDIENTES_DIR.mkdir(parents=True, exist_ok=True)
    fichas = items_pendientes(con, limite, fuentes)
    rels = items_relaciones(con, limite, fuentes)
    (PENDIENTES_DIR / "fichas.jsonl").write_text("".join(json.dumps(i, ensure_ascii=False) + "\n" for i in fichas), encoding="utf-8")
    (PENDIENTES_DIR / "relaciones.jsonl").write_text("".join(json.dumps(i, ensure_ascii=False) + "\n" for i in rels), encoding="utf-8")
    (PENDIENTES_DIR / "INSTRUCCIONES.md").write_text(
        "# Fichas pendientes\n\n## fichas.jsonl\n\n" + instrucciones_fichas()
        + "\n\nDevuelve un JSONL con una ficha por línea y el mismo «id»; impórtalo con "
          "`python -m concordia fichas-importar <fichero> --modelo <modelo>`.\n\n## relaciones.jsonl\n\n"
        + instrucciones_relaciones() + "\n", encoding="utf-8")
    log(f"Exportados {len(fichas)} asuntos sin ficha y {len(rels)} para relaciones en {PENDIENTES_DIR}")


def importar(con, patrones, modelo=None, log=print):
    """Importa fichas (completas o solo relaciones) generadas por otra vía y las anota en data/llm/."""
    tocados = defaultdict(set)
    buenas, malas = defaultdict(list), 0
    for patron in patrones:
        for ruta in glob.glob(patron):
            for linea in open(ruta, encoding="utf-8"):
                if not linea.strip():
                    continue
                d = json.loads(linea)
                m = d.pop("_modelo", None) or modelo
                if not m or not d.get("id"):
                    malas += 1
                    continue
                fuente = _fuente_de(d["id"])
                if "resumen" in d:
                    f, errores = validar(d, _origen_de(fuente))
                    if f:
                        buenas[(m, True, fuente)].append(f)
                    else:
                        malas += 1
                else:
                    buenas[(m, False, fuente)].append({"id": d["id"], "relaciones": validar_relaciones(d.get("relaciones"), _origen_de(fuente))})
    for (m, completa, fuente), lista in buenas.items():
        t = guardar_fichas(con, lista, m) if completa else guardar_relaciones(con, lista, m)
        anotar(FICHAS_DIR if completa else RELACIONES_DIR, fuente, [{**x, "_modelo": m} for x in lista])
        for f, anios in t.items():
            tocados[f] |= anios
    con.commit()
    log(f"Importadas {sum(len(v) for v in buenas.values())} fichas; descartadas {malas}")
    return dict(tocados)
