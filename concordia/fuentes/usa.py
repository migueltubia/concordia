"""Congreso de los Estados Unidos (Cámara de Representantes y Senado): Voteview.

Voteview (Lewis, Poole, Rosenthal, Boche, Rudkin y Sonnet; UCLA) publica un CSV por Congreso y cámara
con cada votación nominal, el voto de cada congresista y su partido, desde 1789, y lo actualiza a
diario. Un Congreso dura dos años (el 119 es 2025-2026). Los cerrados se descargan una vez; el actual se
revisa en cada recogida.
"""

import csv
import io
import re
from datetime import date

from .modelo import Asunto, Fuente, Votacion

FUENTE = Fuente(
    codigo="usa", pais="USA", nombre="Congreso de los Estados Unidos", corto="EEUU", tipo="parlamento",
    detalle="nominal", web="https://voteview.com", desde=2001, idioma="en",
    licencia="Voteview (UCLA): datos públicos",
    camaras={"usa-h": ("Cámara de Representantes", "Cámara", 435), "usa-s": ("Senado", "Senado", 100)},
    partidos={"D": ("Partido Demócrata", "Dem.", "#2a78d6"), "R": ("Partido Republicano", "Rep.", "#e34948"),
              "I": ("Independientes", "Ind.", "#898781")},
    notas="Voto de cada congresista. Se recoge desde 2001 (107.º Congreso); Voteview tiene todo el histórico.",
)

BASE = "https://voteview.com/static/data/out"
PARTIDO = {"100": "D", "200": "R"}
CAMARA = {"House": ("H", "usa-h"), "Senate": ("S", "usa-s")}
SENTIDO = {"1": "si", "2": "si", "3": "si", "4": "no", "5": "no", "6": "no", "7": "abstencion", "8": "abstencion",
           "9": "no_vota"}

# Prefijo del número de iniciativa: (código legible, tipo de asunto, tramo de la URL de congress.gov)
PREFIJOS = [
    ("HCONRES", "H.Con.Res.", "resolucion", "house-concurrent-resolution"),
    ("SCONRES", "S.Con.Res.", "resolucion", "senate-concurrent-resolution"),
    ("HJRES", "H.J.Res.", "ley", "house-joint-resolution"),
    ("SJRES", "S.J.Res.", "ley", "senate-joint-resolution"),
    ("HRES", "H.Res.", "resolucion", "house-resolution"),
    ("SRES", "S.Res.", "resolucion", "senate-resolution"),
    ("HR", "H.R.", "ley", "house-bill"),
    ("S", "S.", "ley", "senate-bill"),
    ("PN", "PN", "nombramiento", None),
    ("TREATY", "Tratado", "tratado", None),
]


def congreso_de(anio):
    return (anio - 1789) // 2 + 1


def ordinal(n):
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def iniciativa(numero, congreso):
    """«HR9497» -> («H.R. 9497», tipo, url)."""
    numero = (numero or "").strip().upper().replace(" ", "")
    for pref, legible, tipo, tramo in PREFIJOS:
        m = re.fullmatch(pref + r"(\d+)(?:-\d+)?", numero)
        if m:
            n = int(m.group(1))
            if tramo:
                url = f"https://www.congress.gov/bill/{ordinal(congreso)}-congress/{tramo}/{n}"
            elif pref == "PN":
                url = f"https://www.congress.gov/nomination/{ordinal(congreso)}-congress/{n}"
            else:
                url = None
            return f"{legible} {n}", tipo, url
    return numero or None, "otro", None


def tipo_votacion(pregunta, tipo_asunto):
    p = (pregunta or "").lower()
    if "nomination" in p or "speaker" in p:
        return "nombramiento"
    if any(k in p for k in ("amendment", "motion to strike")) and "senate amendment" not in p and "house amendment" not in p:
        return "enmienda"
    if any(k in p for k in ("cloture", "table", "previous question", "recommit", "motion to proceed", "journal", "quorum",
                            "adjourn", "waive", "point of order", "discharge", "instruct", "reconsider", "question of consideration")):
        return "procedimiento"
    if any(k in p for k in ("passage", "suspend the rules and pass", "suspend the rules and agree", "conference report",
                            "concur", "override", "objections of the president", "ratification", "agreeing to the resolution",
                            "on the resolution", "on the joint resolution", "on the concurrent resolution", "on the bill")):
        return "final"
    return "otra"


RESULTADO_SI = ("passed", "agreed", "adopted", "confirmed", "concurred", "ratified", "sustained", "overridden", "cloture invoked")
RESULTADO_NO = ("failed", "rejected", "not agreed", "defeated", "not sustained", "not invoked", "not passed")


def resultado(texto, si, no):
    t = (texto or "").lower()
    if any(k in t for k in RESULTADO_NO):
        return "rechazada"
    if any(k in t for k in RESULTADO_SI):
        return "aprobada"
    return "aprobada" if (si or 0) > (no or 0) else "rechazada"


def _csv(ctx, nombre, actual):
    ruta = ctx.cache(f"{BASE}/{nombre.split('_')[-1]}/{nombre}.csv", f"{nombre}.csv", caduca_horas=6 if actual else None)
    return list(csv.DictReader(io.StringIO(ruta.read_text(encoding="utf-8", errors="replace"))))


