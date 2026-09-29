"""Genera el catálogo de países (concordia/datos/paises.json) y el mapa de la web (web/vendor/mundo.js).

Se ejecuta una sola vez, o cuando se quiera rehacer el catálogo: el resultado se versiona y ni la
actualización diaria ni la web lo vuelven a descargar.

    python herramientas/generar_paises.py

Fuentes, todas abiertas:
- Códigos ISO 3166 y nombres en español e inglés: paquete i18n-iso-countries (MIT).
- Regiones y subregiones en español: clasificación M49 de la División de Estadística de la ONU.
- Geometría: world-atlas (ISC), a partir de Natural Earth (dominio público). La web dibuja la versión
  1:110m; los centroides salen de la 1:50m, que también tiene los microestados.
"""

import json
import re
import sys
import urllib.request
from html import unescape
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "concordia" / "datos" / "paises.json"
MAPA = RAIZ / "web" / "vendor" / "mundo.js"
UA = {"User-Agent": "concordia/0.1 (catálogo de países)"}

I18N = "https://cdn.jsdelivr.net/npm/i18n-iso-countries@7.14.0"
ATLAS = "https://cdn.jsdelivr.net/npm/world-atlas@2.0.2"
M49 = "https://unstats.un.org/unsd/methodology/m49/overview/"

# Estados que ya no existen y aparecen en las votaciones de la ONU. «sucesor» es el país del mapa
# actual donde se dibujan.
HISTORICOS = {
    "CSK": ("Checoslovaquia", "Czechoslovakia", "CZE", 49.8, 15.5),
    "DDR": ("República Democrática Alemana", "German Democratic Republic", "DEU", 52.0, 12.6),
    "YAR": ("Yemen del Norte", "Yemen Arab Republic", "YEM", 15.4, 44.2),
    "YMD": ("Yemen del Sur", "People's Democratic Republic of Yemen", "YEM", 13.2, 46.4),
    "YUG": ("Yugoslavia", "Yugoslavia", "SRB", 44.0, 20.9),
    "EAZ": ("Zanzíbar", "Zanzibar", "TZA", -6.1, 39.3),
}
# Microestados que no están en la geometría 1:50m.
CENTROIDES = {"TUV": (-8.52, 179.2)}
# Sin región en la clasificación M49.
REGIONES = {"TWN": ("Asia", "Asia oriental"), "XKK": ("Europa", "Europa meridional")}
# Geometrías sin código numérico en world-atlas.
SIN_CODIGO = {"Kosovo": "XKK", "Somaliland": "SOM", "N. Cyprus": "CYP"}
# Organismos con parlamento propio (el Parlamento Europeo): solo son origen de relaciones, nunca destino, y
# no tienen alias para que las reglas no los busquen en los títulos. Se dibujan como un punto, como los
# microestados (la Unión Europea, en Estrasburgo, sede del pleno). EUU es el código del Banco Mundial.
ORGANISMOS = {"EUU": ("EU", "Unión Europea", "European Union", "Europa", "Europa occidental", 48.6, 7.77)}

