"""Estonia: votaciones del pleno del Riigikogu (API oficial de datos abiertos, https://api.riigikogu.ee).

La API da, por rango de fechas, las sesiones del pleno con sus votaciones (y el proyecto, «eelnõu», al
que se refiere cada una), el orden del día con los puntos tratados (título con el número y tipo del
proyecto —«768 OE», «524 SE»—, lectura, mayoría exigida, quién lo presenta y qué votaciones hubo en
cada punto) y el detalle de cada votación con el voto de cada diputado y su grupo (fraktsioon) en ese
momento. Hay datos desde mucho antes de 2019; se recoge desde 2019: final de la XIII legislatura, la XIV
(abril de 2019) y la XV (abril de 2023). El número de proyecto vuelve a empezar en cada legislatura, que
forma parte del id del asunto («est:15:768»).

Particularidades:
- Las votaciones se agrupan por proyecto (número del proyecto dentro de la legislatura): primera lectura
  (propuesta de rechazo), enmiendas de la segunda, votación final de la tercera y, si el Presidente
  devuelve la ley, la nueva votación. Los asuntos sin proyecto (moción de censura, mandato al candidato
  a primer ministro, propuestas del Canciller de Justicia) se agrupan por punto del orden del día o
  documento; las votaciones de trámite (orden del día, prórroga de la sesión, calendario) van a un
  asunto de procedimiento por semana.
- Los controles de presencia («Kohaloleku kontroll») no son votaciones y no se recogen. Las votaciones
  secretas (nombramientos) solo tienen totales.
- «Erapooletu» es la abstención; «ei hääletanud» (presente sin votar) y «puudub» (ausente) son «no vota»,
  como en los totales de la fuente.
- La fuente no publica el resultado: se calcula con la mayoría que exige cada caso (simple; la de la
  cámara, 51 votos, cuando el orden del día lo indica, en las mociones de censura y en las propuestas
  al Gobierno; 3/5 o 2/3 en las reformas constitucionales). Cuadra con la decisión del orden del día.
- La API limita a una petición por segundo: la recogida va en serie, con pausa, y la primera completa
  desde 2019 tarda más de una hora; las siguientes solo traen lo nuevo (margen de dos semanas).
- Títulos en estonio: las reglas no los leen y la ficha de la IA los resume en español.
"""

import re
import threading
import time
from datetime import date, timedelta

from .modelo import Asunto, Fuente, Votacion

FUENTE = Fuente(
    codigo="est", pais="EST", nombre="Riigikogu de Estonia", corto="Estonia", tipo="parlamento",
    detalle="nominal", web="https://www.riigikogu.ee", desde=2019, idioma="otro",
    licencia="Datos abiertos del Riigikogu, CC BY-SA 3.0",
    camaras={"est-r": ("Riigikogu", "Riigikogu", 101)},
    partidos={
        "RE": ("Partido Reformista de Estonia", "RE", "#f2c300"),
        "KE": ("Partido del Centro de Estonia", "KE", "#00843d"),
        "EKRE": ("Partido Popular Conservador de Estonia", "EKRE", "#1f2f5c"),
        "I": ("Isamaa (Patria)", "Isamaa", "#009fe3"),
        "SDE": ("Partido Socialdemócrata", "SDE", "#e10600"),
        "E200": ("Estonia 200", "E200", "#00a5a8"),
        "EVA": ("Partido Libre de Estonia", "EVA", "#8a4f9e"),
        "FMK": ("No adscritos", "No adscr.", "#898781"),
    },
    notas=("Votaciones electrónicas del pleno con el voto de cada diputado (las secretas, solo con totales); "
           "el resultado se calcula con la mayoría exigida."),
)

API = "https://api.riigikogu.ee/api"
WEB = "https://www.riigikogu.ee"
PAUSA = 1.25   # segundos entre peticiones: la API responde 429 por encima de una por segundo
LOTE = 100
MARGEN_DIAS = 14

