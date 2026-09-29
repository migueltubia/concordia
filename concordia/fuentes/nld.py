"""Países Bajos: votaciones de la Tweede Kamer (Gegevensmagazijn, API OData v4 oficial).

El Gegevensmagazijn de la Tweede Kamer (https://gegevensmagazijn.tweedekamer.nl/OData/v4/2.0/) da cada
decisión del pleno (Besluit) con el asunto (Zaak) que decide y su voto (Stemming). Casi todo se vota a mano
alzada por grupo (fractie): la fuente da, por grupo, «Voor/Tegen/Niet deelgenomen» y su tamaño; si un
diputado se aparta de su grupo aparece además una fila suya. Las votaciones nominales (hoofdelijk, unas
decenas al año) traen el voto de cada diputado. Lo que se aprueba sin votación (hamerstukken) no tiene
Stemming y no se recoge.

Cada moción (motie) es un asunto; las enmiendas (amendementen) y la votación final de un proyecto de ley
se agrupan en el asunto del expediente (Kamerstukdossier). Los proyectos de aprobación de tratados
(«Goedkeuring van het … Verdrag») son «tratado». Los títulos están en neerlandés: la ficha la hace la IA.

El total de cada votación es la suma de los grupos, como en el acta; cuando un diputado vota distinto que su
grupo se le cuenta aparte y se le resta al grupo (tweedekamer.nl no lo resta). Los votos marcados «Vergissing»
(el grupo dice haberse equivocado) cuentan como se emitieron, igual que en el resultado oficial.

Se recoge por meses a partir de la fecha de la sesión de votaciones (Activiteit): una página de 250 decisiones
tarda de 5 a 25 s y la recogida completa desde 2019 (unas 33.000 votaciones) unos 11 minutos. Los meses
cerrados se marcan y no se vuelven a pedir.
"""

import re
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from .modelo import Asunto, Fuente, Votacion

FUENTE = Fuente(
    codigo="nld", pais="NLD", nombre="Tweede Kamer de los Países Bajos", corto="Países Bajos", tipo="parlamento",
    detalle="grupo", web="https://www.tweedekamer.nl/kamerstukken/stemmingsuitslagen", desde=2019, idioma="otro",
    licencia="Open data de la Tweede Kamer: CC0 1.0 (dominio público)",
    camaras={"nld-tk": ("Tweede Kamer (Cámara de Representantes)", "Tweede Kamer", 150)},
    partidos={
        "VVD": ("Partido Popular por la Libertad y la Democracia", "VVD", "#ff7709"),
        "PVV": ("Partido por la Libertad", "PVV", "#0e2c5c"),
        "CDA": ("Llamamiento Demócrata Cristiano", "CDA", "#007b5f"),
        "D66": ("Demócratas 66", "D66", "#01af40"),
        "GroenLinks": ("GroenLinks (Izquierda Verde)", "GL", "#48a832"),
        "PvdA": ("Partido del Trabajo", "PvdA", "#df111a"),
        "GroenLinks-PvdA": ("GroenLinks-PvdA", "GL-PvdA", "#c8102e"),
        "PRO": ("Países Bajos Progresista (GroenLinks-PvdA)", "PRO", "#b3123e"),
        "SP": ("Partido Socialista", "SP", "#ee2e24"),
        "ChristenUnie": ("Unión Cristiana", "CU", "#00a5e8"),
        "PvdD": ("Partido por los Animales", "PvdD", "#006b2d"),
        "50PLUS": ("50PLUS", "50PLUS", "#92278f"),
        "SGP": ("Partido Político Reformado", "SGP", "#e96b10"),
        "DENK": ("DENK", "DENK", "#00b7b2"),
        "FVD": ("Foro para la Democracia", "FvD", "#841818"),
        "JA21": ("JA21", "JA21", "#242b57"),
        "BBB": ("Movimiento Campesino-Ciudadano", "BBB", "#95c11f"),
        "NSC": ("Nuevo Contrato Social", "NSC", "#f0c400"),
        "Volt": ("Volt", "Volt", "#502379"),
        "BIJ1": ("BIJ1", "BIJ1", "#f5d000"),
        "Groep Markuszower": ("Grupo Markuszower (escisión del PVV)", "Gr. Markuszower", "#3d5a8a"),
        "Keijzer": ("Diputada Keijzer", "Keijzer", "#898781"),
        "Van Haga": ("Diputado Van Haga", "Van Haga", "#898781"),
        "Groep Van Haga": ("Grupo Van Haga", "Gr. Van Haga", "#6d6a64"),
        "Van Kooten-Arissen": ("Diputada Van Kooten-Arissen", "vKA", "#898781"),
        "Krol": ("Diputado Krol", "Krol", "#898781"),
        "Groep Krol/vKA": ("Grupo Krol/Van Kooten-Arissen", "Krol/vKA", "#898781"),
        "Fractie Den Haan": ("Grupo Den Haan", "Den Haan", "#898781"),
        "Omtzigt": ("Diputado Omtzigt", "Omtzigt", "#898781"),
        "Gündoğan": ("Diputada Gündoğan", "Gündoğan", "#898781"),
        "Ephraim": ("Diputado Ephraim", "Ephraim", "#898781"),
    },
    notas="Voto por grupo (fractie) en las votaciones a mano alzada y de cada diputado en las nominales (hoofdelijk); "
          "lo aprobado sin votación (hamerstukken) no se recoge.",
)

