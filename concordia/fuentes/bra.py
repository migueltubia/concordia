"""Brasil: votaciones del Congreso Nacional (Câmara dos Deputados y Senado Federal).

Câmara: ficheros anuales de datos abiertos (https://dadosabertos.camara.leg.br/swagger/api.html#staticfile):
`votacoes-{año}.csv` (cada votación de pleno y comisiones, con descripción, resultado y totales),
`votacoesVotos-{año}.csv` (el voto de cada diputado con su partido en ese momento) y
`votacoesProposicoes-{año}.csv` (la proposición a la que afecta cada votación, con su ementa). Se usan los
CSV porque pesan la mitad que los JSON (el de votos de 2021 pasa de 100 MB) y se leen fila a fila. Solo el
pleno (PLEN); las comisiones no. Las votaciones nominales tienen el voto de cada diputado; las simbólicas
(la mayoría: se aprueban «por los líderes», sin registro) no. De las simbólicas se guardan, sin votos ni
totales, solo las decisivas (aprobación o rechazo del proyecto, de la PEC, de la MP, del PDL) de los
tratados internacionales, que la Cámara aprueba casi siempre así, y de los asuntos que tienen alguna
votación nominal (una urgencia, un destaque), para que tengan resultado; las leyes aprobadas solo de forma
simbólica no se recogen. Las votaciones secretas (autoridades) llegan sin voto individual: solo totales.

Senado: API de datos abiertos (https://legis.senado.leg.br/dadosabertos/votacao?dataInicio=...&dataFim=...,
que sustituye a plenario/lista/votacao), con cada votación nominal del pleno, la materia, su ementa y el
voto de cada senador con su partido. El Senado vota casi todo de forma simbólica (y esas no están en la
API): lo nominal son sobre todo PEC, leyes complementarias y autoridades (embajadores, agencias,
tribunales), estas en votación secreta (solo totales).

El asunto es la proposición (PL 1234/2023, PLP, PEC, MPV, PDL, PRC…), con el mismo id en las dos cámaras
(desde 2019 la numeración es única): `bra:PL-1234-2023`. Los PDL que aprueban el texto de un acuerdo,
tratado o convenio son «tratado». Cuando la Cámara vota el mensaje presidencial de un tratado (MSC) y el
PDL nace en el pleno, el asunto es el PDL que cita la descripción. Títulos (ementas) en portugués.
"""

import csv
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from .modelo import Asunto, Fuente, Votacion

