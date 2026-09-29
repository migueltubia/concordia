"""Alemania: votaciones nominales del Bundestag (namentliche Abstimmungen).

En el Bundestag casi todo se vota a mano alzada o levantándose, sin registro de quién vota qué. Solo las
votaciones nominales (unas 50 al año, las que pide un grupo) dejan el voto de cada diputado, y son justo
las importantes: misiones de la Bundeswehr en el extranjero, ayuda militar a Ucrania, reformas de la Ley
Fundamental, presupuestos, leyes discutidas... Se juntan dos fuentes:

- La lista oficial del Bundestag (https://www.bundestag.de/parlament/plenum/abstimmung/liste): todas las
  votaciones nominales, cada una con un XLSX con el voto de cada diputado y su grupo (legislatura, sesión y
  número de votación). Antes de mediados de 2019 el fichero es XLS binario, que no se lee. El título es
  corto («Erster Entschließungsantrag der Linken zur GKV-Finanzreform») y no da el documento (Drucksache).
- abgeordnetenwatch.de (API v2, CC0), proyecto cívico que documenta unas 4 de cada 5 de esas votaciones
  con un título claro, un resumen, los documentos y el voto de cada diputado con un id estable. Admite 30
  peticiones por minuto por IP.

Cada votación oficial se empareja con la de abgeordnetenwatch del mismo día (±2) con el mismo recuento. Si
casan, el asunto (título, resumen, documentos) y los votos con el id de cada diputado salen de
abgeordnetenwatch, y la votación lleva el id oficial (legislatura:sesión:número), su título oficial como texto
y el enlace al PDF oficial del resultado. Las que solo están en la lista oficial (sobre todo mociones de
acompañamiento, «Entschließungsanträge», y enmiendas) se juntan al asunto de otra votación de la misma sesión
sobre el mismo proyecto, y sus diputados se identifican por el nombre; las que solo están en
abgeordnetenwatch (las de enero a junio de 2019) se toman de allí. Lo que una fuente tiene y la otra todavía
no se espera dos semanas antes de guardarlo solo con una.

Sobre las mociones (Anträge) se vota la recomendación de la comisión (Beschlussempfehlung), casi siempre de
rechazo: votar «Ja» es rechazar la moción. Se guarda así, como en el acta, y el título lo dice («Ablehnung
des Antrags…», «Keine…»). Hasta 2022 abgeordnetenwatch daba la vuelta a esos votos (sí = apoyar la moción);
se detectan porque casan con el sí y el no cambiados y se guardan como en el acta.

El voto por grupo de las demás votaciones (a mano alzada) solo consta en texto libre en el diario de
sesiones («mit den Stimmen der Koalitionsfraktionen gegen die Stimmen der AfD…») y en DIP como nota sin
estructura, así que no se recoge.
"""

import html
import re
import threading
import time
import unicodedata
import zipfile
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from .modelo import Asunto, Fuente, Votacion

FUENTE = Fuente(
    codigo="deu", pais="DEU", nombre="Bundestag de Alemania", corto="Alemania", tipo="parlamento",
    detalle="nominal", web="https://www.bundestag.de", desde=2019, idioma="otro",
    licencia="Bundestag: uso libre con cita de la fuente; abgeordnetenwatch.de: CC0 1.0",
    camaras={"deu-bt": ("Bundestag", "Bundestag", 630)},
    partidos={
        "CDU/CSU": ("Unión Demócrata Cristiana / Unión Social Cristiana", "CDU/CSU", "#2d2d2d"),
        "SPD": ("Partido Socialdemócrata de Alemania", "SPD", "#e3000f"),
        "AfD": ("Alternativa para Alemania", "AfD", "#009ee0"),
        "FDP": ("Partido Democrático Libre", "FDP", "#f5c400"),
        "GRÜNE": ("Alianza 90/Los Verdes", "Verdes", "#46962b"),
        "LINKE": ("La Izquierda", "Linke", "#be3075"),
        "BSW": ("Alianza Sahra Wagenknecht", "BSW", "#7d254f"),
        "fraktionslos": ("No adscritos", "No adscr.", "#898781"),
    },
    notas=("Solo las votaciones nominales (namentliche Abstimmungen), unas 50 al año; lo que se vota a mano "
           "alzada no tiene registro de voto."),
)

LISTA = "https://www.bundestag.de/parlament/plenum/abstimmung/liste"
LISTA_AJAX = "https://www.bundestag.de/ajax/filterlist/de/parlament/plenum/abstimmung/liste/462112-462112"
AW = "https://www.abgeordnetenwatch.de/api/v2"
# Legislatura (Wahlperiode) -> id del periodo en abgeordnetenwatch, inicio. Las nuevas se buscan solas.
LEGISLATURAS = {19: (111, "2017-10-24"), 20: (132, "2021-10-26"), 21: (161, "2025-03-25")}
MARGEN = 30    # días que se vuelven a leer en cada recogida
ESPERA = 14    # días que se espera a la otra fuente antes de guardar una votación que solo está en una
VENTANA = 2    # días de diferencia admitidos al emparejar (sesiones que pasan de medianoche)

MESES = {m: i for i, m in enumerate(("januar", "februar", "märz", "april", "mai", "juni", "juli", "august",
                                     "september", "oktober", "november", "dezember"), 1)}
SENTIDO_AW = {"yes": "si", "no": "no", "abstain": "abstencion", "no_show": "no_vota"}
ORDINALES = ("erste", "zweite", "dritte", "vierte", "fünfte", "sechste", "siebte", "achte", "neunte", "zehnte")


# ------------------------------------------------------------------ abgeordnetenwatch (30 peticiones/minuto)

