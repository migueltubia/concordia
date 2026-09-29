"""Chile: votaciones de la Sala de la Cámara de Diputadas y Diputados y del Senado.

Cámara: servicios de datos abiertos de la Cámara (https://opendata.camara.cl, XML). Por año,
`retornarVotacionesXAnno` da cada votación electrónica de la Sala con sus totales; `retornarVotacionDetalle`,
el voto de cada diputado (sin partido: la militancia con fechas sale de `retornarDiputadosXPeriodo`), y
`retornarVotacionesXProyectoLey`, por boletín, el nombre del proyecto y qué se vota en cada votación
(artículo, «en general», trámite). Los proyectos de resolución y de acuerdo y las demás votaciones
(acusaciones constitucionales, comisiones investigadoras, estados de excepción…) no tienen servicio de
datos: su materia se lee de la ficha HTML de la votación en camara.cl.

Senado: servicios públicos de tramitación (https://tramitacion.senado.cl/wspublico). No hay listado de
votaciones por fecha: `votaciones.php?boletin=` da las de un proyecto con el nombre de cada senador, y
`tramitacion.php?fecha=` los proyectos con movimiento en el último mes con sus votaciones. La primera
recogida (o si pasa más de un mes sin recoger) repasa los boletines votados en la Cámara y los
proyectos ingresados por el Senado; después basta el listado del último mes. El partido de cada
senador, con fechas, sale de los datos enlazados de la Biblioteca del Congreso (https://datos.bcn.cl).

El asunto es el boletín (p. ej. «17286-05»), que une las votaciones de las dos cámaras. Los proyectos
de acuerdo que aprueban tratados («Aprueba el Convenio entre la República de Chile y…») son «tratado».
Las votaciones del Senado no tienen página propia: su enlace es la tramitación del proyecto.

Volumen: unas 1.300-1.800 votaciones al año en la Cámara (una petición por votación, lentas: la primera
recogida desde 2019 lleva hora y media o dos) y unas 500-700 en el Senado.

Certificados: opendata.camara.cl presenta una cadena que termina en «emSign Root CA - G1», que está en
el almacén de Mozilla (Linux, GitHub Actions). Windows descarga esas raíces bajo demanda, cuando las pide
su propia pila TLS, y Python solo ve las que ya están en el almacén: en un Windows que nunca ha abierto la
web da CERTIFICATE_VERIFY_FAILED. Se arregla sin tocar el código: instalando esa raíz en el almacén de
Windows o con SSL_CERT_FILE apuntando a un almacén completo (p. ej. el de Git para Windows). El acceso
por http:// lo corta el servidor.
"""

import html
import json
import re
import unicodedata
import urllib.parse
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta

from .modelo import Asunto, Fuente, Votacion

FUENTE = Fuente(
    codigo="chl", pais="CHL", nombre="Congreso Nacional de Chile", corto="Chile", tipo="parlamento",
    detalle="nominal", web="https://www.camara.cl", desde=2019, idioma="es",
    licencia=("Datos abiertos del Congreso Nacional de Chile (uso libre, sin restricciones de derechos de autor); "
              "militancia de los senadores: BCN, CC BY 3.0 CL"),
    camaras={"chl-d": ("Cámara de Diputadas y Diputados", "Cámara", 155), "chl-s": ("Senado", "Senado", 50)},
    partidos={
        "PS": ("Partido Socialista", "PS", "#e4312b"), "PPD": ("Partido por la Democracia", "PPD", "#f2b705"),
        "PC": ("Partido Comunista", "PC", "#a3131a"), "FA": ("Frente Amplio", "FA", "#6a2c91"),
        "RD": ("Revolución Democrática", "RD", "#2a9d8f"), "PCS": ("Convergencia Social", "CS", "#8e3a9d"),
        "COMUNES": ("Comunes", "Comunes", "#d6337a"), "DC": ("Partido Demócrata Cristiano", "PDC", "#3a7fc1"),
        "PR": ("Partido Radical", "PR", "#b3263f"), "PL": ("Partido Liberal", "PL", "#e39b00"),
        "LIBERAL": ("Partido Liberal", "PL", "#e39b00"), "PH": ("Partido Humanista", "PH", "#ff7f00"),
        "PAH": ("Acción Humanista", "AH", "#ff9f40"), "FRVS": ("Federación Regionalista Verde Social", "FRVS", "#4caf50"),
        "PEV": ("Partido Ecologista Verde", "PEV", "#2e8b57"), "IGUAL": ("Partido Igualdad", "Igualdad", "#d35400"),
        "PRO": ("Partido Progresista", "PRO", "#e67e22"), "PAIS": ("País Progresista (PAIS)", "PAIS", "#c0392b"),
        "MAS": ("Movimiento Amplio Social", "MAS", "#e05a47"), "DEM": ("Demócratas", "Demócratas", "#56a0d3"),
        "AMA": ("Amarillos por Chile", "Amarillos", "#f4d03f"), "PDG": ("Partido de la Gente", "PDG", "#f08a24"),
        "RN": ("Renovación Nacional", "RN", "#0a74da"), "UDI": ("Unión Demócrata Independiente", "UDI", "#29539b"),
        "EVOP": ("Evolución Política", "Evópoli", "#00a3e0"), "PREP": ("Partido Republicano", "Rep.", "#0b2545"),
        "PNL": ("Partido Nacional Libertario", "PNL", "#8a6d1f"), "PSC": ("Partido Social Cristiano", "PSC", "#7d3c98"),
        "PCCH": ("Partido Cristiano de Chile", "PCCh", "#6c5b7b"), "PCC": ("Partido Conservador Cristiano", "PCC", "#4b3b8f"),
        "PRI": ("Partido Regionalista Independiente", "PRI", "#1e8449"), "IND": ("Independientes", "Ind.", "#898781"),
    },
    notas=("Votaciones electrónicas de la Sala de ambas cámaras; en el Senado solo las de proyectos con boletín "
           "(no los nombramientos ni los proyectos de acuerdo propios del Senado)."),
)