API = "https://gegevensmagazijn.tweedekamer.nl/OData/v4/2.0"
WEB = "https://www.tweedekamer.nl/kamerstukken"
CABECERAS = {"Accept": "application/json"}
SENTIDO = {"Voor": "si", "Tegen": "no", "Niet deelgenomen": "no_vota"}
COLUMNA = {"Voor": 0, "Tegen": 1, "Niet deelgenomen": 3}  # en (sí, no, abstención, no vota)

# Lo que se pide de cada decisión: el voto, el asunto con su expediente y su documento principal (para la URL
# de la ficha) y el punto del orden del día con la sesión de votaciones (la fecha).
EXPAND = (
    "Stemming($filter=Verwijderd eq false;$select=Soort,FractieGrootte,ActorNaam,ActorFractie,Vergissing,Persoon_Id,Fractie_Id;"
    "$expand=Persoon($select=Roepnaam,Tussenvoegsel,Achternaam)),"
    "Zaak($select=Id,Nummer,Soort,Titel,Onderwerp,GestartOp,Volgnummer;"
    "$expand=Kamerstukdossier($select=Nummer,Toevoeging,Titel),"
    "Document($select=DocumentNummer;$filter=Verwijderd eq false;$orderby=Datum;$top=1)),"
    "Agendapunt($select=Nummer,Volgorde;$expand=Activiteit($select=Datum))"
)

# Clases de asunto (Zaak.Soort) que se agrupan en el asunto de su expediente: el proyecto y sus enmiendas.
DE_EXPEDIENTE = {"Wetgeving", "Initiatiefwetgeving", "Begroting", "Amendement", "Wijzigingen voorgesteld door de regering",
                 "Verdrag", "Wijziging RvO"}
ENMIENDAS = {"Amendement", "Wijzigingen voorgesteld door de regering"}
TRATADO = re.compile(r"\b(verdrag|overeenkomst|protocol|akkoord|handvest|statuut|conventie|memorandum|verdragen)", re.I)
PROCEDIMIENTO = ("controversi", "behandelvoorbehoud", "comptabiliteitswet", "reglement van orde", "presidium", "werkwijze",
                 "procedure", "agenda", "uitstel", "rondetafelgesprek", "hoorzitting", "debat", "ontoelaatbaar",
                 "geloofsbrieven", "gedragscode")


