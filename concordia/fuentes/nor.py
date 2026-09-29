"""Noruega: votaciones del Storting (API de datos abiertos, https://data.stortinget.no).

La API da, por sesión (de octubre a septiembre), los asuntos (sak) del Storting; por cada sak, sus votaciones
(votering) y, cuando se vota con pulsadores, el voto de cada representante con su partido. Se recoge desde la
sesión 2018-2019 (solo lo votado desde enero de 2019). Los títulos están en noruego: las reglas no los leen y
la ficha de la IA los resume en español.

- El asunto es la sak (título corto, «korttittel»; el largo va en extra «etiqueta»). Se vota sobre propuestas
  (forslag): primero las de los partidos en minoría («Forslag nr. 3 på vegne av SV og R»: «enmienda»), luego la
  recomendación de la comisión («Innstillingens tilråding», o en las leyes «Lovens overskrift og loven i sin
  helhet»: «final»); las partes sueltas de la recomendación («Romertall II», «Stor bokstav B») quedan como
  «otra» y los artículos, «parcial». Las sak tratadas juntas (el presupuesto revisado, p. ej.) comparten
  votaciones: cada una va solo al asunto de la sak de id más bajo.
- En las propuestas de representantes (representantforslag) y de reforma constitucional (grunnlovsforslag) la
  comisión suele recomendar no aprobarlas («Ikke vedtatt», «vedlegges protokollen»). Se pide la decisión
  (voteringsvedtak) de las votaciones de la recomendación, también del lado «innstillingen» de las votaciones
  alternativas: si todo lo que recomienda es no aprobar, su votación pasa a «procedimiento» y las de las
  propuestas a «final», para que el asunto salga rechazado y no aprobado (en una reforma constitucional, igual si
  ninguna decisión es «Grunnlovsvedtak»: cuenta el voto de la reforma, que necesita dos tercios).
- Muchas votaciones se hacen sin pulsadores (casi todas las unánimes, «Enstemmig vedtatt»): se guardan con su
  resultado y sin voto nominal. En el Storting no hay abstención: se vota a favor, en contra o no se está.
- Certificado: la raíz de data.stortinget.no («Buypass Class 2 Root CA») no está en el almacén de Windows
  hasta que Windows la descarga; en Windows hay que poner SSL_CERT_FILE en .env (ver http_util.py).
- La API corta con 429 a partir de unas 100 peticiones por minuto: se va a unas 75-85 por minuto. Recogerlo todo desde
  2019 son ~35.000 peticiones (unas 7 h), así que cada recogida se para a los PRESUPUESTO_MIN minutos y la
  siguiente sigue donde se quedó (marca de las sak vistas en cada sesión); la sesión en curso va primero.
"""

import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

from .. import http_util
from .modelo import Asunto, Fuente, Votacion

FUENTE = Fuente(
    codigo="nor", pais="NOR", nombre="Storting de Noruega", corto="Noruega", tipo="parlamento",
    detalle="nominal", web="https://www.stortinget.no", desde=2019, idioma="otro",
    licencia="Norsk lisens for offentlige data (NLOD), Stortinget",
    camaras={"nor-s": ("Storting", "Storting", 169)},
    partidos={
        "A": ("Partido Laborista", "A", "#e11926"),
        "H": ("Partido Conservador", "H", "#87add7"),
        "FrP": ("Partido del Progreso", "FrP", "#004f80"),
        "Sp": ("Partido de Centro", "Sp", "#00843d"),
        "SV": ("Partido de la Izquierda Socialista", "SV", "#b5317c"),
        "R": ("Rojo", "R", "#871212"),
        "V": ("Partido Liberal (Venstre)", "V", "#006666"),
        "MDG": ("Partido Verde", "MDG", "#6a9325"),
        "KrF": ("Partido Demócrata Cristiano", "KrF", "#f0c800"),
        "PF": ("Foco en el Paciente", "PF", "#f69465"),
        "Uav": ("Independientes", "Uav", "#898781"),
    },
    notas=("Votaciones del pleno desde enero de 2019; las que se hacen sin pulsadores (casi siempre unánimes) "
           "tienen resultado pero no voto nominal. No hay abstención en el Storting."),
)

