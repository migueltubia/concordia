"""Israel: votaciones del pleno de la Knesset (OData V4 oficial, https://knesset.gov.il/OdataV4/ParliamentInfo).

El servicio OData de la Knesset (sin clave) da cada votación del pleno (KNS_PlenumVote: fecha, título del
punto del orden del día, qué se vota —«ForOptionDesc»: tercera lectura, reserva, lectura preliminar,
moción de censura...— y el punto, ItemID) con el voto de cada diputado (KNS_PlenumVoteResult: a favor, en
contra, abstención o «presente sin votar»; los ausentes no aparecen). No publica totales ni resultado: se
cuentan de los votos, y el resultado es a favor > en contra, salvo en las mociones de censura, que necesitan
61 votos (con esas reglas cuadra con el campo «is_accepted» del servicio antiguo, Votes.svc, que se quedó en
2021). Las votaciones a mano alzada y las secretas (Presidente del Estado, Interventor) no tienen voto
nominal y no se recogen.

- Asunto = el punto votado (ItemID), que es un identificador único de la Knesset: el proyecto de ley
  (KNS_Bill; todas sus lecturas y reservas llevan el mismo ItemID; código «P/1234/25» para las
  proposiciones de ley de diputados, «M/<número>» para los proyectos del Gobierno y «K/<número>» para los de
  comisión, como פ/, מ/ y כ/ en la Knesset), la moción para el orden del día (KNS_Agenda), la legislación
  secundaria (KNS_SecondaryLaw) o, sin ficha, las comunicaciones del Gobierno, mociones de censura,
  elecciones y propuestas de la Comisión de la Knesset. Las proposiciones que la comisión funde en otro
  proyecto conservan su asunto con la lectura preliminar; la tercera lectura va en el proyecto principal.
- Tipo de votación por «ForOptionID»: tercera lectura → final; lectura preliminar, primera y segunda
  (esta, por artículos) → otra; reserva (הסתייגות, las enmiendas de la oposición) → enmienda; pase a otra
  comisión, continuidad, división del proyecto → procedimiento; moción de censura, mociones para el orden
  del día, legislación secundaria y comunicaciones del Gobierno → final.
- Voto de cada diputado; los diputados en ejercicio ese día que no votan se añaden como «no vota».
  La facción de cada uno ese día sale de KNS_PersonToPosition (fechas de alta y baja en cada facción). Las
  facciones cambian de nombre en cada Knesset y se separan y juntan a menudo: se agrupan por partido con
  códigos estables (Likud, YeshAtid, Shas...) según el nombre hebreo. El identificador del diputado en las
  votaciones (MkId) es el de KNS_Person (comprobado en 2026-09; en agosto de 2026 el servicio dio otros en
  parte de los votos: si un MkId no es un diputado conocido, se busca por el nombre hebreo). Los nombres en
  alfabeto latino salen de View_Vote_MK_Individual del servicio antiguo (con otros identificadores: se cruza
  por el nombre hebreo) y, si falta, quedan en hebreo.

El servicio tiene votaciones desde 1950 (las antiguas, pasadas de papel); se recoge desde 2019 (Knesset 20 a
25; 2019 tiene poco: tres Knesset disueltas). Se piden meses enteros, con los votos expandidos en la misma
respuesta (100 votaciones por página y hasta 100 votos por votación; el resto de las de más de 100 votantes
en una segunda petición); los meses cerrados se guardan en data/raw/isr/. Los títulos están en hebreo: las
reglas no los leen y la ficha la hace la IA. La vista repite algunas filas (se descartan) y el cortafuegos de
la Knesset bloquea ráfagas de peticiones y algunas consultas ($orderby dentro de $expand, funciones): se piden
pocas y sencillas.
"""

import json
import re
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from urllib.parse import quote

from ..http_util import Bloqueada
from .modelo import Asunto, Fuente, Votacion