def _todas(ctx, url):
    """Sigue las páginas (@odata.nextLink, 250 por página) de una consulta."""
    salida = []
    while url:
        d = ctx.json(url, headers=CABECERAS)
        salida += d.get("value") or []
        url = d.get("@odata.nextLink")
    return salida


def _mes(ctx, inicio, fin):
    filtro = (f"Verwijderd eq false and Stemming/any(s: s/Verwijderd eq false)"
              f" and Agendapunt/Activiteit/Datum ge {inicio}T00:00:00Z and Agendapunt/Activiteit/Datum lt {fin}T00:00:00Z")
    return _todas(ctx, f"{API}/Besluit?" + urllib.parse.urlencode(
        {"$filter": filtro, "$select": "Id,StemmingsSoort,BesluitSoort,BesluitTekst,AgendapuntZaakBesluitVolgorde",
         "$expand": EXPAND, "$orderby": "Id"}, quote_via=urllib.parse.quote))


def _limpio(t):
    t = re.sub(r"\s+", " ", t or "").strip()
    return re.sub(r"\s*\(t\.v\.v\.[^)]*\)\s*$", "", t)  # «(t.v.v. 21501-02-3022)»: sustituye a una moción anterior


def _expediente(zaak):
    """(número legible, tramo de la URL) del Kamerstukdossier: «36915-XVII»; «(R2096)» (rijkswet) no cuenta."""
    ks = (zaak.get("Kamerstukdossier") or [None])[0]
    if not ks or not ks.get("Nummer"):
        return None, None
    toev = (ks.get("Toevoeging") or "").strip()
    numero = f"{ks['Nummer']}-{toev}" if toev and not toev.startswith("(") else str(ks["Nummer"])
    return numero, ks


def tipo_expediente(titulo, soort):
    t = (titulo or "").lower()
    if soort == "Wijziging RvO" or any(k in t for k in ("reglement van orde", "gedragscode leden", "raming der voor de")):
        return "procedimiento"  # reglamento, código de conducta y presupuesto propio de la Cámara
    if soort == "Verdrag" or (re.search(r"\b(goedkeuring|opzegging)\b", t) and TRATADO.search(t)):
        return "tratado"
    return "ley"


def tipo_zaak(soort, titulo):
    """Tipo de un asunto que no es un proyecto: mociones, cartas de la Mesa o de comisiones…"""
    if soort == "Motie":
        return "mocion"
    if soort in DE_EXPEDIENTE:  # un proyecto sin expediente (no debería pasar)
        return tipo_expediente(titulo, soort)
    t = (titulo or "").lower()
    if any(k in t for k in PROCEDIMIENTO):
        return "procedimiento"
    if any(k in t for k in ("benoeming", "voordracht", "kandidaat", "verkiezing van")):
        return "nombramiento"
    return "otro"


def resultado(besluit, si, no):
    s = f"{besluit.get('BesluitSoort') or ''} {besluit.get('BesluitTekst') or ''}".lower()
    if any(k in s for k in ("niet aangenomen", "verworpen", "gestaakt")):  # empate: no se aprueba
        return "rechazada"
    if "aangenomen" in s:
        return "aprobada"
    return "aprobada" if si > no else "rechazada"


def _nombre(s):
    p = s.get("Persoon") or {}
    if p.get("Achternaam"):
        return " ".join(x for x in (p.get("Roepnaam"), (p.get("Tussenvoegsel") or "").lower(), p["Achternaam"]) if x)
    return s.get("ActorNaam")


