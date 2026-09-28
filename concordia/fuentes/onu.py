"""Asamblea General de las Naciones Unidas: el voto de cada Estado en cada votación registrada.

Dos vías, la primera se carga una sola vez:

1. Histórico (1946 a septiembre de 2023, sesiones 1 a 77): «United Nations General Assembly Voting
   Data» de Erik Voeten y otros, Harvard Dataverse, doi:10.7910/DVN/LEJUQZ, versión 32 (CC0). Trae el
   título de cada resolución y sus temas (Oriente Próximo, nuclear, desarme, derechos humanos,
   colonialismo, desarrollo), que sirven de tema provisional.
2. Desde entonces: el fichero oficial de la Biblioteca Digital de la ONU («General Assembly voting
   data», https://digitallibrary.un.org/record/4060887), que se actualiza de forma continua.
   La web usa AWS WAF que bloquea las peticiones de Python (tanto la página HTML como el endpoint
   JSON de Invenio). Para obtener datos más recientes, descarga el CSV con un navegador y déjalo en
   data/raw/onu/undl/.
"""

import csv
import io
import re
from collections import defaultdict

from .. import paises
from ..config import RAW_DIR
from .modelo import Asunto, Fuente, Votacion

FUENTE = Fuente(
    codigo="onu", pais=None, nombre="Asamblea General de las Naciones Unidas", corto="ONU", tipo="organismo",
    detalle="estado", web="https://www.un.org/es/ga/", desde=1946, idioma="en",
    licencia="Voeten et al., Harvard Dataverse (CC0) hasta 2023; Biblioteca Digital de la ONU después",
    camaras={"onu-ag": ("Asamblea General", "AG", 193)},
    # Los «grupos» de la Asamblea son las regiones M49 (colores categóricos en orden fijo).
    partidos={"AFR": ("África", "África", "#2a78d6"), "AME": ("América", "América", "#eb6834"),
              "ASI": ("Asia", "Asia", "#1baf7a"), "EUR": ("Europa", "Europa", "#eda100"),
              "OCE": ("Oceanía", "Oceanía", "#e87ba4"), "OTR": ("Otros", "Otros", "#898781")},
    notas="Solo votaciones registradas: lo adoptado sin votación no aparece.",
)

VOETEN_URL = "https://dataverse.harvard.edu/api/access/datafile/9656257"  # UNVotes.csv, versión 32
UNDL_URL = "https://digitallibrary.un.org/record/4060887"
UNDL_JSON = "https://digitallibrary.un.org/record/4060887?of=recjson"
VOETEN_HASTA = "2023-09-30"
SENTIDO_VOETEN = {"1": "si", "2": "abstencion", "3": "no", "8": "no_vota"}  # 9: no era miembro
# Códigos COW sin ISO3 propio (o con uno que no es el del Estado de entonces).
COW_HISTORICO = {"680": "YMD", "260": "DEU", "315": "CSK", "265": "DDR", "678": "YAR", "345": "YUG", "511": "EAZ"}


def _frase(t):
    """«TO ADOPT A CUBAN AMENDMENT» -> «To adopt a cuban amendment» (los títulos antiguos van en mayúsculas)."""
    t = re.sub(r"\s+", " ", (t or "").replace("\\", "")).strip(" .")
    t = re.sub(r"\s*:\s*resolution\s*/\s*adopted by the General Assembly.*$", "", t, flags=re.I)
    if t and t.upper() == t:
        t = t.capitalize()
        t = re.sub(r"\b(u\.?n\.?|u\.?k\.?|u\.?s\.?a?\.?|ussr|comm\.)(?=\W)", lambda m: m.group(1).upper(), t)
    return t


def simbolo(unres):
    """«R/45/11» -> «A/RES/45/11»."""
    unres = (unres or "").strip()
    if not unres or unres == "NA":
        return None
    m = re.fullmatch(r"R/(.+)", unres)
    return f"A/RES/{m.group(1)}" if m else unres


def url_resolucion(sim):
    return f"https://undocs.org/es/{sim}" if sim and sim.startswith("A/") else None


