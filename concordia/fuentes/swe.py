"""Suecia: votaciones nominales del Riksdag (datos abiertos, https://data.riksdagen.se).

El Riksdag vota por puntos (förslagspunkter) de los informes de sus comisiones (betänkanden, p. ej.
2024/25:UU12): cada punto es una decisión aparte («la cámara aprueba el proyecto de ley X», «rechaza las
mociones sobre Y») y solo se vota con registro cuando algún grupo mantiene una propuesta alternativa
(reservation); lo demás se aprueba por aclamación y no deja rastro nominal. Por eso el asunto es el punto
del informe («2024/25:UU12 p. 3»), con el título del informe y el epígrafe del punto, y no el informe
entero, que en las comisiones de exteriores o defensa junta decisiones sobre países distintos.

En cada punto hay una votación principal (huvudvotering) «i sakfrågan» —la propuesta de la comisión contra
la reserva que ganó las votaciones previas, que no se publican— y, a veces, otra «i motivfrågan», sobre la
motivación del informe y no sobre la decisión (se guarda como enmienda). Sí = propuesta de la comisión;
No = la reserva. El texto de cada votación lleva la propuesta de la comisión («Riksdagen godkänner avtalet...»,
«Riksdagen avslår motionerna... (V)»), que es lo que dice qué se aprueba, y el título avisa cuando lo que se
aprueba es rechazar mociones o el proyecto del Gobierno («… (avslag på motioner)»), que es lo más frecuente.

Fuentes:
- Descarga masiva por periodo de sesiones (riksmöte, de septiembre a septiembre):
  https://data.riksdagen.se/dataset/votering/votering-202425.json.zip, un JSON por votación con el voto de
  cada diputado. Los cerrados se descargan una vez; el abierto, cada día.
- La lista de votaciones de la API (voteringlista agrupada por votación), que manda: trae lo que el fichero no
  tiene (investiduras del primer ministro, mociones de censura y otras votaciones sin informe, que hasta
  2024/25 no están en los ficheros, y lo votado desde la última actualización) y deja fuera las votaciones
  anuladas y repetidas que el fichero conserva.
- Los puntos de cada informe (utskottsforslag/<dok_id>): título del informe, epígrafe y propuesta de cada
  punto, la reserva con la que se enfrentó y el vencedor (que decide el resultado con mayorías especiales).

Datos desde 1993/94; se recoge desde 2019. Algunas votaciones con mayoría especial no tienen voto nominal en
los datos abiertos (la aprobación del acuerdo de defensa con EEUU, 2023/24:UFöU1 p. 1, en junio de 2024). Los
títulos están en sueco: las reglas no los leen y la ficha la hace la IA.
"""

import html
import json
import re
import urllib.error
import zipfile
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from urllib.parse import quote

from .modelo import Asunto, Fuente, Votacion

FUENTE = Fuente(
    codigo="swe", pais="SWE", nombre="Riksdag de Suecia", corto="Suecia", tipo="parlamento", detalle="nominal",
    web="https://www.riksdagen.se", desde=2019, idioma="otro",
    licencia="Datos abiertos del Riksdag: uso y difusión libres citando la fuente («Källa: Sveriges riksdag»)",
    camaras={"swe-r": ("Riksdag", "Riksdag", 349)},
    partidos={
        "S": ("Partido Socialdemócrata", "S", "#e8112d"), "M": ("Partido Moderado", "M", "#52bdec"),
        "SD": ("Demócratas de Suecia", "SD", "#dddd00"), "C": ("Partido del Centro", "C", "#009933"),
        "V": ("Partido de la Izquierda", "V", "#da291c"), "KD": ("Democristianos", "KD", "#000077"),
        "L": ("Liberales", "L", "#006ab3"), "MP": ("Partido Verde", "MP", "#83cf39"),
        "-": ("Independientes (sin partido)", "Indep.", "#898781"),
    },
    notas="Votaciones nominales del pleno por punto de cada informe de comisión, investiduras y mociones de censura; "
          "lo que se aprueba por aclamación (la mayoría de los puntos) no tiene votación registrada.",
)