def votos_de(ctx, stemmingen, fracciones):
    """Voto nominal [(id, nombre, fractie, sentido)] o por grupo {fractie: (sí, no, abstención, no vota)}.

    A mano alzada hay una fila por grupo con su tamaño; un diputado que se aparta de su grupo tiene fila propia
    y la de su grupo sigue contándolo: se le resta al grupo. En la nominal solo hay filas de diputados.
    «Vergissing» marca un voto que el grupo declara equivocado: la Cámara lo cuenta tal cual (así sale en
    tweedekamer.nl y en el resultado), y aquí también.
    """
    for s in stemmingen:
        f = s.get("ActorFractie") or "?"
        if f not in FUENTE.partidos:
            nombre, siglas = fracciones.get(s.get("Fractie_Id"), (None, None))
            ctx.partido(f, nombre or f, siglas or f, "#898781")
    grupos = {s.get("ActorFractie") or "?": s for s in stemmingen if not s.get("Persoon_Id")}
    personas = [s for s in stemmingen if s.get("Persoon_Id")]
    if not grupos:
        return [(f"nld:{s['Persoon_Id']}", _nombre(s), s.get("ActorFractie") or "?", SENTIDO.get(s.get("Soort"), "no_vota"))
                for s in personas], None
    cuenta = {}
    for f, s in grupos.items():
        cuenta.setdefault(f, [0, 0, 0, 0])[COLUMNA.get(s.get("Soort"), 3)] += s.get("FractieGrootte") or 0
    for s in personas:
        f = s.get("ActorFractie") or "?"
        c = cuenta.setdefault(f, [0, 0, 0, 0])
        if f in grupos:
            j = COLUMNA.get(grupos[f].get("Soort"), 3)
            c[j] = max(0, c[j] - 1)
        c[COLUMNA.get(s.get("Soort"), 3)] += 1
    return None, {f: tuple(c) for f, c in cuenta.items()}


def convertir(ctx, besluit, fracciones):
    """(Asunto, Votacion) de una decisión con votación, o None si no tiene asunto o fecha."""
    zaken = besluit.get("Zaak") or []
    act = (besluit.get("Agendapunt") or {}).get("Activiteit") or {}
    if not zaken or not act.get("Datum"):
        return None
    zaak = zaken[0]
    fecha = act["Datum"][:10]
    soort = zaak.get("Soort") or ""
    nummer = zaak.get("Nummer")
    onderwerp = _limpio(zaak.get("Onderwerp") or zaak.get("Titel"))
    doc = (zaak.get("Document") or [{}])[0].get("DocumentNummer")
    url_zaak = f"{WEB}/detail?id={nummer}&did={doc}" if doc else None
    agendapunt = (besluit.get("Agendapunt") or {}).get("Nummer")
    url_stemming = f"{WEB}/stemmingsuitslagen/detail?id={agendapunt}" if agendapunt else None
    expediente, ks = _expediente(zaak)
    volg = zaak.get("Volgnummer")
    if soort in DE_EXPEDIENTE and expediente:
        # El proyecto: su título es el del expediente, igual venga de una enmienda o de la votación final.
        titulo = _limpio(ks.get("Titel")) or onderwerp
        tipo_a = tipo_expediente(titulo, soort)
        propio = soort not in ENMIENDAS
        url_a = (f"{WEB}/wetsvoorstellen/detail?cfg=wetsvoorsteldetails&qry=wetsvoorstel%3A{expediente}"
                 if tipo_a != "procedimiento" else (url_zaak if propio else None))
        asunto = Asunto(id=f"nld:{expediente}", titulo=titulo[:400], tipo=tipo_a, codigo=f"Kamerstuk {expediente}",
                        fecha=(zaak.get("GestartOp") or fecha)[:10] if propio else fecha, url=url_a)
        if soort in ENMIENDAS:
            texto = onderwerp + (f" (nr. {volg})" if volg else "")
            tipo_v, url_v = "enmienda", url_zaak or url_stemming
        else:
            texto = "Eindstemming over het wetsvoorstel" if tipo_a != "procedimiento" else f"Eindstemming: {onderwerp}"
            tipo_v, url_v = "final", url_stemming or url_zaak
    else:
        codigo = f"Kamerstuk {expediente}, nr. {volg}" if expediente and volg else (f"Kamerstuk {expediente}" if expediente else nummer)
        extra = None
        if ks and ks.get("Titel") and ks["Titel"].strip().lower() not in onderwerp.lower():
            extra = {"etiqueta": _limpio(ks["Titel"])[:200]}
        asunto = Asunto(id=f"nld:{nummer}", titulo=onderwerp[:400], tipo=tipo_zaak(soort, onderwerp), codigo=codigo,
                        fecha=(zaak.get("GestartOp") or fecha)[:10], url=url_zaak or url_stemming, extra=extra)
        texto, url_v = onderwerp, url_zaak or url_stemming
        tipo_v = "enmienda" if soort in ENMIENDAS else "final"
    votos, por_partido = votos_de(ctx, besluit.get("Stemming") or [], fracciones)
    if votos:
        si = sum(1 for v in votos if v[3] == "si")
        no = sum(1 for v in votos if v[3] == "no")
        nv = sum(1 for v in votos if v[3] == "no_vota")
    else:
        si, no, nv = (sum(c[i] for c in por_partido.values()) for i in (0, 1, 3))
    numero = ((besluit.get("Agendapunt") or {}).get("Volgorde") or 0) * 1000 + (besluit.get("AgendapuntZaakBesluitVolgorde") or 0)
    if besluit.get("StemmingsSoort") == "Hoofdelijk":
        texto += " (hoofdelijke stemming)"
    return asunto, Votacion(
        id=f"nld:{besluit['Id']}", fecha=fecha, asunto_id=asunto.id, camara="nld-tk", numero=numero, texto=texto[:600],
        tipo=tipo_v, a_favor=si, en_contra=no, abstenciones=0, no_votan=nv, resultado=resultado(besluit, si, no),
        url=url_v, votos=votos, por_partido=por_partido)


