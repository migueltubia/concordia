"""Suiza: votaciones nominales del Consejo Nacional (servicio OData del Parlamento, ws.parlament.ch).

El servicio de datos abiertos de la Asamblea Federal (https://ws.parlament.ch/odata.svc/) publica cada
votación electrónica del Consejo Nacional (entidad `Vote`) con el voto de cada diputado y su grupo
parlamentario (`Voting`), desde 2007. Cada registro sale una vez por idioma (DE, FR, IT…): se usa solo
el francés, así que los títulos de los asuntos están en francés; lo que se vota en concreto («Subject»,
«MeaningYes/MeaningNo») lo escribe la secretaría en su lengua, casi siempre en alemán. El Consejo de
los Estados no publica su voto nominal en este servicio (solo el Consejo Nacional).

El asunto es el objeto parlamentario (Geschäft/objet: «24.017», mensaje del Consejo Federal, moción,
postulado, iniciativa parlamentaria o cantonal, petición, declaración…), con todas sus votaciones de
todas las sesiones, y su ficha en Curia Vista. Un mensaje puede traer varios proyectos (ley y decretos):
van en el mismo asunto y el texto de cada votación dice a qué proyecto se refiere. Las mociones de
orden y los controles de presencia (objeto «00.000») se agrupan por sesión.

Particularidad importante: en el Consejo Nacional «sí» es a menudo la propuesta de la mayoría de la
comisión, aunque esa propuesta sea rechazar («Antrag der Mehrheit (Ablehnung der Motion)», «keine
Folge geben», «Nichteintreten»). En esos casos se invierten sí y no (votos y totales) para que «sí»
sea siempre a favor del objeto, y el texto de la votación lo avisa. La fuente no da el resultado: se
calcula (mayoría simple; 101 votos en las del freno al gasto y la cláusula de urgencia).

Se recoge por sesiones (cuatro ordinarias al año y alguna especial o extraordinaria); las cerradas no
se vuelven a descargar y la abierta se repasa desde la última fecha con margen.
"""

import re
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

from .modelo import Asunto, Fuente, Votacion

FUENTE = Fuente(
    codigo="che", pais="CHE", nombre="Asamblea Federal de Suiza (Consejo Nacional)", corto="Suiza", tipo="parlamento",
    detalle="nominal", web="https://www.parlament.ch", desde=2019, idioma="otro",
    licencia="Open Government Data de los Servicios del Parlamento (opendata.swiss «terms_by»: uso libre citando la fuente)",
    camaras={"che-n": ("Consejo Nacional", "Nacional", 200)},
    partidos={
        "V": ("Unión Democrática de Centro (UDC/SVP)", "UDC", "#005e29"),
        "S": ("Partido Socialista (PS/SP)", "PS", "#d0274e"),
        "RL": ("Partido Liberal-Radical (PLR/FDP)", "PLR", "#0094eb"),
        "M-E": ("El Centro y Partido Evangélico (Le Centre/Mitte, PEV)", "Centro", "#ea7815"),
        "M-CED": ("Grupo del Centro: PDC, PEV y PBD", "Centro", "#ea7815"),
        "CE": ("Partido Demócrata Cristiano y Partido Evangélico (PDC/CVP, PEV)", "PDC", "#ea7815"),
        "C": ("Partido Demócrata Cristiano y Partido Evangélico (PDC/CVP, PEV)", "PDC", "#ea7815"),
        "BD": ("Partido Burgués Democrático (PBD/BDP)", "PBD", "#e8c300"),
        "G": ("Los Verdes (Verts/Grüne)", "Verdes", "#89ba2c"),
        "GL": ("Partido Verde Liberal (PVL/GLP)", "PVL", "#b5c800"),
        "-": ("No inscritos", "No inscr.", "#9a9a8e"),
        "FRAKTIONSLOS": ("No inscritos", "No inscr.", "#9a9a8e"),
    },
    notas=("Voto de cada diputado del Consejo Nacional en todas las votaciones electrónicas; el Consejo de los "
           "Estados no publica su voto nominal en el servicio de datos. «Sí» es siempre a favor del objeto."),
)

