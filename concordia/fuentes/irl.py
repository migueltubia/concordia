"""Irlanda: divisiones del Oireachtas, Dáil Éireann y Seanad Éireann (API oficial, https://api.oireachtas.ie).

La API de datos abiertos del Oireachtas (/v1/votes) da cada división de las dos cámaras desde mucho antes
de 2019 con la lista de quién votó Tá (sí), Níl (no) y, en el Dáil, Staon (abstención), el debate en el
que se votó («Finance Bill 2026: Committee and Remaining Stages», «Neutrality: Motion [Private Members]»),
la pregunta («Question put: "That the Bill be now read a Second Time."», «Amendment put») y el resultado.

- El partido no viene en la división: sale de /v1/members (cada diputado o senador con sus partidos y
  fechas en cada legislatura) y se asigna por la fecha de la votación. Los miembros de la cámara en esa
  fecha que no aparecen en ninguna lista se guardan como «no vota» (el Ceann Comhairle, las ausencias y
  los emparejamientos).
- Las divisiones de un proyecto de ley se agrupan en un asunto por su número («Bill 45 of 2024»): la
  sección del debate de cada división se busca en la lista de debates de cada proyecto (/v1/legislation)
  y, si no está, por el título corto. Las mociones y lo demás se agrupan por debate y fecha.
- Numeración: en el Dáil «vote_N» corre por año; en el Seanad, por día. El id lleva cámara, fecha y número.
- Solo hay división cuando se pide: lo que se aprueba a viva voz no aparece. Los títulos están en inglés
  (algún debate, en irlandés). La pregunta casi nunca dice el número de la enmienda.

Se recoge desde 2019 (32.º Dáil y 25.º Seanad). Los años cerrados se guardan en data/raw/irl/.
"""

import json
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from .modelo import Asunto, Fuente, Votacion

FUENTE = Fuente(
    codigo="irl", pais="IRL", nombre="Oireachtas de Irlanda (Dáil y Seanad)", corto="Irlanda", tipo="parlamento",
    detalle="nominal", web="https://www.oireachtas.ie", desde=2019, idioma="en",
    licencia="Oireachtas (Open Data) PSI Licence (incorpora CC BY 4.0)",
    camaras={"irl-d": ("Dáil Éireann", "Dáil", 174), "irl-s": ("Seanad Éireann", "Seanad", 60)},
    partidos={
        "Fianna_Fáil": ("Fianna Fáil", "FF", "#66bb66"),
        "Fine_Gael": ("Fine Gael", "FG", "#6699ff"),
        "Sinn_Féin": ("Sinn Féin", "SF", "#326760"),
        "Labour_Party": ("Partido Laborista", "Lab.", "#cc0000"),
        "Social_Democrats": ("Socialdemócratas", "SD", "#752f8b"),
        "Green_Party": ("Partido Verde", "Verdes", "#8cc63e"),
        "People_Before_Profit_Solidarity": ("People Before Profit–Solidarity", "PBP–S", "#8e2420"),
        "Anti-Austerity_Alliance_People_Before_Profit": ("Anti-Austerity Alliance–People Before Profit", "AAA–PBP", "#8e2420"),
        "Aontú": ("Aontú", "Aontú", "#44532a"),
        "Independent_Ireland": ("Independent Ireland", "II", "#127a7a"),
        "Independents_4_Change": ("Independents 4 Change", "I4C", "#c2527a"),
        "100%_RDR": ("100% Redress", "100% RDR", "#d9a21b"),
        "Independent": ("Independientes", "Ind.", "#898781"),
    },
    notas="Solo divisiones (votaciones con recuento nominal) del Dáil y del Seanad: lo aprobado a viva voz no queda "
          "registrado. El Dáil tuvo 160 escaños hasta 2024 y 174 desde la 34.ª legislatura.",
)

API = "https://api.oireachtas.ie/v1"
WEB = "https://www.oireachtas.ie/en"
CAMARAS = {"dail": ("irl-d", "d", "Dáil"), "seanad": ("irl-s", "s", "Seanad")}
LISTAS = (("taVotes", "si"), ("nilVotes", "no"), ("staonVotes", "abstencion"))
POR_PAGINA = 1000
LOTE = 200


def _slug(t):
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")[:80]


def _limpio(t):
    return re.sub(r"\s+", " ", t or "").strip()


def _norm(t):
    """Título comparable: minúsculas, sin «[Seanad]», «[Certified Money Bill]»..., comillas y guiones unificados."""
    t = (t or "").replace("’", "'").replace("‘", "'").replace("–", "-")
    return _limpio(re.sub(r"\s*\[[^\]]*\]", "", t)).lower()


