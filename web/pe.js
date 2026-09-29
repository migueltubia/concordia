"use strict";

// ------------------------------------------------------------------ En el Parlamento Europeo
// Cómo votan los eurodiputados de cada país. El país va en el id de cada eurodiputado («eup:ESP:257043»):
// la plantilla de cada año dice qué posiciones de la cadena de sentidos son de cada delegación nacional.
// Con la Unión Europea elegida, la comparación de todas las delegaciones.

const PE = "eup";
const paisDeMiembro = (id) => id.split(":")[1];
const LETRAS_PE = "SNA-"; // sí, no, abstención, no vota («.»: no era eurodiputado ese día)
const SIN_GRUPO_PE = new Set(["NI", "?"]); // los no inscritos no votan como grupo: no se mide si votan «con su grupo»

VISTAS.pe = {
  titulo: "En el Parlamento Europeo",
  datos: () => (CAT.fuentes[PE]?.votaciones ? nombresFuente(PE, aniosPe()) : []),
  pintar: pintarPe,
};
const aniosPe = () => recortarAnios(aniosActuales(), CAT.fuentes[PE] || {});

// Posición de un recuento: la opción más votada entre sí, no y abstención (null si nadie vota o hay empate).
function posicionPe(si, no, ab) {
  const m = Math.max(si, no, ab);
  if (!m || (si === m) + (no === m) + (ab === m) > 1) return null;
  return si === m ? "S" : no === m ? "N" : "A";
}
// Como en el voto por partido: la opción de al menos dos tercios de los que votan; si no, «dividido».
function sentidoPe(si, no, ab) {
  const t = si + no + ab;
  if (!t) return "no_vota";
  return si * 3 >= 2 * t ? "si" : no * 3 >= 2 * t ? "no" : ab * 3 >= 2 * t ? "abstencion" : "dividido";
}
const LETRA_A_SENTIDO = { S: "si", N: "no", A: "abstencion" };

// Una pasada por todas las votaciones (salvo trámites) de esos años, guardada para no repetirla al cambiar de
// país o de filtro: por votación, cuántos sí, no, abstenciones y ausencias tiene cada delegación y qué vota
// cada grupo (la opción más votada por sus miembros).
let CACHE_PE = null;
function recuentoPe([a, b]) {
  const clave = `${a}-${b}-${CARGADOS.size}`;
  if (CACHE_PE?.clave === clave) return CACHE_PE;
  const idx = {}, paises = [], plantilla = {}, dePais = []; // dePais[c][anio]: los eurodiputados de un país ese año
  for (const r of q("SELECT anio, pos, miembro_id FROM plantilla WHERE fuente=? AND anio BETWEEN ? AND ? ORDER BY anio, pos", [PE, a, b])) {
    const p = paisDeMiembro(r.miembro_id);
    if (!(p in idx)) { idx[p] = paises.length; paises.push(p); dePais.push({}); }
    const m = { pos: r.pos, id: r.miembro_id, c: idx[p] };
    (plantilla[r.anio] = plantilla[r.anio] || []).push(m);
    (dePais[m.c][r.anio] ??= []).push(m);
  }
  const grupoDe = {}; // «anio|índice» -> código del grupo
  for (const r of q("SELECT anio, idx, codigo FROM partido_idx WHERE fuente=? AND anio BETWEEN ? AND ?", [PE, a, b])) grupoDe[`${r.anio}|${r.idx}`] = r.codigo;
  const votos = [];
  for (const v of q(`SELECT v.id, v.anio, v.resultado, vn.sentidos, vn.partidos FROM votacion v JOIN voto_nominal vn ON vn.votacion_id=v.id
                     WHERE v.fuente=? AND v.anio BETWEEN ? AND ? AND v.tipo <> 'procedimiento'`, [PE, a, b])) {
    const cuenta = new Int16Array(paises.length * 4);
    const grupos = {};
    for (const m of plantilla[v.anio] || []) {
      const s = LETRAS_PE.indexOf(v.sentidos[m.pos]);
      if (s < 0) continue;
      cuenta[m.c * 4 + s]++;
      if (s < 3) (grupos[v.partidos.charCodeAt(m.pos)] ??= [0, 0, 0])[s]++;
    }
    const posGrupo = {};
    for (const [g, [si, no, ab]] of Object.entries(grupos)) posGrupo[g] = posicionPe(si, no, ab);
    // Posición de cada delegación, una letra por país («.»: sin posición), para comparar delegaciones deprisa.
    let pos = "";
    for (let c = 0; c < paises.length; c++) pos += posicionPe(cuenta[c * 4], cuenta[c * 4 + 1], cuenta[c * 4 + 2]) || ".";
    votos.push({ id: v.id, anio: v.anio, resultado: v.resultado, sentidos: v.sentidos, partidos: v.partidos, cuenta, posGrupo, pos });
  }
  CACHE_PE = { clave, idx, paises, plantilla, dePais, grupoDe, votos, porId: Object.fromEntries(votos.map((v) => [v.id, v])) };
  return CACHE_PE;
}
const cuentaDe = (v, c) => [v.cuenta[c * 4], v.cuenta[c * 4 + 1], v.cuenta[c * 4 + 2], v.cuenta[c * 4 + 3]];

