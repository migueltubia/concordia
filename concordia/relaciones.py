"""Reglas sin IA: tema provisional y relaciones con otros países a partir del título.

Sirven hasta que llega la ficha de la IA (y siempre, si no hay clave): la IA las sustituye porque lee el
asunto entero y sabe, por ejemplo, que una resolución sobre la «integridad territorial de Ucrania» va
contra Rusia aunque el título no la nombre. Las reglas solo dicen lo que el título dice.

Orientación: +1 positiva (acuerdo, ayuda, cooperación, apoyo, reconocimiento), -1 negativa (sanciones,
condena, restricciones, conflicto) y 0 neutra (se nombra al país sin orientación clara).
"""

import re

from . import paises
from .catalogos import TEMAS_ONU

# ------------------------------------------------------------------ tema provisional

TEMA_EN = [
    ("PRE", r"appropriation|budget|continuing resolution|debt limit|rescission|supply and appropriation|estimates day|financing of the united nations|scale of assessments|programme budget"),
    ("FIS", r"\btax|revenue|finance \(no|finance bill|customs duty|\bduties\b"),
    ("DEF", r"defen[cs]e|armed forces|military|nuclear weapon|nuclear-weapon|disarmament|arms (trade|race|control)|missile|chemical weapons|biological weapons|veterans|navy|army|nato|peacekeeping|war\b|outer space"),
    ("SEG", r"terror|police|crime|criminal|firearm|gun|border security|homeland|drug|narcotic|traffick|prison|cybercrime"),
    ("MIG", r"immigra|migra|asylum|refugee|visa|deport|border\b|displaced persons"),
    ("IGU", r"human rights|civil rights|discriminat|women|gender|racism|racial|equality|lgbt|same-sex|abortion|freedom of|torture|death penalty|indigenous|minorities|religious|apartheid|genocide|self-determination"),
    ("SAN", r"health|medic|hospital|drug pricing|vaccine|pandemic|covid|opioid|mental|disease|tobacco"),
    ("EDU", r"educat|school|student|universit|science|research"),
    ("PEN", r"pension|social security|retirement|medicare"),
    ("EMP", r"employ|labou?r|worker|wage|union|workplace|jobs"),
    ("VIV", r"housing|homeless|mortgage|tenant|rent\b|building safety"),
    ("ENE", r"energy|oil|gas\b|pipeline|nuclear power|electric|renewable|coal"),
    ("MED", r"climate|environment|pollution|water|ocean|sea\b|wildlife|conservation|biodiversity|emission|forest|desertification"),
    ("AGR", r"agricultur|farm|fisher|food|rural"),
    ("TRA", r"transport|highway|rail|aviation|airport|infrastructure|shipping|maritime"),
    ("DIG", r"digital|internet|cyber|data protection|telecom|artificial intelligence|online|broadband|information and communications"),
    ("JUS", r"court|judicia|judge|justice|legal|crimes against humanity|international law|extradition"),
    ("ECO", r"trade|tariff|bank|financial|econom|commerce|consumer|business|development|debt\b|investment|industr|competition"),
    ("TER", r"colonial|decoloni|non-self-governing|independence|territor|sovereignty|devolution|scotland|northern ireland|wales"),
    ("INS", r"election|electoral|ethics|impeach|nomination|speaker|standing orders|committee|privilege|parliament|congress\b|credentials|admission of|membership|secretary-general|recess|lobbying|standards"),
    ("CUL", r"cultur|sport|olympic|heritage|art\b|museum|broadcast|media"),
    ("SOC", r"child|famil|disabilit|poverty|older persons|ageing|welfare|benefit|youth"),
    ("EXT", r"sanction|foreign|diploma|embassy|international|united nations|treaty|agreement|alliance|cooperation|middle east|palestin|israel"),
]
TEMA_ES = [
    ("PRE", r"presupuest|techo de gasto|estabilidad presupuestaria|cr[eé]dito extraordinario"),
    ("FIS", r"impuest|tribut|fiscal|\biva\b|irpf"),
    ("DEF", r"defensa|fuerzas armadas|militar|otan|misi[oó]n"),
    ("SEG", r"terroris|polic|guardia civil|seguridad ciudadana|crimen|narcotr"),
    ("MIG", r"inmigra|migra|asilo|refugiad|extranjer"),
    ("IGU", r"derechos humanos|igualdad|violencia de g[eé]nero|mujer|lgtb|discrimina|memoria"),
    ("SAN", r"sanid|salud|sanitari|medicament|vacun"),
    ("EDU", r"educa|universi|escuel|becas|ciencia|investigaci[oó]n"),
    ("PEN", r"pensi|seguridad social"),
    ("EMP", r"emple|trabaj|laboral|salario"),
    ("VIV", r"vivienda|alquiler|desahuci"),
    ("ENE", r"energ|el[eé]ctric|gas\b|nuclear"),
    ("MED", r"clima|medio ambiente|agua|residuo|biodiversidad"),
    ("AGR", r"agr[ií]c|agrari|pesc|ganad|rural"),
    ("TRA", r"transport|ferrocarril|carretera|aeropuerto|puerto"),
    ("DIG", r"digital|ciberseg|inteligencia artificial|telecomunica|datos personales"),
    ("JUS", r"justicia|judicial|c[oó]digo penal|tribunal|extradici"),
    ("ECO", r"econ[oó]m|comercio|empresa|consum|banca|inversi"),
    ("INS", r"electoral|reglamento del congreso|transparencia|corrupci|investidura|comisi[oó]n de investigaci"),
    ("CUL", r"cultur|deport|patrimonio"),
    ("SOC", r"dependencia|discapacidad|infancia|pobreza|familia"),
    ("EXT", r"convenio|tratado|acuerdo internacional|exterior|uni[oó]n europea|embajad|cooperaci[oó]n internacional"),
]
TEMA_PL = [
    ("PRE", r"budżet"), ("FIS", r"podat|akcyz|vat\b"), ("DEF", r"obron|wojsk|zbroj|nato"), ("SEG", r"policj|bezpieczeństw|przestęp"),
    ("MIG", r"cudzoziem|migra|azyl|granic"), ("SAN", r"zdrow|lecz|medyc|szpital"), ("EDU", r"oświat|szkoł|nauk|uczel"),
    ("PEN", r"emerytur|rent|ubezpieczeń społecznych"), ("EMP", r"prac|wynagrodz"), ("VIV", r"mieszka|lokal"),
    ("ENE", r"energ|gaz|paliw|ropy"), ("MED", r"środowisk|klimat|wod|odpad"), ("AGR", r"rol|ryb|żywno"),
    ("TRA", r"transport|kolej|drog|lotnisk"), ("DIG", r"cyfrow|cyberbezp|telekomunik"), ("JUS", r"sąd|karn|prokurat"),
    ("ECO", r"gospodar|handl|przedsiębior|konsument|bank"), ("INS", r"wybor|trybunał|sejm|regulamin"),
    ("EXT", r"ratyfikac|umow|międzynarodow|unii europejskiej"), ("SOC", r"rodzin|dziec|niepełnospraw|świadcze"),
]
_REGLAS_TEMA = {k: [(c, re.compile(p, re.I)) for c, p in v] for k, v in (("en", TEMA_EN), ("es", TEMA_ES), ("otro", TEMA_PL))}