# Nombres en español más cortos o más habituales que los de la lista ISO.
NOMBRE_ES = {
    "USA": "Estados Unidos", "GBR": "Reino Unido", "RUS": "Rusia", "KOR": "Corea del Sur", "PRK": "Corea del Norte",
    "IRN": "Irán", "SYR": "Siria", "VEN": "Venezuela", "BOL": "Bolivia", "TZA": "Tanzania", "MDA": "Moldavia",
    "LAO": "Laos", "VNM": "Vietnam", "FSM": "Micronesia", "COD": "República Democrática del Congo",
    "COG": "República del Congo", "PSE": "Palestina", "VAT": "Santa Sede", "TWN": "Taiwán", "CZE": "Chequia",
    "MKD": "Macedonia del Norte", "SWZ": "Esuatini", "CIV": "Costa de Marfil", "BRN": "Brunéi", "CPV": "Cabo Verde",
    "TLS": "Timor Oriental", "MMR": "Myanmar", "NLD": "Países Bajos", "ARE": "Emiratos Árabes Unidos",
    "HKG": "Hong Kong", "MAC": "Macao", "FJI": "Fiyi", "XKK": "Kosovo",
    # Formas de España donde la ONU usa otra.
    "BLR": "Bielorrusia", "NRU": "Nauru", "NZL": "Nueva Zelanda", "TUR": "Turquía", "KEN": "Kenia", "RWA": "Ruanda",
    "BWA": "Botsuana", "LSO": "Lesoto", "DJI": "Yibuti", "SUR": "Surinam", "KAZ": "Kazajistán", "BHR": "Baréin",
    "BEN": "Benín", "TTO": "Trinidad y Tobago", "ROU": "Rumanía", "IRQ": "Irak", "BTN": "Bután", "MWI": "Malaui",
    "SAU": "Arabia Saudí", "FLK": "Islas Malvinas",
}
# Formas en inglés que usan los títulos de la ONU y de los parlamentos, además de las de la lista.
ALIAS_EN = {
    "USA": ["United States", "United States of America", "U.S.", "USA"],
    "GBR": ["United Kingdom", "Great Britain", "Britain", "U.K."],
    "RUS": ["Russia", "Russian Federation", "Soviet Union", "USSR"],
    "KOR": ["Republic of Korea", "South Korea"],
    "PRK": ["Democratic People's Republic of Korea", "North Korea", "DPRK"],
    "IRN": ["Iran", "Islamic Republic of Iran"],
    "SYR": ["Syria", "Syrian Arab Republic", "Syrian Golan"],
    "PSE": ["Palestine", "State of Palestine", "Palestinian", "Palestinians", "Occupied Palestinian Territory", "Gaza",
            "West Bank", "East Jerusalem"],
    "ISR": ["Israel", "Israeli"],
    "CHN": ["China", "People's Republic of China", "Chinese"],
    "TWN": ["Taiwan", "Republic of China"],
    "COD": ["Democratic Republic of the Congo", "DR Congo", "Zaire"],
    "COG": ["Republic of the Congo"],
    "MMR": ["Myanmar", "Burma"],
    "TUR": ["Turkey", "Türkiye", "Turkiye"],
    "CZE": ["Czech Republic", "Czechia"],
    "MKD": ["North Macedonia", "Macedonia", "Former Yugoslav Republic of Macedonia"],
    "SWZ": ["Eswatini", "Swaziland"],
    "CIV": ["Côte d'Ivoire", "Cote d'Ivoire", "Ivory Coast"],
    "VNM": ["Viet Nam", "Vietnam"],
    "LAO": ["Lao People's Democratic Republic", "Laos"],
    "BOL": ["Bolivia", "Plurinational State of Bolivia"],
    "VEN": ["Venezuela", "Bolivarian Republic of Venezuela"],
    "TZA": ["United Republic of Tanzania", "Tanzania"],
    "MDA": ["Republic of Moldova", "Moldova"],
    "UKR": ["Ukraine", "Ukrainian"],
    "AFG": ["Afghanistan", "Afghan"],
    "CUB": ["Cuba", "Cuban"],
    "VAT": ["Holy See", "Vatican"],
    "ESH": ["Western Sahara"],
    "CYP": ["Cyprus", "Cypriot"],
    "KHM": ["Cambodia", "Kampuchea"],
    "LKA": ["Sri Lanka", "Ceylon"],
    "YEM": ["Yemen"],
    "SRB": ["Serbia"],
    "BIH": ["Bosnia and Herzegovina", "Bosnia"],
    "ZAF": ["South Africa"],
    "NAM": ["Namibia", "South West Africa"],
    "ZWE": ["Zimbabwe", "Southern Rhodesia", "Rhodesia"],
}
ALIAS_ES = {
    "USA": ["Estados Unidos", "EEUU", "EE. UU.", "EE.UU."],
    "GBR": ["Reino Unido", "Gran Bretaña"],
    "RUS": ["Rusia", "Federación de Rusia", "Federación Rusa", "Unión Soviética"],
    "PSE": ["Palestina", "palestino", "palestina", "Gaza", "Cisjordania"],
    "KOR": ["Corea del Sur", "República de Corea"],
    "PRK": ["Corea del Norte"],
    "MAR": ["Marruecos", "marroquí"],
    "DZA": ["Argelia"],
    "UKR": ["Ucrania", "ucraniano", "ucraniana"],
    "ISR": ["Israel", "israelí"],
    "VEN": ["Venezuela"],
    "CUB": ["Cuba"],
    "CHN": ["China"],
    "ESH": ["Sáhara Occidental", "Sahara Occidental", "saharaui"],
    "DEU": ["Alemania"],
    "FRA": ["Francia"],
    "PRT": ["Portugal"],
    "AND": ["Andorra"],
}


