"use strict";

// ------------------------------------------------------------------ vistas de un país
// Resumen, Votaciones y Partidos usan las votaciones de su parlamento (si hay fuente); «En la ONU» existe
// para cualquier Estado miembro. Todo se filtra por el país y los años elegidos en la cabecera.

const fuentesPais = (iso3) => CAT.fuentesDe[iso3] || [];
const recortarAnios = ([a, b], f) => [Math.max(a, f.anio_min || a), Math.min(b, f.anio_max || b)];
const aniosOnu = () => { const [a, b] = aniosActuales(); return [a, Math.min(b, ONU_HASTA)]; };
const nombresOnu = () => nombresFuente("onu", aniosOnu());

// Cabecera de las vistas de un país: la sección como antetítulo, el país y un atajo para cambiarlo.
// Sin país (iso3 null), «Todos los países».
function cabeceraPais(iso3, subtitulo, seccion) {
  const p = CAT.paises[iso3] || {};
  return el("div", { class: "cab-pais" },
    seccion ? el("div", { class: "antetitulo" }, seccion) : null,
    el("h2", {}, iso3 ? p.nombre || iso3 : "Todos los países",
      iso3 ? el("span", { class: "muted small" }, ` · ${[p.subregion, p.region].filter(Boolean).join(", ")}`) : null,
      el("button", { type: "button", class: "boton-cambiar", onclick: abrirSelectorPais }, iso3 ? "Cambiar de país" : "Elegir un país")),
    subtitulo ? el("p", { class: "sub" }, subtitulo) : null);
}

// Votaciones y Partidos son de un parlamento: sin país elegido, se elige uno.
function elegirParlamento(seccion) {
  const paises = Object.keys(CAT.fuentesDe).sort((a, b) => nombrePais(a).localeCompare(nombrePais(b), "es"));
  return el("div", {}, cabeceraPais(null, null, seccion),
    el("section", { class: "card" }, el("h3", {}, "Elige un parlamento"),
      el("p", { class: "muted small" }, "Cada parlamento vota sus propios asuntos con sus propios partidos, así que aquí no hay vista de conjunto. Lo que votan todos sobre otros países está en el mapa y en Resumen."),
      el("div", { class: "pais-grupo" }, paises.map((i) => el("button", { type: "button", class: "pais-op", onclick: () => elegirPais(i) },
        el("span", {}, nombrePais(i)), el("span", { class: "badge ok" }, camarasDe(i)))))));
}

// Autores de las iniciativas del Congreso (códigos de los grupos parlamentarios).
const AUTORES_ESP = {
  GP: "Grupo Popular", GS: "Grupo Socialista", GVOX: "Grupo VOX", GMx: "Grupo Mixto", GCs: "Grupo Ciudadanos",
  "GCUP-EC-EM": "Grupo Unidas Podemos-En Comú Podem-Galicia en Común", "GC-CiU": "Grupo Catalán (Convergència i Unió)",
  "GV (EAJ-PNV)": "Grupo Vasco (EAJ-PNV)", GIP: "Grupo de La Izquierda Plural", GR: "Grupo Republicano", GSUMAR: "Grupo Sumar",
  GEH: "Grupo EH Bildu", GJxCAT: "Grupo Junts per Catalunya", GPlu: "Grupo Plural", CCAA: "Comunidades Autónomas", Gobierno: "Gobierno",
};
const nombreAutor = (a) => AUTORES_ESP[a] || a;

function sinParlamento(iso3) {
  const info = (typeof DISPONIBILIDAD !== "undefined" && DISPONIBILIDAD[iso3]) || null;
  return el("div", { class: "card aviso-card" },
    el("h3", {}, "No se recogen todavía las votaciones de su parlamento"),
    info ? el("p", {}, `Según el estudio de fuentes: ${info.voto}.${info.fuente !== "—" ? ` ${info.fuente}.` : ""} `,
      /^\d/.test(info.dificultad) ? `Dificultad ${info.dificultad} de 5.` : "Excluido: su parlamento no es competitivo o no publica votos.")
      : el("p", {}, "El estudio de fuentes no encontró datos abiertos de voto de su parlamento, o su parlamento no es competitivo."),
    el("p", { class: "muted small" }, `Sí están su voto en la Asamblea General de la ONU${CAT.fuentes.onu ? ` (${CAT.fuentes.onu.anio_min}–${CAT.fuentes.onu.anio_max})` : ""} y lo que otros parlamentos y Estados votan sobre él.`),
    el("p", {}, el("a", { href: hashDe("ayuda", { p: iso3 }) + "", onclick: (e) => { e.preventDefault(); irA("ayuda", { sec: "paises" }); } }, "Qué datos hay de cada país")));
}

// ------------------------------------------------------------------ Resumen

VISTAS.resumen = {
  titulo: "Resumen del país",
  datos: () => {
    const iso3 = paisActual();
    return [...fuentesPais(iso3).flatMap((f) => nombresFuente(f.codigo, aniosActuales())), ...nombresMundo(aniosActuales())];
  },
  pintar: pintarResumen,
};

// Los 8 con más saldo a favor (signo 1) o en contra (signo -1), entre los que tienen relación.
const ordenarSaldo = (filas, signo) => filas.filter((r) => signo * (r.pos - r.neg) > 0)
  .sort((a, b) => signo * ((b.pos - b.neg) - (a.pos - a.neg)) || b.n - a.n).slice(0, 8);

function relacionesDesde(iso3, anios, via, { entrantes = false, limite = 15 } = {}) {
  const lado = entrantes ? "destino" : "origen", otro = entrantes ? "origen" : "destino";
  return q(`SELECT ${otro} AS pais, SUM(orientacion>0) AS pos, SUM(orientacion<0) AS neg, SUM(orientacion=0) AS neu, COUNT(*) AS n,
              COUNT(DISTINCT asunto_id) AS asuntos
            FROM relacion WHERE ${lado}=? AND via=? AND anio BETWEEN ? AND ? AND (via='onu' OR aprobado=1)
            GROUP BY ${otro} ORDER BY n DESC LIMIT ${limite}`, [iso3, via, ...anios]);
}

function barrasSaldo(filas, alClicar, { etiqueta = (r) => nombrePais(r.pais), vacio = "Nada con estos años." } = {}) {
  if (!filas.length) return el("p", { class: "muted" }, vacio);
  const max = Math.max(...filas.map((r) => r.n));
  return el("div", { class: "barrash" }, filas.flatMap((r) => {
    const t = Math.max(1, r.pos + r.neg + r.neu), w = (100 * r.n) / max;
    return [
      el("div", { class: "bh-label" }, etiqueta(r)),
      conTip(el("div", { class: "bh-pista clic", onclick: () => alClicar(r) },
        el("div", { class: "bh-pila", style: `width:${Math.max(2, w)}%` },
          el("span", { class: "si", style: `flex:${r.pos}` }), el("span", { class: "abs", style: `flex:${r.neu}` }), el("span", { class: "no", style: `flex:${r.neg}` })),
        el("b", {}, fmt(r.n))),
        textoSaldo(r.pos, r.neg, r.neu), etiqueta(r), "Pulsa para ver el detalle"),
    ];
  }));
}
const leyendaSaldo = () => el("div", { class: "legend" }, el("span", {}, el("i", { style: "background:var(--si)" }), "positivas"),
  el("span", {}, el("i", { style: "background:var(--abs)" }), "neutras"), el("span", {}, el("i", { style: "background:var(--no)" }), "negativas"));

