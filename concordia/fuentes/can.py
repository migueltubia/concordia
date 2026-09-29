"""Canadá: divisiones (votaciones nominales) de la Cámara de los Comunes.

La web oficial (https://www.ourcommons.ca/members/en/votes) publica, por sesión de cada legislatura («44-1»
es la 1.ª sesión de la 44.ª legislatura), un XML con todas las divisiones: número, fecha, qué se vota
(«3rd reading and adoption of Bill C-69, An Act to implement…»), totales, resultado y número del proyecto
de ley; y, por división, un CSV con el voto de cada diputado (Yea, Nay o Paired) y su grupo. Se recoge desde
2019: la 42-1 (solo sus votaciones de 2019), 43-1, 43-2, 44-1 y 45-1; las sesiones nuevas (tras una
prórroga o unas elecciones) se buscan solas. Los títulos de los proyectos de ley salen de LEGISinfo
(https://www.parl.ca/legisinfo), que da en un JSON todos los de una sesión. Las sesiones cerradas se
descargan una vez.

Particularidades:
- Solo hay voto registrado cuando se pide una división: lo que se aprueba «on division» o sin oposición no
  aparece. El Senado (no electo) no se recoge.
- El CSV solo trae a los que votan y a los emparejados («paired», que no votan): los ausentes se deducen de
  la lista de diputados de la legislatura (con sus fechas de alta y baja) y cuentan como «no_vota», con el
  grupo que tenían en la votación más cercana (hay cambios de grupo a mitad de legislatura).
- Asunto: el proyecto de ley de la sesión (C-69, S-211…) con todas sus lecturas, enmiendas, «time allocation»
  y cierres; o la moción: de la oposición («Opposition Motion (…)», agrupada por tema y fecha), del Gobierno
  («Government Business No. N»), de un diputado («M-N»), la respuesta al discurso del Trono, la política
  presupuestaria, las «ways and means» o la aprobación de un informe de comisión. Los votos de los créditos
  («supply»: partidas impugnadas y aprobación de las «estimates») se agrupan por jornada y los trámites
  sueltos (levantar la sesión, pasar al orden del día…), por día.
- Una segunda o tercera lectura dividida por partes («Clauses 1 to 136…», «Part 1») es «parcial»; la
  votación decisiva de esos proyectos es entonces la anterior votación sobre el conjunto.
"""

import bisect
import csv
import io
import json
import re
import time
import unicodedata
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from .modelo import Asunto, Fuente, Votacion

FUENTE = Fuente(
    codigo="can", pais="CAN", nombre="Parlamento de Canadá (Cámara de los Comunes)", corto="Canadá",
    tipo="parlamento", detalle="nominal", web="https://www.ourcommons.ca/members/en/votes", desde=2019, idioma="en",
    licencia=("Permiso del Presidente de la Cámara de los Comunes: reproducción libre si es exacta, "
              "no se presenta como oficial y no tiene fines comerciales"),
    camaras={"can-c": ("Cámara de los Comunes", "Comunes", 343)},
    partidos={
        "Liberal": ("Partido Liberal", "PLC", "#d71920"),
        "Conservative": ("Partido Conservador", "PCC", "#1a4782"),
        "Bloc Québécois": ("Bloque Quebequés", "BQ", "#33b2cc"),
        "NDP": ("Nuevo Partido Democrático", "NPD", "#f37021"),
        "Green Party": ("Partido Verde", "Verdes", "#3d9b35"),
        "People's Party": ("Partido Popular de Canadá", "PPC", "#4e2a84"),
        "Co-operative Commonwealth Federation": ("Co-operative Commonwealth Federation", "CCF", "#b5541c"),
        "Independent": ("Independientes", "Ind.", "#898781"),
    },
    notas=("Solo divisiones (votaciones con recuento nominal pedidas en el pleno); lo aprobado sin división "
           "no aparece. Los ausentes se deducen de la lista de diputados."),
)