API = "https://data.riksdagen.se"
WEB = "https://www.riksdagen.se/sv/dokument-och-lagar/dokument/betankande"
CAMARA = "swe-r"
SENTIDO = {"Ja": "si", "Nej": "no", "Avstår": "abstencion", "Frånvarande": "no_vota"}
MAYORIA_ABSOLUTA = 175  # más de la mitad de los 349 escaños
LOTE = 300
UTSKOTT = {
    "AU": "Arbetsmarknadsutskottet", "CU": "Civilutskottet", "FiU": "Finansutskottet", "FöU": "Försvarsutskottet",
    "JuU": "Justitieutskottet", "KU": "Konstitutionsutskottet", "KrU": "Kulturutskottet",
    "MJU": "Miljö- och jordbruksutskottet", "NU": "Näringsutskottet", "SfU": "Socialförsäkringsutskottet",
    "SkU": "Skatteutskottet", "SoU": "Socialutskottet", "TU": "Trafikutskottet", "UbU": "Utbildningsutskottet",
    "UU": "Utrikesutskottet", "UFöU": "Sammansatta utrikes- och försvarsutskottet",
}
# Votaciones sin informe: la «beteckning» es la fecha y un número («0621-1»).
ESPECIAL = re.compile(r"\d{4}-\d+")


def riksmoten(desde, hoy):
    """Periodos de sesiones (septiembre-septiembre) desde el que incluye el 1 de enero de `desde`: «2018/19»..."""
    ultimo = hoy.year if hoy.month >= 9 else hoy.year - 1
    return [f"{a}/{(a + 1) % 100:02d}" for a in range(desde - 1, ultimo + 1)]


def _lista(x):
    return x if isinstance(x, list) else [x] if x else []


def _texto_html(s):
    s = re.sub(r"<br\s*/?>", " ", s or "", flags=re.I)
    s = html.unescape(re.sub(r"<[^>]+>", " ", s)).replace("\xad", "")  # sin guiones de corte
    return re.sub(r"\s+", " ", s).strip()


_NUM = r"\d+(?![\d/:])(?:\s*[-–]\s*\d+(?![\d/:]))?"
_YRKANDE = rf"(?: yrkande(?:na)? {_NUM}(?:(?:,| och) {_NUM})*)?"


def forslag_corto(s):
    """La propuesta de la comisión sin los autores ni los apartados de cada moción:

    «Riksdagen avslår motionerna 2025/26:2372 av Ciczie Weidby m.fl. (V) yrkande 9 och 2025/26:3321 av Leila
    Ali Elmi (MP) yrkandena 1 och 2.» -> «Riksdagen avslår motionerna 2025/26:2372 (V) och 2025/26:3321 (MP).»
    """
    t = _texto_html(s)
    t = re.sub(rf"(\d{{4}}/\d{{2,4}}:\w+) av [^()]*?\((?:båda |alla |samtliga )?([^)]*)\){_YRKANDE}", r"\1 (\2)", t)
    return t


# «Riksdagen godkänner avtalet / det avancerade ramavtalet / Sveriges anslutning till konventionen / protokollet...»
_TRATADO = re.compile(r"godkänner (?:\S+ ){0,6}?\w*(?:avtal|konvention|överenskommelse|protokoll|fördrag|stadga|anslutning)")
_PRESUPUESTO = re.compile(r"anvisar|anslag|utgiftsram|utgiftsområde|statens budget|statsbudget|inkomstberäkning|beräkningen av")
# Leyes («antar regeringens förslag till lag / till vapenlag», «antar slutligt det vilande förslaget»), rechazos de
# proyectos y autorizaciones al Gobierno.
_LEY = re.compile(r"\bantar\b(?! utlåtande)|förslag till (?:\d+\. )?\w*lag\b|lagförslag|grundlag|bemyndig"
                  r"|avslår propositionen|avslår regeringens förslag")


