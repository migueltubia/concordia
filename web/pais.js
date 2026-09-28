"use strict";

// ------------------------------------------------------------------ vistas de un país
// Resumen, Votaciones y Partidos usan las votaciones de su parlamento (si hay fuente); «En la ONU» existe
// para cualquier Estado miembro. Todo se filtra por el país y los años elegidos en la cabecera.

const fuentesPais = (iso3) => CAT.fuentesDe[iso3] || [];
const recortarAnios = ([a, b], f) => [Math.max(a, f.anio_min || a), Math.min(b, f.anio_max || b)];
const aniosOnu = () => { const [a, b] = aniosActuales(); return [a, Math.min(b, ONU_HASTA)]; };
const nombresOnu = () => nombresFuente("onu", aniosOnu());

function cabeceraPais(iso3, subtitulo) {
  const p = CAT.paises[iso3] || {};
  return el("div", { class: "cab-pais" },
    el("h2", {}, p.nombre || iso3, el("span", { class: "muted small" }, ` · ${[p.subregion, p.region].filter(Boolean).join(", ")}`)),
    subtitulo ? el("p", { class: "sub" }, subtitulo) : null);
}

function sinParlamento(iso3) {
  const info = (typeof DISPONIBILIDAD !== "undefined" && DISPONIBILIDAD[iso3]) || null;
  return el("div", { class: "card aviso-card" },
    el("h3", {}, "No se recogen todavía las votaciones de su parlamento"),
    info ? el("p", {}, `Según el estudio de fuentes: ${info.voto}.${info.fuente !== "—" ? ` ${info.fuente}.` : ""} `,
      /^\d/.test(info.dificultad) ? `Dificultad ${info.dificultad} de 5.` : "Excluido: su parlamento no es competitivo o no publica votos.")
      : el("p", {}, "El estudio de fuentes no encontró datos abiertos de voto de su parlamento, o su parlamento no es competitivo."),
    el("p", { class: "muted small" }, "Sí están su voto en la Asamblea General de la ONU (1946–2023) y lo que otros parlamentos y Estados votan sobre él."),
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

function barrasSaldo(filas, alClicar, { etiqueta = (r) => nombrePais(r.pais) } = {}) {
  if (!filas.length) return el("p", { class: "muted" }, "Nada con estos años.");
  const max = Math.max(...filas.map((r) => r.n));
  return el("div", { class: "barrash" }, filas.flatMap((r) => {
    const t = Math.max(1, r.pos + r.neg + r.neu), w = (100 * r.n) / max;
    return [
      el("div", { class: "bh-label" }, etiqueta(r)),
      conTip(el("div", { class: "bh-pista clic", onclick: () => alClicar(r) },
        el("div", { class: "bh-pila", style: `width:${Math.max(2, w)}%` },
          el("span", { class: "si", style: `flex:${r.pos}` }), el("span", { class: "abs", style: `flex:${r.neu}` }), el("span", { class: "no", style: `flex:${r.neg}` })),
        el("b", {}, fmt(r.n))),
        `${fmt(r.pos)} positivas · ${fmt(r.neg)} negativas · ${fmt(r.neu)} neutras`, etiqueta(r), "Pulsa para ver el detalle"),
    ];
  }));
}
const leyendaSaldo = () => el("div", { class: "legend" }, el("span", {}, el("i", { style: "background:var(--si)" }), "positivas"),
  el("span", {}, el("i", { style: "background:var(--abs)" }), "neutras"), el("span", {}, el("i", { style: "background:var(--no)" }), "negativas"));

function pintarResumen() {
  const iso3 = paisActual();
  const anios = aniosActuales();
  const fs = fuentesPais(iso3);
  const bloques = [];
  if (fs.length) {
    for (const f of fs) {
      const [a, b] = recortarAnios(anios, f);
      const t = q1(`SELECT COUNT(*) AS votaciones, COUNT(DISTINCT asunto_id) AS asuntos,
                     SUM(decisiva=1 AND tipo='final') AS finales, SUM(decisiva=1 AND tipo='final' AND resultado='aprobada') AS aprobadas
                   FROM votacion WHERE fuente=? AND anio BETWEEN ? AND ?`, [f.codigo, a, b]);
      const fichas = q1(`SELECT SUM(fi.origen NOT IN ('reglas','escrutinio:reglas')) AS ia, COUNT(*) AS n FROM ficha fi
                         WHERE fi.asunto_id IN (SELECT asunto_id FROM votacion WHERE fuente=? AND anio BETWEEN ? AND ?)`, [f.codigo, a, b]);
      const porAnio = q("SELECT anio AS x, COUNT(*) AS y FROM votacion WHERE fuente=? AND anio BETWEEN ? AND ? GROUP BY anio ORDER BY anio", [f.codigo, a, b]);
      const temas = q(`SELECT COALESCE(fi.tema_principal, '') AS tema, COUNT(DISTINCT v.asunto_id) AS n FROM votacion v
                       LEFT JOIN ficha fi ON fi.asunto_id=v.asunto_id JOIN asunto s ON s.id=v.asunto_id
                       WHERE v.fuente=? AND v.anio BETWEEN ? AND ? AND v.decisiva=1 AND s.tipo NOT IN ('procedimiento','nombramiento')
                       GROUP BY 1 ORDER BY n DESC`, [f.codigo, a, b]);
      const camaras = Object.values(CAT.camaras).filter((c) => c.fuente === f.codigo).map((c) => c.nombre).join(" y ");
      bloques.push(
        el("section", {}, el("h3", {}, f.nombre),
          el("p", { class: "muted small" }, `${camaras} · ${f.detalle === "nominal" ? "voto de cada legislador" : f.detalle} · datos de ${f.anio_min} a ${f.anio_max} · `,
            enlace(f.web, "fuente"), f.notas ? ` · ${f.notas}` : ""),
          el("div", { class: "grid g4" },
            stat("Votaciones", fmt(t.votaciones), textoAnios([a, b])),
            stat("Asuntos votados", fmt(t.asuntos), "leyes, resoluciones, mociones…"),
            stat("Aprobado en la votación final", `${pct(t.aprobadas, t.finales)} %`, `${fmt(t.aprobadas)} de ${fmt(t.finales)}`),
            stat("Con ficha de la IA", `${pct(fichas.ia, fichas.n)} %`, "el resto, con reglas")),
          el("div", { class: "grid g2", style: "margin-top:16px" },
            el("div", { class: "card" }, el("h3", {}, "Votaciones por año"), columnasAnio(porAnio)),
            el("div", { class: "card" }, el("h3", {}, "Asuntos por tema"), el("p", { class: "muted small" }, "Tema de la ficha (IA, Escrutinio o reglas)."),
              barrasH(temas.slice(0, 12).map((r) => ({ etiqueta: temaNombre(r.tema), valor: r.n, color: "var(--accent)" })),
                { alClicar: (i) => irA("votaciones", { tema: (temas.find((r) => temaNombre(r.tema) === i.etiqueta) || {}).tema || "" }) })))));
    }
  } else {
    bloques.push(sinParlamento(iso3));
  }
  const salen = relacionesDesde(iso3, anios, "ley");
  const entran = relacionesDesde(iso3, anios, "ley", { entrantes: true });
  const onuSobre = relacionesDesde(iso3, anios, "onu", { entrantes: true, limite: 400 });
  const panel = (o, d) => panelArista(o, d, {});
  bloques.push(el("div", { class: "grid g2", style: "margin-top:16px" },
    el("section", { class: "card" }, el("h3", {}, `Lo que el parlamento de ${nombrePais(iso3)} vota sobre otros países`),
      el("p", { class: "muted small" }, "Asuntos aprobados, por país objeto y orientación."), leyendaSaldo(),
      fs.length ? barrasSaldo(salen, (r) => panel(iso3, r.pais)) : el("p", { class: "muted" }, "Sin datos de su parlamento.")),
    el("section", { class: "card" }, el("h3", {}, `Lo que otros parlamentos votan sobre ${nombrePais(iso3)}`),
      el("p", { class: "muted small" }, "Solo de los parlamentos con datos."), leyendaSaldo(),
      barrasSaldo(entran, (r) => panel(r.pais, iso3)))));
  const [ao, bo] = aniosOnu();
  if (ao <= bo) {
    const afines = afinidadCon(iso3, [ao, bo]).sort((a, b) => b.pct - a.pct);
    bloques.push(el("div", { class: "grid g2", style: "margin-top:16px" },
      el("section", { class: "card" }, el("h3", {}, `En la ONU, sobre ${nombrePais(iso3)}`),
        el("p", { class: "muted small" }, `Cómo votan los demás Estados las resoluciones que tratan de ${nombrePais(iso3)} (${textoAnios([ao, bo])}). Positiva: votar en el sentido favorable al país.`),
        leyendaSaldo(),
        el("h4", {}, "Los que más votan a su favor"), barrasSaldo(ordenarSaldo(onuSobre, 1), (r) => panel(r.pais, iso3)),
        el("h4", {}, "Los que más votan en su contra"), barrasSaldo(ordenarSaldo(onuSobre, -1), (r) => panel(r.pais, iso3))),
      el("section", { class: "card" }, el("h3", {}, `Con quién vota ${nombrePais(iso3)} en la ONU`),
        afines.length ? el("div", {},
          el("p", { class: "muted small" }, "Coincidencia en las votaciones finales de la Asamblea General."),
          barrasH([...afines.slice(0, 6), ...afines.slice(-4)].map((r) => ({ etiqueta: nombrePais(r.otro), valor: r.pct, color: "var(--accent)" })),
            { max: 100, formato: (v) => `${Math.round(v)} %` }),
          el("p", {}, el("button", { class: "boton", onclick: () => irA("mundo", { modo: "afinidad", ref: iso3 }) }, "Ver en el mapa")))
          : el("p", { class: "muted" }, "Sin votos en la ONU en esos años."))));
  }
  return el("div", {},
    cabeceraPais(iso3, fs.length ? null : "Sin votaciones de su parlamento: su perfil sale de la ONU y de lo que votan los demás."),
    el("div", { class: "segmentos" },
      el("button", { class: "boton", onclick: () => irA("mundo", { o: iso3, d: "" }) }, `Mapa: desde ${nombrePais(iso3)}`),
      el("button", { class: "boton", onclick: () => irA("mundo", { d: iso3, o: "" }) }, `Mapa: hacia ${nombrePais(iso3)}`),
      el("button", { class: "boton", onclick: () => irA("onu") }, "Su voto en la ONU")),
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

function filaVotacion(v, fuente, alClicar) {
  const rels = jsonDe(v.relaciones, []);
  return el("div", { class: "fila", onclick: alClicar },
    el("div", {}, el("div", { class: "fecha" }, fecha(v.fecha)), el("div", { class: "muted small" }, CAT.camaras[v.camara]?.corto || "")),
    el("div", {},
      el("div", { class: "titulo" }, recortar(v.titulo, 200)),
      el("div", { class: "detalle" }, [v.codigo, v.tipo !== "final" ? TIPOS_VOTACION[v.tipo] : null, v.texto && v.texto !== v.titulo ? recortar(v.texto, 140) : null].filter(Boolean).join(" · ")),
      v.resumen ? el("div", { class: "resumen" }, v.resumen) : null,
      el("div", { class: "badges" },
        v.tema_principal ? el("span", { class: "badge" }, temaNombre(v.tema_principal)) : null,
        el("span", { class: "badge" }, TIPOS_ASUNTO[v.tipo_asunto] || v.tipo_asunto),
        v.importante ? el("span", { class: "badge", title: "Votación que el Departamento de Estado de EEUU considera importante" }, "importante") : null,
        rels.slice(0, 5).map((r) => chipRelacion(r)))),
    el("div", {}, badgeResultado(v.resultado), barraVotos(v), v.grupos ? chipsPartidos(fuente.codigo, v.grupos) : null));
}

function pintarVotaciones(qq) {
  const iso3 = paisActual();
  const fs = fuentesPais(iso3);
  if (!fs.length) {
    return el("div", {}, cabeceraPais(iso3), sinParlamento(iso3),
      el("p", {}, el("button", { class: "boton", onclick: () => irA("onu") }, `Ver cómo vota ${nombrePais(iso3)} en la ONU`)));
  }
  const fuente = fs.find((f) => f.codigo === qq.f) || fs[0];
  const [where, args] = filtrosVotaciones(qq, fuente);
  const pagina = Math.max(1, +(qq.pagina || 1));
  const total = q1(`SELECT COUNT(*) AS n ${BASE_VOT} WHERE ${where}`, args).n;
  const filas = q(`SELECT v.*, s.titulo, s.codigo, s.tipo AS tipo_asunto, fi.resumen, fi.tema_principal, fi.relaciones
                   ${BASE_VOT} WHERE ${where} ORDER BY v.fecha ${qq.orden === "asc" ? "ASC" : "DESC"}, v.numero DESC LIMIT ? OFFSET ?`,
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
    buscarFiltro("q", qq.q, "Buscar en título, resumen, etiquetas…"),
    camaras.length > 1 ? selectFiltro("camara", [["", "Todas las cámaras"], ...camaras.map((c) => [c.codigo, c.nombre])], qq.camara) : null,
    multiSelect("tipo", Object.entries(TIPOS_ASUNTO), qq.tipo, "Todo tipo de asunto", "tipos"),
    multiSelect("tema", CAT.temas.map((t) => [t.codigo, t.nombre]), qq.tema, "Todos los temas", "temas"),
    selectFiltro("resultado", [["", "Cualquier resultado"], ["aprobada", "Aprobadas"], ["rechazada", "Rechazadas"]], qq.resultado),
    selectFiltro("con", [["", "Sobre cualquier país"], ...paisesRel], qq.con),
    checkFiltro("rel", "Solo con relaciones con otros países", qq.rel),
    checkFiltro("todas", "Incluir enmiendas y trámites", qq.todas),
    selectFiltro("orden", [["", "Más recientes"], ["asc", "Más antiguas"]], qq.orden),
  ], cambiar);
  return el("div", {},
    cabeceraPais(iso3, `${fuente.nombre} · ${textoAnios(recortarAnios(aniosActuales(), fuente))}. Por defecto, solo la votación que decide cada asunto (la final); marca «Incluir enmiendas y trámites» para verlas todas.`),
    fs.length > 1 ? segmentos(fs.map((f) => [f.codigo, f.corto]), fuente.codigo, (v) => cambiar({ f: v })) : null,
    filtros,
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
  const ficha = el("div", { class: "ficha" },
    fi.resumen ? el("p", {}, fi.resumen) : el("p", { class: "muted" }, "Sin resumen todavía."),
    el("div", { class: "badges" },
      fi.tema_principal ? el("span", { class: "badge" }, temaNombre(fi.tema_principal)) : null,
      jsonDe(fi.temas_secundarios, []).map((t) => el("span", { class: "badge" }, temaNombre(t))),
      jsonDe(fi.etiquetas, []).map((t) => el("span", { class: "badge ia" }, t))),
    rels.length ? el("div", {}, el("h4", {}, "Relaciones con otros países"), el("div", { class: "chips" }, rels.map((r) => chipRelacion(r))),
      el("div", { class: "rel-motivos" }, rels.filter((r) => r.motivo).map((r) => el("div", { class: "small muted" }, `${nombrePais(r.pais)}: ${r.motivo.replace(/^regla: /, "")}`)))) : null,
    el("div", { class: "procedencia" }, `Ficha: ${origenFicha(fi.origen)} · relaciones: ${origenFicha(fi.relaciones_origen)}. Resumen, tema y relaciones salen del título; lo oficial es el voto.`));
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
      esOnu ? el("a", { href: "#", onclick: (e) => { e.preventDefault(); cerrarPanel(); irA("onu", { p: m.iso3 }); } }, m.nombre) : el("span", {}, m.nombre),
      el("span", { class: `v ${m.sentido}` }, SENTIDO[m.sentido][1])))))) : null;
  abrirPanel(el("div", {},
    el("div", { class: "muted small" }, `${fuente?.nombre || v.fuente} · ${CAT.camaras[v.camara]?.nombre || ""} · ${fecha(v.fecha)}`),
    el("h2", {}, v.titulo),
    el("div", { class: "badges" }, v.codigo ? el("span", { class: "badge" }, v.codigo) : null, el("span", { class: "badge" }, TIPOS_ASUNTO[v.tipo_asunto] || v.tipo_asunto),
      v.autor ? el("span", { class: "badge" }, v.autor) : null, v.url_asunto ? enlace(v.url_asunto, "Texto en la fuente ↗") : null),
    el("section", {}, ficha),
    el("section", {}, el("h3", {}, "Esta votación"),
      el("p", { class: "muted" }, [TIPOS_VOTACION[v.tipo], v.texto].filter(Boolean).join(" · ")),
      el("div", { class: "badges" }, badgeResultado(v.resultado), v.mayoria ? el("span", { class: "badge" }, `mayoría ${v.mayoria}`) : null,
        v.url ? enlace(v.url, "Votación en la fuente ↗") : null),
      el("div", { style: "max-width:420px;margin-top:8px" }, barraVotos(v))),
    tablaGrupos ? el("section", {}, el("h3", {}, esOnu ? "Por región" : "Por partido"), el("div", { class: "tabla-scroll" }, tablaGrupos)) : null,
    otras.length > 1 ? el("section", {}, el("h3", {}, `Todas las votaciones del asunto (${otras.length})`),
      el("div", { class: "tabla-scroll" }, el("table", { class: "tabla" }, el("tbody", {}, otras.map((o) =>
        el("tr", { class: "clic" + (o.id === id ? " actual" : ""), onclick: () => panelVotacion(o.id) },
          el("td", {}, fecha(o.fecha)), el("td", {}, CAT.camaras[o.camara]?.corto || ""), el("td", {}, TIPOS_VOTACION[o.tipo]),
          el("td", {}, recortar(o.texto || "", 90)), el("td", {}, badgeResultado(o.resultado)),
          el("td", { class: "num" }, `${fmt(o.a_favor)}–${fmt(o.en_contra)}`))))))) : null,
    nominalNodo ? el("section", {}, el("h3", {}, esOnu ? "Voto de cada Estado" : "Voto de cada legislador"), nominalNodo) : null));
}