// Sin país elegido: los parlamentos con datos, y de qué países tratan más sus leyes y las resoluciones de la ONU.
function pintarResumenGlobal() {
  const anios = aniosActuales(), [ao, bo] = aniosOnu();
  const sobreOtros = Object.fromEntries(q(`SELECT origen, COUNT(DISTINCT asunto_id) AS n FROM relacion
                                           WHERE via='ley' AND aprobado=1 AND anio BETWEEN ? AND ? GROUP BY origen`, anios).map((r) => [r.origen, r.n]));
  const parlamentos = Object.entries(CAT.fuentesDe).map(([iso3, fs]) => {
    const cs = CAT.cobertura.filter((c) => fs.some((f) => f.codigo === c.fuente) && c.anio >= anios[0] && c.anio <= anios[1]);
    return { iso3, votaciones: cs.reduce((s, c) => s + c.votaciones, 0), asuntos: cs.reduce((s, c) => s + c.asuntos, 0), sobreOtros: sobreOtros[iso3] || 0 };
  }).sort((a, b) => b.votaciones - a.votaciones || nombrePais(a.iso3).localeCompare(nombrePais(b.iso3), "es"));
  // n: asuntos (o resoluciones) distintos; el color, el sentido de cada relación.
  const destinos = (via, [a, b]) => q(`SELECT destino AS pais, SUM(orientacion>0) AS pos, SUM(orientacion<0) AS neg, SUM(orientacion=0) AS neu,
                                         COUNT(DISTINCT asunto_id) AS n FROM relacion
                                       WHERE via=? AND anio BETWEEN ? AND ? AND (via='onu' OR aprobado=1) GROUP BY destino ORDER BY n DESC LIMIT 12`, [via, a, b]);
  const alMapa = (r) => irA("mundo", { o: "", d: r.pais }, { arriba: true });
  return el("div", {},
    cabeceraPais(null, `La foto de conjunto · ${textoAnios(anios)}. Elige un país para ver lo suyo.`, "Resumen"),
    el("div", { class: "segmentos" },
      el("button", { class: "boton", onclick: () => irA("mundo", { o: "", d: "" }) }, "Mapa: lo que vota cada país sobre otros"),
      el("button", { class: "boton", onclick: () => irA("mundo", { modo: "afinidad" }) }, "Mapa: con quién vota igual cada país en la ONU")),
    el("section", { class: "card" }, el("h3", {}, "Parlamentos con datos"),
      el("p", { class: "muted small" }, `Votaciones recogidas en ${textoAnios(anios)}. «Sobre otros países»: asuntos aprobados que tratan de otro país. Pulsa uno para ver su resumen.`),
      el("div", { class: "tabla-scroll" }, el("table", { class: "tabla" },
        el("thead", {}, el("tr", {}, el("th", {}, "País"), el("th", {}, "Cámara"), el("th", { class: "num" }, "Votaciones"),
          el("th", { class: "num" }, "Asuntos"), el("th", { class: "num" }, "Sobre otros países"))),
        el("tbody", {}, parlamentos.map((r) => el("tr", { class: "clic", onclick: () => irA("resumen", { p: r.iso3 }, { arriba: true }) },
          el("td", {}, nombrePais(r.iso3)), el("td", { class: "small muted" }, camarasDe(r.iso3)), el("td", { class: "num" }, fmt(r.votaciones)),
          el("td", { class: "num" }, fmt(r.asuntos)), el("td", { class: "num" }, fmt(r.sobreOtros)))))))),
    el("div", { class: "grid g2 arriba", style: "margin-top:16px" },
      el("section", { class: "card" }, el("h3", {}, "De qué países tratan más las leyes"),
        el("p", { class: "muted small" }, `Asuntos aprobados por los parlamentos con datos que tratan de cada país (${textoAnios(anios)}), con su sentido. Pulsa una barra para verlo en el mapa.`),
        leyendaSaldo(), barrasSaldo(destinos("ley", anios), alMapa)),
      el("section", { class: "card" }, el("h3", {}, "De qué países tratan más las resoluciones de la ONU"),
        ao <= bo ? [el("p", { class: "muted small" }, `Resoluciones votadas en la Asamblea General que tratan de cada país (${textoAnios([ao, bo])}); el color, cómo votaron los Estados. Pulsa una barra para verlo en el mapa.`),
          leyendaSaldo(), barrasSaldo(destinos("onu", [ao, bo]), alMapa)]
          : el("p", { class: "muted" }, `La ONU tiene datos hasta ${ONU_HASTA}: elige años anteriores.`))));
}

function pintarResumen() {
  const iso3 = paisActual();
  if (!iso3) return pintarResumenGlobal();
  const anios = aniosActuales();
  const fs = fuentesPais(iso3);
  const bloques = [];
  if (fs.length) {
    for (const f of fs) {
      const [a, b] = recortarAnios(anios, f);
      // Asuntos (no votaciones sueltas): un asunto votado por puntos cuenta una vez, aprobado si pasó algún punto.
      const t = q1(`SELECT COUNT(*) AS votaciones, COUNT(DISTINCT asunto_id) AS asuntos,
                     COUNT(DISTINCT CASE WHEN decisiva=1 AND tipo='final' THEN asunto_id END) AS finales,
                     COUNT(DISTINCT CASE WHEN decisiva=1 AND tipo='final' AND resultado='aprobada' THEN asunto_id END) AS aprobadas
                   FROM votacion WHERE fuente=? AND anio BETWEEN ? AND ?`, [f.codigo, a, b]);
      const fichas = q1(`SELECT SUM(fi.origen NOT IN ('reglas','escrutinio:reglas')) AS ia,
                           SUM(COALESCE(fi.relaciones_origen, 'reglas') NOT IN ('reglas','escrutinio:reglas')) AS rel_ia, COUNT(*) AS n FROM ficha fi
                         WHERE fi.asunto_id IN (SELECT asunto_id FROM votacion WHERE fuente=? AND anio BETWEEN ? AND ?)`, [f.codigo, a, b]);
      const porAnio = q("SELECT anio AS x, COUNT(*) AS y FROM votacion WHERE fuente=? AND anio BETWEEN ? AND ? GROUP BY anio ORDER BY anio", [f.codigo, a, b]);
      const temas = q(`SELECT COALESCE(fi.tema_principal, '') AS tema, COUNT(DISTINCT v.asunto_id) AS n FROM votacion v
                       LEFT JOIN ficha fi ON fi.asunto_id=v.asunto_id JOIN asunto s ON s.id=v.asunto_id
                       WHERE v.fuente=? AND v.anio BETWEEN ? AND ? AND v.decisiva=1 AND s.tipo NOT IN ('procedimiento','nombramiento')
                       GROUP BY 1 ORDER BY n DESC`, [f.codigo, a, b]);
      // «Sin tema» no es un tema: va al final, en gris.
      const conTema = temas.filter((r) => r.tema).slice(0, 12), sinTema = temas.find((r) => !r.tema);
      const camaras = Object.values(CAT.camaras).filter((c) => c.fuente === f.codigo).map((c) => c.nombre).join(" y ");
      const legislador = { esp: "diputado", eup: "eurodiputado" }[f.codigo] || "legislador";
      bloques.push(
        el("section", {}, el("h3", {}, f.nombre),
          el("p", { class: "muted small" }, unirPartes([camaras, f.detalle === "nominal" ? `voto de cada ${legislador}` : f.detalle,
            `la base cubre de ${f.anio_min} a ${f.anio_max}; aquí, ${textoAnios([a, b])}`]), " · ", enlace(f.web, "fuente oficial"), f.notas ? ` · ${f.notas}` : ""),
          el("div", { class: "grid g4" },
            stat("Votaciones", fmt(t.votaciones), `${textoAnios([a, b])}, contando enmiendas y trámites`),
            stat("Asuntos votados", fmt(t.asuntos), "leyes, resoluciones, mociones…"),
            stat("Asuntos aprobados", `${pct(t.aprobadas, t.finales)} %`, `${fmt(t.aprobadas)} de ${cuenta(t.finales, "asunto", "asuntos")} con votación final`),
            stat("Resumen hecho por IA", `${pct(fichas.ia, fichas.n)} %`,
              fichas.n && fichas.rel_ia < fichas.n ? `países y sentido: ${pct(fichas.rel_ia, fichas.n)} % por IA, el resto por reglas automáticas` : "el resto, sin resumen")),
          el("div", { class: "grid g2", style: "margin-top:16px" },
            el("div", { class: "card" }, el("h3", {}, "Votaciones por año"), el("p", { class: "muted small" }, "Todas las votaciones del pleno, también enmiendas y trámites."),
              columnasAnio(porAnio, { ancho: 560, alto: 300 })),
            el("div", { class: "card" }, el("h3", {}, "Asuntos por tema"), el("p", { class: "muted small" }, "Pulsa un tema para ver sus votaciones."),
              barrasH([...conTema.map((r) => ({ etiqueta: temaNombre(r.tema), valor: r.n, color: "var(--accent)", tema: r.tema })),
                ...(sinTema ? [{ etiqueta: "Sin clasificar", valor: sinTema.n, color: "var(--abs)", tema: "", tip: "Asuntos cuyo título no permite asignar un tema" }] : [])],
              { alClicar: (i) => { if (i.tema) irA("votaciones", { tema: i.tema }); } })))));
    }
  } else {
    bloques.push(sinParlamento(iso3));
  }
  const salen = relacionesDesde(iso3, anios, "ley");
  const entran = relacionesDesde(iso3, anios, "ley", { entrantes: true });
  const onuSobre = relacionesDesde(iso3, anios, "onu", { entrantes: true, limite: 400 });
  const panel = (o, d) => panelArista(o, d, {});
  const conDatos = Object.keys(CAT.fuentesDe).filter((i) => i !== iso3).map(nombrePais).join(", ");
  bloques.push(el("div", { class: "grid g2 arriba", style: "margin-top:16px" },
    el("section", { class: "card" }, el("h3", {}, `Lo que ${organo(iso3)} vota sobre otros países`),
      fs.length && salen.length ? [el("p", { class: "muted small" }, "Asuntos aprobados, por país del que tratan y su sentido. Pulsa una barra para ver cuáles."), leyendaSaldo(),
        barrasSaldo(salen, (r) => panel(iso3, r.pais))]
        : el("p", { class: "muted" }, fs.length ? `Ningún asunto aprobado sobre otros países en ${textoAnios(anios)}.` : "No se recogen todavía las votaciones de su parlamento.")),
    // La Unión Europea no es destino de nada (no es un Estado): en su lugar, las delegaciones nacionales.
    esOrganismo(iso3) ? el("section", { class: "card" }, el("h3", {}, "Las delegaciones nacionales"),
      el("p", {}, "El partido de cada eurodiputado es su grupo europeo (Votaciones y Partidos). Cómo vota la delegación de cada país, con qué otras coincide y cada uno de sus eurodiputados está en «En el PE»."),
      el("p", {}, el("button", { class: "boton", onclick: () => irA("pe") }, "Comparar las delegaciones nacionales")))
    : el("section", { class: "card" }, el("h3", {}, `Lo que otros parlamentos votan sobre ${nombrePais(iso3)}`),
      entran.length ? [el("p", { class: "muted small" }, `Solo de los parlamentos con datos (${conDatos}).`), leyendaSaldo(),
        barrasSaldo(entran, (r) => panel(r.pais, iso3))]
        : el("p", { class: "muted" }, `Ningún parlamento con datos (${conDatos}) ha aprobado nada sobre ${nombrePais(iso3)} en ${textoAnios(anios)}.`))));
  const [ao, bo] = aniosOnu();
  if (ao <= bo && !esOrganismo(iso3)) {
    const afines = afinidadCon(iso3, [ao, bo]).sort((a, b) => b.pct - a.pct);
    const aFavor = ordenarSaldo(onuSobre, 1), enContra = ordenarSaldo(onuSobre, -1);
    const verDetalle = (r) => panel(r.pais, iso3);
    const puntos = (xs, color) => puntosH(xs.map((r) => ({ etiqueta: nombrePais(r.otro), valor: r.pct, tip: cuenta(r.t, "votación en común", "votaciones en común"), iso3: r.otro })),
      { color, alClicar: (i) => irA("resumen", { p: i.iso3 }, { arriba: true }) });
    bloques.push(el("div", { class: "grid g2 arriba", style: "margin-top:16px" },
      el("section", { class: "card" }, el("h3", {}, `En la ONU, sobre ${nombrePais(iso3)}`),
        aFavor.length || enContra.length ? [
          el("p", { class: "muted small" }, `Cómo votan los demás Estados las resoluciones que tratan de ${nombrePais(iso3)} (${textoAnios([ao, bo])}). A favor: votar en el sentido favorable al país.`),
          leyendaSaldo(),
          el("h4", {}, "Los que más votan a su favor"), barrasSaldo(aFavor, verDetalle, { vacio: "Ninguno." }),
          el("h4", {}, "Los que más votan en su contra"), barrasSaldo(enContra, verDetalle, { vacio: "Ninguno." })]
          : el("p", { class: "muted" }, `Ninguna resolución votada en la ONU trató de ${nombrePais(iso3)} en ${textoAnios([ao, bo])}.`)),
      el("section", { class: "card" }, el("h3", {}, `Con quién vota ${nombrePais(iso3)} en la ONU`),
        afines.length ? el("div", {},
          el("p", { class: "muted small" }, `Coincidencia en las votaciones finales de la Asamblea General, ${textoAnios([ao, bo])}${bo < anios[1] ? ` (la ONU tiene datos hasta ${ONU_HASTA})` : ""}.`),
          el("h4", {}, "Los que más votan como él"), puntos(afines.slice(0, 6), "var(--rel-p2)"),
          el("h4", {}, "Los que menos"), puntos(afines.slice(-4).reverse(), "var(--rel-n2)"),
          el("p", {}, el("button", { class: "boton", onclick: () => irA("mundo", { modo: "afinidad", ref: iso3 }) }, "Ver en el mapa")))
          : el("p", { class: "muted" }, "Sin votos en la ONU en esos años."))));
  }
  return el("div", {},
    cabeceraPais(iso3, fs.length ? null : "Sin votaciones de su parlamento: su perfil sale de la ONU y de lo que votan los demás.", "Resumen"),
    esOrganismo(iso3)
      ? el("div", { class: "segmentos" },
        el("button", { class: "boton", onclick: () => irA("mundo", { o: iso3, d: "" }) }, `Mapa: lo que vota ${organo(iso3)} sobre otros países`),
        el("button", { class: "boton", onclick: () => irA("pe") }, "Las delegaciones nacionales"))
      : el("div", { class: "segmentos" },
        el("button", { class: "boton", onclick: () => irA("mundo", { o: iso3, d: "" }) }, `Mapa: lo que vota ${nombrePais(iso3)} sobre otros`),
        el("button", { class: "boton", onclick: () => irA("mundo", { d: iso3, o: "" }) }, `Mapa: lo que otros votan sobre ${nombrePais(iso3)}`),
        el("button", { class: "boton", onclick: () => irA("onu") }, "Su voto en la ONU"),
        eurodiputados(iso3, anios) ? el("button", { class: "boton", onclick: () => irA("pe") }, "Sus eurodiputados") : null),
    bloques);
}