FUENTE = Fuente(
    codigo="isr", pais="ISR", nombre="Knesset de Israel", corto="Israel", tipo="parlamento", detalle="nominal",
    web="https://main.knesset.gov.il", desde=2019, idioma="otro",
    licencia="Datos abiertos de la Knesset (OData): uso según las condiciones del sitio de la Knesset "
             "(no comercial y citando la fuente; las leyes y las actas son de dominio público)",
    camaras={"isr-k": ("Knesset", "Knesset", 120)},
    partidos={
        "Likud": ("Likud", "Likud", "#1f4e9c"),
        "YeshAtid": ("Yesh Atid (Hay Futuro)", "Yesh Atid", "#29a3d6"),
        "KaholLavan": ("Azul y Blanco (Kajol Lavan)", "Kajol Lavan", "#5b8ed6"),
        "MahaneMamlakhti": ("Unidad Nacional (HaMajané HaMamlajtí)", "Unidad Nac.", "#3a5fb0"),
        "Shas": ("Shas", "Shas", "#1d2b4f"),
        "UTJ": ("Judaísmo Unido de la Torá", "JUT", "#2b2b2b"),
        "Degel": ("Deguel HaTorá", "Deguel", "#474747"),
        "Agudat": ("Agudat Israel", "Agudat", "#626262"),
        "TziyonutDatit": ("Sionismo Religioso", "Sion. Rel.", "#b8651b"),
        "Otzma": ("Poder Judío (Otzmá Yehudit)", "Otzmá", "#e3a51c"),
        "Noam": ("Noam", "Noam", "#8a5a2b"),
        "YisraelBeiteinu": ("Israel Nuestra Casa (Yisrael Beiteinu)", "Yisrael B.", "#4b3f8f"),
        "TikvaHadasha": ("Nueva Esperanza / Derecha Estatal (Tikvá Jadashá)", "N. Esperanza", "#2a8199"),
        "Yamina": ("Yamina", "Yamina", "#8a5fb5"),
        "YaminHadash": ("Nueva Derecha (HaYamín HeJadash)", "N. Derecha", "#a07fd0"),
        "BayitYehudi": ("Hogar Judío (HaBait HaYehudí)", "Hogar Judío", "#6aa84f"),
        "Kulanu": ("Kulanu", "Kulanu", "#23a0c8"),
        "Avoda": ("Partido Laborista (HaAvodá)", "Laboristas", "#e2231a"),
        "Meretz": ("Meretz", "Meretz", "#3fae29"),
        "MahaneTziyoni": ("Unión Sionista (HaMajané HaTzioní)", "U. Sionista", "#e3522c"),
        "MahaneDemokrati": ("Unión Democrática (HaMajané HaDemokratí)", "U. Democr.", "#48a846"),
        "Gesher": ("Gesher", "Gesher", "#c060a1"),
        "DerekhEretz": ("Derej Eretz", "Derej Eretz", "#5c7fa3"),
        "Telem": ("Telem", "Telem", "#2c6e8f"),
        "HaTnua": ("Hatnuá", "Hatnuá", "#4a90c2"),
        "Ahi": ("Ahi", "Ahi", "#8aa55a"),
        "HofeshKalkali": ("Libertad Económica", "Lib. Econ.", "#9a9a9a"),
        "Meshutefet": ("Lista Conjunta", "L. Conjunta", "#5b9b4f"),
        "HadashTaal": ("Hadash-Ta'al", "Hadash-Ta'al", "#d6362c"),
        "Hadash": ("Hadash (Frente Democrático por la Paz y la Igualdad)", "Hadash", "#e0301e"),
        "Taal": ("Ta'al (Movimiento Árabe para la Renovación)", "Ta'al", "#2e8b57"),
        "Raam": ("Lista Árabe Unida (Ra'am)", "Ra'am", "#1b7f3a"),
        "Balad": ("Balad (Asamblea Nacional Democrática)", "Balad", "#9c1c1c"),
        "Unipersonal": ("Facción unipersonal (diputado escindido)", "Unipers.", "#898781"),
    },
    notas="Voto de cada diputado en las votaciones electrónicas y nominales del pleno; las votaciones a mano alzada "
          "y las secretas no tienen registro nominal y no se recogen.",
    # Sin probar de principio a fin: el cortafuegos de knesset.gov.il bloqueó la IP de prueba (HTTP 474) tras
    # la exploración. Se activa cuando `python -m concordia probar isr --desde 2026` termine bien.
    activa=False,
)

API = "https://knesset.gov.il/OdataV4/ParliamentInfo"
API_ANTIGUA = "https://knesset.gov.il/Odata/Votes.svc"
CAB = {"Accept": "application/json"}
URL_VOTO = "https://main.knesset.gov.il/activity/plenum/votes/pages/vote.aspx?voteid={}"
URL_LEY = "https://main.knesset.gov.il/Activity/Legislation/Laws/Pages/LawBill.aspx?t=lawsuggestionssearch&lawitemid={}"
# Día en que empieza cada Knesset (para pedir solo los diputados y facciones de las que tocan).
INICIO_KNESSET = {18: "2009-02-24", 19: "2013-02-05", 20: "2015-03-31", 21: "2019-04-30", 22: "2019-10-03",
                  23: "2020-03-16", 24: "2021-04-06", 25: "2022-11-15"}
MIEMBRO, MIEMBRA, PORTAVOZ, EN_FACCION = 43, 61, 48, 54   # KNS_Position
VOTOS = "MkId,ResultCode,FirstName,LastName"
# ResultCode: 7 a favor, 8 en contra, 9 abstención, 6 presente sin votar, 10 no presente, 11 «votó» (secreta).
SENTIDO = {7: "si", 8: "no", 9: "abstencion", 6: "abstencion", 10: "no_vota"}
SECRETA = 11
CENSURA = 16

