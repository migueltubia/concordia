"""Chequia: votaciones de la Poslanecká sněmovna (Cámara de Diputados), datos abiertos de psp.cz.

La Cámara publica cada día, por legislatura, un ZIP con todas las votaciones electrónicas del pleno
(hl-AAAAps.zip: la votación con sus totales y el voto de cada diputado) y otros con los diputados y sus
clubes (poslanci.zip), el orden del día de cada sesión (schuze.zip) y los proyectos o «sněmovní tisky»
(tisky.zip). Formato UNL: texto separado por «|» en Windows-1250 (https://www.psp.cz/sqw/hp.sqw?k=1300).

Cada votación va al punto del orden del día (bod) en que se votó; si el punto trata un tisk, todas las
votaciones del tisk (primera, segunda y tercera lectura, vuelta del Senado o del presidente) forman un
solo asunto. Los puntos sin tisk (resoluciones, elecciones, informes) son un asunto cada uno, y las
votaciones del orden del día y de procedimiento van juntas por sesión.

Los ficheros no dicen qué se vota en cada votación (el título es el del punto). Eso sale del
estenograma: en la página de cada punto (bqbs) cada votación enlaza a hlasy.sqw?G=<id>, y lo que dice
la presidencia justo antes («hlasujeme o pozměňovacím návrhu B1», «o návrhu zákona jako celku»,
«o přikázání výboru») da el texto y el tipo. Si el estenograma aún no está (tarda unos días) se usa la
historia del tisk (hist, que enlaza la votación final de los proyectos aprobados) y la fase del punto;
cada recogida repasa las tres últimas semanas para completarlo. Las votaciones anuladas (zmatečné) no se
recogen. Votos: A sí; B/N no; C, F y K (abstención o presente sin votar) abstención; @, M y W (sin
registrar, excusado, antes de jurar el cargo) no vota.
Se recogen las legislaturas 8.ª (2017-2021, desde 2019), 9.ª (2021-2025) y 10.ª (desde octubre de 2025);
los títulos están en checo y la ficha la hace la IA.
"""

import html
import io
import json
import re
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from ..config import RAW_DIR
from .modelo import Asunto, Fuente, Votacion

FUENTE = Fuente(
    codigo="cze", pais="CZE", nombre="Cámara de Diputados de Chequia (Poslanecká sněmovna)", corto="Chequia",
    tipo="parlamento", detalle="nominal", web="https://www.psp.cz", desde=2019, idioma="otro",
    licencia="Datos abiertos de la Poslanecká sněmovna: uso libre y gratuito citando la fuente",
    camaras={"cze-ps": ("Cámara de Diputados", "Diputados", 200)},
    partidos={
        "ANO": ("ANO 2011", "ANO", "#261060"),
        "ODS": ("Partido Democrático Cívico", "ODS", "#034ea2"),
        "STAN": ("Alcaldes e Independientes", "STAN", "#cd0f69"),
        "KDU-ČSL": ("Unión Cristiana y Democrática – Partido Popular Checoslovaco", "KDU-ČSL", "#f2c200"),
        "TOP09": ("TOP 09", "TOP 09", "#993366"),
        "Piráti": ("Partido Pirata Checo", "Piráti", "#1d1d1b"),
        "SPD": ("Libertad y Democracia Directa", "SPD", "#6696ae"),
        "MS": ("Motoristas por Sí Mismos (Motoristé sobě)", "Motoristé", "#009ee3"),
        "ČSSD": ("Partido Socialdemócrata Checo", "ČSSD", "#ed5700"),
        "KSČM": ("Partido Comunista de Bohemia y Moravia", "KSČM", "#c10506"),
        "Nezařaz": ("Diputados no adscritos", "No adscr.", "#898781"),
    },
    notas="Voto de cada diputado en las votaciones electrónicas del pleno; qué se vota en cada una sale del estenograma.",
)

OPENDATA = "https://www.psp.cz/eknih/cdrom/opendata"
MARGEN = 21            # días que se repasan en cada recogida (el estenograma se publica con retraso)
DIAS_CIERRE = 60       # una legislatura terminada hace más que esto no se vuelve a descargar
SENTIDO = {"A": "si", "B": "no", "N": "no", "C": "abstencion", "F": "abstencion", "K": "abstencion"}
CLUB = {"ANO2011": "ANO"}  # el club de ANO cambió de sigla en 2025
MESES = {"ledna": 1, "února": 2, "března": 3, "dubna": 4, "května": 5, "června": 6, "července": 7, "srpna": 8,
         "září": 9, "října": 10, "listopadu": 11, "prosince": 12}

# Fase del punto del orden del día (bod_schuze.id_typ, tabla de https://www.psp.cz/sqw/hp.sqw?k=1308).
FASE = {**dict.fromkeys((1, 7, 15, 17, 18, 40, 41, 44, 67, 71), "1. čtení"), **dict.fromkeys((2, 3, 4, 72), "2. čtení"),
        5: "3. čtení", 73: "3. čtení", 13: "vráceno prezidentem", 74: "vráceno prezidentem", 14: "vráceno Senátem",
        24: "vráceno Senátem", 63: "vráceno Senátem", 75: "vráceno Senátem", 27: "zamítnuto Senátem", 76: "zamítnuto Senátem",
        10: "zkrácené jednání", 43: "zkrácené jednání"}

