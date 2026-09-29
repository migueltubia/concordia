"""Finlandia: votaciones del pleno del Eduskunta (API oficial de datos abiertos, https://api.eduskunta.fi).

La API nueva del Eduskunta (la antigua, avoindata.eduskunta.fi, se retira a finales de 2026) tiene un
buscador que devuelve cada votación del pleno con el asunto (código del documento principal: «HE
29/2025 vp» proyecto del Gobierno, «KAA» iniciativa ciudadana, «VK» interpelación, «VNS» informe del
Gobierno…), el punto del orden del día, la lectura, lo que se vota («Mietintö JAA / X:n ehdotus EI»),
los totales y el voto de cada diputado con su grupo. Se pide por años naturales, en páginas de 100
votaciones (unas setenta peticiones para todo desde 2019). Se recoge desde 2019, lo que incluye el
final de la legislatura 2015-2019 (los plenos de enero a marzo de 2019 pertenecen al periodo de
sesiones de 2018).

Particularidades:
- Cada votación enfrenta dos propuestas (JAA / EI). La votación final es la de «aprobación / rechazo»
  en segunda lectura, la de confianza en las interpelaciones y comunicaciones del Gobierno y, en los
  asuntos de lectura única (informes, iniciativas ciudadanas), la del dictamen de la comisión frente a
  la alternativa que ganó las votaciones previas. Las propuestas de declaración («lausumaehdotus»), los
  artículos de la primera lectura y las partidas del presupuesto son enmiendas. Muchos proyectos se
  aprueban sin votación y no aparecen.
- Las votaciones anuladas («mitätöity») y las elecciones por papeleta sin recuento no se recogen.
- Los títulos de las partidas del presupuesto no nombran el proyecto: el título del asunto se pide a
  la ficha del asunto («valtiopäiväasia»).
- «Tyhjää» es la abstención y «Poissa» (ausente) es «no vota». Resultado: gana la propuesta con más
  votos (sí > no).
- Títulos en finés (también los hay en sueco; se usa el finés): las reglas no los leen y la ficha de la
  IA los resume en español.
"""

import re
from datetime import date, timedelta
from urllib.parse import quote

from .modelo import Asunto, Fuente, Votacion

FUENTE = Fuente(
    codigo="fin", pais="FIN", nombre="Eduskunta (Parlamento de Finlandia)", corto="Finlandia", tipo="parlamento",
    detalle="nominal", web="https://www.eduskunta.fi", desde=2019, idioma="otro",
    licencia="Datos abiertos del Eduskunta, CC BY 4.0",
    camaras={"fin-e": ("Eduskunta", "Eduskunta", 200)},
    partidos={
        "kok": ("Coalición Nacional (Kokoomus)", "KOK", "#006288"),
        "ps": ("Partido de los Finlandeses (Perussuomalaiset)", "PS", "#d9a400"),
        "sd": ("Partido Socialdemócrata de Finlandia", "SDP", "#e11931"),
        "kesk": ("Partido del Centro (Keskusta)", "KESK", "#01954b"),
        "vihr": ("Liga Verde (Vihreät)", "VIHR", "#61bf1a"),
        "vas": ("Alianza de la Izquierda (Vasemmistoliitto)", "VAS", "#f00a64"),
        "r": ("Partido Popular Sueco de Finlandia (RKP)", "RKP", "#ffd23f"),
        "kd": ("Democristianos de Finlandia", "KD", "#18359b"),
        "liik": ("Movimiento Ahora (Liike Nyt)", "LIIK", "#b41f79"),
        "sin": ("Futuro Azul (Sininen tulevaisuus)", "SIN", "#0a3a8c"),
        "tl": ("Movimiento Estrella (Tähtiliike)", "TL", "#c47c00"),
        "vkk": ("El Poder Pertenece al Pueblo (Valta kuuluu kansalle)", "VKK", "#7a5c3e"),
        "wr": ("Grupo Wille Rydman", "WR", "#898781"),
        "tv": ("Grupo Timo Vornanen", "TV", "#898781"),
        "erk": ("No adscritos (eduskuntaryhmään kuulumaton)", "No adscr.", "#a9a7a1"),
    },
    notas=("Votaciones del pleno con el voto de cada diputado; solo se vota con registro cuando hay propuestas "
           "enfrentadas, así que muchos proyectos se aprueban sin votación."),
)

API = "https://api.eduskunta.fi/api/v1"
WEB = "https://www.eduskunta.fi"
POR_PAGINA = 100
MARGEN_DIAS = 14

SENTIDO = {"Jaa": "si", "Ei": "no", "Tyhjää": "abstencion", "Poissa": "no_vota"}

# Algunos votos llegan sin la abreviatura del grupo (Ano Turtiainen en 2020, cuyo grupo se llamó luego «Valta
# kuuluu kansalle»): se deduce del nombre.
GRUPO_NOMBRE = [("kokoomu", "kok"), ("perussuomalai", "ps"), ("sosialidemokraat", "sd"), ("keskusta", "kesk"),
                ("vihre", "vihr"), ("vasemmisto", "vas"), ("ruotsalai", "r"), ("kristillisdemokraat", "kd"),
                ("liike nyt", "liik"), ("sininen", "sin"), ("tähtiliike", "tl"), ("ano turtiainen", "vkk"),
                ("valta kuuluu kansalle", "vkk"), ("wille rydman", "wr"), ("timo vornanen", "tv"), ("kuulumaton", "erk")]