class _Ritmo:
    """Espacia las peticiones: una cada `intervalo` segundos como mucho, con varios hilos."""

    def __init__(self, intervalo):
        self.intervalo = intervalo
        self.proxima = 0.0
        self.cerrojo = threading.Lock()

    def esperar(self):
        with self.cerrojo:
            ahora = time.monotonic()
            espera = self.proxima - ahora
            self.proxima = max(ahora, self.proxima) + self.intervalo
        if espera > 0:
            time.sleep(espera)


_RITMO = _Ritmo(2.1)


def _aw(ctx, ruta):
    for intento in range(3):
        _RITMO.esperar()
        try:
            d = ctx.json(f"{AW}/{ruta}")
        except RuntimeError as e:  # 429 tras los reintentos de http_util: se para un minuto
            if "429" not in str(e) or intento == 2:
                raise
            time.sleep(60)
            continue
        if (d.get("meta") or {}).get("status") != "ok":
            raise RuntimeError(f"abgeordnetenwatch {ruta}: {(d.get('meta') or {}).get('status_message')}")
        return d["data"]


def _aw_todo(ctx, ruta):
    """Todas las páginas de un listado (1.000 por petición como mucho)."""
    datos, inicio = [], 0
    while True:
        pagina = _aw(ctx, f"{ruta}&range_start={inicio}&range_end=1000")
        datos += pagina
        if len(pagina) < 1000:
            return datos
        inicio += 1000


def legislaturas(ctx):
    """{legislatura: (id del periodo en abgeordnetenwatch, inicio)}, con las que abgeordnetenwatch añada."""
    legs = dict(LEGISLATURAS)
    try:
        periodos = _aw(ctx, "parliament-periods?parliament=5&type=legislature&range_end=100")
    except Exception as e:
        ctx.log(f"   ! no se pudieron leer las legislaturas de abgeordnetenwatch: {e}")
        return legs
    conocidos = {p for p, _ in legs.values()}
    for p in sorted(periodos, key=lambda p: p.get("start_date_period") or ""):
        inicio = p.get("start_date_period")
        if p["id"] not in conocidos and inicio and inicio > max(i for _, i in legs.values()):
            legs[max(legs) + 1] = (p["id"], inicio)
    return legs


def _texto(h):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", h or ""))).replace("\xad", "").strip()


def _limpio(t):
    return re.sub(r"\s+", " ", (t or "").replace("\xad", "")).strip(" .")


def _fraccion(etiqueta):
    """«BÜNDNIS 90/­DIE GRÜNEN (Bundestag 2021 - 2025)», «BÜ90/GR», «DIE LINKE.» -> código estable."""
    t = re.sub(r"\s*\(Bundestag.*$", "", (etiqueta or "").replace("\xad", "")).strip().lower()
    if not t or "fraktionslos" in t or t in ("parteilos", "unabhängig"):
        return "fraktionslos"
    if "cdu" in t or "csu" in t:
        return "CDU/CSU"
    if "grün" in t or "bü90" in t or "bündnis" in t:
        return "GRÜNE"
    if "linke" in t:
        return "LINKE"
    if "wagenknecht" in t or t.startswith("bsw"):
        return "BSW"
    for p in ("SPD", "AfD", "FDP"):
        if p.lower() == t:
            return p
    return t


def _poll(p, wp):
    intro = p.get("field_intro") or ""
    enlaces = re.findall(r'href="([^"]+)"', intro)
    drucksachen = []
    for m in re.finditer(r"bundestag\.de/(?:dip21/)?btd/(\d+)/\d+/(\d+)\.pdf", intro):
        ds = f"{m.group(1)}/{int(m.group(2)[len(m.group(1)):])}"
        if ds not in drucksachen:
            drucksachen.append(ds)
    padres = [re.sub(r"[?#].*$", "", e).rstrip("/") for e in enlaces
              if re.search(r"abgeordnetenwatch\.de/bundestag/\d+/abstimmungen/", e)]
    resumen = _texto(intro)
    return {"id": p["id"], "wp": wp, "fecha": p["field_poll_date"], "titulo": _limpio(p["label"]),
            "url": p.get("abgeordnetenwatch_url"), "aceptada": p.get("field_accepted"), "resumen": resumen,
            "drucksachen": drucksachen, "padres": padres,
            "temas": [t["label"] for t in p.get("field_topics") or [] if t.get("label")]}


def _votos_aw(ctx, poll, politico):
    datos = _aw(ctx, f"votes?poll={poll['id']}&range_end=1000")
    votos = []
    for v in datos:
        mandato = (v.get("mandate") or {})
        pid, nombre = politico.get(mandato.get("id"), (None, None))
        if not nombre:
            nombre = re.sub(r"\s*\(Bundestag.*$", "", mandato.get("label") or "").strip()
        mid = f"deu:{pid}" if pid else f"deu:m{mandato.get('id')}"
        votos.append((mid, nombre, _fraccion((v.get("fraction") or {}).get("label")),
                      SENTIDO_AW.get(v.get("vote"), "no_vota")))
    return votos


# ------------------------------------------------------------------ lista oficial y XLSX por votación

def _fecha_lista(t):
    m = re.match(r"(\d{1,2})\.\s*([A-Za-zäÄ]+)\s+(\d{4})", (t or "").strip())
    if not m or m.group(2).lower() not in MESES:
        return None
    return f"{m.group(3)}-{MESES[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"


