"""México: votaciones nominales del Pleno de la Cámara de Diputados, de la Gaceta Parlamentaria.

La Gaceta Parlamentaria (https://gaceta.diputados.gob.mx/gp_votaciones.html) publica, por legislatura
y periodo de sesiones, la lista de dictámenes votados con un enlace a cada votación
(`/Gaceta/Votaciones/66/tabla1or1-2.php3`: totales por grupo parlamentario) y, desde esa tabla, la
lista de diputados de cada sentido con su grupo (un formulario de consulta que solo responde por POST;
da nombres sin identificador, así que el id del diputado es legislatura + nombre normalizado). Se
recogen la LXIV (2018-2021), la LXV (2021-2024) y la LXVI (2024-2027): unas 150-350 votaciones al año.
Cada entrada de la lista es un asunto (el dictamen con sus votaciones «en lo general» y «en lo
particular»). En unas pocas votaciones la Gaceta lista un nombre menos que el total oficial.

Otras vías probadas: el SITL (sitl.diputados.gob.mx) tiene lo mismo con identificador de diputado,
pero su servidor no envía el certificado intermedio (RapidSSL TLS RSA CA G1) y Python no puede
verificarlo; http:// redirige a https://. El Senado (senado.gob.mx, infosen.senado.gob.mx) está tras
un reto anti-robots de Imperva: no se recoge.
"""

import html
import re
import unicodedata
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from .modelo import Asunto, Fuente, Votacion

FUENTE = Fuente(
    codigo="mex", pais="MEX", nombre="Cámara de Diputados de México", corto="México", tipo="parlamento",
    detalle="nominal", web="https://gaceta.diputados.gob.mx", desde=2019, idioma="es",
    licencia=("Gaceta Parlamentaria de la Cámara de Diputados: información pública sin licencia expresa "
              "(reutilización citando la fuente)"),
    camaras={"mex-d": ("Cámara de Diputados", "Diputados", 500)},
    partidos={
        "MORENA": ("Morena", "Morena", "#a8233d"), "PAN": ("Partido Acción Nacional", "PAN", "#1f4e9c"),
        "PRI": ("Partido Revolucionario Institucional", "PRI", "#00923f"),
        "PVEM": ("Partido Verde Ecologista de México", "PVEM", "#7cc242"), "PT": ("Partido del Trabajo", "PT", "#d62828"),
        "MC": ("Movimiento Ciudadano", "MC", "#ff8300"), "PRD": ("Partido de la Revolución Democrática", "PRD", "#ffcc00"),
        "PES": ("Partido Encuentro Social", "PES", "#6a2c91"), "SP": ("Sin partido", "SP", "#898781"),
        "IND": ("Independientes", "Ind.", "#898781"),
    },
    notas="Votaciones nominales del Pleno de la Cámara de Diputados desde 2019; el Senado no se recoge (web con reto anti-robots).",
)

BASE = "https://gaceta.diputados.gob.mx"
PARTIDO = {
    "morena": "MORENA", "partido accion nacional": "PAN", "partido revolucionario institucional": "PRI",
    "partido verde ecologista de mexico": "PVEM", "partido del trabajo": "PT", "movimiento ciudadano": "MC",
    "partido de la revolucion democratica": "PRD", "partido encuentro social": "PES", "encuentro social": "PES",
    "sin partido": "SP", "independientes": "IND", "independiente": "IND",
}
# Fila de la tabla de una votación (lola[<columna><fila>]): 1 a favor, 2 en contra, 3 abstención,
# 4 «quórum» (pasó lista y no votó), 5 ausente.
FILAS = {"1": "si", "2": "no", "3": "abstencion", "4": "abstencion", "5": "no_vota"}
MESES = {m: i for i, m in enumerate(("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
                                     "octubre", "noviembre", "diciembre"), 1)}
LOTE = 150


def _plano(t):
    t = unicodedata.normalize("NFKD", t or "")
    return re.sub(r"\s+", " ", "".join(c for c in t if not unicodedata.combining(c))).strip().lower()


def _slug(t):
    return re.sub(r"[^a-z0-9]+", "-", _plano(t)).strip("-")


def _texto(fragmento):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragmento or ""))).strip()


def _html(datos):
    return datos.decode("cp1252", "replace")


def _fecha(texto):
    """«03 de septiembre de 2024» o «Martes 3 de septiembre de 2024» -> 2024-09-03."""
    m = re.search(r"(\d{1,2}) de (\w+) de (\d{4})", _plano(texto))
    if m and m.group(2) in MESES:
        return f"{m.group(3)}-{MESES[m.group(2)]:02d}-{int(m.group(1)):02d}"
    return None


def _legislatura_de(anio):
    """Legislatura en curso el 1 de enero de ese año (la LXIV empezó el 1 de septiembre de 2018)."""
    return 64 + ((anio - 2018) * 12 - 8) // 36