def _apellido(t):
    """«McCONNELL» -> «McConnell», «VAN HOLLEN» -> «Van Hollen»."""
    return re.sub(r"\bMc(\w)", lambda m: "Mc" + m.group(1).upper(), t.title())


def _nombre(bioname, estado):
    partes = [p.strip() for p in (bioname or "").split(",", 1)]
    apellido = _apellido(partes[0]) if partes else ""
    return f"{partes[1]} {apellido}".strip() + (f" ({estado})" if estado else "") if len(partes) > 1 else apellido


def cargar_congreso(ctx, congreso, camara, actual, desde_fecha=None):
    letra, codigo_camara = CAMARA[camara]
    base = f"{letra}{congreso:03d}"
    miembros = {}
    for m in _csv(ctx, f"{base}_members", actual):
        if m["chamber"] != camara:
            continue
        miembros[m["icpsr"]] = (_nombre(m["bioname"], m["state_abbrev"]), PARTIDO.get(m["party_code"], "I"))
    rollcalls = [r for r in _csv(ctx, f"{base}_rollcalls", actual)
                 if r["chamber"] == camara and (not desde_fecha or r["date"] >= desde_fecha)]
    if not rollcalls:
        return
    quiero = {r["rollnumber"] for r in rollcalls}
    votos = {}
    for v in _csv(ctx, f"{base}_votes", actual):
        if v["chamber"] == camara and v["rollnumber"] in quiero:
            s = SENTIDO.get(v["cast_code"])
            if s and v["icpsr"] in miembros:
                nombre, partido = miembros[v["icpsr"]]
                votos.setdefault(v["rollnumber"], []).append((f"usa:{v['icpsr']}", nombre, partido, s))
    asuntos, votaciones = {}, []
    for r in rollcalls:
        numero = r["bill_number"].strip()
        codigo, tipo_a, url_a = iniciativa(numero, congreso)
        desc = (r["vote_desc"] or "").strip()
        pregunta = (r["vote_question"] or "").strip()
        if numero:
            aid = f"usa:{congreso}:{numero.upper()}"
        else:
            aid = f"usa:{congreso}:{letra}{r['rollnumber']}"
            tipo_a = "nombramiento" if "speaker" in pregunta.lower() else "procedimiento"
        if desc.lower().startswith(("providing for consideration", "providing for the consideration", "waiving")):
            tipo_a = "procedimiento"
        tv = tipo_votacion(pregunta, tipo_a)
        titulo = desc or pregunta or codigo or aid
        previo = asuntos.get(aid)
        # El título del asunto es el de su votación final, si la hay.
        if not previo or (tv == "final" and desc):
            asuntos[aid] = Asunto(id=aid, titulo=titulo[:400], tipo=tipo_a, fecha=previo.fecha if previo else r["date"],
                                  codigo=codigo, url=url_a, extra={"congreso": congreso})
        si, no = int(r["yea_count"] or 0), int(r["nay_count"] or 0)
        detalle = (r.get("dtl_desc") or "").strip()
        votaciones.append(Votacion(
            id=f"usa-{letra.lower()}:{congreso}:{r['rollnumber']}", fecha=r["date"], asunto_id=aid, camara=codigo_camara,
            numero=int(r["rollnumber"]), texto=(pregunta + (f" — {detalle}" if detalle else ""))[:600] or None, tipo=tv,
            a_favor=si, en_contra=no, mayoria=r["majority_requirement"] or None, resultado=resultado(r["vote_result"], si, no),
            url=f"https://voteview.com/rollcall/R{letra}{congreso:03d}{int(r['rollnumber']):04d}",
            votos=votos.get(r["rollnumber"], [])))
    for i in range(0, len(votaciones), 200):
        lote = votaciones[i:i + 200]
        ctx.guardar([asuntos[a] for a in dict.fromkeys(v.asunto_id for v in lote)], lote)


def recoger(ctx):
    actual = congreso_de(date.today().year)
    cerrados = set(ctx.marca("cerrados", []))
    for congreso in range(congreso_de(ctx.desde), actual + 1):
        es_actual = congreso == actual
        if not es_actual and congreso in cerrados and not ctx.completo:
            continue
        desde_fecha = None
        if es_actual and not ctx.completo:
            ultima = ctx.con.execute("SELECT MAX(fecha) FROM votacion WHERE fuente='usa' AND id LIKE ?",
                                     (f"usa-_:{congreso}:%",)).fetchone()[0]
            if ultima:  # se repasan dos semanas por si Voteview corrige algo
                desde_fecha = date.fromordinal(date.fromisoformat(ultima).toordinal() - 14).isoformat()
        for camara in ("House", "Senate"):
            ctx.log(f"   {congreso}.º Congreso, {'Cámara' if camara == 'House' else 'Senado'}"
                    + (f" desde {desde_fecha}" if desde_fecha else ""))
            cargar_congreso(ctx, congreso, camara, es_actual, desde_fecha)
        if not es_actual:
            cerrados.add(congreso)
            ctx.poner_marca("cerrados", sorted(cerrados))
