"""Dinamarca: votaciones del Folketing (datos abiertos oficiales, OData de https://oda.ft.dk).

La API OData del Folketing (Folketingets Åbne Data, «ODA») da cada votación del pleno (Afstemning) con
su sesión (Møde), la fase del asunto en que se vota (Sagstrin) y el asunto (Sag: «L 12» proyecto de ley,
«B 16» propuesta de resolución, «V 3» propuesta de resolución tras una interpelación), y el voto de cada
diputado (Stemme: for, imod, fravær, hverken for eller imod). El grupo de cada diputado sale de su
pertenencia (AktørAktør) a los grupos parlamentarios de cada «samling» (periodo de sesiones anual, de
octubre a octubre; hay dos en los años con elecciones). Se recoge desde 2019.

Particularidades:
- Todo lo que se vota en el pleno se vota con el sistema electrónico. Un 7 % de las votaciones no trae el
  voto de cada diputado (casi todo junio de 2020, en la pandemia, y jornadas largas como el 19-12-2024,
  el 3-6-2025 o el 19-12-2025): de esas se guarda el voto por grupo del acta (konklusion), que dice qué
  grupos votaron qué y cuántos votos hubo en cada sentido. Cuántos de cada grupo no lo dice: se reparte en
  proporción a los escaños (estimación) y el texto de la votación lo avisa.
- Grupos: los códigos de la fuente (S, V, DF...); los independientes, «UFG» (uden for folketingsgrupperne).
- Un proyecto de ley se vota en 2.ª lectura (enmiendas) y en 3.ª lectura (enmiendas y votación final,
  «endelig vedtagelse»); una propuesta de resolución (B) se vota en su 2.ª y última lectura. Si en 2.ª
  lectura se divide un proyecto («L 86» -> «L 86 A» y «L 86 B»), cada parte es un asunto propio.
- Las propuestas de resolución (V) que cierran una interpelación (F) o un debate sobre un informe del
  Gobierno (R) se agrupan en un asunto por debate: se suelen votar las de la oposición y la que sale
  adelante, que es la última y la decisiva.
- La API da como mucho 100 filas por página y no deja expandir más de 100 votos por votación: se piden
  los votos de cada votación aparte (dos páginas), con pocos hilos.
- Los títulos están en danés: las reglas no los leen y la ficha la hace la IA.
"""

import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from urllib.parse import quote

from .modelo import Asunto, Fuente, Votacion

FUENTE = Fuente(
    codigo="dnk", pais="DNK", nombre="Folketing de Dinamarca", corto="Dinamarca", tipo="parlamento",
    detalle="nominal", web="https://www.ft.dk", desde=2019, idioma="otro",
    licencia="Condiciones de uso de los datos abiertos del Folketing (reutilización libre citando la fuente)",
    camaras={"dnk-f": ("Folketing", "Folketing", 179)},
    partidos={
        "S": ("Socialdemócratas (Socialdemokratiet)", "S", "#a82721"),
        "V": ("Venstre, Partido Liberal de Dinamarca", "V", "#254264"),
        "DF": ("Partido Popular Danés (Dansk Folkeparti)", "DF", "#e3b505"),
        "RV": ("Partido Social Liberal (Radikale Venstre)", "RV", "#733280"),
        "SF": ("Partido Popular Socialista (SF)", "SF", "#e07ea8"),
        "EL": ("Alianza Rojiverde (Enhedslisten)", "EL", "#d0004d"),
        "KF": ("Partido Popular Conservador (Det Konservative Folkeparti)", "KF", "#96b226"),
        "LA": ("Alianza Liberal (Liberal Alliance)", "LA", "#3fb2be"),
        "ALT": ("La Alternativa (Alternativet)", "ALT", "#2b8738"),
        "NB": ("Nueva Derecha (Nye Borgerlige)", "NB", "#127b7f"),
        "M": ("Moderados (Moderaterne)", "M", "#b48cd2"),
        "DD": ("Demócratas de Dinamarca (Danmarksdemokraterne)", "DD", "#6a8bc4"),
        "BP": ("Partido de los Ciudadanos (Borgernes Parti)", "BP", "#1f3a5f"),
        "KD": ("Democristianos (Kristendemokraterne)", "KD", "#f7a800"),
        "FG": ("Verdes Libres (Frie Grønne)", "FG", "#8cc63f"),
        "SIU": ("Siumut (Groenlandia)", "SIU", "#ef3e42"),
        "IA": ("Inuit Ataqatigiit (Groenlandia)", "IA", "#c4122f"),
        "N": ("Naleraq (Groenlandia)", "N", "#f39200"),
        "NQ": ("Nunatta Qitornai (Groenlandia)", "NQ", "#2e8b57"),
        "SP": ("Partido de la Unión (Sambandsflokkurin, Feroe)", "SP", "#1b5299"),
        "JF": ("Partido Socialdemócrata (Javnaðarflokkurin, Feroe)", "JF", "#d71921"),
        "T": ("República (Tjóðveldi, Feroe)", "T", "#2f8f3a"),
        "UFG": ("Fuera de los grupos parlamentarios", "Indep.", "#898781"),
    },
    notas="Voto de cada diputado en todas las votaciones del pleno desde 2019; en un 7 % (junio de 2020 y algunas "
          "jornadas largas) solo hay el acta: voto por grupo, con el reparto de votos entre grupos estimado.",
)