# Grupos (fraktsioon) por su uuid, que la fuente mantiene entre legislaturas.
FACCIONES = {
    "8772fd6f-3197-6a53-2ffc-8c4d63407d1e": "RE",
    "3c1832c0-7727-18d1-d9d3-e685a58f44b0": "KE",
    "d4e90963-1d10-4f8a-bf37-a99ca8531ff3": "EKRE",
    "a844d128-287d-4c20-bf30-61fcb0af23cf": "I",
    "d188e268-5d01-7e93-0c22-3ae7f0c1e851": "SDE",
    "e4bf6970-f928-4230-961c-615cc54118f9": "E200",
    "2faa5389-46c8-4dfd-ac8a-5a9b498912c4": "EVA",
    "c99e4e31-617c-49ad-bfa6-814736842182": "FMK",
}
# Por si aparece un uuid nuevo de un grupo conocido.
FACCION_NOMBRE = [("reformierakon", "RE"), ("keskerakon", "KE"), ("konservatiivse rahvaerakon", "EKRE"),
                  ("isamaa", "I"), ("sotsiaaldemokraat", "SDE"), ("eesti 200", "E200"), ("vabaerakon", "EVA"),
                  ("mittekuuluv", "FMK")]

SENTIDO = {"POOLT": "si", "VASTU": "no", "ERAPOOLETU": "abstencion", "EI_HAALETANUD": "no_vota", "PUUDUB": "no_vota"}

LECTURA = {"ESIMENE_LUGEMINE": "1.ª lectura", "TEINE_LUGEMINE": "2.ª lectura", "TEISE_LUGEMISE_JATKAMINE": "2.ª lectura",
           "KOLMAS_LUGEMINE": "3.ª lectura", "III_LUGEMINE_KUI_II_LOPETATAKSE": "3.ª lectura",
           "UUESTI_ARUTAMINE": "nuevo examen"}

# Descripción de la votación en la fuente -> (texto en español, tipo). Las de trámite van al asunto semanal.
QUE_SE_VOTA = [
    ("lõpphääletus", "Votación final", "final"),
    ("muutmata kujul uuesti vastuvõtmine", "Nueva aprobación sin cambios de la ley devuelta por el Presidente", "final"),
    ("muudatusettepanek", "Enmienda", "enmienda"),
    ("tagasi lükkamine", "Propuesta de rechazo del proyecto", "enmienda"),
    ("eriarvamus", "Voto particular", "enmienda"),
    ("lugemise katkestamine", "Suspensión de la lectura", "procedimiento"),
    ("päevakorra", "Aprobación del orden del día", "procedimiento"),
    ("tööaja pikendamine", "Prórroga de la sesión", "procedimiento"),
    ("töö ajagraafik", "Calendario de trabajo del pleno", "procedimiento"),
    ("ettepaneku hääletamine", "Votación de la propuesta", "otra"),
    ("hääletus", "Votación", "otra"),
]
TRAMITE = ("päevakorra", "tööaja pikendamine", "töö ajagraafik", "istungjärgu")

_candado = threading.Lock()
_ultima = [0.0]


def _get(ctx, url):
    """GET con pausa: la API corta (429) si se le pide más de una cosa por segundo."""
    with _candado:
        espera = PAUSA - (time.monotonic() - _ultima[0])
        if espera > 0:
            time.sleep(espera)
        _ultima[0] = time.monotonic()
    return ctx.json(url, headers={"Accept": "application/json"})


def _limpio(t):
    return re.sub(r"\s+", " ", (t or "").replace(" ", " ")).strip()


def que_se_vota(descripcion):
    d = (descripcion or "").lower()
    for clave, texto, tipo in QUE_SE_VOTA:
        if clave in d:
            if clave == "muudatusettepanek":
                n = re.match(r"\s*(\d+)", d)
                texto = f"Enmienda {n.group(1)}" if n else texto
            elif clave == "lugemise katkestamine":
                n = re.match(r"\s*(i+)\b", d)
                texto = f"Suspensión de la {len(n.group(1))}.ª lectura" if n else texto
            return texto, tipo
    return (descripcion or "Votación"), "otra"


def es_tramite(descripcion):
    d = (descripcion or "").lower()
    return any(k in d for k in TRAMITE)


def tipo_proyecto(titulo, codigo_tipo=None):
    """Tipo de asunto de un proyecto a partir de su título (y del tipo del número, si se sabe)."""
    t = titulo.lower()
    if re.search(r"ratifitseeri|denonsseeri|ühinemise seadus|lepingu(?:te)? (?:muutmise )?heakskiit", t) \
            and "ettepaneku tegemine" not in t:
        return "tratado"
    if codigo_tipo in ("SE", "UA") or re.search(r"seadus(?:tik)?\b|seaduse\b|seadustiku\b", t) and not t.startswith("riigikogu"):
        return "ley"
    if "ettepaneku tegemine" in t:
        return "mocion"
    if t.startswith("riigikogu otsus") or codigo_tipo == "OE":
        if re.search(r"nimetamine|valimine|tagasikutsumine|ametisse|liikmeks|volituste andmine|nõusoleku andmine", t):
            return "nombramiento"
        if re.search(r"(komisjoni|delegatsiooni|koosseisu|töörühma)\w* (moodustamine|muutmine)", t):
            return "procedimiento"
        return "resolucion"
    if t.startswith(("riigikogu avaldus", "riigikogu pöördumi", "eesti vabariigi riigikogu pöördumine")) \
            or codigo_tipo in ("AE", "PE"):
        return "resolucion"
    return "otro"