# ForOptionID -> (qué se vota, tipo de votación)
OPCIONES = {
    8: ("Tercera lectura (aprobación final)", "final"),
    6: ("Segunda lectura", "otra"),
    7: ("Reserva (enmienda)", "enmienda"),
    1: ("Primera lectura", "otra"),
    2: ("Primera lectura (comisión que fije la Comisión de la Knesset)", "otra"),
    12: ("Lectura preliminar", "otra"),
    13: ("Lectura preliminar (comisión que fije la Comisión de la Knesset)", "otra"),
    32: ("Lectura preliminar (comisión que fije la comisión organizadora)", "otra"),
    14: ("Convertir la proposición de ley en moción y enviarla a comisión", "otra"),
    CENSURA: ("Moción de censura al Gobierno", "final"),
    17: ("Enviar el asunto a comisión", "final"),
    18: ("Enviar el asunto a la comisión que fije la Comisión de la Knesset", "final"),
    19: ("Incluir el asunto en el orden del día", "final"),
    20: ("No incluir el asunto en el orden del día", "final"),
    21: ("Propuesta de conclusiones del debate", "final"),
    23: ("Aprobar la legislación secundaria", "final"),
    25: ("Aprobar la comunicación del Gobierno", "final"),
    26: ("Aprobar la comunicación del primer ministro", "final"),
    38: ("Aprobar la propuesta", "final"),
    22: ("Propuesta de la Comisión de la Knesset", "final"),
    27: ("Propuesta de comisión", "final"),
    15: ("Decisión de comisión (división del proyecto)", "procedimiento"),
    28: ("Propuesta de la comisión organizadora", "procedimiento"),
    29: ("Composición de la comisión organizadora", "procedimiento"),
    9: ("Aplicar la continuidad al proyecto", "procedimiento"),
    35: ("Pasar el proyecto a otra comisión", "procedimiento"),
    36: ("Pasar la moción a otra comisión", "procedimiento"),
    3: ("Devolver el proyecto a comisión", "procedimiento"),
    37: ("Devolver el proyecto a comisión", "procedimiento"),
    4: ("Retirar el proyecto del orden del día", "procedimiento"),
    39: ("Corregir un error en una ley aprobada", "otra"),
    31: ("Propuesta de un diputado", "otra"),
    30: ("Votación", "otra"),
}
# Opciones que dicen de qué es el asunto cuando el punto no tiene ficha (comunicaciones, propuestas...).
OPCION_ASUNTO = {17: "mocion", 18: "mocion", 19: "mocion", 20: "mocion", 21: "mocion", 26: "mocion", CENSURA: "mocion",
                 23: "ley", 8: "ley", 6: "ley", 7: "ley", 1: "ley", 2: "ley", 12: "ley", 13: "ley", 32: "ley"}

# Facción (nombre hebreo, cambia en cada Knesset) -> partido. Por orden: gana la primera que casa.
FACCIONES = [
    (r'ימינה', "Yamina"), (r'הבית היהודי', "BayitYehudi"), (r'הימין החדש', "YaminHadash"),
    (r'הימין הממלכתי|תקווה חדשה', "TikvaHadasha"), (r'עוצמה יהודית', "Otzma"), (r'^נעם\b', "Noam"),
    (r'הציונות הדתית|^האיחוד הלאומי', "TziyonutDatit"), (r'ש"ס|התאחדות הספרדים', "Shas"),
    (r'יהדות התורה', "UTJ"), (r'דגל התורה', "Degel"), (r'אגודת ישראל', "Agudat"), (r'הליכוד', "Likud"),
    (r'יש עתיד', "YeshAtid"), (r'^תל"ם', "Telem"), (r'כחול לבן', "KaholLavan"),
    (r'המחנה הממלכתי', "MahaneMamlakhti"), (r'המחנה הציוני', "MahaneTziyoni"),
    (r'המחנה הדמוקרטי', "MahaneDemokrati"), (r'ישראל ביתנו', "YisraelBeiteinu"), (r'כולנו', "Kulanu"),
    (r'העבודה', "Avoda"), (r'מרצ', "Meretz"), (r'^גשר|אורלי לוי', "Gesher"),
    (r'הרשימה המשותפת', "Meshutefet"), (r'חד"ש.{0,3}תע"ל', "HadashTaal"), (r'^חד"ש', "Hadash"),
    (r'^תע"ל|התנועה הערבית', "Taal"), (r'רע"[םמ]|הרשימה הערבית המאוחדת', "Raam"), (r'בל"ד', "Balad"),
    (r'^התנועה$', "HaTnua"), (r'דרך ארץ', "DerekhEretz"), (r'אח"י', "Ahi"), (r'חופש כלכלי', "HofeshKalkali"),
    (r'^חה"כ|^ביחד$|^עתיד אחד$', "Unipersonal"),
]