API = "https://oda.ft.dk/api/"
WEB = "https://www.ft.dk/samling"
POR_PAGINA = 100          # máximo de la API
LOTE = 150                # votaciones por guardado
MARGEN_DIAS = 14          # se revisa lo de las dos últimas semanas (votos que se corrigen o llegan tarde)
SENTIDO = {1: "si", 2: "no", 3: "no_vota", 4: "abstencion"}   # Stemmetype: for, imod, fravær, hverken for eller imod
TRAMO = {"L": "lovforslag", "B": "beslutningsforslag", "F": "forespoergsel", "R": "redegoerelse", "V": "vedtagelse"}

# Ratificación, adhesión, denuncia o aplicación de tratados y convenios internacionales. «Aftale» a secas
# no basta: «gennemførelse af aftale om ...» suele ser un acuerdo político entre partidos, y «overenskomst»
# también es el convenio colectivo.
TRATADO = re.compile(
    r"ratifikation|ratificer|tiltrædelse af|tilslutning på mellemstatsligt grundlag|"
    r"(?:gennemførelse|opsigelse|indgåelse|ændring) af [^.()]{0,60}dobbeltbeskatnings|dobbeltbeskatnings\w+ (?:mellem|med)\b|"
    r"multilateral konvention|tillægsprotokol|aftalegrundlag|forsvarssamarbejds?aftale|"
    r"(?:overenskomst|aftale|konvention|protokol|traktat)\w* (?:af \d+\. \w+ \d{4} )?mellem (?:kongeriget |den )?danmark|"
    r"mellem (?:kongeriget )?danmarks? (?:regering )?(?:og|sammen|på den ene side)|"
    r"(?:indgåelse|godkendelse|opsigelse) af (?:\w+ )?(?:overenskomst|konvention|protokol|traktat)|"
    r"udtræd\w* af .{0,60}(?:konvention|traktat)|samtykke til .{0,80}(?:overenskomst|konvention|traktat)", re.I)


# ------------------------------------------------------------------ API

def _url(entidad, **params):
    q = "&".join(f"${k}={quote(str(v), safe=chr(39) + ',()/=:')}" for k, v in params.items())
    return f"{API}{quote(entidad)}?$format=json&{q}"


def _todas(ctx, entidad, **params):
    """Todas las filas de una consulta, página a página (la API no pasa de 100 por página)."""
    filas, skip = [], 0
    while True:
        pagina = ctx.json(_url(entidad, top=POR_PAGINA, skip=skip, **params))["value"]
        filas += pagina
        if len(pagina) < POR_PAGINA:
            return filas
        skip += POR_PAGINA


def _por_ids(ctx, entidad, ids, select):
    """Filas de una entidad por id, de 40 en 40 (el filtro va en la URL)."""
    ids, filas = sorted(set(ids)), []
    for i in range(0, len(ids), 40):
        filtro = " or ".join(f"id eq {x}" for x in ids[i:i + 40])
        filas += _todas(ctx, entidad, filter=filtro, select=select, orderby="id")
    return filas


def _dia(fecha):
    return (fecha or "")[:10]


def _limpio(texto, n=400):
    t = re.sub(r"\s+", " ", texto or "").strip()
    return t if len(t) <= n else t[:n - 1].rstrip() + "…"


