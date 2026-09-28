"""Polonia: votaciones del Sejm (API oficial, https://api.sejm.gov.pl).

La API da, por legislatura (kadencja) y sesión (posiedzenie), cada votación electrónica con el voto de
cada diputado y su club. Se recogen la IX (2019-2023) y la X (desde noviembre de 2023). Los títulos
están en polaco: las reglas no los leen y la ficha de la IA los resume en español.
"""

import hashlib
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from .modelo import Asunto, Fuente, Votacion

FUENTE = Fuente(
    codigo="pol", pais="POL", nombre="Sejm de la República de Polonia", corto="Polonia", tipo="parlamento",
    detalle="nominal", web="https://www.sejm.gov.pl", desde=2019, idioma="otro",
    licencia="Datos abiertos del Sejm (reutilización libre con cita de la fuente)",
    camaras={"pol-s": ("Sejm", "Sejm", 460)},
    partidos={
        "PiS": ("Ley y Justicia", "PiS", "#1d4e9e"), "KO": ("Coalición Cívica", "KO", "#eb6834"),
        "PSL-TD": ("Partido Campesino (Tercera Vía)", "PSL", "#1baf7a"), "PSL-KP": ("Coalición Polaca", "PSL", "#1baf7a"),
        "Polska2050-TD": ("Polonia 2050 (Tercera Vía)", "PL2050", "#eda100"), "Polska2050": ("Polonia 2050", "PL2050", "#eda100"),
        "Lewica": ("La Izquierda", "Lewica", "#e34948"), "Konfederacja": ("Confederación", "Konf.", "#7a5c3e"),
        "Razem": ("Juntos", "Razem", "#e87ba4"), "Kukiz15": ("Kukiz'15", "K'15", "#52514e"),
        "niez.": ("No adscritos", "No adscr.", "#898781"),
    },
    notas="Votaciones electrónicas del pleno; las elecciones con varias candidaturas (por lista) no se recogen.",
)

API = "https://api.sejm.gov.pl/sejm"
LEGISLATURAS = {9: "2019-11-12", 10: "2023-11-13"}
SENTIDO = {"YES": "si", "NO": "no", "ABSTAIN": "abstencion"}


def tipo_votacion(texto):
    t = (texto or "").lower()
    if any(k in t for k in ("całości", "całość")):
        return "final"
    if any(k in t for k in ("kandydatur", "powołani", "wybor", "wybór", "odwołani")):
        return "nombramiento"
    if any(k in t for k in ("poprawk", "wniosk mniejszości", "wnioski mniejszości", "wniosek mniejszości", "odrzucenie")):
        return "enmienda"
    if any(k in t for k in ("przerw", "odrocz", "zamknięcie dyskusji", "proceduraln", "skrócenie terminu",
                            "bez dyskusji", "przystąpienie do", "porządk", "odesłanie", "kworum")):
        return "procedimiento"
    if "przyjęci" in t or "wniosku z druku" in t:
        return "final"
    return "otra"


def tipo_asunto(titulo):
    t = titulo.lower()
    if "ratyfikacji" in t:
        return "tratado"
    if "projekt" in t and "ustaw" in t:
        return "ley"
    if "uchwał" in t:
        return "resolucion"
    if any(k in t for k in ("powołanie", "wybór", "odwołanie", "wotum")):
        return "nombramiento"
    if "składach" in t or "regulamin" in t:
        return "procedimiento"
    return "otro"