# Paso de la historia del tisk que enlaza una votación (typ_akce) -> tipo de votación.
HISTORIA = {"souhlas": "final", "schváleno": "final", "setrváno": "final", "pozm. přijat": "final", "nepřijat": "final",
            "neschválen": "final", "neschválena": "final", "zamítnut": "procedimiento", "vrácen": "procedimiento",
            "opakovat": "procedimiento", "přerušeno": "procedimiento", "odročeno": "procedimiento"}


# ------------------------------------------------------------------ ficheros UNL

def _zip(ctx, nombre, caduca_horas=None):
    ruta = ctx.cache(f"{OPENDATA}/{nombre}.zip", f"{nombre}.zip", caduca_horas=caduca_horas)
    return zipfile.ZipFile(io.BytesIO(ruta.read_bytes()))


def _filas(z, nombre):
    """Filas de un fichero UNL: «|» separa columnas y «\\» escapa (en la práctica, algún tabulador)."""
    if nombre not in z.namelist():
        return []
    salida = []
    for linea in z.read(nombre).decode("cp1250", errors="replace").splitlines():
        if "\\" in linea:
            campos = [re.sub(r"\\(.)", r"\1", c).replace("\t", " ") for c in re.split(r"(?<!\\)\|", linea)]
        else:
            campos = linea.split("|")
        salida.append(campos)
    return salida


def _iso(fecha):
    """«03.11.2025» -> «2025-11-03»; «2025-10-08 00» -> «2025-10-08»."""
    fecha = (fecha or "").strip()
    if re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", fecha):
        return f"{fecha[6:10]}-{fecha[3:5]}-{fecha[:2]}"
    return fecha[:10] or None


def _limpio(t):
    return re.sub(r"\s+", " ", t or "").strip()


def _corta(t, n):
    t = _limpio(t)
    return t if len(t) <= n else t[:n - 1].rstrip(" ,;") + "…"


# ------------------------------------------------------------------ datos comunes

def _legislaturas(organos):
    """Legislaturas de la Cámara (organy de tipo 11, «PSP10»): número, año de inicio, órgano y fechas."""
    salida = []
    for r in organos:
        m = re.fullmatch(r"PSP(\d+)", r[3]) if len(r) > 8 and r[2] == "11" else None
        if m:
            salida.append({"numero": int(m.group(1)), "organo": r[0], "inicio": _iso(r[6]), "fin": _iso(r[7]),
                           "anio": int(_iso(r[6])[:4])})
    return sorted(salida, key=lambda x: x["numero"])


class Comun:
    """Lo que comparten todas las legislaturas: diputados y clubes, orden del día y tisky."""

    def __init__(self, ctx, poslanci):
        self.ctx = ctx
        organos = _filas(poslanci, "organy.unl")
        # las legislaturas que tocan el periodo que se recoge
        self.legislaturas = [x for x in _legislaturas(organos) if not x["fin"] or x["fin"] >= f"{ctx.desde}-01-01"]
        de_leg = {x["organo"] for x in self.legislaturas}
        # Clubes (organy de tipo 1) de cada legislatura: órgano -> código de partido
        self.clubes, self.nombres_club = {}, {}
        for r in organos:
            if len(r) > 5 and r[2] == "1" and r[1] in de_leg:
                codigo = CLUB.get(r[3], r[3])
                self.clubes[r[0]] = codigo
                self.nombres_club[codigo] = r[4] or codigo
        self.personas = {r[0]: _limpio(f"{r[3]} {r[2]}") for r in _filas(poslanci, "osoby.unl") if len(r) > 3}
        self.diputados = {r[0]: r[1] for r in _filas(poslanci, "poslanec.unl") if len(r) > 4 and r[4] in de_leg}
        self.afiliacion = {}   # persona -> [(desde, hasta, club)]
        for r in _filas(poslanci, "zarazeni.unl"):
            if len(r) > 4 and r[2] == "0" and r[1] in self.clubes:
                self.afiliacion.setdefault(r[0], []).append((_iso(r[3]), _iso(r[4]) or "9999", self.clubes[r[1]]))
        for lista in self.afiliacion.values():
            lista.sort()
        self._club_cache = {}

        tisky = _zip(ctx, "tisky", caduca_horas=20)
        self.tisky = {r[0]: r for r in _filas(tisky, "tisky.unl") if len(r) > 15 and r[7] in de_leg}
        self.druhs = {r[0]: r[2] for r in _filas(tisky, "druh_tisku.unl") if len(r) > 2}
        acciones = {r[0]: r[1] for r in _filas(tisky, "typ_akce.unl") if len(r) > 1}
        pasos = {r[0]: acciones.get(r[3]) for r in _filas(tisky, "prechody.unl") if len(r) > 3}
        self.historia = {}     # votación -> tipo según la historia del tisk
        for r in _filas(tisky, "hist.unl"):
            if len(r) > 4 and r[3] and pasos.get(r[4]) in HISTORIA:
                self.historia[r[3]] = HISTORIA[pasos[r[4]]]

        schuze = _zip(ctx, "schuze", caduca_horas=20)
        self.sesiones = {}     # (órgano de la legislatura, número de sesión) -> id_schuze
        for r in _filas(schuze, "schuze.unl"):
            if len(r) > 2 and r[1] in de_leg:
                self.sesiones[(r[1], r[2])] = r[0]
        ids = set(self.sesiones.values())
        self.puntos = {}       # (id_schuze, número de punto) -> fila de bod_schuze (del orden aprobado si lo hay)
        for r in _filas(schuze, "bod_schuze.unl"):
            if len(r) > 9 and r[1] in ids:
                clave = (r[1], r[4])
                if clave not in self.puntos or r[9] == "":
                    self.puntos[clave] = r

    def club(self, persona, fecha):
        clave = (persona, fecha)
        if clave not in self._club_cache:
            club = "Nezařaz"
            for desde, hasta, codigo in self.afiliacion.get(persona, ()):
                if desde <= fecha <= hasta:
                    club = codigo
            if club not in FUENTE.partidos:   # un club nuevo: se da de alta con su nombre
                self.ctx.partido(club, self.nombres_club.get(club, club), club)
            self._club_cache[clave] = club
        return self._club_cache[clave]


