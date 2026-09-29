"""Ucrania: votaciones nominales de la Verjovna Rada (portal de datos abiertos, https://data.rada.gov.ua).

La Rada publica, por convocatoria (скликання), ficheros completos que regenera cada día de pleno y que se
descargan enteros y comprimidos (unos 6 MB en total para la IX):
- plenary_vote_results-skl9: cada votación con sus totales, su resultado y, empaquetado, el voto de cada
  diputado con su facción («id_diputado:id_facción:voto|…»);
- plenary_event_question-skl9: el enunciado de cada votación, p. ej. «Поіменне голосування про проект Закону
  про … (№9020) - в цілому», y la cuestión del orden del día en que se votó;
- plenary_agenda-skl9: las cuestiones del orden del día con el número de registro del proyecto;
- billinfo_list-skl9 (registro de proyectos): título, fecha de registro y ficha en itd.rada.gov.ua.
Se recoge la IX convocatoria (desde el 29 de agosto de 2019); la VIII (hasta julio de 2019) no. Los títulos
están en ucraniano: las reglas no los leen y la ficha de la IA los resume en español.

El asunto es el proyecto (de ley, de resolución «постанова»…) por su número de registro: todas sus
votaciones (inclusión en el orden del día, procedimiento abreviado, primera lectura «за основу», enmiendas
«поправка», segunda lectura y «в цілому») van juntas, y la versión revisada «-д» se une a la original (las
alternativas «-1», «-2» y las resoluciones «-П» sobre un proyecto son asuntos aparte). Los proyectos 0xxx
son los de tratados internacionales (ratificación, adhesión, denuncia). «в цілому» (en su conjunto) es la
votación final; la primera lectura «за основу» queda como «otra». Las votaciones sin proyecto se agrupan por
cuestión del orden del día (nombramientos, ceses), las de procedimiento por día, y las demás (peticiones de
diputados al presidente, «депутатський запит») van cada una en su asunto.

La recogida baja cada vez los ficheros enteros (tardan segundos; la IX entera se procesa en ~20 s) y guarda
lo votado desde dos semanas antes de la última fecha recogida.

Ojo: la facción que da la Rada es la actual de cada diputado, recodificada en todo el histórico, no la del
día de la votación (los antiguos diputados de ОПЗЖ, prohibida en 2022, figuran en «Plataforma por la Vida y la
Paz», «Restauración de Ucrania» o como no adscritos también en 2019-2022). Los códigos de facción son los de
la Rada precedidos de la convocatoria («9-1»), porque cada convocatoria numera las suyas.
"""

import csv
import io
import json
import re
import zipfile
from datetime import date, timedelta

from .modelo import Asunto, Fuente, Votacion

FUENTE = Fuente(
    codigo="ukr", pais="UKR", nombre="Verjovna Rada de Ucrania", corto="Ucrania", tipo="parlamento",
    detalle="nominal", web="https://www.rada.gov.ua", desde=2019, idioma="otro",
    licencia="Datos abiertos de la Verjovna Rada (CC BY 4.0)",
    camaras={"ukr-r": ("Verjovna Rada", "Rada", 450)},
    partidos={
        "9-0": ("Diputados no adscritos", "No adscr.", "#898781"),
        "9-1": ("Servidor del Pueblo", "SN", "#38b34a"),
        "9-2": ("Plataforma de Oposición-Por la Vida", "OPZZh", "#1b62b0"),
        "9-3": ("Unión Panucraniana «Patria»", "Batk.", "#ed1c24"),
        "9-4": ("Solidaridad Europea", "ES", "#1b3892"),
        "9-5": ("Voz (Holos)", "Holos", "#fa4616"),
        "9-6": ("Grupo «Por el Futuro»", "ZM", "#5c068c"),
        "9-7": ("Grupo «Confianza» (Dovira)", "Dovira", "#1a9daa"),
        "9-8": ("Grupo «Partido Por el Futuro»", "ZM", "#5c068c"),
        "9-9": ("Grupo «Plataforma por la Vida y la Paz»", "PZZhM", "#21409a"),
        "9-10": ("Grupo «Restauración de Ucrania»", "VU", "#e6b800"),
    },
    notas=("Todas las votaciones electrónicas del pleno desde la IX convocatoria (29-8-2019). La facción es la "
           "actual de cada diputado (la Rada la recodifica en todo el histórico), no la del día de la votación."),
)