def asunto_de(termino, sesion, titulo):
    """Id, título limpio y código (druk) del asunto de una votación."""
    t = re.sub(r"\s+", " ", titulo or "").strip()
    if re.match(r"\d+\. posiedzenie Sejmu", t) or t.lower().startswith("głosowanie proceduralne"):
        return f"pol:{termino}:{sesion}:proc", f"Votaciones de procedimiento, {sesion}.ª sesión", None, "procedimiento"
    limpio = re.sub(r"^Pkt\.\s*\d+\.?\s*", "", t)
    druk = re.search(r"\(druki? nr ([\d, i-]+)", limpio)
    numero = re.match(r"\d+", druk.group(1)).group(0) if druk else None
    limpio = re.sub(r"\s*\(druki? nr [^)]*\)\s*$", "", limpio)
    if numero:
        return f"pol:{termino}:druk{numero}", limpio, f"druk {numero}", tipo_asunto(limpio)
    return f"pol:{termino}:{hashlib.sha1(limpio.encode()).hexdigest()[:10]}", limpio, None, tipo_asunto(limpio)


def resultado(d):
    si, no = d.get("yes") or 0, d.get("no") or 0
    if d.get("majorityType") in (None, "SIMPLE_MAJORITY"):
        return "aprobada" if si > no else "rechazada"
    return "aprobada" if d.get("majorityVotes") and si >= d["majorityVotes"] else "rechazada"


def recoger(ctx):
    hechas = set(ctx.marca("sesiones", []))
    limite = (date.today() - timedelta(days=4)).isoformat()
    for termino, inicio in LEGISLATURAS.items():
        if int(inicio[:4]) < ctx.desde - 4:
            continue
        dias = ctx.json(f"{API}/term{termino}/votings")
        sesiones = sorted({d["proceeding"] for d in dias})
        ultima_fecha = {s: max(d["date"] for d in dias if d["proceeding"] == s) for s in sesiones}
        for sesion in sesiones:
            clave = f"{termino}:{sesion}"
            if clave in hechas and not ctx.completo:
                continue
            lista = [v for v in ctx.json(f"{API}/term{termino}/votings/{sesion}") if v.get("kind") != "ON_LIST"]
            with ThreadPoolExecutor(16) as ex:
                detalles = list(ex.map(lambda v: ctx.json(f"{API}/term{termino}/votings/{sesion}/{v['votingNumber']}"), lista))
            asuntos, votaciones = {}, []
            for d in detalles:
                aid, titulo, codigo, tipo_a = asunto_de(termino, sesion, d.get("title"))
                fecha = d["date"][:10]
                url_a = f"https://www.sejm.gov.pl/Sejm{termino}.nsf/druk.xsp?nr={codigo.split()[-1]}" if codigo else None
                asuntos.setdefault(aid, Asunto(id=aid, titulo=titulo[:400], tipo=tipo_a, fecha=fecha, codigo=codigo, url=url_a))
                texto = " · ".join(x for x in (d.get("description"), d.get("topic")) if x) or None
                votos = []
                for v in d.get("votes") or []:
                    club = v.get("club") or "niez."
                    if club not in FUENTE.partidos:
                        ctx.partido(club)
                    nombre = " ".join(x for x in (v.get("firstName"), v.get("lastName")) if x)
                    votos.append((f"pol:{termino}:{v['MP']}", nombre, club, SENTIDO.get(v.get("vote"), "no_vota")))
                votaciones.append(Votacion(
                    id=f"pol:{termino}:{sesion}:{d['votingNumber']}", fecha=fecha, asunto_id=aid, camara="pol-s",
                    numero=d["votingNumber"], texto=texto, tipo=tipo_votacion(texto),
                    a_favor=d.get("yes"), en_contra=d.get("no"), abstenciones=d.get("abstain"),
                    no_votan=d.get("notParticipating"), mayoria=d.get("majorityType"), resultado=resultado(d),
                    url=(f"https://www.sejm.gov.pl/Sejm{termino}.nsf/agent.xsp?symbol=glosowania&NrKadencji={termino}"
                         f"&NrPosiedzenia={sesion}&NrGlosowania={d['votingNumber']}"),
                    votos=votos))
            ctx.guardar(list(asuntos.values()), votaciones)
            ctx.log(f"   legislatura {termino}, sesión {sesion}: {len(votaciones)} votaciones")
            if ultima_fecha[sesion] < limite:
                hechas.add(clave)
                ctx.poner_marca("sesiones", sorted(hechas))