WEB = "https://www.ourcommons.ca/members/en"
LEGISINFO = "https://www.parl.ca/legisinfo/en"
# Sesiones conocidas: «legislatura-sesión» -> (primer año, último año). Las siguientes se buscan solas.
SESIONES = {"42-1": (2015, 2019), "43-1": (2019, 2020), "43-2": (2020, 2021), "44-1": (2021, 2025), "45-1": (2025, None)}
SENTIDO = {"yea": "si", "nay": "no"}
MESES = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
         "November", "December")
LOTE = 150


# ------------------------------------------------------------------ textos

def _limpio(t):
    t = re.sub(r"\s+", " ", t or "").strip()
    while t.endswith(")") and t.count(")") > t.count("("):   # «… (amendment))» en la fuente
        t = t[:-1].rstrip()
    return re.sub(r"^Tme allocation", "Time allocation", t)


def _norma(t):
    return re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()


def _slug(t):
    t = unicodedata.normalize("NFKD", t.lower()).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:60] or "x"


# Paréntesis finales que no son parte del nombre del asunto sino de lo que se vota dentro de él.
CALIFICA = re.compile(
    r"(?:(?:original )?main motion(?: as amended)?(?: with subamendment)?|(?:with )?(?:amendment )?as amended"
    r"|(?:reasoned |hoist )?(?:sub)?amendments?(?: as amended)?|(?:sub)?amendment to g-\d+"
    r"|report stage (?:sub)?amendment.*|motion(?: no\.?)?\s*\d.*|previous question|recommittal.*"
    r"|clauses? \d.*|part \d.*|all remaining provisions.*|opposed vote no\.?\s*\d+)[\s;.,]*(?:and)?",
    re.I)


def _parentesis_final(t):
    """Posición del «(» que abre el paréntesis con el que acaba t (equilibrado), o None."""
    if not t.endswith(")"):
        return None
    nivel = 0
    for i in range(len(t) - 1, -1, -1):
        if t[i] == ")":
            nivel += 1
        elif t[i] == "(":
            nivel -= 1
            if nivel == 0:
                return i
    return None


def cola(t):
    """Separa los paréntesis finales que califican la votación:

    «Opposition Motion (Carbon tax) (amendment)» -> («Opposition Motion (Carbon tax)», ["amendment"]);
    «… (report stage amendment) (Motion No. 3)» -> (…, ["report stage amendment", "Motion No. 3"]).
    """
    t = t.strip()
    quals = []
    while True:
        i = _parentesis_final(t)
        if i is None:
            break
        dentro = t[i + 1:-1].strip()
        if not CALIFICA.fullmatch(dentro):
            break
        quals.insert(0, dentro)
        t = t[:i].rstrip()
    return t, quals


def _tema(base, prefijo):
    """«Opposition Motion (Opioid crisis (original main motion))» -> «Opioid crisis»."""
    resto = base[len(prefijo):].strip() if base.lower().startswith(prefijo.lower()) else base
    if resto.startswith("(") and _parentesis_final(resto) == 0:
        resto = resto[1:-1]
    resto = cola(resto.strip())[0]
    resto = re.sub(r"^as amended\s*[-–—:]\s*", "", resto, flags=re.I)
    return resto.strip(" -–—")


ORDINALES = {w: i for i, w in enumerate(
    ("first second third fourth fifth sixth seventh eighth ninth tenth eleventh twelfth thirteenth fourteenth "
     "fifteenth sixteenth seventeenth eighteenth nineteenth twentieth").split(), 1)}
ORDINALES.update({"nineth": 9, "eight": 8})


