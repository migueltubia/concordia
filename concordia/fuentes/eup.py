"""Parlamento Europeo: el voto de cada eurodiputado en las votaciones nominales del pleno, desde julio de 2019.

Los datos son de HowTheyVote.eu (ODbL), que cada semana publica en GitHub
(https://github.com/HowTheyVote/data/releases) lo que saca de las actas oficiales de votaciones nominales:
una fila por votación (votes.csv, con el procedimiento del Observatorio Legislativo y el título en inglés)
y otra por eurodiputado y votación (member_votes.csv, con su país y su grupo ese día). La API
(https://howtheyvote.eu/api) solo lista las votaciones finales y va de una en una: no se usa.

- Asunto: el procedimiento del Observatorio Legislativo (OEIL), «2026/2874(RSP)». Lo que no tiene
  procedimiento va por documento («C9-0104/2021»), el orden del día por sesión y el resto por título y día.
- Partido: el grupo político europeo (PPE, S&D, Renew...). El país del eurodiputado va en su id
  («eup:ESP:257043»): así se ve cómo votan los eurodiputados de cada país sin cambiar el esquema.
- Origen de las relaciones «por ley»: EUU, la Unión Europea, que en el catálogo de países solo es origen.
- Los países que HowTheyVote asocia a cada votación van en el extra del asunto («paises»), como pista.

Cada semana hay una versión nueva (marca «version»); sin versión nueva no se descarga nada. Con una
versión nueva se guardan otra vez los dos últimos meses, por si HowTheyVote ha corregido algo.
"""

import csv
import gzip
import hashlib
import io
import re
from collections import Counter, defaultdict
from datetime import date, timedelta

from .modelo import Asunto, Fuente, Votacion

FUENTE = Fuente(
    codigo="eup", pais="EUU", nombre="Parlamento Europeo", corto="Parlamento Europeo", tipo="parlamento",
    detalle="nominal", web="https://howtheyvote.eu", desde=2019, idioma="en",
    licencia="HowTheyVote.eu (ODbL), a partir de las actas de votaciones nominales del Parlamento Europeo",
    camaras={"eup-p": ("Pleno del Parlamento Europeo", "Pleno", 720)},
    partidos={
        "EPP": ("Grupo del Partido Popular Europeo", "PPE", "#3399ff"),
        "SD": ("Alianza Progresista de Socialistas y Demócratas", "S&D", "#e02a2a"),
        "RENEW": ("Renew Europe", "Renew", "#e6b800"),
        "GREEN_EFA": ("Los Verdes/Alianza Libre Europea", "Verdes/ALE", "#3fa34d"),
        "ECR": ("Conservadores y Reformistas Europeos", "ECR", "#1d4e9e"),
        "PFE": ("Patriotas por Europa", "PfE", "#6a3d9a"),
        "ESN": ("Europa de las Naciones Soberanas", "ESN", "#7a5c3e"),
        "ID": ("Identidad y Democracia", "ID", "#2b3856"),
        "GUE_NGL": ("La Izquierda (GUE/NGL)", "La Izquierda", "#990000"),
        "NI": ("No inscritos", "NI", "#898781"),
    },
    notas="Votaciones nominales del pleno (también enmiendas y votaciones por partes). El partido es el grupo "
          "europeo; el país de cada eurodiputado permite ver cómo vota cada delegación nacional.",
)

DESCARGAS = "https://github.com/HowTheyVote/data/releases/latest/download"
SENTIDO = {"FOR": "si", "AGAINST": "no", "ABSTENTION": "abstencion", "DID_NOT_VOTE": "no_vota"}
GRUPO = {"GUE_NGL_1995_0": "GUE_NGL"}  # nombre de La Izquierda hasta 2021: es el mismo grupo
GEO = {"XKX": "XKK"}  # Kosovo, con el código del catálogo
REVISAR_DIAS = 60