def tipo_punto(tipo_codigo):
    """Tipo de asunto de un punto del orden del día sin proyecto."""
    return {"UMBUSALDUSE_AVALDAMINE": "mocion", "PEAMINISTRILE_VOLITUSTE_ANDMINE": "nombramiento",
            "OIGUSKANTSLERI_ETTEPANEKUD": "resolucion", "VALITSUSE_POLIITILISED_AVALDUSED": "otro"}.get(tipo_codigo, "otro")


def mayoria_exigida(titulo_punto, tipo_codigo, titulo_asunto):
    """Votos a favor que exige la decisión (None si basta la mayoría simple)."""
    t = (titulo_punto or "").lower()
    if "kahekolmandik" in t:
        return 68
    if "kolmeviiendik" in t:
        return 61
    if "koosseisu häälteenamus" in t or tipo_codigo == "UMBUSALDUSE_AVALDAMINE" \
            or "ettepaneku tegemine vabariigi valitsusele" in (titulo_asunto or "").lower():
        return 51
    return None


def faccion(ctx, f):
    if not f or not f.get("uuid"):
        return "FMK"
    cod = FACCIONES.get(f["uuid"])
    if cod:
        return cod
    nombre = (f.get("name") or "").lower()
    for clave, c in FACCION_NOMBRE:
        if clave in nombre:
            return c
    cod = f["uuid"][:8]
    ctx.partido(cod, f.get("name"), (f.get("name") or cod)[:12])
    return cod


def _semana(fecha, membership):
    d = date.fromisoformat(fecha)
    lunes = d - timedelta(days=d.weekday())
    iso = d.isocalendar()
    aid = f"est:{membership}:tramite:{iso[0]}-W{iso[1]:02d}"
    return aid, f"Votaciones de trámite del pleno, semana del {lunes.strftime('%d.%m.%Y')}", lunes.isoformat()


def _puntos(agenda):
    """uuid de votación -> punto del orden del día (None para las votaciones de la sesión en sí)."""
    punto = {}
    for s in (agenda or {}).get("sittings") or []:
        for v in s.get("votings") or []:
            punto[v["uuid"]] = None
        for it in s.get("agendaItems") or []:
            for v in it.get("votings") or []:
                punto[v["uuid"]] = it
    return punto


def _asunto(ctx, v, d, it, membership, fecha):
    """Asunto de una votación: proyecto, punto sin proyecto o trámite de la semana."""
    borrador = v.get("relatedDraft") or d.get("relatedDraft") or (it or {}).get("relatedDraft")
    if es_tramite(v.get("description")) or (not borrador and not it):
        aid, titulo, lunes = _semana(fecha, membership)
        return Asunto(id=aid, titulo=titulo, tipo="procedimiento", fecha=lunes)
    titulo_punto = _limpio((it or {}).get("title"))
    autor = ", ".join(_limpio(i.get("name")) for i in (it or {}).get("initiators") or [] if i.get("name"))[:200] or None
    if borrador and borrador.get("mark"):
        mark = borrador["mark"]
        m = re.search(rf"\(\s*{mark}\s+([A-ZÕÄÖÜ]{{2,3}})\b", titulo_punto)
        codigo_tipo = m.group(1) if m else None
        titulo = _limpio(borrador.get("title"))
        codigo = f"{mark} {'SE' if codigo_tipo == 'UA' else codigo_tipo}" if codigo_tipo else f"eelnõu {mark}"
        return Asunto(id=f"est:{membership}:{mark}", titulo=titulo[:400], tipo=tipo_proyecto(titulo, codigo_tipo),
                      fecha=fecha, codigo=codigo, autor=autor, url=f"{WEB}/tegevus/eelnoud/eelnou/{borrador['uuid']}/")
    doc = d.get("relatedDocument") or {}
    titulo = re.sub(r"\s*\((?:Riigikogu koosseisu[^)]*|usaldusküsimusega[^)]*)\)", "", titulo_punto) or _limpio(doc.get("title"))
    steno = ((it or {}).get("_links") or {}).get("steno", {}).get("href")
    clave = f"dok:{doc['uuid']}" if doc.get("uuid") else f"punto:{it['uuid']}"
    return Asunto(id=f"est:{membership}:{clave}", titulo=titulo[:400], tipo=tipo_punto(it["type"]["code"]), fecha=fecha,
                  codigo=doc.get("reference"), autor=autor, url=steno)