API = "https://data.stortinget.no/eksport"
SAK = "https://www.stortinget.no/no/Saker-og-publikasjoner/Saker/Sak"
INTERVALO = 0.7            # segundos entre peticiones (la API admite unas 100 por minuto)
PRESUPUESTO_MIN = int(os.environ.get("CONCORDIA_NOR_MINUTOS") or 40)  # minutos por recogida
POR_LOTE = 40              # sak por guardado
SENTIDO = {2: "si", 3: "no", 1: "no_vota"}  # voteringsresultat: 1 ikke_tilstede, 2 for, 3 mot
# Enumeraciones del formato JSON (en el XML van con su nombre).
BUDSJETT, LOVSAK = 1, 3                                    # sak.type (2: alminneligsak)
PROPOSISJON, MELDING, REDEGJORELSE, REPRESENTANTFORSLAG, GRUNNLOVSFORSLAG = 1, 2, 3, 4, 5  # sak.dokumentgruppe
BEHANDLET, TIL_BEHANDLING = 1, 2                           # sak.status
RECHAZO = re.compile(r"ikke vedtatt|vedlegges|bifalles ikke|avvis|forkast", re.I)

http_util.ritmo("data.stortinget.no", INTERVALO)


def _get(url):
    """GET de la API en JSON, a ritmo de INTERVALO entre peticiones (compartido por todos los hilos)."""
    return http_util.json_url(url, retries=5, headers={"Accept": "application/json"})


def _fecha(valor):
    """«/Date(1776778215703+0200)/» -> «2026-04-21» (fecha local de Noruega)."""
    m = re.search(r"\((-?\d+)(?:([+-]\d{2})(\d{2}))?\)", valor or "")
    if not m:
        return None
    signo, horas, minutos = (m.group(2) or "+00")[0], int(m.group(2) or 0), int(m.group(3) or 0)
    zona = timezone(timedelta(hours=horas, minutes=int(signo + str(minutos))))
    return datetime.fromtimestamp(int(m.group(1)) / 1000, zona).date().isoformat()


def _cuenta(v, clave):
    """Totales de la votación personal; en las que se hacen sin pulsadores la API pone -1."""
    n = v.get(clave)
    return n if isinstance(n, int) and n >= 0 else None


def _titulo(sak):
    return re.sub(r"\s+", " ", sak.get("korttittel") or sak.get("tittel") or f"Sak {sak['id']}").strip()


def tipo_asunto(sak):
    t = _titulo(sak).lower()
    if sak.get("type") != LOVSAK and "samtykke til" in t and re.search(
            r"avtale|konvensjon|protokoll|traktat|eøs|overenskomst|ratifika|tiltred|oppsigelse|charter|vedtekt", t):
        return "tratado"
    if re.search(r"\bvalg (av|til)\b|suppleringsvalg|oppnevning", t):
        return "nombramiento"
    if sak.get("type") in (LOVSAK, BUDSJETT) or sak.get("dokumentgruppe") == GRUNNLOVSFORSLAG:
        return "ley"
    if re.search(r"forretningsorden", t):
        return "procedimiento"
    if sak.get("dokumentgruppe") == REPRESENTANTFORSLAG:
        return "mocion"
    return "resolucion"


def tipo_votacion(tema, tipo_a):
    t = re.sub(r"\s+", " ", (tema or "").lower()).strip()
    if "loven i sin helhet" in t or "lovens overskrift" in t:
        return "final"
    if re.search(r"utsett|sendes tilbake|sende saken tilbake|oversendes regjeringen uten|dagsorden", t):
        return "procedimiento"
    if t.startswith("alternativ") or re.match(r"forslag(ene)?\b", t) or "på vegne av" in t:
        return "enmienda"
    if re.search(r"§|\bledd\b|punktum|kapittel|\bkap\.|\bpost\b|\bposter\b", t):
        return "parcial"
    if re.search(r"(innstillingens|komiteens) tilråding|^innstillingen\b|^tilrådingen\b|komiteens innstilling", t) \
            and not re.search(r"romertall|bokstav|resten", t):
        return "nombramiento" if tipo_a == "nombramiento" else "final"
    if tipo_a in ("nombramiento", "procedimiento"):
        return tipo_a
    return "otra"  # «Romertall II», «Stor bokstav B», «Rammeområde 3»: partes de la recomendación


