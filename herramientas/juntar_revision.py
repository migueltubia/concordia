"""Comprueba las respuestas de data/llm/pendientes/revision/salida/ y las junta para importarlas.

Cada respuesta debe traer los mismos «id» que su lote, sin repetir. De las relaciones solo se guardan las que
encuentran algún país: las vacías dejarían el asunto como estaba. Escribe salida/_importar.jsonl; después:
  python -m concordia fichas-importar data/llm/pendientes/revision/salida/_importar.jsonl --modelo claude:claude-opus-5-5
Uso: python herramientas/juntar_revision.py [lotes...]   (sin lotes, todos los que tengan respuesta)
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path

CARPETA = Path(__file__).resolve().parent.parent / "data" / "llm" / "pendientes" / "revision"
SALIDA = CARPETA / "salida"
_ETIQUETAS = CARPETA / "_etiquetas.json"
_SIN_ETIQUETA = set(json.loads(_ETIQUETAS.read_text(encoding="utf-8"))) if _ETIQUETAS.exists() else set()
_RELLENO = re.compile(r"\bAfecta a\b|\b[Ee]l título\b|no permite (conocer|determinar)|\bpor tanto\b|en materia de|en el marco de")


def _leer(ruta):
    lineas = []
    for n, l in enumerate(ruta.read_text(encoding="utf-8").splitlines(), 1):
        if l.strip():
            try:
                lineas.append(json.loads(l))
            except json.JSONDecodeError as e:
                print(f"  ! {ruta.name}:{n}: {e}")
    return lineas


def main(lotes):
    rutas = [SALIDA / f"{x}.jsonl" for x in lotes] if lotes else sorted(SALIDA.glob("[rf]*_*.jsonl"))
    buenas, cuenta = [], Counter()
    for ruta in rutas:
        pedidos = [d["id"] for d in _leer(CARPETA / ruta.name)]
        resp = {d.get("id"): d for d in _leer(ruta)}
        faltan = [i for i in pedidos if i not in resp]
        sobran = [i for i in resp if i not in set(pedidos)]
        rel = ruta.name.startswith("rel_")
        con_pais = [d for d in resp.values() if d.get("id") in set(pedidos) and (not rel or d.get("relaciones"))]
        if re.fullmatch(r"fichas_\d+\.jsonl", ruta.name):
            # Los primeros lotes salieron sin «etiqueta»; los asuntos que la tenían se rehicieron en fichas_rN.
            con_pais = [d for d in con_pais if d["id"] not in _SIN_ETIQUETA]
        if rel:
            con_pais = [{"id": d["id"], "relaciones": d["relaciones"]} for d in con_pais]
        for d in con_pais if not rel else []:
            if _RELLENO.search(d.get("resumen") or ""):
                print(f"  ? {d['id']}: {d['resumen'][:120]}")
        buenas += con_pais
        cuenta["con país" if rel else "fichas"] += len(con_pais)
        print(f"{ruta.name}: {len(resp)}/{len(pedidos)} respuestas, faltan {len(faltan)}, sobran {len(sobran)}, "
              f"{'con país' if rel else 'fichas'} {len(con_pais)}")
    (SALIDA / "_importar.jsonl").write_text("".join(json.dumps(d, ensure_ascii=False) + "\n" for d in buenas), encoding="utf-8")
    print(f"{len(buenas)} líneas en {SALIDA / '_importar.jsonl'}: {dict(cuenta)}")


if __name__ == "__main__":
    main(sys.argv[1:])