// Participación, unidad y coincidencia con el resultado de una delegación.
function perfilDelegacion(R, c) {
  let votaciones = 0, emitidos = 0, escanos = 0, unida = 0, conVoto = 0, conPleno = 0, conResultado = 0;
  for (const v of R.votos) {
    const [si, no, ab, nv] = cuentaDe(v, c);
    const t = si + no + ab;
    if (!t && !nv) continue; // sin eurodiputados ese día
    votaciones++; emitidos += t; escanos += t + nv;
    if (!t) continue;
    conVoto++;
    if (Math.max(si, no, ab) * 3 >= 2 * t) unida++;
    const p = posicionPe(si, no, ab);
    if (p && v.resultado) { conResultado++; if (p === (v.resultado === "aprobada" ? "S" : "N")) conPleno++; }
  }
  return { votaciones, participacion: pct(emitidos, escanos), unida: pct(unida, conVoto), conPleno: pct(conPleno, conResultado) };
}

// Con qué delegaciones coincide la posición de una: [{otro, pct, t}].
function afinidadDelegaciones(R, c) {
  const n = R.paises.map(() => [0, 0]);
  for (const v of R.votos) {
    const p = v.pos[c];
    if (p === ".") continue;
    for (let d = 0; d < R.paises.length; d++) {
      const o = v.pos[d];
      if (d !== c && o !== ".") { n[d][1]++; if (o === p) n[d][0]++; }
    }
  }
  return R.paises.map((otro, d) => ({ otro, pct: n[d][1] ? (100 * n[d][0]) / n[d][1] : 0, t: n[d][1] })).filter((x) => x.t >= 20);
}

// Cada eurodiputado de la delegación: votaciones, participación y cuántas veces vota como su grupo.
function eurodiputadosDe(R, c) {
  const m = {};
  for (const v of R.votos) {
    for (const x of R.dePais[c][v.anio] || []) {
      const s = v.sentidos[x.pos];
      if (s === "." || s === undefined) continue;
      const e = (m[x.id] ??= { id: x.id, escano: 0, votos: 0, conGrupo: 0, conGrupoN: 0, grupos: new Map() });
      const g = R.grupoDe[`${v.anio}|${v.partidos.charCodeAt(x.pos) - 48}`];
      e.escano++;
      e.grupos.set(g, (e.grupos.get(g) || 0) + 1);
      if (s === "-") continue;
      e.votos++;
      const pg = v.posGrupo[v.partidos.charCodeAt(x.pos)];
      if (pg && !SIN_GRUPO_PE.has(g)) { e.conGrupoN++; if (pg === s) e.conGrupo++; }
    }
  }
  const nombres = Object.fromEntries(q(`SELECT id, nombre FROM miembro WHERE id IN (${marcas(Object.keys(m))})`, Object.keys(m)).map((r) => [r.id, r.nombre]));
  return Object.values(m).map((e) => ({
    ...e, nombre: nombres[e.id] || e.id,
    grupo: [...e.grupos.entries()].sort((x, y) => y[1] - x[1])[0][0], // el grupo en el que más votaciones ha estado
  }));
}

