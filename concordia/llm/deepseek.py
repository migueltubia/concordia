"""IA con DeepSeek (API compatible con OpenAI), solo con la biblioteca estándar.

Variables de entorno (o del fichero .env de la raíz; en GitHub Actions, secreto y variable del repositorio):
  DEEPSEEK_API_KEY   (obligatoria)
  DEEPSEEK_MODEL     (por defecto deepseek-flash)
  DEEPSEEK_BASE_URL  (por defecto https://api.deepseek.com)

Todo lo que devuelve se valida contra los catálogos cerrados y se guarda en data/llm/ (la fuente de verdad).
"""

import http.client
import json
import os
import time
import urllib.error
import urllib.request
from collections import defaultdict

from ..fuentes import FUENTES
from .fichas_io import (FICHAS_DIR, RELACIONES_DIR, _fuente_de, anotar, guardar_fichas, guardar_relaciones, items_pendientes,
                        items_relaciones)
from .prompt import instrucciones_fichas, instrucciones_relaciones, validar, validar_relaciones

POR_LLAMADA = 12


class ErrorIA(RuntimeError):
    pass


class RespuestaTruncada(ErrorIA):
    pass


def disponible():
    return bool(os.environ.get("DEEPSEEK_API_KEY"))


def modelo_por_defecto():
    return os.environ.get("DEEPSEEK_MODEL") or "deepseek-flash"


IDIOMA = ("Escribe siempre en español de España (castellano peninsular): ortografía, vocabulario y expresiones de España, "
          "no de Hispanoamérica, aunque el texto original esté en otra lengua.")


def chat_json(sistema, usuario, modelo=None, max_tokens=32_000, reintentos=5):
    """Una llamada en modo JSON. Devuelve (objeto, modelo_real, uso)."""
    base = (os.environ.get("DEEPSEEK_BASE_URL") or "https://api.deepseek.com").rstrip("/")
    cuerpo = {
        "model": modelo or modelo_por_defecto(),
        "messages": [{"role": "system", "content": f"{sistema}\n\n{IDIOMA}"}, {"role": "user", "content": usuario}],
        "response_format": {"type": "json_object"},
        "max_tokens": max_tokens,
        "temperature": 0.2,
        "stream": False,
    }
    peticion = urllib.request.Request(
        base + "/chat/completions", data=json.dumps(cuerpo).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {os.environ['DEEPSEEK_API_KEY']}"})
    ultimo = None
    for intento in range(reintentos):
        try:
            with urllib.request.urlopen(peticion, timeout=600) as r:
                d = json.loads(r.read().decode("utf-8"))
            eleccion = d["choices"][0]
            contenido = (eleccion.get("message") or {}).get("content") or ""
            if eleccion.get("finish_reason") == "length":
                raise RespuestaTruncada("respuesta truncada por max_tokens")
            if contenido.strip():
                return json.loads(contenido), d.get("model") or cuerpo["model"], d.get("usage") or {}
            ultimo = ErrorIA("respuesta vacía")
        except urllib.error.HTTPError as e:
            detalle = e.read().decode("utf-8", "replace")[:300]
            if e.code not in (429, 500, 502, 503, 504):
                raise ErrorIA(f"HTTP {e.code}: {detalle}") from e
            ultimo = ErrorIA(f"HTTP {e.code}: {detalle}")
        except json.JSONDecodeError as e:
            ultimo = ErrorIA(f"JSON inválido en la respuesta: {e}")
        except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException) as e:
            ultimo = ErrorIA(f"red: {e}")
        time.sleep(min(60, 5 * 2 ** intento))
    raise ultimo or ErrorIA("sin respuesta")


def _lotes(con, items, sistema, completa, modelo, log):
    """Pide las fichas en grupos; si una respuesta no cabe, parte el grupo. Devuelve los años tocados."""
    tocados = defaultdict(set)
    hechas, fallidas, tokens = 0, 0, 0
    for i in range(0, len(items), POR_LLAMADA):
        cola = [(items[i:i + POR_LLAMADA], 0)]
        while cola:
            pendientes, ronda = cola.pop(0)
            por_id = {it["id"]: it for it in pendientes}
            try:
                datos, modelo_real, uso = chat_json(sistema, "Asuntos:\n" + "\n".join(json.dumps(it, ensure_ascii=False) for it in pendientes), modelo)
            except RespuestaTruncada:
                if len(pendientes) > 1:
                    mitad = len(pendientes) // 2
                    cola[:0] = [(pendientes[:mitad], ronda), (pendientes[mitad:], ronda)]
                else:
                    fallidas += 1
                continue
            except ErrorIA as e:
                log(f"  ! {e}")
                fallidas += len(pendientes)
                continue
            tokens += uso.get("total_tokens", 0)
            etiqueta = f"deepseek:{modelo_real}"
            buenas = defaultdict(list)
            for f in datos.get("fichas") or []:
                if not isinstance(f, dict) or f.get("id") not in por_id:
                    continue
                fuente = _fuente_de(f["id"])
                origen = FUENTES[fuente].pais
                if completa:
                    ficha, _ = validar(dict(f), origen)
                    if ficha:
                        buenas[fuente].append(ficha)
                else:
                    buenas[fuente].append({"id": f["id"], "relaciones": validar_relaciones(f.get("relaciones"), origen)})
            hechos = set()
            for fuente, lista in buenas.items():
                t = guardar_fichas(con, lista, etiqueta) if completa else guardar_relaciones(con, lista, etiqueta)
                anotar(FICHAS_DIR if completa else RELACIONES_DIR, fuente, [{**x, "_modelo": etiqueta} for x in lista])
                for f, anios in t.items():
                    tocados[f] |= anios
                hechos |= {x["id"] for x in lista}
            con.commit()
            hechas += len(hechos)
            faltan = [it for it in pendientes if it["id"] not in hechos]
            if faltan and ronda == 0:
                cola.append((faltan, 1))
            else:
                fallidas += len(faltan)
        log(f"  {min(i + POR_LLAMADA, len(items))}/{len(items)}")
    log(f"  hechas {hechas}, sin hacer {fallidas}, tokens {tokens}")
    return tocados


def generar_fichas(con, limite=300, fuentes=None, modelo=None, log=print):
    """Fichas completas de los asuntos que no tienen y relaciones de los que ya tienen resumen (Escrutinio)."""
    tocados = defaultdict(set)
    items = items_pendientes(con, limite, fuentes)
    if items:
        log(f"Fichas con DeepSeek: {len(items)} asuntos (límite {limite})")
        for f, a in _lotes(con, items, instrucciones_fichas(), True, modelo, log).items():
            tocados[f] |= a
    resto = max(0, limite - len(items))
    rels = items_relaciones(con, resto, fuentes) if resto else []
    if rels:
        log(f"Relaciones con DeepSeek: {len(rels)} asuntos con ficha de Escrutinio")
        for f, a in _lotes(con, rels, instrucciones_relaciones(), False, modelo, log).items():
            tocados[f] |= a
    if not items and not rels:
        log("No hay asuntos pendientes de ficha")
    return dict(tocados)