def fecha_y_titulo(fecha_lista, titulo):
    """El título suele empezar por la fecha de la votación («18.11.2020: …»), más fiable que la de la lista
    (que a veces es la de publicación), salvo erratas («08.05.20626: …»)."""
    fecha = _fecha_lista(fecha_lista)
    m = re.match(r"(\d{2})\.(\d{2})\.(\d+):?\s*", titulo or "")
    if m:
        titulo = titulo[m.end():]
        try:
            del_titulo = date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
        except ValueError:
            del_titulo = None
        if del_titulo and (not fecha or abs((date.fromisoformat(del_titulo) - date.fromisoformat(fecha)).days) <= 7):
            fecha = del_titulo
    return fecha, _limpio(titulo)


def lista_oficial(ctx, desde):
    """Votaciones nominales de la lista oficial desde una fecha: [{fecha, titulo, pdf, xlsx}], de la más nueva a
    la más vieja. Cada fila da la fecha, el título y los enlaces al PDF y al XLSX con el resultado."""
    ajax = LISTA_AJAX
    try:
        m = re.search(r"ajax/filterlist/de/parlament/plenum/abstimmung/liste/[\d-]+", ctx.fetch(LISTA).decode("utf-8", "replace"))
        if m:
            ajax = "https://www.bundestag.de/" + m.group(0)
    except Exception:
        pass
    salida, offset = [], 0
    while True:
        t = ctx.fetch(f"{ajax}?limit=30&noFilterSet=true&offset={offset}").decode("utf-8", "replace")
        filas = re.findall(r"<tr class=\"e-table__row.*?</tr>", t, re.S)
        for f in filas:
            celdas = re.findall(r"<td[^>]*>(.*?)</td>", f, re.S)
            enlaces = re.findall(r'href="([^"]+)"', f)
            a = re.search(r"<a [^>]*>(.*?)</a>", celdas[2] if len(celdas) > 2 else f, re.S)
            titulo = _texto(re.sub(r"<svg.*?</svg>", " ", a.group(1), flags=re.S)) if a else ""
            fecha, titulo = fecha_y_titulo(_texto(celdas[0]) if celdas else "", titulo)
            if not fecha:
                continue
            salida.append({"fecha": fecha, "titulo": titulo,
                           "pdf": next((e for e in enlaces if e.lower().endswith(".pdf")), None),
                           "xlsx": next((e for e in enlaces if re.search(r"\.xlsx?$", e, re.I)), None)})
        if len(filas) < 30 or (salida and max(s["fecha"] for s in salida[-len(filas):]) < desde):
            return [s for s in salida if s["fecha"] >= desde]
        offset += 30


def _hoja(ruta):
    """Primera hoja de un XLSX como lista de diccionarios {cabecera: valor} (solo biblioteca estándar)."""
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    with zipfile.ZipFile(ruta) as z:
        comunes = []
        if "xl/sharedStrings.xml" in z.namelist():
            comunes = ["".join(t.text or "" for t in si.iter(ns + "t"))
                       for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(ns + "si")]
        hoja = sorted(n for n in z.namelist() if n.startswith("xl/worksheets/sheet"))[0]
        filas = []
        for row in ET.fromstring(z.read(hoja)).iter(ns + "row"):
            fila = {}
            for c in row.iter(ns + "c"):
                col = re.match(r"[A-Z]+", c.get("r") or "")
                v = c.find(ns + "v")
                if c.get("t") == "s" and v is not None:
                    valor = comunes[int(v.text)]
                elif c.get("t") == "inlineStr":
                    valor = "".join(t.text or "" for t in c.iter(ns + "t"))
                else:
                    valor = v.text if v is not None else None
                if col:
                    fila[col.group(0)] = valor
            filas.append(fila)
    if not filas:
        return []
    cab = {k: (v or "").strip().lower() for k, v in filas[0].items()}
    return [{cab[k]: v for k, v in f.items() if k in cab} for f in filas[1:] if f]


def _n(x):
    try:
        return int(float(x or 0))
    except ValueError:
        return 0


FALLO = "fallo"


def _oficial(ctx, o):
    """Lee el XLSX de una votación oficial: legislatura, sesión, número y voto de cada diputado.

    None si no hay XLSX (los XLS binarios de antes de mediados de 2019 no se leen); FALLO si no se pudo
    descargar o leer (la web a veces responde con una redirección que acaba en error 400 si se le piden
    muchos a la vez)."""
    if not o["xlsx"] or not o["xlsx"].lower().endswith(".xlsx"):
        return None
    blob = re.search(r"/blob/(\d+)/", o["xlsx"])
    nombre = f"{blob.group(1) if blob else ''}_{o['xlsx'].rsplit('/', 1)[-1]}"
    for intento in range(3):
        ruta = None
        try:
            ruta = ctx.cache(o["xlsx"], nombre)
            filas = _hoja(ruta)
            break
        except Exception as e:
            if ruta is not None and isinstance(e, zipfile.BadZipFile):
                ruta.unlink(missing_ok=True)  # fichero en caché roto: se vuelve a descargar
            if intento == 2:
                ctx.log(f"   ! {o['fecha']} {o['titulo'][:60]}: no se pudo leer {o['xlsx']}: {e}")
                return FALLO
            time.sleep(5 + 15 * intento)
    filas = [f for f in filas if f.get("wahlperiode") and f.get("name")]
    if not filas:
        return FALLO
    diputados = []
    for f in filas:
        if _n(f.get("ja")):
            s = "si"
        elif _n(f.get("nein")):
            s = "no"
        elif _n(f.get("enthaltung")):
            s = "abstencion"
        else:  # no ha votado o voto no válido
            s = "no_vota"
        nombre = _limpio(f.get("bezeichnung") or f"{f.get('vorname') or ''} {f.get('name') or ''}")
        diputados.append({"nombre": nombre, "vorname": f.get("vorname") or "", "apellido": f.get("name") or "",
                          "partido": _fraccion(f.get("fraktion/gruppe")), "sentido": s})
    wp, sesion, numero = _n(filas[0]["wahlperiode"]), _n(filas[0].get("sitzungnr")), _n(filas[0].get("abstimmnr"))
    return {**o, "wp": wp, "sesion": sesion, "numero": numero, "id": f"deu:{wp}:{sesion}:{numero}",
            "blob": blob.group(1) if blob else nombre, "diputados": diputados}