API = "https://ws.parlament.ch/odata.svc"
LENGUA = "FR"
CAMPOS_VOTE = ("ID,RegistrationNumber,BusinessNumber,BusinessShortNumber,BusinessTitle,BillNumber,BillTitle,"
               "IdLegislativePeriod,IdSession,SessionName,Subject,MeaningYes,MeaningNo,VoteEnd,VoteEndWithTimezone")
CAMPOS_VOTING = "IdVote,PersonNumber,FirstName,LastName,Canton,ParlGroupCode,Decision"
CAMPOS_BUSINESS = "ID,BusinessShortNumber,BusinessType,BusinessTypeAbbreviation,Title,SubmittedBy,SubmissionDate"
# Decision: 1 sí, 2 no, 3 abstención, 5 no participa, 6 excusado, 7 preside (no vota).
SENTIDO = {1: "si", 2: "no", 3: "abstencion"}
MAYORIA_ABSOLUTA = 101  # mayoría de los miembros: freno al gasto y cláusula de urgencia
# Objetos ficticios «00.000»: se agrupan por sesión.
FICTICIOS = {1: "Mociones de orden", 2: "Controles de presencia"}
# BusinessType -> tipo de asunto (1 mensaje del Consejo Federal y 2 objeto del Parlamento se miran aparte).
TIPO_OBJETO = {3: "ley", 4: "ley", 5: "mocion", 6: "mocion", 7: "mocion", 10: "otro"}


def _odata(ctx, entidad, filtro, campos, orden=None):
    """Todas las filas de una consulta OData (sigue «__next» si el servidor pagina)."""
    url = (f"{API}/{entidad}?$format=json&$select={campos}&$filter=" + urllib.parse.quote(filtro, safe="'(),:")
           + (f"&$orderby={orden}" if orden else ""))
    filas = []
    while url:
        d = ctx.json(url)["d"]
        if isinstance(d, list):
            return filas + d
        filas += d.get("results", [])
        url = d.get("__next")
    return filas


def _fecha(valor):
    """«/Date(1741013301493+0060)/» -> «2025-03-03», en hora local (el desfase va en minutos)."""
    m = re.match(r"/Date\((-?\d+)([+-]\d+)?\)/", valor or "")
    if not m:
        return None
    t = datetime.fromtimestamp(int(m.group(1)) / 1000, timezone.utc)
    if m.group(2):
        t += timedelta(minutes=int(m.group(2)))
    return t.date().isoformat()


def _limpio(t):
    return re.sub(r"\s+", " ", (t or "").replace("’", "'")).strip()


ESTACION = {"printemps": "primavera", "été": "verano", "automne": "otoño", "hiver": "invierno"}


def _sesion_es(nombre):
    """«Session d'hiver 2023» -> «sesión de invierno de 2023», «Session spéciale 4. 2024» -> «sesión especial de 2024»."""
    n = _limpio(nombre)
    m = re.match(r"Session (?:de |d')(printemps|été|automne|hiver) (\d{4})$", n)
    if m:
        return f"sesión de {ESTACION[m.group(1)]} de {m.group(2)}"
    m = re.match(r"Session (spéciale|extraordinaire)\b.*?(\d{4})$", n)
    if m:
        return f"sesión {'especial' if m.group(1) == 'spéciale' else 'extraordinaria'} de {m.group(2)}"
    return n


# ------------------------------------------------------------------ tipo de asunto

TRATADO = (r"(accords?|conventions?|traités?|protocoles?|arrangements?|échanges? de notes|avenants?|amendements?|addendum"
           r"|statut de rome|acte de genève)")


def es_tratado(titulo, proyectos):
    """Mensaje que aprueba un tratado: por el título del objeto o porque todos sus proyectos son decretos de aprobación."""
    t = _limpio(titulo).lower()
    if re.search(r"convention collective|conventions?-programmes?", t):
        return False
    if re.search(TRATADO, t) and re.search(r"approbation|ratification|\bavec\b|\bentre\b|adhésion", t):
        return True
    aprobaciones = [p for p in proyectos if re.match(
        r"arrêté fédéral\s+(portant|relatif à|concernant)\s+(l'|la |le )?(approbation|ratification)", _limpio(p).lower())]
    return bool(proyectos) and len(aprobaciones) == len(proyectos) and all(re.search(TRATADO, p.lower()) for p in aprobaciones)