# Tipo de asunto de los puntos sin ficha, por el título (en hebreo).
TRATADO = (r"הסכמי אברהם|הסכם (?:ה)?שלום|חוזה שלום|יחסים דיפלומטיים|קשרי דיפלומטיה|(?:^|\s)(?:הצעת )?חוק (?:ה)?אמנת"
           r"|אשרור (?:ה)?(?:הסכם|אמנ)")
NOMBRAMIENTO = (r"בחירת (?:ה)?(?:יושב|סגנ|נשיא|מבקר|נציגי|שופט)|יושב-?\s?ראש הכנסת|סגני?ם?\s+(?:זמניים\s+)?(?:נוספים\s+)?"
                r"ליושב|נשיא המדינה|מבקר המדינה|מינוי|למנות|צירוף|לצרף|כינון (?:ה)?ממשלת|כינון הממשלה|השבעת|"
                r"חלוקת התפקידים|שר נוסף")
PROCEDIMIENTO = (r"הרכב|הוועדה המסדרת|ועדת הכנסת|מוועדה לוועדה|דין רציפות|פיצול|הקמת (?:ה)?ועד|הוועדה המיוחדת|"
                 r"בחירת (?:ה)?ועד|חסינות|ערעור|תיקון טעות|תקנון")
MOCION = r"^(?:הצעה|הצעות) (?:דחופ\S* |רגיל\S* )?לסדר|דיון בהשתתפות ראש הממשלה|סיכום הדיון|הודעת ראש הממשלה"
LEY = r"^(?:הצעת )?(?:חוק|תקנות|צו)\b|חקיקת משנה|(?:^|\s)(?:צו|תקנות) "
INICIATIVA = {"פרטית": ("P", "de diputados"), "ממשלתית": ("M", "del Gobierno"), "ועדה": ("K", "de comisión")}


# ------------------------------------------------------------------ descargas

def _json(ctx, url):
    """GET JSON. El cortafuegos de la Knesset contesta 47x/49x («access denied») a las ráfagas: se para."""
    for intento in range(3):
        try:
            return ctx.json(url, headers=CAB)
        except RuntimeError as e:
            if re.search(r"HTTP Error 4[79]\d", str(e)):
                raise Bloqueada(f"{url}: el cortafuegos de la Knesset rechaza las peticiones ({e})") from e
            raise
        except ValueError:  # respuesta vacía o cortada: se reintenta
            if intento == 2:
                raise


def _pagina(ctx, url, nombre=None, caduca=None):
    if not nombre:
        return _json(ctx, url)
    try:
        ruta = ctx.cache(url, nombre, caduca_horas=caduca, headers=CAB)
    except RuntimeError as e:
        if re.search(r"HTTP Error 4[79]\d", str(e)):
            raise Bloqueada(f"{url}: el cortafuegos de la Knesset rechaza las peticiones ({e})") from e
        raise
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except ValueError:
        ruta.unlink(missing_ok=True)
        return _json(ctx, url)


def _paginas(ctx, url, nombre=None, caduca=None):
    """Filas de una consulta OData siguiendo @odata.nextLink (100 por página)."""
    n = 0
    while url:
        d = _pagina(ctx, url, f"{nombre}-{n}.json" if nombre else None, caduca)
        yield from d.get("value", [])
        url = d.get("@odata.nextLink") or d.get("odata.nextLink")
        if url and not url.startswith("http"):  # el servicio antiguo da el enlace relativo y sin $format
            url = f"{API_ANTIGUA}/{url}" + ("" if "$format=" in url else "&$format=json")
        n += 1


def _filtro(expr):
    return quote(expr, safe="():,'")


# ------------------------------------------------------------------ diputados y facciones

def _normaliza(t):
    return (t or "").replace("\u05f4", '"').replace("\u05f3", "'").replace("\u200f", "").replace("\u200e", "").strip()


def _hebreo(t):
    return re.sub(r"[^א-ת]", "", t or "")