def tema(titulo, idioma="en", extra=None):
    """Tema provisional: el de la primera regla que casa (más específicas primero)."""
    temas_onu = (extra or {}).get("temas_voeten") or []
    if temas_onu:
        return TEMAS_ONU[temas_onu[0]][0]
    for codigo, patron in _REGLAS_TEMA.get(idioma, _REGLAS_TEMA["en"]):
        if patron.search(titulo or ""):
            return codigo
    return None


# ------------------------------------------------------------------ relaciones

NEG_EN = r"sanction|embargo|condemn|aggression|occupation|occupied|violation|terroris|hostile|countering|counter |combat|threat|accountab|genocide|annex|invasion|prohibit|restrict|ban on|boycott|designat|expel|malign|atrocit|repression|detention|war crimes|nuclear program"
POS_EN = r"assistance|\baid\b|cooperation|partnership|friendship|support|solidarity|reconstruction|recovery|agreement|treaty|free trade|alliance|relief|recognition|normalization|security supplemental|lend-lease|enhancement|peace process|protection of|admission of|reconciliation"
NEG_ES = r"sanci[oó]n|embargo|conden|agresi[oó]n|ocupaci[oó]n|violaci[oó]n|terroris|invasi[oó]n|anexi[oó]n|genocidio|represi[oó]n|ruptura|expuls|rechazo a|crímenes"
POS_ES = r"acuerdo|convenio|tratado|cooperaci[oó]n|ayuda|apoyo|solidaridad|reconocimiento|reconstrucci[oó]n|amistad|asociaci[oó]n|canje de notas|protocolo|adhesi[oó]n"