CAMARA = "https://opendata.camara.cl/camaradiputados/WServices"
WEB_CAMARA = "https://www.camara.cl/legislacion"
SENADO = "https://tramitacion.senado.cl/wspublico"
NS = "{http://opendata.camara.cl/camaradiputados/v1}"
SENTIDO_CAMARA = {"1": "si", "0": "no", "2": "abstencion", "3": "no_vota", "4": "no_vota"}
SENTIDO_SENADO = {"si": "si", "no": "no", "abstencion": "abstencion", "pareo": "no_vota"}
LOTE = 300


# ------------------------------------------------------------------ utilidades

def _t(e, ruta):
    """Texto de un hijo (ruta «A/B») de un elemento del espacio de nombres de la Cámara."""
    x = e.find(_ns(ruta)) if e is not None else None
    return (x.text or "").strip() if x is not None and x.text else ""


def _ns(ruta):
    return "/".join(NS + p for p in ruta.split("/"))


def _plano(t):
    t = unicodedata.normalize("NFKD", t or "")
    return re.sub(r"\s+", " ", "".join(c for c in t if not unicodedata.combining(c))).strip().lower()


def _slug(t):
    return re.sub(r"[^a-z0-9]+", "-", _plano(t)).strip("-")


def _limpio(t):
    return re.sub(r"\s+", " ", html.unescape(t or "")).strip()


def _periodo(fecha):
    """Periodo legislativo de la Cámara (9 = 2018-2022, 10 = 2022-2026…); empieza el 11 de marzo."""
    a = int(fecha[:4]) - (1 if fecha[5:10] < "03-11" else 0)
    return 9 + (a - 2018) // 4


def _xml(ctx, url, nombre=None, caduca_horas=None):
    if nombre:
        return ET.parse(ctx.cache(url, nombre, caduca_horas=caduca_horas)).getroot()
    return ET.fromstring(ctx.fetch(url))


# ------------------------------------------------------------------ clasificación

TRATADO = re.compile(r"^(aprueba|proyecto de acuerdo que aprueba)\b.{0,160}?\b(acuerdo|convenio|tratado|protocolo|convenci[oó]n|"
                     r"enmiendas?|memor[aá]ndum|canje de notas|estatuto|carta|pacto|arreglo)\b", re.I)


def tipo_asunto_proyecto(nombre, boletin):
    n = _limpio(nombre)
    if TRATADO.search(n) and (boletin.endswith("-10") or re.search(
            r"rep[uú]blica|gobierno|reino|internacional|organizaci[oó]n|suscrit|adoptad|firmad|uni[oó]n europea|naciones", n, re.I)):
        return "tratado"
    return "ley"


# Se aplica al texto sin tildes y en minúsculas (_plano).
PARCIAL = re.compile(r"^((en )?votacion (en )?(particular|general|separada)( de| del)? )?(el |la |los |las |lo )?"
                     r"(articulos?\b|numerales?\b|numeros?\b|letras?\b|literal(es)?\b|incisos?\b|parrafos?\b|frases?\b|"
                     r"titulos?\b|resto del|norma|"
                     r"enmiendas? (incorporadas? por el senado |del senado )?(al|a la|a los|a las|en el|"
                     r"recaidas? en (el|la|los|las) "
                     r"(art|num|inc|letr|lit|parr|frase|tit))|enmiendas? (del senado |incorporadas? por el senado )?"
                     r"(que|para)\b|propuesta del senado|(la |las )?modificacion(es)? del senado (al|a la|que|para))")


def tipo_votacion_camara(tipo, texto):
    """`tipo` es TipoVotacionProyectoLey (General, Particular, General y Particular, Admisibilidad, Cierre Debate, Única)."""
    t = _plano(texto).lstrip("-–•· ")
    tp = _plano(tipo)
    if tp in ("admisibilidad", "cierre debate") or re.search(r"\b(clausura|cierre) del debate|reapertura|cuesti[oó]n de reglamento|"
                                                            r"reclamaci[oó]n|segunda discusi[oó]n|aplazamiento", t):
        return "procedimiento"
    if "comision mixta" in t and re.search(r"proposici[oó]n|informe|propuesta", t):
        return "final"
    if re.search(r"^(las |la )?observaciones|\bveto\b", t):
        return "enmienda"
    if re.match(r"^(la |las )?indicaci[oó]n", t):
        return "enmienda"
    if PARCIAL.match(t) or "votacion separada" in t:
        return "parcial"
    if tp in ("general", "general y particular", "unica"):
        return "final"
    if tp == "particular":
        return "parcial"
    return "otra"