// ------------------------------------------------------------------ Votaciones

VISTAS.votaciones = {
  titulo: "Votaciones",
  datos: () => fuentesPais(paisActual()).flatMap((f) => nombresFuente(f.codigo, aniosActuales())),
  pintar: pintarVotaciones,
};

const TAM_PAGINA = 40;

function filtrosVotaciones(qq, fuente) {
  const [a, b] = recortarAnios(aniosActuales(), fuente);
  const w = ["v.fuente=?", "v.anio BETWEEN ? AND ?"], args = [fuente.codigo, a, b];
  if (qq.todas !== "1") w.push("v.decisiva=1");
  if (qq.camara) { w.push("v.camara=?"); args.push(qq.camara); }
  const tipos = lista(qq.tipo);
  if (tipos.length) { w.push(`s.tipo IN (${marcas(tipos)})`); args.push(...tipos); }
  const temas = lista(qq.tema);
  if (temas.length) { w.push(`fi.tema_principal IN (${marcas(temas)})`); args.push(...temas); }
  if (qq.resultado) { w.push("v.resultado=?"); args.push(qq.resultado); }
  if (qq.rel === "1") w.push("fi.relaciones IS NOT NULL AND fi.relaciones <> '[]'");
  if (qq.con) { w.push("fi.relaciones LIKE ?"); args.push(`%"pais": "${qq.con}"%`); }
  if (qq.imp === "1") w.push("v.importante=1");
  for (const palabra of (qq.q || "").split(/\s+/).filter(Boolean)) {
    w.push("(s.titulo LIKE ? OR fi.resumen LIKE ? OR fi.etiquetas LIKE ? OR s.codigo LIKE ? OR v.texto LIKE ?)");
    args.push(...Array(5).fill(`%${palabra}%`));
  }
  return [w.join(" AND "), args];
}
const BASE_VOT = `FROM votacion v JOIN asunto s ON s.id=v.asunto_id LEFT JOIN ficha fi ON fi.asunto_id=v.asunto_id`;

function chipsPartidos(fuente, grupos) {
  return el("div", { class: "chips" }, grupos.map((g) => {
    const p = partido(fuente, g.partido);
    return el("span", { class: "chip", title: `${p.nombre}: ${SENTIDO[g.sentido]?.[1] || g.sentido} (${g.si} sí, ${g.no} no, ${g.abstencion} abst.)` },
      el("span", { class: "sw", style: `background:${p.color || "#898781"}` }), p.siglas || g.partido,
      el("span", { class: `s ${g.sentido}` }, SENTIDO[g.sentido]?.[0] || ""));
  }));
}

// Leyenda de los símbolos del voto de cada partido.
const leyendaSentidos = () => el("div", { class: "legend leyenda-sentidos" }, el("span", { class: "leyenda-titulo" }, "Voto de cada partido:"),
  ["si", "no", "abstencion", "dividido"].map((s) => el("span", {}, el("b", { class: `s ${s}` }, SENTIDO[s][0]), " ", SENTIDO[s][1].toLowerCase())));

function filaVotacion(v, fuente, alClicar) {
  const rels = jsonDe(v.relaciones, []);
  // Un asunto votado por puntos (o en las dos cámaras) sale una vez, con el recuento de sus votaciones.
  const varias = v.puntos > 1 ? el("span", { class: "badge varias", title: "Pulsa para ver cada votación" },
    `${fmt(v.puntos)} votaciones por separado: ${[v.aprobadas ? cuenta(v.aprobadas, "aprobada", "aprobadas") : "", v.puntos - v.aprobadas ? cuenta(v.puntos - v.aprobadas, "rechazada", "rechazadas") : ""].filter(Boolean).join(", ")}`) : null;
  return el("div", { class: "fila", onclick: alClicar },
    el("div", {}, el("div", { class: "fecha" }, fecha(v.fecha)), el("div", { class: "muted small" }, CAT.camaras[v.camara]?.corto || "")),
    el("div", {},
      el("div", { class: "titulo" }, recortar(v.titulo, 200)),
      el("div", { class: "detalle" }, unirPartes([v.codigo, v.autor ? `Propuesto por: ${nombreAutor(v.autor)}` : null,
        v.puntos > 1 ? null : v.tipo !== "final" ? TIPOS_VOTACION[v.tipo] : null,
        v.puntos > 1 ? null : v.texto && v.texto !== v.titulo ? recortar(v.texto, 140) : null])),
      limpiarResumen(v.resumen) ? el("div", { class: "resumen" }, limpiarResumen(v.resumen)) : null,
      el("div", { class: "badges" },
        varias,
        v.tema_principal ? el("span", { class: "badge" }, temaNombre(v.tema_principal)) : null,
        el("span", { class: "badge" }, TIPOS_ASUNTO[v.tipo_asunto] || v.tipo_asunto),
        v.importante ? el("span", { class: "badge", title: "Votación que el Departamento de Estado de EE. UU. considera clave en su informe anual sobre la ONU" }, "votación clave") : null,
        rels.slice(0, 5).map((r) => chipRelacion(r)))),
    el("div", {}, v.puntos > 1 ? el("div", { class: "muted small" }, `${recortar(unirPartes([v.texto || TIPOS_VOTACION[v.tipo]]), 60)}:`) : null,
      badgeResultado(v.resultado), barraVotos(v), v.grupos ? chipsPartidos(fuente.codigo, v.grupos) : null));
}