# ------------------------------------------------------------------ descargas

def _todas(ctx, url, nombre=None, caduca_horas=None):
    """Todas las páginas de una consulta (1000 por página). Con nombre se guardan en data/raw/irl/."""
    resultados, skip = [], 0
    while True:
        pagina_url = f"{url}&limit={POR_PAGINA}&skip={skip}"
        if nombre:
            ruta = ctx.cache(pagina_url, f"{nombre}_{skip}.json", caduca_horas=caduca_horas)
            pagina = json.loads(ruta.read_text(encoding="utf-8"))
        else:
            pagina = ctx.json(pagina_url)
        r = pagina.get("results") or []
        resultados += r
        skip += len(r)
        if len(r) < POR_PAGINA:
            return resultados


def _divisiones(ctx, camara, desde, hasta, cerrado):
    url = f"{API}/votes?chamber_type=house&chamber={camara}&date_start={desde}&date_end={hasta}"
    return [r["division"] for r in _todas(ctx, url, f"votos_{camara}_{desde[:4]}" if cerrado else None)]


def _miembros(ctx, camara, numero, actual):
    """[(código, nombre, inicio, fin, [(partido, nombre del partido, inicio, fin)])] de una legislatura."""
    filas = _todas(ctx, f"{API}/members?chamber={camara}&house_no={numero}", f"miembros_{camara}_{numero}",
                   caduca_horas=12 if actual else 24 * 30)
    salida = []
    for r in filas:
        m = r["member"]
        for s in (x["membership"] for x in m.get("memberships") or []):
            casa = s.get("house") or {}
            if casa.get("houseCode") != camara or str(casa.get("houseNo")) != str(numero):
                continue
            partidos = []
            for p in (x["party"] for x in s.get("parties") or []):
                rango = p.get("dateRange") or {}
                partidos.append((p["partyCode"], p.get("showAs"), rango.get("start") or "", rango.get("end")))
            rango = s.get("dateRange") or {}
            salida.append((m["memberCode"], _limpio(m.get("fullName") or m.get("showAs")), rango.get("start") or "",
                           rango.get("end"), partidos))
    return salida


def _partido_en(partidos, fecha):
    for codigo, nombre, inicio, fin in partidos:
        if inicio <= fecha and (not fin or fecha <= fin):
            return codigo, nombre
    # Huecos en los datos: el último partido anterior a la fecha, o el primero que tuvo.
    anteriores = [p for p in partidos if p[2] <= fecha]
    p = max(anteriores, key=lambda p: p[2]) if anteriores else min(partidos, key=lambda p: p[2], default=None)
    return (p[0], p[1]) if p else ("?", None)


class Proyectos:
    """Índice de los proyectos de ley por sección de debate y por título corto."""

    def __init__(self, bills):
        self.por_seccion, self.por_titulo, self.por_debate = {}, {}, {}
        for b in bills:
            for d in b.get("debates") or []:
                self.por_seccion.setdefault((d.get("uri"), d.get("debateSectionId")), []).append(b)
                # Título con el que se debatió (a veces el provisional: «Gas (Amendment) Bill 2023»).
                self.por_debate.setdefault(_norm(partes_debate(d.get("showAs"))[0]), b)
            for t in (b.get("shortTitleEn"), b.get("shortTitleGa")):
                if t:
                    self.por_titulo.setdefault(_norm(t), b)

    def buscar(self, debate, nombre):
        candidatos = self.por_seccion.get((debate.get("uri"), debate.get("debateSection"))) or []
        n = _norm(nombre)
        for b in candidatos:
            if _norm(b.get("shortTitleEn")) == n:
                return b
        return self.por_titulo.get(n) or (candidatos[0] if candidatos else None) or self.por_debate.get(n)


# ------------------------------------------------------------------ clasificación

# Lo que va tras los dos puntos del debate de una moción: «Neutrality: Motion», «EU Regulations: Motions»...
FASES_MOCION = r"(?:motions?|tairiscint|referral to (?:select|joint) committee)"
PROCEDIMIENTO = (r"order of business|business of (?:the )?(?:d[áa]il|seanad)|\bsittings?\b|adjournment of|speaking arrangements"
                 r"|standing orders|committee of selection|business committee|d[áa]il reform")
TRATADO = r"\btreat(?:y|ies)\b|\bagreements?\b|\bconvention\b|\bprotocol\b|ratification|status of forces"