TIPO_POR_PALABRA = [
    ("sanciones", r"sanction|embargo|boycott|sanci[oó]n|restrict|ban on|prohibit|designat"),
    ("derechos", r"human rights|derechos humanos"),
    # «Invasión migratoria» no es un conflicto armado: cae en «migración», más abajo.
    ("conflicto", r"aggression|invasion|war\b|military action|armed|agresi[oó]n|invasi[oó]n(?! (?:in)?migratori)|guerra|annex|anexi"),
    ("seguridad", r"security assistance|security supplemental|defen[cs]e|military aid|alliance|nato|otan|defensa"),
    ("condena", r"condemn|conden|accountab|atrocit|genocide|genocidio|repression|represi"),
    ("tratado", r"agreement|treaty|convention|protocol|acuerdo|convenio|tratado|protocolo|canje de notas"),
    ("comercio", r"trade|tariff|investment|comercio|arancel|inversi"),
    ("ayuda", r"assistance|\baid\b|relief|reconstruction|recovery|ayuda|reconstrucci"),
    ("soberania", r"sovereignty|territorial integrity|self-determination|recognition|question of|soberan|integridad territorial|reconocimiento|autodeterminaci|libre determinaci"),
    ("migracion", r"refugee|asylum|\bvisas?\b|migra|refugiad|asilo|\bvisados?\b|menores no acompa"),
    ("cooperacion", r"cooperation|partnership|friendship|support|solidarity|cooperaci|apoyo|amistad|solidaridad"),
]
_TIPO = [(t, re.compile(p, re.I)) for t, p in TIPO_POR_PALABRA]

# Patrones de títulos de la ONU: (expresión, país que captura el grupo 1 u otro fijo, orientación, tipo).
# Van en orden: el primero que asigna un país gana. Los territorios ocupados de un país lo hacen víctima,
# no objeto de condena («Situation of human rights in the temporarily occupied territories of Ukraine»).
PATRONES_ONU = [
    (r"(?:temporarily )?occupied territor(?:y|ies) of (?:the )?(.+?)(?:$|,| including)", 1, "soberania"),
    (r"(?:refugees|displaced persons)(?: and refugees)? from (.+?)(?:$| and the)", 1, "migracion"),
    (r"situation of human rights in (?:the )?(.+?)(?:$|,| and )", -1, "derechos"),
    (r"human rights situation in (?:the )?(.+?)(?:$|,| and )", -1, "derechos"),
    (r"assistance to (?:the )?(.+?)(?:$|,| for )", 1, "ayuda"),
    (r"territorial integrity of (.+?)(?:$|:|,)", 1, "soberania"),
    (r"aggression against (.+?)(?:$|:|,)", 1, "conflicto"),
    (r"(?:peaceful settlement of )?(?:the )?question of (.+?)(?:$|:|,)", 1, "soberania"),
]


# Ocupaciones conocidas: cuando el título habla de territorios ocupados de X, de agresión contra X o de
# sus desplazados, el ocupante es la otra parte aunque el título no lo nombre. Contexto mínimo y conocido.
OCUPANTES = {
    "UKR": ("RUS", r"occupied|aggression|crimea|sevastopol|territorial integrity"),
    "GEO": ("RUS", r"abkhazia|south ossetia|tskhinvali"),
    "AZE": ("ARM", r"occupied"),
    "CYP": ("TUR", r"occupied|question of cyprus"),
}