def tipo_asunto(titulo, rubrik, forslag):
    """Tipo de asunto por la propuesta de la comisión («Riksdagen antar / godkänner / avslår...»).

    Cuenta lo que se decide, antes de «Därmed bifaller riksdagen proposition... och avslår motionerna...».
    Los presupuestos son leyes aunque aprueben de paso un acuerdo (la garantía de un préstamo de la UE).
    """
    todo = (forslag or "").lower()
    f = re.split(r"\bdärmed\b", todo)[0]
    r = f"{rubrik or ''} {titulo or ''}".lower()
    if re.search(r"\bväljer\b", f):
        return "nombramiento"
    if _PRESUPUESTO.search(f):
        return "ley"
    if _TRATADO.search(f) or ("godkänner" in f and re.search(r"skatteavtal|dubbelbeskattning|godkännande av (?:\S+ ){0,4}?(?:avtal|konvention|protokoll|fördrag)", r)):
        return "tratado"
    if _LEY.search(f):
        return "ley"
    if re.search(r"tillkännager|ställer sig bakom|godkänner|beslutar|medger|utlåtande|yttrande", f):
        return "resolucion"
    if re.search(r"motion|yrkande", todo):
        return "mocion"
    return "otro"


def especial(titulo):
    """Tipo de asunto, tipo de votación y regla de mayoría de una votación sin informe, por su título."""
    t = (titulo or "").lower()
    if "misstroende" in t:
        return "mocion", "final", "censura"                    # hace falta el sí de 175
    if "statsminister" in t:
        return "nombramiento", "nombramiento", "investidura"   # sale adelante si no votan en contra 175
    if "folkomröstning" in t:
        return "mocion", "final", "tercio"                     # referéndum sobre una reforma constitucional: 117 síes
    if "talman" in t:
        return "nombramiento", "nombramiento", "simple"
    if any(k in t for k in ("ledighet", "hänvisning", "arbetsplenum", "kammarens sammanträde")):
        return "procedimiento", "procedimiento", "simple"
    return "mocion", "final", "simple"


def resultado_especial(regla, si, no):
    """(resultado, mayoría) de una votación sin informe según su regla (Regeringsformen 6:4, 13:2 y 8:16)."""
    if regla == "investidura":
        return ("rechazada" if no >= MAYORIA_ABSOLUTA else "aprobada"), "Menos de 175 votos en contra"
    if regla == "censura":
        return ("aprobada" if si >= MAYORIA_ABSOLUTA else "rechazada"), "Mayoría absoluta (175)"
    if regla == "tercio":
        return ("aprobada" if si >= 117 else "rechazada"), "Un tercio de los escaños (117)"
    return ("aprobada" if si > no else "rechazada"), "Enkel majoritet"


def _textos(x):
    """Las cadenas de un resumen de votación (HTML convertido a JSON, con formas distintas según el año)."""
    if isinstance(x, dict):
        for v in x.values():
            yield from _textos(v)
    elif isinstance(x, list):
        for v in x:
            yield from _textos(v)
    elif isinstance(x, str) and x.strip():
        yield x.strip()


def resumenes(sammanfattning):
    """[(avser, rótulo, (sí, no, abst., ausentes))] de cada tabla del resumen de votación de un punto."""
    salida = []
    for tabla in _lista((sammanfattning or {}).get("table") if isinstance(sammanfattning, dict) else None):
        textos = list(_textos(tabla))
        avser, rotulo, totales = None, None, None
        for i, s in enumerate(textos):
            m = re.match(r"Omröstning i (\w+)", s)
            if m and avser is None:
                avser = m.group(1).lower()
                sig = textos[i + 1] if i + 1 < len(textos) else ""
                rotulo = s if sig in ("Parti",) else f"{s}: {sig}"
            if s == "Totalt" and i + 4 < len(textos):
                try:
                    totales = tuple(int(n) for n in textos[i + 1:i + 5])
                except ValueError:
                    pass
        if avser:
            salida.append((avser, rotulo, totales))
    return salida