# ------------------------------------------------------------------ periodos y asuntos

def _periodos(ctx, leg_min):
    """Páginas de votaciones por periodo de sesiones, del índice de la Gaceta: [(legislatura, ruta)]."""
    indice = _html(ctx.cache(f"{BASE}/gp_votaciones.html", "indice.html", caduca_horas=6).read_bytes())
    rutas = dict.fromkeys(re.findall(r'href="(/Gaceta/Votaciones/(\d+)/vot\d*_a\d\w+\.html)"', indice, re.I))
    return sorted({(int(leg), ruta) for ruta, leg in rutas if int(leg) >= leg_min})


TITULO = re.compile(r"^De (?:las?|los) ((?:Comisi[oó]n|Comisiones|Junta|Mesa)\b.*?),? (?:con|a la|al|a las|relativo a|sobre) "
                    r"((?:el |la |las )?(?:proyecto|punto|minuta|dictamen|iniciativa|propuesta|acuerdo|solicitud|"
                    r"observaciones)\b.*)$")


def titulo_y_autor(t):
    """«De la Comisión de Salud, con proyecto de decreto por el que…»
    -> («Proyecto de decreto por el que…», «Comisión de Salud»)."""
    t = t.strip().rstrip(".")
    m = TITULO.match(t)
    if m:
        cuerpo = m.group(2).strip()
        return cuerpo[:1].upper() + cuerpo[1:], m.group(1)
    return t, None


PARTICULAS = {"de", "del", "la", "las", "los", "y", "e", "van", "von", "da", "di"}


def _nombre(t):
    """Algunas listas vienen en mayúsculas: «AGUILERA CLARO ZARIA» -> «Aguilera Claro Zaria»."""
    t = re.sub(r"\s+", " ", t).strip()
    if t.isupper():
        t = " ".join(p.lower() if i and p.lower() in PARTICULAS else p.capitalize() for i, p in enumerate(t.split()))
    return t


def tipo_asunto(titulo):
    t = _plano(titulo)
    if re.search(r"se aprueba (el|la) (tratado|convenio|acuerdo|protocolo|convencion)", t):
        return "tratado"
    if re.search(r"\bnombramiento|\bdesigna (al|a la|a los|a las)\b|\beleccion de (las |los )?(consejer|titular|magistrad)|"
                 r"\bse elige", t) and not re.search(r"comision permanente|mesa directiva|integracion de (la|las) comision", t):
        return "nombramiento"
    if re.search(r"\bpunto de acuerdo\b|exhorta", t):
        return "resolucion"
    if re.search(r"proyecto de (decreto|ley)|minuta|iniciativa|ley de ingresos|presupuesto de egresos|\bdecreto\b", t):
        return "ley"
    if re.search(r"^acuerdo|mesa directiva|comision permanente|integracion de|orden del dia|reglamento de la camara", t):
        return "procedimiento"
    if re.search(r"declaratoria|declaracion de procedencia", t):
        return "otro"
    return "otro"


def tipo_votacion(linea, tipo_a):
    t = _plano(linea)
    if re.search(r"mocion suspensiva|dispensa|orden del dia|mocion de procedimiento|excitativa", t):
        return "procedimiento"
    if "en lo particular" in t and "en lo general" not in t:
        return "parcial"
    if re.search(r"\breservad[oa]s?\b|\breserva\b", t) and "en lo general" not in t:
        return "parcial"
    if re.search(r"\bpropuesta de modificacion|\bmodificacion(es)? propuesta", t):
        return "enmienda"
    if tipo_a == "nombramiento":
        return "nombramiento"
    if tipo_a == "procedimiento":
        return "procedimiento"
    return "final"


def resultado(linea, titulo, si, no, abst):
    t = _plano(linea)
    if re.search(r"\b(desechad|rechazad|no se aprob|no alcanz)", t):
        return "rechazada"
    if re.search(r"\baprobad", t):
        return "aprobada"
    if "constitucion politica de los estados unidos mexicanos" in _plano(titulo):
        return "aprobada" if si * 3 >= 2 * (si + no + abst) else "rechazada"
    return "aprobada" if si > no else "rechazada"


