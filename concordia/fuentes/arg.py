"""Argentina: votaciones nominales del Congreso de la Nación (Cámara de Diputados y Senado).

Diputados. El sitio oficial de votaciones (https://votaciones.hcdn.gob.ar) publica el acta de cada
votación electrónica con el voto de cada diputado, pero no responde fuera de Argentina (acepta la
conexión y nunca completa el TLS) y desde julio de 2026 pide reCAPTCHA en su buscador; el conjunto
«votaciones_nominales» de datos.hcdn.gob.ar se quedó en 2019. Se usa el espejo de ¿Cómo Votó?
(https://github.com/rquiroga7/como_voto, MIT): un único JSON con todas las actas del sitio oficial desde
1993, que su autor actualiza cada día con una GitHub Action (id del acta, título, fecha, resultado y
diputado, bloque y voto de cada banca). Cada acta es una votación: «en general», «en particular» (un
artículo, un título o un capítulo), «en general y en particular» o una moción. El título del acta nombra
el orden del día («O.D. 208 - ...») o, hasta 2021, el expediente («Expediente 0016-PE-2019 - ...»); con los
datos abiertos de la Cámara (dictámenes y proyectos, https://datos.hcdn.gob.ar, CC BY) se pasa del
orden del día al expediente, a su tipo y a su título oficial (en mayúsculas y sin tildes).

Senado. El sitio oficial (https://www.senado.gob.ar/votaciones/actas) da por año la lista de actas con
su expediente, su orden del día y si es en general o en particular, y el detalle de cada acta en HTML
con el voto de cada senador (id, bloque y provincia); no hace falta el PDF.

Un proyecto se identifica por su expediente en la cámara de origen: el Senado numera «CD-1/24» lo que
llega de Diputados y Diputados «0026-S-2026» lo que llega del Senado, y la tabla de proyectos de la HCDN
da la correspondencia; así la votación de las dos cámaras sobre la misma ley es un solo asunto. Los
órdenes del día se numeran de nuevo con cada composición de la Cámara (el 10 de diciembre de los años
impares); lo que no se puede enlazar con un expediente se agrupa por orden del día o por título.
"""

import csv
import hashlib
import html
import io
import json
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from .. import paises
from .modelo import Asunto, Fuente, Votacion


def codigo_bloque(nombre):
    """Código estable de un bloque: su nombre sin tildes, en mayúsculas y con los guiones y espacios
    normalizados (la fuente escribe el mismo bloque «Union Por La Patria», «UNIÓN POR LA PATRIA»...)."""
    s = unicodedata.normalize("NFKD", nombre or "").encode("ascii", "ignore").decode().upper()
    s = re.sub(r"\s*[-–—]\s*", " - ", s)
    return re.sub(r"\s+", " ", s).strip(" -") or "SIN BLOQUE"


# Color por familia política (sobre el código del bloque); lo que no casa es un partido provincial.
FAMILIAS = [
    (r"LIBERTAD AVANZA", "#6c3fb5"),
    (r"UNION POR LA PATRIA|FRENTE DE TODOS|FRENTE PARA LA VICTORIA|UNIDAD CIUDADANA|FRENTE NACIONAL Y POPULAR", "#1b9ad6"),
    (r"JUSTICIALIS|\bPJ\b|JUSTICIA SOCIAL|MOVIMIENTO EVITA|PERONISMO|FRENTE CIVICO POR SANTIAGO|INDEPENDENCIA|"
     r"PRODUCCION Y TRABAJO|NUEVO ENCUENTRO|RED POR ARGENTINA|ACCION FEDERAL|UNIDAD Y EQUIDAD", "#5fb4e0"),
    (r"^PRO$|FRENTE PRO|^PRO\b", "#f5c400"),
    (r"EVOLUCION RADICAL|DEMOCRACIA PARA SIEMPRE", "#ee7d7d"),
    (r"UNION CIVICA RADICAL|^UCR", "#d6202b"),
    (r"COALICION CIVICA", "#23a39a"),
    (r"IZQUIERDA|TRABAJADORES|\bPTS\b|PARTIDO OBRERO|\bMST\b", "#9e1b32"),
    (r"AVANZA LIBERTAD|REPUBLICANOS UNIDOS|BUENOS AIRES LIBRE|FUERZAS DEL CIELO|INTEGRACION Y DESARROLLO|^CREO$|"
     r"LIGA DEL INTERIOR|FUTURO Y LIBERTAD|COHERENCIA|VALORES REPUBLICANOS|DEMOCRATA", "#8e6bbf"),
    (r"HACEMOS|ENCUENTRO FEDERAL|PROVINCIAS UNIDAS|CONSENSO FEDERAL|CORDOBA FEDERAL|IDENTIDAD BONAERENSE|DEFENDAMOS|"
     r"FEDERAL UNIDOS|^UNIDOS$|PAIS FEDERAL|ADELANTE BUENOS AIRES|CAMBIO FEDERAL|ARGENTINA FEDERAL", "#f08a24"),
    (r"INNOVACION FEDERAL|CONCORDIA|MISION", "#00a19a"),
    (r"SOCIALIS|PROGRESISTA", "#e8579b"),
    (r"SIN DEFINIR|NO INTEGRA|SIN ESPECIFICAR|SIN BLOQUE", "#898781"),
]
COLOR_PROVINCIAL = "#9a8f7d"