def _votacion(ctx, v, d, it, asunto, fecha):
    texto, tipo = que_se_vota(v.get("description"))
    if tipo == "final" and asunto.tipo == "nombramiento":
        tipo = "nombramiento"
    lectura = LECTURA.get((it or {}).get("stage"))
    if lectura and asunto.tipo != "procedimiento" and "lectura" not in texto:
        texto = f"{texto} ({lectura})"
    secreta = (d.get("type") or v.get("type") or {}).get("code") == "SALAJANE"
    if secreta:
        texto += ", voto secreto"
    si, no = d.get("inFavor") or 0, d.get("against") or 0
    exigida = None
    desc = (v.get("description") or "").lower()
    if tipo in ("final", "nombramiento") or ("ettepaneku" in desc and (it or {}).get("type", {}).get("code") == "OIGUSKANTSLERI_ETTEPANEKUD"):
        exigida = mayoria_exigida((it or {}).get("title"), (it or {}).get("type", {}).get("code"), asunto.titulo)
    votos = []
    for m in d.get("voters") or []:
        nombre = m.get("fullName") or " ".join(x for x in (m.get("firstName"), m.get("lastName")) if x)
        sentido = SENTIDO.get((m.get("decision") or {}).get("code"), "no_vota")
        votos.append((f"est:{m['uuid']}", nombre, faccion(ctx, m.get("faction")), sentido))
    return Votacion(
        id=f"est:{v['uuid']}", fecha=fecha, asunto_id=asunto.id, camara="est-r", numero=v.get("votingNumber"),
        texto=texto, tipo=tipo, a_favor=d.get("inFavor"), en_contra=d.get("against"), abstenciones=d.get("neutral"),
        no_votan=d.get("abstained"), mayoria=f"{exigida} votos" if exigida else "simple",
        resultado="aprobada" if (si >= exigida if exigida else si > no) else "rechazada",
        url=f"{WEB}/haaletustulemused/{v['uuid']}/", votos=votos or None)


def recoger(ctx):
    hoy = date.today()
    inicio = date(ctx.desde, 1, 1)
    ultima = ctx.ultima_fecha()
    if ultima and not ctx.completo:
        inicio = max(inicio, date.fromisoformat(ultima) - timedelta(days=MARGEN_DIAS))
    for anio in range(inicio.year, hoy.year + 1):
        desde, hasta = max(inicio, date(anio, 1, 1)), min(hoy, date(anio, 12, 31))
        sesiones = _get(ctx, f"{API}/votings?startDate={desde}&endDate={hasta}&lang=ET") or []
        pendientes = [(s.get("membership"), v) for s in sesiones for v in s.get("votings") or []
                      if (v.get("type") or {}).get("code") != "KOHALOLEKU_KONTROLL"
                      and desde.isoformat() <= (v.get("startDateTime") or "")[:10] <= hasta.isoformat()]
        if not pendientes:
            continue
        punto = _puntos(_get(ctx, f"{API}/agenda/plenary?startDate={desde}&endDate={hasta}&lang=ET"))
        ctx.log(f"   {anio}: {len(pendientes)} votaciones desde {desde}")
        for i in range(0, len(pendientes), LOTE):
            asuntos, votaciones = {}, []
            for membership, v in pendientes[i:i + LOTE]:
                d = _get(ctx, f"{API}/votings/{v['uuid']}?lang=ET")
                fecha = (d.get("startDateTime") or v["startDateTime"])[:10]
                if fecha < f"{ctx.desde}-01-01":
                    continue
                it = punto.get(v["uuid"])
                nuevo = _asunto(ctx, v, d, it, membership, fecha)
                a = asuntos.setdefault(nuevo.id, nuevo)
                if (a.codigo or "").startswith("eelnõu") and nuevo.codigo and not nuevo.codigo.startswith("eelnõu"):
                    a.codigo, a.tipo = nuevo.codigo, nuevo.tipo   # el número con su tipo sale del orden del día
                a.autor = a.autor or nuevo.autor
                votaciones.append(_votacion(ctx, v, d, it, a, fecha))
            ctx.guardar(list(asuntos.values()), votaciones)
            ctx.log(f"   {anio}: {min(i + LOTE, len(pendientes))}/{len(pendientes)}")