class Diputados:
    """Quién es diputado cada día, en qué facción está y cómo se llama."""

    def __init__(self, ctx, desde):
        self.ctx = ctx
        kmin = max((k for k, d in INICIO_KNESSET.items() if d <= desde.isoformat()), default=17)
        cargos = list(_paginas(
            ctx, f"{API}/KNS_PersonToPosition?$filter="
                 + _filtro(f"KnessetNum ge {kmin} and PositionID in ({MIEMBRO},{MIEMBRA},{PORTAVOZ},{EN_FACCION})")
                 + "&$select=PersonID,PositionID,KnessetNum,StartDate,FinishDate,FactionID,FactionName",
            f"cargos-k{kmin}", caduca=24))
        self.escanos = defaultdict(list)   # persona -> [(inicio, fin, knesset)]
        self.facciones = defaultdict(list)  # persona -> [(inicio, fin, partido)]
        self.nuevas = {}
        self._ejercicio = {}
        for c in cargos:
            ini, fin = c["StartDate"][:10], (c.get("FinishDate") or "9999-12-31")[:10]
            if c["PositionID"] in (MIEMBRO, MIEMBRA):
                self.escanos[c["PersonID"]].append((ini, fin, c["KnessetNum"]))
            elif c.get("FactionID"):
                self.facciones[c["PersonID"]].append((ini, fin, self._partido(c["FactionID"], c.get("FactionName"))))
        self.por_nombre = {}
        self.nombres = self._nombres(ctx, sorted(self.escanos))

    def _partido(self, fid, nombre):
        n = _normaliza(nombre)
        for patron, codigo in FACCIONES:
            if re.search(patron, n):
                return codigo
        codigo = f"F{fid}"
        self.nuevas[codigo] = n or codigo
        return codigo

    def _nombres(self, ctx, ids):
        """Nombre de cada diputado: en alfabeto latino si el servicio antiguo lo tiene; si no, en hebreo."""
        hebreo = {}
        for i in range(0, len(ids), 50):
            filtro = _filtro(f"Id in ({','.join(map(str, ids[i:i + 50]))})")
            for p in _paginas(ctx, f"{API}/KNS_Person?$filter={filtro}&$select=Id,FirstName,LastName"):
                hebreo[p["Id"]] = (p.get("FirstName") or "", p.get("LastName") or "")
        claves = Counter((_hebreo(n), _hebreo(a)) for n, a in hebreo.values())
        self.por_nombre = {(_hebreo(n), _hebreo(a)): pid for pid, (n, a) in hebreo.items() if claves[(_hebreo(n), _hebreo(a))] == 1}
        latino = {}
        try:
            candidatos = defaultdict(set)
            for m in _paginas(ctx, f"{API_ANTIGUA}/View_Vote_MK_Individual?$format=json", "nombres-latinos", caduca=24 * 7):
                clave = (_hebreo(m.get("mk_individual_first_name")), _hebreo(m.get("mk_individual_name")))
                en = " ".join(x.strip() for x in (m.get("mk_individual_first_name_eng"), m.get("mk_individual_name_eng")) if x)
                if en:
                    candidatos[clave].add(en)
            latino = {k: v.pop() for k, v in candidatos.items() if len(v) == 1}
        except Exception as e:  # el servicio antiguo va a desaparecer: los nombres quedan en hebreo
            ctx.log(f"   ! sin nombres en alfabeto latino ({type(e).__name__}: {e})")
        nombres = {}
        for pid, (nom, ape) in hebreo.items():
            nombres[pid] = latino.get((_hebreo(nom), _hebreo(ape))) or f"{nom} {ape}".strip()
        return nombres

    def persona(self, mkid, nom, ape):
        """Id de KNS_Person del votante. MkId lo es, pero en 2026 el servicio llegó a dar en un tercio de los votos
        otros identificadores (se arregló en septiembre): si no es un diputado conocido, se busca por el nombre."""
        if mkid in self.escanos:
            return mkid
        return self.por_nombre.get((_hebreo(nom), _hebreo(ape)), mkid)

    def nombre(self, pid, nom=None, ape=None):
        if pid not in self.nombres:
            self.nombres[pid] = f"{nom or ''} {ape or ''}".strip() or str(pid)
        return self.nombres[pid]

    def partido(self, pid, dia):
        """Facción ese día (el día del cambio, la nueva; en los huecos de un día, la más cercana)."""
        periodos = self.facciones.get(pid) or []
        dentro = [p for p in periodos if p[0] <= dia <= p[1]]
        if dentro:
            return max(dentro)[2]
        if periodos:
            d = date.fromisoformat(dia).toordinal()
            distancia = lambda p: min(abs(date.fromisoformat(f).toordinal() - d) for f in (p[0], min(p[1], "9999-12-30")))
            return min(periodos, key=distancia)[2]
        return "?"

    def en_ejercicio(self, dia, votantes):
        """Diputados de la Knesset de esa votación en ejercicio ese día (el día del relevo, los que entran)."""
        ks = [k for pid in votantes for ini, fin, k in self.escanos.get(pid, ()) if ini <= dia <= fin]
        if not ks:
            return set()
        clave = (max(ks), dia)
        if clave not in self._ejercicio:
            self._ejercicio[clave] = {pid for pid, ps in self.escanos.items()
                                      for ini, fin, k in ps if k == clave[0] and ini <= dia < fin}
        return self._ejercicio[clave]