FUENTE = Fuente(
    codigo="bra", pais="BRA", nombre="Congreso Nacional de Brasil", corto="Brasil", tipo="parlamento",
    detalle="nominal", web="https://www.congressonacional.leg.br", desde=2019, idioma="otro",
    licencia="Datos abiertos de la Cámara de Diputados y del Senado Federal (uso libre citando la fuente)",
    camaras={"bra-c": ("Cámara de Diputados", "Cámara", 513), "bra-s": ("Senado Federal", "Senado", 81)},
    partidos={
        "PT": ("Partido de los Trabajadores", "PT", "#c4122d"),
        "PL": ("Partido Liberal", "PL", "#1c2f66"),
        "PR": ("Partido de la República (hoy PL)", "PR", "#1c2f66"),
        "UNIÃO": ("União Brasil", "União", "#2a5caa"),
        "PP": ("Progresistas", "PP", "#6ab0de"),
        "PSD": ("Partido Social Democrático", "PSD", "#f2a900"),
        "MDB": ("Movimiento Democrático Brasileño", "MDB", "#30914d"),
        "REPUBLICANOS": ("Republicanos", "Rep.", "#0d6e8a"),
        "PRB": ("Partido Republicano Brasileño (hoy Republicanos)", "PRB", "#0d6e8a"),
        "PDT": ("Partido Democrático Laborista", "PDT", "#e4572e"),
        "PSB": ("Partido Socialista Brasileño", "PSB", "#f7c600"),
        "PSDB": ("Partido de la Social Democracia Brasileña", "PSDB", "#0a72c0"),
        "PSOL": ("Partido Socialismo y Libertad", "PSOL", "#9e1c47"),
        "PODE": ("Podemos", "Pode", "#38a3a5"),
        "AVANTE": ("Avante", "Avante", "#6a4c93"),
        "PCdoB": ("Partido Comunista de Brasil", "PCdoB", "#8b0000"),
        "CIDADANIA": ("Cidadania", "Cid.", "#ec008c"),
        "PPS": ("Partido Popular Socialista (hoy Cidadania)", "PPS", "#ec008c"),
        "PV": ("Partido Verde", "PV", "#1b9e3e"),
        "NOVO": ("Partido Novo", "Novo", "#f58220"),
        "SOLIDARIEDADE": ("Solidariedade", "SD", "#e76f51"),
        "PRD": ("Partido Renovación Democrática", "PRD", "#23395b"),
        "REDE": ("Rede Sustentabilidad", "Rede", "#00a19a"),
        "MISSÃO": ("Partido Misión", "Missão", "#d4a017"),
        "PSL": ("Partido Social Liberal", "PSL", "#2b4c7e"),
        "DEM": ("Demócratas", "DEM", "#8cc63e"),
        "PTB": ("Partido Laborista Brasileño", "PTB", "#3f3f3f"),
        "PROS": ("Partido Republicano del Orden Social", "PROS", "#f4a261"),
        "PSC": ("Partido Social Cristiano", "PSC", "#3a7d44"),
        "PATRIOTA": ("Patriota", "Patri.", "#2d6a4f"),
        "PATRI": ("Patriota", "Patri.", "#2d6a4f"),
        "PRP": ("Partido Republicano Progresista", "PRP", "#6c757d"),
        "PMN": ("Partido de la Movilización Nacional", "PMN", "#b5838d"),
        "PHS": ("Partido Humanista de la Solidaridad", "PHS", "#9c6644"),
        "PTC": ("Partido Laborista Cristiano (hoy Agir)", "PTC", "#7f5539"),
        "AGIR": ("Agir", "Agir", "#7f5539"),
        "PMB": ("Partido de la Mujer Brasileña", "PMB", "#c77dff"),
        "PPL": ("Partido Patria Libre", "PPL", "#9d0208"),
        "PRTB": ("Partido Renovador Laborista Brasileño", "PRTB", "#588157"),
        "DC": ("Democracia Cristiana", "DC", "#5c677d"),
        "S.PART.": ("Sin partido", "S/P", "#898781"),
    },
    notas=("Votaciones nominales del pleno de las dos cámaras desde 2019 (voto de cada parlamentario); de las "
           "simbólicas (sin registro), solo la aprobación de tratados y de asuntos con alguna votación nominal; "
           "las secretas (autoridades), solo con totales."),
)

CAMARA = "https://dadosabertos.camara.leg.br/arquivos"
API_CAMARA = "https://dadosabertos.camara.leg.br/api/v2"
SENADO = "https://legis.senado.leg.br/dadosabertos"
FICHA_CAMARA = "https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao={}"
FICHA_SENADO = "https://www25.senado.leg.br/web/atividade/materias/-/materia/{}"
MARGEN = 14   # días que se repasan en cada recogida (correcciones de la fuente)
LOTE = 200

SENTIDO_CAMARA = {"Sim": "si", "Não": "no", "Abstenção": "abstencion"}  # Obstrução, Artigo 17 (presidente) -> no_vota
# Senado: «P-NRV» (presente, no registró voto), «Presidente (art. 51 RISF)», licencias, misiones… -> no_vota.
SENTIDO_SENADO = {"Sim": "si", "Não": "no", "Abstenção": "abstencion"}
SIN_PARTIDO = {None, "", "S/Partido", "Sem registro", "S.PART.", "S/PARTIDO", "SEM PARTIDO"}

# Tipos de proposición que no son el asunto sino un trámite dentro de él (requerimientos, recursos,
# enmiendas, destaques, pareceres…). Si una votación solo tiene uno de estos, el asunto es ese.
AUXILIARES = {"REQ", "REC", "EMP", "EMC", "EMR", "ESB", "DTQ", "SBT", "SBE", "PRLP", "PRLE", "PEP", "PPP", "PAR", "RPD",
              "ERD", "EMA", "SSP", "PRL", "RDF", "DVT"}
PREFERENCIA = ["PEC", "PLP", "PL", "MPV", "PLV", "PDL", "PDC", "PRC", "PLN", "MSC"]

NOMBRES_PROPOSICAO = [
    (r"proposta de emenda (?:à|a) constitui[çc][ãa]o", "PEC"),
    (r"projeto de lei complementar", "PLP"),
    (r"projeto de lei de convers[ãa]o", "PLV"),
    (r"projeto de decreto legislativo", "PDL"),
    (r"projeto de resolu[çc][ãa]o", "PRC"),
    (r"medida provis[óo]ria", "MPV"),
    (r"projeto de lei", "PL"),
]
# Ementa de un tratado: «Aprova o texto do Acordo…», o solo el nombre («Acordo sobre…», «Convenção nº 190…»)
# cuando el asunto es el mensaje presidencial o el PDL que nace de él.
TRATADO = re.compile(r"^(?:o |a |os |as )?(?:texto d\w+ )?(?:acordo|tratado|conven[çc][ãa]o|protocolo|conv[êe]nio|"
                     r"memorando|ajuste|estatuto|carta|emendas?|ata|instrumento|decis[ãa]o)\b")