def bajar(url):
    print("  descargando", url)
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
        return r.read()


def nombres(lang):
    d = json.loads(bajar(f"{I18N}/langs/{lang}.json"))["countries"]
    return {k: (v if isinstance(v, list) else [v]) for k, v in d.items()}


def tabla_m49(html, idioma):
    i = html.index(f'id = "downloadTable{idioma}"')
    tabla = html[i:html.index("</table>", i)]
    filas = []
    for tr in re.findall(r"<tr>(.*?)</tr>", tabla, re.S):
        celdas = [unescape(re.sub(r"<[^>]+>", "", c)).strip() for c in re.findall(r"<td>(.*?)</td>", tr, re.S)]
        if len(celdas) >= 12 and re.fullmatch(r"[A-Z]{3}", celdas[11]):
            filas.append(celdas)
    return {c[11]: c for c in filas}


# ------------------------------------------------------------------ TopoJSON

def arcos(topo):
    """Arcos decodificados a lon/lat (TopoJSON cuantizado y con deltas)."""
    t = topo.get("transform")
    salida = []
    for arco in topo["arcs"]:
        x = y = 0
        pts = []
        for p in arco:
            if t:
                x += p[0]
                y += p[1]
                pts.append((x * t["scale"][0] + t["translate"][0], y * t["scale"][1] + t["translate"][1]))
            else:
                pts.append(tuple(p))
        salida.append(pts)
    return salida


def anillo(indices, arcs):
    pts = []
    for i in indices:
        a = arcs[i] if i >= 0 else list(reversed(arcs[~i]))
        pts.extend(a if not pts else a[1:])
    return pts


def poligonos(geo, arcs):
    if geo["type"] == "Polygon":
        return [[anillo(r, arcs) for r in geo["arcs"]]]
    if geo["type"] == "MultiPolygon":
        return [[anillo(r, arcs) for r in p] for p in geo["arcs"]]
    return []


def area_centroide(ring):
    # Un anillo que cruza el antimeridiano (Rusia, Fiyi) se calcula con longitudes continuas.
    if max(x for x, _ in ring) - min(x for x, _ in ring) > 180:
        ring = [(x + 360 if x < 0 else x, y) for x, y in ring]
    a = cx = cy = 0.0
    for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1]):
        f = x0 * y1 - x1 * y0
        a += f
        cx += (x0 + x1) * f
        cy += (y0 + y1) * f
    if abs(a) < 1e-12:
        xs, ys = zip(*ring)
        return 0.0, (sum(xs) / len(xs), sum(ys) / len(ys))
    return abs(a) / 2, (cx / (3 * a), cy / (3 * a))


def centroides(topo, iso_de):
    arcs = arcos(topo)
    salida = {}
    for g in topo["objects"]["countries"]["geometries"]:
        iso = iso_de(g)
        if not iso:
            continue
        mejor = None
        for pol in poligonos(g, arcs):
            area, c = area_centroide(pol[0])
            if not mejor or area > mejor[0]:
                mejor = (area, c)
        if mejor and (iso not in salida or mejor[0] > salida[iso][0]):
            salida[iso] = mejor
    return {k: (round(v[1][1], 2), round((v[1][0] + 180) % 360 - 180, 2)) for k, v in salida.items()}