def _clave_generica(base):
    """Clave para agrupar votaciones del mismo asunto sin número: «Twelfth report» = «12th Report»."""
    t = re.sub(r"\b(\d+)(?:st|nd|rd|th)\b", r"\1", base.lower())
    t = re.sub(r"\b(" + "|".join(ORDINALES) + r")\b(?= report)", lambda m: str(ORDINALES[m.group(1)]), t)
    t = re.sub(r" affairs\b", "", t)   # la fuente escribe a veces «Committee on Veterans» y otras «on Veterans Affairs»
    return _slug(t)


# ------------------------------------------------------------------ tipos

TRATADO = re.compile(r"\b(?:implement|give effect to|accession to)\b.*?\b(?:agreements?|conventions?|protocol|treaty|arrangement)\b"
                     r"|free trade agreement|trade agreement\b|tax (?:convention|agreement)|partnership agreement", re.I)
NO_TRATADO = re.compile(r"self-government|first nations?|\bnation\b|m[ée]tis|\bcrees?\b|indigenous|provinces|modern treaty|"
                        r"atlantic accord", re.I)
PROCEDIMIENTO = re.compile(r"time allocation|closure|previous question|recommittal|proceedings on|instruction to|\bdivide\b|"
                           r"adjourn|orders? of the day|hear another member|presenting petitions|first reading of senate", re.I)
GB_PROCEDIMIENTO = re.compile(r"sitting|standing orders|business of the house|proceedings on|order respecting|extended proceedings|"
                              r"hybrid|house and its committees", re.I)


def tipo_proyecto(titulo, corto=None):
    t = " ".join(x for x in (titulo, corto) if x)
    return "tratado" if TRATADO.search(t) and not NO_TRATADO.search(t) else "ley"


def tipo_votacion_proyecto(fase):
    """Qué se vota de un proyecto de ley, por la fase («2nd reading of Bill C-5 (reasoned amendment)»)."""
    f = fase.lower()
    # Lo que dice una parte («Clauses 197 to 208 … regarding amendments to the Canada Labour Code») no cuenta.
    sin_partes = re.sub(r"\((?:clauses?|part) \d[^()]*\)", "", f)
    if PROCEDIMIENTO.search(sin_partes) or "government business" in sin_partes:   # mociones de trámite del Gobierno
        return "procedimiento"
    if "amendment" in sin_partes.replace("senate amendments", ""):
        return "enmienda"
    if sin_partes != f:
        return "parcial"
    # «Concurrence at report stage and second reading» (proyectos enviados a comisión antes de la 2.ª lectura).
    if re.search(r"(?:2nd|3rd|second|third) reading|senate amendments", f):
        return "final"
    return "otra"   # «Concurrence at report stage», informes de comisión sobre el proyecto


def tipo_votacion_mocion(base, quals, prefijo_enmienda, tipo_a):
    q = " ".join(quals).lower()
    if tipo_a == "procedimiento" or "previous question" in q:
        return "procedimiento"
    if tipo_a == "nombramiento":
        return "nombramiento"
    if prefijo_enmienda or re.search(r"(?:^|\b)(?:reasoned |hoist )?(?:sub)?amendment(?! to g)", q) and "main motion" not in q:
        return "enmienda"
    if re.search(r"(?:clauses?|part) \d|opposed vote", q) or "opposed item" in base.lower():
        return "parcial"
    return "final"


def resultado(nombre, si, no):
    n = (nombre or "").lower()
    if n.startswith("agreed"):
        return "aprobada"
    if n.startswith("negatived"):
        return "rechazada"
    return "aprobada" if (si or 0) > (no or 0) else "rechazada"


def _fecha_larga(f, dia=True):
    d = date.fromisoformat(f)
    return f"{d.day} {MESES[d.month - 1]} {d.year}" if dia else f"{MESES[d.month - 1]} {d.year}"


# ------------------------------------------------------------------ descargas

def _descarga(ctx, url, nombre, caduca_horas):
    """ctx.cache; si la descarga falla, vale la copia anterior aunque haya caducado."""
    try:
        return ctx.cache(url, nombre, caduca_horas=caduca_horas)
    except Exception:
        return ctx.cache(url, nombre)


