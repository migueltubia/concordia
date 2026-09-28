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
from concurrent.futures import ThreadPoolExecutor, as_completed

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


def _pedir(sistema, pendientes, modelo):
    """Una llamada (en un hilo). Si la respuesta no cabe, parte el grupo en dos. Devuelve [(grupo, datos, modelo, uso, error)]."""
    try:
        datos, modelo_real, uso = chat_json(sistema, "Asuntos:\n" + "\n".join(json.dumps(it, ensure_ascii=False) for it in pendientes), modelo)
        return [(pendientes, datos, modelo_real, uso, None)]
    except RespuestaTruncada as e:
        if len(pendientes) > 1:
            mitad = len(pendientes) // 2
            return _pedir(sistema, pendientes[:mitad], modelo) + _pedir(sistema, pendientes[mitad:], modelo)
        return [(pendientes, None, None, {}, str(e))]
    except ErrorIA as e:
        return [(pendientes, None, None, {}, str(e))]


def _lotes(con, items, sistema, completa, modelo, log, hilos=4):
    """Pide las fichas en grupos, varias llamadas a la vez; guarda en el hilo principal según llegan.

    Los asuntos que faltan en una respuesta se piden otra vez al final (una sola vez). Devuelve los años tocados.
    """
    tocados = defaultdict(set)
    cuenta = {"hechas": 0, "fallidas": 0, "tokens": 0}
    inicio = time.time()

    def guardar(pendientes, datos, modelo_real, uso):
        cuenta["tokens"] += uso.get("total_tokens", 0)
        por_id = {it["id"] for it in pendientes}
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
        cuenta["hechas"] += len(hechos)
        return [it for it in pendientes if it["id"] not in hechos]

    def ronda(grupos, ultima):
        faltan = []
        with ThreadPoolExecutor(hilos) as ex:
            futuros = [ex.submit(_pedir, sistema, g, modelo) for g in grupos]
            for n, fut in enumerate(as_completed(futuros), 1):
                for pendientes, datos, modelo_real, uso, error in fut.result():
                    if error:
                        log(f"  ! {error[:200]}")
                        cuenta["fallidas"] += len(pendientes)
                        continue
                    resto = guardar(pendientes, datos, modelo_real, uso)
                    if ultima:
                        cuenta["fallidas"] += len(resto)
                    else:
                        faltan += resto
                if n % 10 == 0 or n == len(grupos):
                    minutos = (time.time() - inicio) / 60
                    log(f"  {cuenta['hechas']}/{len(items)} fichas · {cuenta['tokens']:,} tokens · {minutos:.1f} min"
                        + (f" · {cuenta['hechas'] / minutos:.0f} por minuto" if minutos else ""))
        return faltan

    faltan = ronda([items[i:i + POR_LLAMADA] for i in range(0, len(items), POR_LLAMADA)], False)
    if faltan:
        log(f"  segunda ronda con {len(faltan)} asuntos que faltaban en las respuestas")
        ronda([faltan[i:i + POR_LLAMADA] for i in range(0, len(faltan), POR_LLAMADA)], True)
    log(f"  hechas {cuenta['hechas']}, sin hacer {cuenta['fallidas']}, tokens {cuenta['tokens']:,}")
    return tocados


def generar_fichas(con, limite=300, fuentes=None, modelo=None, log=print, hilos=4):
    """Fichas completas de los asuntos que no tienen y relaciones de los que ya tienen resumen (Escrutinio)."""
    tocados = defaultdict(set)
    items = items_pendientes(con, limite, fuentes)
    if items:
        log(f"Fichas con DeepSeek: {len(items)} asuntos (límite {limite})")
        for f, a in _lotes(con, items, instrucciones_fichas(), True, modelo, log, hilos).items():
            tocados[f] |= a
    resto = max(0, limite - len(items))
    rels = items_relaciones(con, resto, fuentes) if resto else []
    if rels:
        log(f"Relaciones con DeepSeek: {len(rels)} asuntos con ficha de Escrutinio")
        for f, a in _lotes(con, rels, instrucciones_relaciones(), False, modelo, log, hilos).items():
            tocados[f] |= a
    if not items and not rels:
        log("No hay asuntos pendientes de ficha")
    return dict(tocados)