def _meses(desde, hasta):
    d = date(desde, 1, 1)
    while d <= hasta:
        sig = date(d.year + d.month // 12, d.month % 12 + 1, 1)
        yield d, sig
        d = sig


def recoger(ctx):
    hoy = date.today()
    fracciones = {f["Id"]: (f.get("NaamNL"), f.get("Afkorting"))
                  for f in _todas(ctx, f"{API}/Fractie?$select=Id,Afkorting,NaamNL")}
    cerrados = set(ctx.marca("meses", []))
    meses = [(a, b) for a, b in _meses(ctx.desde, hoy) if ctx.completo or a.isoformat()[:7] not in cerrados]
    ctx.log(f"   {len(meses)} meses por pedir")
    with ThreadPoolExecutor(6) as ex:  # el servidor no da mucho más en paralelo
        for (inicio, fin), besluiten in zip(meses, ex.map(lambda m: _mes(ctx, m[0].isoformat(), m[1].isoformat()), meses)):
            asuntos, votaciones = {}, []
            for b in besluiten:
                r = convertir(ctx, b, fracciones)
                if not r or r[1].fecha < f"{ctx.desde}-01-01":
                    continue
                asunto, votacion = r
                previo = asuntos.get(asunto.id)
                if previo:  # la fecha más antigua y la URL que haya
                    asunto.fecha = min(previo.fecha, asunto.fecha)
                    asunto.url = asunto.url or previo.url
                asuntos[asunto.id] = asunto
                votaciones.append(votacion)
            votaciones.sort(key=lambda v: (v.fecha, v.numero))
            for i in range(0, len(votaciones), 300):
                lote = votaciones[i:i + 300]
                ctx.guardar([asuntos[a] for a in dict.fromkeys(v.asunto_id for v in lote)], lote)
            ctx.log(f"   {inicio.isoformat()[:7]}: {len(votaciones)} votaciones, {len(asuntos)} asuntos")
            if fin + timedelta(days=21) < hoy:  # mes cerrado: no se vuelve a pedir
                cerrados.add(inicio.isoformat()[:7])
                ctx.poner_marca("meses", sorted(cerrados))