function pintarVotaciones(qq) {
  const iso3 = paisActual();
  if (!iso3) return elegirParlamento("Votaciones");
  const fs = fuentesPais(iso3);
  if (!fs.length) {
    return el("div", {}, cabeceraPais(iso3, null, "Votaciones"), sinParlamento(iso3),
      el("p", {}, el("button", { class: "boton", onclick: () => irA("onu") }, `Ver cómo vota ${nombrePais(iso3)} en la ONU`)));
  }
  const fuente = fs.find((f) => f.codigo === qq.f) || fs[0];
  const [where, args] = filtrosVotaciones(qq, fuente);
  const pagina = Math.max(1, +(qq.pagina || 1));
  const orden = qq.orden === "asc" ? "ASC" : "DESC";
  // Por defecto, un asunto por fila: sus votaciones decisivas (puntos votados por separado, las dos cámaras)
  // se resumen en la fila, que enseña la del último día (el primer punto) y cuántas se aprobaron.
  const agrupar = qq.todas !== "1";
  const total = q1(`SELECT COUNT(${agrupar ? "DISTINCT v.asunto_id" : "*"}) AS n ${BASE_VOT} WHERE ${where}`, args).n;
  const campos = "v.*, s.titulo, s.codigo, s.tipo AS tipo_asunto, s.autor, fi.resumen, fi.tema_principal, fi.relaciones";
  const filas = agrupar
    ? q(`SELECT * FROM (SELECT ${campos}, COUNT(*) OVER w AS puntos, SUM(v.resultado='aprobada') OVER w AS aprobadas,
                          ROW_NUMBER() OVER (PARTITION BY v.asunto_id ORDER BY v.fecha DESC, v.numero ASC) AS rn
                        ${BASE_VOT} WHERE ${where} WINDOW w AS (PARTITION BY v.asunto_id))
         WHERE rn=1 ORDER BY fecha ${orden}, numero DESC LIMIT ? OFFSET ?`, [...args, TAM_PAGINA, (pagina - 1) * TAM_PAGINA])
    : q(`SELECT ${campos} ${BASE_VOT} WHERE ${where} ORDER BY v.fecha ${orden}, v.numero DESC LIMIT ? OFFSET ?`,
      [...args, TAM_PAGINA, (pagina - 1) * TAM_PAGINA]);
  if (filas.length) {
    const grupos = {};
    for (const g of q(`SELECT * FROM voto_partido WHERE votacion_id IN (${marcas(filas)}) ORDER BY si + no + abstencion DESC`, filas.map((f) => f.id))) {
      (grupos[g.votacion_id] = grupos[g.votacion_id] || []).push(g);
    }
    for (const f of filas) f.grupos = grupos[f.id] || [];
  }
  const camaras = Object.values(CAT.camaras).filter((c) => c.fuente === fuente.codigo);
  const paisesRel = q(`SELECT DISTINCT destino FROM relacion WHERE fuente=? AND anio BETWEEN ? AND ?`, [fuente.codigo, ...aniosActuales()])
    .map((r) => [r.destino, nombrePais(r.destino)]).sort((a, b) => a[1].localeCompare(b[1], "es"));
  const cambiar = (c) => irA("votaciones", { ...c, pagina: "" });
  const filtros = filaFiltros([
    buscarFiltro("q", qq.q, "Buscar palabras o un código…"),
    camaras.length > 1 ? selectFiltro("camara", [["", "Todas las cámaras"], ...camaras.map((c) => [c.codigo, c.nombre])], qq.camara) : null,
    multiSelect("tipo", Object.entries(TIPOS_ASUNTO), qq.tipo, "Todo tipo de asunto", "tipos"),
    multiSelect("tema", CAT.temas.map((t) => [t.codigo, t.nombre]), qq.tema, "Todos los temas", "temas"),
    selectFiltro("resultado", [["", "Cualquier resultado"], ["aprobada", "Aprobadas"], ["rechazada", "Rechazadas"]], qq.resultado),
    selectFiltro("con", [["", "Sobre cualquier país"], ...paisesRel], qq.con),
    checkFiltro("rel", "Solo con relaciones con otros países", qq.rel),
    checkFiltro("todas", "Incluir enmiendas y trámites", qq.todas),
    selectFiltro("orden", [["", "Más recientes"], ["asc", "Más antiguas"]], qq.orden),
  ], cambiar);
  const quePais = qq.con ? ` sobre ${nombrePais(qq.con)}` : "";
  return el("div", {},
    cabeceraPais(iso3, `${fuente.nombre} · ${textoAnios(recortarAnios(aniosActuales(), fuente))}. Por defecto, un asunto por fila con su votación final; marca «Incluir enmiendas y trámites» para ver cada votación.`, "Votaciones"),
    fs.length > 1 ? segmentos(fs.map((f) => [f.codigo, f.corto]), fuente.codigo, (v) => cambiar({ f: v })) : null,
    filtros,
    el("div", { class: "lista-cab" },
      el("b", {}, agrupar ? `${cuenta(total, "asunto", "asuntos")}${quePais}` : `${cuenta(total, "votación", "votaciones")}${quePais}`),
      leyendaSentidos()),
    filas.length ? el("div", { class: "lista" }, filas.map((v) => filaVotacion(v, fuente, () => panelVotacion(v.id)))) : el("div", { class: "vacio" }, "Ninguna votación con estos filtros."),
    total > TAM_PAGINA ? paginacion(total, pagina, TAM_PAGINA, (p) => irA("votaciones", { pagina: p })) : null);
}

// ------------------------------------------------------------------ detalle de una votación

function votoNominal(v) {
  const vn = q1("SELECT * FROM voto_nominal WHERE votacion_id=?", [v.id]);
  if (!vn.sentidos) return null;
  const plantilla = q(`SELECT p.pos, p.miembro_id, m.nombre FROM plantilla p LEFT JOIN miembro m ON m.id=p.miembro_id
                       WHERE p.fuente=? AND p.anio=? ORDER BY p.pos`, [v.fuente, v.anio]);
  const idx = Object.fromEntries(q("SELECT idx, codigo FROM partido_idx WHERE fuente=? AND anio=?", [v.fuente, v.anio]).map((r) => [r.idx, r.codigo]));
  const letra = { S: "si", N: "no", A: "abstencion", "-": "no_vota" };
  const grupos = {};
  for (const m of plantilla) {
    const s = vn.sentidos[m.pos];
    if (!s || s === ".") continue;
    const p = idx[vn.partidos.charCodeAt(m.pos) - 48];
    (grupos[p] = grupos[p] || []).push({ nombre: v.fuente === "onu" ? nombrePais(m.miembro_id) : m.nombre || m.miembro_id, iso3: m.miembro_id, sentido: letra[s] });
  }
  return grupos;
}