def partes_debate(titulo):
    """«Finance Bill 2026 [Seanad]: Report and Final Stages (Resumed) [Private Members]» ->
    (nombre, fase, es_proyecto, de miembros privados). Quita los rótulos en irlandés del procedimiento
    («An tOrd Gnó - Order of Business» -> «Order of Business»)."""
    t = _limpio(titulo)
    privado = bool(re.search(r"\[(?:Private Members|Comhaltaí Príobháideacha)\]", t, re.I))
    t = re.sub(r"\s*\[(?:Private Members|Comhaltaí Príobháideacha)\]", "", t, flags=re.I)
    t = _limpio(re.sub(r"\s*[(\[](?:Resumed|Atógáil)[)\]]", "", t, flags=re.I))
    t = re.sub(r"^(?:An tOrd Gnó|Gnó na Dála|Gnó an tSeanaid|Taoiseach a Ainmniú)\s*-\s*", "", t)
    m = re.match(r"^(.*?\bBill(?:e)?\b.*?)\s*:\s*(.+)$", t)
    if m:
        return m.group(1).strip(), m.group(2).strip(), True, privado
    if re.search(r"\bBill\b", t):
        return t, "", True, privado
    m = re.match(rf"^(.+?)\s*:\s*({FASES_MOCION})$", t, re.I)
    if m:
        return m.group(1).strip(), m.group(2).strip(), False, privado
    return t, "", False, privado


def tipo_asunto(nombre, privado):
    n = nombre.lower()
    if re.search(PROCEDIMIENTO, n):
        return "procedimiento"
    if "confidence" in n:
        return "mocion"
    if re.match(r"(?:the )?(?:nomination|appointment|election) of", n) or re.search(r"ceann comhairle|cathaoirleach", n):
        return "nombramiento"
    if not privado and re.search(TRATADO, n):
        return "tratado"
    if "financial resolution" in n:
        return "resolucion"
    # Legislación delegada (reglamentos, órdenes) y prórrogas de leyes que se aprueban por moción.
    if re.search(r"\b(?:regulations|order|scheme|rules)\s+\d{4}\b|\bs\.i\. no\b|\bact,? \d{4}\b", n):
        return "ley"
    return "mocion"


def tipo_proyecto(titulo):
    return "tratado" if re.search(r"\btreat(?:y|ies)\b|\bagreement on\b|bretton woods|\bratif", titulo, re.I) else "ley"


FASES_PROCEDIMIENTO = ("instruction to committee", "order for", "referral to", "restoration to order paper",
                       "waiver of pre-legislative", "first stage", "an chéad chéim")
FASES_FINALES = ("second stage", "dara céim", "remaining stages", "final stage", "fifth stage", "subsequent stages",
                 "chéim dheiridh", "céimeanna")


def tipo_votacion(accion, pregunta, fase, tipo_a, es_proyecto):
    """accion: «Question put», «Amendment put», «Seanad amendment put», «Recommendation put»...;
    pregunta: el texto de la cuestión, cuando lo hay («That the Bill do now pass»)."""
    a, q, f = accion.lower(), pregunta.lower(), fase.lower()
    if tipo_a == "procedimiento":
        return "procedimiento"
    if any(k in f for k in FASES_PROCEDIMIENTO) or (es_proyecto and re.search(r"\bmotion\b|tairiscint", f)):
        return "procedimiento"
    if not a.startswith("question"):  # enmiendas, enmiendas del Seanad, recomendaciones del Seanad
        return "enmienda"
    # «That the motion, as amended, be agreed to» en la segunda lectura es la votación de la lectura
    # tras la enmienda del Gobierno que la aplaza («read a second time this day twelve months»).
    if re.search(r"do now pass|hereby passed|read a second time|\bmotion\b.*\bagreed\b", q):
        return "final"
    if re.search(r"stand part|be the schedule|\bthe title\b", q):
        return "parcial"
    if re.search(r"amendments? no\b|seanad amendment|amendment be made", q):
        return "enmienda"
    if re.search(r"stage be taken|leave be given|recommit|final consideration|returned to|arrangements for|be taken now", q):
        return "procedimiento"
    if tipo_a == "nombramiento":
        return "nombramiento"
    if not es_proyecto:
        return "final"
    if q:
        return "otra"
    if any(k in f for k in FASES_FINALES):
        return "final"
    if "committee stage" in f or "céim an choiste" in f:
        return "parcial"
    if "from the seanad" in f or "ón seanad" in f:
        return "enmienda"
    return "otra"


