"""Conectores: uno por parlamento nacional u organismo internacional.

Cada módulo declara FUENTE (fuentes.modelo.Fuente) y `recoger(ctx)`, que trae lo publicado desde la
última recogida y lo guarda con `ctx.guardar(asuntos, votaciones)`. Para añadir un país basta un
módulo nuevo y una línea en MODULOS; se prueba con `python -m concordia probar <código>` sin tocar la
base.
"""

import importlib

MODULOS = ["onu", "usa", "gbr", "pol", "esp", "irl", "che", "can", "bra", "swe", "fra", "nld", "dnk", "cze", "arg", "fin", "est", "deu", "chl", "mex", "ukr", "nor", "isr", "eup"]

FUENTES = {}
_MODULO = {}
for _nombre in MODULOS:
    _m = importlib.import_module(f".{_nombre}", __name__)
    FUENTES[_m.FUENTE.codigo] = _m.FUENTE
    _MODULO[_m.FUENTE.codigo] = _m


def modulo(codigo):
    return _MODULO[codigo]


def del_pais(iso3):
    return [f for f in FUENTES.values() if f.pais == iso3]
