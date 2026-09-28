"""España: Pleno del Congreso de los Diputados, tomado de Escrutinio.

Escrutinio (https://github.com/migueltubia/escrutinio) ya descarga cada día los datos abiertos del
Congreso, enlaza cada votación con su iniciativa, decide qué votación es la decisiva y hace la ficha de
cada iniciativa (resumen, tema). Aquí se reutiliza su base troceada (data/bd/congreso/legNN.sqlite),
que se descarga del repositorio público cuando cambia su huella. Solo el ámbito nacional: los
parlamentos autonómicos y los ayuntamientos de Escrutinio no se incluyen.

Con la variable ESCRUTINIO_BD apuntando a una copia local de data/bd/ de Escrutinio se lee de ahí.
"""

import json
import os
import sqlite3
from pathlib import Path

from .modelo import Asunto, Fuente, Votacion

FUENTE = Fuente(
    codigo="esp", pais="ESP", nombre="Congreso de los Diputados (España)", corto="España", tipo="parlamento",
    detalle="nominal", web="https://migueltubia.github.io/escrutinio/", desde=2011, idioma="es",
    licencia="Datos abiertos del Congreso de los Diputados, procesados por Escrutinio (MIT)",
    camaras={"esp-c": ("Congreso de los Diputados", "Congreso", 350)},
    notas="Desde la X legislatura (2012), la primera con voto nominal en datos abiertos. Fichas de Escrutinio.",
    decisiva_propia=True,
)

REPO = "https://raw.githubusercontent.com/migueltubia/escrutinio/main/data/bd"
SENTIDO = {"S": "si", "N": "no", "A": "abstencion", "-": "no_vota"}
TIPO_FAMILIA = {"ley": "ley", "decreto_ley": "ley", "pnl": "mocion", "mocion": "mocion", "internacional": "tratado",
                "control": "otro", "otro": "otro"}
FINALES = {"conjunto", "pnl", "mocion", "convalidacion", "tratado", "control", "investidura"}
ENMIENDAS = {"enmiendas", "totalidad", "enmiendas_senado", "veto_senado", "articulado"}


def _fichero(ctx, nombre, huella):
    local = os.environ.get("ESCRUTINIO_BD")
    if local:
        return Path(local) / f"{nombre}.sqlite"
    return ctx.cache(f"{REPO}/{nombre}.sqlite", f"{nombre.replace('/', '_')}_{huella[:12]}.sqlite", timeout=600)


def _manifiesto(ctx):
    local = os.environ.get("ESCRUTINIO_BD")
    if local:
        return json.loads((Path(local) / "manifiesto.json").read_text(encoding="utf-8"))
    return ctx.json(f"{REPO}/manifiesto.json")


def tipo_asunto(prefijo, familia):
    if prefijo in ("180", "276", "investidura"):
        return "nombramiento"
    if familia == "organizacion":
        return "procedimiento"
    return TIPO_FAMILIA.get(familia, "otro")