# Bloques de Diputados y del Senado desde 2019 (nombre como lo escribe la fuente, con sus tildes) y siglas.
BLOQUES = [
    ("Unión por la Patria", "UxP"), ("Frente de Todos", "FdT"), ("PRO", "PRO"), ("Frente PRO", "PRO"),
    ("La Libertad Avanza", "LLA"), ("Unión Cívica Radical", "UCR"), ("UCR - Unión Cívica Radical", "UCR"), ("UCR", "UCR"),
    ("Coalición Cívica", "CC"), ("Alianza Coalición Cívica", "CC"), ("Frente para la Victoria - PJ", "FpV"),
    ("PJ Frente para la Victoria", "FpV"), ("Unidad Ciudadana", "UC"), ("Frente Nacional y Popular", "FNyP"),
    ("Justicialista", "PJ"), ("Encuentro Federal", "EF"), ("Innovación Federal", "IF"), ("Provincias Unidas", "PU"),
    ("Evolución Radical", "ER"), ("Democracia para Siempre", "DpS"), ("Hacemos Coalición Federal", "HCF"),
    ("Córdoba Federal", "CF"), ("Producción y Trabajo", "PyT"), ("Independencia", "Indep."),
    ("Frente de la Concordia Misionero", "FCM"), ("Frente Renovador de la Concordia Social", "FRCS"),
    ("Mid - Movimiento de Integración y Desarrollo", "MID"), ("Federal Unidos por una Nueva Argentina", "FUNA"),
    ("Por Santa Cruz", "PSC"), ("Consenso Federal", "CF"), ("Elijo Catamarca", "EC"), ("Juntos Somos Río Negro", "JSRN"),
    ("Socialista", "PS"), ("Partido Socialista", "PS"), ("Identidad Bonaerense", "IB"), ("Creo", "Creo"),
    ("Frente Cívico por Santiago", "FCS"), ("Unidad y Equidad Federal", "UEF"), ("Movimiento Popular Neuquino", "MPN"),
    ("Movimiento Neuquino", "MN"), ("La Neuquinidad", "LN"), ("Liga del Interior Eli", "LI"),
    ("Ser - Somos Energía para Renovar", "SER"), ("Buenos Aires Libre", "BAL"), ("Unidad Justicialista", "UJ"),
    ("Red por Argentina", "RxA"), ("Movimiento Evita", "Evita"), ("Argentina Federal", "AF"), ("Avanza Libertad", "AL"),
    ("Partido por la Justicia Social", "PJS"), ("Frente Progresista Cívico y Social", "FPCyS"), ("Acción Federal", "AcF"),
    ("Republicanos Unidos", "RU"), ("Justicialista por Tucumán", "PJT"), ("Coherencia", "Coh."), ("Unidos", "Unidos"),
    ("Ahora Patria", "AP"), ("Avanzar San Luis", "ASL"), ("Futuro y Libertad", "FyL"), ("Adelante Buenos Aires", "ABA"),
    ("Defendamos Córdoba", "DC"), ("Defendamos Santa Fe", "DSF"), ("Primero San Luis", "PSL"), ("País Federal", "PF"),
    ("Frente Cívico y Social de Catamarca", "FCSC"), ("Fte. Cívico y Social de Catamarca", "FCSC"),
    ("Somos Fueguinos", "SF"), ("Fuerzas del Cielo - Espacio Liberal F.C.E", "FdC"), ("Valores Republicanos", "VR"),
    ("Transformación", "Transf."), ("Transformación B.T", "Transf."), ("Partido Propuesta Salteña", "PPS"),
    ("Todos Juntos por San Juan", "TJSJ"), ("Partido Bloquista de San Juan", "PBSJ"), ("Somos", "Somos"),
    ("Somos Mendoza", "SM"), ("Trabajo y Dignidad", "TyD"), ("Salta Somos Todos", "SST"), ("Somos San Juan", "SSJ"),
    ("Concertación FORJA", "FORJA"), ("Protectora", "Prot."), ("Primero Argentina", "PA"),
    ("Nuevo Espacio Santafesino", "NES"), ("Cultura, Educación y Trabajo", "CEyT"), ("La Unión Mendocina", "LUM"),
    ("Demócrata", "PD"), ("Bloque Sin Definir", "S/B"), ("No Integra Bloque", "S/B"), ("Sin especificar", "S/B"),
    # Frente de Izquierda y de Trabajadores - Unidad y sus partidos (el nombre cambia casi cada año)
    ("Frente de Izquierda y de Trabajadores Unidad", "FIT-U"), ("Fte. de Izquierda y de los Trabajadores", "FIT"),
    ("PTS - Frente de Izquierda", "FIT"), ("PTS - Frente de Izquierda Unidad", "FIT-U"),
    ("PTS - Frente de Izquierda y de Trabajadores - Unidad", "FIT-U"), ("PTS - Frente de Izquierda y de Trabajadores Unidad", "FIT-U"),
    ("Izquierda Socialista - FIT", "FIT"), ("Izquierda Socialista - Frente de Izquierda", "FIT"),
    ("Izquierda Socialista FIT - Unidad", "FIT-U"), ("Izquierda Socialista - FIT - Unidad", "FIT-U"),
    ("Partido Obrero - Frente de Izquierda y de Trabajadores - Unidad", "FIT-U"),
    ("Partido Obrero - Frente de Izquierda y Trabajadores Unidad", "FIT-U"),
    ("Partido Obrero en el Frente de Izquierda y de Trabajadores - Unidad", "FIT-U"),
    ("Partido Obrero en el Fte de Izquierda y de Trabajadores - Unidad", "FIT-U"),
    ("MST - Frente de Izquierda y Trabajadores Unidad", "FIT-U"),
    ("Partido Obrero Frente de Izquierda y de Trabajadores - Unidad", "FIT-U"),
    # Senado
    ("Convicción Federal", "CF"), ("Unidad Federal", "UF"), ("Justicia Social Federal", "JSF"), ("Cambio Federal", "CaF"),
    ("Despierta Chubut", "DC"), ("Movere Santa Cruz", "MSC"), ("Movere por Santa Cruz", "MSC"), ("Misiones", "Mis."),
    ("Hay Futuro Argentina", "HFA"), ("Santa Fe Federal", "SFF"), ("Primero los Salteños", "PLS"),
    ("Movimiento por Misiones", "MxM"), ("Justicialista 8 de Octubre", "PJ"), ("Frente Popular", "FP"),
    ("Movimiento Popular Fueguino", "MPF"), ("PARES", "PARES"), ("Peronismo Republicano Río Negro", "PRRN"),
    ("Proyecto Sur-UNEN", "Sur"), ("RIO - Frente Progresista", "RIO"), ("Encuentro Misionero", "EM"),
    ("Justicialista San Luis", "PJ"), ("Nuevo Encuentro", "NE"), ("Concertación Plural", "CP"), ("Esperanza Federal", "EsF"),
    ("Federalismo Santafesino", "FS"), ("Federalismo y Liberación", "FyL"), ("Fuerza Republicana", "FR"),
    ("Justicialista para el Diálogo de los Argentinos", "PJ"), ("Partido Renovador de Salta", "PRS"),
    ("Proyecto Buenos Aires Federal", "PBAF"), ("Tucumán", "Tuc."), ("Vecinalista - Partido Nuevo", "PN"),
    ("Sin bloque", "S/B"),
]


def color_bloque(codigo):
    for patron, color in FAMILIAS:
        if re.search(patron, codigo):
            return color
    return COLOR_PROVINCIAL


def siglas_de(nombre):
    """Siglas de un bloque que no está en el catálogo: iniciales de las palabras con contenido."""
    palabras = [p for p in re.split(r"[\s\-–,.]+", nombre) if p and p.lower() not in ("de", "del", "la", "las", "los", "y", "por", "el", "en", "para")]
    return ("".join(p[0].upper() for p in palabras) or nombre)[:8]


FUENTE = Fuente(
    codigo="arg", pais="ARG", nombre="Congreso de la Nación Argentina", corto="Argentina", tipo="parlamento",
    detalle="nominal", web="https://votaciones.hcdn.gob.ar", desde=2019, idioma="es",
    licencia=("Dominio público (HCDN y Senado: uso libre citando la fuente); datos abiertos de la HCDN, CC BY 4.0; "
              "espejo de ¿Cómo Votó? (MIT)"),
    camaras={"arg-d": ("Cámara de Diputados", "Diputados", 257), "arg-s": ("Senado", "Senado", 72)},
    partidos={codigo_bloque(n): (n, s, color_bloque(codigo_bloque(n))) for n, s in BLOQUES},
    notas=("Voto de cada diputado y senador en las votaciones electrónicas del pleno (en general, en particular y "
           "mociones); lo que se vota a mano alzada no tiene registro. Diputados llega por el espejo diario de "
           "¿Cómo Votó?, porque el sitio oficial no responde fuera de Argentina."),
)

COMO_VOTO = "https://raw.githubusercontent.com/rquiroga7/como_voto/main/data/diputados.json"
CKAN = "https://datos.hcdn.gob.ar/api/3/action/package_show?id="
HCDN_VOTACION = "https://votaciones.hcdn.gob.ar/votacion/"
# La ficha de un proyecto de la HCDN solo se sirve bajo la ruta de una comisión (no hay una genérica); con
# cualquier comisión enseña la ficha completa del expediente (trámite en las dos cámaras).
HCDN_FICHA = "https://www.hcdn.gob.ar/comisiones/permanentes/caconstitucionales/proyecto.html?exp="
SENADO = "https://www.senado.gob.ar"
MARGEN_DIAS = 30  # se repasa un mes: el orden del día de lo último puede tardar en llegar a los datos abiertos
LOTE = 250

# Voto: ¿Cómo Votó? guarda un código (0 es «SIN VOTAR»: presente sin votar); el Senado, el texto.
SENTIDO_CV = {1: "si", 2: "no", 3: "abstencion", 0: "abstencion", 4: "no_vota", 5: "no_vota"}
SENTIDO_TEXTO = {"AFIRMATIVO": "si", "SI": "si", "NEGATIVO": "no", "NO": "no", "ABSTENCION": "abstencion",
                 "SIN VOTAR": "abstencion", "AUSENTE": "no_vota", "PRESIDENTE": "no_vota", "": "no_vota"}


def _sin_tildes(t):
    return unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode()


def _limpio(t):
    return re.sub(r"\s+", " ", html.unescape(t or "")).strip()


def _texto_html(fragmento):
    return _limpio(re.sub(r"<[^>]+>", " ", fragmento or ""))


# ------------------------------------------------------------------ expedientes y órdenes del día

# «0016-PE-2019», «12-S-2019», «146-S.-2020», «04-PE-20», «92-JGM-20» (numeración de Diputados).
RE_EXP = re.compile(r"\b(\d{1,5})\s*-\s*(D|S|PE|JGM|CD|OV|P)\s*\.?\s*-\s*(\d{4}|\d{2})\b", re.I)
# A veces con el tipo delante: «EXP. PE-76-2024».
RE_EXP_INV = re.compile(r"\b(D|S|PE|JGM|CD|OV)\s*-\s*(\d{1,5})\s*-\s*(\d{4}|\d{2})\b", re.I)
# «O.D. 208», «OD 29», «OD:590», «O.D. 412,413 y 433», «od 386 - od 385» (cada «O.D.» es una coincidencia).
RE_OD = re.compile(r"\bO\.?\s?D\.?\s*[:.]?\s*(\d{1,4}(?:\s*(?:,|\by\b)\s*\d{1,4})*)", re.I)


def exp_norm(numero, tipo, anio):
    anio = int(anio)
    return f"{int(numero):04d}-{tipo.upper()}-{anio + 2000 if anio < 100 else anio}"


def exp_senado_legible(exp):
    """«0074-PE-2026» (numeración del Senado) -> «PE-74/26», como lo escribe el Senado."""
    n, t, a = exp.split("-")
    return f"{t}-{int(n)}/{a[2:]}"