# Conflictos conocidos: cuando el título nombra a la víctima en un contexto de guerra, ocupación o crímenes, la
# víctima es objeto de apoyo y el agresor, de condena, aunque el título diga «condena» o «invasión» y no nombre
# al agresor («Ukraine Invasion War Crimes Deterrence Act», «genocidio en Gaza», «abduction of children from
# Ukraine»). (víctima: (agresor, contexto, excepciones)). Las excepciones evitan leer al revés los títulos en
# los que la víctima es la otra parte («ataque de Hamás contra Israel»).
# Solo con palabras fuertes (invasión, ocupación, genocidio...): «la guerra en Ucrania» a secas no basta.
CONFLICTOS = {
    "UKR": ("RUS", r"occup|aggression|invasion|invad|war crimes|crimea|sevastopol|territorial integrity|abduct|deport|"
                   r"genocid|atrocit|annex|invasi[oó]n|agresi[oó]n|ocupaci[oó]n|ocupad|cr[ií]menes de guerra|deportaci|"
                   r"secuestr|anexi", None),
    "GEO": ("RUS", r"abkhazia|south ossetia|tskhinvali|abjasia|osetia|occup|ocupaci|ocupad", None),
    "PSE": ("ISR", r"genocid|ofensiva|offensive|bombard|bloqueo|blockade|asedio|siege|ocupaci|occup|ocupad|asentamientos|"
                   r"\bsettlements\b|colonos|masacre|massacre|cr[ií]menes de guerra|war crimes|anexi|annex|apartheid",
            r"hamas|ham[aá]s|hezbol|hizbul|yihad|jihad|terroris|antisemit|7 de octubre|october 7|against israel|"
            r"contra israel|attack on israel|ataques? (?:a|contra) israel|rehenes|hostages|self-defen|autodefensa|"
            r"derecho de israel|israel'?s right"),
}


_MIGRATORIO = re.compile(r"(?:in)?migratori|menores no acompa|refugiad|refugee|migrants?\b|migrantes", re.I)


def _tipo(texto):
    for t, p in _TIPO:
        if p.search(texto or ""):
            # Un acuerdo sobre flujos migratorios o una «invasión migratoria» son, ante todo, migración.
            return "migracion" if t in ("tratado", "conflicto") and _MIGRATORIO.search(texto) else t
    return "otro"


def _rel(iso3, orientacion, tipo, motivo):
    return {"pais": iso3, "orientacion": {1: "positiva", -1: "negativa", 0: "neutra"}[orientacion], "tipo": tipo,
            "motivo": motivo}


# Víctima y agresor: «invasión rusa de Ucrania», «aggression against Ukraine», «Russian aggression».
# Con los actos «sobre» algo (invasión, ocupación, genocidio...) lo que va detrás de «de» es la víctima
# («invasión de Ucrania»); con los actos «de» alguien (ofensiva, ataque, agresión), el autor («ofensiva de
# Israel», «ataques de Rusia contra Ucrania»). La guerra solo marca víctima con «en» o «contra».
_SOBRE = (r"(?:invasi[oó]n|ocupaci[oó]n|anexi[oó]n|bloqueo|asedio|genocidio|deportaci[oó]n|invasion|occupation|"
          r"annexation|blockade|siege|genocide|deportation)")
_DE = r"(?:agresi[oó]n|ataques?|bombardeos?|ofensiva|aggression|attacks?|bombing|bombardment|offensive)"
_GUERRA = r"(?:guerra|war)"
_ACTO = f"(?:{_SOBRE}|{_DE}|{_GUERRA})"
_ARTICULO = r"(?:la |el |los |the )?(?:state of |estado de |people of |pueblo de |pueblo )?"
VICTIMA = re.compile(rf"(?:{_SOBRE}(?:\s+\S+){{0,3}}?\s+(?:de|del|contra|a|al|en|sobre|of|against|on|in)"
                     rf"|(?:{_DE}|{_GUERRA})(?:\s+\S+){{0,3}}?\s+(?:contra|a|al|en|sobre|against|on|in))"
                     rf"\s+{_ARTICULO}$", re.I)
AGRESOR_DE = re.compile(_DE + r"\s+(?:de|del|of)\s+(?:la |el |the )?$", re.I)   # «ofensiva de Israel»
AGRESOR_ANTES = re.compile(_ACTO + r"\s+$", re.I)                     # «invasión rusa»: el gentilicio va detrás
# «Russian aggression»: el gentilicio va delante. «Armenian Genocide» es al revés: el genocidio de los armenios.
AGRESOR_DESPUES = re.compile(r"^\s+(?!genocid)" + _ACTO, re.I)
VICTIMA_DESPUES = re.compile(r"^\s+genocid", re.I)
# El agresor explícito va con «by», «por» o «por parte de».
POR_AGRESOR = re.compile(_ACTO + r"(?:\s+\S+){0,2}?\s+(?:by|por parte de|por)\s+(?:la |el |the )?$", re.I)
# «Russian aggression» sí; «Ukraine Invasion ... Act» no: delante del acto solo cuenta un gentilicio.
GENTILICIO_EN = re.compile(r"(?:ian|ean|ese|ish|i)$|^(?:Soviet|Cuban|Mexican|Venezuelan|Nicaraguan|Libyan|North Korean|"
                           r"South Korean|Afghan|Greek|U\.?S\.?A?\.?)$", re.I)
