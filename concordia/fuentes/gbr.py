"""Reino Unido: divisiones de la Cámara de los Comunes (Commons Votes API).

La API oficial (https://commonsvotes-api.parliament.uk) da cada división desde 2016 con el voto de
cada diputado y su partido. En los Comunes solo hay voto registrado cuando se pide una división: lo
que se aprueba sin oposición no aparece.
"""

import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from .modelo import Asunto, Fuente, Votacion

FUENTE = Fuente(
    codigo="gbr", pais="GBR", nombre="Parlamento del Reino Unido (Cámara de los Comunes)", corto="Reino Unido",
    tipo="parlamento", detalle="nominal", web="https://votes.parliament.uk", desde=2016, idioma="en",
    licencia="Open Parliament Licence v3.0",
    camaras={"gbr-c": ("Cámara de los Comunes", "Comunes", 650)},
    notas="Solo divisiones (votaciones con recuento); la API empieza en 2016.",
)

API = "https://commonsvotes-api.parliament.uk/data"
POR_PAGINA = 25


def _slug(t):
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")[:80]


def partes(titulo):
    """«Finance (No. 2) Bill: Report Stage New Clause 7» -> («Finance (No. 2) Bill», «Report Stage New Clause 7»)."""
    t = re.sub(r"\s+", " ", titulo or "").strip()
    m = re.match(r"(.+?\b(?:Bill|Motion|Regulations|Order|Order \d{4}|Rules|Treaty|Estimates)(?: \[[^\]]*\])?(?: \d{4})?)\s*[:\-–]\s*(.+)$", t)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return t, None


PROCEDIMIENTO = ("programme", "money resolution", "closure", "ways and means", "adjourn", "sitting", "business of the house",
                 "question be now put", "carry-over", "instruction")


def tipo_asunto(nombre):
    n = nombre.lower()
    if any(k in n for k in PROCEDIMIENTO):
        return "procedimiento"
    if "treaty" in n:
        return "tratado"
    if re.search(r"\bbill\b", n):
        return "ley"
    if re.search(r"\b(regulations|order|rules)\b", n):
        return "ley"
    if "opposition day" in n or "motion" in n or "estimates" in n:
        return "mocion"
    if "speaker" in n:
        return "nombramiento"
    return "otro"


def tipo_votacion(fase, tipo_a):
    f = (fase or "").lower()
    if tipo_a == "procedimiento":
        return "procedimiento"
    if not f:
        return "final" if tipo_a in ("mocion", "ley", "tratado") else "otra"
    if any(k in f for k in PROCEDIMIENTO):
        return "procedimiento"
    # «Reasoned Amendment to Second Reading» es una enmienda para rechazar el proyecto, no la lectura.
    if any(k in f for k in ("amendment", "new clause", "clause", "schedule", "motion to disagree")):
        return "enmienda"
    if any(k in f for k in ("second reading", "third reading")):
        return "final"
    return "final" if tipo_a == "mocion" else "otra"


def _division(ctx, did):
    return ctx.json(f"{API}/division/{did}.json")


def recoger(ctx):
    ultima = ctx.ultima_fecha()
    inicio = f"{ctx.desde}-01-01"
    if ultima and not ctx.completo:
        inicio = (date.fromisoformat(ultima) - timedelta(days=14)).isoformat()
    ids, skip = [], 0
    while True:
        pagina = ctx.json(f"{API}/divisions.json/search?queryParameters.startDate={inicio}"
                          f"&queryParameters.skip={skip}&queryParameters.take={POR_PAGINA}")
        if not pagina:
            break
        ids += [d["DivisionId"] for d in pagina]
        skip += len(pagina)
        if len(pagina) < POR_PAGINA:
            break
    ctx.log(f"   {len(ids)} divisiones desde {inicio}")
    with ThreadPoolExecutor(6) as ex:
        for i in range(0, len(ids), 120):
            detalles = list(ex.map(lambda d: _division(ctx, d), ids[i:i + 120]))
            asuntos, votaciones = {}, []
            for d in detalles:
                fecha = d["Date"][:10]
                nombre, fase = partes(d.get("Title"))
                tipo_a = tipo_asunto(nombre)
                aid = f"gbr:{fecha[:4]}:{_slug(nombre)}" if fase else f"gbr:div{d['DivisionId']}"
                asuntos.setdefault(aid, Asunto(id=aid, titulo=nombre[:400], tipo=tipo_a, fecha=fecha))
                votos = []
                for lista, sentido in (("Ayes", "si"), ("Noes", "no"), ("NoVoteRecorded", "no_vota")):
                    for m in d.get(lista) or []:
                        partido = m.get("PartyAbbreviation") or m.get("Party") or "?"
                        ctx.partido(partido, m.get("Party"), partido, "#" + m["PartyColour"] if m.get("PartyColour") else None)
                        votos.append((f"gbr:{m['MemberId']}", m.get("Name"), partido, sentido))
                si, no = d.get("AyeCount") or 0, d.get("NoCount") or 0
                votaciones.append(Votacion(
                    id=f"gbr:{d['DivisionId']}", fecha=fecha, asunto_id=aid, camara="gbr-c", numero=d.get("Number"),
                    texto=fase or d.get("Title"), tipo=tipo_votacion(fase, tipo_a), a_favor=si, en_contra=no,
                    resultado="aprobada" if si > no else "rechazada",
                    url=f"https://votes.parliament.uk/votes/commons/division/{d['DivisionId']}", votos=votos))
            ctx.guardar(list(asuntos.values()), votaciones)
            ctx.log(f"   {min(i + 120, len(ids))}/{len(ids)}")