def bienio(fecha):
    """Año de inicio de la composición de la Cámara (10 de diciembre de los años impares): los órdenes del
    día de Diputados se numeran desde 1 en cada una."""
    y = int(fecha[:4])
    if y % 2:
        return y if fecha[5:] >= "12-10" else y - 2
    return y - 1


class Referencias:
    """Datos abiertos de la HCDN: dictámenes (orden del día -> proyecto) y proyectos (expedientes, tipo y
    título). Se cargan solo si hay algo que guardar."""

    def __init__(self, ctx):
        self.ctx = ctx
        self._cargado = False
        self._cd = None
        self.por_id, self.por_dip, self.por_sen, self.ods, self.por_ley = {}, {}, {}, {}, {}

    def _csv(self, paquete, nombre):
        recursos = self.ctx.json(CKAN + paquete)["result"]["resources"]
        url = next(r["url"] for r in recursos if (r.get("format") or "").upper() == "CSV")
        ruta = self.ctx.cache(url.replace(":443/", "/"), nombre, caduca_horas=20, timeout=300)
        return csv.DictReader(io.StringIO(ruta.read_text(encoding="utf-8-sig", errors="replace")))

    def cargar(self):
        if self._cargado:
            return
        for r in self._csv("proyectos-parlamentarios", "hcdn_proyectos.csv"):
            p = {"id": r["PROYECTO_ID"], "titulo": _limpio(r.get("TITULO")), "tipo": (r.get("TIPO") or "").upper(),
                 "dip": _exp_csv(r.get("EXP_DIPUTADOS")), "sen": _exp_csv(r.get("EXP_SENADO")),
                 "origen": r.get("CAMARA_ORIGEN") or "", "autor": _limpio(r.get("AUTOR")) or None}
            self.por_id[p["id"]] = p
            if p["dip"]:
                self.por_dip.setdefault(p["dip"], p)
            if p["sen"]:
                self.por_sen.setdefault(p["sen"], p)
        for r in self._csv("dictamenes", "hcdn_dictamenes.csv"):
            if not (r.get("NUMERO") or "").strip().isdigit() or not r.get("FECHA") or not r["TIPO"].lower().startswith("orden"):
                continue
            fecha = r["FECHA"][:10]
            clave = (bienio(fecha), int(r["NUMERO"]))
            # El proyecto principal del dictamen: no el «tenido a la vista», y el que reúne más expedientes.
            peso = (0 if "TENIDO A LA VISTA" in (r.get("OBSERVACIONES") or "").upper() else 1,
                    int(r["EXPEDIENTES"]) if (r.get("EXPEDIENTES") or "").isdigit() else 1, r["EXPEDIENTE"])
            self.ods.setdefault(clave, []).append((peso, fecha, r["EXPEDIENTE"]))
        # Número de ley -> proyecto: la insistencia tras un veto se vota como «INSISTENCIA PROYECTO DE LEY 27.793».
        for r in self._csv("leyes-sancionadas", "hcdn_leyes.csv"):
            if (r.get("LEY") or "").strip().isdigit():
                self.por_ley[int(r["LEY"])] = r["PROYECTO_ID"]
        self._cargado = True
        self.ctx.log(f"   datos abiertos HCDN: {len(self.por_id)} proyectos, {len(self.ods)} órdenes del día, "
                     f"{len(self.por_ley)} leyes")

    def insistencia(self, titulo):
        """Proyecto de una ley vetada sobre la que se vota la insistencia."""
        t = _sin_tildes(titulo).upper()
        m = re.search(r"\bLEY\b[^.\d]{0,40}?\b(2\d)\.?(\d{3})\b", t)
        if not m or not re.search(r"INSISTENCIA|INSISTIR|VETO|OBSERVACION", t):
            return None
        return self.por_id.get(self.por_ley.get(int(m.group(1) + m.group(2))))

    def orden_del_dia(self, numero, fecha):
        """Proyecto principal del orden del día `numero` de la composición de la Cámara de `fecha` (unos pocos
        órdenes del día se reimprimen con otra fecha: vale el publicado antes de la votación)."""
        filas = [f for f in self.ods.get((bienio(fecha), numero), []) if f[1] <= fecha]
        return self.por_id.get(max(filas)[2]) if filas else None

    def por_titulo(self, titulo, anio):
        """Proyecto de Diputados que el Senado votó sin decir su expediente («Ley de Bases.»): el único llegado
        de Diputados ese año o el anterior («CD») cuyo título tiene todas las palabras del título del Senado."""
        palabras = _palabras(titulo)
        if not palabras:
            return None
        if self._cd is None:
            self._cd = {}
            for p in self.por_sen.values():
                if p["sen"].split("-")[1] == "CD" and p["dip"]:
                    self._cd.setdefault(int(p["sen"][-4:]), []).append((_palabras(p["titulo"]), p))
        candidatos = [p for a in (anio, anio - 1) for ps, p in self._cd.get(a, []) if palabras <= ps]
        if len(candidatos) > 1:  # «Ley de Bases» -> el que empieza así («LEY DE BASES Y PUNTOS DE PARTIDA...»)
            inicio = re.sub(r"\W+", " ", _sin_tildes(titulo).upper()).strip()
            candidatos = [p for p in candidatos if re.sub(r"\W+", " ", _sin_tildes(p["titulo"]).upper()).strip().startswith(inicio)]
        return candidatos[0] if len(candidatos) == 1 else None


VACIAS = {"PARA", "SOBRE", "ENTRE", "DESDE", "COMO", "CADA", "ESTE", "ESTA", "LEYES", "NACION", "NACIONAL", "REPUBLICA",
          "ARGENTINA", "PROYECTO", "MODIFICACION", "MODIFICACIONES", "CREACION", "REGIMEN", "DECLARACION"}


def _palabras(t):
    t = re.sub(r"(?<=\d)\.(?=\d)", "", _sin_tildes(t).upper())
    return {w for w in re.findall(r"[A-Z0-9]{4,}", t) if w not in VACIAS}


def _exp_csv(t):
    m = RE_EXP.search(t or "")
    return exp_norm(*m.groups()) if m else None


def clave_proyecto(p):
    """Clave del asunto de un proyecto: su expediente en la cámara de origen."""
    if p["dip"] and p["dip"].split("-")[1] != "S" and p["origen"] != "Senado":
        return f"d:{p['dip']}"
    if p["sen"]:
        return f"s:{p['sen']}"
    return f"d:{p['dip']}"


def clave_exp_diputados(exp, ref):
    """Expediente con numeración de Diputados -> clave del asunto (lo que llega del Senado es «-S-»)."""
    p = ref.por_dip.get(exp)
    if p:
        return clave_proyecto(p), p
    return f"d:{exp}", None


def clave_exp_senado(exp, ref):
    """Expediente con numeración del Senado -> clave del asunto (lo que llega de Diputados es «-CD-»)."""
    p = ref.por_sen.get(exp)
    if p:
        return clave_proyecto(p), p
    return f"s:{exp}", None


# ------------------------------------------------------------------ títulos y tipos

VERBOS_FIRMA = r"(?:CELEBRAD|SUSCRIPT|SUSCRIT|FIRMAD|ADOPTAD|HECH|APROBAD)[OA]S?"
TRATADO = re.compile(r"\b(ACUERDO|CONVENIO|CONVENCION|TRATADO|PROTOCOLO|MEMORANDO|ENMIENDA|ESTATUTO|ENMIENDAS)\b")
APROBACION = re.compile(r"\b(APRUEB|APROBA|APROBAR|RATIFIC|ADHESION|ADHIER)")
MULTILATERAL = re.compile(r"INTERNACIONAL|INTERAMERICAN|NACIONES UNIDAS|MERCOSUR|MERCADO COMUN DEL SUR|ORGANIZACION|"
                          r"UNESCO|\bOEA\b|\bOIT\b|\bFAO\b|MULTILATERAL|UNION EUROPEA|BANCO (MUNDIAL|INTERAMERICANO)|"
                          r"FONPLATA|\bCAF\b|OCDE|ESTADOS PARTE|IBEROAMERICAN|ANTARTICO|ENERGIA ATOMICA|PATENTES")
# Acuerdos que no son tratados: conciliaciones con acreedores, contratos de deuda, convenios con provincias.
NO_TRATADO = re.compile(r"CONCILIACION|ACREEDOR|TENEDORES|HOLDOUT|TITULOS DE DEUDA|BONOS|PROVINCIAS? DE\b|PROVINCIAS\b|"
                        r"MUNICIPIO|CONVENIO COLECTIVO|PACTO FISCAL|CONSENSO FISCAL|CIUDAD AUTONOMA|CIUDAD DE BUENOS AIRES|"
                        r"GOBIERNO DE LA CIUDAD")
