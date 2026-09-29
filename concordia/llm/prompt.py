"""Prompt, esquema de salida y validación de las fichas IA.

El LLM describe, clasifica y dice qué países son objeto de cada asunto y en qué sentido. Nunca recibe
ni decide resultados o votos: eso sale de los datos.
"""

import json

from .. import paises
from ..catalogos import CODIGOS_TEMA, TEMAS, TIPOS_RELACION

VERSION_PROMPT = "fichas-mundo-v2"
ORIENTACIONES = ["positiva", "negativa", "neutra"]

_TEMAS_TXT = "\n".join(f"- {c}: {n} (p. ej. {s})" for c, n, s in TEMAS)
_TIPOS_TXT = "\n".join(f"- {k}: {v}" for k, v in TIPOS_RELACION.items())

REGLAS_RELACIONES = f"""Relaciones con otros países («relaciones»): los Estados que son OBJETO del asunto, con la
orientación que el asunto tiene hacia cada uno si sale adelante.
- «pais»: código ISO 3166-1 alfa-3 (USA, RUS, UKR, ISR, PSE, CHN, TWN, CUB, IRN...). Para Estados que ya no
  existen: SUN no, usa RUS para la URSS; YUG Yugoslavia, CSK Checoslovaquia, DDR RDA.
- «orientacion»: «positiva» si lo favorece, lo apoya, coopera con él, le da ayuda, firma o ratifica un tratado
  con él, lo reconoce o le levanta sanciones; «negativa» si lo sanciona, lo condena, lo critica, lo acusa,
  restringe el comercio o la entrada de sus nacionales, autoriza o prepara una acción hostil o militar
  contra él o denuncia sus violaciones de derechos; «neutra» si es objeto del asunto sin un sentido claro.
- «tipo», de esta lista cerrada:
{_TIPOS_TXT}
- «motivo»: 3 a 10 palabras que expliquen la orientación.
- No incluyas el país de la cámara que vota. En la ONU, sí cualquier Estado que sea objeto de la resolución.
- No incluyas países que solo se nombran de paso (la ciudad donde se firmó un convenio, una conferencia) ni
  organizaciones internacionales. Si nada encaja, lista vacía.
- Si el asunto trae «paises_fuente» (los países que la fuente de los datos asocia al asunto), tómalos como pista:
  incluye con su orientación los que sean objeto del asunto aunque el título no los nombre (China en una
  resolución sobre Hong Kong); si no ves el sentido, «neutra».
- En la Asamblea General de la ONU, la orientación es la de la resolución: «Situación de los derechos humanos
  en X» es negativa para X; «Necesidad de poner fin al embargo impuesto por los Estados Unidos contra Cuba»
  es negativa para USA y positiva para CUB; «Integridad territorial de Ucrania» es positiva para UKR y
  negativa para RUS; las prácticas israelíes en los territorios ocupados, negativa para ISR y positiva para
  PSE. Usa el conocimiento general solo para saber a qué Estado se refiere algo, no para inventar contenido.
- En una ley de sanciones, el país sancionado es negativo; en una ley de ayuda militar o de seguridad, el país
  que la recibe es positivo; en un convenio para evitar la doble imposición, el otro país es positivo (tratado).
- A veces lo que se vota es la propuesta de la comisión de RECHAZAR mociones, proyectos o iniciativas («avslag på
  motioner», «Ablehnung», «Beschlussempfehlung: Ablehnung», «ikke vedtatt», «vedlegges protokollen», dictamen
  contrario). Entonces el asunto es ese rechazo: dilo en el resumen, y la orientación es la del rechazo, no la de
  lo rechazado (rechazar una moción que pide sancionar a X no es negativo para X; como mucho, neutra).
- Máximo 8 relaciones."""

SYSTEM = f"""Eres un analista neutral de política comparada y de relaciones internacionales. Recibes asuntos votados
en parlamentos nacionales y en la Asamblea General de la ONU: título oficial (a menudo en inglés, polaco u otra
lengua), país y cámara, fecha, tipo y a veces el texto de lo que se votó. Devuelves para cada uno una ficha en JSON.

Reglas:
1. «resumen»: 1 a 3 frases neutras en español de España: qué pide, cambia o declara el asunto y a quién afecta.
   Sin adjetivos valorativos, sin el lenguaje del preámbulo, sin opinar. En resoluciones y mociones sin fuerza de
   ley, di que «pide», «insta» o «declara». Si el título es poco informativo, dilo y baja la confianza.
2. Básate exclusivamente en el título y los metadatos. Puedes usar conocimiento general solo para interpretar
   siglas, nombres de leyes o contexto conocido, pero no inventes ni añadas ninguna información —cifras,
   artículos, medidas, nombres, fechas— que no se deduzca directamente del texto recibido.
3. No se te dan resultados ni votos y no debes mencionarlos ni suponerlos. No digas si se aprobó.
4. «tema_principal»: el del contenido que más cambia, no el del título. Como máximo dos «temas_secundarios».
   En el contexto de otro país, «Gobierno» es el de ese país.
5. «etiquetas»: 0 a 5 términos concretos en minúsculas y en español de España («sanciones a irán», «ayuda a ucrania»).
6. {REGLAS_RELACIONES}
7. «confianza» entre 0 y 1 sobre la clasificación.
8. Redacta en presente y en tercera persona («Establece…», «Condena…», «Insta al Gobierno a…»).

Temas (lista cerrada):
{_TEMAS_TXT}
"""