def _sak(sak, desde, conocidas):
    """Votaciones de una sak desde `desde`: [(votering, fecha, votos, códigos de la decisión, nueva)].

    Los votos (voteringsresultat) se piden solo para las votaciones nuevas con pulsadores; los códigos de la
    decisión (voteringsvedtak), solo para la recomendación de la comisión en propuestas de representantes y
    de reforma constitucional."""
    lista = _get(f"{API}/voteringer?sakid={sak['id']}&format=json").get("sak_votering_liste") or []
    lista = [(v, _fecha(v.get("votering_tid"))) for v in lista]
    lista = [(v, f, f"nor:{v['votering_id']}" not in conocidas) for v, f in lista if f and f >= desde]
    mira_decision = sak.get("dokumentgruppe") in (REPRESENTANTFORSLAG, GRUNNLOVSFORSLAG) and any(n for *_, n in lista)
    salida = []
    for v, fecha, nueva in lista:
        votos = None
        if nueva and v.get("personlig_votering"):
            votos = _get(f"{API}/voteringsresultat?voteringid={v['votering_id']}&format=json").get("voteringsresultat_liste") or []
        codigos = None
        tema = (v.get("votering_tema") or "").strip().lower()
        if mira_decision and (tipo_votacion(tema, "mocion") in ("final", "otra") or tema.startswith("alternativ")):
            vedtak = _get(f"{API}/voteringsvedtak?voteringid={v['votering_id']}&format=json").get("voteringsvedtak_liste") or []
            codigos = [x.get("vedtak_kode") or "" for x in vedtak]
        salida.append((v, fecha, votos, codigos, nueva))
    return sak, salida


def _procesar(ctx, sak, salida, asignadas):
    """Asunto y votaciones (solo las nuevas) de una sak.

    Las sak que se tratan juntas (p. ej. el presupuesto revisado, repartido en varias sak) comparten las mismas
    votaciones: cada votación va al asunto de la primera sak que la trae (la de id más bajo)."""
    tipo_a = tipo_asunto(sak)
    titulo = _titulo(sak)
    extra = {"komite": (sak.get("komite") or {}).get("navn")}
    largo = re.sub(r"\s+", " ", sak.get("tittel") or "").strip()
    if largo and largo.lower() != titulo.lower():
        extra["etiqueta"] = largo[:300]
    asunto = Asunto(id=f"nor:{sak['id']}", titulo=titulo[:400], tipo=tipo_a,
                    fecha=min((f for _, f, *_ in salida), default=None),
                    codigo=(sak.get("henvisning") or "")[:150] or None, url=f"{SAK}/?p={sak['id']}",
                    extra={k: v for k, v in extra.items() if v} or None)
    # ¿La comisión solo recomienda no aprobar la propuesta? (representantforslag y grunnlovsforslag: se mira la
    # decisión de las votaciones de su recomendación, también del lado «innstillingen» de las votaciones
    # alternativas). En una reforma constitucional, si ninguna decisión es «Grunnlovsvedtak» la reforma no salió:
    # lo que cuenta es la votación de la propia propuesta (que necesita dos tercios), no la de la recomendación.
    decisiones = [c for *_, c, _ in salida if c]
    rechazo = bool(decisiones) and all(RECHAZO.search(x) for c in decisiones for x in c)
    if sak.get("dokumentgruppe") == GRUNNLOVSFORSLAG:
        rechazo = not any("grunnlov" in x.lower() for c in decisiones for x in c)
    votaciones = []
    for v, fecha, votos, codigos, nueva in salida:
        if not nueva or asignadas.setdefault(v["votering_id"], sak["id"]) != sak["id"]:
            continue
        tema = re.sub(r"\s+", " ", v.get("votering_tema") or "").strip()
        tipo = tipo_votacion(tema, tipo_a)
        texto = tema
        if v.get("votering_resultat_type_tekst"):
            texto += f" ({v['votering_resultat_type_tekst'].rstrip('.')})"
        if codigos:
            texto += f" [decisión: {', '.join(dict.fromkeys(x.rstrip('.') for x in codigos))}]"
        if rechazo:
            if codigos:
                tipo = "procedimiento"   # la comisión recomienda no aprobar: votarla es archivar la propuesta
            elif tipo == "enmienda":
                tipo = "final"           # lo que de verdad se vota es la propuesta
        elif codigos and tipo == "enmienda":
            tipo = "final"               # lado «innstillingen» de una votación alternativa: la recomendación
        lista = None
        if votos is not None:
            lista = []
            for r in votos:
                rep = r.get("representant") or {}
                partido = (rep.get("parti") or {}).get("id") or "Uav"
                if partido not in FUENTE.partidos:
                    ctx.partido(partido, (rep.get("parti") or {}).get("navn"), partido)
                nombre = " ".join(x for x in (rep.get("fornavn"), rep.get("etternavn")) if x)
                lista.append((f"nor:{rep.get('id')}", nombre or None, partido, SENTIDO.get(r.get("votering"), "no_vota")))
        votaciones.append(Votacion(
            id=f"nor:{v['votering_id']}", fecha=fecha, asunto_id=asunto.id, camara="nor-s", numero=v["votering_id"],
            texto=texto[:600] or None, tipo=tipo, a_favor=_cuenta(v, "antall_for"),
            en_contra=_cuenta(v, "antall_mot"), abstenciones=0 if lista else None, no_votan=_cuenta(v, "antall_ikke_tilstede"),
            resultado="aprobada" if v.get("vedtatt") else "rechazada",
            url=f"{SAK}/Voteringsoversikt/votering-detaljer/?p={sak['id']}&dnid={v.get('behandlingsrekkefoelge') or 1}"
                f"&vt={v['votering_id']}",
            votos=lista))
    return asunto, votaciones