// Voto de la delegación en una votación, por grupo: como el voto por partido de la fila de una votación.
function gruposDelegacion(R, v, c) {
  const g = {};
  for (const x of R.dePais[c][v.anio] || []) {
    const s = LETRAS_PE.indexOf(v.sentidos[x.pos]);
    if (s < 0) continue;
    const codigo = R.grupoDe[`${v.anio}|${v.partidos.charCodeAt(x.pos) - 48}`] || "?";
    (g[codigo] ??= [0, 0, 0, 0])[s]++;
  }
  return Object.entries(g).map(([partido, [si, no, abstencion, no_vota]]) => ({ partido, si, no, abstencion, no_vota, sentido: sentidoPe(si, no, abstencion) }))
    .sort((x, y) => y.si + y.no + y.abstencion - (x.si + x.no + x.abstencion));
}

function pintarPe(qq) {
  const iso3 = paisActual();
  const f = CAT.fuentes[PE];
  const anios = aniosPe();
  if (!f?.votaciones) {
    return el("div", {}, cabeceraPais(iso3, null, "En el Parlamento Europeo"), el("div", { class: "vacio" }, "Todavía no hay votaciones del Parlamento Europeo."));
  }
  if (anios[0] > anios[1]) {
    return el("div", {}, cabeceraPais(iso3, null, "En el Parlamento Europeo"),
      el("div", { class: "vacio" }, `El Parlamento Europeo tiene datos de ${f.anio_min} a ${f.anio_max}: elige esos años.`));
  }
  const R = recuentoPe(anios);
  // Sin país elegido, como con la Unión Europea: todas las delegaciones.
  if (!iso3 || esOrganismo(iso3)) return pintarDelegaciones(R, anios);
  const c = R.idx[iso3];
  if (c === undefined) {
    const otros = eurodiputados(iso3, [f.anio_min, f.anio_max]);
    return el("div", {}, cabeceraPais(iso3, null, "En el Parlamento Europeo"),
      el("div", { class: "card aviso-card" },
        el("h3", {}, `${nombrePais(iso3)} no tiene eurodiputados en ${textoAnios(anios)}`),
        el("p", {}, otros ? `Los tuvo en otros años de los que hay datos (${f.anio_min}–${f.anio_max}): cambia los años en la cabecera.`
          : "Solo los Estados de la Unión Europea eligen eurodiputados."),
        el("p", {}, el("button", { class: "boton", onclick: () => irA("pe", { p: "EUU" }) }, "Ver todas las delegaciones nacionales"))));
  }
  return pintarDelegacion(qq, R, c, iso3, anios);
}

