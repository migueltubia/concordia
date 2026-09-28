"""Modelo común que devuelven los conectores: asuntos y votaciones ya normalizados.

Guardarlos, calcular totales, resultados, voto por partido, votación decisiva, fichas por reglas y
relaciones entre países es común a todas las fuentes (cargar.py y procesar.py).
"""

from dataclasses import dataclass, field

SENTIDOS = ("si", "no", "abstencion", "no_vota")


@dataclass
class Fuente:
    codigo: str          # carpeta en data/bd/ y web/datos/: «usa», «gbr», «onu»...
    pais: str | None     # ISO3 del país (None en organismos internacionales)
    nombre: str
    corto: str
    tipo: str            # parlamento | organismo
    detalle: str         # nominal | grupo | totales | estado (catalogos.DETALLES)
    web: str
    licencia: str
    desde: int           # primer año que se recoge
    idioma: str = "en"   # idioma de los títulos (para las reglas: en | es | otro)
    camaras: dict = field(default_factory=dict)   # código -> (nombre, corto, escaños)
    partidos: dict = field(default_factory=dict)  # código -> (nombre, siglas, color)
    notas: str = ""
    activa: bool = True
    decisiva_propia: bool = False  # el conector marca la votación decisiva de cada asunto (no se calcula)


@dataclass
class Asunto:
    id: str
    titulo: str
    tipo: str = "otro"          # catalogos.TIPOS_ASUNTO
    fecha: str | None = None    # fecha de presentación o de la primera votación
    codigo: str | None = None   # «H.R. 815», «A/RES/77/7», «druk 123»...
    autor: str | None = None
    url: str | None = None
    extra: dict | None = None


@dataclass
class Votacion:
    id: str
    fecha: str
    asunto_id: str
    camara: str | None = None
    numero: int | None = None
    texto: str | None = None    # qué se vota dentro del asunto («On Passage», «Enmienda 3»...)
    tipo: str = "otra"          # catalogos.TIPOS_VOTACION
    a_favor: int | None = None
    en_contra: int | None = None
    abstenciones: int | None = None
    no_votan: int | None = None
    mayoria: str | None = None
    resultado: str | None = None  # aprobada | rechazada (si la fuente lo publica)
    importante: int = 0
    url: str | None = None
    decisiva: int | None = None   # si la fuente ya sabe cuál es la votación que decide el asunto
    # Voto nominal: [(id del miembro, nombre, partido, sentido)] con sentido en SENTIDOS.
    votos: list | None = None
    # Solo si no hay voto nominal: {partido: (sí, no, abstención, no vota)}.
    por_partido: dict | None = None