function panelVotacion(id) {
  const v = q1(`SELECT v.*, s.titulo, s.codigo, s.tipo AS tipo_asunto, s.url AS url_asunto, s.resultado AS resultado_asunto, s.autor
                FROM votacion v JOIN asunto s ON s.id=v.asunto_id WHERE v.id=?`, [id]);
  if (!v.id) return;
  const fi = q1("SELECT * FROM ficha WHERE asunto_id=?", [v.asunto_id]);
  const otras = q("SELECT * FROM votacion WHERE asunto_id=? ORDER BY fecha, numero", [v.asunto_id]);
  const grupos = q("SELECT * FROM voto_partido WHERE votacion_id=? ORDER BY si + no + abstencion + no_vota DESC", [id]);
  const nominal = votoNominal(v);
  const rels = jsonDe(fi.relaciones, []);
  const fuente = CAT.fuentes[v.fuente];
  const esOnu = v.fuente === "onu";
  const esPe = v.fuente === "eup";
  const resumen = limpiarResumen(fi.resumen);
  const relReglas = !fi.relaciones_origen || /reglas/.test(fi.relaciones_origen);
  const quienResume = !fi.origen || /reglas/.test(fi.origen) ? null : fi.origen.startsWith("escrutinio") ? "la IA de Escrutinio" : "una IA";
  // Por qué se le asigna cada país: el «motivo» de las reglas, dicho en llano.
  const motivoLlano = (m) => m.replace(/^regla: /, "").replace(/^nombra «(.+)»$/, "el título nombra «$1»")
    .replace(/^víctima de «(.+)»$/, "el título lo presenta como víctima").replace(/^agresor «(.+)»$/, "el título lo presenta como agresor")
    .replace(/^apoyo a «(.+)»$/, "el título expresa apoyo");
  const ficha = el("div", { class: "ficha" },
    resumen ? el("p", {}, resumen) : el("p", { class: "muted" }, "Sin resumen todavía: el título de arriba es el oficial."),
    el("div", { class: "badges" },
      fi.tema_principal ? el("span", { class: "badge" }, temaNombre(fi.tema_principal)) : null,
      jsonDe(fi.temas_secundarios, []).map((t) => el("span", { class: "badge" }, temaNombre(t))),
      jsonDe(fi.etiquetas, []).map((t) => el("span", { class: "badge ia" }, t))),
    rels.length ? el("div", {}, el("h4", {}, "Países de los que trata"), el("div", { class: "chips" }, rels.map((r) => chipRelacion(r))),
      rels.some((r) => r.motivo) ? el("details", { class: "rel-motivos" }, el("summary", { class: "small muted" }, "¿Por qué estos países y este sentido?"),
        rels.filter((r) => r.motivo).map((r) => el("div", { class: "small muted" }, `${nombrePais(r.pais)}: ${motivoLlano(r.motivo)}`))) : null) : null,
    el("div", { class: "procedencia" }, unirPartes([quienResume ? `Resumen y tema: ${quienResume}, a partir del título` : null,
      rels.length ? (relReglas ? "países y sentido: clasificación automática por palabras del título, sin IA" : "países y sentido: IA, a partir del título") : null]),
    ". Puede equivocarse: lo oficial es el voto y el texto enlazado."));
  const tablaGrupos = grupos.length ? el("table", { class: "tabla" },
    el("thead", {}, el("tr", {}, el("th", {}, esOnu ? "Región" : "Partido"), el("th", { class: "num" }, "Sí"), el("th", { class: "num" }, "No"),
      el("th", { class: "num" }, "Abst."), el("th", { class: "num" }, "No vota"), el("th", {}, "Posición"))),
    el("tbody", {}, grupos.map((g) => {
      const p = partido(v.fuente, g.partido);
      return el("tr", {}, el("td", {}, el("span", { class: "chip" }, el("span", { class: "sw", style: `background:${p.color}` }), p.nombre || g.partido)),
        el("td", { class: "num" }, fmt(g.si)), el("td", { class: "num" }, fmt(g.no)), el("td", { class: "num" }, fmt(g.abstencion)),
        el("td", { class: "num" }, fmt(g.no_vota)), el("td", {}, SENTIDO[g.sentido]?.[1] || g.sentido || ""));
    }))) : null;
  const nominalNodo = nominal ? el("div", { class: "nominal" }, Object.entries(nominal).sort((a, b) => b[1].length - a[1].length).map(([p, ms]) =>
    el("div", { class: "g" }, el("h4", {}, el("span", { class: "sw", style: `display:inline-block;width:10px;height:10px;border-radius:2px;background:${colorPartido(v.fuente, p)}` }),
      partido(v.fuente, p).nombre || p, el("span", { class: "muted" }, ` (${ms.length})`)),
    ms.sort((a, b) => a.nombre.localeCompare(b.nombre, "es")).map((m) => el("div", { class: "d" },
      esOnu ? el("a", { href: "#", onclick: (e) => { e.preventDefault(); cerrarPanel(); irA("onu", { p: m.iso3 }); } }, m.nombre)
        : el("span", {}, m.nombre, esPe ? el("span", { class: "muted small" }, ` · ${nombrePais(paisDeMiembro(m.iso3))}`) : null),
      el("span", { class: `v ${m.sentido}` }, SENTIDO[m.sentido][1])))))) : null;
  // Parlamento Europeo: cómo votan los eurodiputados de cada país (el país va en el id de cada uno).
  const tablaPaises = esPe && nominal ? tablaPaisesPe(nominal) : null;
  const camara = CAT.camaras[v.camara]?.nombre || "";
  const fuenteNombre = fuente?.nombre || v.fuente;
  abrirPanel(el("div", {},
    el("div", { class: "muted small" }, unirPartes([fuenteNombre, camara && !fuenteNombre.includes(camara) ? camara : null, fecha(v.fecha)])),
    el("h2", {}, v.titulo),
    el("div", { class: "badges" }, v.codigo ? el("span", { class: "badge" }, v.codigo) : null, el("span", { class: "badge" }, TIPOS_ASUNTO[v.tipo_asunto] || v.tipo_asunto),
      v.autor ? el("span", { class: "badge", title: v.autor }, `Propuesto por: ${nombreAutor(v.autor)}`) : null, v.url_asunto ? enlace(v.url_asunto, "Texto en la fuente ↗") : null),
    el("section", {}, ficha),
    el("section", {}, el("h3", {}, "Esta votación"),
      el("p", { class: "muted" }, unirPartes([TIPOS_VOTACION[v.tipo], v.texto])),
      el("div", { class: "badges" }, badgeResultado(v.resultado), v.mayoria ? el("span", { class: "badge" }, `mayoría ${v.mayoria}`) : null,
        v.url ? enlace(v.url, "Votación en la fuente ↗") : null),
      el("div", { style: "max-width:420px;margin-top:8px" }, barraVotos(v))),
    tablaGrupos ? el("section", {}, el("h3", {}, esOnu ? "Por región" : esPe ? "Por grupo europeo" : "Por partido"), el("div", { class: "tabla-scroll" }, tablaGrupos)) : null,
    tablaPaises ? el("section", {}, el("h3", {}, "Por país de los eurodiputados"), el("div", { class: "tabla-scroll" }, tablaPaises)) : null,
    otras.length > 1 ? el("section", {}, el("h3", {}, `Todas las votaciones del asunto (${otras.length})`),
      el("div", { class: "tabla-scroll" }, el("table", { class: "tabla" }, el("tbody", {}, otras.map((o) =>
        el("tr", { class: "clic" + (o.id === id ? " actual" : ""), onclick: () => panelVotacion(o.id) },
          el("td", {}, fecha(o.fecha)), el("td", {}, CAT.camaras[o.camara]?.corto || ""), el("td", {}, TIPOS_VOTACION[o.tipo]),
          el("td", {}, recortar(unirPartes([o.texto]), 90)), el("td", {}, badgeResultado(o.resultado)),
          el("td", { class: "num", title: "Sí – No" }, `${fmt(o.a_favor)}–${fmt(o.en_contra)}`))))))) : null,
    nominalNodo ? el("section", {}, el("h3", {}, esOnu ? "Voto de cada Estado" : esPe ? "Voto de cada eurodiputado" : "Voto de cada legislador"), nominalNodo) : null),
  { v: id });
}

// ------------------------------------------------------------------ Partidos

VISTAS.partidos = {
  titulo: "Partidos",
  datos: () => fuentesPais(paisActual()).flatMap((f) => nombresFuente(f.codigo, aniosActuales())),
  pintar: pintarPartidos,
};

// Escala divergente de 7 tramos (rojo, gris, azul) para celdas: índice 0..6 y color de la letra.
const DIVERGENTE = ["--div-1", "--div-2", "--div-3", "--div-4", "--div-5", "--div-6", "--div-7"];
const tintaDivergente = (i) => (i === 0 || i === 6 ? "#fff" : "var(--ink)");
const tramoDe = (v, cortes) => cortes.filter((c) => v >= c).length;
function leyendaCeldas(rampa, izquierda, derecha) {
  return el("div", { class: "leyenda-celdas" }, el("span", {}, izquierda),
    rampa.map((v) => el("i", { style: `background:var(${v})` })), el("span", {}, derecha));
}

// Aviso para cuando faltan relaciones: las reglas solo leen títulos en inglés y en español; en las demás
// lenguas, las relaciones con otros países salen de la ficha de la IA, que se hace poco a poco.
function sinFichaIA(fuente, a, b) {
  const filas = CAT.cobertura.filter((c) => c.fuente === fuente.codigo && c.anio >= a && c.anio <= b);
  const asuntos = filas.reduce((s, c) => s + (c.asuntos || 0), 0), fichas = filas.reduce((s, c) => s + (c.fichas_ia || 0), 0);
  return asuntos && fichas < asuntos ? ` (${fmt(asuntos - fichas)} de ${fmt(asuntos)} asuntos aún no tienen ficha de la IA)` : "";
}