# ------------------------------------------------------------------ asuntos

def tipo_tisk(druh, titulo):
    t = titulo.lower()
    if druh in ("4", "27"):
        return "tratado"
    if druh in ("1", "2", "3", "25", "34", "49"):
        return "ley"
    if "ratifikac" in t:
        return "tratado"
    if druh in ("41", "45", "46", "47", "5"):
        return "nombramiento" if re.search(r"návrh na (?:volbu|jmenování|odvolání)", t) else "resolucion"
    if druh == "6":
        return "mocion"
    return "otro"


def tipo_punto(titulo):
    """Tipo de un punto del orden del día sin tisk, por su título."""
    t = titulo.lower()
    if re.search(r"nedůvěr", t):
        return "mocion"
    if re.match(r"(?:návrh )?usnesení|stanovisk|vyjádření|výzv|deklarac|prohlášení", t):
        return "resolucion"
    if re.search(r"důvěr|volb|volen|jmenov|odvolání|složení orgánů|potvrzení předsed|ustavení|zřízení .*komis|"
                 r"místopředsed|vyznamenání|delegac|kandidát|členů rady|zpravodaj", t):
        return "nombramiento"
    if re.search(r"pořad\w* schůze|termínu a pořadu|pravidel hospodaření|jednacího řádu|legislativní nouz", t):
        return "procedimiento"
    if re.search(r"ratifikac|mezinárodní smlouv", t):
        return "tratado"
    if re.search(r"usnesení|stanovisk|vyjádření|výzv|deklarac|prohlášení|odsouzení|podpor[ay] |nouzov|informac|zpráv|situac", t):
        return "resolucion"
    if re.search(r"interpelac", t):
        return "mocion"
    return "otro"


def asunto_de(comun, leg, h, fecha):
    """(Asunto, fase del punto) de una fila de hlasovani."""
    numero, sesion, bod = leg["numero"], h[2], int(h[4] or 0)
    lista = f"https://www.psp.cz/sqw/phlasa.sqw?o={numero}&s={sesion}"
    extra = {"legislatura": numero}
    if bod < 1:
        return Asunto(id=f"cze:{numero}:s{sesion}:proc", titulo=f"Votaciones de procedimiento y orden del día, {sesion}.ª sesión",
                      tipo="procedimiento", fecha=fecha, url=lista, extra=extra), None
    punto = comun.puntos.get((comun.sesiones.get((leg["organo"], sesion)), h[4]))
    if not punto:
        titulo = _limpio(h[15]) or f"Punto {bod} de la {sesion}.ª sesión"
        return Asunto(id=f"cze:{numero}:s{sesion}:b{bod}", titulo=_corta(titulo, 400), tipo=tipo_punto(titulo),
                      fecha=fecha, url=lista, extra=extra), None
    fase = FASE.get(int(punto[3] or -1))
    tisk = comun.tisky.get(punto[2]) if punto[2] else None
    if tisk:
        ct = f"{tisk[3]}{'-E' if tisk[1] in ('41', '45', '46', '47') else ''}"
        titulo = _limpio(tisk[15]) or _limpio(tisk[10]) or _limpio(punto[5])
        extra["druh"] = comun.druhs.get(tisk[1])
        return Asunto(id=f"cze:{numero}:t{ct}", titulo=_corta(titulo, 400), tipo=tipo_tisk(tisk[1], titulo),
                      fecha=min(x for x in (_iso(tisk[11]), fecha) if x), codigo=f"tisk {ct}",
                      url=f"https://www.psp.cz/sqw/historie.sqw?o={numero}&t={ct}", extra=extra), fase
    coletilla = "" if re.match(r"Není sn", punto[6] or "") else punto[6] or ""   # «Není sn.tiskem»: no es un tisk
    titulo = _limpio(f"{punto[5]} {coletilla}") or _limpio(h[15])
    aid = f"cze:{numero}:b{punto[0]}" + (f"-{bod}" if punto[3] == "6" else "")  # cada respuesta a interpelación aparte
    return Asunto(id=aid, titulo=_corta(titulo, 400), tipo=tipo_punto(titulo), fecha=fecha, url=lista, extra=extra), fase


# ------------------------------------------------------------------ estenograma

def _html(ctx, url):
    try:
        b = ctx.fetch(url, retries=2)
    except Exception:
        return None
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        return b.decode("cp1250", errors="replace")


def _texto(fragmento):
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", fragmento, flags=re.S)
    t = re.sub(r"<[^>]+>", " ", t)
    return _limpio(html.unescape(t).replace("\xa0", " "))