# ------------------------------------------------------------------ asuntos

def _limpia(t):
    t = _normaliza(t)
    t = re.sub(r"(?<=[א-ת\"'])\?(?=\d)", "-", t)   # el guion de «התש"ף-2020» llega como «?»
    t = re.sub(r"\s+\?\s+", " – ", t)
    t = re.sub(r"\s+", " ", t).strip(" *")
    t = re.sub(r"\s*[-–]\s*(?:דיון ו)?הצבעה\s*$", "", t)
    return t.strip()


def tipo_asunto(titulo, opcion=None):
    """Tipo de un punto sin ficha (comunicaciones del Gobierno, propuestas de comisión...) por su título."""
    t = titulo or ""
    if opcion == CENSURA or re.search(r"אי[- ]אמון", t):
        return "mocion"
    if re.search(TRATADO, t):
        return "tratado"
    if re.match(MOCION, t):  # las mociones para el orden del día, aunque hablen de nombramientos o comisiones
        return "mocion"
    if re.search(NOMBRAMIENTO, t):
        return "nombramiento"
    if re.search(PROCEDIMIENTO, t):
        return "procedimiento"
    if re.search(MOCION, t):
        return "mocion"
    if re.search(LEY, t):
        return "ley"
    return OPCION_ASUNTO.get(opcion, "otro")


def _fichas(ctx, ids, conocidos):
    """Busca cada punto en proyectos de ley, mociones y legislación secundaria (lo que no esté, sin ficha)."""
    faltan = sorted(i for i in ids if i not in conocidos)
    for tabla, campos in (("KNS_Bill", "Id,Name,KnessetNum,SubTypeDesc,PrivateNumber,Number"),
                          ("KNS_Agenda", "Id,Name,KnessetNum,Number"),
                          ("KNS_SecondaryLaw", "Id,Name,KnessetNum")):
        for i in range(0, len(faltan), 50):
            filtro = _filtro(f"Id in ({','.join(map(str, faltan[i:i + 50]))})")
            for r in _paginas(ctx, f"{API}/{tabla}?$filter={filtro}&$select={campos}"):
                conocidos[r["Id"]] = (tabla, r)
        faltan = [i for i in faltan if i not in conocidos]
    # Sin ficha (comunicaciones del Gobierno, propuestas de comisión...): el nombre del punto en el orden del día,
    # para las votaciones que llegan sin título.
    nombres = {}
    for i in range(0, len(faltan), 50):
        filtro = _filtro(f"ItemID in ({','.join(map(str, faltan[i:i + 50]))})")
        for r in _paginas(ctx, f"{API}/KNS_PlmSessionItem?$filter={filtro}&$select=ItemID,Name"):
            if _limpia(r.get("Name")):
                nombres.setdefault(r["ItemID"], {"Name": r["Name"]})
    for i in faltan:
        conocidos[i] = (None, nombres.get(i))


def asunto_de(v, tabla, ficha, fecha):
    item = v.get("ItemID")
    titulo_v = _limpia(v.get("VoteTitle")) or _limpia(v.get("VoteSubject"))
    aid = f"isr:{item}" if item else f"isr:v{v['Id']}"
    codigo = url = None
    extra = {"knesset": ficha["KnessetNum"]} if ficha and ficha.get("KnessetNum") else None
    if re.fullmatch(GENERICO, titulo_v or ""):  # «הצבעה»: el nombre del punto o, si no, qué se votó
        titulo_v = _limpia((ficha or {}).get("Name")) or f"{texto_votacion(v)} (votación {v['Id']})"
    if tabla == "KNS_Bill":
        titulo = _limpia(ficha.get("Name")) or titulo_v
        letra, quien = INICIATIVA.get(ficha.get("SubTypeDesc"), ("K", None))
        if letra == "P" and ficha.get("PrivateNumber"):
            codigo = f"P/{ficha['PrivateNumber']}/{ficha.get('KnessetNum')}"
        elif ficha.get("Number"):
            codigo = f"{letra}/{ficha['Number']}"
        if quien:
            extra = {**(extra or {}), "iniciativa": quien}
        url = URL_LEY.format(item)
        tipo = "tratado" if re.search(r"חוק (?:ה)?אמנת|אשרור", titulo) else "ley"
    elif tabla == "KNS_Agenda":
        titulo, tipo = _limpia(ficha.get("Name")) or titulo_v, "mocion"
    elif tabla == "KNS_SecondaryLaw":
        titulo, tipo = _limpia(ficha.get("Name")) or titulo_v, "ley"
    else:
        titulo = titulo_v
        tipo = tipo_asunto(titulo, v.get("ForOptionID"))
    return Asunto(id=aid, titulo=(titulo or f"Votación {v['Id']}")[:400], tipo=tipo, fecha=fecha, codigo=codigo,
                  url=url, extra=extra)