function pintarPartidos(qq) {
  const iso3 = paisActual();
  if (!iso3) return elegirParlamento("Partidos");
  const fs = fuentesPais(iso3);
  if (!fs.length) return el("div", {}, cabeceraPais(iso3, null, "Partidos"), sinParlamento(iso3));
  const fuente = fs.find((f) => f.codigo === qq.f) || fs[0];
  const [a, b] = recortarAnios(aniosActuales(), fuente);
  const tema = qq.tema || "";
  const filas = q(`SELECT a, b, SUM(coinciden) AS c, SUM(total) AS t FROM afinidad WHERE fuente=? AND anio BETWEEN ? AND ? AND tema=?
                   GROUP BY a, b`, [fuente.codigo, a, b, tema]);
  const peso = {};
  for (const r of q(`SELECT p.partido, COUNT(*) AS n, SUM(p.si + p.no + p.abstencion + p.no_vota) AS miembros FROM voto_partido p
                     JOIN votacion v ON v.id=p.votacion_id WHERE v.fuente=? AND v.anio BETWEEN ? AND ? GROUP BY p.partido`, [fuente.codigo, a, b])) {
    peso[r.partido] = r;
  }
  const partidos = Object.keys(peso).filter((p) => peso[p].n >= 20 && p !== "?").sort((x, y) => peso[y].miembros - peso[x].miembros).slice(0, 14);
  const af = {};
  for (const r of filas) { af[`${r.a}|${r.b}`] = r; af[`${r.b}|${r.a}`] = r; }
  const valorAf = (x, y) => { const r = af[`${x}|${y}`]; return r && r.t >= 5 ? r.c / r.t : null; };
  // Orden por bloques: los dos partidos grandes que menos coinciden hacen de polos y cada partido se coloca
  // según se parezca más a uno o a otro. Así los bloques quedan juntos en la matriz.
  let polos = null, peor = 2;
  const grandes = partidos.slice(0, 6);
  grandes.forEach((x, i) => grandes.slice(i + 1).forEach((y) => { const v = valorAf(x, y); if (v !== null && v < peor) { peor = v; polos = [x, y]; } }));
  if (polos) {
    const [A, B] = polos;
    const punt = (p) => (p === A ? 9 : p === B ? -9 : (valorAf(p, A) ?? 0.5) - (valorAf(p, B) ?? 0.5));
    partidos.sort((x, y) => punt(y) - punt(x));
  }
  const RAMPA = ["--seq-100", "--seq-200", "--seq-300", "--seq-400", "--seq-500", "--seq-600", "--seq-700"];
  const siglas = (p) => partido(fuente.codigo, p).siglas || p;
  const nombreCompleto = (p) => partido(fuente.codigo, p).nombre;
  const celda = (x, y) => {
    if (x === y) return el("td", { class: "self" });
    const r = af[`${x}|${y}`];
    if (!r || r.t < 5) return el("td", { class: "self", title: "No coincidieron en esos años (legislaturas distintas) o votaron juntos muy pocas veces" }, "·");
    const v = r.c / r.t, i = Math.min(6, Math.floor(v * 7));
    return conTip(el("td", { style: `background:var(${RAMPA[i]});color:${i >= 4 ? "var(--seq-ink-alto)" : "var(--ink)"}` }, `${Math.round(100 * v)}`),
      `${Math.round(100 * v)} %`, `${siglas(x)} y ${siglas(y)}`, `Votan igual en ${fmt(r.c)} de ${cuenta(r.t, "votación", "votaciones")}`);
  };
  const cabecera = () => el("thead", {}, el("tr", {}, el("th", {}),
    partidos.map((p) => el("th", { class: "rot", title: nombreCompleto(p) }, el("div", {}, siglas(p))))));
  const mapaCalor = partidos.length > 1 ? el("div", { class: "heat" }, el("table", {}, cabecera(),
    el("tbody", {}, partidos.map((x) => el("tr", {}, el("th", { style: "text-align:right", title: nombreCompleto(x) }, siglas(x)), partidos.map((y) => celda(x, y)))))))
    : el("p", { class: "muted" }, "Hace falta más de un partido con votaciones.");
  // Al lado: cómo se lee, los pares que más y menos coinciden y qué es cada sigla.
  const pares = [];
  partidos.forEach((x, i) => partidos.slice(i + 1).forEach((y) => { const r = af[`${x}|${y}`]; if (r && r.t >= 20) pares.push({ x, y, v: r.c / r.t }); }));
  pares.sort((p1, p2) => p2.v - p1.v);
  const par = (p) => el("li", {}, el("b", {}, `${siglas(p.x)} y ${siglas(p.y)}`), ` · ${Math.round(100 * p.v)} %`);
  const conNombre = partidos.filter((p) => nombreCompleto(p) && nombreCompleto(p) !== siglas(p));
  const lateral = el("div", { class: "heat-lateral" },
    leyendaCeldas(RAMPA, "0 %", "100 %"),
    el("p", { class: "muted small" }, "Cada casilla: en qué porcentaje de las votaciones los dos partidos votaron lo mismo. Van ordenados por bloques: los que votan parecido quedan juntos. «·»: no coincidieron en la cámara en esos años."),
    pares.length > 3 ? el("div", {}, el("h4", {}, "Los que más coinciden"), el("ul", { class: "lista-pares" }, pares.slice(0, 3).map(par)),
      el("h4", {}, "Los que menos"), el("ul", { class: "lista-pares" }, pares.slice(-3).reverse().map(par))) : null,
    conNombre.length ? el("details", { class: "siglas" }, el("summary", { class: "small" }, "Qué es cada sigla"),
      el("ul", { class: "lista-pares small" }, conNombre.map((p) => el("li", {}, el("b", {}, siglas(p)), `: ${nombreCompleto(p)}`)))) : null);

  // Apoyo por tema. Un partido del Gobierno vota no a casi todas las mociones de la oposición (y al revés), así
  // que el % de síes dice más de quién propone que del tema. Por defecto se compara con su media: más o menos
  // a favor de lo que ese partido suele votar sí.
  const modoTema = qq.apoyo === "abs" ? "abs" : "rel";
  const temas = q(`SELECT fi.tema_principal AS tema, p.partido, SUM(p.sentido='si') AS si, COUNT(*) AS n FROM voto_partido p
                   JOIN votacion v ON v.id=p.votacion_id JOIN ficha fi ON fi.asunto_id=v.asunto_id
                   WHERE v.fuente=? AND v.anio BETWEEN ? AND ? AND v.decisiva=1 AND p.sentido IN ('si','no','abstencion','dividido')
                     AND fi.tema_principal IS NOT NULL GROUP BY 1, 2`, [fuente.codigo, a, b]);
  const apoyo = {}, media = {};
  for (const r of temas) {
    apoyo[`${r.tema}|${r.partido}`] = r;
    const m = (media[r.partido] = media[r.partido] || { si: 0, n: 0 });
    m.si += r.si; m.n += r.n;
  }
  const pctMedia = (p) => Math.round((100 * media[p].si) / Math.max(1, media[p].n));
  const temasCon = [...new Set(temas.map((r) => r.tema))].sort((x, y) => temaNombre(x).localeCompare(temaNombre(y), "es"));
  const celdaTema = (t, p) => {
    const r = apoyo[`${t}|${p}`];
    if (!r || r.n < 3) return el("td", { class: "self" }, "·");
    const v = r.si / r.n, m = media[p].si / Math.max(1, media[p].n);
    if (modoTema === "abs") {
      const i = Math.min(6, Math.floor(v * 7));
      return conTip(el("td", { style: `background:var(${RAMPA[i]});color:${i >= 4 ? "var(--seq-ink-alto)" : "var(--ink)"}` }, `${Math.round(100 * v)}`),
        `${Math.round(100 * v)} % a favor`, `${siglas(p)} · ${temaNombre(t)}`, `${fmt(r.si)} de ${cuenta(r.n, "votación final", "votaciones finales")}`);
    }
    const d = Math.round(100 * (v - m)), i = tramoDe(d, [-19, -11, -4, 5, 12, 20]);
    return conTip(el("td", { style: `background:var(${DIVERGENTE[i]});color:${tintaDivergente(i)}` }, d > 0 ? `+${d}` : d < 0 ? `−${-d}` : "0"),
      `${Math.round(100 * v)} % a favor en este tema`, `${siglas(p)} · ${temaNombre(t)}`,
      `Su media en todos los temas: ${Math.round(100 * m)} %. ${fmt(r.si)} de ${cuenta(r.n, "votación final", "votaciones finales")}.`);
  };
  const tablaApoyo = el("div", { class: "heat" }, el("table", {}, cabecera(),
    el("tbody", {},
      el("tr", { class: "fila-media" }, el("th", { style: "text-align:right" }, "Todos los temas (% sí)"), partidos.map((p) => (media[p]
        ? el("td", { class: "media", title: `${siglas(p)} vota sí en el ${pctMedia(p)} % de las votaciones finales` }, `${pctMedia(p)}`)
        : el("td", { class: "self" }, "·")))),
      temasCon.map((t) => el("tr", {}, el("th", { style: "text-align:right;white-space:nowrap" }, temaNombre(t)), partidos.map((p) => celdaTema(t, p)))))));

  // Partido × país: cuánto vota cada partido a favor de cada país (lo que distingue a Concordia).
  const relFilas = q(`SELECT v.id, fi.relaciones, p.partido, p.sentido FROM votacion v JOIN ficha fi ON fi.asunto_id=v.asunto_id
                      JOIN voto_partido p ON p.votacion_id=v.id
                      WHERE v.fuente=? AND v.anio BETWEEN ? AND ? AND v.decisiva=1 AND fi.relaciones IS NOT NULL AND fi.relaciones <> '[]'
                        AND p.sentido IN ('si','no','abstencion')`, [fuente.codigo, a, b]);
  const relDe = {}, porPais = {}, votosPais = {};
  for (const r of relFilas) {
    const rels = (relDe[r.id] ??= jsonDe(r.relaciones, []).filter((x) => x.pais !== iso3 && ORIENTACION_TXT[x.orientacion]));
    for (const x of rels) {
      const o = ORIENTACION_TXT[x.orientacion];
      (votosPais[x.pais] = votosPais[x.pais] || new Set()).add(r.id);
      const deP = (porPais[x.pais] = porPais[x.pais] || {});
      const c = (deP[r.partido] = deP[r.partido] || { fav: 0, contra: 0, abst: 0 });
      if (r.sentido === "abstencion") c.abst++;
      else if ((r.sentido === "si") === (o > 0)) c.fav++;
      else c.contra++;
    }
  }
  const paisesTop = Object.keys(votosPais).filter((p) => votosPais[p].size >= 2).sort((x, y) => votosPais[y].size - votosPais[x].size).slice(0, 15);
  const celdaPais = (pais, p) => {
    const c = porPais[pais]?.[p];
    if (!c || c.fav + c.contra < 1) return el("td", { class: "self" }, "·");
    const v = c.fav / (c.fav + c.contra), i = tramoDe(100 * v, [20, 35, 45, 56, 66, 81]);
    return conTip(el("td", { style: `background:var(${DIVERGENTE[i]});color:${tintaDivergente(i)}` }, `${Math.round(100 * v)}`),
      `${Math.round(100 * v)} % a favor de ${nombrePais(pais)}`, `${siglas(p)} · ${nombrePais(pais)}`,
      `A favor en ${cuenta(c.fav, "votación", "votaciones")}, en contra en ${fmt(c.contra)}${c.abst ? `, se abstuvo en ${fmt(c.abst)}` : ""}.`);
  };
  const tablaPaises = paisesTop.length ? el("div", { class: "heat" }, el("table", {}, cabecera(),
    el("tbody", {}, paisesTop.map((pais) => el("tr", { class: "clic", title: `Ver las votaciones sobre ${nombrePais(pais)}`, onclick: () => irA("votaciones", { con: pais }) },
      el("th", { style: "text-align:right;white-space:nowrap" }, nombrePais(pais), el("span", { class: "muted" }, ` (${votosPais[pais].size})`)),
      partidos.map((p) => celdaPais(pais, p)))))))
    : el("p", { class: "muted" }, `Ningún asunto de estos años trata de otros países con un sentido claro${sinFichaIA(fuente, a, b)}.`);

  return el("div", {},
    cabeceraPais(iso3, `${fuente.nombre} · ${textoAnios([a, b])}.`, "Partidos"),
    fs.length > 1 ? segmentos(fs.map((f) => [f.codigo, f.corto]), fuente.codigo, (v) => irA("partidos", { f: v })) : null,
    el("section", { class: "card" }, el("h3", {}, "Con quién vota cada partido"),
      el("p", { class: "muted small" }, "Porcentaje de votaciones (salvo trámites) en que dos partidos adoptan la misma posición: la de al menos dos tercios de sus miembros."),
      filaFiltros([selectFiltro("tema", [["", "Todos los temas"], ...CAT.temas.map((t) => [t.codigo, t.nombre])], tema)], (c) => irA("partidos", c)),
      el("div", { class: "heat-caja" }, mapaCalor, lateral)),
    el("section", { class: "card" }, el("h3", {}, "Cómo vota cada partido sobre otros países"),
      el("p", { class: "muted small" }, "Porcentaje de sus votos a favor de cada país: sí a lo que lo favorece (ayuda, acuerdos, apoyo) o no a lo que lo perjudica (sanciones, condenas). 100: siempre a su favor; 0: siempre en contra. Entre paréntesis, cuántas votaciones hay; pulsa un país para verlas. El sentido de cada asunto se deduce del título y puede equivocarse."),
      el("div", { class: "heat-caja" }, tablaPaises, el("div", { class: "heat-lateral" }, leyendaCeldas(DIVERGENTE, "en contra", "a favor")))),
    el("section", { class: "card" }, el("h3", {}, "A favor, por tema"),
      segmentos([["rel", "Frente a su media"], ["abs", "% de votos a favor"]], modoTema, (v) => irA("partidos", { apoyo: v === "rel" ? "" : v })),
      el("p", { class: "muted small" }, modoTema === "rel"
        ? "Cuántos puntos más (azul) o menos (rojo) vota sí el partido en cada tema que en el conjunto de sus votaciones finales (primera fila). Así se descuenta que un partido del Gobierno vote no a casi todo lo que propone la oposición, y al revés."
        : "Porcentaje de votaciones finales de cada tema en que el partido votó sí. Ojo: depende mucho de quién propone; un partido del Gobierno vota no a casi todas las mociones de la oposición."),
      el("div", { class: "heat-caja" }, tablaApoyo, el("div", { class: "heat-lateral" },
        modoTema === "rel" ? leyendaCeldas(DIVERGENTE, "menos que su media", "más") : leyendaCeldas(RAMPA, "0 %", "100 %")))));
}