# ------------------------------------------------------------------ grupos parlamentarios

def grupos_de_samling(ctx, periodeid):
    """{aktørid: [(desde, hasta, grupo, rol)]} y {aktørid: nombre} de los diputados de una samling.

    La relación persona-grupo está unas veces como persona -> grupo y otras como grupo -> persona (y no
    siempre las dos): se leen ambas.
    """
    miembros, nombres = {}, {}
    sel = "fraaktørid,tilaktørid,startdato,slutdato,rolleid,FraAktør/navn,FraAktør/typeid,FraAktør/gruppenavnkort," \
          "TilAktør/navn,TilAktør/typeid,TilAktør/gruppenavnkort"
    for lado, otro in (("TilAktør", "FraAktør"), ("FraAktør", "TilAktør")):
        filas = _todas(ctx, "AktørAktør", filter=f"{lado}/periodeid eq {periodeid} and {lado}/typeid eq 4",
                       expand="FraAktør,TilAktør", select=sel, orderby="id")
        for r in filas:
            grupo, persona = r[lado], r[otro]
            if not persona or persona.get("typeid") != 5:
                continue
            pid = r["fraaktørid"] if otro == "FraAktør" else r["tilaktørid"]
            nombres[pid] = persona.get("navn")
            codigo = (grupo or {}).get("gruppenavnkort") or "UFG"
            miembros.setdefault(pid, set()).add((_dia(r["startdato"]) or "1900-01-01", _dia(r["slutdato"]), codigo, r["rolleid"]))
    return {p: sorted(v) for p, v in miembros.items()}, nombres


def grupo_de(relaciones, dia):
    """Grupo de un diputado en una fecha: el de la pertenencia vigente (la más reciente si hay varias)."""
    if not relaciones:
        return None
    vigentes = [r for r in relaciones if r[0] <= dia and (not r[1] or dia <= r[1])]
    if vigentes:
        return max(vigentes, key=lambda r: (r[0], r[3] == 15))[2]
    # Fuera de plazo (fechas que no casan por un día o un suplente): la pertenencia más cercana.
    return min(relaciones, key=lambda r: abs((date.fromisoformat(r[0]) - date.fromisoformat(dia)).days))[2]


def escanos_de(miembros, dia):
    """{grupo: diputados en ejercicio ese día} (sin los que están de permiso, rol 6 y 12, que los suple otro)."""
    n = {}
    for relaciones in miembros.values():
        vigentes = [r for r in relaciones if r[0] <= dia and (not r[1] or dia <= r[1])]
        if vigentes and any(r[3] not in (6, 12) for r in vigentes):
            g = max(vigentes, key=lambda r: (r[0], r[3] == 15))[2]
            n[g] = n.get(g, 0) + 1
    return n


# ------------------------------------------------------------------ clasificación

def tipo_asunto(prefijo, titulo):
    t = (titulo or "").lower()
    if prefijo in ("F", "R", "V"):
        return "mocion"
    if "forretningsorden" in t:
        return "procedimiento"
    if TRATADO.search(t):
        return "tratado"
    if prefijo == "L":
        return "ley"
    if prefijo == "B":
        return "resolucion"
    return "otro"


def lectura(fase):
    """«3. behandling, 1. del,» -> «3.ª lectura, 1.ª parte»; «2. (sidste) behandling» -> «2.ª y última lectura»."""
    f = re.sub(r"^eventuelt:\s*", "", (fase or "").strip().rstrip(",").strip(), flags=re.I).lower()
    m = re.search(r"(\d)\. (\(sidste\) )?behandling", f)
    if "eneste" in f:
        texto = "lectura única"
    elif m:
        texto = f"{m.group(1)}.ª {'y última ' if m.group(2) else ''}lectura"
    else:
        texto = "debate"
    parte = re.search(r"(\d)\. del\b", f)
    if parte:
        texto += f", {parte.group(1)}.ª parte"
    if "fortsættelse" in f:
        texto += " (continuación)"
    return texto


def tipo_votacion(typeid, fase):
    """Afstemningstype: 1 endelig vedtagelse, 2 udvalgsindstilling, 3 forslag til vedtagelse, 4 ændringsforslag."""
    if "udvalgshenvisning" in (fase or "").lower():
        return "procedimiento"
    return {1: "final", 3: "final", 4: "enmienda"}.get(typeid, "otra")