# Aperturas de votación genéricas que no dicen qué se vota.
APERTURA_GENERICA = re.compile(r"^(?:continuação da )?votação,? (?:em )?(?:turno único|primeiro turno|segundo turno)\.?$", re.I)


def _limpio(t):
    return re.sub(r"\s+", " ", t or "").strip()


def _corto(t, n=400):
    t = _limpio(t)
    return t if len(t) <= n else t[:n - 1].rsplit(" ", 1)[0] + "…"


def _num(x):
    try:
        return int(x or 0)
    except ValueError:
        return 0


def _aid(sigla, numero, anio):
    return f"bra:{sigla}-{int(numero)}-{anio}"


def proposicao_citada(texto, siglas=None):
    """«… Projeto de Decreto Legislativo nº 50, de 2026 …» -> ("PDL", 50, 2026)."""
    for patron, sigla in NOMBRES_PROPOSICAO:
        if siglas and sigla not in siglas:
            continue
        m = re.search(patron + r"\s+n[º°o.]*\s*([\d.]+)\s*[,/]?\s*(?:de\s*)?(\d{4})", texto or "", re.I)
        if m:
            return sigla, int(m.group(1).replace(".", "")), int(m.group(2))
    # Abreviado: «PL 2903/2023», «PLP nº 177/2023».
    m = re.search(r"\b(PEC|PLP|PLV|PDL|PRC|MPV|PL)\s*(?:n[º°o.]*\s*)?([\d.]+)\s*/\s*(\d{4})\b", texto or "")
    if m and (not siglas or m.group(1) in siglas):
        return m.group(1), int(m.group(2).replace(".", "")), int(m.group(3))
    return None


def tipo_asunto(sigla, ementa):
    e = (ementa or "").lower()
    if sigla in ("PDL", "PDC", "PDS", "MSC") and (
            re.search(r"\b(?:aprova|submete)\b[^.;]{0,80}\btexto\b", e) or re.search(r"\bades[ãa]o d[oa] brasil", e)
            or TRATADO.match(e)):
        return "tratado"
    if sigla in ("MSF", "OFS") or re.search(r"\belei[çc][ãa]o (?:para|de) ", e) or (
            sigla in ("PDL", "PDC", "PDS", "PRS") and re.search(r"\b(?:indica[çc][ãa]o|escolh[ae])\b", e)):
        return "nombramiento"
    if sigla in ("REQ", "RQS") and re.search(r"\bmo[çc][ãa]o\b|\bvoto de (?:aplauso|louvor|pesar|rep[úu]dio|censura|"
                                            r"solidariedade|congratula)", e):
        return "mocion"
    if sigla in ("REQ", "RQS") and re.search(r"\bconvoca", e):
        return "otro"
    if sigla in ("PL", "PLP", "PEC", "MPV", "PLV", "PLN", "PLS", "PLC"):
        return "ley"
    if sigla in ("PRC", "PRS", "PR"):
        return "procedimiento" if "regimento interno" in e else "resolucion"
    if sigla in ("PDL", "PDC", "PDS"):
        return "resolucion"
    if sigla in ("REQ", "RQS", "REC", "RCP"):
        return "procedimiento"
    return "otro"


def _sin_ec(t):
    """Quita «emenda à Constituição» para que no cuente como enmienda."""
    return re.sub(r"emendas? (?:à|a) constitui[çc][ãa]o|emenda constitucional", "", t)