def _forslag(ctx, dok_id, abierto):
    """Título del informe y sus puntos: {punkt: {...}} (utskottsforslag)."""
    try:
        ruta = ctx.cache(f"{API}/utskottsforslag/{quote(dok_id)}.json", f"uf_{dok_id}.json",
                         caduca_horas=20 if abierto else None)
        d = json.loads(ruta.read_text(encoding="utf-8-sig"))["utskottsforslag"]
    except Exception as e:  # sin la ficha del informe, la votación se guarda con un título genérico
        ctx.log(f"   ! {dok_id}: {type(e).__name__}: {e}")
        return None
    doc = d.get("dokument") or {}
    puntos = {}
    for p in _lista((d.get("dokutskottsforslag") or {}).get("utskottsforslag")):
        puntos[str(p.get("punkt"))] = p
    return {"titulo": _texto_html(doc.get("titel")), "organ": doc.get("organ"), "puntos": puntos}


def _leer_zip(ruta):
    """{(votering_id, avser): votación} de la descarga masiva de un periodo de sesiones."""
    salida = {}
    with zipfile.ZipFile(ruta) as z:
        for info in z.infolist():
            m = re.match(r"(.+)-\d+-[0-9A-Fa-f-]{36}\.json$", info.filename)
            filas = _lista(json.loads(z.read(info).decode("utf-8-sig"))["dokvotering"].get("votering"))
            for f in filas:
                _anadir(salida, f, m.group(1) if m else None, (f.get("datum") or "")[:10] or None)
    return salida


def _anadir(salida, f, dok_id, fecha):
    clave = (f["votering_id"].upper(), f.get("avser") or "sakfrågan")
    v = salida.get(clave)
    if v is None:
        v = salida[clave] = {"id": clave[0], "avser": clave[1], "rm": f["rm"], "bet": f["beteckning"],
                             "punkt": str(f.get("punkt") or "0"), "dok_id": f.get("dok_id") or dok_id, "fecha": fecha,
                             "filas": {}}
    v["filas"][f["intressent_id"]] = (f.get("namn") or "", f.get("parti") or "-", f.get("rost"))


def _descarga(ctx, rm, abierto):
    nombre = f"votering-{rm.replace('/', '')}.json.zip"
    try:
        ruta = ctx.cache(f"{API}/dataset/votering/{nombre}", nombre, caduca_horas=20 if abierto else None, timeout=600)
    except urllib.error.HTTPError as e:
        if e.code == 404:  # periodo recién empezado: todavía no hay fichero
            return {}
        raise
    return _leer_zip(ruta)


def _meta(ctx, vid):
    try:
        return ctx.json(f"{API}/votering/{vid}/json")["votering"]["dokument"]
    except Exception as e:
        ctx.log(f"   ! votación {vid}: {type(e).__name__}: {e}")
        return None


def _beslutsdag(ctx, rm, bet):
    try:
        d = ctx.json(f"{API}/dokumentlista/?rm={quote(rm)}&doktyp=bet&bet={quote(bet)}&utformat=json&sz=5")["dokumentlista"]
    except Exception as e:
        ctx.log(f"   ! {rm}:{bet}: {type(e).__name__}: {e}")
        return None
    return next((x["beslutsdag"][:10] for x in _lista(d.get("dokument")) if x.get("beteckning") == bet and x.get("beslutsdag")), None)