def tipo_votacion_senado(tipo, texto):
    t = _plano(texto).lstrip("-–•· ")
    tp = _plano(tipo)
    if re.match(r"(solicitud|peticion)\b", t) or re.search(r"sesionar|simultane|segunda discusion|aplazamiento|clausura del debate|"
                                                          r"reapertura|preferencia|nuevo informe|vuelva a (la )?comision|"
                                                          r"envio a (la )?comision|remitir", t):
        return "procedimiento"
    if "comision mixta" in tp or ("comision mixta" in t and "informe" in t):
        return "final"
    if "observaciones" in t and "presidente" in t or re.search(r"\bveto\b", t):
        return "enmienda"
    # «normas que no fueron objeto de indicaciones» no es una indicación: solo cuenta si es lo que se vota.
    if re.match(r"^((en votacion|aprobacion|rechazo|votacion) (de )?)?(la |las |una )?indicaci", t):
        return "enmienda"
    if "general" in tp:
        return "final"
    if "particular" in tp:
        return "parcial"
    if "unica" in tp:
        return "parcial" if re.search(r"\b(articulo|numeral|inciso|letra|literal)\b", t) and not re.search(
            r"proyecto de acuerdo|modificaciones|enmiendas introducidas|en general", t) else "final"
    return "otra"


def resultado_camara(valor, si, no):
    if valor in ("1", "0", "4"):
        return "aprobada" if valor == "1" else "rechazada"
    return "aprobada" if si > no else "rechazada"


# ------------------------------------------------------------------ Cámara: diputados y militancias

def _militancias(ctx, periodos, actual):
    """{id diputado: [(inicio, fin, partido)]} con la militancia fechada de todos los periodos pedidos."""
    mil = {}
    for p in periodos:
        raiz = _xml(ctx, f"{CAMARA}/WSDiputado.asmx/retornarDiputadosXPeriodo?prmPeriodoId={p}", f"diputados_{p}.xml",
                    caduca_horas=24 if p >= actual else None)
        for dp in raiz.iter(NS + "Diputado"):
            did = _t(dp, "Id")
            lista = mil.setdefault(did, [])
            for m in dp.iter(NS + "Militancia"):
                ini = _t(m, "FechaInicio")[:10]
                fin = _t(m, "FechaTermino")[:10] or "9999-12-31"
                partido = _t(m, "Partido/Id") or "IND"
                if (ini, fin, partido) not in lista:
                    lista.append((ini, fin, partido))
    return mil


def _partido_en(militancias, fecha):
    """La militancia vigente en la fecha (si se solapan, la que empezó más tarde)."""
    vigentes = [m for m in militancias if m[0] <= fecha <= m[1]]
    return max(vigentes)[2] if vigentes else "IND"


# ------------------------------------------------------------------ Cámara: votaciones

def _lista_anio(ctx, anio, cerrado):
    """Votaciones de la Sala de un año (el fichero de un año cerrado no se vuelve a descargar)."""
    raiz = _xml(ctx, f"{CAMARA}/WSLegislativo.asmx/retornarVotacionesXAnno?prmAnno={anio}", f"votaciones_{anio}.xml",
                caduca_horas=None if cerrado else 6)
    salida = []
    for v in raiz.iter(NS + "Votacion"):
        tipo = v.find(NS + "Tipo")
        res = v.find(NS + "Resultado")
        salida.append(dict(id=_t(v, "Id"), desc=_t(v, "Descripcion"), fecha=_t(v, "Fecha"), si=int(_t(v, "TotalSi") or 0),
                           no=int(_t(v, "TotalNo") or 0), abst=int(_t(v, "TotalAbstencion") or 0),
                           disp=int(_t(v, "TotalDispensado") or 0), quorum=_t(v, "Quorum"),
                           tipo=tipo.get("Valor") if tipo is not None else "", resultado=res.get("Valor") if res is not None else ""))
    return salida


def _boletin(desc):
    m = re.search(r"Bolet[íi]n N[°º]?\s*([\d.]+-\d+)", desc or "")
    return m.group(1).replace(".", "") if m else None


def _proyecto(ctx, boletin):
    """Nombre del proyecto y, por votación, (tipo de votación, artículo, trámite)."""
    try:
        raiz = _xml(ctx, f"{CAMARA}/WSLegislativo.asmx/retornarVotacionesXProyectoLey?prmNumeroBoletin={boletin}")
    except Exception as e:
        ctx.log(f"   ! boletín {boletin}: {type(e).__name__}: {e}")
        return None
    votos = {}
    for v in raiz.iter(NS + "VotacionProyectoLey"):
        votos[_t(v, "Id")] = (_t(v, "TipoVotacionProyectoLey"), _limpio(_t(v, "Articulo")), _t(v, "TramiteConstitucional"))
    return dict(id=_t(raiz, "Id"), nombre=_limpio(_t(raiz, "Nombre")), fecha=_t(raiz, "FechaIngreso")[:10] or None, votos=votos)