// ------------------------------------------------------------------ Partidos

VISTAS.partidos = {
  titulo: "Partidos",
  datos: () => fuentesPais(paisActual()).flatMap((f) => nombresFuente(f.codigo, aniosActuales())),
  pintar: pintarPartidos,
};

function pintarPartidos(qq) {
  const iso3 = paisActual();
  const fs = fuentesPais(iso3);
  if (!fs.length) return el("div", {}, cabeceraPais(iso3), sinParlamento(iso3));
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
  const RAMPA = ["--seq-100", "--seq-200", "--seq-300", "--seq-400", "--seq-500", "--seq-600", "--seq-700"];
  const celda = (x, y) => {
    if (x === y) return el("td", { class: "self" });
    const r = af[`${x}|${y}`];
    if (!r || r.t < 5) return el("td", { class: "self" }, "·");
    const v = r.c / r.t, i = Math.min(6, Math.floor(v * 7));
    return conTip(el("td", { style: `background:var(${RAMPA[i]});color:${i >= 4 ? "var(--seq-ink-alto)" : "var(--ink)"}` }, `${Math.round(100 * v)}`),
      `${Math.round(100 * v)} %`, `${partido(fuente.codigo, x).siglas} y ${partido(fuente.codigo, y).siglas}`, `Votan igual en ${fmt(r.c)} de ${fmt(r.t)} votaciones`);
  };
  const siglas = (p) => partido(fuente.codigo, p).siglas || p;
  const mapaCalor = partidos.length > 1 ? el("div", { class: "heat" }, el("table", {},
    el("thead", {}, el("tr", {}, el("th", {}), partidos.map((p) => el("th", { class: "rot" }, el("div", {}, siglas(p)))))),
    el("tbody", {}, partidos.map((x) => el("tr", {}, el("th", { style: "text-align:right" }, siglas(x)), partidos.map((y) => celda(x, y))))))) : el("p", { class: "muted" }, "Hace falta más de un partido con votaciones.");
  // Apoyo por tema: % de votaciones finales en que el partido votó sí.
  const temas = q(`SELECT fi.tema_principal AS tema, p.partido, SUM(p.sentido='si') AS si, COUNT(*) AS n FROM voto_partido p
                   JOIN votacion v ON v.id=p.votacion_id JOIN ficha fi ON fi.asunto_id=v.asunto_id
                   WHERE v.fuente=? AND v.anio BETWEEN ? AND ? AND v.decisiva=1 AND p.sentido IN ('si','no','abstencion','dividido')
                     AND fi.tema_principal IS NOT NULL GROUP BY 1, 2`, [fuente.codigo, a, b]);
  const apoyo = {};
  for (const r of temas) apoyo[`${r.tema}|${r.partido}`] = r;
  const temasCon = [...new Set(temas.map((r) => r.tema))].sort((x, y) => temaNombre(x).localeCompare(temaNombre(y), "es"));
  const tablaApoyo = el("div", { class: "heat" }, el("table", {},
    el("thead", {}, el("tr", {}, el("th", {}), partidos.map((p) => el("th", { class: "rot" }, el("div", {}, siglas(p)))))),
    el("tbody", {}, temasCon.map((t) => el("tr", {}, el("th", { style: "text-align:right;white-space:nowrap" }, temaNombre(t)), partidos.map((p) => {
      const r = apoyo[`${t}|${p}`];
      if (!r || r.n < 3) return el("td", { class: "self" }, "·");
      const v = r.si / r.n, i = Math.min(6, Math.floor(v * 7));
      return conTip(el("td", { style: `background:var(${RAMPA[i]});color:${i >= 4 ? "var(--seq-ink-alto)" : "var(--ink)"}` }, `${Math.round(100 * v)}`),
        `${Math.round(100 * v)} % a favor`, `${siglas(p)} · ${temaNombre(t)}`, `${fmt(r.si)} de ${fmt(r.n)} votaciones finales`);
    }))))));
  return el("div", {},
    cabeceraPais(iso3, `${fuente.nombre} · ${textoAnios([a, b])}.`),
    fs.length > 1 ? segmentos(fs.map((f) => [f.codigo, f.corto]), fuente.codigo, (v) => irA("partidos", { f: v })) : null,
    el("section", { class: "card" }, el("h3", {}, "Con quién vota cada partido"),
      el("p", { class: "muted small" }, "Porcentaje de votaciones (salvo trámites) en que dos partidos adoptan la misma posición: la de al menos dos tercios de sus miembros."),
      filaFiltros([selectFiltro("tema", [["", "Todos los temas"], ...CAT.temas.map((t) => [t.codigo, t.nombre])], tema)], (c) => irA("partidos", c)),
      mapaCalor),
    el("section", { class: "card", style: "margin-top:16px" }, el("h3", {}, "A favor, por tema"),
      el("p", { class: "muted small" }, "Porcentaje de votaciones finales de cada tema en que el partido votó sí."), tablaApoyo));
}