# ------------------------------------------------------------------ votaciones

# Subtítulos que no dicen nada más que la opción votada («votación», «reserva», «aprobar la ley»...).
GENERICO = (r"^(?:הצבעה|הסתייגו(?:ת|יות)|אישור החוק|קריאה (?:שנייה|שלישית)|הודעת (?:ה)?ממשלה|הודעת ראש הממשלה|"
            r"הצעת (?:ה)?ועד(?:ה|ת הכנסת)|הצעת הוועדה המסדרת|הצעת אי[- ]אמון בממשלה|(?:להעביר|לקבל|לאשר|להחיל|לכלול|העברת) .*)?$")
SECCION = r"(לפני\s+)?(?:ל|ב)?סעי(?:ף|פים)\s+(\d+[א-ת]?(?:\s*[-–]\s*\d+)?)"


def _rango(t):
    """«2-1» (escrito de derecha a izquierda) -> «1-2»."""
    m = re.fullmatch(r"(\d+)\s*[-–]\s*(\d+)", t.strip())
    if m and int(m.group(1)) > int(m.group(2)):
        return f"{m.group(2)}–{m.group(1)}"
    return t.strip().replace("-", "–")


def texto_votacion(v):
    """Qué se vota, en español cuando se reconoce («Reserva 12 al artículo 4», «Segunda lectura, artículos 1–3»)."""
    oid, desc = v.get("ForOptionID"), _normaliza(v.get("ForOptionDesc"))
    base = OPCIONES.get(oid, (desc or "Votación", None))[0]
    s = _limpia(v.get("VoteSubject"))
    if re.fullmatch(GENERICO, s) or s == desc or s == _limpia(v.get("VoteTitle")):
        return base
    art = re.search(SECCION, s)
    articulo = (f"{'antes del' if art.group(1) else 'al'} artículo {_rango(art.group(2))}") if art else None
    if oid == 7:
        n = re.search(r"\((\d+)\)|הסתייגו(?:ת|יות)\s+(?:מס['\u05f3]\s*)?(\d+)", s)
        numero = (n.group(1) or n.group(2)) if n else None
        resto = re.search(r"\s[-–]\s+(\S.*)$", s)  # «הסתייגויות לסעיף 09 - משרד החוץ»: la partida
        if numero or articulo:
            return " ".join(x for x in ("Reserva", numero, articulo) if x) + (f" · {resto.group(1)}" if resto else "")
    if oid == 6:
        m = re.fullmatch(r"סעי(?:ף|פים)\s+([\d\s,–\-ו]+?)(?:,?\s*(?:כהצעת|כנוסח) הוועדה)?", s)
        if m:
            plural = "artículos" if s.startswith("סעיפים") else "artículo"
            return f"Segunda lectura, {plural} {_rango(m.group(1))}"
    return f"{base} · {s}"[:300]


def tipo_votacion(v, tipo_a):
    tipo = OPCIONES.get(v.get("ForOptionID"), (None, "otra"))[1]
    if tipo_a == "procedimiento":
        return "procedimiento"
    if tipo_a == "nombramiento" and tipo in ("final", "otra"):
        return "nombramiento"
    return tipo


def votacion_de(v, aid, tipo_a, diputados):
    """Votación con el voto de cada diputado (los ausentes, «no vota»); None si no tiene voto nominal."""
    resultados = v.get("VoteResults") or []
    if not resultados or any(r.get("ResultCode") == SECRETA for r in resultados):
        return None
    dia = v["VoteDateTime"][:10]
    votos, vistos = [], set()
    for r in resultados:
        pid = diputados.persona(r["MkId"], r.get("FirstName"), r.get("LastName"))
        if pid in vistos:
            continue
        vistos.add(pid)
        votos.append((f"isr:{pid}", diputados.nombre(pid, r.get("FirstName"), r.get("LastName")),
                      diputados.partido(pid, dia), SENTIDO.get(r.get("ResultCode"), "no_vota")))
    for pid in sorted(diputados.en_ejercicio(dia, vistos) - vistos):
        votos.append((f"isr:{pid}", diputados.nombre(pid), diputados.partido(pid, dia), "no_vota"))
    n = Counter(s for *_, s in votos)
    censura = v.get("ForOptionID") == CENSURA or bool(v.get("IsNoConfidenceInGov"))
    aprobada = n["si"] >= 61 if censura else n["si"] > n["no"]
    return Votacion(
        id=f"isr:{v['Id']}", fecha=dia, asunto_id=aid, camara="isr-k", numero=v.get("Ordinal"),
        texto=texto_votacion(v), tipo=tipo_votacion(v, tipo_a), a_favor=n["si"], en_contra=n["no"],
        abstenciones=n["abstencion"], no_votan=n["no_vota"], mayoria="absoluta (61)" if censura else "simple",
        resultado="aprobada" if aprobada else "rechazada", url=URL_VOTO.format(v["Id"]), votos=votos)