# Nombramientos: en el Senado, «acuerdos» (pliegos) para designar jueces, embajadores y ascensos militares.
NOMBRAMIENTO = re.compile(
    r"^\s*(ACUERDOS?\b(?!\s+(DE\s+|DEL\s+)?(CONCILIACI|LIBRE|COMERCIO|MARCO|COOPERACI|ENTRE|CON\b|SOBRE|INTERINO|ASOCIACI|"
    r"MUTUO|RECIPROC))|PLIEGOS?\b|DESIGNACION(ES)? DE\s+(?!LA CIUDAD|LA LOCALIDAD|LA PROVINCIA)|RATIFICACION DE SECRETARI|"
    r"ELECCION DE|PRORROGA .{0,40}MANDATO|NOMBRAMIENTOS?\b|DEFENSORA? DE LOS DERECHOS)|DEFENSORA? DEL PUEBLO|"
    r"AUDITOR(ES|IA)? GENERAL|PRESIDENTE PROVISIONAL|"
    r"VICEPRESIDENCIA|PROSECRETARI|SECRETARIO PARLAMENTARIO|SECRETARIO ADMINISTRATIVO|AUTORIDADES DE LA (H\. )?CAMARA")


def quitar_firma(titulo):
    """Quita el lugar y la fecha de la firma de un tratado («..., CELEBRADO EN RÍO DE JANEIRO, REPÚBLICA
    FEDERATIVA DEL BRASIL, EL 7 DE DICIEMBRE DE 2023»): las reglas leerían Brasil como parte."""
    t = _sin_tildes(titulo).upper()
    m = re.search(r",?\s+" + VERBOS_FIRMA + r"\s+(?:EN|POR)\s+", t)
    if m and TRATADO.search(t[:m.start()]):
        return titulo[:m.start()].rstrip(" ,;.") + "."
    return titulo


def es_tratado(titulo, desde_ejecutivo=False):
    """Aprobación de un tratado o convenio internacional (en Argentina se aprueban por ley, a propuesta del
    Poder Ejecutivo): «APRUÉBASE EL CONVENIO ENTRE LA REPÚBLICA ARGENTINA Y ...»."""
    t = _sin_tildes(titulo).upper()
    if not TRATADO.search(t) or NO_TRATADO.search(t):
        return False
    if not (APROBACION.search(t) or re.match(r"\s*(ACUERDO|CONVENIO|CONVENCION|TRATADO|PROTOCOLO|ENMIENDA)", t)):
        return False
    extranjero = paises.detectar(titulo, "es", excluir={"ARG"}) or MULTILATERAL.search(t)
    return bool(extranjero) or desde_ejecutivo


PROCEDIMIENTO = re.compile(r"\b(APARTAMIENTO|MOCI[OÓ]N|HABILITACI[OÓ]N|RECONSIDERACI[OÓ]N|EMPLAZAMIENTO|PREFERENCIA|"
                           r"VUELTA A COMISI[OÓ]N|RETORNO A COMISI[OÓ]N|DESARROLLO DE LA SESI[OÓ]N|CUARTO INTERMEDIO|"
                           r"CUESTI[OÓ]N DE PRIVILEGIO|SOBRE TABLAS|PLAN DE LABOR|ALTERACI[OÓ]N DEL ORDEN|"
                           r"CIERRE DE (LA )?LISTA|CIERRE DEL DEBATE|LEVANTAMIENTO DE LA SESI[OÓ]N|CONSTITUCI[OÓ]N EN COMISI[OÓ]N|"
                           r"AUTORIZACI[OÓ]N PARA (ABSTENERSE|INSERTAR)|INSERCIONES|ABSTENCI[OÓ]N DE|ACTA DE LABOR|"
                           r"PEDIDO DE TRATAMIENTO|RETIRO DE (PLIEGOS|EXPEDIENTES|PROYECTOS)|RETIRO DE LOS)\b|^\s*TRATAMIENTO\b", re.I)


def tipo_asunto(titulo, tipo_proyecto=None, exp_tipo=None, clase_senado=None):
    t = _sin_tildes(titulo).upper()
    if clase_senado == "AC" or (not tipo_proyecto and NOMBRAMIENTO.search(t)):
        return "nombramiento"
    desde_ejecutivo = exp_tipo in ("PE", "JGM") or "MENSAJE" in (tipo_proyecto or "")
    if es_tratado(titulo, desde_ejecutivo):
        return "tratado"
    if (re.match(r"\s*DECRETOS?\b", t) or re.search(r"FACULTADES DELEGADAS|NECESIDAD Y URGENCIA", t)) and "OBSERVA" not in t:
        return "resolucion"  # el Congreso aprueba o rechaza un decreto del Ejecutivo (ley 26.122)
    tp = tipo_proyecto or ""
    if "LEY" in tp or tp == "MENSAJE" or clase_senado == "PL":
        return "ley"
    if tp in ("RESOLUCION", "DECLARACION") or clase_senado in ("PR", "PD", "PC"):
        return "resolucion"
    if re.search(r"DECRETOS? DE NECESIDAD|\bDNUS?\b|DECRETOS? (N|DEL PODER)", t):
        return "resolucion"
    if re.search(r"PEDIDO DE INFORMES|DE INTERES|BENEPLACITO|REPUDIO|^DECLARACION\b|DECLARACION DE INTERES|RESOLUCION|"
                 r"COMISION INVESTIGADORA|BICAMERAL|HOMENAJE|^RECONOCIMIENTO|^EXPRESAR|^SOLICITAR", t):
        return "resolucion"
    if re.search(r"\bLEY\b|CODIGO|PRESUPUESTO|REGIMEN|CREACION|MODIFICACION|DECLARASE|DECLARESE|INSTITUYESE|PRORROGA|"
                 r"EMERGENCIA|TRANSFIERESE|CAPITAL NACIONAL|MONUMENTO|UNIVERSIDAD|MARCO REGULATORIO|TRASPASO|REFORMA|"
                 r"INSTITUCION DE|DIA NACIONAL|FIESTA NACIONAL|HEROE NACIONAL|PARQUE NACIONAL|CREASE|TRANSFERENCIA|DONACION|"
                 r"EXPROPIACION|AUSENTARSE DEL PAIS|TROPAS|FUERZAS NACIONALES|JUBILACION|PENSION", t):
        return "ley"
    return "otro"


def titulo_proyecto(p):
    t = re.sub(r"^(PROYECTO DE )?(LEY|RESOLUCION|DECLARACION)\.\s+", "", p["titulo"])
    return quitar_firma(t)[:400]


def url_asunto(clave, clase=None):
    camara, exp = clave.split(":", 1)
    if not RE_EXP.fullmatch(exp):
        return None
    if camara == "d":
        return HCDN_FICHA + exp
    if clase:
        n, t, a = exp.split("-")
        return f"{SENADO}/parlamentario/comisiones/verExp/{int(n)}.{a[2:]}/{t}/{clase}"
    return None


# ------------------------------------------------------------------ Diputados

def tipo_votacion_diputados(titulo, tipo_a):
    t = _sin_tildes(titulo).upper()
    if tipo_a == "procedimiento" or PROCEDIMIENTO.search(t):
        return "procedimiento"
    if re.search(r"INSISTIR|INSISTENCIA|ACEPTACION DE (LAS )?MODIFICACIONES|ACEPTAR (LAS )?MODIFICACIONES", t):
        return "final"
    if re.search(r"GRAL\.?\s*(Y|E)\s*(EN\s+)?PART|GENERAL\s+Y\s+(EN\s+)?PARTICULAR|EN G\.\s*Y\s*P\.|VOT(\.|ACION)?\s*(EN\s+)?(GRAL|GENERAL)\b"
                 r"|EN GENERAL\b", t):
        return "final"
    if re.search(r"PROPUEST[OA] POR|PROPUESTA DE(L)? (LA )?DIP", t):
        return "enmienda"
    # La parte que se vota va tras un punto o un guion («... 2023. ART. 67.», «... - Artículo 14») o cierra el título
    # («... DEUDA PÚBLICA art. 1»); «Modificación del artículo 44 de la ley...» es el nombre del proyecto.
    if re.search(r"(^|[.\-–,;:(]\s*)(ART(ICULO|S)?\b\.?\s*(\d|NUEVO|[IVX]+\b)|TITULO\s+[IVXLC\d]|CAP(ITULO|\.)?\s*[IVXLC\d]|"
                 r"INCISO|EN PARTICULAR|ANEXO|(INCORPORACION (DE )?)?NUEVO (ARTICULO|CAPITULO|TITULO|INCISO))", t) or re.search(
                 r"\bART(ICULO|S)?\.?\s*\d+\s*[°º]?(\s*(Y|AL|A)\s*\d+)?\s*(\([^)]*\))?\s*\.?\s*$", t):
        return "parcial"
    if tipo_a == "nombramiento":
        return "nombramiento"
    return "final"