def _ids_unicos(oficiales):
    """Legislatura, sesión y número identifican la votación, pero hay XLSX con el número repetido (el del
    30-1-2025 sobre Aspides dice 2, como el de Unmiss): la segunda lleva además el id del fichero."""
    vistos = set()
    for o in sorted(oficiales, key=lambda o: (o["id"], int(o["blob"]) if str(o["blob"]).isdigit() else 0)):
        if o["id"] in vistos:
            o["id"] = f"{o['id']}-{o['blob']}"
        vistos.add(o["id"])


# ------------------------------------------------------------------ nombres de diputados

def _clave(t, numeros=False):
    """Texto sin tildes, títulos académicos ni signos, para comparar nombres y títulos."""
    t = unicodedata.normalize("NFKD", (t or "").replace("ß", "ss")).encode("ascii", "ignore").decode().lower()
    if numeros:
        return " ".join(re.findall(r"[a-z0-9]+", t))
    t = re.sub(r"\b(dr|prof|h\s*c|ing|med|phil|rer|nat|pol|jur|habil|dipl|oec|mult)\b\.?", " ", t)
    return " ".join(re.findall(r"[a-z]+", t))


class Diputados:
    """Identifica por el nombre a los diputados de las votaciones que solo están en la lista oficial."""

    PARTICULAS = {"von", "van", "der", "de", "dos", "zu", "den", "del"}

    def __init__(self, mandatos):
        self.politico = {}          # id de mandato -> (id de político, nombre)
        self.por_nombre = {}
        self.nombres = []           # (id de político, primer nombre, palabras del nombre)
        for m in mandatos:
            pol = m.get("politician") or {}
            if not pol.get("id"):
                continue
            nombre = _limpio(pol.get("label"))
            self.politico[m["id"]] = (pol["id"], nombre)
            clave = _clave(nombre)
            self.por_nombre.setdefault(clave, pol["id"])
            if clave:
                self.nombres.append((pol["id"], clave.split()[0], set(clave.split())))

    def id(self, d):
        # «Michael Brand (Fulda)»: la lista oficial distingue a los homónimos con la circunscripción.
        for n in (re.sub(r"\(.*?\)", " ", d["nombre"]), f"{d['vorname']} {d['apellido']}"):
            pid = self.por_nombre.get(_clave(n))
            if pid:
                return pid
        # Apellidos de casada y nombres abreviados: «Isabel Mackensen» / «Isabel Mackensen-Geis», «Ingeborg
        # Gräßle» / «Inge Gräßle», «Axel E. Fischer» / «Axel Eduard Fischer»: comparte un apellido y el primer
        # nombre de uno empieza como el del otro, y no hay otro igual.
        apellidos = set(_clave(d["apellido"]).split()) - self.PARTICULAS
        nombre = (_clave(d["vorname"]).split() or [""])[0]
        if not apellidos or len(nombre) < 3:
            return None
        candidatos = {p for p, n, palabras in self.nombres
                      if apellidos & palabras and (n.startswith(nombre) or nombre.startswith(n))}
        return candidatos.pop() if len(candidatos) == 1 else None


# ------------------------------------------------------------------ tipos

MISION = re.compile(r"\beunavfor|\bkfor\b|\bunifil\b|\bminusma\b|\bunmiss\b|\batalanta\b|sea guardian|"
                    r"\bresolute support\b|\beutm\b|\beumpm\b|\birini\b|counter daesh|\bunamid\b|\baspides\b|"
                    r"\beufor\b|\balthea\b", re.I)
MANDATO = re.compile(r"bundeswehr|streitkräfte", re.I)
TRATADO = re.compile(r"abkommen|übereinkommen|vertragsgesetz|\bvertrag(es|s)?\b|ratifi|zusatzprotokoll|"
                     r"\bprotokoll(s)? (zu|über|vom)|beitritt .{0,40}\bnato\b|nato-beitritt|staatsvertrag", re.I)
ENMIENDA = re.compile(r"entschließungsantr|entschl\.?\s?antr|änderungsantr|änd\.?\s?antr", re.I)
# Título de una moción: «AfD-Antrag: …», «Antrag der FDP …», «Ablehnung eines Antrags …», «(Beschlussempfehlung)».
ANTRAG = re.compile(r"^((afd|cdu/csu|spd|fdp|grünen?|die linke|linke|bsw)[- ])?antrag\b|ablehnung (des|eines) antrag|"
                    r"\(antrag\b|beschlussempfehlung|\bbeschlempf|entschließungsantr", re.I)


# Moción de un grupo sobre una misión o un tratado («Bundeswehreinsatz in Mali beenden», «AfD-Antrag…»),
# no el mandato o el tratado que presenta el Gobierno.
MOCION_GRUPO = re.compile(r"^(afd|cdu/csu|spd|fdp|grünen?|die linke|linken|linke|bsw)[- ]antrag|"
                          r"antrag (der )?(fraktion|afd|cdu|fdp|linke|grüne|bsw)|ablehnung (des|eines) antrag|"
                          r"\((antrag|entschließungsantrag) (der )?(afd|cdu|fdp|linke|grüne|bsw)|\bbeenden\b|\babziehen\b|"
                          r"\bkeine?\b|entschließungsantr", re.I)