def _lista(ctx, ps, fresca):
    ruta = _descarga(ctx, f"{WEB}/votes/xml?parlSession={ps}", f"votos-{ps}.xml", 6 if fresca else None)
    salida = []
    for v in ET.parse(ruta).getroot().findall("Vote"):
        g = lambda c: (v.findtext(c) or "").strip()  # noqa: E731
        salida.append({"numero": int(g("DecisionDivisionNumber")), "fecha": g("DecisionEventDateTime")[:10],
                       "asunto": _limpio(g("DecisionDivisionSubject")), "resultado": g("DecisionResultName"),
                       "si": int(g("DecisionDivisionNumberOfYeas") or 0), "no": int(g("DecisionDivisionNumberOfNays") or 0),
                       "clase": g("DecisionDivisionDocumentTypeName"), "proyecto": g("BillNumberCode").upper()})
    return sorted(salida, key=lambda x: x["numero"])


def _proyectos(ctx, ps, fresca):
    """Proyectos de ley de la sesión en LEGISinfo: código -> ficha. Sin LEGISinfo, los títulos salen de la votación."""
    try:
        ruta = _descarga(ctx, f"{LEGISINFO}/bills/json?parlsession={ps}", f"proyectos-{ps}.json", 12 if fresca else None)
        return {b["NumberCode"].upper(): b for b in json.loads(ruta.read_text(encoding="utf-8-sig"))}
    except Exception as e:
        ctx.log(f"   ! LEGISinfo {ps}: {type(e).__name__}: {e}"[:200])
        return {}


def _diputados(ctx, legislatura, fresca):
    """Diputados de la legislatura: id -> (nombre, alta, baja, grupo final). Sin la lista no se añaden ausentes."""
    try:
        ruta = _descarga(ctx, f"{WEB}/search/xml?parliament={legislatura}&caucusId=all&province=all&gender=all",
                         f"diputados-{legislatura}.xml", 24 if fresca else None)
        raiz = ET.parse(ruta).getroot()
    except Exception as e:
        ctx.log(f"   ! diputados de la legislatura {legislatura}: {type(e).__name__}: {e}"[:200])
        return {}
    salida = {}
    for m in raiz.findall("MemberOfParliament"):
        g = lambda c: (m.findtext(c) or "").strip()  # noqa: E731
        salida[g("PersonId")] = (f"{g('PersonOfficialFirstName')} {g('PersonOfficialLastName')}".strip(),
                                 g("FromDateTime")[:10] or "0000", g("ToDateTime")[:10] or "9999", g("CaucusShortName") or "Independent")
    return salida


def _votos(ctx, ps, numero):
    """Filas del CSV de una división: [(id, nombre, grupo, sentido)]; si no se puede descargar, el error."""
    p, s = ps.split("-")
    try:
        datos = ctx.fetch(f"{WEB}/votes/{p}/{s}/{numero}/csv")
    except Exception as e:
        return e
    salida = []
    for f in csv.DictReader(io.StringIO(datos.decode("utf-8-sig"))):
        pid = (f.get("Person ID") or "").strip()
        if not pid:
            continue
        nombre = re.sub(r"\s*\([^()]*\)\s*$", "", (f.get("Member of Parliament") or "").strip())
        voto = (f.get("Member Voted") or "").strip().lower()
        sentido = SENTIDO.get(voto, "no_vota")   # «Paired»: emparejado con un ausente del otro lado, no vota
        salida.append((pid, nombre, (f.get("Political Affiliation") or "").strip() or "Independent", sentido))
    return salida


# ------------------------------------------------------------------ asuntos

