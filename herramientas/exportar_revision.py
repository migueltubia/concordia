"""Deja en data/llm/pendientes/revision/ fichas IA ya hechas para que otro modelo o agente las revise.

- rel_NN.jsonl: asuntos de exterior o defensa sin ningún país; se piden solo las relaciones (instrucciones_relaciones).
- fichas_NN.jsonl: fichas con confianza por debajo de 0,5; se piden enteras otra vez (instrucciones_fichas).

Las respuestas se importan con `python -m concordia fichas-importar <ficheros> --modelo <modelo>`.
Uso: python herramientas/exportar_revision.py [--tam-rel 700] [--tam-fichas 400]
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from concordia import db  # noqa: E402
from concordia.llm.fichas_io import PENDIENTES_DIR, _item  # noqa: E402
from concordia.llm.prompt import instrucciones_fichas, instrucciones_relaciones  # noqa: E402

_BASE = """SELECT a.id, a.fuente, a.titulo, a.tipo, a.fecha, a.codigo, a.extra, fi.resumen, fi.tema_principal, fi.confianza,
              (SELECT v.texto FROM votacion v WHERE v.asunto_id=a.id AND v.decisiva=1 LIMIT 1) AS votado
           FROM asunto a JOIN ficha fi ON fi.asunto_id=a.id
           WHERE fi.origen LIKE 'deepseek:%' AND a.fuente <> 'esp' AND {cond} ORDER BY a.fecha DESC"""


def _trozos(lista, tam, prefijo, carpeta):
    for x in lista:  # menos texto por lote: la cámara va implícita en el país («etiqueta» no: a veces es lo único útil)
        x.pop("camara", None)
    for viejo in carpeta.glob(f"{prefijo}_*.jsonl"):
        viejo.unlink()
    for n, i in enumerate(range(0, len(lista), tam), 1):
        (carpeta / f"{prefijo}_{n:02d}.jsonl").write_text(
            "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in lista[i:i + tam]), encoding="utf-8")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--tam-rel", type=int, default=700)
    p.add_argument("--tam-fichas", type=int, default=400)
    a = p.parse_args()
    carpeta = PENDIENTES_DIR / "revision"
    carpeta.mkdir(parents=True, exist_ok=True)
    con = db.connect()
    rel = []
    for r in con.execute(_BASE.format(cond="fi.tema_principal IN ('EXT', 'DEF') AND fi.relaciones = '[]' AND fi.confianza >= 0.5")):
        it = _item(r, r["fuente"])
        it["resumen"] = r["resumen"]
        rel.append(it)
    fichas = []
    for r in con.execute(_BASE.format(cond="fi.confianza < 0.5")):
        it = _item(r, r["fuente"])
        it["resumen_anterior"] = r["resumen"]
        fichas.append(it)
    _trozos(rel, a.tam_rel, "rel", carpeta)
    _trozos(fichas, a.tam_fichas, "fichas", carpeta)
    (carpeta / "INSTRUCCIONES_rel.md").write_text(instrucciones_relaciones(), encoding="utf-8")
    (carpeta / "INSTRUCCIONES_fichas.md").write_text(
        instrucciones_fichas() + "\n\nCada asunto trae en «resumen_anterior» la ficha que hizo otro modelo con poca confianza: "
        "úsala solo como pista, no la copies, y no describas el título.", encoding="utf-8")
    print(f"{len(rel)} asuntos para relaciones y {len(fichas)} fichas para rehacer en {carpeta}")


if __name__ == "__main__":
    main()