def limpiar_titulo_acta(titulo):
    """«O.D. 6 - LEY DE MODERNIZACIÓN LABORAL. DICT. DE MAY. TÍTULO III.» -> «LEY DE MODERNIZACIÓN LABORAL»."""
    t = _limpio(titulo)
    anterior = None
    while t != anterior:
        anterior = t
        t = re.sub(r"^(Pedido de )?Expedientes?\s+[\d\w\s,.\-/]*?(?:y otros)?\s*(?:[-.:]\s+|(?=O\.?\s?D))", "", t, flags=re.I)
        t = re.sub(r"^EXPTES?\.?\s*[\d\w\s,.\-/]*?\d{2,4}\s*[-.:]?\s+", "", t, flags=re.I)
        t = re.sub(r"^Exp\.\s*\d{1,5}\s*-\s*\w+\s*\.?-\s*\d{2,4}\.?\s*[-.:]?\s*", "", t, flags=re.I)
        t = re.sub(r"^\d{1,5}-[A-Z]+-\d{2,4}\s+", "", t)
        t = re.sub(r"^(O\.?\s?D\.?\s*[:.]?\s*[\d,\sy]+\s*[-.:]?\s*)+", "", t, flags=re.I)
        t = re.sub(r"^(De Ley|Proyecto de ley|Varios proyectos de Ley)\.\s*", "", t, flags=re.I)
        t = re.sub(r"^VOT(ACI[OÓ]N|\.)?\s+(EN\s+)?(GRAL|GENERAL)\.?\s+(Y|E)\s+(EN\s+)?PART(ICULAR|\.)?\s*[-.:]?\s*", "", t, flags=re.I)
    # Lo que se vota va detrás de un punto o un guion («... LABORAL. DICT. DE MAY. TÍTULO III.», «... - Artículo 5»);
    # «se modifica el capítulo XIII del Régimen...» es parte del nombre.
    corte = re.search(r"[.\-–,;:(]\s*(\bVOT(ACI[OÓ]N|\.)?\s*(EN\s+)?(GRAL|GENERAL|G\.)|\bVOTACI[OÓ]N\s+(ART|EN\s+PART)|"
                      r"\bDICT(AMEN|\.)?\s+DE\s+(MAY|MIN)|\b(NUEVO\s+)?ART(ICULO|ÍCULO|S)?\b\.?\s*(\d|NUEVO|[IVX]+\b)|"
                      r"\bT[IÍ]TULO\s+[IVXLC\d]|\bCAP(ITULO|ÍTULO|\.)?\s+[IVXLC\d]|\bINCISO|"
                      r"\bEN (GENERAL|PARTICULAR)|\bAPROBACI[OÓ]N\.?\s*$)", t, flags=re.I)
    if corte and corte.start() > 8:
        t = t[:corte.start()]
    t = re.sub(r"\s+ART(ICULO|ÍCULO|S)?\.?\s*\d+\s*[°º]?(\s*(Y|AL|A)\s*\d+)?\s*(\([^)]*\))?\s*\.?\s*$", "", t, flags=re.I)
    t = re.sub(r"\s*[-(]?\s*(Exp(te)?s?\.?\s*)?\d{1,5}\s*-\s*[A-Z]+\s*\.?-\s*\d{2,4}\s*\)?\.?$", "", t, flags=re.I)
    t = re.sub(r"[-.\s]*(O\.?\s?D\.?\s*[:.]?\s*[\d,\sy]+)\.?$", "", t, flags=re.I)
    return t.strip(" .-–:;,") or None


def _fecha_cv(d):
    s = (d or "").strip()
    return f"{s[6:10]}-{s[3:5]}-{s[0:2]}", re.sub(r"\D", "", s[10:])[:4]


def _miembro_diputado(nombre, foto):
    return f"arg:d:{foto}" if foto else "arg:d:" + re.sub(r"[^a-z0-9]+", "-", _sin_tildes(nombre).lower()).strip("-")


def _nombre_persona(t):
    """«MENEM, MARTIN» -> «Martin Menem» (las actas escriben en mayúsculas o en mayúsculas y minúsculas)."""
    t = _limpio(t)
    if "," in t:
        apellido, nombre = [x.strip() for x in t.split(",", 1)]
        t = f"{nombre} {apellido}".strip()
    if t.isupper() or t.islower():
        t = t.title()
    return re.sub(r"\b(De|Del|La|Las|Los|Y)\b", lambda m: m.group(1).lower(), t)


def _referencias_acta(titulo):
    ods = []
    for m in RE_OD.finditer(titulo):
        ods += [int(x) for x in re.findall(r"\d+", m.group(1))]
    exps = [(m.start(), exp_norm(*m.groups())) for m in RE_EXP.finditer(titulo)]
    exps += [(m.start(), exp_norm(m.group(2), m.group(1), m.group(3))) for m in RE_EXP_INV.finditer(titulo)]
    return list(dict.fromkeys(ods)), list(dict.fromkeys(e for _, e in sorted(exps)))


def asuntos_diputados(actas, ref):
    """Asigna a cada acta su asunto: {id de acta: (clave, título, tipo, código, url, autor, extra)}."""
    salida, previa = {}, None
    for a in actas:
        titulo, fecha = a["titulo"], a["fecha"]
        ods, exps = _referencias_acta(titulo)
        proyecto, extra = None, {}
        mayus = _sin_tildes(titulo).upper()
        if len(ods) > 1:
            clave = f"d:od{'+'.join(str(n) for n in sorted(ods))}-{bienio(fecha)}"
            titulos, tipos = [], []
            for n in sorted(ods):
                p = ref.orden_del_dia(n, fecha)
                if p:
                    titulos.append(titulo_proyecto(p).rstrip("."))
                    tipos.append(tipo_asunto(titulos[-1], p["tipo"], p["dip"].split("-")[1] if p["dip"] else None))
            extra["od"] = [f"{n}/{fecha[:4]}" for n in sorted(ods)]
            nombre = ("Varios órdenes del día: " + "; ".join(titulos)) if titulos else (limpiar_titulo_acta(titulo) or titulo)
            # Tipo del conjunto: tratado si alguno lo es (las reglas leen los países del título), si no el común.
            tipo_a = "tratado" if "tratado" in tipos else (tipos[0] if tipos and len(set(tipos)) == 1 else "otro")
            info = (clave, nombre[:400], tipo_a, "O.D. " + ", ".join(str(n) for n in sorted(ods)), None, None, extra)
        else:
            if ods:
                proyecto = ref.orden_del_dia(ods[0], fecha)
                extra["od"] = f"{ods[0]}/{fecha[:4]}"
            if proyecto:
                clave = clave_proyecto(proyecto)
            elif exps:
                clave, proyecto = clave_exp_diputados(exps[0], ref)
            elif ods:
                clave = f"d:od{ods[0]}-{bienio(fecha)}"
            elif ref.insistencia(titulo):
                proyecto = ref.insistencia(titulo)
                clave = clave_proyecto(proyecto)
            elif PROCEDIMIENTO.search(mayus) or not limpiar_titulo_acta(titulo):
                clave = f"d:{fecha}:proc"
            elif previa and previa[0] == fecha and re.match(
                    r"\s*(INCORPORACION (DE )?(UN )?|NUEVO\s+)?(NUEVO\s+)?(ART|TITULO|CAP|INCISO|VOTACION EN PARTICULAR|DICTAMEN)", mayus):
                salida[a["id"]] = salida[previa[1]]  # «NUEVO ARTÍCULO PROPUESTO POR...»: la ley que se votaba
                previa = (fecha, a["id"])
                continue
            else:
                nombre = _sin_tildes(limpiar_titulo_acta(titulo)).lower()
                clave = f"d:t{fecha[:4]}-{hashlib.sha1(nombre.encode()).hexdigest()[:10]}"
            if clave.endswith(":proc"):
                info = (clave, f"Votaciones de procedimiento, sesión del {fecha[8:10]}/{fecha[5:7]}/{fecha[:4]}",
                        "procedimiento", None, None, None, None)
            else:
                if proyecto:
                    nombre = titulo_proyecto(proyecto)
                    tipo_a = tipo_asunto(nombre, proyecto["tipo"], clave.split("-")[1] if RE_EXP.search(clave) else None)
                    extra.update({k: v for k, v in (("diputados", proyecto["dip"]),
                                                    ("senado", exp_senado_legible(proyecto["sen"]) if proyecto["sen"] else None)) if v})
                else:
                    nombre = quitar_firma(limpiar_titulo_acta(titulo) or titulo)
                    exp_tipo = clave.split("-")[1] if RE_EXP.search(clave) else None
                    tipo_a = tipo_asunto(nombre, None, exp_tipo)
                exp = clave.split(":", 1)[1]
                if clave.startswith("s:"):
                    codigo = exp_senado_legible(exp) if RE_EXP.fullmatch(exp) else None
                    clase = {"RESOLUCION": "PR", "DECLARACION": "PD"}.get(proyecto["tipo"], "PL") if proyecto else None
                    url = url_asunto(clave, clase) or (HCDN_FICHA + proyecto["dip"] if proyecto and proyecto["dip"] else None)
                else:
                    codigo = exp if RE_EXP.fullmatch(exp) else ("O.D. " + extra["od"] if "od" in extra else None)
                    url = url_asunto(clave)
                info = (clave, nombre[:400], tipo_a, codigo, url, proyecto["autor"] if proyecto else None, extra or None)
        salida[a["id"]] = info
        previa = (fecha, a["id"])
    return salida