def recoger(ctx):
    reloj = time.monotonic()
    hoy = date.today()
    desde = f"{ctx.desde}-01-01"
    sesiones = []
    for s in _get(f"{API}/sesjoner?format=json")["sesjoner_liste"]:
        fra, til = _fecha(s["fra"]), _fecha(s["til"])
        if til and fra and til >= desde and fra <= hoy.isoformat():
            sesiones.append((s["id"], til))
    sesiones.sort(reverse=True)  # la sesión en curso primero; luego hacia atrás
    cerradas = set(ctx.marca("sesiones_cerradas", []))
    vistas = ctx.marca("saker_vistas", {})  # {sesión: {sak: sist_oppdatert_dato}} de las sesiones a medias
    conocidas = set() if ctx.completo else {r[0] for r in ctx.con.execute("SELECT id FROM votacion WHERE fuente='nor'")}
    asignadas = {}  # votering -> sak a cuyo asunto va (en esta recogida)
    estable = (hoy - timedelta(days=3)).isoformat()  # una sak tocada hace menos se vuelve a mirar
    for sid, til in sesiones:
        if sid in cerradas and not ctx.completo:
            continue
        hechas = {} if ctx.completo else dict(vistas.get(sid, {}))
        pendientes = []
        for s in {s["id"]: s for s in _get(f"{API}/saker?sesjonid={sid}&format=json")["saker_liste"]}.values():
            cambio = _fecha(s.get("sist_oppdatert_dato")) or ""
            if s.get("status") not in (BEHANDLET, TIL_BEHANDLING) or cambio < desde:
                continue  # sin votaciones, o sin cambios desde el año pedido
            if hechas.get(str(s["id"])) == cambio:
                continue  # ya vista y sin cambios de estado desde entonces
            pendientes.append((s, cambio))
        pendientes.sort(key=lambda p: p[0]["id"])
        ctx.log(f"   sesión {sid}: {len(pendientes)} sak por mirar")
        with ThreadPoolExecutor(4) as ex:
            for i in range(0, len(pendientes), POR_LOTE):
                if time.monotonic() - reloj > PRESUPUESTO_MIN * 60:
                    ctx.log(f"   ! {PRESUPUESTO_MIN} min agotados: la próxima recogida sigue por la sesión {sid}")
                    return
                trozo = pendientes[i:i + POR_LOTE]
                asuntos, votaciones = [], []
                for sak, salida in ex.map(lambda p: _sak(p[0], desde, conocidas), trozo):
                    if salida:
                        asunto, nuevas = _procesar(ctx, sak, salida, asignadas)
                        if nuevas:
                            asuntos.append(asunto)
                            votaciones += nuevas
                if votaciones:
                    ctx.guardar(asuntos, votaciones)
                    conocidas.update(v.id for v in votaciones)
                for s, cambio in trozo:
                    if cambio < estable:
                        hechas[str(s["id"])] = cambio
                vistas[sid] = hechas
                ctx.poner_marca("saker_vistas", vistas)
                ctx.log(f"   {sid}: {min(i + POR_LOTE, len(pendientes))}/{len(pendientes)} sak, {len(votaciones)} votaciones")
        if til < (hoy - timedelta(days=45)).isoformat():
            cerradas.add(sid)
            vistas.pop(sid, None)
            ctx.poner_marca("sesiones_cerradas", sorted(cerradas))
            ctx.poner_marca("saker_vistas", vistas)