def _dias(indice, sesion):
    """Días de la sesión según su índice: «31. schůze (22., 23., 24. září 2026)» -> {página: fecha}."""
    enlaces = re.findall(rf'<a href="({sesion}-\d+\.html)"[^>]*>(.*?)</a>', indice)
    salida, mes, anio = {}, None, None
    for pagina, texto in reversed(enlaces):   # el mes y el año solo van en el último día de cada mes
        t = html.unescape(re.sub(r"<[^>]+>", "", texto)).replace("\xa0", " ")
        m = re.match(r"\s*(\d{1,2})\.\s*([^\d\s]+)?\s*(\d{4})?", t)
        if not m:
            continue
        nuevo = MESES.get((m.group(2) or "").lower())
        if m.group(3):
            anio = int(m.group(3))
        elif nuevo and mes and anio and nuevo > mes:   # de enero hacia atrás a diciembre
            anio -= 1
        mes = nuevo or mes
        if mes and anio:
            try:
                salida[pagina] = date(anio, mes, int(m.group(1))).isoformat()
            except ValueError:
                pass
    return salida


def _secciones(pagina):
    """Del índice de un día: [(página bqbs, número de punto)] y los turnos (s031001.htm…) por si no hay bqbs."""
    secciones = []
    for trozo in pagina.split('<div class="media-links">')[1:]:
        m = re.match(r'\s*<a href="bqbs/(b\d+)\.htm"', trozo)
        if m:
            b = re.search(r"</div>\s*(?:<b>\s*(\d+)\.)?", trozo)
            secciones.append((m.group(1), int(b.group(1)) if b and b.group(1) else 0))
    turnos = list(dict.fromkeys(re.findall(r'href="(s\d+\.htm)', pagina)))
    return secciones, turnos


ENLACE = re.compile(r"<a[^>]+hlasy\.sqw\?[gG]=(\d+)[^>]*>")


def _cuerpo(pagina):
    """El texto del estenograma de una página, sin menús ni guiones."""
    pagina = pagina or ""
    i = max(pagina.find('id="main-content"'), 0)
    fines = [j for j in (pagina.find("tippy(", i), pagina.find('id="menu"', i)) if j > 0]
    return pagina[i:min(fines)] if fines else pagina[i:]


def _contextos(pagina):
    """{votación: lo que se dice desde la votación anterior} en el texto de una o varias páginas seguidas."""
    salida, previo = {}, 0
    for m in ENLACE.finditer(pagina):
        salida.setdefault(m.group(1), _texto(pagina[previo:m.start()])[-2500:])
        previo = m.end()
    return salida


def estenograma(ctx, leg, sesion, pedidas, cerrada):
    """{votación: texto previo} de las votaciones pedidas de una sesión.

    pedidas = {fecha: {punto: {votaciones}}}. De cada día se bajan las páginas de esos puntos (bqbs);
    si falta alguna votación (un punto debatido junto con otro, por ejemplo), las demás páginas del día;
    y si aún falta (la continuación de un punto de otro día no siempre tiene página propia), los turnos
    del día, de los últimos hacia atrás, hasta encontrarla. Lo de una sesión cerrada se guarda en
    data/raw/cze/steno/ para no volver a pedirlo.
    """
    ruta = RAW_DIR / FUENTE.codigo / "steno" / f"{leg['anio']}-{sesion}.json"
    pedido = {f"{f}|{b}" for f, puntos in pedidas.items() for b in puntos}
    guardado = {}
    if ruta.exists():
        try:
            guardado = json.loads(ruta.read_text(encoding="utf-8"))
        except ValueError:
            guardado = {}
        if pedido <= set(guardado.get("pedido", [])):
            return guardado.get("contextos", {})
    base = f"https://www.psp.cz/eknih/{leg['anio']}ps/stenprot/{int(sesion):03d}schuz/"
    indice = _html(ctx, base + "index.htm")
    if not indice:
        return {}
    dias = _dias(indice, sesion)
    paginas = [p for p, f in dias.items() if f in pedidas]
    paginas += list(dict.fromkeys(p for p in re.findall(rf'href="({sesion}-\d+\.html)"', indice) if p not in dias))
    secciones, turnos = {}, {}   # fecha -> [(punto, url bqbs)] / [url de turno] en orden
    for p in paginas:
        dia = _html(ctx, base + p)
        if not dia:
            continue
        fecha = dias.get(p)
        if not fecha:
            m = re.search(r"schůze,\s*(\d{1,2})\.(?:&nbsp;|\s)*([^\d&\s<]+)(?:&nbsp;|\s)*(\d{4})", dia)
            if not m or m.group(2).lower() not in MESES:
                continue
            fecha = date(int(m.group(3)), MESES[m.group(2).lower()], int(m.group(1))).isoformat()
        if fecha in pedidas:
            s, t = _secciones(dia)
            secciones[fecha] = [(bod, base + f"bqbs/{b}.htm") for b, bod in s]
            turnos[fecha] = [base + x for x in t]
    salida, bajadas = {}, {}

    def bajar(urls):
        urls = [u for u in dict.fromkeys(urls) if u not in bajadas]
        with ThreadPoolExecutor(6) as ex:
            bajadas.update(zip(urls, ex.map(lambda u: _html(ctx, u), urls)))

    def leer(grupos):   # cada grupo es una lista de páginas que se leen seguidas
        bajar(u for g in grupos for u in g)
        for g in grupos:
            for vid, texto in _contextos("".join(_cuerpo(bajadas.get(u)) for u in g)).items():
                salida.setdefault(vid, texto)

    def faltan(fecha):
        return any(v not in salida for vs in pedidas[fecha].values() for v in vs)

    leer([[u] for fecha, lista in secciones.items() for bod, u in lista if bod in pedidas[fecha]])
    leer([[u] for fecha, lista in secciones.items() if faltan(fecha) for _, u in lista])
    for fecha, lista in turnos.items():
        hechos = 0
        while faltan(fecha) and hechos < min(len(lista), 80):
            hechos = min(len(lista), hechos + 6)
            leer([lista[-hechos:]])
    if cerrada and salida and None not in bajadas.values():
        salida = {**guardado.get("contextos", {}), **salida}
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(json.dumps({"pedido": sorted(pedido | set(guardado.get("pedido", []))), "contextos": salida},
                                   ensure_ascii=False), encoding="utf-8")
    return salida