def tipo_asunto(tipo_objeto, titulo, proyectos):
    t = _limpio(titulo).lower()
    if tipo_objeto == 1:  # mensaje del Consejo Federal: leyes, decretos, presupuestos, tratados, informes
        if es_tratado(titulo, proyectos):
            return "tratado"
        if re.search(r"\brapport\b", t) and not re.search(r"\bloi\b", t):
            return "otro"
        return "ley"
    if tipo_objeto == 2:  # objeto del Parlamento: sobre todo declaraciones del Consejo Nacional y elecciones de jueces
        if re.search(r"élection|election|renouvellement|présidence|\bjuges?\b", t):
            return "nombramiento"
        return "resolucion"
    return TIPO_OBJETO.get(tipo_objeto, "otro")


# ------------------------------------------------------------------ tipo de votación y sentido

# Con las erratas que aparecen en la fuente («Ablehung», «keine Foge geben», «ne pas donner sutite», «rejter»…).
NEGATIVO = re.compile(r"\bab\w?le\w{0,3}ung|keine\s+f\w{1,3}ge\b|nicht\s*f\w{1,3}ge\b|nicht[- ]?eintreten|keine zustimmung"
                      r"|\breje?t|ne pas (donner|entrer)|non[- ]entrée|respinge|non dare|non entra")
POSITIVO = re.compile(r"\ban{1,2}[ah]{1,3}me\b|f\w{1,3}ge geben|eintreten|zustimmung|adopter|accepter|approuver|donner s|"
                      r"entrer en ma|entrée en ma|accettare|accogliere|approvare|dare seguito|entrare in materia")


def polaridad(texto):
    """+1 si la opción acepta el objeto (o la propuesta), -1 si la rechaza, 0 si no se sabe.

    Manda la primera palabra clave: «keine Folge geben» y «Nichteintreten» rechazan; «Annahme der Vorlage
    (Empfehlung auf Ablehnung der Volksinitiative)» acepta (el proyecto).
    """
    t = _limpio(texto).lower()
    neg, pos = NEGATIVO.search(t), POSITIVO.search(t)
    if neg and (not pos or neg.start() <= pos.start()):
        return -1
    return 1 if pos else 0


FINAL = ("gesamtabstimmung", "schlussabstimmung", "vote sur l'ensemble", "vote final", "votazione sul complesso",
         "votazione finale")
SOBRE_OBJETO = ("abstimmung über die motion", "abstimmung über motion", "abstimmung über das postulat",
                "abstimmung über postulat", "abstimmung über kt. iv", "abstimmung über die erklärung", "vote sur la motion",
                "vote sur le postulat")
ORDEN = ("ordnungsantrag", "motion d'ordre", "mozione d'ordine", "proposition d'ordre", "rückkommen", "wiederhol",
         "répéter", "ripetere")
ENTRADA = ("eintreten", "entrer en matière", "entrée en matière", "entrare in materia")
PROCEDIMIENTO = ORDEN + ("rückweisung", "renvoi", "rinvio", "sistierung", "suspension", "sospensione", "fristverlängerung",
                         "frist verlängern", "prolongation du délai", "proroga", "abschreibung", "abschreiben", "classer",
                         "classement", "stralci", "traktandierung", "ordre du jour", "ordine del giorno")
CONCILIACION = ("einigungskonferenz", "conférence de conciliation", "conferenza di conciliazione")
CUALIFICADA = ("ausgabenbremse", "frein aux dépenses", "frain aux dépenses", "freno alle spese", "dringlichkeit",
               "clause d'urgence", "clausola d'urgenza", "zahlungsbedarf", "financement extraordinaire",
               "besoins financiers extraordinaires")
ENMIENDA = ("minderheit", "minorité", "minoranza", "antrag", "proposition", "proposta", "einzelantrag")