def _ultima(ctx, camara):
    r = ctx.con.execute("SELECT MAX(fecha) FROM votacion WHERE fuente=? AND camara=?", (FUENTE.codigo, camara)).fetchone()
    return r[0] if r else None


def _inicio(ctx, camara):
    inicio = f"{ctx.desde}-01-01"
    ultima = _ultima(ctx, camara)
    if ultima and not ctx.completo:
        inicio = max(inicio, (date.fromisoformat(ultima) - timedelta(days=MARGEN_DIAS)).isoformat())
    return inicio


def _registrar_partido(ctx, nombre_fuente):
    codigo = codigo_bloque(nombre_fuente)
    if codigo not in FUENTE.partidos:
        nombre = _limpio(nombre_fuente)
        nombre = nombre.title() if nombre.isupper() else (nombre or "Sin bloque")
        ctx.partido(codigo, nombre, siglas_de(nombre), color_bloque(codigo))
    return codigo


def _guardar(ctx, asuntos, votaciones):
    for i in range(0, len(votaciones), LOTE):
        lote = votaciones[i:i + LOTE]
        ctx.guardar([asuntos[a][0] for a in dict.fromkeys(v.asunto_id for v in lote)], lote)


def _anotar(asuntos, aid, info, fecha, procedimiento):
    """Registra el asunto de una votación. El título y el tipo los pone la primera votación que no sea de
    procedimiento («Moción de preferencia para el proyecto S-1287/25» no es el nombre del proyecto)."""
    clave, nombre, tipo_a, codigo, url_a, autor, extra = info
    previo = asuntos.get(aid)
    if previo and (procedimiento or not previo[1]):
        previo[0].fecha = min(previo[0].fecha, fecha)
        return
    asuntos[aid] = (Asunto(id=aid, titulo=nombre, tipo=tipo_a, fecha=min(fecha, previo[0].fecha) if previo else fecha,
                           codigo=codigo, autor=autor, url=url_a, extra=extra), procedimiento)


def recoger_diputados(ctx, ref):
    inicio = _inicio(ctx, "arg-d")
    ruta = ctx.cache(COMO_VOTO, "como_voto_diputados.json", caduca_horas=6, timeout=300)
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    nombres, bloques, fotos = datos["names"], datos["blocs"], datos.get("photo_ids") or {}
    actas = []
    for v in datos["votaciones"]:
        fecha, hora = _fecha_cv(v.get("d"))
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", fecha) or fecha < f"{ctx.desde}-01-01":
            continue
        actas.append({"id": int(v["id"]), "fecha": fecha, "hora": hora, "titulo": _limpio(v.get("t")), "r": v.get("r") or "",
                      "votos": v.get("v") or [], "slug": v.get("sl")})
    actas.sort(key=lambda a: (a["fecha"], a["hora"], a["id"]))
    nuevas = [a for a in actas if a["fecha"] >= inicio]
    ctx.log(f"   Diputados: {len(nuevas)} actas desde {inicio} (de {len(actas)} desde {ctx.desde})")
    if not nuevas:
        return
    ref.cargar()
    info = asuntos_diputados(actas, ref)
    asuntos, votaciones = {}, []
    for a in nuevas:
        clave, tipo_a = info[a["id"]][0], info[a["id"]][2]
        aid = f"arg:{clave}"
        tipo_v = tipo_votacion_diputados(a["titulo"], tipo_a)
        _anotar(asuntos, aid, info[a["id"]], a["fecha"], tipo_v == "procedimiento")
        votos, vistos = [], set()
        for fila in a["votos"]:
            i_nombre, i_bloque, _prov, cod = fila[:4]
            nombre = nombres[i_nombre] if i_nombre < len(nombres) else ""
            if not nombre.strip(" ,") or "A DESIGNAR" in nombre.upper():
                continue  # banca vacante
            mid = _miembro_diputado(nombre, fotos.get(str(i_nombre)))
            if mid in vistos:
                continue
            vistos.add(mid)
            partido = _registrar_partido(ctx, bloques[i_bloque] if i_bloque < len(bloques) else "")
            votos.append((mid, _nombre_persona(nombre), partido, SENTIDO_CV.get(cod, "no_vota")))
        n = {s: sum(1 for *_, x in votos if x == s) for s in ("si", "no", "abstencion", "no_vota")}
        r = a["r"].upper()
        resultado = "aprobada" if r.startswith("AFIRM") else "rechazada" if r.startswith("NEG") else (
            "aprobada" if n["si"] > n["no"] else "rechazada")
        votaciones.append(Votacion(
            id=f"arg:d:{a['id']}", fecha=a["fecha"], asunto_id=aid, camara="arg-d", numero=a["id"], texto=a["titulo"][:600] or None,
            tipo=tipo_v, a_favor=n["si"], en_contra=n["no"],
            abstenciones=n["abstencion"], no_votan=n["no_vota"], resultado=resultado,
            url=HCDN_VOTACION + (f"{a['slug']}/{a['id']}" if a.get("slug") else str(a["id"])), votos=votos))
    _guardar(ctx, asuntos, votaciones)
    ctx.log(f"   Diputados: {len(votaciones)} votaciones, {len(asuntos)} asuntos")


# ------------------------------------------------------------------ Senado

# «PE-13/26-PL», «S-1563/26» en el texto (numeración del Senado).
RE_EXP_SENADO = re.compile(r"\b(S|PE|CD|JGM|OV|P)\s*-\s*(\d{1,5})\s*/\s*(\d{2}|\d{4})(?:\s*-\s*([A-Z]{2})\b)?")


def _exps_enlaces(html_):
    exps = []
    for n, a, t, c in re.findall(r"verExp/(\d+)\.(\d+)/([A-Z]+)/([A-Z]+)", html_):
        e = (exp_norm(n, t, a), c)
        if e not in exps:
            exps.append(e)
    return exps


def actas_senado(pagina):
    """Filas de la lista de actas de un año del Senado."""
    i = pagina.find("<tbody")
    cuerpo = pagina[i:pagina.find("</tbody>", i)] if i >= 0 else ""
    salida = []
    for fila in re.findall(r"<tr>(.*?)</tr>", cuerpo, re.S):
        tds = re.findall(r"<td[^>]*>(.*?)</td>", fila, re.S)
        det = re.search(r"/votaciones/detalleActa/(\d+)", fila)
        f = re.search(r"(\d{2})/(\d{2})/(\d{4})", tds[0] if tds else "")
        if len(tds) < 7 or not det or not f:
            continue
        celda = tds[2]
        titulo = _texto_html(re.split(r"<a onclick=\"mostrar|<div id=\"mostrarOcultarDiv", celda)[0]).rstrip(" (")
        exps = _exps_enlaces(celda) or [(exp_norm(n, t, a), c or None) for t, n, a, c in RE_EXP_SENADO.findall(titulo)]
        od = re.search(r"ordenDelDiaResultadoLink/(\d{4})/(\d+)", celda)
        partes = re.findall(r"\bArts?\.\s*\d+\s*[°º]?(?:\s*(?:a|al|y)\s*\d+\s*[°º]?)?", _texto_html(celda))
        acta = re.sub(r"\D", "", _texto_html(tds[1]))
        salida.append({
            "id": int(det.group(1)), "fecha": f"{f.group(3)}-{f.group(2)}-{f.group(1)}", "acta": int(acta) if acta else None,
            "titulo": titulo, "exps": exps, "od": (int(od.group(2)), int(od.group(1))) if od else None, "partes": partes,
            "tipo": _texto_html(tds[3]).upper(),
            "resultado": _texto_html(re.sub(r"<span[^>]*display:\s*none[^>]*>.*?</span>", "", tds[4])).upper(),
            "mayoria": _texto_html(tds[6]).upper() or None})
    return salida