def _entradas(pagina):
    """Entradas (asuntos) de una página de periodo: [(fecha de la cabecera, título, (enlace y número de la Gaceta),
    [(ruta de la tabla, línea que describe la votación)])]."""
    salida = []
    fecha = None
    for trozo in re.split(r'(<font color="#CC0000">[^<]*</font>)', pagina, flags=re.I):
        m = re.match(r'<font color="#CC0000">([^<]*)</font>', trozo, re.I)
        if m:
            fecha = _fecha(m.group(1)) or fecha
            continue
        for li in re.findall(r"<li>(.*?)</li>", trozo, re.S | re.I):
            lineas = re.split(r"<br\s*/?>", li, flags=re.I)
            titulo = _texto(lineas[0])
            gaceta = numero = None
            votos = []
            for linea in lineas[1:]:
                tabla = re.search(r'href="(/Gaceta/Votaciones/\d+/tabla[^"]+\.php3)"', linea, re.I)
                if tabla:
                    votos.append((tabla.group(1), _texto(re.sub(r"<a [^>]*>\s*Votaci[oó]n\s*</a>\.?", "", linea, flags=re.I))))
                elif "Gaceta Parlamentaria" in linea:
                    g = re.search(r'href="([^"]+)"', linea)
                    gaceta = urllib.parse.urljoin(BASE, g.group(1)) if g else None
                    n = re.search(r"n[úu]mero ([\w-]+)", _texto(linea))
                    numero = n.group(1) if n else None
            if votos:
                salida.append((fecha, titulo, (gaceta, numero), votos))
    return salida


# ------------------------------------------------------------------ votaciones

def _tabla(ctx, ruta):
    """Tabla de una votación: título, fecha, dirección del formulario, evento y totales por fila (lola[1x])."""
    t = _html(ctx.fetch(BASE + ruta))
    accion = re.search(r'<form method="post" action="([^"]+)"', t, re.I)
    evento = re.search(r'name="evento" value="([^"]*)"', t, re.I)
    nomtit = re.search(r'name="nomtit" value="([^"]*)"', t, re.I | re.S)
    totales = {k[1:]: int(v) for k, v in re.findall(r'name="lola\[(1\d)\]" value="\s*(\d+)\s*"', t)}
    titulo = html.unescape(nomtit.group(1)) if nomtit else ""
    partes = re.split(r"<p>", titulo, flags=re.I)
    # El título de la tabla acaba con lo que se vota entre paréntesis: «(en lo general y en lo particular…)».
    detalle = re.search(r"\(([^()]*)\)\s*\.?\s*$", _texto(partes[0]))
    return dict(accion=accion.group(1) if accion else None, evento=evento.group(1) if evento else None,
                detalle=detalle.group(1) if detalle else "", fecha=_fecha(partes[-1]) if len(partes) > 1 else None,
                totales=totales)


def _lista(ctx, accion, evento, fila, total):
    """Diputados de una fila (sentido) de la votación, de todos los grupos: [(nombre, partido)]."""
    t = _html(ctx.fetch(BASE + accion, formulario={"evento": evento, f"lola[1{fila}]": str(total)}))
    salida = []
    for bloque in re.split(r"(Diputad[oa]s? [^:<]*? que [^:<]*:\s*\d+)", t)[1:]:
        if bloque.startswith("Diputad"):
            m = re.match(r"Diputad[oa]s? (?:de la |del |de los |de )?(.*?) que ", bloque)
            grupo = _plano(m.group(1)) if m else "?"
            partido = PARTIDO.get(grupo) or grupo.upper()[:20]
            continue
        for nombre in re.findall(r"\d+:\s*([^<\n]+)", bloque):
            nombre = _nombre(html.unescape(nombre))
            if nombre:
                salida.append((nombre, partido))
    return salida


def _votacion(ctx, ruta):
    try:
        tabla = _tabla(ctx, ruta)
        votos = []
        if tabla["accion"] and tabla["evento"]:
            for fila, sentido in FILAS.items():
                n = tabla["totales"].get(fila, 0)
                if n:
                    lista = _lista(ctx, tabla["accion"], tabla["evento"], fila, n)
                    if len(lista) != n:
                        ctx.log(f"   ! {ruta}: {len(lista)} nombres en la fila {fila} de {n} votos")
                    votos += [(nombre, partido, sentido) for nombre, partido in lista]
        tabla["votos"] = votos
        return tabla
    except Exception as e:
        ctx.log(f"   ! {ruta}: {type(e).__name__}: {e}")
        return None