FASE = {"Ensimmäinen käsittely": "1.ª lectura", "Toinen käsittely": "2.ª lectura", "Ainoa käsittely": "Lectura única",
        "Ainoa käsittely, muut asiat": "Lectura única", "Yksi käsittely": "Lectura única",
        "Lähetekeskustelu": "Remisión a comisión", "Kokous": "Presupuesto por partidas", "Vaaleja": "Elección"}

# Tipo de asunto por el tipo del documento principal.
TIPO_DOCUMENTO = {
    "HE": "ley", "LA": "ley", "KAA": "ley", "LJL": "ley", "VK": "mocion", "VNT": "mocion", "TPA": "mocion",
    "TAA": "mocion", "LTA": "mocion", "VNS": "resolucion", "K": "resolucion", "U": "resolucion", "E": "resolucion",
    "VAA": "nombramiento", "PNE": "procedimiento", "ETJ": "procedimiento",
}
# Asuntos de una sola lectura en los que la votación dictamen / alternativa es la que decide.
LECTURA_UNICA = ("VNS", "K", "KAA", "M", "VNT", "VK", "U", "E", "PNE", "ETJ")

PROCEDIMIENTO = ("lähettäminen", "lähettämisestä", "pöydällepano", "pöydälle", "päiväjärjestykseen", "kiireellis",
                 "istumajärjestys")


def _fi(x):
    return ((x or {}).get("fi") or "").strip() if isinstance(x, dict) else (x or "").strip()


def _limpio(t):
    return re.sub(r"\s+", " ", t or "").strip()


def clave_asunto(tunnus):
    """«HE 29/2025 vp» -> «HE-29-2025»."""
    return re.sub(r"[\s/]+", "-", re.sub(r"\s+vp$", "", tunnus.strip()))


def tipo_asunto(prefijo, titulo):
    t = titulo.lower()
    if prefijo == "HE" and re.search(r"(sopimu|pöytäkirj)\w*.*\b(hyväksymise|irtisanomise|liittymise)"
                                     r"|\bliittymise\w*.*(sopimu|pöytäkirj)", t):
        return "tratado"
    if prefijo == "M":
        return "nombramiento" if re.search(r"\bvalinta\b|valitseminen|\bvaali\b", t) else "otro"
    return TIPO_DOCUMENTO.get(prefijo, "otro")


def tipo_votacion(otsikko, kasittely, prefijo):
    t = otsikko.lower()
    if kasittely == "Lähetekeskustelu" or any(k in t for k in PROCEDIMIENTO):
        return "procedimiento"
    if prefijo == "VAA" or "pääministeriksi" in t or "valinnan hyväksyminen" in t:
        return "nombramiento"
    if "hyväksyminen" in t and "hylkääminen" in t:
        return "final"
    if re.match(r"\s*(nauttii luottamusta|luottamuslause)", t):
        return "final"
    if kasittely == "Ensimmäinen käsittely":
        return "enmienda"
    if prefijo in LECTURA_UNICA and re.match(r"\s*(kannanotto\s*[,:]?\s*)?(mietintö|valiokunnan ehdotus)\b", t) \
            and not re.search(r"lausuma|§|vastalauseen \d+ mukaiset", t):
        return "final"
    return "enmienda" if t else "otra"


def es_partida(kohta):
    """Votaciones del presupuesto por partidas: el punto es la sección, no el proyecto."""
    return (_fi(kohta.get("kasittelyotsikkonimi")) == "Kokous" or "budjetin" in _fi(kohta.get("kasittelyvaihenimi")).lower()
            or re.match(r"(Pääluokka|Osasto|Yleisperustelut)\b", _fi(kohta.get("otsikko"))))


def grupo(ctx, m):
    cod = _fi(m.get("edkryhmalyhenne"))
    nombre = _fi(m.get("eduskuntaryhma"))
    if not cod:
        n = nombre.lower()
        cod = next((c for clave, c in GRUPO_NOMBRE if clave in n), None) or (re.sub(r"\W+", "-", n).strip("-")[:20] or "erk")
    if cod not in FUENTE.partidos:
        ctx.partido(cod, nombre or cod, cod.upper())
    return cod


def _titulo_documento(ctx, tunnus, cache):
    if tunnus not in cache:
        try:
            d = ctx.json(f"{API}/valtiopaivaasiat/{quote(tunnus, safe='')}", headers={"Accept": "application/json"})
            cache[tunnus] = _limpio(_fi(d.get("nimeke")))
        except Exception as e:
            ctx.log(f"   ! sin ficha de {tunnus}: {e}")
            cache[tunnus] = ""
    return cache[tunnus]