class Clasificador:
    """Asigna a cada división de una sesión su asunto (id, título, tipo…), el texto y el tipo de votación."""

    def __init__(self, ps, lista, proyectos):
        self.ps = ps
        self.proyectos = proyectos
        self.asuntos = {}
        self.de = {}   # número de división -> (asunto_id, texto, tipo)
        self._racimos = {}
        oposicion_del_dia = {}
        for v in lista:   # temas de las mociones de la oposición de cada día (para las que no lo dicen)
            base, _ = cola(v["asunto"])
            if base.lower().startswith("opposition motion"):
                tema = _tema(base, "Opposition Motion")
                if tema:
                    oposicion_del_dia.setdefault(v["fecha"], tema)
        self._oposicion_del_dia = oposicion_del_dia
        # Mociones del Gobierno sobre el trámite de un proyecto («Government Business No. 5 (Proceedings on a bill
        # entitled…)»): sus enmiendas y cierres («Amendment to Government Business No. 5») van también al proyecto.
        self._gb_proyecto = {}
        for v in lista:
            m = re.search(r"government business no\.?\s*(\d+)\s*\(", v["asunto"], re.I)
            codigo = self._codigo(v)
            if m and codigo:
                self._gb_proyecto.setdefault(m.group(1), codigo)
        for v in lista:
            self.de[v["numero"]] = self._clasificar(v)

    def _codigo(self, v):
        """Número del proyecto de ley al que se refiere la división, si se refiere a uno."""
        t = v["asunto"]
        if t.lower().startswith("opposition motion"):
            return None
        if v["proyecto"]:
            return v["proyecto"]
        m = re.search(r"(?:proceedings on|time allocation for|divide|regarding) bill ([CS]-\d+)\b", t, re.I)
        if m:
            return m.group(1).upper()
        if re.search(r"proceedings on (?:a|the) bill entitled", t, re.I):
            return self._por_titulo(t)
        m = re.search(r"government business no\.?\s*(\d+)", t, re.I)
        return self._gb_proyecto.get(m.group(1)) if m else None

    def _asunto(self, aid, titulo, tipo, fecha, codigo=None, url=None, autor=None, extra=None):
        if aid not in self.asuntos:
            self.asuntos[aid] = Asunto(id=aid, titulo=titulo[:400], tipo=tipo, fecha=fecha, codigo=codigo, url=url,
                                       autor=autor or None, extra={"sesion": self.ps, **(extra or {})})
        return aid

    def _racimo(self, clave, fecha, hueco):
        """Asuntos sin número propio: las votaciones con la misma clave separadas menos de `hueco` días van juntas."""
        previo = self._racimos.get(clave)
        if previo and (date.fromisoformat(fecha) - date.fromisoformat(previo[1])).days <= hueco:
            aid = previo[0]
        else:
            aid = f"can:{self.ps}:{clave}:{fecha}"
        self._racimos[clave] = (aid, fecha)
        return aid

    def _clasificar(self, v):
        t, fecha, ps = v["asunto"], v["fecha"], self.ps
        codigo = self._codigo(v)
        if codigo:
            return self._proyecto(v, codigo)
        base, quals = cola(t)
        enmienda = bool(re.match(r"(?:sub)?amendment to ", base, re.I))
        base = re.sub(r"^(?:sub)?amendment to (?:the )?", "", base, flags=re.I).strip()
        bl = base.lower()
        m_gb = re.search(r"government business no\.?\s*(\d+)", bl)
        m_pmb = re.search(r"private members' business (m-\d+)", bl)
        m_pap = re.search(r"production of papers (p-\d+)", bl)
        m_wm = re.search(r"ways and means motion no\.?\s*(\d+)", bl)
        if m_gb:
            n = m_gb.group(1)
            tema = _tema(base[m_gb.end():].strip(), "")
            titulo = f"Government Business No. {n}" + (f" ({tema})" if tema else "")
            tipo_a = "procedimiento" if GB_PROCEDIMIENTO.search(tema) else "mocion"
            aid = self._asunto(f"can:{ps}:gb{n}", titulo, tipo_a, fecha, codigo=f"Government Business No. {n} ({ps})")
            if bl.startswith("closure"):
                return aid, t, "procedimiento"
        elif m_pmb:
            n = m_pmb.group(1).upper()
            tema = _tema(base[m_pmb.end():].strip(), "")
            tipo_a = "procedimiento" if re.search(r"standing orders", tema, re.I) else "mocion"
            aid = self._asunto(f"can:{ps}:{n}", f"Private Members' Motion {n}" + (f" ({tema})" if tema else ""), tipo_a, fecha,
                               codigo=f"{n} ({ps})")
        elif m_pap:
            n = m_pap.group(1).upper()
            tema = _tema(base[m_pap.end():].strip(), "")
            aid = self._asunto(f"can:{ps}:{n}", f"Motion for the production of papers {n}" + (f" ({tema})" if tema else ""),
                               "mocion", fecha, codigo=f"{n} ({ps})")
        elif m_wm:
            n = m_wm.group(1)
            aid = self._asunto(f"can:{ps}:wm{n}", f"Ways and Means Motion No. {n}", "mocion", fecha,
                               codigo=f"Ways and Means No. {n} ({ps})")
        elif bl.startswith("address in reply"):
            aid = self._asunto(f"can:{ps}:trono", "Address in Reply to the Speech from the Throne", "mocion", fecha)
        elif bl.startswith("opposition motion"):
            tema = _tema(base, "Opposition Motion") or self._oposicion_del_dia.get(fecha)
            if not tema:
                aid = self._asunto(f"can:{ps}:div{v['numero']}", "Opposition Motion", "mocion", fecha)
            else:
                aid = self._racimo("opp-" + _clave_generica(tema), fecha, 10)
                self._asunto(aid, f"Opposition Motion ({tema})", "mocion", fecha)
        elif v["clase"] == "Supply":
            aid = self._racimo("supply", fecha, 3)
            self._asunto(aid, f"Supply: concurrence in the Estimates ({_fecha_larga(fecha, dia=False)})", "mocion", fecha)
        elif bl.startswith("budgetary policy"):
            aid = self._racimo("budget", fecha, 30)
            self._asunto(aid, f"Budgetary policy of the Government ({fecha[:4]} budget)", "mocion", fecha)
        elif PROCEDIMIENTO.search(bl) and re.match(r"(?:motion|closure|time allocation)", bl):
            aid = self._asunto(f"can:{ps}:proc:{fecha}", f"Procedural motions of the House of Commons ({_fecha_larga(fecha)})",
                               "procedimiento", fecha)
        elif bl.startswith("appointment of"):
            aid = self._asunto(f"can:{ps}:div{v['numero']}", base, "nombramiento", fecha)
        else:   # informes de comisión, cuestiones de privilegio, estado de emergencia…
            aid = self._racimo(_clave_generica(base), fecha, 21)
            self._asunto(aid, base, "mocion", fecha)
        return aid, t, tipo_votacion_mocion(base, quals, enmienda, self.asuntos[aid].tipo)

    def _por_titulo(self, t):
        """Proyecto de la sesión cuyo título largo aparece en el texto («Proceedings on a bill entitled An Act…»)."""
        texto = _norma(t)
        hallados = [(len(_norma(b.get("LongTitleEn"))), c) for c, b in self.proyectos.items()
                    if len(_norma(b.get("LongTitleEn"))) > 20 and _norma(b.get("LongTitleEn")) in texto]
        return max(hallados)[1] if hallados else None

    def _proyecto(self, v, codigo):
        ps, t = self.ps, v["asunto"]
        ficha = self.proyectos.get(codigo) or {}
        titulo = _limpio(ficha.get("LongTitleEn"))
        corto = _limpio(ficha.get("ShortTitleEn"))
        fase = t if "bill entitled" in t.lower() else _sin_titulo(t, titulo)
        if not titulo:   # sin ficha en LEGISinfo: el título que trae la votación
            m = re.search(rf"\b{re.escape(codigo)}\b,\s*(.+)", t)
            titulo = cola(m.group(1))[0] if m else f"Bill {codigo}"
        aid = self._asunto(f"can:{ps}:{codigo}", titulo, tipo_proyecto(titulo, corto), v["fecha"], codigo=f"{codigo} ({ps})",
                           url=f"{LEGISINFO}/bill/{ps}/{codigo.lower()}", autor=_limpio(ficha.get("SponsorPersonName")),
                           extra={"titulo_corto": corto} if corto else None)
        return aid, fase, tipo_votacion_proyecto(fase)