# ------------------------------------------------------------------ qué se vota

# Marcas en lo que dice la presidencia antes de votar. Gana la que acaba más cerca de la votación; si
# empatan, la de la clase que va antes en PRIORIDAD.
MARCAS = {
    "otra": [r"doprovodn\w* usnesení", r"(?:ne)?souhlasn\w* stanovisk\w*"],
    "procedimiento": [
        r"přikáz\w*", r"garančním výborem|jako (?:ve |v )?(?:výbor\w* garanční\w*|garanční\w* výbor\w*)",
        r"(?:zkrácení|prodloužení|zkrátit|prodloužit|zkrácen\w*|prodloužen\w*) lhůt\w*", r"lhůt\w* (?:k|na|pro) projednání",
        r"změn\w* zpravodaj\w*", r"sloučen\w* rozprav\w*|sloučil\w* rozprav\w*|sloučení bodů", r"procedur\w*", r"protinávrh\w*",
        r"přestávk\w*", r"odročen\w*|odročit|odročí", r"přeruš\w* (?:projednávání|jednání|schůze|bodu|rozpravy)|přerušení do",
        r"vrácení (?:návrhu|předloženého|zákona|tisku|garančnímu|výboru|navrhovateli|k dopracování|do)|"
        r"vrátit (?:návrh|předložen\w*|zákon|tisk|garančnímu|výboru|do)|k dopracování|k novému projednání|do druhého čtení",
        r"\bopakování\b|\bopakovat\b|\bopakovan\w*", r"zpochybn\w*",
        r"(?:návrh\w* na |o )zamítnutí|zamítnutí (?:návrhu|předloženého|zákona|tisku|smlouvy|v prvém|v prvním)|zamítli|"
        r"zamítnout (?:návrh|předložen\w*|zákon|tisk|v prvém)",
        r"o námitce|námitk\w* proti|námitk\w* (?:poslance|poslankyně|předsed\w*|pana|paní)",
        r"tajn\w* volb\w*|způsob\w* volby|form\w* volby|tajným (?:hlasováním|způsobem)|provedena tajně",
        r"s pokračováním|o pokračování", r"§\s*90 odst\. ?[25]|§\s*94", r"pořadu? schůze|z pořadu|do pořadu|návrh\w* pořadu",
        r"zařazení (?:nového )?bodu|zařadit (?:jako|nový|bod)|vyřazení bodu|vyřadit", r"po \d{1,2}\. hodině",
        r"ověřovatel\w*", r"legislativní nouz\w*|zkráceném jednání",
    ],
    # «návrh zákona jako celek», «hlasujeme o zákonu jakožto celku ve znění přijatých pozměňovacích návrhů»
    "final": [r"(?:zákon\w*|návrh\w*|usnesení|předloh\w*|tisk\w*)(?: \w+){0,3} jako(?:žto)? cel(?:ek|ku)\b(?:,? ve znění[^.?!\"“”]*)?",
              r"o cel[ée]m návrhu (?:zákona|usnesení)", r"celého návrhu (?:zákona|usnesení)"],
    "enmienda": [r"pozměňovac\w*", r"legislativně.technick\w*",
                 # «Stanovisko výboru? Stanovisko ministra?»: la ronda de posiciones antes de votar cada enmienda
                 r"stanovisk\w*(?: \w+){0,2} (?:výbor\w*|garanční\w*|navrhovatel\w*|zpravodaj\w*|ministr\w*|vlád\w*|předkladatel\w*)|"
                 r"stanovisk\w*\s*[?:]|(?:o|prosím o|poprosím o|jaké je) stanovisk\w*"],
    "nombramiento": [r"\bvolb(?:a|u|y|ě|ou)\b", r"\bzvol(?:it|en\w*|íme|ila|il)\b", r"\bvolí\b", r"jmenov\w*",
                     r"odvolání|odvolat", r"rezignac\w*", r"potvrzuje\b", r"ve funkci", r"kandidát\w*",
                     r"vyznamenání", r"propůjčení"],
}
# Resoluciones que se leen antes de la votación final: la marca abarca todo el texto leído («Poslanecká
# sněmovna vyslovuje souhlas s … podle sněmovního tisku 246, ve znění …»), para que lo que diga el título
# de la ley no cuente como posterior.
LECTURA = re.compile(r"(?:vyslovuje|dává|vyslovila|dala) (?:předchozí )?souhlas (?:s|se|k)\b(?! tím\b| pokračov)|"
                     r"\bsouhlasí se? (?!tím\b|pokračov)|\bschvaluje\b|setrvává na\b|vyslovuje (?:ne)?důvěru|bere na vědomí")
