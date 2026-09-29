"""Francia: scrutins publics de la Asamblea Nacional (datos abiertos oficiales, https://data.assemblee-nationale.fr).

La Asamblea publica por legislatura un ZIP con un JSON por scrutin public: fecha, qué se vota, resultado,
totales y el voto nominal de cada diputado dentro de su grupo parlamentario en esa votación. Se recogen la XV
(2017-2022, solo desde 2019), la XVI (2022-2024) y la XVII (desde julio de 2024). Los ZIP de las legislaturas
cerradas se descargan una vez; el de la abierta se vuelve a bajar como mucho una vez al día y solo se
convierten los scrutins nuevos (por número, con un pequeño margen). Si aparece una legislatura nueva
(disolución o elecciones), se detecta sola y la anterior se da por cerrada.

Solo hay voto registrado en los scrutins públicos: lo que se vota a mano alzada (la mayoría de las enmiendas y
casi todos los tratados, que van por el procedimiento simplificado) no aparece. El voto nominal lista a los
que votan y a los «non-votants» (presidente de sesión, miembros del Gobierno); los ausentes no se publican, así
que no se añaden. Los textos aprobados con el artículo 49.3 no tienen votación final: lo que se vota es la
moción de censura, que es un asunto aparte.

El título de cada scrutin dice qué se vota dentro de qué texto («l'amendement n° 12 de M. X à l'article 2 du
projet de loi relatif à … (première lecture)», «l'ensemble de la proposition de loi …»): el nombre del texto
se saca con expresiones regulares y agrupa todas sus votaciones (todas las lecturas) en un asunto por
legislatura; los nombres casi iguales (erratas) se juntan con el primero que aparece en la legislatura, así
que los ids no cambian de una recogida a otra. Mociones de censura y declaraciones del Gobierno son asuntos
propios. Desde marzo de 2026 cada scrutin trae su expediente (dossier législatif); para los textos anteriores
se busca por el título en los ficheros de expedientes. Sirve para el código y el enlace del asunto. Nombres de
diputados y siglas de los grupos: del fichero histórico de actores y órganos (AMO30). Los títulos están en
francés: la ficha la hace la IA.
"""

import difflib
import hashlib
import json
import re
import unicodedata
import zipfile
from collections import Counter
from datetime import date

from .modelo import Asunto, Fuente, Votacion

FUENTE = Fuente(
    codigo="fra", pais="FRA", nombre="Asamblea Nacional de Francia", corto="Francia", tipo="parlamento",
    detalle="nominal", web="https://www.assemblee-nationale.fr", desde=2019, idioma="otro",
    licencia="Licence Ouverte / Open Licence (Etalab), datos abiertos de la Asamblea Nacional",
    camaras={"fra-an": ("Asamblea Nacional", "Asamblea", 577)},
    # Código: las siglas del grupo en la fuente; colores de la propia Asamblea (algo más oscuros los muy claros).
    partidos={
        # XVII legislatura (desde 2024)
        "RN": ("Agrupación Nacional", "RN", "#313567"),
        "EPR": ("Juntos por la República", "EPR", "#7b4591"),
        "LFI-NFP": ("La Francia Insumisa (Nuevo Frente Popular)", "LFI", "#c00d0d"),
        "SOC": ("Socialistas y afines", "SOC", "#e27db0"),
        "DR": ("Derecha Republicana", "DR", "#6f9fd8"),
        "EcoS": ("Ecologistas y Sociales", "EcoS", "#77aa79"),
        "Dem": ("Demócratas (MoDem)", "Dem", "#f07e26"),
        "HOR": ("Horizontes e Independientes", "HOR", "#5bc0eb"),
        "LIOT": ("Libertades, Independientes, Ultramar y Territorios", "LIOT", "#e8b923"),
        "GDR": ("Izquierda Demócrata y Republicana", "GDR", "#830e21"),
        "UDR": ("Unión de las Derechas por la República", "UDR", "#3367a7"),
        "AD": ("A la Derecha", "AD", "#3367a7"),
        "NI": ("No inscritos", "NI", "#8d949a"),
        # XVI legislatura (2022-2024)
        "RE": ("Renacimiento", "RE", "#7b4591"),
        "LFI-NUPES": ("La Francia Insumisa (NUPES)", "LFI", "#c00d0d"),
        "GDR-NUPES": ("Izquierda Demócrata y Republicana (NUPES)", "GDR", "#830e21"),
        "Ecolo-NUPES": ("Ecologistas (NUPES)", "Ecolo", "#77aa79"),
        "LR": ("Los Republicanos", "LR", "#6f9fd8"),
        # XV legislatura (2017-2022)
        "LaREM": ("La República en Marcha", "LaREM", "#7b4591"),
        "FI": ("La Francia Insumisa", "FI", "#c00d0d"),
        "UDI-AGIR": ("UDI, Agir e Independientes", "UDI-A", "#94b7e1"),
        "UDI-I": ("UDI e Independientes", "UDI-I", "#94b7e1"),
        "Agir": ("Agir juntos", "Agir", "#c7c034"),
        "LT": ("Libertades y Territorios", "LT", "#e8b923"),
        "EDS": ("Ecología, Democracia, Solidaridad", "EDS", "#3a673e"),
    },
    notas="Scrutins públicos del pleno con voto nominal (los ausentes no se publican); lo votado a mano alzada, "
          "incluida la mayoría de los tratados, no tiene registro. Desde 2019.",
)

