"""Descargas con reintentos, gzip y caché en disco (data/raw/, que no se versiona)."""

import gzip
import hashlib
import json
import time
import urllib.error
import urllib.request

from .config import RAW_DIR, USER_AGENT


class Bloqueada(RuntimeError):
    """La web responde con un reto anti-robots (WAF, «client challenge»). No se intenta saltar."""


def fetch(url, retries=4, timeout=90, headers=None):
    """GET con reintentos y soporte gzip. Devuelve bytes."""
    cab = {"User-Agent": USER_AGENT, "Accept-Encoding": "gzip", "Accept": "*/*", **(headers or {})}
    ultimo = None
    for intento in range(retries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=cab), timeout=timeout) as r:
                if r.status == 202 and r.headers.get("x-amzn-waf-action"):
                    raise Bloqueada(f"{url}: la web pide resolver un reto anti-robots (AWS WAF)")
                datos = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    datos = gzip.decompress(datos)
                if b"<title>Client Challenge</title>" in datos[:2000]:
                    raise Bloqueada(f"{url}: la web pide ejecutar JavaScript (reto anti-robots)")
                return datos
        except Bloqueada:
            raise
        except urllib.error.HTTPError as e:
            if e.code in (400, 401, 403, 404, 410):
                raise
            ultimo = e
        except Exception as e:  # red, timeouts, gzip truncado
            ultimo = e
        time.sleep(2 * (intento + 1))
    raise RuntimeError(f"No se pudo descargar {url}: {ultimo}")


def json_url(url, **kw):
    return json.loads(fetch(url, **kw).decode("utf-8"))


def en_cache(url, subcarpeta, nombre=None, caduca_horas=None, **kw):
    """Descarga a data/raw/<subcarpeta>/ si no está (o si ha caducado) y devuelve la ruta."""
    carpeta = RAW_DIR / subcarpeta
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / (nombre or hashlib.sha1(url.encode()).hexdigest()[:16])
    if ruta.exists() and (caduca_horas is None or time.time() - ruta.stat().st_mtime < caduca_horas * 3600):
        return ruta
    tmp = ruta.with_name(ruta.name + ".tmp")
    tmp.write_bytes(fetch(url, **kw))
    tmp.replace(ruta)
    return ruta