def _detalle(ctx, vid):
    try:
        raiz = _xml(ctx, f"{CAMARA}/WSLegislativo.asmx/retornarVotacionDetalle?prmVotacionId={vid}")
    except Exception as e:
        ctx.log(f"   ! votación {vid}: {type(e).__name__}: {e}")
        return None
    votos = []
    for v in raiz.iter(NS + "Voto"):
        d = v.find(NS + "Diputado")
        op = v.find(NS + "OpcionVoto")
        nombre = " ".join(x for x in (_t(d, "Nombre"), _t(d, "ApellidoPaterno"), _t(d, "ApellidoMaterno")) if x)
        votos.append((_t(d, "Id"), nombre, SENTIDO_CAMARA.get(op.get("Valor") if op is not None else "", "no_vota")))
    return votos


def _materia(ctx, vid):
    """Materia de una votación sin boletín (proyectos de resolución y de acuerdo, otros): solo la da la ficha
    de la votación en camara.cl (los votos se toman igualmente del servicio XML)."""
    try:
        t = ctx.fetch(f"{WEB_CAMARA}/sala_sesiones/votacion_detalle.aspx?prmIdVotacion={vid}").decode("utf-8", "replace")
    except Exception as e:
        ctx.log(f"   ! materia de la votación {vid}: {type(e).__name__}: {e}")
        return None
    m = re.search(r"Materia:</div>\s*<div class=\"info\">\s*<strong>(.*?)</strong>", t, re.S)
    return _limpio(re.sub(r"<[^>]+>", " ", m.group(1))) if m else None


PROCEDIMIENTO_OTROS = re.compile(r"refundir|integraci[oó]n de la comisi[oó]n|clausura|cierre del debate|reapertura|tabla|"
                                 r"sesi[oó]n especial|votaci[oó]n separada|cambio de tr[aá]mite|remitir|env[ií]o|"
                                 r"prorrogar el plazo|ampliar el plazo|plazo de la comisi[oó]n|facultar|autorizaci[oó]n para que sesione|"
                                 r"nuevo tr[aá]mite|tr[aá]mite de comisi[oó]n|dar cuenta|suspender|preferencia|radicad|reclamaci[oó]n|"
                                 r"inadmisib|^petici[oó]n de la comisi[oó]n|^solicitud de la comisi[oó]n|pase a la comisi[oó]n|"
                                 r"remita a la comisi[oó]n|vuelva a (la )?comisi[oó]n", re.I)


def _asunto_otro(v, materia, fecha):
    """Asunto de una votación que no es de un proyecto de ley: (id, título, código, tipo de asunto, tipo de votación)."""
    desc = v["desc"]
    m = re.match(r"Proyecto de (Resoluci[oó]n|Acuerdo) N[°º]?\s*(\d+)", desc)
    periodo = _periodo(fecha)
    titulo = materia or desc
    if m:
        clase = "res" if m.group(1).lower().startswith("resol") else "acu"
        nombre = "Proyecto de resolución" if clase == "res" else "Proyecto de acuerdo"
        return (f"chl:{clase}:{periodo}:{m.group(2)}", titulo, f"{nombre} N.º {m.group(2)} ({2018 + 4 * (periodo - 9)}-"
                f"{2022 + 4 * (periodo - 9)})", "resolucion", "final")
    clase = _plano(re.sub(r"^\d+-", "", desc))
    t = _plano(materia)
    # La categoría de la fuente no siempre acierta (hay cierres de debate marcados como acusación): se mira la materia.
    if "acusacion" in clase and (not t or re.search(r"acusacion|cuestion previa|capitulo", t)):
        tv = ("procedimiento" if re.search(r"integraci[oó]n|comisi[oó]n de tres|formalice", t)
              else "procedimiento" if "cuestion previa" in t else "final")
        return f"chl:acusacion:{fecha}", titulo, "Acusación constitucional", "otro", tv
    if PROCEDIMIENTO_OTROS.search(t) or "tramite" in clase:
        return f"chl:otros:{v['id']}", titulo, None, "procedimiento", "procedimiento"
    if "comision investigadora" in clase or re.search(r"comision especial investigadora", t):
        return f"chl:otros:{v['id']}", titulo, "Comisión investigadora", "otro", "final"
    if re.search(r"estado de (excepci[oó]n|cat[aá]strofe|emergencia|sitio|asamblea)", t):
        return f"chl:otros:{v['id']}", titulo, None, "resolucion", "final"
    if re.search(r"\b(elecci[oó]n|designaci[oó]n|nombramiento|propuesta .* (consejer|ministr|fiscal|contralor))", t):
        return f"chl:otros:{v['id']}", titulo, None, "nombramiento", "nombramiento"
    return f"chl:otros:{v['id']}", titulo, None, "otro", "otra"