def tipo_asunto(titulo, texto, resumen):
    """ley, tratado, resolución (misiones de la Bundeswehr), moción, nombramiento o procedimiento."""
    t = f"{titulo} · {texto}"
    # Lo primero que dice el resumen de abgeordnetenwatch: «Der Gesetzentwurf…» o «Mit ihrem Antrag…».
    primero = re.search(r"gesetz\w*entw\w*|gesetz\b|verordnung|haushalt|entschließungsantrag|\bantrag\b",
                        (resumen or "")[:500], re.I)
    antrag_resumen = bool(primero and "antrag" in primero.group(0).lower())
    es_antrag = bool(ANTRAG.search(titulo) or (ANTRAG.search(texto) and not re.search(r"gesetz|haushalt|verordnung",
                                                                                     titulo, re.I))
                     or (antrag_resumen and not re.search(r"gesetz|haushalt|verordnung", t, re.I)))
    if re.search(r"vertrauensfrage|artikel 68 des grundgesetzes|kanzlerwahl|wahl des bundeskanzlers", t, re.I):
        return "nombramiento"
    if (MISION.search(t) or (MANDATO.search(t) and re.search(r"einsatz|beteiligung|mission|operation|mandat|"
                                                           r"fortsetzung|verlängerung|evakuierung", t, re.I))) \
            and not MOCION_GRUPO.search(t):
        return "resolucion"
    if not es_antrag and (TRATADO.search(t) or re.search(r"vertragsgesetz|ratifizier|zustimmungsgesetz",
                                                         (resumen or "")[:300], re.I)):
        return "tratado"
    if re.search(r"untersuchungsausschuss|geschäftsordnung|einsprüche|wahlprüfung|wahlwiederholung|tagesordnung", t, re.I):
        return "procedimiento"
    if es_antrag:
        return "mocion"
    if re.search(r"gesetz|haushalt|verordnung|\betat\b|einzelplan|artikel \d", t, re.I):
        return "ley"
    if primero:
        return "mocion" if antrag_resumen else "ley"
    return "otro"


def tipo_votacion(texto):
    t = (texto or "").lower()
    if ENMIENDA.search(t):
        return "enmienda"
    if re.search(r"vertrauensfrage|artikel 68 des grundgesetzes", t):
        return "nombramiento"
    if re.search(r"geschäftsordnung|tagesordnung|absetzung|vertagung|überweisung|unterbrechung", t):
        return "procedimiento"
    # Votación separada de unos artículos («Artikel 5 des Entwurfs…», «Tankrabatt (Art. 11, 12…)»), no el
    # proyecto que cambia unos artículos de la Ley Fundamental («Änderung der Artikel 109, 115…»).
    if re.search(r"^(artikel|art\.)\s*\d|\(2\. (beratung|lesung)\)|zweite (beratung|lesung)", t) or \
            (re.search(r"\((artikel|art\.)\s*\d", t) and "änderung" not in t):
        return "parcial"
    return "final"


def _clave_tema(titulo):
    """Lo que identifica el proyecto en un título oficial, para juntar las votaciones de una misma sesión:
    «Zweiter Entschließungsantrag zur „Verbesserung der inneren Sicherheit“» -> «verbesserung der inneren
    sicherheit»; «Bevölkerungsschutzgesetz - Änderungsantrag (19/28760)» -> «bevolkerungsschutzgesetz»."""
    t = titulo or ""
    m = re.search(r"[„\"“]([^“”\"]{6,})[“”\"]", t)
    if m:
        return _clave(m.group(1), True)
    t = re.sub(r"\([^)]*\)", " ", t)
    t = re.sub(r"(?i)\b(erste[rn]?|zweite[rn]?|dritte[rn]?|vierte[rn]?|fünfte[rn]?|sechste[rn]?)\b", " ", t)
    t = re.sub(r"(?i)\b(entschließungsantrag|änderungsantrag|gesetzentwurf|beschlussempfehlung|antrag|ablehnung|"
               r"artikel \d+\w*|des entwurfs|der bundesregierung|breg|der koalition|der fraktion(en)?|"
               r"der (cdu/csu|spd|afd|fdp|grünen|linken|bsw)|(cdu/csu|spd|afd|fdp|linke|grüne)|"
               r"zu[rm]?|des|eines|einer|zweite beratung|dritte beratung)\b", " ", t)
    partes = [p for p in re.split(r"\s[-–]\s|,|:", t) if _clave(p, True)]
    return _clave(max(partes, key=lambda p: len(_clave(p, True))), True) if partes else ""


def _parecido(a, b):
    pa, pb = set(_clave(a).split()), set(_clave(b).split())
    return len(pa & pb) / max(1, len(pa | pb))


def _ordinal(t):
    t = (t or "").lower()
    return next((i for i, o in enumerate(ORDINALES) if re.search(rf"\b{o}[rn]?\b", t)), None)


def _drucksache_url(ds):
    wp, n = ds.split("/")
    n = f"{int(n):05d}"
    return f"https://dserver.bundestag.de/btd/{wp}/{n[:3]}/{wp}{n}.pdf"


def _frase(resumen, largo=300):
    if not resumen:
        return None
    t = resumen[:largo + 100]
    corte = [m.end() for m in re.finditer(r"[.!?](\s|$)", t) if m.end() <= largo]
    return (t[:corte[-1]] if corte else t[:largo]).strip()


# ------------------------------------------------------------------ emparejar y construir