// ------------------------------------------------------------------ En la ONU

VISTAS.onu = {
  titulo: "En la ONU",
  datos: () => [...nombresOnu(), ...nombresMundo(aniosOnu())],
  pintar: pintarOnu,
};

// Sin país elegido: todas las resoluciones con su resultado, sin el voto de ningún Estado en concreto.
function pintarOnuGlobal(qq) {
  const [a, b] = aniosOnu();
  if (a > b) {
    return el("div", {}, cabeceraPais(null, null, "En la ONU"), el("div", { class: "vacio" }, `La ONU tiene datos hasta ${ONU_HASTA}: elige años anteriores.`));
  }
  const base = "FROM votacion v JOIN asunto s ON s.id=v.asunto_id LEFT JOIN ficha fi ON fi.asunto_id=s.id";
  const w = ["v.fuente='onu'", "v.anio BETWEEN ? AND ?"], args = [a, b];
  if (qq.todas !== "1") w.push("v.tipo='final'");
  const temas = lista(qq.tema);
  if (temas.length) { w.push(`fi.tema_principal IN (${marcas(temas)})`); args.push(...temas); }
  if (qq.imp === "1") w.push("v.importante=1");
  for (const palabra of (qq.q || "").split(/\s+/).filter(Boolean)) {
    w.push("(s.titulo LIKE ? OR fi.resumen LIKE ? OR s.codigo LIKE ?)");
    args.push(...Array(3).fill(`%${palabra}%`));
  }
  const where = w.join(" AND ");
  const t = q1(`SELECT COUNT(*) AS n, SUM(v.a_favor) AS si, SUM(v.en_contra) AS no, SUM(v.abstenciones) AS abst,
                  SUM(COALESCE(v.en_contra, 0)=0) AS sin_no ${base} WHERE ${where}`, args);
  const emitidos = (t.si || 0) + (t.no || 0) + (t.abst || 0);
  const pagina = Math.max(1, +(qq.pagina || 1));
  const filas = q(`SELECT v.*, s.titulo, s.codigo, fi.resumen, fi.tema_principal, fi.relaciones ${base} WHERE ${where}
                   ORDER BY v.fecha DESC, v.numero DESC LIMIT ? OFFSET ?`, [...args, TAM_PAGINA, (pagina - 1) * TAM_PAGINA]);
  const cambiar = (c) => irA("onu", { ...c, pagina: "" });
  return el("div", {},
    cabeceraPais(null, `Votaciones de la Asamblea General de la ONU · ${textoAnios([a, b])}${b < aniosActuales()[1] ? ` (los datos llegan a ${ONU_HASTA})` : ""}. Elige un país para ver cómo votó y con quién coincide.`, "En la ONU"),
    el("div", { class: "grid g4" },
      stat("Votaciones", fmt(t.n), qq.todas === "1" ? "todas" : "votaciones finales de resoluciones"),
      stat("Sí", `${pct(t.si, emitidos)} %`, "de todos los votos emitidos"), stat("No", `${pct(t.no, emitidos)} %`, "de todos los votos emitidos"),
      stat("Sin ningún no", `${pct(t.sin_no, t.n)} %`, `${cuenta(t.sin_no, "votación", "votaciones")} sin votos en contra`)),
    el("div", { class: "segmentos", style: "margin-top:16px" },
      el("button", { class: "boton", onclick: () => irA("mundo", { modo: "afinidad" }) }, "Mapa: con quién vota igual cada país")),
    el("h3", { style: "margin-top:20px" }, "Cada resolución, con su resultado"),
    filaFiltros([
      buscarFiltro("q", qq.q, "Buscar resolución…"),
      multiSelect("tema", CAT.temas.map((x) => [x.codigo, x.nombre]), qq.tema, "Todos los temas", "temas"),
      Object.assign(checkFiltro("imp", "Solo las votaciones clave (según EE. UU.)", qq.imp),
        { title: "Votaciones que el Departamento de Estado de EE. UU. considera clave en su informe anual sobre la ONU" }),
      checkFiltro("todas", "Incluir enmiendas y párrafos", qq.todas),
    ], cambiar),
    filas.length ? el("div", { class: "lista" }, filas.map((v) => el("div", { class: "fila", onclick: () => panelVotacion(v.id) },
      el("div", {}, el("div", { class: "fecha" }, fecha(v.fecha)), el("div", { class: "muted small" }, v.codigo || "")),
      el("div", {}, el("div", { class: "titulo" }, recortar(v.titulo, 200)),
        limpiarResumen(v.resumen) ? el("div", { class: "resumen" }, limpiarResumen(v.resumen)) : null,
        el("div", { class: "badges" }, v.tema_principal ? el("span", { class: "badge" }, temaNombre(v.tema_principal)) : null,
          v.tipo !== "final" ? el("span", { class: "badge" }, TIPOS_VOTACION[v.tipo]) : null,
          jsonDe(v.relaciones, []).slice(0, 4).map((r) => chipRelacion(r)))),
      el("div", {}, barraVotos(v)))))
      : el("div", { class: "vacio" }, "Ninguna votación con estos filtros."),
    t.n > TAM_PAGINA ? paginacion(t.n, pagina, TAM_PAGINA, (p) => irA("onu", { pagina: p })) : null);
}