function pintarDelegacion(qq, R, c, iso3, anios) {
  const perfil = perfilDelegacion(R, c);
  const miembros = eurodiputadosDe(R, c);
  const ahora = CAT.delegaciones.find((d) => d.fuente === PE && d.pais === iso3 && d.anio === anios[1])?.miembros;
  const siglas = (g) => partido(PE, g).siglas || g;

  // Por grupo europeo: eurodiputados (por su grupo principal) y cuánto votan con él.
  const porGrupo = {};
  for (const e of miembros) {
    const g = (porGrupo[e.grupo] ??= { grupo: e.grupo, n: 0, votos: 0, escano: 0, conGrupo: 0, conGrupoN: 0 });
    g.n++; g.votos += e.votos; g.escano += e.escano; g.conGrupo += e.conGrupo; g.conGrupoN += e.conGrupoN;
  }
  const grupos = Object.values(porGrupo).sort((x, y) => y.n - x.n || y.escano - x.escano);
  const chipGrupo = (g) => el("span", { class: "chip" }, el("span", { class: "sw", style: `background:${colorPartido(PE, g)}` }), siglas(g));
  const tablaGrupos = el("table", { class: "tabla" },
    el("thead", {}, el("tr", {}, el("th", {}, "Grupo"), el("th", { class: "num" }, "Eurodiputados"), el("th", { class: "num", title: "Votos en el mismo sentido que la mayoría de su grupo" }, "Con su grupo"),
      el("th", { class: "num" }, "Participación"))),
    el("tbody", {}, grupos.map((g) => el("tr", { title: partido(PE, g.grupo).nombre || g.grupo },
      el("td", {}, chipGrupo(g.grupo)), el("td", { class: "num" }, fmt(g.n)),
      el("td", { class: "num" }, g.conGrupoN ? `${pct(g.conGrupo, g.conGrupoN)} %` : "—"), el("td", { class: "num" }, `${pct(g.votos, g.escano)} %`)))));

  const afines = afinidadDelegaciones(R, c).sort((x, y) => y.pct - x.pct);
  const puntos = (xs, color) => puntosH(xs.map((r) => ({ etiqueta: nombrePais(r.otro), valor: r.pct, tip: cuenta(r.t, "votación en común", "votaciones en común"), iso3: r.otro })),
    { color, alClicar: (i) => irA("pe", { p: i.iso3 }, { arriba: true }) });

  const ordenGrupo = Object.fromEntries(grupos.map((g, i) => [g.grupo, i]));
  miembros.sort((x, y) => ordenGrupo[x.grupo] - ordenGrupo[y.grupo] || x.nombre.localeCompare(y.nombre, "es"));
  const tablaMiembros = el("table", { class: "tabla" },
    el("thead", {}, el("tr", {}, el("th", {}, "Eurodiputado"), el("th", {}, "Grupo"), el("th", { class: "num" }, "Votaciones"),
      el("th", { class: "num" }, "Participación"), el("th", { class: "num" }, "Con su grupo"))),
    el("tbody", {}, miembros.map((e) => el("tr", {},
      el("td", {}, e.nombre), el("td", {}, [...e.grupos.keys()].map(chipGrupo)), el("td", { class: "num" }, fmt(e.escano)),
      el("td", { class: "num" }, `${pct(e.votos, e.escano)} %`), el("td", { class: "num" }, e.conGrupoN ? `${pct(e.conGrupo, e.conGrupoN)} %` : "—")))));

  return el("div", {},
    cabeceraPais(iso3, `Voto de sus eurodiputados en las votaciones nominales del pleno · ${textoAnios(anios)}. El partido de cada eurodiputado es su grupo europeo.`, "En el Parlamento Europeo"),
    el("div", { class: "grid g4" },
      stat("Eurodiputados", fmt(miembros.length), ahora && ahora !== miembros.length ? `${fmt(ahora)} en ${anios[1]}; el resto, sustituidos o de la legislatura anterior` : `en ${cuenta(perfil.votaciones, "votación", "votaciones")}`),
      stat("Participación", `${perfil.participacion} %`, "votos (sí, no o abstención) sobre el total de sus escaños en cada votación"),
      stat("Delegación unida", `${perfil.unida} %`, "votaciones en que al menos dos tercios de los suyos votan lo mismo"),
      stat("Con el resultado", `${perfil.conPleno} %`, "votaciones en que lo más votado por la delegación es lo que sale")),
    el("div", { class: "grid g2 arriba", style: "margin-top:16px" },
      el("section", { class: "card" }, el("h3", {}, "Por grupo europeo"),
        el("p", { class: "muted small" }, "Cada eurodiputado cuenta en el grupo en el que más votaciones ha estado. «Con su grupo»: votos en el mismo sentido que la mayoría de su grupo europeo."),
        el("div", { class: "tabla-scroll" }, tablaGrupos)),
      el("section", { class: "card" }, el("h3", {}, `Con qué delegaciones vota ${nombrePais(iso3)}`),
        afines.length ? [el("p", { class: "muted small" }, "Votaciones en que lo más votado por las dos delegaciones coincide (salvo trámites)."),
          el("h4", {}, "Las que más"), puntos(afines.slice(0, 6), "var(--rel-p2)"),
          el("h4", {}, "Las que menos"), puntos(afines.slice(-4).reverse(), "var(--rel-n2)")]
          : el("p", { class: "muted" }, "Pocas votaciones en esos años."))),
    el("section", { class: "card", style: "margin-top:16px" },
      el("details", {}, el("summary", {}, el("b", {}, `Sus ${cuenta(miembros.length, "eurodiputado", "eurodiputados")}`), el("span", { class: "muted small" }, " · participación y voto con su grupo")),
        el("div", { class: "tabla-scroll" }, tablaMiembros))),
    listaDelegacion(qq, R, c, iso3, anios));
}