def _pregunta(subject):
    """«Question put: "That the Bill be now read a Second Time."» -> («Question put», «That the Bill...»)."""
    s = _limpio(subject)
    m = re.match(r"^(.*?\bput)\b[\s:]*(.*)$", s, re.I)
    if not m:
        return s, ""
    return m.group(1), m.group(2).strip(' "“”:.')


def _nombre_lista(show_as):
    """«Boyd Barrett, Richard.» -> «Richard Boyd Barrett»."""
    t = _limpio(show_as).rstrip(".")
    apellido, _, nombre = t.partition(", ")
    return f"{nombre} {apellido}".strip() if nombre else t


def _seccion(debate):
    m = re.search(r"(\d+)$", debate.get("debateSection") or "")
    f = re.search(r"/debateRecord/(\w+)/(\d{4}-\d{2}-\d{2})/", debate.get("uri") or "")
    return f"{WEB}/debates/debate/{f.group(1)}/{f.group(2)}/{m.group(1)}/" if m and f else None


# ------------------------------------------------------------------ recogida

def _asunto(d, camara, proyectos):
    """Asunto de una división y lo que hace falta para clasificarla."""
    _, letra, nombre_camara = CAMARAS[camara]
    fecha = d["date"]
    debate = d.get("debate") or {}
    nombre, fase, es_proyecto, privado = partes_debate(debate.get("showAs"))
    b = proyectos.buscar(debate, nombre) if es_proyecto else None
    if b:
        anio, num = b["billYear"], b["billNo"]
        titulo = _limpio(b.get("shortTitleEn")) or nombre
        sponsor = next((s["sponsor"] for s in b.get("sponsors") or [] if s["sponsor"].get("isPrimary")), None)
        autor = ((sponsor.get("as") or {}).get("showAs") or (sponsor.get("by") or {}).get("showAs")) if sponsor else None
        act = b.get("act") or {}
        extra = {k: v for k, v in (("origen", b.get("source")), ("estado", b.get("status")),
                                   ("ley", f"Act {act['actNo']} of {act['actYear']}" if act.get("actNo") else None)) if v}
        tipo_a = tipo_proyecto(titulo)
        return Asunto(id=f"irl:bill:{anio}:{num}", titulo=titulo[:400], tipo=tipo_a, fecha=fecha,
                      codigo=f"Bill {num} of {anio}", autor=autor, url=f"{WEB}/bills/bill/{anio}/{num}/",
                      extra=extra or None), fase, tipo_a, True
    if es_proyecto:  # proyecto que no está en /legislation: se agrupa por su título
        titulo = _limpio(re.sub(r"\s*\[[^\]]*\]", "", nombre))
        tipo_a = tipo_proyecto(titulo)
        return Asunto(id=f"irl:bill:{_slug(titulo)}", titulo=titulo[:400], tipo=tipo_a, fecha=fecha,
                      url=_seccion(debate)), fase, tipo_a, True
    tipo_a = tipo_asunto(nombre, privado)
    titulo = f"{nombre} ({nombre_camara}, {fecha})" if tipo_a in ("procedimiento", "nombramiento") else nombre
    return Asunto(id=f"irl:{letra}:{fecha}:{_slug(nombre)}", titulo=titulo[:400], tipo=tipo_a, fecha=fecha,
                  url=_seccion(debate), extra={"miembros_privados": True} if privado else None), fase, tipo_a, False