function pintarOnu(qq) {
  const iso3 = paisActual();
  if (!iso3) return pintarOnuGlobal(qq);
  const [a, b] = aniosOnu();
  const p = CAT.paises[iso3] || {};
  if (a > b || !p.onu_desde) {
    return el("div", {}, cabeceraPais(iso3, null, "En la ONU"), el("div", { class: "vacio" },
      esOrganismo(iso3) ? `${nombrePais(iso3)} no es un Estado: no vota en la Asamblea General. Sí votan cada uno de sus miembros.`
        : !p.onu_desde ? `${nombrePais(iso3)} no tiene votos registrados en la Asamblea General.` : `La ONU tiene datos hasta ${ONU_HASTA}: elige años anteriores.`));
  }
  const base = `FROM votacion v JOIN asunto s ON s.id=v.asunto_id LEFT JOIN ficha fi ON fi.asunto_id=s.id
                JOIN plantilla pl ON pl.fuente='onu' AND pl.anio=v.anio AND pl.miembro_id=?
                JOIN voto_nominal vn ON vn.votacion_id=v.id`;
  const w = ["v.fuente='onu'", "v.anio BETWEEN ? AND ?"], args = [iso3, a, b];
  if (qq.todas !== "1") w.push("v.tipo='final'");
  const temas = lista(qq.tema);
  if (temas.length) { w.push(`fi.tema_principal IN (${marcas(temas)})`); args.push(...temas); }
  if (qq.imp === "1") w.push("v.importante=1");
  if (qq.voto) { w.push("substr(vn.sentidos, pl.pos + 1, 1)=?"); args.push(qq.voto); }
  for (const palabra of (qq.q || "").split(/\s+/).filter(Boolean)) {
    w.push("(s.titulo LIKE ? OR fi.resumen LIKE ? OR s.codigo LIKE ?)");
    args.push(...Array(3).fill(`%${palabra}%`));
  }
  const where = w.join(" AND ");
  const t = q1(`SELECT COUNT(*) AS n, SUM(substr(vn.sentidos, pl.pos + 1, 1)='S') AS si, SUM(substr(vn.sentidos, pl.pos + 1, 1)='N') AS no,
                  SUM(substr(vn.sentidos, pl.pos + 1, 1)='A') AS abst, SUM(substr(vn.sentidos, pl.pos + 1, 1)='-') AS aus ${base} WHERE ${where}`, args);
  const pagina = Math.max(1, +(qq.pagina || 1));
  const filas = q(`SELECT v.*, s.titulo, s.codigo, fi.resumen, fi.tema_principal, fi.relaciones, substr(vn.sentidos, pl.pos + 1, 1) AS voto
                   ${base} WHERE ${where} ORDER BY v.fecha DESC, v.numero DESC LIMIT ? OFFSET ?`, [...args, TAM_PAGINA, (pagina - 1) * TAM_PAGINA]);
  const afines = afinidadCon(iso3, [a, b]).sort((x, y) => y.pct - x.pct);
  const comparar = lista(qq.cmp).length ? lista(qq.cmp) : COMPARAR_ONU.filter((x) => x !== iso3).slice(0, 4);
  const series = comparar.map((otro, i) => ({
    nombre: nombrePais(otro), color: COLORES_SERIE[i % COLORES_SERIE.length],
    puntos: q(`SELECT anio AS x, 100.0 * SUM(suma) / SUM(total) AS y FROM afinidad_onu WHERE ((a=?1 AND b=?2) OR (a=?2 AND b=?1))
               AND anio BETWEEN ?3 AND ?4 GROUP BY anio`, [iso3, otro, a, b]),
  })).filter((s) => s.puntos.length);
  const LETRA = { S: ["si", "Sí"], N: ["no", "No"], A: ["abstencion", "Abstención"], "-": ["no_vota", "No vota"] };
  const cambiar = (c) => irA("onu", { ...c, pagina: "" });
  const opPaises = Object.values(CAT.paises).filter((x) => x.onu_desde).sort((x, y) => x.nombre.localeCompare(y.nombre, "es")).map((x) => [x.iso3, x.nombre]);
  return el("div", {},
    cabeceraPais(iso3, `Voto de ${nombrePais(iso3)} en la Asamblea General de la ONU · ${textoAnios([a, b])}${b < aniosActuales()[1] ? ` (los datos llegan a ${ONU_HASTA})` : ""}.`, "En la ONU"),
    el("div", { class: "grid g4" },
      stat("Votaciones", fmt(t.n), qq.todas === "1" ? "todas" : "votaciones finales de resoluciones"),
      stat("Sí", `${pct(t.si, t.n)} %`, cuenta(t.si, "votación", "votaciones")), stat("No", `${pct(t.no, t.n)} %`, cuenta(t.no, "votación", "votaciones")),
      stat("Abstención", `${pct(t.abst, t.n)} %`, unirPartes([cuenta(t.abst, "votación", "votaciones"), t.aus ? `no votó en ${fmt(t.aus)}` : null]))),
    el("div", { class: "grid g2", style: "margin-top:16px" },
      el("section", { class: "card" }, el("h3", {}, `Los que más votan como ${nombrePais(iso3)}`),
        puntosH(afines.slice(0, 10).map((r) => ({ etiqueta: nombrePais(r.otro), valor: r.pct, tip: cuenta(r.t, "votación en común", "votaciones en común"), iso3: r.otro })),
          { color: "var(--rel-p2)", alClicar: (i) => irA("onu", { p: i.iso3 }, { arriba: true }) })),
      el("section", { class: "card" }, el("h3", {}, "Los que menos"),
        puntosH(afines.slice(-10).reverse().map((r) => ({ etiqueta: nombrePais(r.otro), valor: r.pct, tip: cuenta(r.t, "votación en común", "votaciones en común"), iso3: r.otro })),
          { color: "var(--rel-n2)", alClicar: (i) => irA("onu", { p: i.iso3 }, { arriba: true }) }))),
    el("section", { class: "card", style: "margin-top:16px" }, el("h3", {}, "Coincidencia por año"),
      filaFiltros([multiSelect("cmp", opPaises, comparar.join(","), "Comparar con…", "países", { buscar: true })], cambiar),
      lineasAnio(series)),
    el("h3", { style: "margin-top:20px" }, `Cómo ha votado ${nombrePais(iso3)} cada resolución`),
    filaFiltros([
      buscarFiltro("q", qq.q, "Buscar resolución…"),
      multiSelect("tema", CAT.temas.map((x) => [x.codigo, x.nombre]), qq.tema, "Todos los temas", "temas"),
      selectFiltro("voto", [["", "Cualquier voto"], ["S", "Votó sí"], ["N", "Votó no"], ["A", "Se abstuvo"], ["-", "No votó"]], qq.voto),
      Object.assign(checkFiltro("imp", "Solo las votaciones clave (según EE. UU.)", qq.imp),
        { title: "Votaciones que el Departamento de Estado de EE. UU. considera clave en su informe anual sobre la ONU" }),
      checkFiltro("todas", "Incluir enmiendas y párrafos", qq.todas),
    ], cambiar),
    filas.length ? el("div", { class: "lista" }, filas.map((v) => {
      const [c, txt] = LETRA[v.voto] || LETRA["-"];
      return el("div", { class: "fila", onclick: () => panelVotacion(v.id) },
        el("div", {}, el("div", { class: "fecha" }, fecha(v.fecha)), el("div", { class: "muted small" }, v.codigo || "")),
        el("div", {}, el("div", { class: "titulo" }, recortar(v.titulo, 200)),
          limpiarResumen(v.resumen) ? el("div", { class: "resumen" }, limpiarResumen(v.resumen)) : null,
          el("div", { class: "badges" }, v.tema_principal ? el("span", { class: "badge" }, temaNombre(v.tema_principal)) : null,
            v.tipo !== "final" ? el("span", { class: "badge" }, TIPOS_VOTACION[v.tipo]) : null,
            jsonDe(v.relaciones, []).slice(0, 4).map((r) => chipRelacion(r)))),
        el("div", {}, el("div", { class: `voto-pais ${c}` }, `${nombrePais(iso3)}: ${txt}`), barraVotos(v)));
    })) : el("div", { class: "vacio" }, "Ninguna votación con estos filtros."),
    t.n > TAM_PAGINA ? paginacion(t.n, pagina, TAM_PAGINA, (p) => irA("onu", { pagina: p })) : null);
}