# Apoyo explícito justo delante del país («Standing with Israel against...», «solidaridad con el pueblo de...»):
# pesa más que las palabras negativas del resto de la frase, que suelen ir contra otro.
APOYO_ANTES = re.compile(r"(?:standing with|stand with|in support of|supporting|support for|solidarity with|"
                         r"apoyo a(?:l)?|solidaridad con)(?:\s+(?:the|people of|state of|la|el|pueblo|de|del|al))*\s+$", re.I)
# Hamás, la Yihad Islámica o Hezbolá no son el Estado de Palestina ni el Líbano: nombrar Gaza en esos títulos
# no es una relación con orientación hacia Palestina.
GRUPOS_ARMADOS = re.compile(r"ham[aá]s|yihad|jihad|hezbol|hizbul", re.I)


def _conflictos(detectados, t, salida, propios_origen):
    """Víctima y agresor de los conflictos conocidos (ver CONFLICTOS)."""
    nombrados = {iso3 for iso3, *_ in detectados}
    for victima, (agresor, contexto, excepto) in CONFLICTOS.items():
        if victima not in nombrados or victima in salida or victima in propios_origen:
            continue
        if not re.search(contexto, t) or (excepto and re.search(excepto, t)):
            continue
        tipo = _tipo(t)
        salida[victima] = _rel(victima, 1, tipo if tipo in ("derechos", "migracion", "soberania", "ayuda", "seguridad") else "conflicto",
                               "regla: víctima de un conflicto conocido")
        if agresor not in salida and agresor not in propios_origen:
            salida[agresor] = _rel(agresor, -1, tipo if tipo in ("sanciones", "condena", "derechos") else "conflicto",
                                   "regla: agresor en un conflicto conocido" + ("" if agresor in nombrados else " (el título no lo nombra)"))


def _orientacion_de(tramo, neg, pos):
    return -1 if neg.search(tramo) else 1 if pos.search(tramo) else 0