def votos_senado(pagina):
    """Votos y totales del detalle de un acta del Senado."""
    i = pagina.find('id="tabla"')
    cuerpo = pagina[i:pagina.find("</table>", i)] if i >= 0 else ""
    votos = []
    for fila in re.findall(r"<tr>(.*?)</tr>", cuerpo, re.S):
        tds = re.findall(r"<td[^>]*>(.*?)</td>", fila, re.S)
        if len(tds) < 5:
            continue
        sid = re.search(r"/senadores/senador/(\d+)", tds[0])
        votos.append((sid.group(1) if sid else None, _texto_html(tds[1]), _texto_html(tds[2]), _texto_html(tds[4]).upper()))
    totales = {}
    for n, rotulo in re.findall(r"<h3[^>]*>\s*(\d+)\s*</h3>\s*<h4[^>]*>\s*([A-ZÁÉÍÓÚ ]+?)\s*</h4>", pagina):
        totales[_sin_tildes(rotulo).upper()] = int(n)
    return votos, totales


def tipo_votacion_senado(fila, tipo_a):
    t = fila["tipo"]
    titulo = _sin_tildes(fila["titulo"]).upper()
    if tipo_a == "procedimiento" or PROCEDIMIENTO.search(titulo):
        return "procedimiento"
    if tipo_a == "nombramiento":
        return "nombramiento"
    if "GENERAL" in t:
        return "final"
    if "PARTICULAR" in t:
        return "parcial"
    return "final"  # «OTRA»: una declaración o una insistencia que se vota una sola vez


def limpiar_titulo_senado(titulo):
    """«Modificación de la Carta Orgánica del Banco Central. Artículo 18.» -> sin la parte que se vota."""
    t = re.sub(r"^\s*(Proyectos? Varios|Varios Proyectos)\s*:\s*", "", titulo, flags=re.I)
    t = re.sub(r"\.\s+(Art[ií]culos?|Arts?\.|T[ií]tulos?|Cap[ií]tulos?|Incisos?|Anexos?|Primera parte|Segunda parte)\b.*$", "",
               t, flags=re.I)
    t = re.sub(r"\(\s*\)", "", t)
    return t.strip(" .,;(") or titulo


def asunto_senado(fila, ref):
    """(clave, título, tipo, código, url, autor, extra) del asunto de un acta del Senado."""
    titulo = limpiar_titulo_senado(fila["titulo"])
    mayus = _sin_tildes(fila["titulo"]).upper()
    exps = fila["exps"]
    distintos = list(dict.fromkeys(e for e, _ in exps))
    # Varios proyectos votados juntos («Proyectos varios: ...», o varios tratados en una sola votación, cada
    # uno una frase del título); si son varios expedientes de un mismo dictamen, es una sola ley.
    # Varios proyectos votados juntos: si se conocen sus expedientes, la votación va al principal (el que viene de
    # Diputados, o el primero); partirla repetiría votos y un asunto «varios» contaría dos veces cada tratado.
    # Sin expedientes, una votación de varios asuntos (una frase cada uno) es un asunto «varios».
    frases = [x for x in re.split(r"\.\s+(?=[A-ZÁÉÍÓÚÑ])", titulo) if len(x) > 12 and not re.match(
        r"(Dictamen|Insistencia|Aceptaci|Modificaciones|Votaci|En general|En particular|Rechazo|Veto|Observaci|Sanci|Texto|"
        r"Reproducci|Con modificaci|Media sanci|Vuelta|Segunda revisi|Moci)", x, re.I)]
    varios = bool((re.search(r"\bVARIOS\b", mayus) and len(distintos) > 1) or (
        not distintos and len(frases) >= 2 and "GENERAL" in fila["tipo"]))
    proyecto, clase, extra = None, None, {}
    if fila["od"]:
        extra["od"] = f"{fila['od'][0]}/{fila['od'][1]}"
    vetada = ref.insistencia(fila["titulo"])  # la insistencia tras un veto va con la ley, no con el mensaje del veto
    if vetada and vetada["sen"]:
        exps = [(vetada["sen"], "PL")]
    elif not exps and not varios and not PROCEDIMIENTO.search(mayus) and not NOMBRAMIENTO.search(mayus):
        proyecto = ref.por_titulo(titulo, int(fila["fecha"][:4]))
        if proyecto and proyecto["sen"]:
            exps = [(proyecto["sen"], "PL")]
    if exps and not varios:
        # Si trata a la vez un proyecto que viene de Diputados y otros del Senado, manda el de Diputados.
        exp, clase = next((e for e in exps if e[0].split("-")[1] == "CD"), exps[0])
        clave, proyecto = clave_exp_senado(exp, ref)
        extra["senado"] = exp_senado_legible(exp)
    elif varios:
        base = "+".join(sorted(distintos)) if len(distintos) > 1 else _sin_tildes(titulo).lower()
        clave = f"s:varios-{hashlib.sha1(base.encode()).hexdigest()[:10]}"
        if distintos:
            extra["senado"] = [exp_senado_legible(e) for e in distintos]
    elif fila["od"]:
        clave = f"s:od{fila['od'][0]}-{fila['od'][1]}"
    elif PROCEDIMIENTO.search(mayus) and not NOMBRAMIENTO.search(mayus):
        clave = f"s:{fila['fecha']}:proc"
    else:
        clave = f"s:t{fila['fecha'][:4]}-{hashlib.sha1(_sin_tildes(titulo).lower().encode()).hexdigest()[:10]}"
    if clave.endswith(":proc"):
        f = fila["fecha"]
        return (clave, f"Votaciones de procedimiento, sesión del {f[8:10]}/{f[5:7]}/{f[:4]}", "procedimiento", None, None, None, None)
    if proyecto:
        nombre = titulo_proyecto(proyecto)
        if proyecto["dip"]:
            extra["diputados"] = proyecto["dip"]
    else:
        nombre = quitar_firma(titulo)
    exp_c = clave.split(":", 1)[1]
    exp_tipo = exp_c.split("-")[1] if RE_EXP.fullmatch(exp_c) else None
    tipo_a = tipo_asunto(nombre, proyecto["tipo"] if proyecto else None, exp_tipo, clase)
    if clave.startswith("d:"):
        codigo, url = exp_c, url_asunto(clave)
    else:
        codigo = exp_senado_legible(exp_c) if exp_tipo else ("O.D. " + extra["od"] if "od" in extra else None)
        url = url_asunto(clave, clase)
    return (clave, nombre[:400], tipo_a, codigo, url, proyecto["autor"] if proyecto else None, extra or None)


def _detalle(ctx, fila, reciente):
    url = f"{SENADO}/votaciones/detalleActa/{fila['id']}"
    try:
        if reciente:
            return ctx.fetch(url).decode("utf-8", "replace")
        return ctx.cache(url, f"senado_acta_{fila['id']}.html").read_text(encoding="utf-8", errors="replace")
    except Exception as e:  # un acta que no carga no para el año
        ctx.log(f"   ! acta del Senado {fila['id']}: {type(e).__name__}: {e}")
        return None


def _orden_del_dia_senado(ctx, od):
    """Expedientes de un orden del día del Senado (la lista de actas no siempre los trae)."""
    numero, anio = od
    url = f"{SENADO}/parlamentario/parlamentaria/ordenDelDiaResultadoLink/{anio}/{numero}"
    try:
        return _exps_enlaces(ctx.cache(url, f"senado_od_{anio}_{numero}.html").read_text(encoding="utf-8", errors="replace"))
    except Exception as e:
        ctx.log(f"   ! orden del día del Senado {numero}/{anio}: {type(e).__name__}: {e}")
        return []