def _sin_titulo(t, titulo):
    """Lo que se vota de un proyecto, sin su título largo: «3rd reading and adoption of Bill C-59 (Clauses 1 to 136)»."""
    if titulo:
        patron = r"[\s\-–—]+".join(re.escape(p) for p in re.split(r"[\s\-–—]+", titulo) if p)
        m = re.search(patron, t, re.I)
        if m:
            fase = t[:m.start()] + " " + t[m.end():]
            fase = re.sub(r"\s*,\s*(?=\)|$|\()", " ", fase)
            return re.sub(r"\s+", " ", fase).replace("( ", "(").replace(" )", ")").strip(" ,")
    base, quals = cola(t)
    m = re.search(r"\b[CS]-\d+\b", base)
    return " ".join([base[:m.end()] if m else base] + [f"({q})" for q in quals])


# ------------------------------------------------------------------ recogida

def _sesiones(ctx):
    """Sesiones conocidas y las nuevas que ya tengan votaciones (la siguiente de la legislatura o la 1.ª de la siguiente)."""
    sesiones = list(SESIONES)
    p, s = map(int, sesiones[-1].split("-"))
    while True:
        nueva = next((ps for ps in (f"{p}-{s + 1}", f"{p + 1}-1") if _existe(ctx, ps)), None)
        if not nueva:
            return sesiones
        sesiones.append(nueva)
        p, s = map(int, nueva.split("-"))