def _votaciones_rm(ctx, rm, abierto):
    """Todas las votaciones de un periodo: la descarga masiva más lo que solo está en la API."""
    votaciones = _descarga(ctx, rm, abierto)
    try:
        lista = ctx.json(f"{API}/voteringlista/?rm={quote(rm)}&sz=10000&utformat=json&gruppering=votering_id")
        ids = {x["votering_id"].upper() for x in _lista(lista["voteringlista"].get("votering"))}
    except Exception as e:  # sin la lista de la API queda el fichero tal cual
        ctx.log(f"   ! {rm}: lista de votaciones de la API: {type(e).__name__}: {e}")
        ids = set()
    # El fichero trae también votaciones anuladas y repetidas (empates 145-145, registros de prueba con 5 votos) que
    # la API ya no lista: manda la lista de la API.
    anuladas = [clave for clave in votaciones if ids and clave[0] not in ids]
    for clave in anuladas:
        del votaciones[clave]
    if anuladas:
        ctx.log(f"   {rm}: {len(anuladas)} votaciones del fichero que la API no lista (anuladas), fuera")
    faltan = sorted(ids - {vid for vid, _ in votaciones})
    metas = {}
    if faltan:
        with ThreadPoolExecutor(4) as ex:
            metas = dict(zip(faltan, ex.map(lambda v: _meta(ctx, v), faltan)))
        por_bet = defaultdict(set)
        for vid, m in metas.items():
            if m:
                por_bet[m["beteckning"]].add(vid)
        for bet, vids in por_bet.items():
            filas = ctx.json(f"{API}/voteringlista/?rm={quote(rm)}&bet={quote(bet)}&punkt=&sz=10000&utformat=json&gruppering=")
            nuevas = {}
            for f in _lista(filas["voteringlista"].get("votering")):
                if f["votering_id"].upper() in vids:
                    _anadir(nuevas, f, f.get("dok_id"), None)
                    clave = (f["votering_id"].upper(), f.get("avser") or "sakfrågan")
                    sd = (f.get("systemdatum") or "")[:10]
                    if sd and (not nuevas[clave].get("sistema") or sd < nuevas[clave]["sistema"]):
                        nuevas[clave]["sistema"] = sd
            for v in nuevas.values():
                m = metas[v["id"]]
                sistema = v.pop("sistema", None)
                if m.get("typ") == "votering":  # las votaciones sin informe llevan su fecha
                    v["fecha"] = m["datum"][:10]
                elif sistema and f"{rm[:4]}-09-01" <= sistema <= f"{int(rm[:4]) + 1}-09-30":
                    v["fecha"] = sistema  # la del registro de la votación, si cae dentro del periodo
                else:  # registro rehecho años después: el día en que se decidió el informe
                    v["fecha"] = _beslutsdag(ctx, rm, v["bet"])
            votaciones.update(nuevas)
        ctx.log(f"   {rm}: {len(faltan)} votaciones solo en la API")
    # Las votaciones sin informe: título y fecha de su propia ficha.
    for v in votaciones.values():
        if ESPECIAL.fullmatch(v["bet"]):
            m = metas.get(v["id"]) or _meta(ctx, v["id"])
            if m:
                metas[v["id"]] = m
                v["titulo"] = re.sub(r"^Omröstning:\s*", "", m.get("titel") or "").strip()
                v["fecha"] = v["fecha"] or (m.get("datum") or "")[:10] or None
                v["dok_id"] = m.get("dok_id") or v["dok_id"]
    return votaciones


def _cuenta(filas):
    n = {"Ja": 0, "Nej": 0, "Avstår": 0, "Frånvarande": 0}
    for _, _, rost in filas.values():
        if rost in n:
            n[rost] += 1
    return n["Ja"], n["Nej"], n["Avstår"], n["Frånvarande"]


def _votos(ctx, filas):
    votos = []
    for iid, (nombre, parti, rost) in filas.items():
        if parti not in FUENTE.partidos:
            ctx.partido(parti)
        votos.append((f"swe:{iid}", nombre, parti, SENTIDO.get(rost, "no_vota")))
    return votos


def _norma(s):
    return re.sub(r"[\W_]+", "", s.lower())


def titulo_punto(informe, rubrik):
    """«Título del informe: epígrafe del punto», sin repetir lo que ya dice el uno en el otro."""
    if not rubrik:
        return informe
    a, b = _norma(informe), _norma(rubrik)
    if a and a in b:
        return rubrik
    if b in a and len(b) > len(a) / 2:
        return informe
    return f"{informe}: {rubrik}"


