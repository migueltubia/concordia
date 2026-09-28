"""Prueba un conector sin tocar la base de trabajo: lo que habría guardado y algunas comprobaciones."""

from collections import Counter

from . import db
from .fuentes import FUENTES, modulo
from .fuentes.modelo import SENTIDOS
from .recoger import Contexto


def probar(codigo, desde=None, log=print):
    if codigo not in FUENTES:
        log(f"No existe la fuente {codigo}. Hay: {', '.join(FUENTES)}")
        return False
    con = db.connect(":memory:")
    db.init(con)
    ctx = Contexto(con, FUENTES[codigo], log=log, desde=desde, simular=True)
    modulo(codigo).recoger(ctx)
    asuntos = [a for lote in ctx.recogido for a in lote[0]]
    votaciones = [v for lote in ctx.recogido for v in lote[1]]
    ids = Counter(v.id for v in votaciones)
    repetidas = [i for i, n in ids.items() if n > 1]
    ids_asunto = {a.id for a in asuntos}
    huerfanas = [v.id for v in votaciones if v.asunto_id not in ids_asunto]
    malos = [v.id for v in votaciones if v.votos and any(s not in SENTIDOS for *_, s in v.votos)]
    log(f"{len(votaciones)} votaciones, {len(asuntos)} asuntos")
    log(f"Tipos de votación: {dict(Counter(v.tipo for v in votaciones))}")
    log(f"Tipos de asunto: {dict(Counter(a.tipo for a in asuntos))}")
    log(f"Con voto nominal: {sum(1 for v in votaciones if v.votos)}; con voto por partido: {sum(1 for v in votaciones if v.por_partido)}")
    for v in votaciones[:3]:
        log(f"  {v.fecha} {v.id} [{v.tipo}] {v.texto or ''} -> {v.resultado} ({v.a_favor}-{v.en_contra})")
    for a in asuntos[:3]:
        log(f"  {a.id} [{a.tipo}] {a.titulo[:100]}")
    if repetidas or huerfanas or malos:
        log(f"! repetidas {len(repetidas)}, sin asunto {len(huerfanas)}, sentidos desconocidos {len(malos)}")
        return False
    return True