SYSTEM_RELACIONES = f"""Eres un analista neutral de relaciones internacionales. Recibes asuntos votados en un parlamento
nacional (título oficial, país de la cámara, fecha, tipo y un resumen ya hecho) y devuelves SOLO sus relaciones con
otros países, en JSON. Básate exclusivamente en los datos recibidos: no inventes ni añadas información que no se
deduzca directamente del título, el tipo o el resumen.

{REGLAS_RELACIONES}
"""

RELACION_SCHEMA = {
    "type": "object",
    "properties": {
        "pais": {"type": "string"},
        "orientacion": {"type": "string", "enum": ORIENTACIONES},
        "tipo": {"type": "string", "enum": list(TIPOS_RELACION)},
        "motivo": {"type": "string"},
    },
    "required": ["pais", "orientacion", "tipo", "motivo"],
}
FICHA_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "resumen": {"type": "string"},
        "tema_principal": {"type": "string", "enum": CODIGOS_TEMA},
        "temas_secundarios": {"type": "array", "items": {"type": "string", "enum": CODIGOS_TEMA}},
        "etiquetas": {"type": "array", "items": {"type": "string"}},
        "relaciones": {"type": "array", "items": RELACION_SCHEMA},
        "confianza": {"type": "number"},
    },
    "required": ["id", "resumen", "tema_principal", "temas_secundarios", "etiquetas", "relaciones", "confianza"],
}
EJEMPLO = {"fichas": [{
    "id": "usa:118:HR815", "resumen": "Aprueba créditos suplementarios de seguridad nacional con ayuda militar a "
    "Ucrania, Israel y Taiwán y ayuda humanitaria para Gaza.", "tema_principal": "DEF", "temas_secundarios": ["PRE", "EXT"],
    "etiquetas": ["ayuda a ucrania", "ayuda militar"], "relaciones": [
        {"pais": "UKR", "orientacion": "positiva", "tipo": "seguridad", "motivo": "ayuda militar frente a la invasión"},
        {"pais": "ISR", "orientacion": "positiva", "tipo": "seguridad", "motivo": "ayuda militar"},
        {"pais": "TWN", "orientacion": "positiva", "tipo": "seguridad", "motivo": "ayuda militar"},
        {"pais": "PSE", "orientacion": "positiva", "tipo": "ayuda", "motivo": "ayuda humanitaria en Gaza"}],
    "confianza": 0.8}]}


def validar_relaciones(rels, origen=None):
    validas = paises.por_iso3()
    salida, vistos = [], set()
    for r in rels or []:
        if not isinstance(r, dict):
            continue
        iso3 = str(r.get("pais") or "").strip().upper()
        if iso3 == "SUN":
            iso3 = "RUS"
        if iso3 not in validas or paises.solo_origen(iso3) or (origen and iso3 in paises.propios(origen)) or iso3 in vistos:
            continue
        vistos.add(iso3)
        orientacion = r.get("orientacion") if r.get("orientacion") in ORIENTACIONES else "neutra"
        tipo = r.get("tipo") if r.get("tipo") in TIPOS_RELACION else "otro"
        salida.append({"pais": iso3, "orientacion": orientacion, "tipo": tipo, "motivo": str(r.get("motivo") or "")[:120] or None})
    return salida[:8]


def validar(f, origen=None):
    """Valida y normaliza una ficha. Devuelve (ficha, errores)."""
    if not isinstance(f, dict):
        return None, ["no es un objeto"]
    errores = [f"falta {k}" for k in FICHA_SCHEMA["required"] if k not in f]
    if errores:
        return None, errores
    if f["tema_principal"] not in CODIGOS_TEMA:
        return None, [f"tema desconocido {f['tema_principal']}"]
    if not str(f.get("resumen") or "").strip():
        return None, ["resumen vacío"]
    f["temas_secundarios"] = list(dict.fromkeys(t for t in f.get("temas_secundarios") or []
                                                if t in CODIGOS_TEMA and t != f["tema_principal"]))[:2]
    f["etiquetas"] = [e for e in (str(x).strip().lower() for x in f.get("etiquetas") or []) if e][:5]
    f["relaciones"] = validar_relaciones(f.get("relaciones"), origen)
    try:
        f["confianza"] = max(0.0, min(1.0, float(f["confianza"])))
    except (TypeError, ValueError):
        f["confianza"] = 0.5
    return f, []


def instrucciones_fichas():
    return (SYSTEM + "\nFormato de salida: un objeto json con la clave «fichas», una lista con una ficha por asunto, en el "
            "mismo orden y con el mismo «id». Cada ficha sigue este esquema json:\n" + json.dumps(FICHA_SCHEMA, ensure_ascii=False)
            + "\nEjemplo de salida json: " + json.dumps(EJEMPLO, ensure_ascii=False))


def instrucciones_relaciones():
    return (SYSTEM_RELACIONES + "\nFormato de salida: un objeto json con la clave «fichas», una lista con un objeto "
            '{"id": ..., "relaciones": [...]} por asunto, en el mismo orden. Cada relación sigue este esquema json:\n'
            + json.dumps(RELACION_SCHEMA, ensure_ascii=False))