def _procesar_camara(ctx, lista, militancias, proyectos):
    """Descarga el detalle de un lote de votaciones de la Cámara y lo guarda."""
    boletines = sorted({b for v in lista if (b := _boletin(v["desc"])) and b not in proyectos})
    sin_boletin = [v for v in lista if not _boletin(v["desc"])]
    with ThreadPoolExecutor(8) as ex:
        for b, p in zip(boletines, ex.map(lambda b: _proyecto(ctx, b), boletines)):
            proyectos[b] = p
        detalles = dict(zip([v["id"] for v in lista], ex.map(lambda v: _detalle(ctx, v["id"]), lista)))
        materias = dict(zip([v["id"] for v in sin_boletin], ex.map(lambda v: _materia(ctx, v["id"]), sin_boletin)))
    asuntos, votaciones = {}, []
    fallidas = set()
    for v in lista:
        detalle = detalles.get(v["id"])
        if detalle is None:
            fallidas.add(v["id"])
            continue
        fecha = v["fecha"][:10]
        numero = int(v["fecha"][11:19].replace(":", "") or 0) if len(v["fecha"]) >= 19 else None
        b = _boletin(v["desc"])
        url = f"{WEB_CAMARA}/sala_sesiones/votacion_detalle.aspx?prmIdVotacion={v['id']}"
        if b:
            p = proyectos.get(b) or {}
            aid = f"chl:{b}"
            if aid not in asuntos:
                asuntos[aid] = Asunto(
                    id=aid, titulo=(p.get("nombre") or f"Boletín {b}")[:400], tipo=tipo_asunto_proyecto(p.get("nombre") or "", b),
                    fecha=p.get("fecha") or fecha, codigo=f"Boletín {b}",
                    url=f"{WEB_CAMARA}/ProyectosDeLey/tramitacion.aspx?prmID={p['id']}&prmBOLETIN={b}" if p.get("id") else None)
            tipo_v, articulo, tramite = (p.get("votos") or {}).get(v["id"], ("", "", ""))
            texto = " · ".join(x for x in (tramite, tipo_v) if x)
            texto = (f"{texto}: {articulo}" if texto and articulo else texto or articulo or v["desc"])[:600]
            tv = tipo_votacion_camara(tipo_v, articulo)
        else:
            materia = materias.get(v["id"])
            aid, titulo, codigo, tipo_a, tv = _asunto_otro(v, materia, fecha)
            if aid not in asuntos:
                asuntos[aid] = Asunto(id=aid, titulo=titulo[:400], tipo=tipo_a, fecha=fecha, codigo=codigo, url=url)
            elif "deducida" in _plano(titulo) and "deducida" not in _plano(asuntos[aid].titulo):
                asuntos[aid].titulo = titulo[:400]  # la acusación se titula con la votación que dice contra quién es
            texto = (materia or v["desc"])[:600]
        votos = []
        for did, nombre, sentido in detalle:
            partido = _partido_en(militancias.get(did, []), fecha)
            if partido not in FUENTE.partidos:
                ctx.partido(partido)
            votos.append((f"chl:{did}", nombre, partido, sentido))
        votaciones.append(Votacion(
            id=f"chl:d{v['id']}", fecha=fecha, asunto_id=aid, camara="chl-d", numero=numero, texto=texto, tipo=tv,
            a_favor=v["si"], en_contra=v["no"], abstenciones=v["abst"], no_votan=v["disp"], mayoria=v["quorum"] or None,
            resultado=resultado_camara(v["resultado"], v["si"], v["no"]), url=url, votos=votos))
    ctx.guardar(list(asuntos.values()), votaciones)
    return fallidas


def _recoger_camara(ctx, militancias):
    hoy = date.today()
    cerrados = set(ctx.marca("camara_cerrados", []))
    pendientes = set(ctx.marca("camara_pendientes", []))  # votaciones cuyo detalle falló la última vez
    ultima = ctx.con.execute("SELECT MAX(fecha) FROM votacion WHERE fuente='chl' AND camara='chl-d'").fetchone()[0]
    # Se repasan dos semanas antes de la última votación guardada (correcciones, votaciones publicadas tarde).
    desde = (date.fromisoformat(ultima) - timedelta(days=14)).isoformat() if ultima and not ctx.completo else f"{ctx.desde}-01-01"
    proyectos, boletines, fallidas = {}, set(), set()
    for anio in range(ctx.desde, hoy.year + 1):
        cerrado = anio in cerrados and not ctx.completo
        lista = _lista_anio(ctx, anio, cerrado or anio < hoy.year - 1)
        boletines |= {b for v in lista if (b := _boletin(v["desc"]))}
        if cerrado:
            continue
        lista = sorted((v for v in lista if v["fecha"][:10] >= max(desde, f"{ctx.desde}-01-01") or v["id"] in pendientes),
                       key=lambda v: v["fecha"])
        fallidas_anio = set()
        if lista:
            ctx.log(f"   Cámara {anio}: {len(lista)} votaciones")
            for i in range(0, len(lista), LOTE):
                fallidas_anio |= _procesar_camara(ctx, lista[i:i + LOTE], militancias, proyectos)
                ctx.log(f"   Cámara {anio}: {min(i + LOTE, len(lista))}/{len(lista)}")
        if fallidas_anio:
            ctx.log(f"   ! Cámara {anio}: {len(fallidas_anio)} votaciones sin detalle; se reintentan en la próxima recogida")
            fallidas |= fallidas_anio
        elif anio < hoy.year and hoy >= date(anio + 1, 2, 1):
            cerrados.add(anio)
            ctx.poner_marca("camara_cerrados", sorted(cerrados))
    ctx.poner_marca("camara_pendientes", sorted(fallidas))
    return boletines, proyectos


# ------------------------------------------------------------------ Senado