REPO = "https://data.assemblee-nationale.fr/static/openData/repository"
LEGISLATURAS = {15: "2017-06-27", 16: "2022-06-28", 17: "2024-07-18"}
CERRADAS = {15, 16}  # sus ficheros ya no cambian: se descargan una vez
# Nombre de los ficheros cuando no es el de siempre (los de la XV llevan el número romano).
SCRUTINS = {15: "Scrutins_XV.json.zip"}
DOSSIERS = {15: "Dossiers_Legislatifs_XV.json.zip"}
AMO = "amo/tous_acteurs_mandats_organes_xi_legislature/AMO30_tous_acteurs_tous_mandats_tous_organes_historique.json.zip"
MARGEN = 40   # scrutins ya vistos que se repasan en cada recogida, por si llegan tarde o se corrigen
LOTE = 300
SENTIDO = {"pours": "si", "pour": "si", "contres": "no", "contre": "no", "abstentions": "abstencion",
           "abstention": "abstencion", "nonVotants": "no_vota", "nonVotant": "no_vota"}
# Grupos que cambiaron de siglas sin dejar de ser el mismo (libelleAbrege -> código).
SIGLAS = {"MODEM": "Dem", "Agir ens": "Agir"}

# -------------------------------------------------------------- títulos: texto, lectura y qué se vota

_TEXTO = re.compile(r"\b((?:projet de loi|proposition (?:de loi|de r[ée]solution|europ[ée]enne|relative|visant|tendant|"
                    r"portant))\b.*)$", re.I)
_LECTURA = re.compile(
    r"\s*\(\s*((?:premi[èe]re|1[èe]re|deuxi[èe]me|seconde|troisi[èe]me|nouvelle) lecture|lecture d[ée]f\w*|"
    r"texte de la commis\w* (?:mixte )?pari\w*|(?:article|art\.) ?34-1 de la Co\w*|application de l'article [^)]*|"
    r"seconde délibération|article 58 du Règlement[^)]*)\s*\)\s*(.*)$", re.I)
# Lo que sigue al nombre de una ley de presupuestos: «… pour 2022 - Mission Culture».
_PARTE = re.compile(r"\s+[-–]\s+((?:Mission|Compte|Budget annexe|Articles non rattachés|Seconde partie|Première partie)"
                    r"\b.*)$")
_SENADO = re.compile(r",\s*(?:(?:adopt|modifi)\w* par le Sénat|après engagement de la procédure accélérée)\s*,?\s*",
                     re.I)
_TRATADO = re.compile(r"^projet de loi (?:organique )?autorisant (?:la ratification|l'approbation|l'adh[ée]sion)", re.I)
_TITRE = re.compile(rb'"titre":\s*"((?:[^"\\]|\\.)*)"')
_DOSSIER = re.compile(rb'"dossierRef":\s*"(DLR\w+)"')
_FECHA = re.compile(rb'"dateScrutin":\s*"(\d{4})-(\d{2})')
MESES = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre",
         "décembre")