def tipo_votacion_camara(texto):
    """Tipo de votación según la descripción de la Cámara («Aprovado o Substitutivo…», «Mantido o texto»…)."""
    t = re.sub(r"ressalvad\w*[^.;]*", "", _limpio(texto).lower())
    # Lo que se vota: lo que sigue a «Aprovado/Rejeitada…[, em segundo turno,] o/a/os/as».
    objeto = re.sub(r"^(?:aprovad|rejeitad|mantid|suprimid)\w*\s*(?:,[^,]*,\s*)?(?:(?:o|a|os|as)\s+)?", "", t)
    if t.startswith("votos:") or "eleição" in t:  # elección de autoridades (voto secreto por candidato)
        return "nombramiento"
    if any(k in t for k in ("requerimento", "recurso", "preferência", "apreciação preliminar", "admissibilidade",
                            "minuta", "urgência", "adiamento", "retirada de pauta", "encerramento da discussão",
                            "votação parcelada", "quórum")) or objeto.startswith("inclusão"):
        return "procedimiento"
    if "redação final" in t:
        return "otra"
    if "do senado" in t:  # enmiendas o sustitutivo del Senado a un proyecto de la Cámara
        return "enmienda"
    # «Emendas ao Substitutivo» son enmiendas; el substitutivo, la subemenda substitutiva (global) o la emenda
    # aglutinativa substitutiva son el texto entero del proyecto.
    if re.match(r"(?:sub)?emendas?\b", objeto) and not re.match(r"(?:sub)?emenda (?:aglutinativa )?substitutiva", objeto):
        return "enmienda"
    if "substitutiv" in objeto[:60]:
        return "final"
    if any(k in t for k in ("mantido o texto", "suprimido o texto", "mantidos os", "destaque", "dtq", "dispositivo",
                            "artigo", "expressão", "parágrafo", "inciso", "destque", "detaque")):
        return "parcial"
    if "emenda" in _sin_ec(t):
        return "enmienda"
    if any(k in t for k in ("projeto", "proposta", "medida provisória", "turno", "mensagem", "parecer", "indicação")):
        return "final"
    return "otra"


def tipo_votacion_senado(texto, sigla):
    """Tipo de votación según la descripción del Senado («Votação nominal da Emenda nº 3…», «PEC nº 1, de 2019, com
    as Emendas…, (1º Turno)», «Art. 5º do Projeto…, destacado»…)."""
    t = re.sub(r"ressalvad\w*[^.;]*", "", _limpio(texto).lower())
    if sigla in ("MSF", "OFS") or re.search(r"\b(?:escolha|indicação|recondução)\b", t):
        return "nombramiento"
    objeto = re.sub(r"^\(?(?:votação\s+(?:nominal\s+)?(?:conjunta\s+)?(?:em globo\s+)?(?:d[aoe]s?\s+)?)?", "", t)
    if "substitutiv" in objeto[:40]:  # «Emenda nº 8 (Substitutivo)», «Substitutivo da Câmara»: el texto entero
        return "final"
    if re.match(r"(?:(?:primeira |segunda )?parte d[ao]s? )?(?:sub)?emendas?\b", objeto) and not objeto.startswith("emenda à"):
        return "enmienda"
    if "destacad" in t or re.match(r"(?:arts?\.|§|parágrafo|inciso|expressão|alínea|dispositivo)", objeto):
        return "parcial"
    if "projeto de lei de conversão" in t or re.search(r"\bplv\b", t):
        return "final"
    # «MPV nº 913, de 2019 e Pressupostos de Relevância e Urgência» es la votación de la MP.
    sin_pressupostos = re.sub(r"pressupostos (?:constitucionais|de relevância)[^.;]*", "", t)
    if re.match(r"(?:requerimento|rqs|pressupostos|recurso|preferência|solicita)", objeto) or any(
            k in sin_pressupostos for k in ("requerimento", "calendário especial", "urgência", "adiamento", "retirada de pauta")):
        return "procedimiento"
    return "final"


def titulo_senado(ementa):
    """Autoridades: «Submete à apreciação do Senado Federal, nos termos do art. …, o nome do Senhor X, para exercer
    o cargo de Embaixador…» -> «Aprovação do nome do Senhor X, para exercer o cargo de Embaixador…»."""
    m = re.match(r"Submet\w*\b.*?\b(o nome|a indicação|a escolha|a recondução) (.+)$", ementa or "", re.S)
    if m:
        resto = re.sub(r",\s*Ministr[oa] de (?:Primeira|Segunda) Classe[^,]*,", ",", m.group(2))
        return {"o nome": "Aprovação do nome", "a indicação": "Aprovação da indicação",
                "a escolha": "Aprovação da escolha", "a recondução": "Aprovação da recondução"}[m.group(1)] + " " + resto
    return ementa


# ------------------------------------------------------------------ Cámara

def _abierta(ctx, tabla, anio, actual):
    ruta = ctx.cache(f"{CAMARA}/{tabla}/csv/{tabla}-{anio}.csv", f"{tabla}-{anio}.csv",
                     caduca_horas=12 if actual else None, timeout=600)
    return open(ruta, encoding="utf-8-sig", newline="")