def construir(ctx, votaciones, informes):
    """Asuntos y votaciones del modelo a partir de las votaciones de la fuente y las fichas de los informes."""
    asuntos, salida = {}, []
    por_punto = defaultdict(list)
    for v in votaciones:
        por_punto[(v["rm"], v["bet"], v["punkt"])].append(v)
    for (rm, bet, punkt), grupo in por_punto.items():
        hay_sak = any(v["avser"] != "motivfrågan" for v in grupo)
        if ESPECIAL.fullmatch(bet):
            aid = f"swe:{rm}:{bet}"
            titulo = grupo[0].get("titulo") or f"Omröstning {rm}:{bet}"
            tipo_a, tipo_v, regla = especial(titulo)
            asuntos.setdefault(aid, Asunto(id=aid, titulo=titulo[:400], tipo=tipo_a, fecha=min(v["fecha"] for v in grupo),
                                           codigo=f"{rm}:{bet}", url=f"{API}/votering/{grupo[0]['id']}/html"))
            for v in grupo:
                si, no, abst, aus = _cuenta(v["filas"])
                res, mayoria = resultado_especial(regla, si, no)
                salida.append(Votacion(
                    id=f"swe:{v['id']}", fecha=v["fecha"], asunto_id=aid, camara=CAMARA, numero=1, texto=titulo[:500],
                    tipo=tipo_v, a_favor=si, en_contra=no, abstenciones=abst, no_votan=aus, mayoria=mayoria, resultado=res,
                    url=f"{API}/votering/{v['id']}/html", votos=_votos(ctx, v["filas"])))
            continue
        inf = informes.get(grupo[0]["dok_id"]) or {"titulo": "", "organ": None, "puntos": {}}
        p = inf["puntos"].get(punkt) or {}
        titulo_inf = inf["titulo"] or f"Betänkande {rm}:{bet}"
        rubrik = _texto_html(p.get("rubrik"))
        forslag = forslag_corto(p.get("forslag"))
        # Casi todos los puntos votados proponen rechazar mociones de la oposición: «aprobado» es entonces el rechazo,
        # y el título lo dice para que «Sanktioner mot Ryssland» aprobado no se lea como sanciones aprobadas.
        sufijo = ""
        m = re.match(r"(?:\S+ )?Riksdagen avslår (motion|propositionen|regeringens)", re.split(r"\bDärmed\b", forslag)[0])
        if m:
            sufijo = " (avslag på motioner)" if m.group(1) == "motion" else " (avslag på regeringens förslag)"
        titulo = titulo_punto(titulo_inf, rubrik)[:400 - len(sufijo)] + sufijo
        aid = f"swe:{rm}:{bet}:{punkt}"
        organ = inf.get("organ") or re.sub(r"\d+$", "", bet)
        asuntos.setdefault(aid, Asunto(
            id=aid, titulo=titulo, tipo=tipo_asunto(titulo_inf, rubrik, forslag), fecha=min(v["fecha"] for v in grupo),
            codigo=f"{rm}:{bet} p. {punkt}", autor=UTSKOTT.get(organ, organ),
            url=f"{WEB}/_{quote(grupo[0]['dok_id'])}/" if grupo[0]["dok_id"] else None,
            extra={"riksmote": rm, "betankande": bet, "punkt": punkt}))
        tablas = resumenes(p.get("votering_sammanfattning_html"))
        sak = [v for v in grupo if v["avser"] != "motivfrågan"]
        for v in grupo:
            si, no, abst, aus = _cuenta(v["filas"])
            # El rótulo de la tabla que corresponde a esta votación: por la cuestión votada y, si hay dos, por los totales.
            candidatas = [t for t in tablas if t[0] == v["avser"]] or [t for t in tablas if t[0] == "frågan"]
            tabla = next((t for t in candidatas if t[2] == (si, no, abst, aus)), candidatas[0] if len(candidatas) == 1 else None)
            rotulo = tabla[1] if tabla else f"Omröstning i {v['avser']}"
            texto = rotulo + (f". Förslag: {forslag}" if forslag else "")
            if v["avser"] == "motivfrågan":
                # Sobre la motivación, no sobre la decisión: enmienda si el punto tiene también la votación de fondo.
                tipo_v = "enmienda" if hay_sak else "otra"
            else:
                tipo_v = "final"
            # Sí = propuesta de la comisión. En la votación de fondo manda el vencedor que publica el Riksdag
            # («utskottet», «reservation 3», «Avslagen»...), que tiene en cuenta las mayorías especiales (5/6 para
            # declarar «vilande» una ley, 3/4 en el reglamento de la cámara).
            res = "aprobada" if si > no else "rechazada"
            vinnare = (p.get("vinnare") or "").strip().lower()
            regla = "särskild beslutsregel" in rotulo.lower()
            if vinnare and v["avser"] != "motivfrågan" and (len(sak) == 1 or regla or v["id"] == (p.get("votering_id") or "").upper()):
                res = "aprobada" if vinnare in ("utskottet", "bifall", "bifallen") else "rechazada"
            mayoria = p.get("voteringskrav") or ("Särskild beslutsregel" if regla else None)
            if p.get("beslutsregelkvot"):
                mayoria = f"{mayoria or ''} {p['beslutsregelkvot']}".strip()
            salida.append(Votacion(
                id=f"swe:{v['id']}" + (":motiv" if v["avser"] == "motivfrågan" else ""), fecha=v["fecha"], asunto_id=aid,
                camara=CAMARA, numero=int(punkt) if punkt.isdigit() else None, texto=texto[:500], tipo=tipo_v,
                a_favor=si, en_contra=no, abstenciones=abst, no_votan=aus, mayoria=mayoria, resultado=res,
                url=f"{API}/votering/{v['id']}/html", votos=_votos(ctx, v["filas"])))
    return asuntos, salida