def tipo_votacion(ficticio, tipo_a, sujeto, si, no):
    s, m_si, m = sujeto.lower(), si.lower(), f"{si} {no}".lower()
    if ficticio or tipo_a == "procedimiento":
        return "procedimiento"
    if any(k in s for k in ORDEN):
        return "procedimiento"
    # «Gesamtabstimmung», «Schlussabstimmung», «AF Ia … - vote sur l'ensemble», «Abstimmung über die Motion»
    if s.startswith(FINAL + SOBRE_OBJETO) or s.endswith(FINAL):
        return "final"
    if any(k in s for k in PROCEDIMIENTO):
        return "procedimiento"
    s = re.sub(r"^(abstimmung über|vote sur)\s+", "", s)
    # Un sujeto que solo remite a otros objetos («24.453», «gilt auch für 23.410…») es como si no lo hubiera.
    s = re.sub(r"^\(?((la )?votazione |le vote |die abstimmung )?(gilt auch für|vaut (aussi|également) pour|vale anche per)\b.*$"
               r"|^[\d.,;\s]+$", "", s)
    if re.search(r"abschreib|fristverlängerung|frist verlängern|\bclasser|classement|stralci\w* dal ruolo|nessun stralcio", m_si):
        return "procedimiento"  # archivar o prorrogar una iniciativa o una moción
    if s.startswith(ENTRADA):
        return "otra"
    if any(k in s for k in CONCILIACION):
        return "otra"
    if any(k in s for k in CUALIFICADA):
        return "parcial"
    if not s:  # voto sobre el objeto mismo (moción, postulado, iniciativa, petición, declaración…)
        if any(k in m_si for k in PROCEDIMIENTO) or (any(k in m for k in PROCEDIMIENTO) and polaridad(si) == 0):
            return "procedimiento"
        return "nombramiento" if tipo_a == "nombramiento" else "final"
    if tipo_a == "mocion" and re.match(r"(punkt|point|punto|buchstabe|lettre|ziffer|chiffre)\b", s):
        return "otra"  # mociones votadas por puntos: si no hay votación de conjunto decide el último punto
    if tipo_a == "nombramiento":
        return "nombramiento"
    # Decisión sobre el objeto con un sujeto informal: dar curso a una iniciativa, aceptar la moción…
    if re.search(r"f\w{1,3}ge geben|donner suite|dare seguito|(der|la|die) motion\b|(des|le|das) postulat|la mozione|il postulato",
                 m_si):
        return "final"
    if any(k in m for k in ENMIENDA):
        return "enmienda"  # artículos, partidas del presupuesto…: mayoría contra minoría o propuestas individuales
    return "parcial"


ETIQUETA = [
    (("gesamtabstimmung", "vote sur l'ensemble", "votazione sul complesso"), "Votación de conjunto"),
    (("schlussabstimmung", "vote final", "votazione finale"), "Votación final"),
    (("eintreten", "abstimmung über eintreten", "entrer en matière", "entrée en matière", "entrare in materia"),
     "Entrada en materia"),
    (("rückweisungsantrag", "rückweisung", "proposition de renvoi", "proposta di rinvio", "renvoi au conseil fédéral"),
     "Propuesta de devolución"),
    (("abstimmung über die motion", "abstimmung über motion", "vote sur la motion"), "Votación sobre la moción"),
    (("abstimmung über das postulat", "vote sur le postulat"), "Votación sobre el postulado"),
    (("dringlichkeitsklausel", "abstimmung über die dringlichkeitsklausel", "vote sur la clause d'urgence"),
     "Cláusula de urgencia"),
    (("sistierung",), "Suspensión"),
]
SIN_SUJETO = {5: "Votación sobre la moción", 6: "Votación sobre el postulado", 7: "Votación sobre la recomendación",
              4: "Iniciativa parlamentaria", 3: "Iniciativa cantonal", 10: "Petición", 2: "Votación sobre el objeto",
              1: "Votación sobre el proyecto"}


def etiqueta(sujeto, tipo_objeto, ficticio, tipo_a):
    s = sujeto.lower()
    for claves, es in ETIQUETA:
        if s in claves:
            return es
    if sujeto:
        return sujeto
    if ficticio == 2:
        return "Control de presencia"
    if tipo_a == "resolucion":
        return "Votación sobre la declaración"
    return SIN_SUJETO.get(tipo_objeto, "Votación sobre el objeto")