DATOS = "https://data.rada.gov.ua/ogd"
CONVOCATORIAS = {9: "2019-08-29"}  # número -> primer día; la última es la actual
SENTIDO = {"1": "si", "2": "no", "3": "abstencion", "5": "abstencion"}  # 0 ausente y 4 «не голосував» -> no_vota
POR_LOTE = 300

NUMERO = re.compile(r"№\s*(\d{3,5}(?:[-/][0-9A-Za-zА-Яа-яІіЇїЄєҐґ]+)*)")
# Cuestiones del orden del día que reúnen votaciones sin relación entre sí (no sirven de asunto).
CAJON = re.compile(r"запит|додатково включені|продовження|оголошення|реєстрац|різне|порядок роботи|інформаці|заяви", re.I)


def _proyecto(texto):
    """Número de registro del proyecto votado: el del último «(№…)» del enunciado («(№9020)», «(№2178-10)»,
    «(№14271-П)»); si no lo hay, el primer «№» que no sea de una enmienda («проектів законів №9156, №9156-1»)."""
    t = texto or ""
    entre = list(re.finditer(r"\(\s*" + NUMERO.pattern, t))
    if entre:
        return entre[-1].group(1).rstrip("-/")
    for m in NUMERO.finditer(t):
        antes = t[max(0, m.start() - 30):m.start()].lower()
        if "поправ" not in antes and "пропозиц" not in antes:
            return m.group(1).rstrip("-/")
    return None


def _clave(numero):
    """La versión revisada («2285-д») es el mismo proyecto que la original."""
    return re.sub(r"-[дД]$", "", numero)


PROCEDIMIENTO = ("порядку денного", "порядок денний", "скороченою процедурою", "скорочення терміну", "скорочення строк",
                 "направлення на повторне", "повторне перше читання", "повернення на доопрацювання",
                 "повернення до розгляду", "доручення", "невідкладним", "об'єднання обговорення", "черговості",
                 "порядку розгляду", "порядок розгляду", "продовження", "перерв", "запрошення", "порядок роботи",
                 "відсторонення", "пропозицію народного депутата", "пропозицію голови", "пропозицію першого заступника",
                 "игнальне голосування", "рейтингове голосування", "без обговорення", "зняття з розгляду",
                 "в пленарному режимі", "переголосування", "зміну порядку")


TRATADO = re.compile(r"ратифікац|угод|конвенц|протокол|договор|приєднання україни|денонсац|меморандум|статут|вихід україни")


def tipo_asunto(numero, titulo):
    t = re.sub(r"\s+", " ", (titulo or "").lower().replace("’", "'"))
    # Los proyectos 0001-0999 de la IX son los de tratados (los 08xx-09xx del 29-8-2019 son proyectos
    # heredados de la VIII, no tratados: por eso se pide además una palabra de tratado en el título).
    if ((numero or "").startswith("0") and TRATADO.search(t)) or re.match(
            r"про[еє]кт закону про (ратифікацію|приєднання україни|денонсацію|вихід україни|зупинення дії)", t):
        return "tratado"
    if re.match(r"про[еє]кт (\w+ )?(закону|кодексу)|пропозиці\w* президента", t):
        return "ley"
    if re.search(r"скасування рішення|порядок денний|порядку денного|календарний план|регламент верховної ради|"
                 r"розклад засідань|організацію роботи", t):
        return "procedimiento"
    if re.search(r"призначенн|звільненн|обранн|відставк|кандидатур|припинення повноважень|згод\w* на призначення", t):
        return "nombramiento"
    if re.match(r"про[еє]кт (постанови|заяви|звернення)", t) or re.search(r"заяв[аиу]|звернення", t):
        return "resolucion"
    if "запит" in t:
        return "mocion"
    return "otro"


def _partes(texto):
    """(acción, fase) de un enunciado: lo que va antes del título del proyecto («розгляд за скороченою
    процедурою») y lo que va después de su número («- в цілому»). Las palabras clave se buscan solo ahí,
    para que un título como «…про продовження строку мобілізації» no pase por procedimiento."""
    t = (texto or "").lower().replace("’", "'")
    m = re.search(r"про[еє]кт", t)
    accion = t[:m.start()] if m else t
    n = list(re.finditer(r"\(\s*№[^)]*\)", t))
    fase = t[n[-1].end():] if n else (t if not m else "")
    return accion, fase