FIN_LECTURA = re.compile(r"(?P<comilla>[\"“”])|(?P<tisk>tisku\s*\d+(?:/\d+)?(?:-E)?(?:,? ve znění[^.\"“”]*)?)|"
                         r"(?P<voto>(?i:zah[aá]j\w* (?:jsem |tedy )?hlasování))|"
                         r"(?P<punto>(?<!\bč)(?<!\bSb)(?<!\bodst)(?<!\bpísm)(?<!\bčl)(?<!\bzák)(?<!\d)\.\s+(?=[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ]))")
PRIORIDAD = ["otra", "procedimiento", "final", "enmienda", "nombramiento"]
MARCAS_RE = {k: [re.compile(p) for p in v] for k, v in MARCAS.items()}
# «hlasujeme o návrhu B1», «pozměňovací návrh A.3» (en el texto con mayúsculas)
LETRA = re.compile(r"\b(?:návrh\w*|bod\w*|písmen\w*)\s+(?:pod\s+(?:písmenem|číslem)\s+)?[A-Z]{1,2}\d{0,3}(?:\.\d+)*\b")
ZAHAJUJI = re.compile(r"zah[aá]j\w* (?:jsem |tedy |tímto |nyní |teď )?hlasování(?: a (?:ptám|táži) se)?[,:]?\s*", re.I)
FIN_FRASE = re.compile(r"(?<!\bč)(?<!\bSb)(?<!\bodst)(?<!\bpísm)(?<!\bčl)(?<!\bzák)[.?!](?=\s|$)")
RUTINA = re.compile(r"zagong|předsálí|odhlás|přihlas|identifikační|kart[ay]|omlouv|omluv|chviličk|vydrž|počk|ustálil|"
                    r"dobíh|děkuj|zahaj|zaháj|kdo je pro|kdo je proti|přistoupíme k hlasování|přikročíme k hlasování|"
                    r"můžeme (?:přistoupit|hlasovat)|nevidím|nikoho|počet přihlášených|zvukový záznam|"
                    r"^(?:ano|dobře|tak|takže|prosím|výborně|pardon|hlasujeme|budeme hlasovat)\W*$", re.I)


def _recorta(seg):
    """Quita el resultado de la votación anterior y las acotaciones del estenógrafo."""
    seg = re.sub(r"^\s*,?[^.]{0,160}?přihlášen[^.]*\.(?:[^.]{0,160}?(?:přijat|zamítnut|souhlas|nebyl|výsledek)[^.]*\.)?", " ", seg)
    seg = re.sub(r"\([^()]{0,400}\)", " ", seg)
    seg = re.sub(r"stenozáznam (?:části projednávání bodu pořadu schůze|zahájení jednacího dne schůze)|Zvukov[ýy] z[áa]znam|"
                 r"Neprošlo jazykovou korekturou, neautorizováno!?|\bDolů\b|\bNahoru\b", " ", seg, flags=re.I)
    # quién habla («Místopředseda PSP Jan Skopeček: »)
    seg = re.sub(r"\b(?:Místopředsed(?:a|kyně)|Předsed(?:a|kyně)|Poslan(?:ec|kyně)|Ministr(?:yně)?|Náměst(?:ek|kyně)|"
                 r"Senátor(?:ka)?|Guvernér\w*|Prezident\w*|Veřejn\w* ochránk\w*)\b[^:.!?\"“”]{0,90}?: ", " ", seg)
    return _limpio(seg)[-1500:]


CITA = re.compile(r"„[^„“”\"]{0,1500}[“”\"]|\"[^\"„“”]{0,1500}\"|“[^„“”\"]{0,1500}”")


def _marcas(seg, nombramiento):
    """[(fin, -prioridad, clase, inicio)] de todas las marcas del texto."""
    bajo = seg.lower()
    # Lo que se lee entre comillas (el texto de una resolución) solo cuenta para las marcas de lectura.
    sin_citas = CITA.sub(lambda m: " " * len(m.group(0)), bajo)
    salida = []
    for clase in PRIORIDAD:
        if clase == "nombramiento" and not nombramiento:
            continue
        for rx in MARCAS_RE[clase]:
            for m in rx.finditer(sin_citas):
                cl = clase
                previo = (bajo[max(0, m.start() - 60):m.start()] + m.group(0)).split(" jako")[0].split()[-4:]
                if clase == "final" and any(w.startswith(("pozměňovac", "návrz")) for w in previo):
                    cl = "enmienda"   # «pozměňovací návrhy výboru hlasovat jako celek»: en bloque
                elif clase == "final" and re.search(r"\b(?:nakonec|na závěr|následně|poté|potom|pak|bychom)\b",
                                                    sin_citas[max(0, m.start() - 50):m.start()]):
                    cl = "procedimiento"   # «…a nakonec o zákonu jako celku»: se describe el orden de votación
                elif m.group(0).startswith("procedur") and re.search(
                        r"pozměňovac|\b[a-z]\d{1,3}\b", re.split(r"[.?!] ", sin_citas[max(0, m.start() - 200):m.start()])[-1]):
                    continue   # «Pozměňovací návrh V2 … znovuzavedení procedury v památkové péči»: habla de la enmienda
                salida.append((m.end(), -PRIORIDAD.index(cl), cl, m.start()))
    for m in LECTURA.finditer(bajo):
        if not re.search(r"sněmovna\b(?:[^.!?]|\b[ivx]+\.){0,45}$", bajo[max(0, m.start() - 70):m.start()]):
            continue   # «Poslanecká sněmovna [Parlamentu ČR] vyslovuje souhlas…»: lo que resuelve la Cámara
        f = FIN_LECTURA.search(seg, m.end())
        fin = m.end()
        if f:
            fin = max(fin, min(f.end() if f.group("tisk") else f.start(), fin + 600))
        if re.search(r"lhůt|přikáz|pokračov|zpravodaj|pořad\b|pořadu|přeruš|odroč|ověřovatel", bajo[m.start():fin]):
            continue   # «Sněmovna souhlasí se zkrácením lhůty…»: una resolución de trámite
        salida.append((fin, -PRIORIDAD.index("final"), "final", m.start()))
    for m in LETRA.finditer(CITA.sub(lambda m: " " * len(m.group(0)), seg)):
        salida.append((m.end(), -PRIORIDAD.index("enmienda"), "enmienda", m.start()))
    return salida