def texto_votacion(typeid, fase, sag):
    if "udvalgshenvisning" in (fase or "").lower():
        return f"Envío a comisión ({lectura(fase)})"
    if typeid == 3:
        return _limpio(f"Propuesta de resolución {sag.get('nummer')}: {sag.get('titel')}", 500)
    if typeid == 1:
        return f"Votación final ({lectura(fase)})"
    if typeid == 4:
        return f"Enmienda ({lectura(fase)})"
    return lectura(fase)


LADOS = (("si", r"(?:(?<!hverken )for stemte (\d+)|(\d+) stemte for)"),
         ("no", r"(?:(?<!eller )imod stemte (\d+)|(\d+) stemte imod)"),
         ("abstencion", r"(?:hver(?:ken)? for eller imod stemte (\d+)|(\d+) stemte hverken for eller imod)"))
SIGLAS = r"[A-ZÆØÅ]{1,4}"


def acta(konklusion):
    """{sentido: (total, [grupos o «Nombre (GRUPO)»])} del acta de la votación.

    «For stemte 106 (S, SF, V, Emilie Schytte (UFG) og Jacob Harris (UFG)), imod stemte 6 (DD), hverken for
    eller imod stemte 0.» Los grupos van enteros; quien vota distinto de su grupo aparece con su nombre.
    """
    k = re.sub(r"\s+", " ", konklusion or "")
    lados = {}
    for sentido, patron in LADOS:
        m = re.search(patron + r"\s*(\((?:[^()]|\([^()]*\))*\))?", k, re.I)
        if m:
            lista = (m.group(3) or "()")[1:-1]
            lados[sentido] = (int(m.group(1) or m.group(2)), [t.strip() for t in re.split(r",|\s+og\s+", lista) if t.strip()])
    return lados


def totales_acta(konklusion):
    """(a favor, en contra, abstenciones) del acta."""
    lados = acta(konklusion)
    return tuple(lados[s][0] if s in lados else None for s in ("si", "no", "abstencion"))


def _repartir(n, pesos):
    """Reparte n entre los grupos en proporción a su peso (al menos 1 a cada uno si alcanza; restos mayores)."""
    if not pesos or n <= 0:
        return {g: 0 for g in pesos}
    base = {g: 1 if n >= len(pesos) else 0 for g in pesos}
    queda, total = n - sum(base.values()), sum(pesos.values()) or 1
    cuota = {g: queda * p / total for g, p in pesos.items()}
    for g in pesos:
        base[g] += int(cuota[g])
    for g in sorted(pesos, key=lambda g: cuota[g] - int(cuota[g]), reverse=True)[:n - sum(base.values())]:
        base[g] += 1
    return base


def por_grupo_acta(konklusion, escanos):
    """{grupo: (sí, no, abstención, no vota)} a partir del acta, para las votaciones sin voto de cada diputado.

    El acta dice qué grupos votaron qué y cuántos votos hubo en cada sentido, pero no cuántos de cada grupo:
    el total de cada sentido se reparte entre sus grupos en proporción a sus escaños (`escanos`, diputados
    de cada grupo ese día) y el resto de cada grupo cuenta como ausente. La posición de cada grupo es la
    del acta; el reparto de los ausentes entre grupos es una estimación.
    """
    lados = acta(konklusion)
    if not lados:
        return {}
    orden = ("si", "no", "abstencion")
    cuenta = {g: [0, 0, 0, 0] for g in escanos}
    nombrados, enteros = {}, {}
    for s, (_, fichas) in lados.items():
        for f in fichas:
            m = re.fullmatch(r".+\((" + SIGLAS + r")\)", f)
            if m:
                cuenta.setdefault(m.group(1), [0, 0, 0, 0])[orden.index(s)] += 1
                nombrados[m.group(1)] = nombrados.get(m.group(1), 0) + 1
            elif re.fullmatch(SIGLAS, f):
                enteros.setdefault(s, []).append(f)
    veces = {}
    for gs in enteros.values():
        for g in gs:
            veces[g] = veces.get(g, 0) + 1
    for s, gs in enteros.items():
        total = lados[s][0] - sum(c[orden.index(s)] for c in cuenta.values())
        pesos = {g: max(1, escanos.get(g, 1) - nombrados.get(g, 0)) / veces[g] for g in gs}
        for g, n in _repartir(total, pesos).items():
            cuenta.setdefault(g, [0, 0, 0, 0])[orden.index(s)] += n
    for g, c in cuenta.items():
        c[3] = max(0, escanos.get(g, 0) - sum(c[:3]))
    return {g: tuple(c) for g, c in cuenta.items() if any(c)}