def _limpio(t):
    t = unicodedata.normalize("NFC", t or "").replace("’", "'")
    return re.sub(r"\s+", " ", t).strip()


def clave(nombre):
    """Forma normalizada del nombre de un texto (sin tildes, mayúsculas ni comillas) para agrupar."""
    t = unicodedata.normalize("NFKD", nombre.lower())
    t = "".join(c for c in t if not unicodedata.combining(c)).replace("œ", "oe")
    t = re.sub(r"[«»\"“”]", "", t)
    t = re.sub(r"\bn\s*°\s*", "n°", t)
    t = re.sub(r"\s*-\s*", "-", t)
    return re.sub(r"[\s.;,:]+$", "", re.sub(r"\s+", " ", t))


def partes(titulo):
    """Separa el título de un scrutin en (texto, qué se vota, lectura, añadido).

    «l'amendement n° 12 de M. X à l'article 2 du projet de loi relatif à … (première lecture).» ->
    («projet de loi relatif à …», «l'amendement n° 12 de M. X à l'article 2», «première lecture», None).
    Las mociones de censura, las declaraciones del Gobierno y lo que no nombra un texto dan texto None.
    """
    t = _limpio(titulo).rstrip(" .")
    bajo = t.lower()
    if "motion de censure" in bajo[:30] or bajo.startswith("la déclaration"):
        return None, t, None, None
    m = _TEXTO.search(t)
    if not m:
        return None, t, None, None
    nombre, elemento = m.group(1), t[:m.start(1)]
    lectura = extra = None
    ml = _LECTURA.search(nombre)
    if ml:
        lectura = ml.group(1)[0].lower() + ml.group(1)[1:]
        extra = ml.group(2).strip(" -–.") or None
        if extra and _LECTURA.match(extra):  # «(seconde délibération) (première lecture)»
            extra = _LECTURA.match(extra).group(1)
        nombre = nombre[:ml.start()]
    mp = _PARTE.search(nombre)
    if mp:
        extra, nombre = extra or mp.group(1).rstrip(" ."), nombre[:mp.start()]
    if nombre.count(")") > nombre.count("("):  # «… (proposition de loi visant à …)»
        nombre = nombre[:nombre.rfind(")")]
    nombre = _SENADO.sub(" ", nombre)
    # Erratas de la fuente: «la proposition relative à …», «la proposition européenne …».
    nombre = re.sub(r"^proposition (?=relative|visant|tendant|portant)", "proposition de loi ", nombre, flags=re.I)
    nombre = re.sub(r"^proposition europ[ée]enne", "proposition de résolution européenne", nombre, flags=re.I)
    elemento = re.sub(r"\s*\(\s*$", "", elemento.strip())
    elemento = re.sub(r"\s*,?\s*\b(?:du|de la|de l'|des|de|au|à la|sur la|sur le|sur)$", "", elemento, flags=re.I)
    elemento = elemento.strip(" ,")
    return nombre.strip(" .,;"), elemento, lectura, extra


def tipo_asunto(nombre):
    n = nombre.lower()
    if _TRATADO.match(n):
        return "tratado"
    if n.startswith(("proposition de résolution", "proposition de resolution")):
        return "procedimiento" if "règlement de l'assemblée" in n else "resolucion"
    return "ley"


PROCEDIMIENTO = ("motion de rejet", "motion de renvoi", "motion d'ajournement", "motion référendaire", "motion tendant",
                 "demande de", "proposition de la conférence", "proposition du gouvernement", "prolonger la séance",
                 "rappel au règlement")


def tipo_votacion(elemento):
    """Qué es la votación dentro del asunto, por cómo empieza lo que se vota (con las erratas de la fuente)."""
    e = elemento.lower()
    if e in ("", "la", "le", "l'"):  # se vota el texto mismo («la proposition de résolution …»)
        return "final"
    if re.match(r"(?:l'|les |le )(?:sous-)?amen", e):
        return "enmienda"
    if any(k in e for k in PROCEDIMIENTO):
        return "procedimiento"
    if e.startswith("l'ensemble"):
        return "parcial" if "partie" in e else "final"
    # En un texto de artículo único, el voto del artículo vale por el del conjunto.
    if e.startswith("l'article unique"):
        return "final"
    if re.match(r"(?:l'|les )a?r?ticles?\b", e) or e.startswith((
            "la première partie", "la seconde partie", "la deuxième partie", "la troisième partie",
            "la quatrième partie", "les crédits", "l'annexe", "le rapport annexé", "l'état", "le titre", "l'intitulé",
            "la mission")):
        return "parcial"
    return "otra"