def _frase(seg, inicio, fin, lectura):
    """La frase del estenograma que contiene la marca (sin el «zahajuji hlasování» de rutina)."""
    a = max([seg.rfind(s, 0, inicio) + len(s) for s in (". ", "? ", "! ", ": ", "„", "\"", "“") if seg.rfind(s, 0, inicio) >= 0]
            or [max(0, inicio - 200)])
    if lectura:
        b = fin
    else:
        m = FIN_FRASE.search(seg, fin)
        b = m.start() if m else len(seg)
    frase = seg[a:b]
    z = ZAHAJUJI.search(frase)
    if z:
        frase = frase[z.end():] if inicio - a >= z.end() else frase[:z.start()]
    return _corta(frase.strip(" ,\"„“”:"), 280) or None


def clasificar(contexto, nombramiento=False, fase=None):
    """(tipo, frase) de una votación a partir de lo que se dice antes en el estenograma."""
    if len(re.findall(r"(?:Pro návrh|Proti návrhu)\.", contexto)) >= 10:
        # Votación por llamamiento («Babiš Andrej: Pro návrh.»): la de confianza o censura al Gobierno
        return "final", "hlasování podle jmen"
    seg = _recorta(contexto)
    marcas = _marcas(seg, nombramiento)
    if fase in ("1. čtení", "2. čtení"):   # en primera y segunda lectura no se votan enmiendas
        marcas = [m for m in marcas if not seg[m[3]:m[3] + 10].lower().startswith(("stanovisk", "o stanov", "prosím o", "jaké je"))]
    if marcas:
        fin, _, clase, inicio = max(marcas)
        if clase == "enmienda" and seg[inicio:inicio + 10].lower().startswith("stanovisk"):
            # «Stanovisko výboru?» dice poco: mejor la frase que nombra la enmienda («návrh B1 poslance…»)
            fuertes = [m for m in marcas if m[2] == "enmienda" and not seg[m[3]:m[3] + 10].lower().startswith("stanovisk")]
            if fuertes:
                fin, _, _, inicio = max(fuertes)
        lectura = clase == "final" and bool(LECTURA.match(seg.lower(), inicio))
        return clase, _frase(seg, inicio, fin, lectura)
    for frase in reversed(re.split(r"(?<=[.?!])\s+", ZAHAJUJI.split(seg)[0])):
        if len(frase) >= 6 and not RUTINA.search(frase):   # a veces solo el nombre del candidato
            return None, _corta(frase, 280)
    return None, None


def tipo_por_fase(fase, tipo_a, ultima):
    """Tipo de votación sin estenograma ni historia del tisk: por la fase del punto."""
    if fase == "1. čtení":
        return "procedimiento"
    if fase == "2. čtení":
        return "otra" if tipo_a == "tratado" else "procedimiento"
    if fase == "3. čtení":
        return "otra" if ultima else "enmienda"
    return "nombramiento" if tipo_a == "nombramiento" else "otra"


def tipo_votacion(procedimental, en_historia, clase, con_steno, fase, tipo_a, ultima):
    """Tipo de una votación: la historia del tisk manda; luego el estenograma; si no, la fase del punto."""
    if procedimental:
        return "procedimiento"
    tipo = en_historia or clase
    if not tipo:
        if con_steno and fase not in ("1. čtení", "2. čtení"):
            tipo = "nombramiento" if tipo_a == "nombramiento" else "otra"
        else:
            tipo = tipo_por_fase(fase, tipo_a, ultima and not con_steno)
    return "procedimiento" if tipo == "otra" and tipo_a == "procedimiento" else tipo


# ------------------------------------------------------------------ recogida

def _votos(z, anio, ids):
    """{votación: [(diputado, voto)]} de los ficheros hl{AAAA}h{n}.unl."""
    salida = {}
    for nombre in sorted(n for n in z.namelist() if re.fullmatch(rf"hl{anio}h\d+\.unl", n)):
        for linea in z.read(nombre).decode("cp1250", errors="replace").splitlines():
            c = linea.split("|")
            if len(c) > 2 and c[1] in ids:
                salida.setdefault(c[1], []).append((c[0], c[2]))
    return salida


def _mayoria(kvorum, presentes):
    if not kvorum or kvorum == presentes // 2 + 1:
        return None
    return {101: "absoluta (101)", 120: "3/5 (120)"}.get(kvorum, str(kvorum))