def _texto_camara(r):
    """Descripción sin los totales; si es escueta («Mantido o texto», «Resultado»), con la apertura de la votación
    («Votação do DTQ 4 (PT): Destaque… do art. 9º…»), si esa apertura es de lo mismo."""
    t = _limpio(r["descricao"])
    t = re.split(r"\s*\b(?:Sim|N[ãa]o|Abstenç[ãa]o|Total)\s*:?\s*\d|\s*\bVotos:\s", t, maxsplit=1, flags=re.I)[0]
    t = t.strip(" ;,") or _limpio(r["descricao"])
    apertura = _limpio(r.get("ultimaAberturaVotacao_descricao")).rstrip(".")
    if (not apertura or APERTURA_GENERICA.match(apertura) or not apertura.lower().startswith("votação d")
            or (r.get("ultimaAberturaVotacao_dataHoraRegistro") or "")[:10] != r["data"]):
        return t
    base, a = t.lower(), apertura.lower()
    if re.fullmatch(r"(?:resultado|aprovad[oa]s?|rejeitad[oa]s?)\.?", base) \
            or (base.startswith(("mantido o texto", "suprimido o texto", "mantidos", "suprimidos"))
                and any(k in a for k in ("dtq", "destaque", "emenda", "ema "))) \
            or (re.match(r"(?:aprovad|rejeitad)\w* (?:o|a|os|as) (?:requerimento|emenda)s?\.?$", base)
                and ("requerimento" in a if "requerimento" in base else "emenda" in a or "dtq" in a)):
        return f"{t.rstrip('.')} — {apertura}"
    return t


def _resultado_camara(r):
    if r.get("aprovacao") == "1":
        return "aprobada"
    if r.get("aprovacao") == "0":
        return "rechazada"
    d = (r.get("descricao") or "").lower()
    if d.startswith(("aprovad", "mantid")):
        return "aprobada"
    if d.startswith(("rejeitad", "suprimid")):
        return "rechazada"
    si, no = _num(r["votosSim"]), _num(r["votosNao"])
    return ("aprobada" if si > no else "rechazada") if si + no else None


def _proposicao_api(ctx, pid):
    try:
        d = ctx.json(f"{API_CAMARA}/proposicoes/{pid}", headers={"Accept": "application/json"})["dados"]
    except Exception:
        return None
    return {"proposicao_id": str(d["id"]), "proposicao_siglaTipo": d.get("siglaTipo") or "",
            "proposicao_numero": str(d.get("numero") or ""), "proposicao_ano": str(d.get("ano") or ""),
            "proposicao_ementa": d.get("ementa") or ""}


def _principal(props):
    principales = [p for p in props if p["proposicao_siglaTipo"] not in AUXILIARES] or props
    if not principales:
        return None
    return min(principales, key=lambda p: (PREFERENCIA.index(p["proposicao_siglaTipo"])
                                           if p["proposicao_siglaTipo"] in PREFERENCIA else len(PREFERENCIA)))