// Buscador de votaciones con el voto de la delegación.
function listaDelegacion(qq, R, c, iso3, [a, b]) {
  const w = ["v.fuente=?", "v.anio BETWEEN ? AND ?", "v.tipo <> 'procedimiento'"], args = [PE, a, b];
  if (qq.todas !== "1") w.push("v.decisiva=1");
  const temas = lista(qq.tema);
  if (temas.length) { w.push(`fi.tema_principal IN (${marcas(temas)})`); args.push(...temas); }
  if (qq.rel === "1") w.push("fi.relaciones IS NOT NULL AND fi.relaciones <> '[]'");
  for (const palabra of (qq.q || "").split(/\s+/).filter(Boolean)) {
    w.push("(s.titulo LIKE ? OR fi.resumen LIKE ? OR s.codigo LIKE ? OR v.texto LIKE ?)");
    args.push(...Array(4).fill(`%${palabra}%`));
  }
  const filas = q(`SELECT v.*, s.titulo, s.codigo, s.tipo AS tipo_asunto, fi.resumen, fi.tema_principal, fi.relaciones
                   FROM votacion v JOIN asunto s ON s.id=v.asunto_id LEFT JOIN ficha fi ON fi.asunto_id=v.asunto_id
                   WHERE ${w.join(" AND ")} ORDER BY v.fecha DESC, v.numero DESC`, args)
    .map((v) => {
      const r = R.porId[v.id];
      const [si, no, ab, nv] = r ? cuentaDe(r, c) : [0, 0, 0, 0];
      return { ...v, del: { si, no, ab, nv, pos: posicionPe(si, no, ab), sentido: sentidoPe(si, no, ab) } };
    })
    .filter((v) => v.del.si + v.del.no + v.del.ab + v.del.nv > 0
      && (!qq.voto || v.del.pos === qq.voto) && (qq.dividida !== "1" || v.del.sentido === "dividido"));
  const pagina = Math.max(1, +(qq.pagina || 1));
  const trozo = filas.slice((pagina - 1) * TAM_PAGINA, pagina * TAM_PAGINA);
  const cambiar = (x) => irA("pe", { ...x, pagina: "" });
  const nombre = nombrePais(iso3);
  const texto = (d) => unirPartes([d.si ? `${fmt(d.si)} sí` : "", d.no ? `${fmt(d.no)} no` : "", d.ab ? `${fmt(d.ab)} abst.` : ""]) || "nadie votó";
  return el("div", {},
    el("h3", { style: "margin-top:20px" }, `Cómo han votado los eurodiputados de ${nombre}`),
    filaFiltros([
      buscarFiltro("q", qq.q, "Buscar palabras o un código…"),
      multiSelect("tema", CAT.temas.map((x) => [x.codigo, x.nombre]), qq.tema, "Todos los temas", "temas"),
      selectFiltro("voto", [["", "Cualquier voto"], ["S", "La mayoría votó sí"], ["N", "La mayoría votó no"], ["A", "La mayoría se abstuvo"]], qq.voto),
      checkFiltro("dividida", "Delegación dividida", qq.dividida),
      checkFiltro("rel", "Solo con relaciones con otros países", qq.rel),
      checkFiltro("todas", "Incluir enmiendas y votaciones por partes", qq.todas),
    ], cambiar),
    el("div", { class: "lista-cab" }, el("b", {}, cuenta(filas.length, "votación", "votaciones")), leyendaSentidos()),
    trozo.length ? el("div", { class: "lista" }, trozo.map((v) => el("div", { class: "fila", onclick: () => panelVotacion(v.id) },
      el("div", {}, el("div", { class: "fecha" }, fecha(v.fecha)), el("div", { class: "muted small" }, v.codigo || "")),
      el("div", {}, el("div", { class: "titulo" }, recortar(v.titulo, 200)),
        el("div", { class: "detalle" }, unirPartes([v.tipo !== "final" ? TIPOS_VOTACION[v.tipo] : null, v.texto && v.texto !== v.titulo ? recortar(v.texto, 140) : null])),
        limpiarResumen(v.resumen) ? el("div", { class: "resumen" }, limpiarResumen(v.resumen)) : null,
        el("div", { class: "badges" }, v.tema_principal ? el("span", { class: "badge" }, temaNombre(v.tema_principal)) : null,
          el("span", { class: "badge" }, TIPOS_ASUNTO[v.tipo_asunto] || v.tipo_asunto),
          jsonDe(v.relaciones, []).slice(0, 4).map((r) => chipRelacion(r)))),
      el("div", {},
        el("div", { class: `voto-pais ${v.del.sentido === "dividido" ? "abstencion" : v.del.sentido}` }, `${nombre}: ${texto(v.del)}`),
        barraVotos({ a_favor: v.del.si, en_contra: v.del.no, abstenciones: v.del.ab }),
        chipsPartidos(PE, gruposDelegacion(R, R.porId[v.id], c)),
        el("div", { class: "muted small", style: "margin-top:6px" }, badgeResultado(v.resultado), ` Pleno: ${fmt(v.a_favor)} sí, ${fmt(v.en_contra)} no`)))))
      : el("div", { class: "vacio" }, "Ninguna votación con estos filtros."),
    filas.length > TAM_PAGINA ? paginacion(filas.length, pagina, TAM_PAGINA, (p) => irA("pe", { pagina: p })) : null);
}