def recoger_legislatura(ctx, comun, leg, inicio, cerrada):
    anio = leg["anio"]
    z = _zip(ctx, f"hl-{anio}ps", caduca_horas=None if cerrada else 12)
    anuladas = {r[0] for r in _filas(z, "zmatecne.unl")}
    filas = [r for r in _filas(z, f"hl{anio}s.unl")
             if len(r) > 16 and r[1] == leg["organo"] and r[0] not in anuladas and (_iso(r[5]) or "") >= inicio]
    if not filas:
        return
    votos = _votos(z, anio, {r[0] for r in filas})
    ctx.log(f"   legislatura {leg['numero']} ({anio}): {len(filas)} votaciones desde {inicio}")
    sesiones = {}
    for r in filas:
        sesiones.setdefault(int(r[2]), []).append(r)
    for sesion, lista in sorted(sesiones.items()):
        lista.sort(key=lambda r: int(r[3]))
        pedidas = {}   # fecha -> punto -> votaciones que buscar en el estenograma
        for r in lista:
            if int(r[4] or 0) >= 1:
                dia = _iso(r[5])
                if r[6] < "06:00":   # pasada la medianoche, el estenograma sigue en la página del día anterior
                    dia = (date.fromisoformat(dia) - timedelta(days=1)).isoformat()
                pedidas.setdefault(dia, {}).setdefault(int(r[4]), set()).add(r[0])
        ultimo_dia = max(_iso(r[5]) for r in lista)
        sesion_cerrada = (date.today() - date.fromisoformat(ultimo_dia)).days > 30
        steno = estenograma(ctx, leg, sesion, pedidas, sesion_cerrada) if pedidas else {}
        # última votación de cada punto y día (la final, si no hay nada mejor, en tercera lectura)
        ultima = {}
        for r in lista:
            ultima[(r[5], r[4])] = r[0]
        asuntos, votaciones = {}, []
        for r in lista:
            vid, fecha = r[0], _iso(r[5])
            asunto, fase = asunto_de(comun, leg, r, fecha)
            aid, tipo_a = asunto.id, asunto.tipo
            asuntos.setdefault(aid, asunto)
            clase, frase = clasificar(steno[vid], tipo_a == "nombramiento", fase) if vid in steno else (None, None)
            tipo = tipo_votacion(int(r[4] or 0) < 1, comun.historia.get(vid), clase, vid in steno, fase, tipo_a,
                                 ultima[(r[5], r[4])] == vid)
            if int(r[4] or 0) < 1:
                texto = frase or _limpio(r[15]) or "Procedurální hlasování"
            else:
                texto = " – ".join(x for x in (fase, frase) if x) or None
            lista_votos = []
            for diputado, v in votos.get(vid, []):
                persona = comun.diputados.get(diputado)
                if not persona:
                    continue
                lista_votos.append((f"cze:{persona}", comun.personas.get(persona), comun.club(persona, fecha),
                                    SENTIDO.get(v, "no_vota")))
            pro, proti, zdrzel, nehlasoval, prihlaseno, kvorum = (int(x or 0) for x in r[7:13])
            totales = (pro, proti, zdrzel + nehlasoval, 200 - pro - proti - zdrzel - nehlasoval)
            if lista_votos:   # los del voto de cada diputado (alguna vez difieren en uno de los publicados)
                cuenta = {s: 0 for s in ("si", "no", "abstencion", "no_vota")}
                for *_, s in lista_votos:
                    cuenta[s] += 1
                totales = tuple(cuenta.values())
            votaciones.append(Votacion(
                id=f"cze:{vid}", fecha=fecha, asunto_id=aid, camara="cze-ps", numero=int(r[3]),
                texto=_corta(texto, 300) if texto else None, tipo=tipo, a_favor=totales[0], en_contra=totales[1],
                abstenciones=totales[2], no_votan=totales[3], mayoria=_mayoria(kvorum, prihlaseno),
                resultado={"A": "aprobada", "R": "rechazada", "K": "rechazada"}.get(r[14]),
                url=f"https://www.psp.cz/sqw/hlasy.sqw?g={vid}", votos=lista_votos or None))
        for i in range(0, len(votaciones), 250):
            lote = votaciones[i:i + 250]
            ctx.guardar([asuntos[a] for a in dict.fromkeys(v.asunto_id for v in lote)], lote)
        de_punto = sum(1 for r in lista if int(r[4] or 0) >= 1)
        con_steno = sum(1 for r in lista if int(r[4] or 0) >= 1 and r[0] in steno)
        ctx.log(f"   sesión {sesion} ({ultimo_dia}): {len(votaciones)} votaciones; de las {de_punto} de un punto del orden "
                f"del día, {con_steno} con estenograma")


def recoger(ctx):
    poslanci = _zip(ctx, "poslanci", caduca_horas=20)
    comun = Comun(ctx, poslanci)
    cerradas = set(ctx.marca("cerradas", []))
    ultima = None if ctx.completo else ctx.ultima_fecha()
    hoy = date.today()
    for leg in comun.legislaturas:   # las que tocan el periodo pedido
        fin = leg["fin"]
        if leg["numero"] in cerradas and not ctx.completo:
            continue
        inicio = max(f"{ctx.desde}-01-01", leg["inicio"])
        if ultima:
            inicio = max(inicio, (date.fromisoformat(ultima) - timedelta(days=MARGEN)).isoformat())
        cerrada = bool(fin) and (hoy - date.fromisoformat(fin)).days > DIAS_CIERRE
        if not fin or inicio <= fin:
            recoger_legislatura(ctx, comun, leg, inicio, cerrada)
        if cerrada:
            cerradas.add(leg["numero"])
            ctx.poner_marca("cerradas", sorted(cerradas))