def _votaciones_mes(ctx, desde, hasta, cerrado):
    """Votaciones de [desde, hasta) con sus votos. Los meses cerrados se guardan en data/raw/isr/."""
    filtro = _filtro(f"VoteDateTime ge {desde}T00:00:00+02:00 and VoteDateTime lt {hasta}T00:00:00+02:00")
    base = f"{API}/KNS_PlenumVote?$filter={filtro}&$orderby=Id"
    nombre = f"votos-{desde:%Y-%m}" if cerrado else None
    votos, cortadas = {}, False
    for v in _paginas(ctx, f"{base}&$expand=VoteResults($select={VOTOS})", nombre):
        if v["Id"] not in votos:  # la vista repite algunas filas
            votos[v["Id"]] = v
            cortadas |= "VoteResults@odata.nextLink" in v
    if cortadas:  # más de 100 votantes: los que faltan, de todas a la vez
        for v in _paginas(ctx, f"{base}&$select=Id&$expand=VoteResults($skip=100;$select={VOTOS})",
                          f"resto-{desde:%Y-%m}" if cerrado else None):
            if v["Id"] in votos and v.get("VoteResults"):
                ya = {r["MkId"] for r in votos[v["Id"]]["VoteResults"]}
                votos[v["Id"]]["VoteResults"] += [r for r in v["VoteResults"] if r["MkId"] not in ya]
    return sorted(votos.values(), key=lambda v: (v["VoteDateTime"], v.get("Ordinal") or 0, v["Id"]))


def _meses(inicio, hoy):
    """[(desde, hasta, cerrado)] por meses; cerrado = mes entero que acabó hace más de 45 días."""
    salida, a = [], inicio
    while a <= hoy:
        b = date(a.year + (a.month == 12), a.month % 12 + 1, 1)
        salida.append((a, b, a.day == 1 and b < hoy - timedelta(days=45)))
        a = b
    return salida


def _guardar(ctx, asuntos, votaciones, lote=300):
    for i in range(0, len(votaciones), lote):
        trozo = votaciones[i:i + lote]
        ctx.guardar([asuntos[a] for a in dict.fromkeys(v.asunto_id for v in trozo)], trozo)


def recoger(ctx):
    hoy = date.today()
    inicio = date(ctx.desde, 1, 1)
    ultima = ctx.ultima_fecha()
    if ultima and not ctx.completo:
        inicio = max(inicio, date.fromisoformat(ultima) - timedelta(days=21))
    diputados = Diputados(ctx, inicio)
    for codigo, nombre in diputados.nuevas.items():
        ctx.partido(codigo, nombre, nombre[:14])
    ctx.log(f"   {len(diputados.escanos)} diputados; votaciones desde {inicio}")
    fichas = {}
    meses = _meses(inicio, hoy)
    with ThreadPoolExecutor(3) as ex:
        for i in range(0, len(meses), 6):  # de seis en seis meses, para no tener todo en memoria
            tanda = meses[i:i + 6]
            for (desde, _, _), lista in zip(tanda, ex.map(lambda m: _votaciones_mes(ctx, *m), tanda)):
                if lista:
                    _mes(ctx, desde, lista, diputados, fichas)


def _mes(ctx, desde, lista, diputados, fichas):
    _fichas(ctx, {v["ItemID"] for v in lista if v.get("ItemID")}, fichas)
    asuntos, votaciones, sin_nominal = {}, [], 0
    for v in lista:
        fecha = v["VoteDateTime"][:10]
        if fecha < f"{ctx.desde}-01-01":
            continue
        tabla, ficha = fichas.get(v.get("ItemID"), (None, None))
        a = asuntos.get(f"isr:{v.get('ItemID')}") or asunto_de(v, tabla, ficha, fecha)
        vot = votacion_de(v, a.id, a.tipo, diputados)
        if vot is None:
            sin_nominal += 1
            continue
        asuntos.setdefault(a.id, a)
        votaciones.append(vot)
    _guardar(ctx, asuntos, votaciones)
    ctx.log(f"   {desde:%Y-%m}: {len(votaciones)} votaciones, {len(asuntos)} asuntos"
            + (f" ({sin_nominal} a mano alzada o secretas, sin voto nominal)" if sin_nominal else ""))