def tipo_votacion(texto, tipo_a):
    if not (texto or "").strip():
        return "otra"  # hay alguna votación sin enunciado
    accion, fase = _partes(texto)
    clave = accion + " | " + fase
    if re.search(r"поправ\w* №\s*\d|пропозиці\w* №\s*\d", accion):
        return "enmienda"
    if any(k in clave for k in PROCEDIMIENTO):
        return "procedimiento"
    if tipo_a == "procedimiento":
        return "procedimiento"
    if "в цілому" in fase:
        return "nombramiento" if tipo_a == "nombramiento" else "final"
    if any(k in fase for k in ("за основу", "першому читанні", "другому читанні")):
        return "otra"
    if tipo_a == "nombramiento":
        return "nombramiento"
    if tipo_a in ("mocion", "resolucion", "tratado", "otro"):
        return "final"  # «про підтримку запиту…», «про проект Постанови (№…)» sin fase: se vota el conjunto
    return "otra"


def _limpio(texto):
    """Enunciado de la votación sin «Поіменне голосування про», el número ni la fase: el título del asunto."""
    t = re.sub(r"^\s*(Поіменне|Сигнальне|Рейтингове)?\s*голосування\s+(про|щодо|за)\s+", "", texto or "", flags=re.I)
    t = re.sub(r"\s*\(№[^)]*\)\s*(-\s*.*)?$", "", t)
    return re.sub(r"\s+", " ", t).strip()[:400]


def _csv(ruta, sep=","):
    with zipfile.ZipFile(ruta) as z:
        with z.open(z.namelist()[0]) as f:
            yield from csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig"), delimiter=sep)


def _entero(valor):
    valor = (valor or "").strip()
    return int(valor) if valor.lstrip("-").isdigit() else None


def _json_zip(ruta):
    with zipfile.ZipFile(ruta) as z:
        return json.loads(z.read(z.namelist()[0]).decode("utf-8-sig"))