BCN_PARTIDO = {
    "partido-union-democrata-independiente": "UDI", "partido-renovacion-nacional": "RN", "evopoli": "EVOP",
    "partido-republicano-de-chile": "PREP", "partido-socialista-de-chile": "PS", "partido-por-la-democracia": "PPD",
    "partido-democrata-cristiano": "DC", "partido-comunista-de-chile": "PC", "revolucion-democratica": "RD",
    "partido-frente-amplio": "FA", "partido-convergencia-social": "PCS", "partido-democratas-chile": "DEM",
    "partido-social-cristiano": "PSC", "federacion-regionalista-verde-social": "FRVS", "partido-nacional-libertario": "PNL",
    "partido-liberal-de-chile": "PL", "partido-humanista": "PH", "partido-regionalista-de-los-independientes": "PRI",
    "independiente": "IND", "partido-radical-de-chile": "PR", "partido-radical-socialdemocrata": "PR",
    "partido-amplio-de-izquierda-socialista": "PAIS", "partido-pais-progresista": "PAIS", "movimiento-amplio-social": "MAS",
    "partido-de-la-gente": "PDG", "partido-ecologista-verde": "PEV", "partido-comunes": "COMUNES",
    "partido-accion-humanista": "PAH", "partido-progresista": "PRO", "amarillos-por-chile": "AMA",
    "movimiento-amarillos-por-chile": "AMA", "partido-igualdad": "IGUAL", "partido-conservador-cristiano": "PCC",
}

BCN_SPARQL = """PREFIX bio: <http://datos.bcn.cl/ontologies/bcn-biographies#>
SELECT ?persona ?pat ?mat ?nombre ?ini ?fin ?partido ?mini ?mfin WHERE {
 ?persona bio:hasPositionPeriod ?pp . ?pp bio:hasBeginning ?b . ?b <http://www.w3.org/2000/01/rdf-schema#label> ?lab .
 FILTER(CONTAINS(STR(?lab), "Senador"))
 ?b bio:originalDate ?ini . OPTIONAL { ?pp bio:hasEnd ?e . ?e bio:originalDate ?fin }
 FILTER(STR(?ini) >= "2010")
 ?persona bio:surnameOfFather ?pat . OPTIONAL { ?persona bio:surnameOfMother ?mat } ?persona <http://xmlns.com/foaf/0.1/givenName> ?nombre .
 OPTIONAL { ?persona bio:hasMilitancy ?m . ?m bio:hasPoliticalParty ?partido .
            OPTIONAL { ?m bio:hasBeginning ?mb . ?mb bio:originalDate ?mini } OPTIONAL { ?m bio:hasEnd ?me . ?me bio:originalDate ?mfin } }
} LIMIT 10000"""


def _senadores(ctx):
    """Senadores desde 2010 con sus militancias fechadas, de datos.bcn.cl: [dict]."""
    url = "https://datos.bcn.cl/sparql?" + urllib.parse.urlencode({"query": BCN_SPARQL, "format": "json"})
    try:
        ruta = ctx.cache(url, "bcn_senadores.json", caduca_horas=24 * 7, headers={"Accept": "application/sparql-results+json"})
        filas = json.loads(ruta.read_text(encoding="utf-8"))["results"]["bindings"]
    except Exception as e:
        ctx.log(f"   ! datos.bcn.cl no responde ({type(e).__name__}: {e}): senadores sin partido")
        return []
    personas = {}
    for f in filas:
        g = lambda k: (f.get(k) or {}).get("value", "").strip()
        p = personas.setdefault(g("persona"), dict(pat=_plano(g("pat")), mat=_plano(g("mat")), nombre=_plano(g("nombre")),
                                                   completo=f"{g('nombre')} {g('pat')} {g('mat')}".strip(),
                                                   escanos=set(), militancias=set()))
        p["escanos"].add((g("ini")[:10], g("fin")[:10] or "9999-12-31"))
        if g("partido"):
            p["militancias"].add((g("mini")[:10] or "0000-00-00", g("mfin")[:10] or "9999-12-31", g("partido").rsplit("/", 1)[-1]))
    return list(personas.values())


def _nombre_senado(t):
    """«Ossandón I., Manuel José» -> («ossandón», «i», «manuel josé»)."""
    t = re.sub(r"\s+", " ", t or "").strip()
    izq, _, der = t.rpartition(",")
    if not izq:
        izq, der = t, ""
    izq = izq.strip()
    m = re.match(r"^(.*\S)\s+(\w)\.?$", izq)
    if m and len(m.group(2)) == 1:
        return m.group(1), m.group(2), der.strip()
    return izq.rstrip(" ."), "", der.strip()


class Senadores:
    def __init__(self, ctx):
        self.ctx = ctx
        self.lista = _senadores(ctx)
        self.cache = {}
        self.sin_partido = set()

    def buscar(self, texto, fecha):
        clave = (texto, fecha)
        if clave in self.cache:
            return self.cache[clave]
        pat, ini, nombre = _nombre_senado(texto)
        pp, pi, pn = _plano(pat), _plano(ini), _plano(nombre)
        cand = [s for s in self.lista if s["pat"] == pp or s["pat"].replace(" ", "") == pp.replace(" ", "")]
        if pi:
            cand = [s for s in cand if s["mat"].startswith(pi)] or cand
        if len(cand) > 1:
            cand = [s for s in cand if any(a <= fecha <= b for a, b in s["escanos"])] or cand
        if len(cand) > 1 and pn:
            cand = [s for s in cand if set(pn.split()) & set(s["nombre"].split())] or cand
        mid = "chl:s-" + _slug(f"{pat} {ini} {nombre}")
        visible = f"{nombre} {pat}".strip() if nombre else pat
        partido = "IND"
        if len(cand) == 1:
            s = cand[0]
            visible = s["completo"]
            vigentes = [m for m in s["militancias"] if m[0] <= fecha <= m[1]]
            if vigentes:
                slug = max(vigentes)[2]
                partido = BCN_PARTIDO.get(slug) or slug.upper()[:20]
                if partido not in FUENTE.partidos:
                    self.ctx.partido(partido, slug.replace("-", " ").capitalize())
        else:
            self.sin_partido.add(texto)
        self.cache[clave] = (mid, visible, partido)
        return self.cache[clave]


