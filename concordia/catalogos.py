"""Catálogos cerrados: temas, tipos de asunto y de votación, y tipos de relación entre países.

Los 23 temas son los de Escrutinio con los mismos códigos (las fichas del Congreso se reutilizan tal
cual), redactados para cualquier país: «Gobierno» es el del país de la cámara.
"""

TEMAS = [
    ("VIV", "Vivienda y urbanismo", "alquiler, vivienda pública, desahucios, suelo, planeamiento"),
    ("EMP", "Empleo y relaciones laborales", "salario mínimo, jornada, sindicatos, desempleo, autónomos"),
    ("PEN", "Pensiones y seguridad social", "pensiones, cotizaciones, prestaciones, rentas mínimas"),
    ("FIS", "Fiscalidad", "impuestos sobre la renta, IVA, sociedades, aranceles como impuesto, fraude fiscal"),
    ("PRE", "Presupuestos y finanzas públicas", "presupuestos, deuda, techo de gasto, créditos extraordinarios"),
    ("ECO", "Economía, empresa y comercio", "banca, competencia, consumo, industria, comercio exterior, aranceles"),
    ("SAN", "Sanidad", "sanidad pública, medicamentos, salud mental, pandemias, aborto como prestación"),
    ("EDU", "Educación, universidades y ciencia", "leyes educativas, becas, universidades, investigación"),
    ("SOC", "Políticas sociales y familia", "dependencia, discapacidad, infancia, pobreza, mayores"),
    ("IGU", "Igualdad y derechos humanos", "derechos civiles, violencia de género, LGTBI, libertades, memoria"),
    ("MIG", "Inmigración y asilo", "fronteras, asilo, refugiados, visados, deportaciones"),
    ("JUS", "Justicia", "código penal, tribunales, amnistías, extradición, cooperación judicial"),
    ("SEG", "Seguridad e interior", "policía, terrorismo, crimen organizado, prisiones, armas"),
    ("DEF", "Defensa, desarme y conflictos", "fuerzas armadas, gasto militar, alianzas, desarme, armas nucleares, guerras"),
    ("EXT", "Política exterior y relaciones internacionales", "tratados, diplomacia, organismos internacionales, sanciones, cooperación"),
    ("TER", "Organización territorial y soberanía", "autonomías, federalismo, secesión, descolonización, territorios"),
    ("INS", "Instituciones y calidad democrática", "régimen electoral, transparencia, corrupción, reglamentos, nombramientos"),
    ("ENE", "Energía", "electricidad, renovables, nuclear civil, petróleo, gas"),
    ("MED", "Medio ambiente y clima", "cambio climático, agua, océanos, biodiversidad, residuos"),
    ("AGR", "Agricultura, pesca y mundo rural", "política agraria, pesca, alimentación, desarrollo rural"),
    ("TRA", "Transporte e infraestructuras", "ferrocarril, carreteras, aeropuertos, puertos, espacio"),
    ("DIG", "Digital y tecnología", "inteligencia artificial, ciberseguridad, datos, telecomunicaciones"),
    ("CUL", "Cultura, deporte y lenguas", "cultura, patrimonio, deporte, medios de comunicación, lenguas"),
]
CODIGOS_TEMA = [t[0] for t in TEMAS]
VERSION_TAXONOMIA = "temas-23-mundo-v1"

# Qué se vota. «ley» incluye las leyes de presupuestos y las resoluciones conjuntas con fuerza de ley.
TIPOS_ASUNTO = {
    "ley": "Ley o proyecto de ley",
    "resolucion": "Resolución o declaración",
    "mocion": "Moción",
    "tratado": "Tratado o convenio internacional",
    "nombramiento": "Nombramiento, elección o investidura",
    "procedimiento": "Procedimiento y organización de la cámara",
    "otro": "Otro",
}

# Qué votación es dentro del asunto.
TIPOS_VOTACION = {
    "final": "Votación final (conjunto, aprobación, resolución)",
    "enmienda": "Enmienda o voto particular",
    "parcial": "Votación separada de un párrafo o artículo",
    "procedimiento": "Procedimiento (trámite, orden del día, cierre del debate)",
    "nombramiento": "Nombramiento o elección",
    "otra": "Otra",
}

ORIENTACIONES = {1: "positiva", -1: "negativa", 0: "neutra"}
ORIENTACION_DE = {v: k for k, v in ORIENTACIONES.items()}

# Tipo de relación que establece un asunto con otro país (lista cerrada para el LLM y las reglas).
TIPOS_RELACION = {
    "sanciones": "Sanciones, embargo o restricciones",
    "condena": "Condena, crítica o denuncia",
    "conflicto": "Conflicto armado u operación militar",
    "seguridad": "Alianza, ayuda militar o de seguridad",
    "tratado": "Tratado, acuerdo o convenio",
    "cooperacion": "Cooperación, diálogo o apoyo político",
    "ayuda": "Ayuda humanitaria o al desarrollo",
    "comercio": "Comercio, inversiones o aranceles",
    "derechos": "Derechos humanos",
    "soberania": "Soberanía, territorio o reconocimiento",
    "migracion": "Migración, fronteras o visados",
    "otro": "Otro",
}

# Códigos de tema de los datos de Voeten para la Asamblea General de la ONU (tema provisional sin IA).
TEMAS_ONU = {
    "me": ("EXT", "Oriente Próximo"),
    "nu": ("DEF", "Armas nucleares"),
    "di": ("DEF", "Desarme"),
    "hr": ("IGU", "Derechos humanos"),
    "co": ("TER", "Colonialismo"),
    "ec": ("ECO", "Desarrollo económico"),
}

# Nivel de detalle del voto de una fuente (el mismo que en Escrutinio).
DETALLES = {
    "nominal": "Voto de cada legislador",
    "grupo": "Voto por grupo",
    "totales": "Totales",
    "estado": "Voto de cada Estado",
}