def camara(ctx, anio, actual, desde_fecha, vistos):
    """Votaciones del pleno de la Cámara de un año (desde `desde_fecha` si se da)."""
    with _abierta(ctx, "votacoes", anio, actual) as f:
        pleno = [r for r in csv.DictReader(f, delimiter=";") if r["siglaOrgao"] == "PLEN" and r["data"][:4] == str(anio)]
    props = {}
    with _abierta(ctx, "votacoesProposicoes", anio, actual) as f:
        for r in csv.DictReader(f, delimiter=";"):
            props.setdefault(r["idVotacao"], []).append(r)

    nominal = {r["id"] for r in pleno if _num(r["votosSim"]) + _num(r["votosNao"]) + _num(r["votosOutros"]) > 0}
    candidatas = []
    for r in pleno:
        texto = _texto_camara(r)
        tv = tipo_votacion_camara(r["descricao"])
        if tv == "otra" and " — " in texto:
            tv = tipo_votacion_camara(texto.split(" — ", 1)[-1])
        if r["id"] in nominal or tv == "final":
            candidatas.append((r, tv, texto))
    if not any(not desde_fecha or r["data"] >= desde_fecha for r, _, _ in candidatas):
        return

    # Votaciones sin proposición en el fichero: la del id de la votación («proposición-secuencia»), de la API.
    faltan = sorted({r["id"].split("-")[0] for r, _, _ in candidatas
                     if not props.get(r["id"]) and (not desde_fecha or r["data"] >= desde_fecha)})
    if faltan:
        with ThreadPoolExecutor(4) as ex:
            encontradas = dict(zip(faltan, ex.map(lambda p: _proposicao_api(ctx, p), faltan)))
        for r, _, _ in candidatas:
            p = encontradas.get(r["id"].split("-")[0])
            if not props.get(r["id"]) and p:
                props[r["id"]] = [p]

    # Mensajes presidenciales de tratados (MSC) cuyo PDL nace en el pleno: el asunto es el PDL.
    msc_pdl = {}
    for r in pleno:
        ps = props.get(r["id"], [])
        p = _principal(ps)
        if p and p["proposicao_siglaTipo"] == "MSC":
            citada = proposicao_citada(r["descricao"], {"PDL"})
            if citada:
                msc_pdl[p["proposicao_id"]] = citada
        pdl = [q for q in ps if q["proposicao_siglaTipo"] == "PDL"]
        for m in ps:
            if m["proposicao_siglaTipo"] == "MSC" and pdl:
                msc_pdl[m["proposicao_id"]] = ("PDL", _num(pdl[0]["proposicao_numero"]), _num(pdl[0]["proposicao_ano"]))

    def resolver(r):
        """(id del asunto, sigla, número, año, id de la proposición en la Cámara, ementa, provisional)."""
        p = _principal(props.get(r["id"], []))
        if not p:
            return None
        sigla, pid = p["proposicao_siglaTipo"], p["proposicao_id"]
        ementa = _limpio(p["proposicao_ementa"])
        numero, ano_p = _num(p["proposicao_numero"]), _num(p["proposicao_ano"])
        provisional = False
        if sigla == "MSC" and pid in msc_pdl:
            sigla, numero, ano_p = msc_pdl[pid]
        elif sigla == "REQ" and tipo_asunto(sigla, ementa) == "procedimiento":
            # Requerimiento suelto (urgencia, retirada…) sobre un proyecto que cita: el asunto es el proyecto.
            citada = proposicao_citada(ementa + " " + r["descricao"])
            if citada:
                (sigla, numero, ano_p), provisional = citada, True
        return _aid(sigla, numero, ano_p), sigla, numero, ano_p, pid, ementa, provisional

    # Las nominales se guardan todas. De las simbólicas, solo las decisivas (tipo «final») de los tratados y de
    # los asuntos que tienen alguna votación nominal (así esos asuntos tienen resultado): el resto de leyes
    # aprobadas «por los líderes» no se guardan.
    resueltas = {r["id"]: resolver(r) for r, _, _ in candidatas}
    con_nominal = {resueltas[r["id"]][0] for r, _, _ in candidatas if r["id"] in nominal and resueltas[r["id"]]}
    elegidas = []
    for r, tv, texto in candidatas:
        res = resueltas[r["id"]]
        if not res or (desde_fecha and r["data"] < desde_fecha):
            continue  # sin proposición no hay asunto
        if r["id"] in nominal or res[0] in con_nominal or tipo_asunto(res[1], res[5]) == "tratado" \
                or ctx.con.execute("SELECT 1 FROM asunto WHERE id=?", (res[0],)).fetchone():
            elegidas.append((r, tv, texto))

    # Votos (fichero grande: se lee fila a fila y solo se guardan los de las votaciones elegidas).
    quiero = {r["id"] for r, _, _ in elegidas if r["id"] in nominal}
    votos = {}
    with _abierta(ctx, "votacoesVotos", anio, actual) as f:
        for v in csv.DictReader(f, delimiter=";"):
            if v["idVotacao"] not in quiero:
                continue
            partido = v["deputado_siglaPartido"]
            partido = "S.PART." if partido in SIN_PARTIDO else partido
            votos.setdefault(v["idVotacao"], []).append(
                (f"bra:dep:{v['deputado_id']}", _limpio(v["deputado_nome"]), partido, v["voto"]))

    asuntos, votaciones, provisionales = {}, [], set()
    for r, tv, texto in elegidas:
        aid, sigla, numero, ano_p, pid, ementa, provisional = resueltas[r["id"]]
        if provisional and aid not in asuntos:
            previo = _asunto_existente(ctx, aid, vistos)
            if previo:
                asuntos[aid] = previo
            else:  # hasta que se vote el proyecto, el título es el del requerimiento
                asuntos[aid] = Asunto(id=aid, titulo=_corto(ementa), tipo=tipo_asunto(sigla, ""), fecha=r["data"],
                                      codigo=f"{sigla} {numero}/{ano_p}", url=FICHA_CAMARA.format(pid))
                provisionales.add(aid)
        elif aid not in asuntos or (aid in provisionales and not provisional):
            asuntos[aid] = Asunto(id=aid, titulo=_corto(ementa or f"{sigla} {numero}/{ano_p}"),
                                  tipo=tipo_asunto(sigla, ementa), fecha=r["data"], codigo=f"{sigla} {numero}/{ano_p}",
                                  url=FICHA_CAMARA.format(pid))
            provisionales.discard(aid)
        lista = votos.get(r["id"])
        a_favor = en_contra = abst = no_votan = None
        if r["id"] in nominal and lista and any(s for *_, s in lista):
            lista = [(m, n, par, SENTIDO_CAMARA.get(s, "no_vota")) for m, n, par, s in lista]
            for par in {par for _, _, par, _ in lista}:
                if par not in FUENTE.partidos:
                    ctx.partido(par)
            a_favor = sum(1 for *_, s in lista if s == "si")
            en_contra = sum(1 for *_, s in lista if s == "no")
            abst = sum(1 for *_, s in lista if s == "abstencion")
            no_votan = sum(1 for *_, s in lista if s == "no_vota")
        elif r["id"] in nominal:  # votación secreta (todos los votos en blanco): solo totales
            lista = None
            a_favor, en_contra, abst = _num(r["votosSim"]), _num(r["votosNao"]), _num(r["votosOutros"])
            texto += " (votação secreta)"
        else:
            lista = None
            texto += " (votação simbólica)"
        url = (f"https://www.camara.leg.br/presenca-comissoes/votacao-portal?reuniao={r['idEvento']}"
               if r["id"] in nominal and _num(r["idEvento"]) else FICHA_CAMARA.format(r["id"].split("-")[0]))
        # Número: la secuencia del id de la fuente («2557414-32»), que ordena las votaciones de un proyecto.
        votaciones.append(Votacion(
            id=f"bra:c:{r['id']}", fecha=r["data"], asunto_id=aid, camara="bra-c", numero=_num(r["id"].rsplit("-", 1)[-1]),
            texto=texto[:600], tipo=tv, a_favor=a_favor, en_contra=en_contra, abstenciones=abst, no_votan=no_votan,
            resultado=_resultado_camara(r), url=url, votos=lista))
    vistos.update(asuntos)
    votaciones.sort(key=lambda v: (v.fecha, v.id))
    for i in range(0, len(votaciones), LOTE):
        lote = votaciones[i:i + LOTE]
        ctx.guardar([asuntos[a] for a in dict.fromkeys(v.asunto_id for v in lote)], lote)
    ctx.log(f"   Cámara {anio}: {len(votaciones)} votaciones ({sum(1 for v in votaciones if v.votos)} con voto nominal), "
            f"{len(asuntos)} asuntos")


