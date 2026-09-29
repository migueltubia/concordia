"""Descargas con reintentos, gzip y caché en disco (data/raw/, que no se versiona).

Los certificados se verifican siempre. En Windows, Python solo ve las raíces que ya están en el almacén del
sistema, y a algunas webs (data.stortinget.no, opendata.camara.cl) les falta la suya: basta con poner en
`.env` SSL_CERT_FILE con la ruta de un almacén de Mozilla (el de Git para Windows sirve). En Linux, y por
tanto en GitHub Actions, no hace falta.
"""

import gzip
import hashlib
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from .config import RAW_DIR, USER_AGENT


class Bloqueada(RuntimeError):
    """La web responde con un reto anti-robots (WAF, «client challenge»). No se intenta saltar."""


# Ritmo por servidor, para las API que cortan con 429 si se les pide demasiado: {host: [intervalo, cerrojo,
# momento en que puede salir la siguiente petición]}. Vale para todos los hilos a la vez.
_RITMO = {}


def ritmo(host, segundos):
    """Deja al menos `segundos` entre dos peticiones a `host`, aunque las hagan varios hilos."""
    _RITMO.setdefault(host, [segundos, threading.Lock(), 0.0])[0] = segundos


def _turno(host, pausa=0.0):
    r = _RITMO.get(host)
    if not r:
        if pausa:
            time.sleep(pausa)
        return
    with r[1]:
        r[2] = max(r[2], time.monotonic() + pausa)
        espera = r[2] - time.monotonic()
        if espera > 0:
            time.sleep(espera)
        r[2] = time.monotonic() + r[0]


def fetch(url, retries=4, timeout=90, headers=None, formulario=None, post_json=None):
    """GET con reintentos y soporte gzip. Devuelve bytes.

    Con `formulario` (dict) es un POST de formulario; con `post_json`, un POST con ese cuerpo en JSON.
    Un 429 (demasiadas peticiones) se espera lo que diga Retry-After (un minuto si no lo dice).
    """
    cab = {"User-Agent": USER_AGENT, "Accept-Encoding": "gzip", "Accept": "*/*", **(headers or {})}
    cuerpo = None
    if formulario is not None:
        cuerpo = urllib.parse.urlencode(formulario).encode()
        cab.setdefault("Content-Type", "application/x-www-form-urlencoded")
    elif post_json is not None:
        cuerpo = json.dumps(post_json).encode()
        cab.setdefault("Content-Type", "application/json")
    host = urllib.parse.urlsplit(url).hostname
    ultimo, pausa = None, 0.0
    for intento in range(retries):
        _turno(host, pausa)
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=cuerpo, headers=cab), timeout=timeout) as r:
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
            if e.code == 429:
                espera = (e.headers.get("Retry-After") or "").strip()
                pausa = (int(espera) if espera.isdigit() else 60) + 5
                continue
        except Exception as e:  # red, timeouts, gzip truncado
            ultimo = e
        pausa = 2 * (intento + 1)
    raise RuntimeError(f"No se pudo descargar {url}: {ultimo}")


def json_url(url, **kw):
    return json.loads(fetch(url, **kw).decode("utf-8-sig"))


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