def _convertir(ctx, a, asuntos, titulos):
    """Una votación de la API -> Votacion (y su Asunto en `asuntos`), o None si no se recoge."""
    if a.get("aanestysmitatoity"):
        return None
    tulos = a.get("aanestystulos") or {}
    jaa, ei, tyhjia = tulos.get("jaa") or 0, tulos.get("ei") or 0, tulos.get("tyhjia") or 0
    if jaa + ei + tyhjia == 0:
        return None
    fecha = (a.get("aanestysalkuaika") or a.get("istuntopvm") or "")[:10]
    kohta = a.get("kohta") or {}
    asiak = kohta.get("asiakirjat") or {}
    tunnus = _limpio(_fi(asiak.get("paaasiakirjaEduskuntatunnus")))
    prefijo = (asiak.get("paaasiakirjaAsiatyyppi") or (re.match(r"[A-ZÄÖ]+", tunnus) or [""])[0]).strip()
    kasittely = _fi(kohta.get("kasittelyotsikkonimi"))
    otsikko_kohta = _limpio(_fi(kohta.get("otsikko")).split(" | ")[0])
    partida = es_partida(kohta)
    if tunnus and re.match(r"[A-ZÄÖ]+ \d+/\d{4}", tunnus):
        aid = f"fin:{clave_asunto(tunnus)}"
        if aid not in asuntos:
            titulo = (_titulo_documento(ctx, tunnus, titulos) if partida else otsikko_kohta) or otsikko_kohta or tunnus
            asuntos[aid] = Asunto(id=aid, titulo=titulo[:400], tipo=tipo_asunto(prefijo, titulo), fecha=fecha, codigo=tunnus,
                                  url=f"{WEB}/asiat-ja-aanestykset/valtiopaivaasiat/{quote(tunnus, safe='')}")
    else:
        aid = f"fin:{a.get('istunnonTunniste')}:{kohta.get('tunniste')}"
        asuntos.setdefault(aid, Asunto(id=aid, titulo=(otsikko_kohta or "Asunto sin título")[:400],
                                       tipo=tipo_asunto(prefijo, otsikko_kohta), fecha=fecha))
    otsikko = _limpio(_fi(a.get("aanestysotsikko")))
    partes = [FASE.get(kasittely, kasittely)]
    if partida and otsikko_kohta:
        partes.append(otsikko_kohta)
    if otsikko:
        partes.append(otsikko)
    votos = []
    for m in a.get("aanestystapahtumat") or []:
        nombre = " ".join(x for x in (m.get("etunimi"), m.get("sukunimi")) if x)
        votos.append((f"fin:{m['henkilonumero']}", nombre, grupo(ctx, m), SENTIDO.get(_fi(m.get("kayttaytyminen")), "no_vota")))
    vuosi, istunto, numero = a.get("istuntovpvuosi"), a.get("istuntonumero"), a.get("aanestysnumero")
    return Votacion(
        id=f"fin:{a['id']}", fecha=fecha, asunto_id=aid, camara="fin-e", numero=int(numero) if numero else None,
        texto=" · ".join(p for p in partes if p) or None, tipo=tipo_votacion(otsikko, kasittely, prefijo),
        a_favor=jaa, en_contra=ei, abstenciones=tyhjia, no_votan=tulos.get("poissa"), mayoria="simple",
        resultado="aprobada" if jaa > ei else "rechazada",
        url=f"{WEB}/aanestystulos/{numero}/{istunto}/{vuosi}" if numero and istunto and vuosi else None,
        votos=votos or None)


def recoger(ctx):
    hoy = date.today()
    inicio = date(ctx.desde, 1, 1)
    ultima = ctx.ultima_fecha()
    if ultima and not ctx.completo:
        inicio = max(inicio, date.fromisoformat(ultima) - timedelta(days=MARGEN_DIAS))
    titulos = {}
    for anio in range(inicio.year, hoy.year + 1):
        desde, hasta = max(inicio, date(anio, 1, 1)), date(anio + 1, 1, 1)
        indice, total = 0, None
        while total is None or indice < total:
            d = ctx.json(f"{API}/search", timeout=180, headers={"Accept": "application/json"}, post_json={
                "category": "aanestys", "maxResults": POR_PAGINA, "startFromIndex": indice,
                "expression": {"and": [{"property": "aanestysalkuaika", "fromDate": desde.isoformat(),
                                        "toDate": hasta.isoformat()}]},
                "sort": [{"property": "aanestysalkuaika", "ascending": True}, {"property": "id", "ascending": True}],
            })
            total = (d.get("searchMetadata") or {}).get("totalResultCount") or 0
            pagina = [r["aanestys"] for r in d.get("results") or [] if r.get("aanestys")]
            if not pagina:
                break
            indice += len(pagina)
            asuntos, votaciones = {}, []
            for a in pagina:
                v = _convertir(ctx, a, asuntos, titulos)
                if v and v.fecha >= f"{ctx.desde}-01-01":
                    votaciones.append(v)
            usados = {v.asunto_id for v in votaciones}
            ctx.guardar([x for x in asuntos.values() if x.id in usados], votaciones)
            ctx.log(f"   {anio}: {min(indice, total)}/{total}")