def _entero(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def cargar_voeten(ctx):
    ruta = RAW_DIR / "onu" / "UNVotes.csv"
    if not ruta.exists():
        ctx.log("   descargando el histórico de Voeten (393 MB, una sola vez)…")
        ruta = ctx.cache(VOETEN_URL, "UNVotes.csv", timeout=1800)
    ctx.log("   leyendo el histórico de Voeten…")
    csv.field_size_limit(10**9)
    cow = {}
    filas = defaultdict(list)
    cabecera = {}
    with open(ruta, encoding="utf-8", errors="replace", newline="") as fh:
        for d in csv.DictReader(fh):
            c = d["Country"]
            if len(c) == 3 and c.isupper():
                cow.setdefault(d["ccode"], COW_HISTORICO.get(d["ccode"], c))
            if d["date"][:4].isdigit() and int(d["date"][:4]) < ctx.desde:
                continue
            rcid = d["rcid"]
            if rcid not in cabecera:
                cabecera[rcid] = {k: d[k] for k in ("date", "unres", "amend", "para", "short", "descr", "importantvote",
                                                     "me", "nu", "di", "hr", "co", "ec", "yes", "no", "abstain", "session")}
            filas[rcid].append((d["ccode"], d["vote"]))
    ctx.log(f"   {len(cabecera)} votaciones; guardando…")
    asuntos, votaciones = {}, []
    for rcid in sorted(cabecera, key=lambda r: (cabecera[r]["date"], int(r))):
        h = cabecera[rcid]
        sim = simbolo(h["unres"])
        aid = f"onu:{sim}" if sim else f"onu:rcid{rcid}"
        temas = [k for k in ("me", "nu", "di", "hr", "co", "ec") if h[k] == "1"]
        titulo = _frase(h["descr"]) or _frase(h["short"]) or aid
        if aid not in asuntos:
            asuntos[aid] = Asunto(id=aid, titulo=titulo[:400], tipo="resolucion", fecha=h["date"], codigo=sim,
                                  url=url_resolucion(sim),
                                  extra={"etiqueta": _frase(h["short"]), "temas_voeten": temas, "sesion": h["session"]})
        tipo = "enmienda" if h["amend"] == "1" else "parcial" if h["para"] == "1" else "final"
        votos = []
        for ccode, voto in filas[rcid]:
            iso3 = cow.get(ccode)
            sentido = SENTIDO_VOETEN.get(voto)
            if iso3 and sentido:
                votos.append((iso3, paises.nombre(iso3), paises.region(iso3), sentido))
        si = sum(1 for v in votos if v[3] == "si")
        no = sum(1 for v in votos if v[3] == "no")
        votaciones.append(Votacion(
            id=f"onu:{rcid}", fecha=h["date"], asunto_id=aid, camara="onu-ag", numero=int(rcid),
            texto=None if titulo == _frase(h["descr"]) and tipo == "final" else _frase(h["descr"])[:600],
            tipo=tipo, a_favor=si, en_contra=no, abstenciones=sum(1 for v in votos if v[3] == "abstencion"),
            no_votan=sum(1 for v in votos if v[3] == "no_vota"),
            resultado="aprobada" if si > no else "rechazada", importante=int(h["importantvote"] == "1"),
            url=url_resolucion(sim), votos=votos))
        if len(votaciones) >= 300:
            ctx.guardar([asuntos.pop(v.asunto_id) for v in votaciones if v.asunto_id in asuntos], votaciones)
            votaciones = []
    ctx.guardar(list(asuntos.values()), votaciones)
    ctx.poner_marca("cow_iso3", cow)
    ctx.poner_marca("voeten", VOETEN_URL)


# ------------------------------------------------------------------ Biblioteca Digital de la ONU

SENTIDO_UNDL = {"y": "si", "yes": "si", "in favour": "si", "in favor": "si", "n": "no", "no": "no", "against": "no",
                "a": "abstencion", "abstain": "abstencion", "abstention": "abstencion", "abstaining": "abstencion",
                "x": "no_vota", "": "no_vota", "not voting": "no_vota", "non-voting": "no_vota"}


def _columna(cabecera, *claves):
    for c in cabecera:
        n = c.lower().strip()
        if any(n == k or n.startswith(k) for k in claves):
            return c
    return None


def importar_undl(ctx, texto, desde=VOETEN_HASTA):
    """Importa el CSV oficial de la Biblioteca Digital (un voto por fila) a partir de `desde`."""
    lector = csv.DictReader(io.StringIO(texto))
    cab = lector.fieldnames or []
    c_pais = _columna(cab, "ms_code", "member_state_code", "iso")
    c_voto = _columna(cab, "ms_vote", "vote")
    c_fecha = _columna(cab, "date", "vote_date")
    c_res = _columna(cab, "resolution")
    c_tit = _columna(cab, "title")
    c_id = _columna(cab, "undl_id", "record", "id")
    if not all((c_pais, c_voto, c_fecha, c_res)):
        raise ValueError(f"CSV de la Biblioteca Digital con columnas inesperadas: {cab[:20]}")
    grupos = defaultdict(list)
    for d in lector:
        fecha = (d[c_fecha] or "")[:10]
        if fecha <= desde:
            continue
        grupos[(d[c_id] if c_id else d[c_res], fecha)].append(d)
    asuntos, votaciones = {}, []
    for (clave, fecha), filas in sorted(grupos.items(), key=lambda kv: kv[0][1]):
        sim = (filas[0][c_res] or "").strip() or None
        aid = f"onu:{sim}" if sim else f"onu:undl{clave}"
        titulo = _frase(filas[0][c_tit]) if c_tit else (sim or aid)
        asuntos.setdefault(aid, Asunto(id=aid, titulo=(titulo or aid)[:400], tipo="resolucion", fecha=fecha, codigo=sim,
                                       url=url_resolucion(sim)))
        votos = []
        for d in filas:
            iso3 = (d[c_pais] or "").strip().upper()
            sentido = SENTIDO_UNDL.get((d[c_voto] or "").strip().lower())
            if len(iso3) == 3 and sentido:
                votos.append((iso3, paises.nombre(iso3), paises.region(iso3), sentido))
        si = sum(1 for v in votos if v[3] == "si")
        no = sum(1 for v in votos if v[3] == "no")
        votaciones.append(Votacion(
            id=f"onu:undl:{clave}", fecha=fecha, asunto_id=aid, camara="onu-ag", tipo="final", a_favor=si, en_contra=no,
            abstenciones=sum(1 for v in votos if v[3] == "abstencion"), no_votan=sum(1 for v in votos if v[3] == "no_vota"),
            resultado="aprobada" if si > no else "rechazada", url=url_resolucion(sim), votos=votos))
    ctx.guardar(list(asuntos.values()), votaciones)
    return len(votaciones)


_CHROME_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")


def _undl_csv_url(ctx):
    """URL del CSV actual de la Biblioteca Digital. Devuelve None si la web está bloqueada por WAF."""
    for url in (UNDL_JSON, UNDL_URL + "?ln=en"):
        try:
            datos = ctx.fetch(url)
            texto = datos.decode("utf-8", "replace")
            if url.endswith("recjson"):
                import json as _json
                meta = _json.loads(texto)
                registro = meta[0] if isinstance(meta, list) else meta
                for f in registro.get("files", []):
                    if f.get("eformat") == ".csv":
                        return f["url"]
            else:
                enlaces = re.findall(r'href="([^"]+/files/[^"]+\.csv)"', texto)
                if enlaces:
                    return enlaces[-1] if enlaces[-1].startswith("http") else "https://digitallibrary.un.org" + enlaces[-1]
        except Exception:
            pass
    return None


def _playwright_undl(ctx):
    """Abre un navegador real para pasar el WAF y descarga el CSV. Devuelve el texto del CSV o None.

    En Linux sin display (GitHub Actions) necesita xvfb:
      sudo apt-get install -y xvfb
      xvfb-run python -m concordia recoger --fuente onu
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    ctx.log("   la Biblioteca Digital requiere navegador real (WAF); abriendo Chrome…")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=False,
                args=["--disable-blink-features=AutomationControlled"],
            )
            context = browser.new_context(
                user_agent=_CHROME_UA,
                locale="es-ES",
                viewport={"width": 1280, "height": 800},
            )
            page = context.new_page()
            page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            page.goto(UNDL_URL + "?ln=en", wait_until="networkidle", timeout=30000)
            links = page.eval_on_selector_all("a[href*='.csv']", "els => els.map(e => e.href)")
            csv_url = links[-1] if links else None
            if not csv_url:
                ctx.log("   ! No se encontró el enlace al CSV en la Biblioteca Digital")
                browser.close()
                return None
            ctx.log(f"   descargando {csv_url.split('/')[-1]} (puede tardar varios minutos)…")
            cookies = context.cookies()
            browser.close()
        cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
        datos = ctx.fetch(csv_url, timeout=900, headers={"Cookie": cookie_str, "User-Agent": _CHROME_UA})
        return datos.decode("utf-8-sig", "replace")
    except Exception as e:
        ctx.log(f"   ! Playwright: {e}")
        return None


def recoger(ctx):
    if ctx.completo or not ctx.marca("voeten"):
        cargar_voeten(ctx)
    # CSV oficiales descargados a mano (tienen prioridad sobre la descarga automática).
    manuales = sorted((RAW_DIR / "onu" / "undl").glob("*.csv")) if (RAW_DIR / "onu" / "undl").exists() else []
    for ruta in manuales:
        n = importar_undl(ctx, ruta.read_text(encoding="utf-8-sig", errors="replace"))
        ctx.log(f"   {ruta.name}: {n} votaciones posteriores a {VOETEN_HASTA}")
    if manuales:
        ctx.poner_marca("undl_manual", [r.name for r in manuales])
        return
    # Descarga automática: primero intenta fetch directo, luego Playwright si el WAF bloquea.
    url = _undl_csv_url(ctx)
    if url is not None:
        ctx.log(f"   descargando {url.split('/')[-1]} de la Biblioteca Digital (puede tardar)…")
        n = importar_undl(ctx, ctx.fetch(url, timeout=600).decode("utf-8-sig", "replace"))
        ctx.log(f"   Biblioteca Digital: {n} votaciones posteriores a {VOETEN_HASTA}")
        return
    texto = _playwright_undl(ctx)
    if texto is None:
        ctx.log(f"   ! No se pudo descargar el CSV de la Biblioteca Digital."
                f" Descárgalo manualmente desde {UNDL_URL} y déjalo en data/raw/onu/undl/")
        return
    n = importar_undl(ctx, texto)
    ctx.log(f"   Biblioteca Digital (Playwright): {n} votaciones posteriores a {VOETEN_HASTA}")
