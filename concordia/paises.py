"""Catálogo de países (generado por herramientas/generar_paises.py) y detección de países en títulos."""

import json
import re
import unicodedata
from functools import lru_cache

from .config import DATOS_PAQUETE


@lru_cache(maxsize=1)
def todos():
    return json.loads((DATOS_PAQUETE / "paises.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def por_iso3():
    return {p["iso3"]: p for p in todos()}


def nombre(iso3):
    p = por_iso3().get(iso3)
    return p["nombre"] if p else iso3


# Regiones M49 como «grupos» de la Asamblea General de la ONU (códigos cortos, estables).
REGIONES = {"África": "AFR", "Américas": "AME", "Asia": "ASI", "Europa": "EUR", "Oceanía": "OCE"}
NOMBRE_REGION = {v: k for k, v in REGIONES.items()}


# Territorios que dependen de un Estado: para su metrópoli no son una relación exterior.
DEPENDENCIAS = {
    "USA": {"PRI", "GUM", "VIR", "ASM", "MNP", "UMI"},
    "GBR": {"GIB", "FLK", "BMU", "CYM", "VGB", "MSR", "TCA", "AIA", "SHN", "PCN", "IOT", "SGS", "GGY", "JEY", "IMN"},
    "FRA": {"GUF", "GLP", "MTQ", "MYT", "REU", "NCL", "PYF", "SPM", "WLF", "BLM", "MAF", "ATF"},
    "NLD": {"ABW", "CUW", "SXM", "BES"}, "DNK": {"GRL", "FRO"}, "NOR": {"SJM", "BVT"}, "AUS": {"CXR", "CCK", "NFK", "HMD"},
    "NZL": {"COK", "NIU", "TKL"}, "CHN": {"HKG", "MAC"}, "FIN": {"ALA"},
}


def propios(iso3):
    """El país y sus territorios dependientes."""
    return {iso3} | DEPENDENCIAS.get(iso3, set())


def solo_origen(iso3):
    """Organismos con parlamento propio (la Unión Europea, EUU): origen de relaciones, nunca destino."""
    return bool((por_iso3().get(iso3) or {}).get("organismo"))


def region(iso3):
    p = por_iso3().get(iso3) or {}
    if p.get("sucesor"):
        p = por_iso3().get(p["sucesor"]) or p
    return REGIONES.get(p.get("region"), "OTR")


# ------------------------------------------------------------------ detección en títulos

def _sin_tildes(t):
    return "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")


# Nombres que casi nunca son el país en un título de ese idioma: se exige una forma inequívoca.
AMBIGUOS = {
    # «Georgia» es casi siempre el estado de EEUU; «Jordan» y «Chad», nombres de pila; «Turkey», el pavo...
    "en": {"Georgia", "Jersey", "Chad", "Jordan", "Turkey", "Guinea", "Niger", "Mali", "Congo", "Dominica", "Samoa",
           "Macao", "Monaco", "Panama", "Wales", "Jamaica", "Grenada", "Montserrat", "Man", "Micronesia", "Guernsey",
           "Nauru", "Reunion", "Réunion"},
    "es": {"Georgia", "Chad", "Jordania", "Guinea", "Níger", "Malí", "Congo", "Dominica", "Samoa", "Granada", "Jersey",
           "Man", "Santa Lucía", "Reunión", "Guadalupe", "Montserrat", "Mauricio", "Palau", "Martinica"},
}
# Formas inequívocas de algunos ambiguos (se añaden a la búsqueda).
INEQUIVOCOS = {
    "en": {"GEO": ["Republic of Georgia", "Tbilisi"], "TCD": ["Republic of Chad"], "JOR": ["Kingdom of Jordan",
           "Hashemite Kingdom of Jordan"], "TUR": ["Republic of Turkey", "Türkiye", "Turkiye", "Turkish"],
           "CHL": ["Republic of Chile", "Chilean"], "CYP": ["Republic of Cyprus", "Cyprus question", "question of Cyprus"],
           "PSE": ["Palestinian people", "Palestinian territory", "Palestinian refugees",
           "Palestine refugees", "Palestinian Authority"], "ISR": ["Israeli practices", "Israeli settlements"],
           "CUB": ["Cuban Liberty"], "UKR": ["Ukrainian territories"], "COG": ["Republic of the Congo"],
           "NER": ["Republic of the Niger", "Republic of Niger"], "MLI": ["Republic of Mali"],
           # Gentilicios frecuentes en los títulos («Russian aggression», «Iranian regime»).
           "RUS": ["Russian", "Soviet"], "IRN": ["Iranian"], "SYR": ["Syrian"], "PRK": ["North Korean"],
           "VEN": ["Venezuelan"], "SAU": ["Saudi"], "MEX": ["Mexican"], "JPN": ["Japanese"], "KOR": ["South Korean"],
           "IRQ": ["Iraqi"], "LBY": ["Libyan"], "SDN": ["Sudanese"], "VNM": ["Vietnamese"], "TWN": ["Taiwanese"],
           "BLR": ["Belarusian"], "NIC": ["Nicaraguan"], "CUB": ["Cuban"], "ISR": ["Israeli"], "UKR": ["Ukrainian"],
           "AFG": ["Afghan"], "EGY": ["Egyptian"], "HTI": ["Haitian"], "ARM": ["Armenian"], "AZE": ["Azerbaijani"],
           "MMR": ["Burmese"], "YEM": ["Yemeni"], "LBN": ["Lebanese"], "GRC": ["Greek"], "POL": ["Polish"]},
    "es": {"GEO": ["República de Georgia"], "JOR": ["Reino de Jordania"], "PSE": ["pueblo palestino",
           "Estado palestino", "Estado de Palestina", "territorios palestinos"],
           "ISR": ["Estado de Israel"], "UKR": ["pueblo ucraniano"], "MAR": ["Reino de Marruecos"],
           "ESH": ["pueblo saharaui", "saharaui", "saharauis"],
           # Gentilicios («invasión rusa», «colonos israelíes»).
           "RUS": ["ruso", "rusa", "rusos", "rusas", "soviético", "soviética"], "ISR": ["israelí", "israelíes"],
           "MAR": ["marroquí", "marroquíes"], "UKR": ["ucraniano", "ucraniana", "ucranianos", "ucranianas"],
           "USA": ["estadounidense", "estadounidenses", "norteamericano", "norteamericana"], "IRN": ["iraní", "iraníes"],
           "VEN": ["venezolano", "venezolana", "venezolanos"], "CUB": ["cubano", "cubana", "cubanos"],
           "PSE": ["pueblo palestino", "Estado palestino", "Estado de Palestina", "territorios palestinos", "palestino",
                   "palestina", "palestinos", "palestinas"], "DZA": ["argelino", "argelina"], "CHN": ["chino", "chinos"],
           "TUR": ["turco", "turca"], "NIC": ["nicaragüense"], "BLR": ["bielorruso", "bielorrusa"]},
}
# En la ONU, «Georgia», «Jordan», «Chad»... son siempre el país.
AMBIGUOS_ONU = {"Jersey", "Man", "Wales", "Guernsey", "Montserrat"}
# Palabras delante que convierten el nombre en otra cosa (New Mexico, Northern Ireland, Papua New Guinea...).
_PREFIJOS_NO = r"(?<!New )(?<!Northern )(?<!Nueva )(?<!Papua )(?<!Equatorial )(?<!South )(?<!North )(?<!West )"


@lru_cache(maxsize=4)
def _patron(idioma, onu=False):
    formas = {}
    for p in todos():
        if p.get("sucesor") and idioma == "es":
            continue
        for a in p["alias_" + ("en" if idioma == "en" else "es")]:
            if len(a) < 4 and a not in ("USA", "U.S.", "U.K.", "EEUU"):
                continue
            if a in (AMBIGUOS_ONU if onu else AMBIGUOS[idioma]):
                continue
            formas.setdefault(_sin_tildes(a).lower(), p["iso3"])
    for iso3, lista in INEQUIVOCOS[idioma].items():
        for a in lista:
            formas[_sin_tildes(a).lower()] = iso3
    orden = sorted(formas, key=len, reverse=True)
    patron = re.compile(r"(?<!\w)" + _PREFIJOS_NO.lower() + "(" + "|".join(re.escape(f) for f in orden) + r")(?!\w)")
    return patron, formas


def detectar(texto, idioma="en", excluir=(), onu=False, posiciones=False):
    """Países nombrados en un texto, en orden de aparición: [(iso3, forma encontrada[, inicio])].

    onu=True: títulos de la ONU, donde «Georgia» o «Jordan» son siempre el país.
    """
    if not texto:
        return []
    patron, formas = _patron("en" if idioma == "en" else "es", onu)
    t = _sin_tildes(texto).lower()
    vistos, salida = set(), []
    for m in patron.finditer(t):
        iso3 = formas[m.group(1)]
        # «Guinea-Bissau» y «Papua New Guinea» ya van enteras; «Sudan» dentro de «South Sudan», también.
        if iso3 in excluir or iso3 in vistos:
            continue
        vistos.add(iso3)
        salida.append((iso3, texto[m.start(1):m.end(1)], m.start(1)) if posiciones else (iso3, texto[m.start(1):m.end(1)]))
    return salida