def cargar_convocatoria(ctx, skl, actual, desde_fecha):
    caduca = 12 if actual else None
    base = f"{DATOS}/zal/ppz/skl{skl}"

    def fichero(url, nombre):
        return ctx.cache(url, f"skl{skl}_{nombre}", caduca_horas=caduca, timeout=300)

    diputados = {str(m["id_mp"]): m["name"] for m in json.loads(fichero(f"{base}/dict/mps.json", "mps.json").read_text("utf-8-sig"))["mp"]}
    facciones = {str(f["id"]): f["name"] for f in json.loads(fichero(f"{base}/dict/factions.json", "factions.json").read_text("utf-8-sig"))["faction"]}
    for fid, nombre in facciones.items():
        if f"{skl}-{fid}" not in FUENTE.partidos:
            ctx.partido(f"{skl}-{fid}", nombre)
    proyectos = {b["registrationNumber"]: b for b in _json_zip(
        fichero(f"{DATOS}/zpr/skl{skl}/billinfo_list-skl{skl}.zip", "billinfo_list.zip"))}
    orden = {r["id_question"]: (r["number_question"], r["name_question"])
             for r in _csv(fichero(f"{base}/plenary_agenda-skl{skl}-csv.zip", "agenda.zip"))}
    eventos = {r["id_event"]: r for r in _csv(fichero(f"{base}/plenary_event_question-skl{skl}.zip", "eventos.zip"))
               if r["type_event"] == "0" and r["id_event"]}

    # 1. Asunto de cada votación (con todo el histórico de la convocatoria, para que el título y la fecha
    #    del asunto no dependan de qué votaciones entran en esta recogida).
    asuntos, de_votacion, tipos = {}, {}, {}
    for eid in sorted(eventos, key=int):
        e = eventos[eid]
        texto = e["name_event"]
        num_orden, titulo_orden = orden.get(e["id_question"], ("0", ""))
        numero = _proyecto(texto) or (num_orden if re.match(r"\d{3,5}", num_orden or "") else None)
        fecha = (e["date_event"] or e["date_agenda"])[:10]
        if numero:
            clave = _clave(numero)
            if f"ukr:{skl}:{clave}" not in asuntos:
                b = proyectos.get(clave) or proyectos.get(numero)
                titulo = (b["name"] if b else None) or (titulo_orden if num_orden in (numero, clave) else None) or _limpio(texto)
                asuntos[f"ukr:{skl}:{clave}"] = Asunto(
                    id=f"ukr:{skl}:{clave}", titulo=titulo[:400], tipo=tipo_asunto(clave, titulo),
                    fecha=(b["registrationDate"][:10] if b and b.get("registrationDate") else fecha), codigo=f"№ {clave}",
                    url=f"https://itd.rada.gov.ua/billInfo/Bills/Card/{b['id']}" if b else None)
            aid = f"ukr:{skl}:{clave}"
        elif titulo_orden and not CAJON.search(titulo_orden) and tipo_votacion(texto, "otro") != "procedimiento":
            aid = f"ukr:{skl}:q{e['id_question']}"  # p. ej. «Про призначення членів Рахункової палати»
            asuntos.setdefault(aid, Asunto(id=aid, titulo=titulo_orden[:400], tipo=tipo_asunto(None, titulo_orden), fecha=fecha))
        elif tipo_votacion(texto, "otro") == "procedimiento":
            aid = f"ukr:{skl}:proc:{fecha}"
            asuntos.setdefault(aid, Asunto(id=aid, titulo=f"Votaciones de procedimiento del {fecha}", tipo="procedimiento", fecha=fecha))
        else:
            aid = f"ukr:{skl}:v{eid}"  # un deputatski zapyt, una propuesta suelta…
            titulo = _limpio(texto) or titulo_orden or f"Votación {eid} sin enunciado"
            asuntos[aid] = Asunto(id=aid, titulo=titulo[:400], tipo=tipo_asunto(None, titulo), fecha=fecha)
        de_votacion[eid] = aid
        tipos[eid] = tipo_votacion(texto, asuntos[aid].tipo)

    # 2. Votaciones con el voto de cada diputado, por lotes (el fichero entero no cabe cómodo en memoria).
    lote = []

    def guardar():
        if lote:
            ctx.guardar([asuntos[a] for a in dict.fromkeys(v.asunto_id for v in lote)], lote)
            lote.clear()

    n = 0
    for r in _csv(fichero(f"{base}/plenary_vote_results-skl{skl}.zip", "votaciones.zip"), "\t"):
        eid = r["id_event"]
        e = eventos.get(eid)
        fecha = ((e["date_event"] or e["date_agenda"]) if e else r["date_agenda"])[:10]
        if fecha < desde_fecha:
            continue
        if eid not in de_votacion:
            ctx.log(f"   ! votación {eid} ({fecha}) sin enunciado en el fichero de eventos: no se guarda")
            continue
        votos = []
        for trozo in r["results"].split("|"):
            partes = trozo.split(":")
            if len(partes) < 3:
                continue
            mp, fac, voto = partes[:3]
            votos.append((f"ukr:{skl}:{mp}", diputados.get(mp), f"{skl}-{fac}", SENTIDO.get(voto, "no_vota")))
        lote.append(Votacion(
            id=f"ukr:{skl}:{eid}", fecha=fecha, asunto_id=de_votacion[eid], camara="ukr-r", numero=int(eid),
            texto=re.sub(r"^\s*Поіменне голосування\s+", "", e["name_event"])[:600], tipo=tipos[eid],
            a_favor=_entero(r["for"]), en_contra=_entero(r["against"]), abstenciones=_entero(r["abstain"]),
            no_votan=(_entero(r["not_voting"]) or 0) + (_entero(r["absent"]) or 0),
            resultado={"1": "aprobada", "0": "rechazada"}.get(r["voting_result"].strip()),
            url=f"https://w1.c1.rada.gov.ua/pls/radan_gs{skl:02d}/ns_golos?g_id={eid}", votos=votos))
        n += 1
        if len(lote) >= POR_LOTE:
            guardar()
    guardar()
    ctx.log(f"   convocatoria {skl}: {n} votaciones desde {desde_fecha}")


def recoger(ctx):
    cerradas = set(ctx.marca("cerradas", []))
    inicio = f"{ctx.desde}-01-01"
    ultima = ctx.ultima_fecha()
    if ultima and not ctx.completo:  # se repasan dos semanas por si la Rada corrige algo
        inicio = max(inicio, (date.fromisoformat(ultima) - timedelta(days=14)).isoformat())
    numeros = sorted(CONVOCATORIAS)
    for i, skl in enumerate(numeros):
        actual = skl == numeros[-1]
        fin = CONVOCATORIAS[numeros[i + 1]] if not actual else None
        if fin and (fin < f"{ctx.desde}-01-01" or (skl in cerradas and not ctx.completo)):
            continue
        cargar_convocatoria(ctx, skl, actual, inicio)
        if not actual:
            cerradas.add(skl)
            ctx.poner_marca("cerradas", sorted(cerradas))
