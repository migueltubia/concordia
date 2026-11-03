"""Próximas votaciones del pleno del Parlamento Europeo: el orden del día provisional de los próximos plenos.

Sale de la API de datos abiertos del PE (https://data.europarl.europa.eu/api/v2), no de HowTheyVote, que solo
trae lo ya votado: de las sesiones del año («meetings») se toman las de las próximas semanas y, de cada una, lo
que tiene previsto («foreseen-activities»); se guardan los puntos que se votan (PLENARY_VOTE), sin los genéricos
(«Textos cuyo debate haya concluido»). El orden del día cambia hasta el mismo pleno: cada recogida sustituye
entera la anterior.

Es una foto, no un histórico: va en data/bd/agenda_pe.json (texto, para ver los cambios en git) y la web la
lleva en comun.js. Las relaciones con otros países salen del título con las mismas reglas que las votaciones.
"""

import json
import re
from datetime import date, datetime, timedelta, timezone

from . import http_util, relaciones
from .config import BD_DIR

API = "https://data.europarl.europa.eu/api/v2"
FICHERO = BD_DIR / "agenda_pe.json"
SEMANAS = 9  # cuánto por delante: el PE publica el calendario del año, y el orden del día unas semanas antes
_FORMATO = "format=application%2Fld%2Bjson"
# Puntos que no son un asunto: las votaciones sin debate o las peticiones de urgencia, que se concretan en el pleno.
GENERICOS = re.compile(r"^(?:Texts on which debate is closed|\(possibly\)|Votes? on requests for urgent procedure|Voting time)", re.I)
# Informes (A), propuestas de resolución (B) y propuestas comunes (RC): «A-10-2026-0278», que el PE cita como
# «A10-0278/2026». Su página en el sitio del PE no existe hasta que se publican; el orden del día, sí.
DOC_PE = re.compile(r"^(A|B|RC)-(\d+)-(\d{4})-(\d{4})$")
LUGAR = {"BEL_BRU": "Bruselas", "FRA_SXB": "Estrasburgo"}


def _datos(url):
    # Una sesión sin orden del día publicado responde con el cuerpo vacío.
    cuerpo = http_util.fetch(url).decode("utf-8-sig").strip()
    return json.loads(cuerpo).get("data", []) if cuerpo else []


def sesiones(hoy, hasta):
    """Días de pleno entre hoy y `hasta`: [(fecha, id, lugar)]."""
    salida = []
    for anio in sorted({hoy.year, hasta.year}):
        for m in _datos(f"{API}/meetings?year={anio}&{_FORMATO}&limit=500&offset=0"):
            f = m.get("activity_date", "")
            if m.get("had_activity_type", "").endswith("PLENARY_SITTING") and hoy.isoformat() <= f <= hasta.isoformat():
                salida.append((f, m["activity_id"], LUGAR.get((m.get("hasLocality") or "").rsplit("/", 1)[-1])))
    return sorted(salida)


def puntos(fecha, sesion, lugar):
    """Lo que se vota un día de pleno, en el orden previsto."""
    salida = []
    for x in _datos(f"{API}/meetings/{sesion}/foreseen-activities?{_FORMATO}&limit=500"):
        if not x.get("had_activity_type", "").endswith("PLENARY_VOTE"):
            continue
        etiqueta = x.get("activity_label") or {}
        en = (etiqueta.get("en") or "").strip()
        es = (etiqueta.get("es") or "").strip() or en
        if not es or GENERICOS.search(en):
            continue
        docs = [d.rsplit("/", 1)[-1] for d in x.get("based_on_a_realization_of") or []]
        informe = next((DOC_PE.sub(r"\1\2-\4/\3", d) for d in sorted(docs) if DOC_PE.match(d)), None)
        orden = (x.get("documented_by_a_realization_of") or [""])[0].rsplit("/", 1)[-1]  # «OJQ-10-2026-11-24»
        rels = relaciones.relaciones(en, "en", origen="EUU") if en else relaciones.relaciones(es, "es", origen="EUU")
        salida.append({
            "id": x["activity_id"], "fecha": fecha, "lugar": lugar, "punto": x.get("notation_agendaPoint"),
            "orden": float(x.get("activity_order") or 0), "titulo": es, "titulo_en": en, "informe": informe,
            "url": f"https://www.europarl.europa.eu/doceo/document/{orden}_ES.html" if orden else None,
            "relaciones": [{k: r[k] for k in ("pais", "orientacion", "tipo", "motivo")} for r in rels],
        })
    return sorted(salida, key=lambda p: p["orden"])


def recoger(log=print, hoy=None):
    """Descarga el orden del día de los próximos plenos y lo guarda en data/bd/agenda_pe.json."""
    hoy = hoy or date.today()
    dias = sesiones(hoy, hoy + timedelta(weeks=SEMANAS))
    previstos, sin_orden = [], 0
    for fecha, sesion, lugar in dias:
        xs = puntos(fecha, sesion, lugar)
        sin_orden += not xs
        previstos += xs
    log(f"   {len(dias)} días de pleno en las próximas {SEMANAS} semanas, {len(previstos)} votaciones previstas"
        + (f" ({sin_orden} días aún sin orden del día)" if sin_orden else ""))
    anterior = leer()
    agenda = {"actualizado": anterior.get("actualizado"), "plenos": [{"fecha": f, "lugar": l} for f, _, l in dias], "puntos": previstos}
    # Sin cambios, el fichero no se toca (ni su fecha): así no sale en git cada vez que se recoge.
    if {k: v for k, v in agenda.items() if k != "actualizado"} != {k: v for k, v in anterior.items() if k != "actualizado"}:
        agenda["actualizado"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        FICHERO.parent.mkdir(parents=True, exist_ok=True)
        FICHERO.write_text(json.dumps(agenda, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return agenda


def leer():
    try:
        return json.loads(FICHERO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