def emparejar(oficiales, polls):
    """Empareja votaciones oficiales y de abgeordnetenwatch por fecha (±VENTANA días) y recuento.

    Devuelve {índice oficial: índice poll}. Con recuentos iguales (varias mociones de un mismo grupo en la
    misma sesión) desempata el parecido del título y el ordinal («Zweiter Entschließungsantrag…»).

    Hasta 2022, en las mociones que se votan por la recomendación de rechazo de la comisión, abgeordnetenwatch
    da la vuelta a los votos para que «sí» sea apoyar la moción: casan con el sí y el no cambiados, y se
    marcan con p["invertida"].
    """
    candidatos = []
    for i, o in enumerate(oficiales):
        c_o = [sum(1 for d in o["diputados"] if d["sentido"] == s) for s in ("si", "no", "abstencion")]
        for j, p in enumerate(polls):
            dias = abs((date.fromisoformat(o["fecha"]) - date.fromisoformat(p["fecha"])).days)
            if dias > VENTANA:
                continue
            c_p = [sum(1 for v in p["votos"] if v[3] == s) for s in ("si", "no", "abstencion")]
            dif = sum(abs(a - b) for a, b in zip(c_o, c_p))
            if re.search(r"antrag", f"{p['titulo']} {p['resumen'][:600]}", re.I):
                inv = abs(c_o[0] - c_p[1]) + abs(c_o[1] - c_p[0]) + abs(c_o[2] - c_p[2])
            else:
                inv = dif + 1
            if min(dif, inv) > max(4, sum(c_o) // 50):
                continue
            ordinal = 0 if _ordinal(o["titulo"]) == _ordinal(p["titulo"]) else 1
            candidatos.append((min(dif, inv), inv < dif, ordinal, -_parecido(o["titulo"], p["titulo"]), dias, i, j))
    pares, usados_o, usados_p = {}, set(), set()
    for p in polls:
        p["invertida"] = False
    for _, invertida, *_, i, j in sorted(candidatos):
        if i not in usados_o and j not in usados_p:
            pares[i] = j
            polls[j]["invertida"] = invertida
            usados_o.add(i)
            usados_p.add(j)
    return pares


def construir(oficiales, polls, pares, diputados, vecinos=()):
    """Asuntos y votaciones de un tramo (una semana de sesiones más o menos). `vecinos`: todas las votaciones
    de abgeordnetenwatch del tramo, también las que esperan, para juntar mociones con su proyecto."""
    asuntos, votaciones = {}, []
    por_url = {p["url"].rstrip("/"): p for p in list(vecinos) + list(polls) if p.get("url")}
    asunto_poll = {}

    def asunto_de_poll(p):
        if p["id"] in asunto_poll:
            return asunto_poll[p["id"]]
        # Mociones y enmiendas que abgeordnetenwatch enlaza a la votación del proyecto: el mismo asunto.
        if re.search(r"entschließungsantrag|änderungsantrag", f"{p['titulo']} {p['resumen'][:300]}", re.I):
            for u in p["padres"]:
                padre = por_url.get(u)
                if padre and padre["id"] != p["id"] and not re.search(r"entschließungsantrag|änderungsantrag",
                                                                    padre["titulo"], re.I):
                    asunto_poll[p["id"]] = asunto_de_poll(padre)
                    return asunto_poll[p["id"]]
        aid = f"deu:aw{p['id']}"
        o = next((oficiales[i] for i, j in pares.items() if polls[j] is p), None)
        texto = o["titulo"] if o else ""
        titulo, tipo = p["titulo"], tipo_asunto(p["titulo"], texto, p["resumen"])
        if p.get("invertida"):
            # Se guarda lo que se votó de verdad (la recomendación de rechazo): el título lo dice.
            titulo = f"Ablehnung: {titulo}" if re.search(r"antrag", titulo, re.I) else f"Ablehnung des Antrags: {titulo}"
            tipo = "mocion"
        extra = {"legislatura": p["wp"], "abgeordnetenwatch": p["id"], "etiqueta": _frase(p["resumen"]),
                 "drucksachen": p["drucksachen"] or None, "temas_abgeordnetenwatch": p["temas"] or None}
        asuntos[aid] = Asunto(
            id=aid, titulo=titulo[:400], tipo=tipo, fecha=p["fecha"],
            codigo=f"Drucksache {p['drucksachen'][0]}" if p["drucksachen"] else None, url=p["url"],
            extra={k: v for k, v in extra.items() if v})
        asunto_poll[p["id"]] = aid
        return aid

    # 1) Votaciones oficiales emparejadas y votaciones solo de abgeordnetenwatch
    asunto_oficial = {}
    for i, o in enumerate(oficiales):
        if i in pares:
            asunto_oficial[i] = asunto_de_poll(polls[pares[i]])
    emparejados = set(pares.values())
    for j, p in enumerate(polls):
        if j not in emparejados:
            asunto_de_poll(p)

    # 2) Votaciones solo oficiales: con otra de la misma sesión sobre el mismo proyecto, o un asunto propio
    for i, o in sorted(enumerate(oficiales), key=lambda x: (x[1]["wp"], x[1]["sesion"], x[1]["numero"])):
        if i in asunto_oficial:
            continue
        # Solo se juntan con el proyecto las enmiendas, mociones de acompañamiento y votaciones por artículos; otro
        # proyecto o moción sobre lo mismo («Gesetzentwurf der FDP: Abschaffung des Solidaritätszuschlags» junto
        # al del Gobierno) es otro asunto.
        clave = _clave_tema(o["titulo"]) if tipo_votacion(o["titulo"]) != "final" else ""
        hermanas = [k for k, x in enumerate(oficiales) if k != i and k in asunto_oficial
                    and (x["wp"], x["sesion"]) == (o["wp"], o["sesion"]) and clave and len(clave) >= 6
                    and (_clave_tema(x["titulo"]) == clave or
                         (len(clave) >= 12 and (clave in _clave_tema(x["titulo"]) or _clave_tema(x["titulo"]) in clave)))]
        if hermanas:
            asunto_oficial[i] = asunto_oficial[hermanas[0]]
            continue
        aid = o["id"]
        ds = re.search(r"\((\d{2})/(\d+)\)", o["titulo"])
        ds = f"{ds.group(1)}/{int(ds.group(2))}" if ds else None
        titulo = re.sub(r"\s*\((\d{2})/\d+\)\s*", " ", o["titulo"]).strip()
        tipo = tipo_asunto(titulo, "", "")
        asuntos[aid] = Asunto(id=aid, titulo=titulo[:400], tipo="mocion" if tipo == "otro" else tipo, fecha=o["fecha"],
                              codigo=f"Drucksache {ds}" if ds else None, url=_drucksache_url(ds) if ds else None,
                              extra={"legislatura": o["wp"]})
        asunto_oficial[i] = aid

    # 3) Votaciones
    for i, o in enumerate(oficiales):
        p = polls[pares[i]] if i in pares else None
        texto = texto_votado(o["titulo"], p["resumen"] if p else "")
        aceptada = p["aceptada"] if p else None
        if p and p.get("invertida"):
            votos = [(m, n, pa, {"si": "no", "no": "si"}.get(s, s)) for m, n, pa, s in p["votos"]]
            aceptada = None  # la de abgeordnetenwatch es la de la moción, no la de la recomendación
            if not re.search(r"ablehn", texto, re.I):
                texto = _con_rechazo(texto)
        elif p:
            votos = p["votos"]
        else:
            votos = []
            for d in o["diputados"]:
                pid = diputados.get(o["wp"]).id(d) if diputados.get(o["wp"]) else None
                mid = f"deu:{pid}" if pid else "deu:" + "-".join(_clave(d["nombre"]).split())
                votos.append((mid, d["nombre"], d["partido"], d["sentido"]))
        votaciones.append(_votacion(o["id"], o["fecha"], asunto_oficial[i],
                                    o["numero"], texto, votos, aceptada, o["pdf"], len(o["diputados"])))
    for j, p in enumerate(polls):
        if j not in emparejados:
            votaciones.append(_votacion(f"deu:aw{p['id']}", p["fecha"], asunto_poll[p["id"]], None, p["titulo"],
                                        p["votos"], p["aceptada"], p["url"], len(p["votos"])))

    # Si el proyecto se votó a mano alzada y solo hubo votación nominal de unos artículos, de una enmienda o de
    # una moción de acompañamiento, el asunto es eso mismo (así lo titula abgeordnetenwatch) y esa votación lo
    # decide: la de artículos pasa a «otra» y la moción o enmienda a «final».
    for de, a in (("parcial", "otra"), ("enmienda", "final")):
        decididos = {v.asunto_id for v in votaciones if v.tipo in ("final", "otra")}
        for v in votaciones:
            if v.tipo == de and v.asunto_id not in decididos:
                v.tipo = a
    return list(asuntos.values()), votaciones


def _votacion(vid, fecha, aid, numero, texto, votos, aceptada, url, miembros):
    cuenta = {s: sum(1 for v in votos if v[3] == s) for s in ("si", "no", "abstencion", "no_vota")}
    tipo = tipo_votacion(texto)
    # Reformas de la Ley Fundamental: dos tercios de los miembros. Excepción al freno de la deuda (art. 115.2):
    # mayoría de los miembros. Lo demás, mayoría simple.
    mayoria = None
    if tipo == "final" and re.search(r"änderung (des|der) (artikels? [^.]{0,40})?grundgesetz|grundgesetzänderung|"
                                     r"(im|ins) grundgesetz|grundgesetzes \(artikel", texto or "", re.I):
        mayoria = "dos tercios"
    elif tipo in ("final", "otra") and re.search(r"artikel 115|art\. 115|115 ii gg|schuldenbremse", texto or "", re.I):
        mayoria = "absoluta"
    if aceptada is not None:
        resultado = "aprobada" if aceptada else "rechazada"
    elif mayoria == "dos tercios":
        resultado = "aprobada" if cuenta["si"] * 3 >= miembros * 2 else "rechazada"
    elif mayoria == "absoluta":
        resultado = "aprobada" if cuenta["si"] * 2 > miembros else "rechazada"
    else:
        resultado = "aprobada" if cuenta["si"] > cuenta["no"] else "rechazada"
    return Votacion(id=vid, fecha=fecha, asunto_id=aid, camara="deu-bt", numero=numero, texto=texto, tipo=tipo,
                    a_favor=cuenta["si"], en_contra=cuenta["no"], abstenciones=cuenta["abstencion"],
                    no_votan=cuenta["no_vota"], mayoria=mayoria, resultado=resultado, url=url, votos=votos)


RECHAZO = re.compile(r"(empf\w*|beschlussempfehlung)[^.]{0,120}(ablehnung|abzulehnen|abehnung)|"
                     r"(ablehnung|abzulehnen)[^.]{0,60}empf\w*", re.I)


def texto_votado(titulo, resumen):
    """Sobre una moción se vota la recomendación de la comisión (Beschlussempfehlung), casi siempre de rechazarla:
    votar sí es rechazar la moción. Si el título oficial no lo dice y el resumen sí, se añade."""
    if re.search(r"beschlussempfehlung|beschlempf", titulo, re.I) and not re.search(r"ablehn", titulo, re.I) \
            and RECHAZO.search(resumen or ""):
        return _con_rechazo(titulo)
    return titulo


def _con_rechazo(titulo):
    """«Lieferung des Taurus (Beschlussempfehlung)» -> «Lieferung des Taurus (Beschlussempfehlung: Ablehnung)»."""
    nuevo = re.sub(r"\((beschlussempfehlung|beschlempf\.?)\)", "(Beschlussempfehlung: Ablehnung)", titulo, count=1,
                   flags=re.I)
    return nuevo if nuevo != titulo else f"{titulo} (Ablehnung empfohlen)"


def _tramos(fechas):
    """Parte una lista ordenada de fechas en tramos separados por más de VENTANA + 1 días sin votaciones."""
    tramos, actual, anterior = [], [], None
    for f in fechas:
        if anterior and (date.fromisoformat(f) - date.fromisoformat(anterior)).days > VENTANA + 1:
            tramos.append(actual)
            actual = []
        actual.append(f)
        anterior = f
    if actual:
        tramos.append(actual)
    return tramos


# ------------------------------------------------------------------ recogida

def recoger(ctx):
    ultima = ctx.ultima_fecha()
    inicio = f"{ctx.desde}-01-01"
    if ultima and not ctx.completo:
        inicio = max(inicio, (date.fromisoformat(ultima) - timedelta(days=MARGEN)).isoformat())
    hoy = date.today()
    espera = (hoy - timedelta(days=ESPERA)).isoformat()
    leer_desde = (date.fromisoformat(inicio) - timedelta(days=VENTANA)).isoformat()

    oficiales = lista_oficial(ctx, leer_desde)
    ctx.log(f"   {len(oficiales)} votaciones en la lista oficial desde {leer_desde}")

    polls, mandatos = [], {}
    legs = sorted(legislaturas(ctx).items())
    for k, (wp, (periodo, comienzo)) in enumerate(legs):
        fin = legs[k + 1][1][1] if k + 1 < len(legs) else None
        if comienzo > hoy.isoformat() or (fin and fin < leer_desde):
            continue
        lista = _aw(ctx, f"polls?field_legislature={periodo}&range_end=1000")
        lista = [_poll(p, wp) for p in lista if (p.get("field_poll_date") or "") >= leer_desde]
        if not lista and not any(comienzo <= o["fecha"] < (fin or "9999") for o in oficiales):
            continue
        polls += lista
        mandatos[wp] = _aw_todo(ctx, f"candidacies-mandates?parliament_period={periodo}&type=mandate&current_on=all")
    diputados = {wp: Diputados(m) for wp, m in mandatos.items()}
    politico = {k: v for d in diputados.values() for k, v in d.politico.items()}
    ctx.log(f"   {len(polls)} votaciones en abgeordnetenwatch desde {leer_desde}")

    fechas = sorted({o["fecha"] for o in oficiales} | {p["fecha"] for p in polls})
    guardar_a, guardar_v = [], []
    cuenta = {"emparejadas": 0, "solo oficiales": 0, "solo abgeordnetenwatch": 0, "en espera": 0}
    with ThreadPoolExecutor(3) as ex_aw, ThreadPoolExecutor(2) as ex_bt:
        tramos = _tramos(fechas)
        for tramo in tramos:
            dentro = set(tramo)
            ofs = [o for o in oficiales if o["fecha"] in dentro]
            pls = [p for p in polls if p["fecha"] in dentro]
            leidos = list(ex_bt.map(lambda o: _oficial(ctx, o), ofs))
            # Si falta el XLSX de alguna votación del tramo, lo que solo está en una fuente se deja para otra vez
            # (podría ser esa misma votación).
            completo = FALLO not in leidos
            ofs = [o for o in leidos if o and o != FALLO]
            _ids_unicos(ofs)
            for p, votos in zip(pls, ex_aw.map(lambda p: _votos_aw(ctx, p, politico), pls)):
                p["votos"] = votos
            pls = [p for p in pls if p["votos"]]
            pares = emparejar(ofs, pls)
            # Lo que solo está en una fuente se deja para más adelante mientras la otra pueda publicarlo.
            ofs_ok = [i for i, o in enumerate(ofs) if i in pares or (completo and o["fecha"] < espera)]
            pls_ok = [j for j, p in enumerate(pls) if j in pares.values() or (completo and p["fecha"] < espera)]
            pares = {ofs_ok.index(i): pls_ok.index(j) for i, j in pares.items()}
            asuntos, votaciones = construir([ofs[i] for i in ofs_ok], [pls[j] for j in pls_ok], pares, diputados, pls)
            votaciones = [v for v in votaciones if v.fecha >= f"{ctx.desde}-01-01"]
            for partido in {m[2] for v in votaciones for m in v.votos} - set(FUENTE.partidos):
                ctx.partido(partido)
            usados = {v.asunto_id for v in votaciones}
            guardar_a += [a for a in asuntos if a.id in usados]
            guardar_v += votaciones
            cuenta["emparejadas"] += len(pares)
            cuenta["solo oficiales"] += len(ofs_ok) - len(pares)
            cuenta["solo abgeordnetenwatch"] += len(pls_ok) - len(pares)
            cuenta["en espera"] += len(ofs) + len(pls) - len(ofs_ok) - len(pls_ok)
            if len(guardar_v) >= 100 or tramo is tramos[-1]:
                if guardar_v:
                    ctx.guardar(guardar_a, guardar_v)
                ctx.log(f"   hasta {tramo[-1]}: " + ", ".join(f"{v} {k}" for k, v in cuenta.items()))
                guardar_a, guardar_v = [], []