def recoger(ctx):
    hoy = date.today()
    cerrados = set(ctx.marca("cerrados", []))
    inicio = f"{ctx.desde}-01-01"
    for rm in riksmoten(ctx.desde, hoy):
        # Un periodo acaba en septiembre; hasta noviembre puede recibir alguna corrección.
        cerrado = hoy > date(int(rm[:4]) + 1, 10, 31)
        if cerrado and rm in cerrados and not ctx.completo:
            continue
        desde = inicio
        if not ctx.completo:
            ultima = ctx.con.execute("SELECT MAX(fecha) FROM votacion WHERE fuente='swe' AND asunto_id LIKE ?",
                                     (f"swe:{rm}:%",)).fetchone()[0]
            if ultima:  # se repasan dos semanas por si llega tarde alguna votación
                desde = max(inicio, (date.fromisoformat(ultima) - timedelta(days=14)).isoformat())
        todas = _votaciones_rm(ctx, rm, not cerrado)
        sin_fecha = [v["id"] for v in todas.values() if not v["fecha"]]
        if sin_fecha:
            ctx.log(f"   ! {rm}: {len(sin_fecha)} votaciones sin fecha: {sin_fecha[:3]}")
        nuevas = sorted((v for v in todas.values() if v["fecha"] and v["fecha"] >= desde),
                        key=lambda v: (v["fecha"], v["bet"], int(v["punkt"]) if v["punkt"].isdigit() else 0))
        ctx.log(f"   {rm}: {len(nuevas)} votaciones desde {desde} (de {len(todas)})")
        dok_ids = sorted({v["dok_id"] for v in nuevas if v["dok_id"] and not ESPECIAL.fullmatch(v["bet"])})
        with ThreadPoolExecutor(6) as ex:
            informes = dict(zip(dok_ids, ex.map(lambda d: _forslag(ctx, d, not cerrado), dok_ids)))
        informes = {k: v for k, v in informes.items() if v}
        # Lotes de unos cientos de votaciones, por fecha y sin partir un punto.
        puntos = defaultdict(list)
        for v in nuevas:
            puntos[(v["rm"], v["bet"], v["punkt"])].append(v)
        lote = []
        for grupo in puntos.values():
            lote += grupo
            if len(lote) >= LOTE:
                asuntos, votaciones = construir(ctx, lote, informes)
                ctx.guardar(list(asuntos.values()), votaciones)
                lote = []
        if lote:
            asuntos, votaciones = construir(ctx, lote, informes)
            ctx.guardar(list(asuntos.values()), votaciones)
        if cerrado:
            cerrados.add(rm)
            ctx.poner_marca("cerrados", sorted(cerrados))