def _mayus(t):
    return t[:1].upper() + t[1:] if t else t


def _sin_articulo(t):
    """«La motion de censure déposée … .» -> «Motion de censure déposée …»."""
    return _mayus(re.sub(r"^(?:la |le |l')", "", t.rstrip(" ."), flags=re.I))


def _hash(t):
    return hashlib.sha1(t.encode()).hexdigest()[:10]


def _parecidas(a, b):
    """Dos nombres del mismo texto que solo se diferencian por una errata («syteme», «de travail»)."""
    if a.split()[:4] != b.split()[:4] or re.findall(r"\d+", a) != re.findall(r"\d+", b):
        return False
    s = difflib.SequenceMatcher(None, a, b)
    return s.quick_ratio() >= 0.95 and s.ratio() >= 0.95


def _fase(lectura):
    """Orden de la lectura: 1 la primera, 2 la segunda o tercera, 3 la nueva lectura o la comisión mixta, 4 la
    definitiva (None si no es una lectura: «seconde délibération», «article 34-1»…)."""
    t = (lectura or "").lower()
    if t.startswith(("premi", "1")):
        return 1
    if t.startswith(("deuxi", "seconde lecture", "troisi")):
        return 2
    if t.startswith("nouvelle") or "commis" in t:
        return 3
    return 4 if "lecture d" in t else None


class Indice:
    """Los textos de toda una legislatura, recorriendo los títulos por orden de número de scrutin.

    El primer nombre de cada grupo de nombres casi iguales da el id y el título del asunto, así que no cambian
    de una recogida a otra. Si un texto vuelve a primera lectura después de haber pasado de ella, es otro texto
    con el mismo nombre (las leyes de presupuestos rectificativas de un mismo año): se numera aparte. También se
    apuntan los expedientes que citan los scrutins de cada texto.
    """

    def __init__(self, z, numeros):
        self.canonica, self.nombre, self.dossiers, self.variantes = {}, {}, {}, {}
        self.ciclo, self.inicio, fase, vistas = {}, {}, {}, []
        for num, n in numeros:
            raw = z.read(n)
            m = _TITRE.search(raw)
            nombre, _, lectura, _ = partes(json.loads(b'"' + m.group(1) + b'"')) if m else (None,) * 4
            if not nombre:
                continue
            k = clave(nombre)
            c = self.canonica.get(k)
            if c is None:
                c = self.canonica[k] = next((v for v in vistas if _parecidas(k, v)), k)
                self.variantes.setdefault(c, []).append(k)
                if c == k:
                    vistas.append(k)
                    self.nombre[k] = nombre
            f = _fase(lectura)
            ciclo, maxima = fase.get(c, (1, 0))
            if f == 1 and maxima >= 2:
                ciclo, maxima = ciclo + 1, 0
                fecha = _FECHA.search(raw)
                self.inicio[(c, ciclo)] = (f"{MESES[int(fecha.group(2)) - 1]} {fecha.group(1).decode()}" if fecha
                                           else str(ciclo))
            fase[c] = (ciclo, max(maxima, f or 0))
            self.ciclo[num] = ciclo
            d = _DOSSIER.search(raw)
            if d:
                self.dossiers.setdefault((c, ciclo), Counter())[d.group(1).decode()] += 1

    def texto(self, numero, nombre):
        """-> (clave del asunto, nombre para el título, expediente citado, variantes del nombre)"""
        k = clave(nombre)
        c = self.canonica.get(k, k)
        ciclo = self.ciclo.get(numero, 1)
        cuenta = self.dossiers.get((c, ciclo))
        dossier = cuenta.most_common(1)[0][0] if cuenta else None
        titulo = self.nombre.get(c, nombre)
        if ciclo > 1:  # «… rectificative pour 2022 (novembre 2022)»
            return f"{c}#{ciclo}", f"{titulo} ({self.inicio[(c, ciclo)]})", dossier, []
        return c, titulo, dossier, self.variantes.get(c, [k])