def _del_titulo(titulo, idioma="en", origen=None, es_onu=False, texto=None):
    """Relaciones con otros países que se deducen del título (y del texto de lo votado)."""
    if idioma not in ("en", "es"):
        return []
    completo = " ".join(x for x in (titulo, texto) if x)
    t = completo.lower()
    if re.search(r"designate the facility of the united states postal service|post office", t):
        return []  # nombre de una oficina de correos («... Vietnam Veterans Post Office»): no es política exterior
    salida = {}
    propios_origen = paises.propios(origen) if origen else set()
    encontrados = paises.detectar(completo, idioma, excluir=propios_origen, onu=es_onu, posiciones=True)
    if es_onu:
        m = re.search(r"embargo imposed by (?:the )?(.+?) against (.+?)(?:$|,)", completo, re.I)
        if m:
            for iso3, _ in paises.detectar(m.group(1), onu=True):
                salida[iso3] = _rel(iso3, -1, "sanciones", "regla: embargo impuesto por")
            for iso3, _ in paises.detectar(m.group(2), onu=True):
                salida[iso3] = _rel(iso3, 1, "sanciones", "regla: embargo contra")
        if re.search(r"israeli (practices|settlements|occupation)|occupied (palestinian|syrian|arab) territor|syrian golan|jerusalem", t):
            salida["ISR"] = _rel("ISR", -1, "condena", "regla: prácticas de Israel en territorios ocupados")
            for iso3, _ in paises.detectar(completo, onu=True):
                if iso3 in ("PSE", "SYR", "LBN") and iso3 not in salida:
                    salida[iso3] = _rel(iso3, 1, "soberania", "regla: territorios ocupados")
            if "palestin" in t and "PSE" not in salida:
                salida["PSE"] = _rel("PSE", 1, "soberania", "regla: pueblo palestino")
    _conflictos(encontrados, t, salida, propios_origen)
    if es_onu:
        for patron, orientacion, tipo in PATRONES_ONU:
            for m in re.finditer(patron, completo, re.I):
                for iso3, _ in paises.detectar(m.group(1), onu=True):
                    salida.setdefault(iso3, _rel(iso3, orientacion, tipo, f"regla: «{m.group(0).strip()[:60]}»"))
        for victima, (ocupante, patron) in OCUPANTES.items():
            if victima in salida and salida[victima]["orientacion"] == "positiva" and re.search(patron, t) and ocupante not in salida:
                salida[ocupante] = _rel(ocupante, -1, "conflicto", "regla: ocupación o agresión (contexto conocido)")
    neg = re.compile(NEG_EN if idioma == "en" else NEG_ES, re.I)
    pos = re.compile(POS_EN if idioma == "en" else POS_ES, re.I)
    general = _orientacion_de(completo, neg, pos)
    for iso3, forma, inicio in encontrados:
        if iso3 in salida:
            continue
        if es_onu and re.search(r"cooperation between the united nations and", t) and not re.search(
                r"cooperation between the united nations and (?:the )?" + re.escape(forma.lower()), t):
            continue  # «Cooperación entre la ONU y la Organización X»: el país que aparezca va de paso
        antes, despues = completo[:inicio], completo[inicio + len(forma):]
        # Solo con el nombre del país o de su pueblo: «support for Chinese activists» no es apoyo a China.
        nombre_propio = (forma[:1].isupper() and not GENTILICIO_EN.search(forma)) or forma.lower().startswith("pueblo")
        if APOYO_ANTES.search(antes) and nombre_propio:
            salida[iso3] = _rel(iso3, 1, "cooperacion", f"regla: apoyo a «{forma}»")
            continue
        if iso3 in ("PSE", "LBN") and GRUPOS_ARMADOS.search(completo):
            salida[iso3] = _rel(iso3, 0, "otro", f"regla: nombra «{forma}» en un asunto sobre un grupo armado")
            continue
        if (VICTIMA.search(antes) and not POR_AGRESOR.search(antes)) or (VICTIMA_DESPUES.search(despues) and GENTILICIO_EN.search(forma)):
            salida[iso3] = _rel(iso3, 1, "conflicto", f"regla: víctima de «{forma}»")
            continue
        if (AGRESOR_ANTES.search(antes) or (AGRESOR_DESPUES.search(despues) and GENTILICIO_EN.search(forma))
                or POR_AGRESOR.search(antes) or AGRESOR_DE.search(antes)):
            salida[iso3] = _rel(iso3, -1, "conflicto", f"regla: agresor «{forma}»")
            continue
        # Orientación del tramo de la frase donde aparece el país (separado por «;», «:» o « - »); si ese
        # tramo no dice nada y solo hay un país, la de todo el título.
        tramos = re.split(r"[;:]| - | — ", completo)
        pos_acum, tramo = 0, completo
        for tr in tramos:
            if pos_acum <= inicio < pos_acum + len(tr) + 1:
                tramo = tr
                break
            pos_acum += len(tr) + 1
        orientacion = _orientacion_de(tramo, neg, pos)
        if not orientacion and len(encontrados) == 1:
            orientacion = general
        salida[iso3] = _rel(iso3, orientacion, _tipo(tramo if orientacion else "") if orientacion else "otro",
                            f"regla: nombra «{forma}»")
    if origen:
        for propio in paises.propios(origen):
            salida.pop(propio, None)
    return list(salida.values())[:8]


def relaciones(titulo, idioma="en", origen=None, es_onu=False, texto=None, paises_fuente=()):
    """Relaciones del título y, detrás, las de los países que la propia fuente asocia al asunto (HowTheyVote en el
    Parlamento Europeo). Esos entran aunque el título no los nombre o los nombre de forma ambigua («Georgia»), como
    neutros: la fuente dice de qué país trata el asunto, no en qué sentido. El título manda si también lo nombra."""
    salida = _del_titulo(titulo, idioma, origen, es_onu, texto)
    vistos = {r["pais"] for r in salida} | (paises.propios(origen) if origen else set())
    for iso3 in paises_fuente or ():
        if iso3 in vistos or iso3 not in paises.por_iso3() or paises.solo_origen(iso3):
            continue  # ya está, es el propio país, o no es un Estado del catálogo («EUR», la Antártida)
        vistos.add(iso3)
        salida.append(_rel(iso3, 0, "otro", "regla: la fuente lo asocia al asunto; el título no dice en qué sentido"))
    return salida[:8]