# Tipo de procedimiento del OEIL -> tipo de asunto.
TIPO_PROCEDIMIENTO = {
    "COD": "ley", "CNS": "ley", "APP": "ley", "NLE": "ley", "BUD": "ley",
    "RSP": "resolucion", "INI": "resolucion", "INL": "resolucion", "DEA": "resolucion", "RPS": "resolucion",
    "DEC": "resolucion", "BUI": "resolucion", "ACI": "resolucion", "INS": "resolucion",
    "REG": "procedimiento", "RSO": "procedimiento",
}
# Peticiones de los grupos para cambiar el orden del día («Wednesday’s agenda – Request by The Left Group –
# Israel»): son trámite, aunque nombren un país.
ORDEN_DEL_DIA = re.compile(r"ordre du jour|demande d[eu]s? groupes?\b|\bagenda\b.*\brequest\b", re.I)

# Lo que se vota viene en francés (las actas de votaciones nominales): lo más frecuente, en español.
TRADUCCION = [
    (r"\(ensemble du texte\)", "(conjunto del texto)"),
    (r"Propositions? de résolution", "Propuesta de resolución"),
    (r"Proposition de la Commission au Conseil", "Propuesta de la Comisión al Consejo"),
    (r"Proposition de la Commission et amendements?", "Propuesta de la Comisión y enmiendas"),
    (r"Proposition de la Commission", "Propuesta de la Comisión"),
    (r"Accord provisoire", "Acuerdo provisional"),
    (r"Projet de décision du Conseil", "Proyecto de decisión del Consejo"),
    (r"Projet de règlement du Conseil", "Proyecto de reglamento del Consejo"),
    (r"Propositions? de décision", "Propuesta de decisión"),
    (r"Décision d'engager des négociations interinstitutionnelles", "Decisión de entablar negociaciones interinstitucionales"),
    (r"Proposition de rejet", "Propuesta de rechazo"),
    (r"Projet de recomm[ae]ndation", "Proyecto de recomendación"),
    (r"Demande de décision d'urgence", "Solicitud de procedimiento de urgencia"),
    (r"Demande de procéder au vote sur les amendements", "Solicitud de votar las enmiendas"),
    (r"Projet commun", "Texto conjunto"),
    (r"Projet du Conseil", "Proyecto del Consejo"),
    (r"Amendements de la commission compétente - votes? séparés?", "Enmiendas de la comisión competente, votación por separado"),
    (r"Procédure d'approbation", "Procedimiento de aprobación"),
    (r"Vote unique", "Votación única"),
    (r"^Résolution$", "Resolución"),
    (r"^Décision$", "Decisión"),
    (r"[Aa]près le considérant", "Después del considerando"),
    (r"[Aa]près le visa", "Después del visto"),
    (r"[Aa]près l'article", "Después del artículo"),
    (r"[Aa]près le §", "Después del §"),
    (r"[Aa]vant le §", "Antes del §"),
    (r"\bConsidérant\b", "Considerando"),
    (r"\bVisa\b", "Visto"),
    (r"\bArticle\b", "Artículo"),
    (r"\b[Aa]m (?=\d)", "Enm. "),
]


def texto_votacion(descripcion):
    t = re.sub(r"\s+", " ", descripcion or "").strip()
    for patron, cambio in TRADUCCION:
        t = re.sub(patron, cambio, t)
    return t or None


def tipo_votacion(v):
    if v["is_main"] == "True":
        return "final"
    # «amendment_number» vale «§» en la votación por partes de un párrafo del texto, que no es una enmienda.
    if re.search(r"\d", v["amendment_number"] or "") or re.search(r"\b[Aa]m \d", v["description"] or ""):
        return "enmienda"
    return "parcial"