def _extracto_senado(ctx, exp, clase):
    """Extracto de un expediente del Senado, para las actas que la lista trae sin título."""
    n, t, a = exp.split("-")
    url = f"{SENADO}/parlamentario/comisiones/verExp/{int(n)}.{a[2:]}/{t}/{clase or 'PL'}"
    try:
        pagina = ctx.cache(url, f"senado_exp_{t}_{int(n)}_{a}.html").read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        ctx.log(f"   ! expediente del Senado {exp}: {type(e).__name__}: {e}")
        return ""
    m = re.search(r'summary="N\S*mero de Expediente[^"]*"\s*>.*?<tbody>(.*?)</tbody>', pagina, re.S)
    celdas = [_texto_html(x) for x in re.split(r"<td[^>]*>", m.group(1))[1:]] if m else []
    extracto = celdas[3] if len(celdas) >= 4 else ""
    return re.sub(r"^MENSAJE N\S*\s*[\d/]+\s*(Y PROYECTO DE (LEY|RESOLUCION)\s*)?((QUE|POR EL QUE|POR EL CUAL)\s+)?", "", extracto)


class Senadores:
    """Id de los senadores que ya no lo son (su fila del acta no enlaza su ficha), por su nombre, con el listado
    histórico de datos abiertos del Senado."""

    def __init__(self, ctx):
        self.ctx, self._ids = ctx, None

    def id(self, nombre, fecha):
        if self._ids is None:
            self._ids = {}
            try:
                ruta = self.ctx.cache(f"{SENADO}/micrositios/DatosAbiertos/ExportarListadoSenadoresHistorico/json",
                                      "senadores_historico.json", caduca_horas=24 * 7)
                filas = json.loads(re.sub(r"[\x00-\x1f]", " ", ruta.read_text(encoding="utf-8", errors="replace")))["table"]["rows"]
            except Exception as e:
                self.ctx.log(f"   ! listado histórico de senadores: {type(e).__name__}: {e}")
                filas = []
            for r in filas:
                self._ids.setdefault(_nombre_clave(r.get("SENADOR")), []).append(
                    (r.get("ID"), (r.get("INICIO PERIODO REAL") or "")[:10], (r.get("CESE PERIODO REAL") or "")[:10]))
        opciones = self._ids.get(_nombre_clave(nombre), [])
        ids = {i for i, _, _ in opciones}
        if len(ids) > 1:
            ids = {i for i, ini, fin in opciones if ini <= fecha and (not re.match(r"\d{4}", fin) or fecha <= fin)} or ids
        return next(iter(ids)) if len(ids) == 1 else None


def _nombre_clave(t):
    return re.sub(r"\s+", " ", _sin_tildes(t or "").upper().replace(" ,", ",")).strip()


def asuntos_senado(filas, ref):
    """Asunto de cada acta. Si varias actas de la misma sesión tienen el mismo título y casi todas el mismo
    asunto, las que no lo tienen se unen a él (la lista a veces trae el expediente mal o no lo trae)."""
    info = {f["id"]: asunto_senado(f, ref) for f in filas}
    # Una votación en particular sin expediente cuyo título empieza como el de otra de la sesión («Medidas Fiscales
    # Paliativas y Relevantes. Otras Medidas Fiscales. Artículo 112.») es de esa ley.
    for f in filas:
        clave = info[f["id"]][0]
        if "PARTICULAR" in f["tipo"] and re.match(r"s:(t\d|od|varios)", clave):
            propio = _sin_tildes(limpiar_titulo_senado(f["titulo"])).lower()
            for g in filas:
                otro = _sin_tildes(limpiar_titulo_senado(g["titulo"])).lower()
                if (g["fecha"] == f["fecha"] and g["id"] != f["id"] and len(otro) >= 10 and propio.startswith(otro)
                        and propio != otro and not info[g["id"]][0].endswith(":proc")):
                    info[f["id"]] = info[g["id"]]
                    break
    grupos = {}
    for f in filas:
        if not info[f["id"]][0].endswith(":proc"):
            grupos.setdefault((f["fecha"], _sin_tildes(limpiar_titulo_senado(f["titulo"])).lower()), []).append(f["id"])
    for ids in grupos.values():
        cuenta = {}
        for i in ids:
            cuenta[info[i][0]] = cuenta.get(info[i][0], 0) + 1
        mayor = max(cuenta, key=cuenta.get)
        if cuenta[mayor] >= 2:
            modelo = next(info[i] for i in ids if info[i][0] == mayor)
            for i in ids:
                if cuenta[info[i][0]] == 1:
                    info[i] = modelo
    return info


def recoger_senado(ctx, ref):
    inicio = _inicio(ctx, "arg-s")
    hace_un_mes = (date.today() - timedelta(days=30)).isoformat()
    senadores = Senadores(ctx)
    for anio in range(int(inicio[:4]), date.today().year + 1):
        filas = actas_senado(ctx.fetch(f"{SENADO}/votaciones/actas", timeout=120, formulario={
            "busqueda_actas[anio]": str(anio), "busqueda_actas[titulo]": ""}).decode("utf-8", "replace"))
        filas = sorted((f for f in filas if f["fecha"] >= inicio and f["fecha"][:4] == str(anio)),
                       key=lambda f: (f["fecha"], f["acta"] or 0, f["id"]))
        if not filas:
            continue
        ref.cargar()
        faltan = sorted({f["od"] for f in filas if f["od"] and not f["exps"]})
        with ThreadPoolExecutor(6) as ex:
            exps_od = dict(zip(faltan, ex.map(lambda od: _orden_del_dia_senado(ctx, od), faltan)))
            paginas = list(ex.map(lambda f: _detalle(ctx, f, f["fecha"] >= hace_un_mes), filas))
        for f in filas:
            # La lista a veces enlaza el orden del día de otra cosa: pliegos («AC») para una ley.
            desde_od = exps_od.get(f["od"]) or []
            if not f["exps"] and desde_od and (any(c != "AC" for _, c in desde_od)
                                                or NOMBRAMIENTO.search(_sin_tildes(f["titulo"]).upper())):
                f["exps"] = desde_od
            if not f["titulo"] and f["exps"]:
                f["titulo"] = _extracto_senado(ctx, *f["exps"][0]) or f"Expediente {exp_senado_legible(f['exps'][0][0])}"
        info = asuntos_senado(filas, ref)
        asuntos, votaciones = {}, []
        for fila, pagina in zip(filas, paginas):
            if not pagina:
                continue
            votos_raw, totales = votos_senado(pagina)
            if not votos_raw:
                continue
            clave, tipo_a = info[fila["id"]][0], info[fila["id"]][2]
            aid = f"arg:{clave}"
            tipo_v = tipo_votacion_senado(fila, tipo_a)
            _anotar(asuntos, aid, info[fila["id"]], fila["fecha"], tipo_v == "procedimiento")
            votos, vistos = [], set()
            for sid, nombre_s, bloque, voto in votos_raw:
                sid = sid or senadores.id(nombre_s, fila["fecha"])
                mid = f"arg:s:{sid}" if sid else "arg:s:" + re.sub(r"[^a-z0-9]+", "-", _sin_tildes(nombre_s).lower()).strip("-")
                if mid in vistos or not nombre_s:
                    continue
                vistos.add(mid)
                partido = _registrar_partido(ctx, bloque)
                votos.append((mid, _nombre_persona(nombre_s), partido, SENTIDO_TEXTO.get(_sin_tildes(voto), "no_vota")))
            n = {s: sum(1 for *_, x in votos if x == s) for s in ("si", "no", "abstencion", "no_vota")}
            if (n["si"], n["no"], n["abstencion"]) != (totales.get("AFIRMATIVOS"), totales.get("NEGATIVOS"), totales.get("ABSTENCIONES")):
                ctx.log(f"   ! acta del Senado {fila['id']}: los totales del acta {totales} no cuadran con los votos {n}")
            r = fila["resultado"]
            resultado = "aprobada" if r.startswith("AFIRM") else "rechazada" if r.startswith("NEG") else None
            partes = ", ".join(p for p in fila["partes"] if _sin_tildes(p).lower() not in _sin_tildes(fila["titulo"]).lower())
            texto = " · ".join(x for x in (fila["titulo"], partes, fila["tipo"].capitalize() if fila["tipo"] else None) if x)
            votaciones.append(Votacion(
                id=f"arg:s:{fila['id']}", fecha=fila["fecha"], asunto_id=aid, camara="arg-s", numero=fila["acta"],
                texto=texto[:600], tipo=tipo_v, a_favor=n["si"], en_contra=n["no"], abstenciones=n["abstencion"],
                no_votan=n["no_vota"], mayoria=fila["mayoria"], resultado=resultado,
                url=f"{SENADO}/votaciones/detalleActa/{fila['id']}", votos=votos))
        _guardar(ctx, asuntos, votaciones)
        ctx.log(f"   Senado {anio}: {len(votaciones)} votaciones, {len(asuntos)} asuntos")


def recoger(ctx):
    ref = Referencias(ctx)
    recoger_diputados(ctx, ref)
    recoger_senado(ctx, ref)