def _procesar(ctx, leg, entradas):
    """Descarga las votaciones de una lista de (entrada, votación) y las guarda."""
    pendientes = [(e, v) for e in entradas for v in e[3]]
    with ThreadPoolExecutor(4) as ex:
        tablas = list(ex.map(lambda p: _votacion(ctx, p[1][0]), pendientes))
    asuntos, votaciones, fallidas = {}, [], set()
    for (entrada, (ruta, linea)), tabla in zip(pendientes, tablas):
        if tabla is None:
            fallidas.add(ruta)
            continue
        fecha_cab, titulo_bruto, (gaceta, num_gaceta), votos_e = entrada
        # Fecha: la que da la línea de la votación («…, el martes 25 de noviembre de 2025»); si no, la de la tabla,
        # salvo que se aleje de la cabecera del día en la lista (hay tablas con el mes equivocado).
        fecha = _fecha(linea)
        if not fecha:
            fecha = tabla["fecha"] or fecha_cab
            if fecha and fecha_cab and abs((date.fromisoformat(fecha) - date.fromisoformat(fecha_cab)).days) > 3:
                fecha = fecha_cab
        if not fecha or fecha < f"{ctx.desde}-01-01":
            continue
        titulo, autor = titulo_y_autor(titulo_bruto)
        tipo_a = tipo_asunto(titulo)
        codigo_1 = re.search(r"tabla([^/]+)\.php3", votos_e[0][0]).group(1)
        aid = f"mex:{leg}:{codigo_1}"
        if aid not in asuntos:
            asuntos[aid] = Asunto(id=aid, titulo=titulo[:400], tipo=tipo_a, fecha=fecha_cab or fecha, autor=autor,
                                  codigo=f"Gaceta Parlamentaria {num_gaceta}" if num_gaceta else None,
                                  url=gaceta or BASE + ruta, extra={"legislatura": leg})
        tot = tabla["totales"]
        si, no, abst, aus = tot.get("1", 0), tot.get("2", 0), tot.get("3", 0) + tot.get("4", 0), tot.get("5", 0)
        votos = []
        for nombre, partido, sentido in tabla["votos"]:
            if partido not in FUENTE.partidos:
                ctx.partido(partido)
            votos.append((f"mex:{leg}:{_slug(nombre)}", nombre, partido, sentido))
        codigo = re.search(r"tabla([^/]+)\.php3", ruta).group(1)
        numero = re.search(r"-(\d+)$", codigo)
        detalle = tabla["detalle"][:1].upper() + tabla["detalle"][1:]
        texto = linea if _plano(detalle) in _plano(linea) else " · ".join(x for x in (detalle, linea) if x)
        votaciones.append(Votacion(
            id=f"mex:{leg}:{codigo}", fecha=fecha, asunto_id=aid, camara="mex-d", numero=int(numero.group(1)) if numero else None,
            texto=texto[:600] or None, tipo=tipo_votacion(f"{tabla['detalle']} {linea}", tipo_a), a_favor=si, en_contra=no,
            abstenciones=abst, no_votan=aus, resultado=resultado(linea, titulo, si, no, abst), url=BASE + ruta, votos=votos or None))
    if votaciones:
        usados = {v.asunto_id for v in votaciones}
        ctx.guardar([a for a in asuntos.values() if a.id in usados], votaciones)
    return len(votaciones), fallidas


def recoger(ctx):
    hoy = date.today()
    cerrados = set(ctx.marca("periodos_cerrados", []))
    pendientes = set(ctx.marca("pendientes", []))  # tablas que fallaron la última vez
    ultima = ctx.ultima_fecha()
    # Se repasan dos semanas antes de la última votación guardada (la Gaceta añade votaciones con retraso).
    desde = (date.fromisoformat(ultima) - timedelta(days=14)).isoformat() if ultima and not ctx.completo else f"{ctx.desde}-01-01"
    fallidas, vistas = set(), set()
    for leg, ruta in _periodos(ctx, _legislatura_de(ctx.desde)):
        if ruta in cerrados and not ctx.completo:
            continue
        nombre = ruta.rsplit("/", 1)[-1]
        pagina = _html(ctx.cache(BASE + ruta, f"{leg}_{nombre}", caduca_horas=6).read_bytes())
        todas = []
        for fecha, titulo, gaceta, votos in _entradas(pagina):
            # Hay tablas enlazadas dos veces (errores de copia en la lista): cuenta la primera.
            unicos = []
            for r, linea in votos:
                if r not in vistas:
                    vistas.add(r)
                    unicos.append((r, linea))
            if unicos:
                todas.append((fecha, titulo, gaceta, unicos))
        entradas = [e for e in todas if (e[0] or "9999") >= desde or any(r in pendientes for r, _ in e[3])]
        fallidas_periodo = set()
        if entradas:
            ctx.log(f"   {nombre}: {sum(len(e[3]) for e in entradas)} votaciones")
            n = 0
            for i in range(0, len(entradas), LOTE):
                guardadas, f = _procesar(ctx, leg, entradas[i:i + LOTE])
                n += guardadas
                fallidas_periodo |= f
            ctx.log(f"   {nombre}: {n} guardadas" + (f", {len(fallidas_periodo)} fallidas (se reintentan)" if fallidas_periodo else ""))
        fallidas |= fallidas_periodo
        # Un periodo cuya última votación tiene más de 45 días no cambia: no se vuelve a descargar.
        fechas = [e[0] for e in todas if e[0]]
        if fechas and max(fechas) < (hoy - timedelta(days=45)).isoformat() and not fallidas_periodo:
            cerrados.add(ruta)
            ctx.poner_marca("periodos_cerrados", sorted(cerrados))
    ctx.poner_marca("pendientes", sorted(fallidas))