def tipo_asunto(tipo_proc, titulo):
    t = titulo.lower()
    if "motion of censure" in t:
        return "mocion"
    if tipo_proc in ("", "NLE", "INS", "RSO") and re.match(r"(proposed )?(election|appointment|nomination)\b", t):
        return "nombramiento"
    if tipo_proc in ("NLE", "APP") and re.search(r"\b(agreement|protocol|convention|accession)\b", t) and "interinstitutional" not in t:
        return "tratado"
    if not tipo_proc and "objection pursuant" in t:
        return "resolucion"
    return TIPO_PROCEDIMIENTO.get(tipo_proc, "otro")


def _leer(ctx, nombre, **kw):
    datos = ctx.fetch(f"{DESCARGAS}/{nombre}", timeout=300, **kw)
    return list(csv.DictReader(io.StringIO(gzip.decompress(datos).decode("utf-8-sig"))))


def _clave_asunto(v):
    """Id del asunto de una votación y, si es el orden del día, su título."""
    if v["procedure_reference"]:
        return f"eup:{v['procedure_reference']}", None
    if v["reference"]:
        return f"eup:{v['reference']}", None
    if ORDEN_DEL_DIA.search(v["display_title"]):
        return f"eup:orden:{v['timestamp'][:10]}", "Orden del día: peticiones de los grupos políticos"
    titulo = v["display_title"] or v["description"] or v["id"]
    return f"eup:{v['timestamp'][:10]}:{hashlib.sha1(titulo.encode()).hexdigest()[:10]}", None


def _titulo(v):
    t = re.sub(r"\s+", " ", v["display_title"] or "").strip()
    if t.lower() == "toutes sections":  # votaciones a distancia del presupuesto de 2021, sin título
        return "Draft general budget of the European Union - all sections"
    return t or v["procedure_title"] or v["reference"] or v["id"]


def asuntos_de(votos, geo):
    """{vote_id: id del asunto} y {id del asunto: Asunto}, con todo lo publicado (los títulos no dependen del lote)."""
    grupos, fijo = defaultdict(list), {}
    for v in votos:
        aid, titulo = _clave_asunto(v)
        grupos[aid].append(v)
        if titulo:
            fijo[aid] = titulo
    de, asuntos = {}, {}
    for aid, vs in grupos.items():
        vs.sort(key=lambda v: (v["timestamp"], int(v["id"])))
        principales = [v for v in vs if v["is_main"] == "True"]
        # El título que HowTheyVote da a la votación final más reciente; si no hay final, el más repetido.
        titulo = fijo.get(aid) or (_titulo(principales[-1]) if principales else Counter(_titulo(v) for v in vs).most_common(1)[0][0])
        primera = vs[0]
        proc = primera["procedure_reference"]
        tipo_proc = primera["procedure_type"]
        extra = {}
        formal = re.sub(r"\s+", " ", primera["procedure_title"] or "").strip()
        if formal and formal.lower() != titulo.lower():
            extra["etiqueta"] = formal[:400]
        paises = sorted({GEO.get(c, c) for v in vs for c in geo.get(v["id"], ())})
        if paises:
            extra["paises"] = paises
        if tipo_proc:
            extra["procedimiento"] = tipo_proc
        asuntos[aid] = Asunto(
            id=aid, titulo=titulo[:400], fecha=primera["timestamp"][:10],
            tipo="procedimiento" if aid in fijo else tipo_asunto(tipo_proc, titulo),
            codigo=proc or primera["reference"] or None,
            url=(f"https://oeil.europarl.europa.eu/oeil/en/procedure-file?reference={proc}" if proc
                 else f"https://howtheyvote.eu/votes/{primera['id']}"),
            extra=extra or None)
        for v in vs:
            de[v["id"]] = aid
    return de, asuntos