# ------------------------------------------------------------------ Senado

def _asunto_existente(ctx, aid, vistos):
    """El asunto ya visto en la Cámara (su ementa y su ficha tienen preferencia)."""
    if aid in vistos:
        return vistos[aid]
    fila = ctx.con.execute("SELECT titulo, tipo, codigo, url FROM asunto WHERE id=?", (aid,)).fetchone()
    if fila:
        return Asunto(id=aid, titulo=fila[0], tipo=fila[1], codigo=fila[2], url=fila[3])
    return None


def senado(ctx, anio, actual, desde_fecha, vistos):
    """Votaciones nominales del pleno del Senado de un año (desde `desde_fecha` si se da)."""
    inicio = max(f"{anio}-01-01", desde_fecha or "")
    fin = min(f"{anio}-12-31", date.today().isoformat())
    if inicio > fin:
        return
    url = f"{SENADO}/votacao?dataInicio={inicio}&dataFim={fin}"
    cab = {"Accept": "application/json"}
    if actual:
        datos = ctx.json(url, headers=cab, timeout=300)
    else:
        ruta = ctx.cache(url, f"senado-votacao-{anio}.json", headers=cab, timeout=300)
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    asuntos, votaciones = {}, []
    for d in datos or []:
        fecha = (d.get("dataSessao") or "")[:10]
        if not fecha.startswith(str(anio)) or fecha < inicio:
            continue
        sigla, numero, ano_p = d.get("sigla"), str(d.get("numero") or "").strip(), d.get("ano")
        descr = _limpio(d.get("descricaoVotacao"))
        ementa = _limpio(d.get("ementa"))
        if sigla == "RQS":  # requerimiento sobre otra materia (urgencia…): el asunto es la materia
            citada = proposicao_citada(descr + " " + ementa)
            if citada:
                sigla, numero, ano_p = {"PRC": "PRS"}.get(citada[0], citada[0]), str(citada[1]), citada[2]
                ementa = ""
        if sigla and numero.isdigit() and ano_p:
            aid, codigo = _aid(sigla, numero, ano_p), f"{sigla} {int(numero)}/{ano_p}"
        else:
            aid, codigo = f"bra:s:{d['codigoSessaoVotacao']}", d.get("identificacao")
        if aid not in asuntos:
            asuntos[aid] = _asunto_existente(ctx, aid, vistos) or Asunto(
                id=aid, titulo=_corto(titulo_senado(ementa) or descr or codigo or aid), tipo=tipo_asunto(sigla, ementa),
                fecha=fecha, codigo=codigo,
                url=FICHA_SENADO.format(d["codigoMateria"]) if d.get("codigoMateria") and ementa else None)
        # «(Ementa…)» entre paréntesis como descripción: es la votación de la materia.
        texto = descr.strip("() ") if descr.startswith("(") else descr
        if not texto or texto[:40].lower() == ementa[:40].lower():
            texto = "Votação nominal da matéria"
        lista, a_favor, en_contra, abst, no_votan = None, None, None, None, None
        if d.get("votacaoSecreta") == "S":
            a_favor, en_contra, abst = d.get("totalVotosSim"), d.get("totalVotosNao"), d.get("totalVotosAbstencao")
            texto += " (votação secreta)"
        elif not d.get("votos"):
            continue  # sin votos ni totales no hay nada que guardar
        else:
            lista = []
            for v in d["votos"]:
                partido = v.get("siglaPartidoParlamentar")
                partido = "S.PART." if partido in SIN_PARTIDO else partido
                if partido not in FUENTE.partidos:
                    ctx.partido(partido)
                lista.append((f"bra:sen:{v['codigoParlamentar']}", _limpio(v.get("nomeParlamentar")), partido,
                              SENTIDO_SENADO.get(v.get("siglaVotoParlamentar"), "no_vota")))
            a_favor = sum(1 for *_, s in lista if s == "si")
            en_contra = sum(1 for *_, s in lista if s == "no")
            abst = sum(1 for *_, s in lista if s == "abstencion")
            no_votan = sum(1 for *_, s in lista if s == "no_vota")
        resultado = {"A": "aprobada", "R": "rechazada"}.get(d.get("resultadoVotacao"))
        if not resultado and a_favor is not None:  # sin resultado publicado: mayoría (tres quintos en una PEC)
            resultado = "aprobada" if (a_favor >= 49 if d.get("sigla") == "PEC" else a_favor > (en_contra or 0)) else "rechazada"
        url_v = (f"https://www25.senado.leg.br/web/atividade/materias/-/materia/{d['codigoMateria']}/votacoes"
                 f"#votacao_{d['codigoSessaoVotacao']}") if d.get("codigoMateria") else None
        votaciones.append(Votacion(
            id=f"bra:s:{d['codigoSessaoVotacao']}", fecha=fecha, asunto_id=aid, camara="bra-s",
            numero=d.get("sequencialSessao"), texto=texto[:600], tipo=tipo_votacion_senado(descr, d.get("sigla")),
            a_favor=a_favor, en_contra=en_contra, abstenciones=abst, no_votan=no_votan, resultado=resultado,
            url=url_v, votos=lista))
    votaciones.sort(key=lambda v: (v.fecha, v.numero or 0))
    for i in range(0, len(votaciones), LOTE):
        lote = votaciones[i:i + LOTE]
        ctx.guardar([asuntos[a] for a in dict.fromkeys(v.asunto_id for v in lote)], lote)
    ctx.log(f"   Senado {anio}: {len(votaciones)} votaciones ({sum(1 for v in votaciones if v.votos)} con voto nominal)")


# ------------------------------------------------------------------ recogida

def _ultima(ctx, camara_):
    return ctx.con.execute("SELECT MAX(fecha) FROM votacion WHERE fuente='bra' AND camara=?", (camara_,)).fetchone()[0]


def recoger(ctx):
    hoy = date.today()
    cerrados = set(ctx.marca("cerrados", []))
    # Un año se da por cerrado mes y medio después de terminar (los ficheros se corrigen unos días).
    abierto_desde = (hoy - timedelta(days=45)).year
    for anio in range(ctx.desde, hoy.year + 1):
        actual = anio >= abierto_desde
        if anio in cerrados and not ctx.completo:
            continue
        vistos = {}
        for codigo, funcion in (("bra-c", camara), ("bra-s", senado)):
            desde_fecha = None
            if actual and not ctx.completo:
                ultima = _ultima(ctx, codigo)
                if ultima:
                    desde_fecha = (date.fromisoformat(ultima) - timedelta(days=MARGEN)).isoformat()
                    if desde_fecha[:4] > str(anio):
                        continue
            funcion(ctx, anio, actual, desde_fecha, vistos)
        if not actual:
            cerrados.add(anio)
            ctx.poner_marca("cerrados", sorted(cerrados))