# ------------------------------------------------------------------ descarga de una sesión

def _sesion(ctx, sesion, corte):
    """Votaciones, votos y objetos de una sesión (desde la fecha de corte)."""
    filtro = f"IdSession eq {sesion['ID']} and Language eq '{LENGUA}' and VoteEnd ge datetime'{corte}T00:00:00'"
    votes = _odata(ctx, "Vote", filtro, CAMPOS_VOTE)
    votos = {}
    if votes:
        for v in _odata(ctx, "Voting", filtro, CAMPOS_VOTING):
            votos.setdefault(v["IdVote"], []).append(
                (v["PersonNumber"], _limpio(f"{v.get('FirstName') or ''} {v.get('LastName') or ''}"), v.get("Canton"),
                 v.get("ParlGroupCode") or "-", v.get("Decision")))
    ids = sorted({v["BusinessNumber"] for v in votes if (v.get("BusinessNumber") or 0) > 1000})
    objetos = {}
    for i in range(0, len(ids), 40):
        filtro_b = f"Language eq '{LENGUA}' and (" + " or ".join(f"ID eq {n}" for n in ids[i:i + 40]) + ")"
        for b in _odata(ctx, "Business", filtro_b, CAMPOS_BUSINESS):
            objetos[b["ID"]] = b
    return sesion, votes, votos, objetos


def _procesar(ctx, sesion, votes, votos, objetos):
    desde = f"{ctx.desde}-01-01"
    votes = sorted((v for v in votes if (_fecha(v.get("VoteEndWithTimezone") or v["VoteEnd"]) or "") >= desde),
                   key=lambda v: (v["VoteEnd"], v["RegistrationNumber"] or 0))
    proyectos = {}
    for v in votes:
        if v.get("BillTitle"):
            proyectos.setdefault(v["BusinessNumber"], set()).add(_limpio(v["BillTitle"]))
    asuntos, votaciones = {}, []
    for v in votes:
        fecha = _fecha(v.get("VoteEndWithTimezone") or v["VoteEnd"])
        numero_obj = v.get("BusinessNumber") or 0
        ficticio = numero_obj <= 1000  # «00.000»: 1 mociones de orden, 2 controles de presencia
        b = objetos.get(numero_obj) or {}
        tipo_objeto = b.get("BusinessType")
        if ficticio:
            aid = f"che:{sesion['ID']}:{numero_obj}"
            nombre = FICTICIOS.get(numero_obj) or _limpio(v.get("BusinessTitle")) or "Procedimiento"
            titulo, tipo_a = f"{nombre}, {_sesion_es(sesion.get('SessionName'))}", "procedimiento"
            codigo = url_a = autor = abrev = None
            fecha_a = fecha
        else:
            corto = v.get("BusinessShortNumber") or b.get("BusinessShortNumber")
            aid = f"che:{corto}"
            titulo = _limpio(b.get("Title") or v.get("BusinessTitle")) or corto
            tipo_a = tipo_asunto(tipo_objeto, titulo, sorted(proyectos.get(numero_obj, ())))
            abrev = b.get("BusinessTypeAbbreviation")
            codigo = f"{abrev} {corto}" if abrev else corto
            url_a = f"https://www.parlament.ch/fr/ratsbetrieb/suche-curia-vista/geschaeft?AffairId={numero_obj}"
            autor = "Consejo Federal" if tipo_objeto == 1 else _limpio(b.get("SubmittedBy")) or None
            fecha_a = _fecha(b.get("SubmissionDate")) or fecha
        if aid not in asuntos:
            asuntos[aid] = Asunto(id=aid, titulo=titulo[:400], tipo=tipo_a, fecha=fecha_a, codigo=codigo, autor=autor, url=url_a,
                                  extra={"objeto": abrev} if abrev else None)
        sujeto = _limpio(v.get("Subject"))
        si_txt, no_txt = _limpio(v.get("MeaningYes")), _limpio(v.get("MeaningNo"))
        tipo = tipo_votacion(ficticio, tipo_a, sujeto, si_txt, no_txt)
        # «Sí» a favor del objeto: si la opción del sí es rechazarlo (y la del no no), se invierten.
        invertir = tipo != "procedimiento" and polaridad(si_txt) < 0 and polaridad(no_txt) >= 0
        cambio = {"si": "no", "no": "si"} if invertir else {}
        lista = []
        for persona, nombre, canton, grupo, decision in votos.get(v["ID"], []):
            if grupo not in FUENTE.partidos:
                ctx.partido(grupo)
            sentido = SENTIDO.get(decision, "no_vota")
            lista.append((f"che:{persona}", f"{nombre} ({canton})" if canton else nombre, grupo, cambio.get(sentido, sentido)))
        n = {s: sum(1 for x in lista if x[3] == s) for s in ("si", "no", "abstencion", "no_vota")}
        cualificada = tipo != "procedimiento" and any(k in f"{sujeto} {si_txt}".lower() for k in CUALIFICADA)
        if (ficticio and numero_obj == 2) or not lista:
            resultado = None
        elif cualificada:
            resultado = "aprobada" if n["si"] >= MAYORIA_ABSOLUTA else "rechazada"
        else:
            resultado = "aprobada" if n["si"] > n["no"] else "rechazada"
        if invertir:
            si_txt, no_txt = no_txt, si_txt
        partes = [etiqueta(sujeto, tipo_objeto, numero_obj if ficticio else None, tipo_a)]
        if v.get("BillTitle"):
            proyecto = _limpio(v["BillTitle"])
            partes.append(proyecto if len(proyecto) <= 200 else proyecto[:197] + "…")
        texto = " · ".join(partes)
        if si_txt or no_txt:
            texto += f" (sí: {si_txt or '—'} / no: {no_txt or '—'}"
            texto += "; sí y no invertidos respecto al acta)" if invertir else ")"
        leg, reg = v.get("IdLegislativePeriod"), v.get("RegistrationNumber")
        votaciones.append(Votacion(
            id=f"che:n{v['ID']}", fecha=fecha, asunto_id=aid, camara="che-n", numero=reg, texto=texto[:600], tipo=tipo,
            a_favor=n["si"], en_contra=n["no"], abstenciones=n["abstencion"], no_votan=n["no_vota"],
            mayoria="absoluta" if cualificada else "simple", resultado=resultado,
            url=f"https://www.parlament.ch/poly/Abstimmung/{leg}/out/vote_{leg}_{reg}.pdf" if leg and reg else None,
            votos=lista or None))
    for i in range(0, len(votaciones), 200):
        lote = votaciones[i:i + 200]
        ctx.guardar([asuntos[a] for a in dict.fromkeys(x.asunto_id for x in lote)], lote)
    return len(votaciones)