def votacion_de(v, aid, votos):
    hora = v["timestamp"][11:19].replace(":", "")
    resultado = {"ADOPTED": "aprobada", "REJECTED": "rechazada"}.get(v["result"])  # antes de 2024, por los totales
    entero = lambda x: int(x) if x not in (None, "") else None
    orden = aid.startswith("eup:orden:")  # la petición concreta va en el título de la votación
    return Votacion(
        id=f"eup:{v['id']}", fecha=v["timestamp"][:10], asunto_id=aid, camara="eup-p",
        numero=int(hora) if hora.isdigit() else None,
        texto=_titulo(v)[:600] if orden else texto_votacion(v["description"]),
        tipo="procedimiento" if orden else tipo_votacion(v),
        a_favor=entero(v["count_for"]), en_contra=entero(v["count_against"]), abstenciones=entero(v["count_abstention"]),
        no_votan=entero(v["count_did_not_vote"]), resultado=resultado,
        url=f"https://howtheyvote.eu/votes/{v['id']}", votos=votos)


def recoger(ctx):
    version = ctx.fetch(f"{DESCARGAS}/last_updated.txt").decode().strip()
    if version == ctx.marca("version") and not ctx.completo:
        ctx.log(f"   sin versión nueva de HowTheyVote (la última es del {version[:10]})")
        return
    inicio = f"{ctx.desde}-01-01"
    ultima = ctx.ultima_fecha()
    if ultima and not ctx.completo:
        inicio = max(inicio, (date.fromisoformat(ultima) - timedelta(days=REVISAR_DIAS)).isoformat())
    ctx.log(f"   versión del {version[:10]}; votaciones desde el {inicio}")

    votos = _leer(ctx, "votes.csv.gz")
    geo = defaultdict(list)
    for r in _leer(ctx, "geo_area_votes.csv.gz"):
        geo[r["vote_id"]].append(r["geo_area_code"])
    nombres = {m["id"]: " ".join(x for x in (m["first_name"], m["last_name"]) if x) for m in _leer(ctx, "members.csv.gz")}
    asunto_de, asuntos = asuntos_de(votos, geo)
    elegidas = {v["id"]: v for v in votos if v["timestamp"][:10] >= inicio}
    ctx.log(f"   {len(votos)} votaciones publicadas, {len(elegidas)} por guardar; descargando el voto de cada eurodiputado…")

    ruta = ctx.cache(f"{DESCARGAS}/member_votes.csv.gz", f"member_votes-{version[:10]}.csv.gz", timeout=1800)
    for viejo in ruta.parent.glob("member_votes-*.csv.gz"):
        if viejo != ruta:
            viejo.unlink()

    guardados, lote = set(), []
    nuevos_grupos = set()

    def vaciar():
        aids = {v.asunto_id for v in lote} - guardados
        ctx.guardar([asuntos[a] for a in sorted(aids)], lote)
        guardados.update(aids)
        lote.clear()

    actual, filas = None, []

    def cerrar():
        if actual in elegidas and filas:
            lote.append(votacion_de(elegidas[actual], asunto_de[actual], list(filas)))
            if len(lote) >= 200:
                vaciar()

    # Viene ordenado por votación: cada una es un bloque seguido de filas, así no hace falta tenerlo todo en memoria.
    with gzip.open(ruta, "rt", encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            if r["vote_id"] != actual:
                cerrar()
                actual, filas = r["vote_id"], []
            if actual not in elegidas:
                continue
            grupo = GRUPO.get(r["group_code"], r["group_code"]) or None
            if grupo and grupo not in FUENTE.partidos and grupo not in nuevos_grupos:
                nuevos_grupos.add(grupo)
                ctx.partido(grupo)
            filas.append((f"eup:{r['country_code']}:{r['member_id']}", nombres.get(r["member_id"]), grupo,
                          SENTIDO.get(r["position"], "no_vota")))
        cerrar()
    if lote:
        vaciar()
    faltan = len(elegidas) - ctx.n_votaciones
    if faltan:
        ctx.log(f"   ! {faltan} votaciones sin voto nominal en member_votes.csv")
    ctx.poner_marca("version", version)