// Detalle de una votación: el voto de los eurodiputados de cada país (grupos: lo que da votoNominal).
function tablaPaisesPe(grupos) {
  const n = {};
  for (const ms of Object.values(grupos)) {
    for (const m of ms) (n[paisDeMiembro(m.iso3)] ??= { si: 0, no: 0, abstencion: 0, no_vota: 0 })[m.sentido]++;
  }
  const actual = paisActual();
  return el("table", { class: "tabla" },
    el("thead", {}, el("tr", {}, el("th", {}, "País"), el("th", { class: "num" }, "Sí"), el("th", { class: "num" }, "No"),
      el("th", { class: "num" }, "Abst."), el("th", { class: "num" }, "No vota"), el("th", {}, "Posición"))),
    el("tbody", {}, Object.entries(n).sort(([a, x], [b, y]) => (b === actual) - (a === actual) || y.si + y.no + y.abstencion + y.no_vota - (x.si + x.no + x.abstencion + x.no_vota))
      .map(([p, x]) => el("tr", { class: "clic" + (p === actual ? " actual" : ""), title: `Ver cómo votan los eurodiputados de ${nombrePais(p)}`,
        onclick: () => { cerrarPanel(); irA("pe", { p }); } },
      el("td", {}, nombrePais(p)), el("td", { class: "num" }, fmt(x.si)), el("td", { class: "num" }, fmt(x.no)),
      el("td", { class: "num" }, fmt(x.abstencion)), el("td", { class: "num" }, fmt(x.no_vota)),
      el("td", {}, SENTIDO[sentidoPe(x.si, x.no, x.abstencion)][1])))));
}

// Con la Unión Europea elegida: todas las delegaciones, para compararlas.
function pintarDelegaciones(R, anios) {
  // Eurodiputados del último año (en un año de elecciones europeas, los de las dos legislaturas se sumarían).
  const ultimo = Math.max(...CAT.delegaciones.filter((d) => d.fuente === PE && d.anio <= anios[1]).map((d) => d.anio));
  const filas = R.paises.map((p, c) => ({ p, ...perfilDelegacion(R, c),
    n: CAT.delegaciones.find((d) => d.fuente === PE && d.pais === p && d.anio === ultimo)?.miembros || 0 }))
    .sort((x, y) => y.n - x.n || nombrePais(x.p).localeCompare(nombrePais(y.p), "es"));
  return el("div", {},
    cabeceraPais("EUU", `Cómo vota cada delegación nacional en el Parlamento Europeo · ${textoAnios(anios)}. Pulsa un país para ver el voto de sus eurodiputados.`, "En el Parlamento Europeo"),
    el("section", { class: "card" },
      el("div", { class: "tabla-scroll" }, el("table", { class: "tabla" },
        el("thead", {}, el("tr", {}, el("th", {}, "País"), el("th", { class: "num", title: `Eurodiputados que han votado en ${ultimo} (cuenta a los sustitutos)` }, `Eurodiputados (${ultimo})`),
          el("th", { class: "num" }, "Participación"), el("th", { class: "num", title: "Votaciones en que al menos dos tercios de los suyos votan lo mismo" }, "Unida"),
          el("th", { class: "num", title: "Votaciones en que lo más votado por la delegación es lo que sale" }, "Con el resultado"))),
        el("tbody", {}, filas.map((r) => el("tr", { class: "clic", onclick: () => irA("pe", { p: r.p }, { arriba: true }) },
          el("td", {}, nombrePais(r.p)), el("td", { class: "num" }, fmt(r.n)), el("td", { class: "num" }, `${r.participacion} %`),
          el("td", { class: "num" }, `${r.unida} %`), el("td", { class: "num" }, `${r.conPleno} %`)))))),
      el("p", { class: "muted small" }, "Todas las votaciones nominales salvo los trámites, también enmiendas y votaciones por partes. Lo que vota el Parlamento Europeo en conjunto está en Resumen, Votaciones y Partidos (los grupos europeos).")));
}