def _votacion(ctx, d, camara, asunto, fase, tipo_a, es_proyecto, miembros):
    cod_camara, letra, _ = CAMARAS[camara]
    fecha, casa = d["date"], str((d.get("house") or {}).get("houseNo") or "")
    numero = int(re.sub(r"\D", "", d.get("voteId") or "") or 0)
    accion, pregunta = _pregunta((d.get("subject") or {}).get("showAs"))
    texto = " — ".join(x for x in (fase, f"{accion}: {pregunta}" if pregunta else accion) if x)
    de_la_casa = miembros.get((camara, casa), [])
    activos = {m[0]: m for m in de_la_casa if m[2] <= fecha and (not m[3] or fecha <= m[3])}
    de_la_casa = {m[0]: m for m in de_la_casa}
    votos, vistos, totales = [], set(), {}
    for lista, sentido in LISTAS:
        t = (d.get("tallies") or {}).get(lista) or {}
        totales[sentido] = t.get("tally") or 0
        for x in t.get("members") or []:
            codigo = x["member"]["memberCode"]
            if codigo in vistos:
                continue
            vistos.add(codigo)
            m = activos.get(codigo) or de_la_casa.get(codigo)
            partido, nombre_p = _partido_en(m[4], fecha) if m else ("?", None)
            if partido not in FUENTE.partidos:
                ctx.partido(partido, nombre_p)
            votos.append((f"irl:{codigo}", m[1] if m else _nombre_lista(x["member"].get("showAs")), partido, sentido))
    ausentes = [m for c, m in activos.items() if c not in vistos]
    for codigo, nombre, _, _, partidos in ausentes:
        partido, nombre_p = _partido_en(partidos, fecha)
        if partido not in FUENTE.partidos:
            ctx.partido(partido, nombre_p)
        votos.append((f"irl:{codigo}", nombre, partido, "no_vota"))
    si, no = totales["si"], totales["no"]
    resultado = {"Carried": "aprobada", "Lost": "rechazada"}.get(d.get("outcome"))
    # Algún resultado contradice el recuento (errores de la fuente): manda el recuento.
    if resultado is None or (resultado == "aprobada" and si < no) or (resultado == "rechazada" and si > no):
        resultado = "aprobada" if si > no else "rechazada"
    return Votacion(
        id=f"irl:{letra}:{fecha}:{numero}", fecha=fecha, asunto_id=asunto.id, camara=cod_camara, numero=numero,
        texto=texto[:600] or None, tipo=tipo_votacion(accion, pregunta, fase, tipo_a, es_proyecto),
        a_favor=si, en_contra=no, abstenciones=totales["abstencion"], no_votan=len(ausentes) if activos else None,
        resultado=resultado, url=f"{WEB}/debates/vote/{camara}/{casa}/{fecha}/{numero}/", votos=votos)


def recoger(ctx):
    hoy = date.today()
    inicio = date(ctx.desde, 1, 1)
    ultima = ctx.ultima_fecha()
    if ultima and not ctx.completo:  # se repasan tres semanas por si se corrige o publica algo tarde
        inicio = max(inicio, date.fromisoformat(ultima) - timedelta(days=21))
    tareas = []
    for anio in range(inicio.year, hoy.year + 1):
        desde = max(inicio, date(anio, 1, 1))
        cerrado = desde == date(anio, 1, 1) and anio < (hoy - timedelta(days=60)).year
        for camara in CAMARAS:
            tareas.append((camara, desde.isoformat(), f"{anio}-12-31", cerrado))
    with ThreadPoolExecutor(4) as ex:
        listas = list(ex.map(lambda t: _divisiones(ctx, *t), tareas))
    divisiones = sorted(((t[0], d) for t, lista in zip(tareas, listas) for d in lista if d["date"] >= inicio.isoformat()),
                        key=lambda x: (x[1]["date"], x[0], int(re.sub(r"\D", "", x[1].get("voteId") or "") or 0)))
    ctx.log(f"   {len(divisiones)} divisiones desde {inicio}")
    if not divisiones:
        return

    casas = {(c, str((d.get("house") or {}).get("houseNo") or "")) for c, d in divisiones} - {(c, "") for c in CAMARAS}
    actual = {c: max(int(n) for cc, n in casas if cc == c) for c, _ in casas}
    with ThreadPoolExecutor(4) as ex:
        miembros = dict(zip(casas, ex.map(lambda k: _miembros(ctx, k[0], k[1], int(k[1]) == actual[k[0]]), casas)))
    # Proyectos con actividad desde un año antes (el título corto sirve si la sección del debate aún no está).
    proyectos = Proyectos([r["bill"] for r in _todas(ctx, f"{API}/legislation?date_start={inicio - timedelta(days=365)}")])
    ctx.log(f"   {sum(len(m) for m in miembros.values())} miembros en {len(casas)} legislaturas; "
            f"{len({id(b) for v in proyectos.por_seccion.values() for b in v})} proyectos de ley")

    for anio in sorted({d["date"][:4] for _, d in divisiones}):
        del_anio = [(c, d) for c, d in divisiones if d["date"][:4] == anio]
        for i in range(0, len(del_anio), LOTE):
            asuntos, votaciones = {}, []
            for camara, d in del_anio[i:i + LOTE]:
                asunto, fase, tipo_a, es_proyecto = _asunto(d, camara, proyectos)
                asuntos.setdefault(asunto.id, asunto)
                votaciones.append(_votacion(ctx, d, camara, asunto, fase, tipo_a, es_proyecto, miembros))
            ctx.guardar(list(asuntos.values()), votaciones)
        ctx.log(f"   {anio}: {sum(1 for c, _ in del_anio if c == 'dail')} divisiones del Dáil y "
                f"{sum(1 for c, _ in del_anio if c == 'seanad')} del Seanad")