def _existe(ctx, ps):
    try:
        return bool(_lista(ctx, ps, fresca=True))
    except Exception:   # una sesión que aún no existe puede dar error en vez de una lista vacía
        return False


def recoger(ctx):
    hechas = ctx.marca("sesiones", {})   # sesión -> {desde, hasta, cerrada}
    inicio = f"{ctx.desde}-01-01"
    sesiones = _sesiones(ctx)
    for ps in sesiones:
        fin = SESIONES.get(ps, (None, None))[1]
        if fin and fin < ctx.desde:
            continue
        actual = ps == sesiones[-1]
        previa = None if ctx.completo else hechas.get(ps)
        corte = inicio
        if previa and previa["desde"] <= inicio:
            if previa.get("cerrada"):
                continue
            corte = max(inicio, (date.fromisoformat(previa["hasta"]) - timedelta(days=7)).isoformat())
        lista = _lista(ctx, ps, fresca=True)
        nuevas = [v for v in lista if v["fecha"] >= corte]
        ctx.log(f"   sesión {ps}: {len(nuevas)} divisiones desde {corte} (de {len(lista)})")
        fallidas = []
        if nuevas:
            fallidas = _recoger_sesion(ctx, ps, lista, nuevas, fresca=actual or not previa)
        hasta = max([v["fecha"] for v in nuevas if v["numero"] not in fallidas] + ([previa["hasta"]] if previa else []),
                    default=corte)
        if fallidas:
            hasta = min([hasta] + [v["fecha"] for v in nuevas if v["numero"] in fallidas])
        hechas[ps] = {"desde": min(inicio, previa["desde"]) if previa else inicio, "hasta": hasta,
                      "cerrada": not actual and not fallidas}
        ctx.poner_marca("sesiones", hechas)


def _motivo(f):
    return f"{type(f).__name__}: {f}"[:120] if isinstance(f, Exception) else "CSV vacío"