// ------------------------------------------------------------------ En la ONU

VISTAS.onu = {
  titulo: "En la ONU",
  datos: () => [...nombresOnu(), ...nombresMundo(aniosOnu())],
  pintar: pintarOnu,
};

function pintarOnu(qq) {
  const iso3 = paisActual();
  const [a, b] = aniosOnu();
  const p = CAT.paises[iso3] || {};
  if (a > b || !p.onu_desde) {
    return el("div", {}, cabeceraPais(iso3), el("div", { class: "vacio" },
      !p.onu_desde ? `${nombrePais(iso3)} no tiene votos registrados en la Asamblea General.` : `La ONU tiene datos hasta ${ONU_HASTA}: elige años anteriores.`));
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
  const comparar = lista(qq.cmp).length ? lista(qq.cmp) : ["USA", "CHN", "RUS", "ESP"].filter((x) => x !== iso3).slice(0, 3);
  const colores = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"];
  const series = comparar.map((otro, i) => ({
    nombre: nombrePais(otro), color: colores[i % colores.length],
    puntos: q(`SELECT anio AS x, 100.0 * SUM(suma) / SUM(total) AS y FROM afinidad_onu WHERE ((a=?1 AND b=?2) OR (a=?2 AND b=?1))
               AND anio BETWEEN ?3 AND ?4 GROUP BY anio`, [iso3, otro, a, b]),
  })).filter((s) => s.puntos.length);
  const LETRA = { S: ["si", "Sí"], N: ["no", "No"], A: ["abstencion", "Abstención"], "-": ["no_vota", "No vota"] };
  const cambiar = (c) => irA("onu", { ...c, pagina: "" });
  const opPaises = Object.values(CAT.paises).filter((x) => x.onu_desde).sort((x, y) => x.nombre.localeCompare(y.nombre, "es")).map((x) => [x.iso3, x.nombre]);
  return el("div", {},
    cabeceraPais(iso3, `Voto de ${nombrePais(iso3)} en la Asamblea General de la ONU · ${textoAnios([a, b])}${b < aniosActuales()[1] ? ` (los datos llegan a septiembre de ${ONU_HASTA})` : ""}.`),
    el("div", { class: "grid g4" },
      stat("Votaciones", fmt(t.n), qq.todas === "1" ? "todas" : "votaciones finales de resoluciones"),
      stat("Sí", `${pct(t.si, t.n)} %`, fmt(t.si)), stat("No", `${pct(t.no, t.n)} %`, fmt(t.no)),
      stat("Abstención", `${pct(t.abst, t.n)} %`, `${fmt(t.aus)} ausencias`)),
    el("div", { class: "grid g2", style: "margin-top:16px" },
      el("section", { class: "card" }, el("h3", {}, "Más afines"),
        barrasH(afines.slice(0, 10).map((r) => ({ etiqueta: nombrePais(r.otro), valor: r.pct, color: "var(--accent)", tip: `${fmt(r.t)} votos` })),
          { max: 100, formato: (v) => `${Math.round(v)} %` })),
      el("section", { class: "card" }, el("h3", {}, "Menos afines"),
        barrasH(afines.slice(-10).reverse().map((r) => ({ etiqueta: nombrePais(r.otro), valor: r.pct, color: "var(--accent)", tip: `${fmt(r.t)} votos` })),
          { max: 100, formato: (v) => `${Math.round(v)} %` }))),
    el("section", { class: "card", style: "margin-top:16px" }, el("h3", {}, "Coincidencia por año"),
      filaFiltros([multiSelect("cmp", opPaises, comparar.join(","), "Comparar con…", "países", { buscar: true })], cambiar),
      lineasAnio(series)),
    el("h3", { style: "margin-top:20px" }, "Sus votos"),
    filaFiltros([
      buscarFiltro("q", qq.q, "Buscar resolución…"),
      multiSelect("tema", CAT.temas.map((x) => [x.codigo, x.nombre]), qq.tema, "Todos los temas", "temas"),
      selectFiltro("voto", [["", "Cualquier voto"], ["S", "Votó sí"], ["N", "Votó no"], ["A", "Se abstuvo"], ["-", "No votó"]], qq.voto),
      checkFiltro("imp", "Solo votaciones importantes (EEUU)", qq.imp),
      checkFiltro("todas", "Incluir enmiendas y párrafos", qq.todas),
    ], cambiar),
    filas.length ? el("div", { class: "lista" }, filas.map((v) => {
      const [c, txt] = LETRA[v.voto] || LETRA["-"];
      return el("div", { class: "fila", onclick: () => panelVotacion(v.id) },
        el("div", {}, el("div", { class: "fecha" }, fecha(v.fecha)), el("div", { class: "muted small" }, v.codigo || "")),
        el("div", {}, el("div", { class: "titulo" }, recortar(v.titulo, 200)),
          v.resumen ? el("div", { class: "resumen" }, v.resumen) : null,
          el("div", { class: "badges" }, v.tema_principal ? el("span", { class: "badge" }, temaNombre(v.tema_principal)) : null,
            v.tipo !== "final" ? el("span", { class: "badge" }, TIPOS_VOTACION[v.tipo]) : null,
            jsonDe(v.relaciones, []).slice(0, 4).map((r) => chipRelacion(r)))),
        el("div", {}, el("div", { class: `voto-pais ${c}` }, `${nombrePais(iso3)}: ${txt}`), barraVotos(v)));
    })) : el("div", { class: "vacio" }, "Ninguna votación con estos filtros."),
    t.n > TAM_PAGINA ? paginacion(t.n, pagina, TAM_PAGINA, (p) => irA("onu", { pagina: p })) : null);
}
