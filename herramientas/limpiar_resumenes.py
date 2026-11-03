"""Quita de los resúmenes de las fichas IA las frases de relleno, sin volver a llamar a la IA.

- La última frase «Afecta a…» cuando hay otra antes (la regla de estilo 9 de llm/prompt.py).
- Las frases que hablan del título o de los metadatos («El título no precisa…», «…no permiten conocer…»).
- «El asunto consiste, por tanto, en ese rechazo» y parecidas.

Las fichas cambiadas se añaden al JSONL del mes (vale la última línea de cada asunto); lo anterior no se toca.
Uso: python herramientas/limpiar_resumenes.py [--guardar]   (sin --guardar solo enseña lo que cambiaría)
"""

import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
FICHAS = RAIZ / "data" / "llm" / "fichas"
LIMPIEZA = "limpieza-v1"

# Corta tras . ! ? cuando sigue mayúscula; «EE. UU. Afecta» se parte de más, pero solo se quitan frases enteras
# que empiezan como las de abajo, así que no importa.
_FRASES = re.compile(r"(?<=[.!?»])\s+(?=[A-ZÁÉÍÓÚÑ¿«])")
_RELLENO = [
    re.compile(r"^Afecta (a|al|principalmente|sobre todo|en especial|directamente)\b"),
    re.compile(r"^(El|Su) título\b.*\b(no|sin)\b"),
    re.compile(r"^(El|Su) título y (los|sus) metadatos\b"),
    re.compile(r"^(Los|Sus) metadatos\b.*\bno\b"),
    re.compile(r"^No se (precisa|especifica|detalla|indica|concreta)\b"),
    re.compile(r"^(Por (el|su) título|Del título|Con los datos disponibles),? no (se puede|puede|es posible)\b"),
    re.compile(r"^El asunto (consiste|es),? (por tanto|por lo tanto|así),? (en )?ese rechazo\b"),
    re.compile(r"^El asunto es, por tanto,"),
]
# La misma idea pegada al final de una frase útil: «…el proyecto S-1287/25-PL, por lo que no puede determinarse su objeto».
_COLA = re.compile(r"[,;]? (por lo que|de modo que|así que) no (puede|se puede|es posible) (determinarse|saberse|conocerse|precisarse)[^.]*\.$"
                   r"|[;,] (pero |aunque )?(el título|los metadatos) no (detalla|precisa|concreta|indica|especifica|permite)[^.]*\.$")


def limpiar(resumen):
    frases = _FRASES.split(resumen.strip())
    quedan = []
    for i, fr in enumerate(frases):
        afecta = _RELLENO[0].match(fr)
        if afecta and (i != len(frases) - 1 or not quedan):
            quedan.append(fr)  # «Afecta a…» solo se quita al final y si hay algo antes
        elif not afecta and any(p.match(fr) for p in _RELLENO[1:]):
            continue
        elif not afecta:
            quedan.append(fr)
    if not quedan:
        return resumen
    texto = " ".join(quedan)
    texto = _COLA.sub(".", texto)
    return texto if len(texto) >= 25 else resumen


def main(guardar):
    ultima = {}
    for ruta in sorted(FICHAS.glob("*/*.jsonl"), key=lambda r: (r.stem, r.parent.name)):
        for linea in ruta.read_text(encoding="utf-8").splitlines():
            try:
                d = json.loads(linea)
            except json.JSONDecodeError:
                continue
            ultima[d["id"]] = d
    # Las líneas antiguas no traen versión ni fecha: se toman de la base, o al reimportar pasarían a la versión actual.
    import sqlite3
    base = sqlite3.connect(RAIZ / "data" / "concordia.sqlite")
    version = {i: (v, c) for i, v, c in base.execute("SELECT asunto_id, version, creado FROM ficha")}
    cambios = defaultdict(list)
    motivos = Counter()
    ejemplos = []
    for d in ultima.values():
        if not str(d.get("_modelo") or "").startswith("deepseek:"):
            continue
        nuevo = limpiar(d["resumen"])
        if nuevo == d["resumen"]:
            continue
        motivos["afecta" if re.search(r"\bAfecta ", d["resumen"]) and not re.search(r"\bAfecta ", nuevo) else "título u otras"] += 1
        v, c = version.get(d["id"], (None, None))
        cambios[d["id"].split(":", 1)[0].split("-")[0]].append(
            {"_version": v, "_creado": c, **d, "resumen": nuevo, "_limpieza": LIMPIEZA})
        if len(ejemplos) < 2000:
            ejemplos.append((d["resumen"], nuevo))
    total = sum(len(v) for v in cambios.values())
    print(f"{total} de {len(ultima)} resúmenes cambian: {dict(motivos)}")
    import random
    random.seed(7)
    for antes, despues in random.sample(ejemplos, min(25, len(ejemplos))):
        print(f"\n- {antes}\n+ {despues}")
    if guardar:
        mes = f"{datetime.now(timezone.utc):%Y-%m}"
        for fuente, lista in cambios.items():
            with open(FICHAS / fuente / f"{mes}.jsonl", "a", encoding="utf-8") as fh:
                for d in lista:
                    fh.write(json.dumps(d, ensure_ascii=False) + "\n")
        print(f"\nGuardadas en data/llm/fichas/<fuente>/{mes}.jsonl")


if __name__ == "__main__":
    main("--guardar" in sys.argv)