def _codigo_samling(periodo):
    """«2025-26 (2. samling)» -> «2025-26, 2. samling»."""
    return re.sub(r" \((\d)\. samling\)", r", \1. samling", periodo["titel"])


# ------------------------------------------------------------------ recogida

def recoger(ctx):
    periodos = {p["id"]: p for p in _todas(ctx, "Periode", filter="type eq 'samling'", orderby="id")}
    inicio = f"{ctx.desde}-01-01"
    ultima = ctx.ultima_fecha()
    if ultima and not ctx.completo:
        inicio = max(inicio, (date.fromisoformat(ultima) - timedelta(days=MARGEN_DIAS)).isoformat())
    sel = ("id,nummer,konklusion,vedtaget,typeid,Møde/dato,Møde/periodeid,Sagstrin/titel,Sagstrin/Sag/id,"
           "Sagstrin/Sag/nummer,Sagstrin/Sag/nummerprefix,Sagstrin/Sag/titel,Sagstrin/Sag/titelkort,"
           "Sagstrin/Sag/periodeid,Sagstrin/Sag/fremsatundersagid")
    lista = _todas(ctx, "Afstemning", filter=f"Møde/dato ge datetime'{inicio}T00:00:00'",
                   expand="Møde,Sagstrin/Sag", select=sel, orderby="id")
    sin_sag = [a["id"] for a in lista if not (a.get("Sagstrin") or {}).get("Sag")]
    if sin_sag:
        ctx.log(f"   ! {len(sin_sag)} votaciones sin asunto, no se guardan: {sin_sag[:5]}")
    lista = [a for a in lista if a["id"] not in sin_sag and _dia(a["Møde"]["dato"]) >= f"{ctx.desde}-01-01"]
    lista.sort(key=lambda a: (a["Møde"]["dato"], a["nummer"]))
    ctx.log(f"   {len(lista)} votaciones desde {inicio}")
    if not lista:
        return

    # Debates (interpelaciones F, informes R) a los que pertenecen las propuestas de resolución V.
    debates = {s["id"]: s for s in _por_ids(
        ctx, "Sag", [a["Sagstrin"]["Sag"]["fremsatundersagid"] for a in lista
                     if a["Sagstrin"]["Sag"].get("nummerprefix") == "V" and a["Sagstrin"]["Sag"].get("fremsatundersagid")],
        "id,nummer,nummerprefix,titel,titelkort,periodeid")}

    # Grupos parlamentarios de cada samling.
    grupos, nombres = {}, {}
    for pid in sorted({a["Møde"]["periodeid"] for a in lista}):
        grupos[pid], n = grupos_de_samling(ctx, pid)
        nombres.update(n)
        ctx.log(f"   samling {periodos[pid]['kode']}: {len(grupos[pid])} diputados en grupos")
    for pid in grupos:
        for g in {r[2] for rel in grupos[pid].values() for r in rel}:
            if g not in FUENTE.partidos:
                ctx.partido(g)

    def votos_de(a):
        return _todas(ctx, "Stemme", filter=f"afstemningid eq {a['id']}", select="aktørid,typeid", orderby="id")

    sin_grupo = set()

    def partido_de(p, pid, dia):
        partido = grupo_de(grupos[pid].get(p), dia)
        if not partido:  # sin pertenencia en esta samling: la de otra samling cargada, si la hay
            partido = next((grupo_de(g[p], dia) for g in grupos.values() if p in g), None)
        if not partido:
            sin_grupo.add(p)
        return partido or "UFG"

    # Quiénes ocupan los escaños (con los suplentes): los de la última votación nominal de cada samling. Sirve
    # para repartir por grupos las votaciones que solo traen el acta (la pertenencia a grupos arrastra a veces
    # gente que ya no está).
    ocupantes, sin_votos = {}, 0
    with ThreadPoolExecutor(6) as ex:
        for i in range(0, len(lista), LOTE):
            trozo = lista[i:i + LOTE]
            stemmer = [list({s["aktørid"]: s for s in ss}.values()) for ss in ex.map(votos_de, trozo)]
            faltan = {s["aktørid"] for ss in stemmer for s in ss} - set(nombres)
            if faltan:
                nombres.update({x["id"]: x["navn"] for x in _por_ids(ctx, "Aktør", faltan, "id,navn")})
            for a, ss in zip(trozo, stemmer):  # si una samling empieza sin voto nominal, la primera que lo tenga
                if ss:
                    ocupantes.setdefault(a["Møde"]["periodeid"], [s["aktørid"] for s in ss])
            asuntos, votaciones = {}, []
            for a, ss in zip(trozo, stemmer):
                dia, pid = _dia(a["Møde"]["dato"]), a["Møde"]["periodeid"]
                samling = periodos[pid]["kode"]
                sag = a["Sagstrin"]["Sag"]
                base = debates.get(sag.get("fremsatundersagid")) if sag.get("nummerprefix") == "V" else None
                base = base or sag
                prefijo = base.get("nummerprefix") or (base.get("nummer") or "?").split()[0]
                periodo_a = periodos.get(base.get("periodeid"), periodos[pid])
                nummer = re.sub(r"\s+", "", base.get("nummer") or str(base["id"]))
                aid = f"dnk:{periodo_a['kode']}:{nummer}"
                if aid not in asuntos:
                    titulo = base.get("titel") or base.get("titelkort") or base.get("nummer")
                    tramo = TRAMO.get(prefijo)
                    asuntos[aid] = Asunto(
                        id=aid, titulo=_limpio(titulo), tipo=tipo_asunto(prefijo, titulo), fecha=dia,
                        codigo=f"{base.get('nummer')} ({_codigo_samling(periodo_a)})",
                        url=f"{WEB}/{periodo_a['kode']}/{tramo}/{nummer.lower()}/index.htm" if tramo else None,
                        extra={"samling": periodo_a["kode"], "sag": base["id"]})
                fase = a["Sagstrin"].get("titel")
                texto = texto_votacion(a["typeid"], fase, sag)
                votos = [(f"dnk:{s['aktørid']}", nombres.get(s["aktørid"]), partido_de(s["aktørid"], pid, dia),
                          SENTIDO.get(s["typeid"], "no_vota")) for s in ss]
                grupos_acta = None
                if votos:
                    ocupantes[pid] = [s["aktørid"] for s in ss]
                    si, no, abst = (sum(1 for v in votos if v[3] == x) for x in ("si", "no", "abstencion"))
                    no_votan = sum(1 for v in votos if v[3] == "no_vota")
                else:
                    # Sin voto de cada diputado (junio de 2020 y algunas jornadas largas): lo del acta.
                    sin_votos += 1
                    (si, no, abst), no_votan = totales_acta(a.get("konklusion")), None
                    if pid in ocupantes:
                        escanos = {}
                        for p in ocupantes[pid]:
                            g = partido_de(p, pid, dia)
                            escanos[g] = escanos.get(g, 0) + 1
                    else:
                        escanos = escanos_de(grupos[pid], dia)
                    grupos_acta = por_grupo_acta(a.get("konklusion"), escanos) or None
                    if grupos_acta:
                        texto += " · voto por grupo según el acta"
                        for g in grupos_acta:
                            if g not in FUENTE.partidos:
                                ctx.partido(g)
                votaciones.append(Votacion(
                    id=f"dnk:{a['id']}", fecha=dia, asunto_id=aid, camara="dnk-f", numero=a["nummer"],
                    texto=texto, tipo=tipo_votacion(a["typeid"], fase),
                    a_favor=si, en_contra=no, abstenciones=abst, no_votan=no_votan,
                    resultado="aprobada" if a.get("vedtaget") else "rechazada",
                    url=f"{WEB}/{samling}/afstemning/{a['nummer']}.htm", votos=votos or None, por_partido=grupos_acta))
            ctx.guardar(list(asuntos.values()), votaciones)
            ctx.log(f"   {min(i + LOTE, len(lista))}/{len(lista)} (hasta {votaciones[-1].fecha})")
    if sin_votos:
        ctx.log(f"   {sin_votos} votaciones sin voto de cada diputado (voto por grupo según el acta)")
    if sin_grupo:
        ctx.log(f"   ! {len(sin_grupo)} diputados sin grupo conocido (como UFG): {sorted(sin_grupo)[:8]}")