def cargar_legislatura(ctx, leg, ruta, comun):
    c = sqlite3.connect(ruta)
    c.row_factory = sqlite3.Row
    familias = {r["prefijo"]: r["familia"] for r in comun.execute("SELECT prefijo, familia FROM tipo_expediente")}
    nombres = {r["id"]: r["nombre"] for r in comun.execute("SELECT id, nombre FROM diputado WHERE cuerpo='congreso'")}
    siglas = {}
    for g in c.execute("SELECT codigo, nombre, siglas, color FROM grupo"):
        s = g["siglas"] or g["codigo"]
        siglas[g["codigo"]] = s
        ctx.partido(s, s if s != "?" else "Sin grupo", s, g["color"])
    iniciativas = {r["expediente"]: r for r in c.execute("SELECT * FROM iniciativa")}
    plantilla = dict(c.execute("SELECT pos, diputado_id FROM plantilla").fetchall())
    grupo_idx = dict(c.execute("SELECT idx, codigo FROM grupo_idx").fetchall())
    compacto = {r[0]: (r[1], r[2]) for r in c.execute("SELECT votacion_id, sentidos, grupos FROM voto_compacto")}
    asuntos, votaciones = {}, []
    for v in c.execute("SELECT * FROM votacion WHERE camara='Congreso' OR camara IS NULL ORDER BY fecha, sesion, numero"):
        exp = v["expediente"] or f"SIN/{v['id']}"
        aid = f"esp:{leg}:{exp}"
        i = iniciativas.get(exp)
        if aid not in asuntos:
            prefijo = (i["prefijo"] if i else v["prefijo"]) or exp.split("/")[0]
            titulo = (i["titulo"] if i else None) or v["texto_expediente"] or exp
            asuntos[aid] = Asunto(id=aid, titulo=titulo[:600], tipo=tipo_asunto(prefijo, familias.get(prefijo, "otro")),
                                  fecha=(i["fecha_presentacion"] if i else None) or v["fecha"], codigo=None if exp.startswith("SIN") else exp,
                                  autor=(i["grupo_autor"] or i["autor"]) if i else None,
                                  extra={"legislatura": leg, "tipo_escrutinio": i["tipo"] if i else None})
        tv = v["tipo_votacion"]
        tipo = ("final" if v["decisiva"] or tv in FINALES else "enmienda" if tv in ENMIENDAS
                else "nombramiento" if tv == "nombramiento" else "procedimiento" if tv in ("organizacion", "tramitacion_ley")
                else "otra")
        votos = []
        if v["id"] in compacto:
            sentidos, grupos = compacto[v["id"]]
            for pos, (s, g) in enumerate(zip(sentidos, grupos)):
                if s != "." and pos in plantilla:
                    did = plantilla[pos]
                    votos.append((f"esp:{did}", nombres.get(did, str(did)), siglas.get(grupo_idx.get(ord(g) - 48), "?"), SENTIDO[s]))
        texto = " · ".join(x for x in (v["titulo_subgrupo"], v["texto_subgrupo"]) if x) or None
        votaciones.append(Votacion(
            id=f"esp:{v['id']}", fecha=v["fecha"], asunto_id=aid, camara="esp-c", numero=v["numero"], texto=texto, tipo=tipo,
            a_favor=v["a_favor"], en_contra=v["en_contra"], abstenciones=v["abstenciones"], no_votan=v["no_votan"],
            mayoria=v["mayoria"], resultado=v["resultado"], url=v["url"], votos=votos or None, decisiva=int(bool(v["decisiva"]))))
        if len(votaciones) >= 400:
            ctx.guardar([asuntos[a] for a in dict.fromkeys(x.asunto_id for x in votaciones)], votaciones)
            votaciones = []
    if votaciones:
        ctx.guardar([asuntos[a] for a in dict.fromkeys(x.asunto_id for x in votaciones)], votaciones)
    if ctx.simular:
        return
    # Fichas de Escrutinio (resumen y tema). Las relaciones con otros países las pone Concordia.
    filas = []
    for f in c.execute("SELECT * FROM ficha_llm"):
        filas.append((f"esp:{leg}:{f['expediente']}", f["resumen"], f["tema_principal"], f["temas_secundarios"], f["etiquetas"],
                      f["confianza"], f"escrutinio:{f['modelo']}", f["version_prompt"], f["creado"]))
    for f in c.execute("SELECT p.* FROM tema_provisional p WHERE NOT EXISTS (SELECT 1 FROM ficha_llm f WHERE f.expediente=p.expediente)"):
        filas.append((f"esp:{leg}:{f['expediente']}", None, f["tema_principal"], f["temas_secundarios"], "[]", None,
                      "escrutinio:reglas", f["version"], f["creado"]))
    ctx.con.executemany(
        """INSERT INTO ficha(asunto_id, resumen, tema_principal, temas_secundarios, etiquetas, confianza, origen, version, creado)
           SELECT ?,?,?,?,?,?,?,?,? WHERE EXISTS (SELECT 1 FROM asunto WHERE id=?1)
           ON CONFLICT(asunto_id) DO UPDATE SET resumen=excluded.resumen, tema_principal=excluded.tema_principal,
             temas_secundarios=excluded.temas_secundarios, etiquetas=excluded.etiquetas, confianza=excluded.confianza,
             origen=excluded.origen, version=excluded.version, creado=excluded.creado""", filas)
    ctx.con.commit()
    c.close()


def recoger(ctx):
    manifiesto = _manifiesto(ctx)
    previas = ctx.marca("huellas", {})
    comun = sqlite3.connect(_fichero(ctx, "comun", manifiesto["comun"]["huella"]))
    comun.row_factory = sqlite3.Row
    for nombre, info in sorted(manifiesto.items(), key=lambda kv: kv[0]):
        if not nombre.startswith("congreso/leg"):
            continue
        leg = int(nombre.split("leg")[-1])
        if previas.get(nombre) == info["huella"] and not ctx.completo:
            continue
        ctx.log(f"   {nombre}: {info.get('votaciones', '?')} votaciones")
        ruta = _fichero(ctx, nombre, info["huella"])  # antes de borrar nada: la descarga no bloquea la base
        # Si cambia la legislatura se recarga entera: se borra lo anterior (Escrutinio puede reenlazar votaciones).
        if not ctx.simular:
            ctx.con.execute("DELETE FROM voto WHERE votacion_id IN (SELECT id FROM votacion WHERE fuente='esp' AND asunto_id LIKE ?)",
                            (f"esp:{leg}:%",))
            ctx.con.execute("DELETE FROM votacion WHERE fuente='esp' AND asunto_id LIKE ?", (f"esp:{leg}:%",))
        cargar_legislatura(ctx, leg, ruta, comun)
        previas[nombre] = info["huella"]
        ctx.poner_marca("huellas", previas)
    comun.close()