def main():
    codigos = json.loads(bajar(f"{I18N}/codes.json"))
    es, en = nombres("es"), nombres("en")
    html = bajar(M49).decode("utf-8", "replace")
    m49_es, m49_en = tabla_m49(html, "ES"), tabla_m49(html, "EN")
    num_a_iso3 = {c[2]: c[1] for c in codigos}

    def iso_de(g):
        if g.get("id") in num_a_iso3:
            return num_a_iso3[g["id"]]
        return SIN_CODIGO.get((g.get("properties") or {}).get("name"))

    t50 = json.loads(bajar(f"{ATLAS}/countries-50m.json"))
    t110 = json.loads(bajar(f"{ATLAS}/countries-110m.json"))
    cent = centroides(t50, iso_de)
    en_mapa = {iso_de(g) for g in t110["objects"]["countries"]["geometries"]} - {None}

    paises = []
    for iso2, iso3, num, _ in codigos:
        if iso3 == "ATA":
            continue
        m = m49_es.get(iso3)
        nombre_es = NOMBRE_ES.get(iso3) or (m[8] if m else None) or es.get(iso2, [iso3])[0]
        alias_en = list(dict.fromkeys(ALIAS_EN.get(iso3, []) + en.get(iso2, []) + ([m49_en[iso3][8]] if iso3 in m49_en else [])))
        alias_es = list(dict.fromkeys([nombre_es] + ALIAS_ES.get(iso3, []) + es.get(iso2, []) + ([m[8]] if m else [])))
        lat, lon = cent.get(iso3) or CENTROIDES.get(iso3) or (None, None)
        region, subregion = REGIONES.get(iso3) or ((m[3], m[7] or m[5]) if m else (None, None))
        paises.append({
            "iso3": iso3, "iso2": iso2, "num": num, "nombre": nombre_es, "nombre_en": en.get(iso2, [iso3])[0],
            "region": region, "subregion": subregion,
            "lat": lat, "lon": lon, "sucesor": None, "en_mapa": int(iso3 in en_mapa),
            "alias_en": alias_en, "alias_es": alias_es,
        })
    regiones = {p["iso3"]: (p["region"], p["subregion"]) for p in paises}
    for iso3, (nes, nen, suc, lat, lon) in HISTORICOS.items():
        reg = regiones.get(suc or "SRB", (None, None))
        c = cent.get(iso3)
        paises.append({
            "iso3": iso3, "iso2": None, "num": None, "nombre": nes, "nombre_en": nen, "region": reg[0], "subregion": reg[1],
            "lat": c[0] if c else lat, "lon": c[1] if c else lon, "sucesor": suc, "en_mapa": int(iso3 in en_mapa),
            "alias_en": [nen], "alias_es": [nes],
        })
    for iso3, (iso2, nes, nen, reg, subreg, lat, lon) in ORGANISMOS.items():
        paises.append({
            "iso3": iso3, "iso2": iso2, "num": None, "nombre": nes, "nombre_en": nen, "region": reg, "subregion": subreg,
            "lat": lat, "lon": lon, "sucesor": None, "en_mapa": 0, "organismo": 1, "alias_en": [], "alias_es": [],
        })
    faltan = [p["iso3"] for p in paises if p["lat"] is None]
    if faltan:
        print("  sin centroide (no se dibujarán flechas):", ", ".join(faltan))
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(json.dumps(paises, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")
    print(f"{SALIDA}: {len(paises)} países y territorios")

    # Mapa de la web: 1:110m sin la Antártida, con el código ISO3 como identificador.
    geos = []
    for g in t110["objects"]["countries"]["geometries"]:
        iso = iso_de(g)
        if iso == "ATA" or not iso:
            continue
        geos.append({"type": g["type"], "arcs": g["arcs"], "id": iso})
    t110["objects"]["countries"]["geometries"] = geos
    t110["objects"].pop("land", None)
    MAPA.write_text(
        "// Generado por herramientas/generar_paises.py. world-atlas 2.0.2 (ISC), datos de Natural Earth (dominio público).\n"
        f"window.MUNDO_TOPO = {json.dumps(t110, separators=(',', ':'))};\n", encoding="utf-8")
    print(f"{MAPA}: {MAPA.stat().st_size / 1e3:.0f} kB")


if __name__ == "__main__":
    sys.exit(main())