def _fecha_senado(t):
    try:
        return datetime.strptime(t.strip(), "%d/%m/%Y").date().isoformat()
    except ValueError:
        return None


def _votaciones_senado(raiz):
    """Elementos <votacion> de votaciones.php o de un <proyecto> de tramitacion.php."""
    return [v for v in raiz.iter("votacion")]


def _url_senado(boletin):
    return f"https://tramitacion.senado.cl/appsenado/templates/tramitacion/index.php?boletin_ini={boletin}"


def _titulo_tema(tema):
    """«Proyecto de ley, en segundo trámite constitucional, que otorga reajuste… (Boletín N° 17.286-05)…»
    -> «Otorga reajuste…»."""
    m = re.search(r"\bque (.+?)\s*[,.]?\s*\(Bolet", tema or "", re.S | re.I)
    t = _limpio(m.group(1) if m else (tema or "")[:300])
    return t[:1].upper() + t[1:]


def _procesar_senado(ctx, boletin, elementos, fichas, senadores):
    """Convierte las votaciones de un boletín en el Senado: (asunto, [Votacion])."""
    # El servicio se consulta por número; el sufijo (comisión) bueno es el que cita el propio Senado.
    for v in elementos:
        citado = re.search(r"Bolet[íi]n N[°º]?\s*([\d.]+-\d+)", v.findtext("TEMA") or "")
        if citado and citado.group(1).replace(".", "").split("-")[0] == boletin.split("-")[0]:
            boletin = citado.group(1).replace(".", "")
            break
    ficha = fichas.get(boletin) or {}
    aid = f"chl:{boletin}"
    votaciones = []
    if not ficha.get("nombre") and any((_fecha_senado(v.findtext("FECHA") or "") or "") >= f"{ctx.desde}-01-01" for v in elementos):
        # Proyecto antiguo: el nombre, de la Cámara (mismo título que sus votaciones allí).
        ficha = fichas[boletin] = _proyecto(ctx, boletin) or {}
    por_sesion = {}
    primera = None
    for v in elementos:
        g = lambda k: _limpio((v.findtext(k) or ""))
        fecha = _fecha_senado(g("FECHA"))
        sesion = g("SESION")
        k = por_sesion[sesion] = por_sesion.get(sesion, 0) + 1
        if not fecha or fecha < f"{ctx.desde}-01-01":
            continue
        tema = g("TEMA")
        primera = primera or tema
        resto = re.split(r"\(Bolet[íi]n[^)]*\)\s*\.?", tema, maxsplit=1)
        detalle = (resto[1] if len(resto) > 1 else tema).strip() or tema
        tipo_v = g("TIPOVOTACION")
        texto = " · ".join(x for x in (g("ETAPA"), tipo_v) if x)
        texto = (f"{texto}: {detalle}" if texto else detalle)[:600]
        si, no, abst, pareo = (int(g(x) or 0) for x in ("SI", "NO", "ABSTENCION", "PAREO"))
        m = re.findall(r"\b(APROBAD[OA]S?|RECHAZAD[OA]S?)\b", tema)
        resultado = ("aprobada" if m[-1].startswith("APROB") else "rechazada") if m else ("aprobada" if si > no else "rechazada")
        votos = []
        for voto in v.iter("VOTO"):
            nombre = _limpio(voto.findtext("PARLAMENTARIO"))
            sentido = SENTIDO_SENADO.get(_plano(voto.findtext("SELECCION")), "no_vota")
            mid, visible, partido = senadores.buscar(nombre, fecha)
            votos.append((mid, visible, partido, sentido))
        numero_sesion = re.sub(r"\D+", "-", sesion).strip("-") or "s"
        votaciones.append(Votacion(
            id=f"chl:s:{boletin.split('-')[0]}:{numero_sesion}:{k}", fecha=fecha, asunto_id=aid, camara="chl-s",
            numero=len(votaciones) + 1, texto=texto, tipo=tipo_votacion_senado(tipo_v, detalle), a_favor=si, en_contra=no,
            abstenciones=abst, no_votan=pareo, mayoria=g("QUORUM") or None, resultado=resultado, url=_url_senado(boletin),
            votos=votos or None))
    if not votaciones:
        return None, []
    nombre = ficha.get("nombre") or _titulo_tema(primera)
    asunto = Asunto(id=aid, titulo=nombre[:400], tipo=tipo_asunto_proyecto(nombre, boletin),
                    fecha=ficha.get("fecha") or min(v.fecha for v in votaciones), codigo=f"Boletín {boletin}",
                    url=(f"{WEB_CAMARA}/ProyectosDeLey/tramitacion.aspx?prmID={ficha['id']}&prmBOLETIN={boletin}"
                         if ficha.get("id") else _url_senado(boletin)))
    return asunto, votaciones