def recoger(ctx):
    hechas = set(ctx.marca("sesiones", []))
    hoy = date.today()
    corte = f"{ctx.desde}-01-01"
    ultima = ctx.ultima_fecha()
    if ultima and not ctx.completo:  # se repasan diez días por si se corrige algo
        corte = max(corte, (date.fromisoformat(ultima) - timedelta(days=10)).isoformat())
    sesiones = _odata(ctx, "Session", f"Language eq '{LENGUA}' and EndDate ge datetime'{ctx.desde}-01-01T00:00:00'",
                      "ID,SessionName,StartDate,EndDate", orden="StartDate")
    pendientes = [s for s in sesiones if _fecha(s["StartDate"]) <= hoy.isoformat()
                  and (ctx.completo or s["ID"] not in hechas)]
    ctx.log(f"   {len(pendientes)} sesiones por recoger desde {corte}")
    with ThreadPoolExecutor(4) as ex:
        for i in range(0, len(pendientes), 4):
            for sesion, votes, votos, objetos in ex.map(lambda s: _sesion(ctx, s, corte), pendientes[i:i + 4]):
                n = _procesar(ctx, sesion, votes, votos, objetos)
                ctx.log(f"   {_limpio(sesion.get('SessionName'))}: {n} votaciones")
                if _fecha(sesion["EndDate"]) < (hoy - timedelta(days=3)).isoformat():
                    hechas.add(sesion["ID"])
                    ctx.poner_marca("sesiones", sorted(hechas))