# -------------------------------------------------------------- ficheros

def _romano(n):
    salida = ""
    for v, r in ((10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")):
        while n >= v:
            salida, n = salida + r, n - v
    return salida


def _zip_scrutins(ctx, leg, abierta):
    nombres = [SCRUTINS[leg]] if leg in SCRUTINS else ["Scrutins.json.zip", f"Scrutins_{_romano(leg)}.json.zip"]
    for i, nombre in enumerate(nombres):
        try:
            return ctx.cache(f"{REPO}/{leg}/loi/scrutins/{nombre}", f"scrutins_{leg}.zip",
                             caduca_horas=20 if abierta else None, timeout=300)
        except Exception:
            if i == len(nombres) - 1:
                raise


def _existe(ctx, leg):
    """¿Ha empezado ya la legislatura `leg`? (existe su ZIP de scrutins)."""
    try:
        _zip_scrutins(ctx, leg, True)
        return True
    except Exception:
        return False


def _lista(x):
    return x if isinstance(x, list) else [x] if x else []


class Actores:
    """Nombres de los diputados y siglas de los grupos (AMO30: histórico de todas las legislaturas)."""

    def __init__(self, ctx, leg):
        self.ctx, self.leg, self.refrescado = ctx, leg, False
        self._cargar(caduca_horas=24 * 7)

    def _cargar(self, caduca_horas):
        for leg in (self.leg, self.leg - 1):  # al empezar una legislatura puede no estar aún su AMO
            try:
                ruta = self.ctx.cache(f"{REPO}/{leg}/{AMO}", f"amo30_{leg}.zip", caduca_horas=caduca_horas, timeout=300)
                break
            except Exception:
                if leg == self.leg - 1:
                    raise
        self.nombres, self.grupos, self.mandatos, self.info = {}, {}, {}, {}
        with zipfile.ZipFile(ruta) as z:
            for n in z.namelist():
                if "/organe/" in n:
                    o = json.loads(z.read(n))["organe"]
                    if o.get("codeType") == "GP":
                        siglas = (o.get("libelleAbrege") or o.get("libelleAbrev") or o["uid"]).replace(" - ", "-").strip()
                        codigo = SIGLAS.get(siglas, siglas)
                        self.grupos[o["uid"]] = codigo
                        color = o.get("couleurAssociee")
                        self.info[codigo] = (o.get("libelle") or codigo, color if color and color.startswith("#") else None)
                elif "/acteur/" in n:
                    a = json.loads(z.read(n))["acteur"]
                    uid = a["uid"]["#text"] if isinstance(a["uid"], dict) else a["uid"]
                    ident = a["etatCivil"]["ident"]
                    self.nombres[uid] = f"{ident.get('prenom') or ''} {ident.get('nom') or ''}".strip()
                    for m in _lista((a.get("mandats") or {}).get("mandat")):
                        if m.get("typeOrgane") == "GP":
                            self.mandatos.setdefault(uid, []).append(
                                (m.get("dateDebut") or "", m.get("dateFin") or "9999", m["organes"]["organeRef"]))

    def completar(self, refs):
        """Si aparecen diputados que no están en la copia guardada, se vuelve a bajar (una vez por recogida)."""
        if not self.refrescado and any(r not in self.nombres for r in refs):
            self.refrescado = True
            self._cargar(caduca_horas=6)

    def grupo(self, organe, acteur, fecha):
        codigo = self.grupos.get(organe)
        if codigo is None:
            # Algunos scrutins traen el grupo vacío («PO0»): el de su mandato ese día.
            codigo = next((self.grupos[ref] for inicio, fin, ref in self.mandatos.get(acteur, [])
                           if inicio <= fecha <= fin and ref in self.grupos), "NI")
        if codigo not in FUENTE.partidos:  # grupo nuevo: con su nombre y color oficiales hasta que se añada
            nombre, color = self.info.get(codigo, (codigo, None))
            self.ctx.partido(codigo, nombre, codigo, color)
        return codigo


class Expedientes:
    """Expediente (dossier législatif) de un texto por su título, para los scrutins que no lo citan."""

    def __init__(self, ctx):
        self.ctx, self.titulos = ctx, {}

    def _cargar(self, leg):
        nombre = DOSSIERS.get(leg, "Dossiers_Legislatifs.json.zip")
        try:
            ruta = self.ctx.cache(f"{REPO}/{leg}/loi/dossiers_legislatifs/{nombre}", f"dossiers_{leg}.zip",
                                  caduca_horas=None if leg in CERRADAS else 24 * 30, timeout=300)
        except Exception as e:
            self.ctx.log(f"   ! sin expedientes de la legislatura {leg}: {e}")
            return {}
        titulos = {}
        with zipfile.ZipFile(ruta) as z:
            for n in z.namelist():
                if "/document/" not in n:
                    continue
                d = json.loads(z.read(n))["document"]
                for k in ("titrePrincipal", "titrePrincipalCourt"):
                    t = (d.get("titres") or {}).get(k)
                    if t and d.get("dossierRef"):
                        titulos.setdefault(clave(_SENADO.sub(" ", _limpio(t))), set()).add(d["dossierRef"])
        return titulos

    def buscar(self, leg, clave_texto):
        if leg not in self.titulos:
            self.titulos[leg] = self._cargar(leg)
        encontrados = self.titulos[leg].get(clave_texto) or set()
        return next(iter(encontrados)) if len(encontrados) == 1 else None  # si hay varios, mejor ninguno


def url_expediente(dossier):
    m = re.match(r"DLR5L(\d+)N", dossier or "")
    return f"https://www.assemblee-nationale.fr/dyn/{m.group(1)}/dossiers/{dossier}" if m else None


# -------------------------------------------------------------- scrutin -> asunto y votación

def convertir(s, leg, indice, actores, expedientes, asuntos):
    numero = int(s["numero"])
    fecha = s["dateScrutin"][:10]
    url = f"https://www.assemblee-nationale.fr/dyn/{leg}/scrutins/{numero}"
    titulo = _limpio(s.get("titre") or s["objet"].get("libelle"))
    nombre, elemento, lectura, extra = partes(titulo)
    dossier = url_a = None
    if nombre:
        c, nombre, dossier, variantes = indice.texto(numero, nombre)
        aid = f"fra:{leg}:{_hash(c)}"
        tipo_a, tipo_v, autor = tipo_asunto(nombre), tipo_votacion(elemento), None
        titulo_a = _mayus(nombre)
        if not dossier and aid not in asuntos:
            dossier = next(filter(None, (expedientes.buscar(leg, v) for v in variantes)), None)
        elemento = "" if elemento.lower() in ("la", "le", "l'") else elemento
        texto = " · ".join(x for x in (_mayus(elemento) or "Vote sur le texte", lectura, extra) if x)
    else:
        # Mociones de censura, declaraciones del Gobierno y lo que no nombra un texto: un asunto cada una.
        aid = f"fra:{leg}:v{numero}"
        bajo = titulo.lower()
        if "motion de censure" in bajo[:30]:
            tipo_a, tipo_v = "mocion", "final"
        elif bajo.startswith("la déclaration de politique générale"):
            tipo_a, tipo_v = "nombramiento", "final"   # cuestión de confianza (art. 49.1)
        elif bajo.startswith("la déclaration"):
            tipo_a, tipo_v = "resolucion", "final"     # declaración del Gobierno con voto (art. 50-1)
        else:
            tipo_a, tipo_v = "procedimiento", "procedimiento"
        titulo_a = texto = _sin_articulo(titulo)
        url_a = url  # no tienen expediente propio: su única página es la del scrutin
        autor = re.search(r"\bpar (.+)$", titulo.rstrip(" .")) if tipo_a == "mocion" else None
        autor = autor.group(1)[:200] if autor else None
    if aid not in asuntos:
        asuntos[aid] = Asunto(id=aid, titulo=titulo_a[:400], tipo=tipo_a, fecha=fecha, autor=autor, codigo=dossier,
                              url=url_expediente(dossier) or url_a, extra={"legislatura": leg})

    votos = []
    for g in _lista(s["ventilationVotes"]["organe"]["groupes"]["groupe"]):
        for posicion, lista in ((g.get("vote") or {}).get("decompteNominatif") or {}).items():
            for v in _lista((lista or {}).get("votant")):
                ref = v["acteurRef"]
                votos.append((f"fra:{ref}", actores.nombres.get(ref, ref), actores.grupo(g["organeRef"], ref, fecha),
                              SENTIDO.get(posicion, "no_vota")))
    d = s["syntheseVote"]["decompte"]
    si, no = int(d.get("pour") or 0), int(d.get("contre") or 0)
    sort = ((s.get("sort") or {}).get("code") or "").lower()
    resultado = ("aprobada" if sort.startswith("adopt") else "rechazada" if sort.startswith("rejet")
                 else "aprobada" if si > no else "rechazada")
    tipo_voto = s.get("typeVote") or {}
    return Votacion(
        id=f"fra:{leg}:{numero}", fecha=fecha, asunto_id=aid, camara="fra-an", numero=numero, texto=texto[:600],
        tipo=tipo_v, a_favor=si, en_contra=no, abstenciones=int(d.get("abstentions") or 0),
        no_votan=int(d.get("nonVotants") or 0) + int(d.get("nonVotantsVolontaires") or 0),
        mayoria=tipo_voto.get("typeMajorite"), resultado=resultado,
        # Scrutins solemnes (los grandes textos) y mociones de censura.
        importante=1 if tipo_voto.get("codeTypeVote") in ("SPS", "MOC") else 0,
        url=url, votos=votos)


def _refs(s):
    for g in _lista(s["ventilationVotes"]["organe"]["groupes"]["groupe"]):
        for lista in ((g.get("vote") or {}).get("decompteNominatif") or {}).values():
            for v in _lista((lista or {}).get("votant")):
                yield v["acteurRef"]


# -------------------------------------------------------------- recogida

def recoger(ctx):
    legs = dict(LEGISLATURAS)
    siguiente = max(legs) + 1
    while _existe(ctx, siguiente):  # legislatura nueva tras unas elecciones
        legs[siguiente] = None
        siguiente += 1
    actual = max(legs)
    cerradas = set(ctx.marca("cerradas", []))
    ultimos = ctx.marca("ultimo", {})
    desde = f"{ctx.desde}-01-01"
    actores, expedientes = None, Expedientes(ctx)
    for leg in sorted(legs):
        fin = legs.get(leg + 1) or date.today().isoformat()
        if (leg < actual and fin < desde) or (leg in cerradas and not ctx.completo):
            continue
        ruta = _zip_scrutins(ctx, leg, abierta=leg not in CERRADAS)
        with zipfile.ZipFile(ruta) as z:
            # Solo la Asamblea («VTANR»): el Congreso (VTCGR, las dos cámaras reunidas en Versalles) queda fuera.
            numeros = sorted((int(m.group(1)), n) for n in z.namelist() if (m := re.search(r"VTANR5L\d+V(\d+)\.json$", n)))
            previo = 0 if ctx.completo else int(ultimos.get(str(leg), 0))
            pendientes = [(num, n) for num, n in numeros if num > previo - MARGEN]
            ctx.log(f"   legislatura {leg}: {len(pendientes)} scrutins por revisar de {len(numeros)}")
            indice, hechas = (Indice(z, numeros) if pendientes else None), 0
            for i in range(0, len(pendientes), LOTE):
                scrutins = [json.loads(z.read(n))["scrutin"] for _, n in pendientes[i:i + LOTE]]
                scrutins = [s for s in scrutins if s["dateScrutin"][:10] >= desde]
                if not scrutins:
                    continue
                if actores is None:
                    actores = Actores(ctx, actual)
                actores.completar({r for s in scrutins for r in _refs(s)})
                asuntos = {}
                votaciones = [convertir(s, leg, indice, actores, expedientes, asuntos) for s in scrutins]
                ctx.guardar(list(asuntos.values()), votaciones)
                hechas += len(votaciones)
            if hechas:
                ctx.log(f"   legislatura {leg}: {hechas} votaciones")
        if numeros:
            ultimos[str(leg)] = max(numeros[-1][0], previo)
            ctx.poner_marca("ultimo", ultimos)
        if leg < actual:
            cerradas.add(leg)
            ctx.poner_marca("cerradas", sorted(cerradas))