def _fichas(ctx, anios):
    """Proyectos ingresados en esos años (mociones y mensajes, de las dos cámaras): {boletín: ficha}."""
    fichas = {}
    hoy = date.today().year
    for anio in anios:
        for op in ("retornarMocionesXAnno", "retornarMensajesXAnno"):
            try:
                raiz = _xml(ctx, f"{CAMARA}/WSLegislativo.asmx/{op}?prmAnno={anio}", f"{op[8:].lower()}_{anio}.xml",
                            caduca_horas=None if anio < hoy else 24)
            except Exception as e:
                ctx.log(f"   ! {op} {anio}: {type(e).__name__}: {e}")
                continue
            for p in raiz.iter(NS + "ProyectoLey"):
                origen = p.find(NS + "CamaraOrigen")
                fichas[_t(p, "NumeroBoletin")] = dict(id=_t(p, "Id"), nombre=_limpio(_t(p, "Nombre")),
                                                      fecha=_t(p, "FechaIngreso")[:10] or None,
                                                      senado=origen is not None and origen.get("Valor") == "2")
    return fichas


def _recoger_senado(ctx, boletines_camara, proyectos):
    hoy = date.today()
    senadores = Senadores(ctx)
    hasta = ctx.marca("senado_hasta")
    fichas = _fichas(ctx, range(ctx.desde - 6, hoy.year + 1))
    fichas.update({b: p for b, p in proyectos.items() if p and p.get("nombre")})
    guardadas = 0
    if hasta and not ctx.completo and (hoy - date.fromisoformat(hasta)).days <= 25:
        # Lo nuevo: proyectos con movimiento desde la última recogida (el servicio no deja ir más de un mes atrás).
        desde = max(date.fromisoformat(hasta) - timedelta(days=5), hoy - timedelta(days=29))
        raiz = ET.fromstring(ctx.fetch(f"{SENADO}/tramitacion.php?fecha={desde.strftime('%d/%m/%Y')}", timeout=300))
        asuntos, votaciones = [], []
        for p in raiz.iter("proyecto"):
            boletin = (p.findtext("descripcion/boletin") or "").strip()
            if not boletin:
                continue
            ficha = fichas.setdefault(boletin, {})
            ficha.setdefault("nombre", _limpio(p.findtext("descripcion/titulo")))
            a, vs = _procesar_senado(ctx, boletin, _votaciones_senado(p), fichas, senadores)
            if a:
                asuntos.append(a)
                votaciones += vs
        for i in range(0, len(votaciones), LOTE):
            lote = votaciones[i:i + LOTE]
            ids = {v.asunto_id for v in lote}
            ctx.guardar([a for a in asuntos if a.id in ids], lote)
        guardadas = len(votaciones)
        ctx.log(f"   Senado: {guardadas} votaciones de proyectos con movimiento desde {desde}")
    else:
        # Repaso completo: boletines votados en la Cámara (desde tres años antes) y proyectos ingresados por el Senado.
        extra = set()
        for anio in range(ctx.desde - 3, ctx.desde):
            extra |= {b for v in _lista_anio(ctx, anio, anio < hoy.year - 1) if (b := _boletin(v["desc"]))}
        senado = {b for b, f in fichas.items() if f.get("senado") and (f.get("fecha") or "") >= f"{ctx.desde - 4}"}
        candidatos = sorted({b for b in set(boletines_camara) | extra | senado if re.fullmatch(r"\d+-\d+", b)},
                            key=lambda b: tuple(int(x) for x in b.split("-")))
        ctx.log(f"   Senado: repaso de {len(candidatos)} boletines")

        def bajar(b):
            try:
                datos = ctx.fetch(f"{SENADO}/votaciones.php?boletin={b.split('-')[0]}")
            except Exception as e:
                ctx.log(f"   ! Senado, boletín {b}: {type(e).__name__}: {e}")
                return b, None
            return b, ET.fromstring(datos) if datos.lstrip().startswith(b"<votaciones") else None

        with ThreadPoolExecutor(6) as ex:
            for i in range(0, len(candidatos), 200):
                asuntos, votaciones = [], []
                for b, raiz in ex.map(bajar, candidatos[i:i + 200]):
                    if raiz is None:
                        continue
                    a, vs = _procesar_senado(ctx, b, _votaciones_senado(raiz), fichas, senadores)
                    if a:
                        asuntos.append(a)
                        votaciones += vs
                if votaciones:
                    ctx.guardar(asuntos, votaciones)
                guardadas += len(votaciones)
                ctx.log(f"   Senado: {min(i + 200, len(candidatos))}/{len(candidatos)} boletines, {guardadas} votaciones")
    if senadores.sin_partido:
        ctx.log(f"   ! senadores sin identificar en datos.bcn.cl: {sorted(senadores.sin_partido)[:10]}")
    ctx.poner_marca("senado_hasta", hoy.isoformat())


def recoger(ctx):
    hoy = date.today().isoformat()
    periodos = range(_periodo(f"{ctx.desde}-01-01"), _periodo(hoy) + 1)
    militancias = _militancias(ctx, periodos, _periodo(hoy))
    boletines, proyectos = _recoger_camara(ctx, militancias)
    _recoger_senado(ctx, boletines, proyectos)