def _recoger_sesion(ctx, ps, lista, nuevas, fresca):
    legislatura = ps.split("-")[0]
    clas = Clasificador(ps, lista, _proyectos(ctx, ps, fresca))
    diputados = _diputados(ctx, legislatura, fresca)
    with ThreadPoolExecutor(4) as ex:
        filas = list(ex.map(lambda v: _votos(ctx, ps, v["numero"]), nuevas))
    # La web corta a veces tras cientos de peticiones seguidas: las que fallan se reintentan una a una, más despacio.
    fallos = [i for i, f in enumerate(filas) if not isinstance(f, list) or not f]
    if fallos:
        ctx.log(f"   {len(fallos)} divisiones sin votos al primer intento ({_motivo(filas[fallos[0]])}); se reintentan")
        time.sleep(15)
        for i in fallos:
            filas[i] = _votos(ctx, ps, nuevas[i]["numero"])
            time.sleep(0.5)
    filas = [f if isinstance(f, list) and f else None for f in filas]
    fallidas = [v["numero"] for v, f in zip(nuevas, filas) if not f]
    if fallidas:
        ctx.log(f"   ! {len(fallidas)} divisiones sin votos: {fallidas[:5]}{' …' if len(fallidas) > 5 else ''}")
    # Grupo de cada diputado en cada votación, para dar a los ausentes el de la votación más cercana.
    historial = {}
    for v, f in zip(nuevas, filas):
        for pid, _, grupo, _ in f or []:
            historial.setdefault(pid, []).append((v["numero"], grupo))

    def grupo_de(pid, numero):
        h = historial.get(pid)
        if not h:
            return diputados[pid][3]
        i = bisect.bisect_left(h, (numero, ""))
        cerca = [x for x in (h[i - 1] if i else None, h[i] if i < len(h) else None) if x]
        return min(cerca, key=lambda x: abs(x[0] - numero))[1]

    asuntos, votaciones = {}, []
    for v, f in zip(nuevas, filas):
        if not f:
            continue
        aid, texto, tipo = clas.de[v["numero"]]
        votos, presentes = [], set()
        for pid, nombre, grupo, sentido in f:
            if grupo not in FUENTE.partidos:
                ctx.partido(grupo)
            presentes.add(pid)
            votos.append((f"can:{pid}", diputados.get(pid, (nombre,))[0] or nombre, grupo, sentido))
        for pid, (nombre, alta, baja, _) in diputados.items():   # ausentes: diputados en su escaño ese día que no votan
            if pid not in presentes and alta <= v["fecha"] <= baja:
                grupo = grupo_de(pid, v["numero"])
                if grupo not in FUENTE.partidos:
                    ctx.partido(grupo)
                votos.append((f"can:{pid}", nombre, grupo, "no_vota"))
        p, s = ps.split("-")
        asuntos[aid] = clas.asuntos[aid]
        votaciones.append(Votacion(
            id=f"can:{ps}:{v['numero']}", fecha=v["fecha"], asunto_id=aid, camara="can-c", numero=v["numero"],
            texto=texto[:400], tipo=tipo, a_favor=v["si"], en_contra=v["no"], abstenciones=0,
            no_votan=sum(1 for x in votos if x[3] == "no_vota"), resultado=resultado(v["resultado"], v["si"], v["no"]),
            url=f"{WEB}/votes/{p}/{s}/{v['numero']}", votos=votos))
        if len(votaciones) >= LOTE:
            ctx.guardar(list(asuntos.values()), votaciones)
            ctx.log(f"   sesión {ps}: {len(votaciones)} votaciones guardadas (hasta la división {v['numero']})")
            asuntos, votaciones = {}, []
    if votaciones:
        ctx.guardar(list(asuntos.values()), votaciones)
        ctx.log(f"   sesión {ps}: {len(votaciones)} votaciones guardadas")
    return fallidas
