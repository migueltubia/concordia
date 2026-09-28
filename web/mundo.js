"use strict";

// ------------------------------------------------------------------ Mundo: mapa de relaciones entre países
// Dos modos:
// - «Orientación»: flechas origen -> destino por lo que el parlamento del país de origen vota sobre el de
//   destino (leyes, resoluciones, tratados) y por cómo vota el país de origen en la ONU las resoluciones
//   sobre el de destino. El color es el saldo: azul si casi todo es positivo, rojo si casi todo es negativo,
//   gris si está repartido o es neutro. El grosor, cuántos asuntos o votos hay detrás.
// - «Afinidad en la ONU»: cuánto coincide el voto de un país con el de cada uno de los demás en la Asamblea
//   General (coropletas), con flechas hacia los más y los menos afines.
// En los dos, una línea de tiempo permite ver el periodo entero, año a año o acumulado, y reproducirlo.

const CLASES_SALDO = [
  [0.6, "p2", "Casi todo positivo"], [0.2, "p1", "Más positivo"], [-0.2, "n0", "Repartido o neutro"],
  [-0.6, "n1", "Más negativo"], [-Infinity, "n2", "Casi todo negativo"],
];
const claseSaldo = (s) => CLASES_SALDO.find(([u]) => s >= u)[1];
const saldoDe = (e) => (e.pos - e.neg) / Math.max(1, e.pos + e.neg + e.neu);
const ONU_HASTA = 2023;
const CENTRO_FIJO = 10; // meridiano central del mapa «fijo»: América a la izquierda y Asia a la derecha

VISTAS.mundo = {
  titulo: "Mapa de relaciones",
  datos: () => nombresMundo(aniosActuales()),
  pintar: pintarMundo,
};

function filtrosRelacion(qq, [desde, hasta] = aniosActuales()) {
  const w = ["r.anio BETWEEN ? AND ?"], a = [desde, hasta];
  if (qq.via) { w.push("r.via=?"); a.push(qq.via); }
  if (qq.todo !== "1") w.push("(r.via='onu' OR r.aprobado=1)");
  if (qq.ori === "pos") w.push("r.orientacion>0");
  if (qq.ori === "neg") w.push("r.orientacion<0");
  if (qq.ori === "neu") w.push("r.orientacion=0");
  const temas = lista(qq.tema);
  if (temas.length) { w.push(`r.tema IN (${marcas(temas)})`); a.push(...temas); }
  const tipos = lista(qq.tipo);
  if (tipos.length) { w.push(`r.tipo IN (${marcas(tipos)})`); a.push(...tipos); }
  const o = lista(qq.o), d = lista(qq.d);
  if (o.length) { w.push(`r.origen IN (${marcas(o)})`); a.push(...o); }
  if (d.length) { w.push(`r.destino IN (${marcas(d)})`); a.push(...d); }
  return [w.join(" AND "), a];
}

function opcionesPaises() {
  return Object.values(CAT.paises).filter((p) => p.onu_desde || CAT.fuentesDe[p.iso3] || p.lat != null)
    .sort((a, b) => a.nombre.localeCompare(b.nombre, "es")).map((p) => [p.iso3, p.nombre]);
}

// Longitud media (circular) de unos países: el mapa se centra ahí para que las flechas no den la vuelta
// al mundo por el lado equivocado (EEUU -> Japón por el Pacífico, no por Europa).
function centroDe(isos) {
  const pts = isos.map(puntoPais).filter(Boolean);
  if (!pts.length) return null;
  const rad = Math.PI / 180;
  const x = pts.reduce((s, [lon]) => s + Math.cos(lon * rad), 0), y = pts.reduce((s, [lon]) => s + Math.sin(lon * rad), 0);
  return Math.atan2(y, x) / rad;
}

let RELOJ = null; // reproducción de la línea de tiempo (se para al cambiar de vista)
function pararReloj() { if (RELOJ) { clearInterval(RELOJ); RELOJ = null; } }

const COMO_AMPLIAR = () => (esMovil() ? "Pellizca para ampliar." : "Amplía con Ctrl + rueda, doble clic o los botones +/−; arrastra para moverte.");

// Preguntas para empezar: atajos a las vistas que las responden, con el país elegido en la cabecera.
function preguntasInicio() {
  const iso3 = paisActual(), nombre = nombrePais(iso3);
  const cerrar = () => { try { localStorage.setItem("concordia.preguntas", "no"); } catch { /* sin almacenamiento */ } caja.remove(); };
  const otro = el("select", { class: "pregunta-pais", "aria-label": "Otro país" },
    el("option", { value: "" }, "elige un país…"),
    opcionesPaises().filter(([i]) => i !== iso3).map(([i, t]) => el("option", { value: i }, t)));
  otro.addEventListener("change", () => { if (otro.value) irA("mundo", { o: iso3, d: otro.value, modo: "" }, { arriba: true }); });
  const boton = (texto, accion) => el("button", { type: "button", class: "pregunta", onclick: accion }, texto);
  const caja = el("section", { class: "preguntas" },
    el("div", { class: "preguntas-cab" }, el("b", {}, "Empieza por una pregunta"),
      el("button", { type: "button", class: "boton-cerrar", title: "No volver a mostrar", "aria-label": "Cerrar", onclick: cerrar }, "✕")),
    el("div", { class: "preguntas-lista" },
      el("div", { class: "pregunta pregunta-compuesta" }, `¿Qué ha votado ${nombre} sobre `, otro, "?"),
      boton(`¿Qué votan otros países sobre ${nombre}?`, () => irA("mundo", { d: iso3, o: "", modo: "" }, { arriba: true })),
      boton(`¿Con qué países vota igual ${nombre} en la ONU?`, () => irA("mundo", { modo: "afinidad", ref: iso3 }, { arriba: true })),
      CAT.fuentesDe[iso3] ? boton(`¿Qué ha votado cada partido en el parlamento de ${nombre}?`, () => irA("votaciones", {})) : null,
      boton("Cambiar de país", abrirSelectorPais)));
  return caja;
}
const mostrarPreguntas = () => { try { return localStorage.getItem("concordia.preguntas") !== "no"; } catch { return true; } };

async function pintarMundo(qq) {
  pararReloj();
  const modo = qq.modo === "afinidad" ? "afinidad" : "orientacion";
  const cab = el("div", {},
    el("h2", {}, modo === "orientacion" ? "Relaciones entre países" : "Afinidad en la ONU"),
    el("p", { class: "sub" }, modo === "orientacion"
      ? `Qué vota cada país sobre los demás: lo que aprueba su parlamento (sanciones, tratados, ayuda, condenas…) y cómo vota en la ONU las resoluciones sobre otros Estados. Cada flecha va del país que vota al país del que trata; pulsa una para ver qué hay detrás. ${COMO_AMPLIAR()} `
      : `Cuánto coincide el voto de un país con el de cada uno de los demás en la Asamblea General de la ONU: azul, mucha coincidencia; rojo, poca. Pulsa un país para compararlo con todos. ${COMO_AMPLIAR()} `,
    enlaceAyuda(modo === "orientacion" ? "mapa" : "glosario", "Cómo se lee")),
    segmentos([["orientacion", "Qué vota cada país sobre otros"], ["afinidad", "Con quién vota igual en la ONU"]], modo,
      (v) => irA("mundo", { modo: v === "orientacion" ? "" : v, tiempo: "", t: "" })));
  // Sin nada elegido todavía (la portada), se ofrecen preguntas para empezar.
  const sinElegir = !["o", "d", "via", "ori", "tema", "tipo", "modo", "ref", "tiempo", "clic"].some((k) => qq[k] !== undefined);
  if (sinElegir && mostrarPreguntas()) cab.append(preguntasInicio());
  if (!nombresMundo(aniosActuales()).length) {
    return el("div", {}, cab, el("div", { class: "vacio" }, `No hay relaciones en ${textoAnios(aniosActuales())}.`));
  }
  return modo === "afinidad" ? pintarAfinidad(qq, cab) : pintarOrientacion(qq, cab);
}

// Guarda en la URL el fotograma de la línea de tiempo sin volver a pintar la vista.
function recordarFotograma(tiempo, t) {
  history.replaceState(null, "", hashDe("mundo", { ...leerRuta().q, tiempo, t: tiempo ? t : "" }));
}

// ------------------------------------------------------------------ línea de tiempo
// barras: {año: {pos, neg, neu}} (apiladas) o {año: {valor}} (una serie). alCambiar({modo, anio}).
// sinBarras: solo el deslizador (en la afinidad, las medias de cada año son casi iguales y no dicen nada).
function lineaTiempo({ desde, hasta, modo, anio, barras, alCambiar, modos, etiquetaBarra, sinBarras = false }) {
  const estado = { modo, anio: Math.min(hasta, Math.max(desde, anio || hasta)) };
  const n = hasta - desde + 1;
  const ancho = 1000, alto = 44, margen = 9;
  const x = (y) => margen + ((ancho - 2 * margen) * (y - desde + 0.5)) / n;
  const bw = Math.max(2, (ancho - 2 * margen) / n - 2);
  const total = (b) => (b ? (b.valor ?? (b.pos || 0) + (b.neg || 0) + (b.neu || 0)) : 0);
  const max = Math.max(1, ...Object.values(barras).map(total));
  const svg = svgEl("svg", { viewBox: `0 0 ${ancho} ${alto}`, preserveAspectRatio: "none", class: "lt-hist" });
  const grupos = {};
  for (let y = desde; y <= hasta; y++) {
    const b = barras[y];
    const g = svgEl("g", { class: "lt-barra" });
    let base = alto;
    const tramo = (v, clase) => {
      if (!v) return;
      const h = (alto - 4) * v / max;
      g.append(svgEl("rect", { class: clase, x: x(y) - bw / 2, y: base - h, width: bw, height: Math.max(0.5, h) }));
      base -= h;
    };
    if (b && b.valor !== undefined) tramo(b.valor, "lt-valor");
    else if (b) { tramo(b.pos, "lt-pos"); tramo(b.neu, "lt-neu"); tramo(b.neg, "lt-neg"); }
    g.append(svgEl("rect", { class: "hit", x: x(y) - (ancho - 2 * margen) / n / 2, y: 0, width: (ancho - 2 * margen) / n, height: alto }));
    g.addEventListener("pointermove", (e) => tip(e, y === ANIO_ACTUAL ? `${y} (año en curso)` : String(y), b ? etiquetaBarra(b) : "Sin datos", "Pulsa para ver ese año"));
    g.addEventListener("pointerleave", tipOff);
    g.addEventListener("click", () => { detener(); fijar(y, estado.modo || "anio"); });
    grupos[y] = g;
    svg.append(g);
  }
  const deslizador = el("input", { type: "range", min: desde, max: hasta, step: 1, value: estado.anio, class: "lt-rango", "aria-label": "Año" });
  const rotulo = el("div", { class: "lt-anio" });
  const boton = el("button", { type: "button", class: "boton lt-play", title: "Reproducir año a año", "aria-label": "Reproducir" }, "▶");
  const modosNodo = el("div", { class: "segmentos lt-modos" });
  const pintarModos = () => modosNodo.replaceChildren(...modos.map(([v, t]) =>
    el("button", { type: "button", class: "boton" + (estado.modo === v ? " activo" : ""), "aria-pressed": String(estado.modo === v),
      onclick: () => { detener(); fijar(estado.anio, v); } }, t)));
  const pintar = () => {
    deslizador.value = estado.anio;
    rotulo.textContent = !estado.modo ? textoAnios([desde, hasta]) : estado.modo === "acum" ? `${desde}–${estado.anio}` : String(estado.anio);
    for (const [y, g] of Object.entries(grupos)) {
      const dentro = !estado.modo || (estado.modo === "acum" ? +y <= estado.anio : +y === estado.anio);
      g.classList.toggle("fuera", !dentro);
    }
    deslizador.disabled = false;
    nodo.classList.toggle("sin-tiempo", !estado.modo);
    pintarModos();
  };
  let pendiente = null;
  const fijar = (anio, modo = estado.modo) => {
    estado.anio = anio;
    estado.modo = modo;
    pintar();
    cancelAnimationFrame(pendiente);
    pendiente = requestAnimationFrame(() => alCambiar({ ...estado }));
  };
  const detener = () => { pararReloj(); boton.textContent = "▶"; boton.setAttribute("aria-label", "Reproducir"); };
  deslizador.addEventListener("input", () => { detener(); fijar(+deslizador.value, estado.modo || "anio"); });
  deslizador.addEventListener("change", () => recordarFotograma(estado.modo, estado.anio));
  boton.addEventListener("click", () => {
    if (RELOJ) { detener(); recordarFotograma(estado.modo, estado.anio); return; }
    const modoPlay = estado.modo || "anio";
    fijar(estado.anio >= hasta || !estado.modo ? desde : estado.anio + 1, modoPlay);
    boton.textContent = "❚❚";
    boton.setAttribute("aria-label", "Pausa");
    RELOJ = setInterval(() => {
      if (!document.body.contains(nodo)) return pararReloj();
      if (estado.anio >= hasta) { detener(); recordarFotograma(estado.modo, estado.anio); return; }
      fijar(estado.anio + 1);
    }, 1100);
  });
  // Un rótulo bajo cada barra (o cada pocos años si hay muchos), alineado con ella.
  const cada = n <= 14 ? 1 : n <= 30 ? 5 : 10;
  const escala = el("div", { class: "lt-escala", style: `grid-template-columns:repeat(${n}, minmax(0, 1fr))` });
  for (let y = desde; y <= hasta; y++) {
    const ver = y === desde || y === hasta || (y % cada === 0 && y - desde >= cada / 2 && hasta - y >= cada / 2);
    escala.append(el("span", {}, ver ? String(y) : ""));
  }
  const nodo = el("div", { class: "linea-tiempo" + (sinBarras ? " sin-barras" : "") },
    el("div", { class: "lt-cab" }, modosNodo, el("div", { class: "lt-control" }, boton, rotulo)),
    el("div", { class: "lt-pista" }, sinBarras ? null : svg, deslizador, escala));
  pintar();
  return nodo;
}

// ------------------------------------------------------------------ modo orientación

function pintarOrientacion(qq0, cab) {
  const [desde, hasta] = aniosActuales();
  // Sin nada en la URL, el origen es el país elegido; «todos» (o vaciar el selector) quita el filtro.
  const qq = { ...qq0, o: qq0.o === undefined && qq0.d === undefined ? paisActual() : qq0.o === "todos" ? "" : qq0.o || "" };
  const cambiar = (c) => irA("mundo", { ...c, ...(c.o === "" ? { o: "todos" } : {}) });
  const paisesOp = opcionesPaises();
  const filtros = filaFiltros([
    multiSelect("o", paisesOp, qq.o, "Origen: todos", "países", { buscar: true }),
    multiSelect("d", paisesOp, qq.d, "Destino: todos", "países", { buscar: true }),
    selectFiltro("via", [["", "Leyes y ONU"], ["ley", "Solo leyes nacionales"], ["onu", "Solo votos en la ONU"]], qq.via),
    selectFiltro("ori", [["", "Toda orientación"], ["pos", "Solo positivas"], ["neg", "Solo negativas"], ["neu", "Solo neutras"]], qq.ori),
    multiSelect("tema", CAT.temas.map((t) => [t.codigo, t.nombre]), qq.tema, "Todos los temas", "temas"),
    multiSelect("tipo", Object.entries(CAT.tiposRel), qq.tipo, "Todo tipo de relación", "tipos"),
    selectFiltro("n", [["30", "30 flechas"], ["60", "60 flechas"], ["120", "120 flechas"], ["250", "250 flechas"]], qq.n || "60"),
    checkFiltro("todo", "Incluir leyes rechazadas", qq.todo),
    checkFiltro("centro", "Mapa fijo (sin centrar en el origen)", qq.centro),
  ], (c) => cambiar(c));

  // Todo el periodo, por par de países y año: los fotogramas se agregan en el navegador.
  const [w, a] = filtrosRelacion(qq);
  const filas = q(`SELECT r.origen, r.destino, r.anio, SUM(r.orientacion>0) AS pos, SUM(r.orientacion<0) AS neg,
                     SUM(r.orientacion=0) AS neu, COUNT(*) AS n, SUM(r.via='ley') AS leyes, SUM(r.via='onu') AS onu
                   FROM relacion r WHERE ${w} GROUP BY 1, 2, 3`, a);
  const porAnio = {};
  for (const f of filas) {
    const b = (porAnio[f.anio] = porAnio[f.anio] || { pos: 0, neg: 0, neu: 0 });
    b.pos += f.pos; b.neg += f.neg; b.neu += f.neu;
  }
  const agregar = (dentro) => {
    const m = new Map();
    for (const f of filas) {
      if (!dentro(f.anio)) continue;
      const k = f.origen + ">" + f.destino;
      const e = m.get(k) || { origen: f.origen, destino: f.destino, pos: 0, neg: 0, neu: 0, n: 0, leyes: 0, onu: 0 };
      e.pos += f.pos; e.neg += f.neg; e.neu += f.neu; e.n += f.n; e.leyes += f.leyes; e.onu += f.onu;
      m.set(k, e);
    }
    return [...m.values()].sort((x, y) => y.n - x.n);
  };
  const total = agregar(() => true);
  // Grosor comparable entre fotogramas: año a año, contra el par con más relaciones en un solo año.
  const maxAnio = Math.max(1, ...filas.map((f) => f.n));
  const maxTotal = Math.max(1, ...total.map((e) => e.n));

  const o = new Set(lista(qq.o)), d = new Set(lista(qq.d));
  const clic = qq.clic || "o";
  const lado = o.size && !d.size ? "destino" : d.size && !o.size ? "origen" : null;
  const max = Math.max(1, +(qq.n || 60));
  const libres = !o.size && !d.size;
  const tope = libres ? Math.max(4, Math.ceil(max / 10)) : Infinity;

  const fotograma = ({ modo, anio }) => {
    const todas = !modo ? total : agregar(modo === "acum" ? (y) => y <= anio : (y) => y === anio);
    // Sin origen ni destino, un mismo destino (Palestina, en casi todos los años) acapararía todas las flechas:
    // cada país recibe o envía como mucho una décima parte.
    const cuenta = {}, visibles = [];
    for (const e of todas) {
      if (visibles.length >= max) break;
      if (!puntoPais(e.origen) || !puntoPais(e.destino)) continue;
      const kd = "d" + e.destino, ko = "o" + e.origen;
      if ((cuenta[kd] || 0) >= tope || (cuenta[ko] || 0) >= tope) continue;
      cuenta[kd] = (cuenta[kd] || 0) + 1;
      cuenta[ko] = (cuenta[ko] || 0) + 1;
      visibles.push(e);
    }
    const porPais = {}, saldoPais = {};
    for (const e of todas) {
      (porPais[e.origen] = porPais[e.origen] || { sale: 0, entra: 0 }).sale += e.n;
      (porPais[e.destino] = porPais[e.destino] || { sale: 0, entra: 0 }).entra += e.n;
      if (lado) {
        const s = (saldoPais[e[lado]] = saldoPais[e[lado]] || { pos: 0, neg: 0, neu: 0, n: 0 });
        s.pos += e.pos; s.neg += e.neg; s.neu += e.neu; s.n += e.n;
      }
    }
    return { modo, anio, todas, visibles, porPais, saldoPais, anios: !modo ? [desde, hasta] : modo === "acum" ? [desde, anio] : [anio, anio] };
  };

  const opcionesMapa = (fr) => {
    // Rótulos: los países elegidos y, después, los extremos de las flechas más gruesas.
    const etiquetas = [...o, ...d];
    for (const e of fr.visibles) etiquetas.push(lado === "origen" ? e.origen : lado === "destino" ? e.destino : e.destino, e.origen);
    return {
      rellenar: (iso3) => (o.has(iso3) ? "var(--mapa-origen)" : d.has(iso3) ? "var(--mapa-destino)"
        : fr.saldoPais[iso3] ? `var(--relf-${claseSaldo(saldoDe(fr.saldoPais[iso3]))})` : null),
      tipPais: (iso3) => {
        const c = fr.porPais[iso3], s = fr.saldoPais[iso3];
        const accion = clic === "p" ? "Pulsa para ver el país"
          : `Pulsa para ${o.has(iso3) || d.has(iso3) ? "quitarlo" : "añadirlo"} como ${clic === "d" ? "destino" : "origen"}`;
        if (s) {
          const [x, y] = lado === "destino" ? [[...o].map(nombrePais).join(" + "), nombrePais(iso3)] : [nombrePais(iso3), [...d].map(nombrePais).join(" + ")];
          return [nombrePais(iso3), `${x} → ${y} (${textoAnios(fr.anios)}): ${textoSaldo(s.pos, s.neg, s.neu)}`, accion];
        }
        return [nombrePais(iso3), c ? `${fmt(c.sale)} como origen · ${fmt(c.entra)} como destino (${textoAnios(fr.anios)})` : "Sin relaciones con estos filtros", accion];
      },
      flechas: fr.visibles.map((e) => ({
        desde: e.origen, hasta: e.destino, n: e.n, clase: claseSaldo(saldoDe(e)),
        tip: () => [`${nombrePais(e.origen)} → ${nombrePais(e.destino)}`,
          `${textoAnios(fr.anios)}: ${textoSaldo(e.pos, e.neg, e.neu)}`,
          unirPartes([e.leyes ? `Parlamento: ${cuenta(e.leyes, "asunto", "asuntos")}` : "", e.onu ? `ONU: ${cuenta(e.onu, "voto", "votos")}` : "", "pulsa para ver el detalle"])],
        alClicar: () => panelArista(e.origen, e.destino, qq, fr.anios),
      })),
      maxN: fr.modo === "anio" ? maxAnio : maxTotal,
      origenes: o,
      etiquetas,
    };
  };

  const alClicarPais = (iso3) => {
    if (clic === "p") return irA("resumen", { p: iso3, a: leerRuta().q.a });
    const clave = clic === "d" ? "d" : "o";
    const set = new Set(lista(qq[clave]));
    set.has(iso3) ? set.delete(iso3) : set.add(iso3);
    cambiar({ [clave]: [...set].join(",") });
  };
  const anioInicial = Math.min(hasta, Math.max(desde, +qq.t || hasta));
  let fr = fotograma({ modo: qq.tiempo === "anio" || qq.tiempo === "acum" ? qq.tiempo : "", anio: anioInicial });
  const centro = qq.centro === "1" ? CENTRO_FIJO : centroDe([...o]) ?? centroDe([...d]) ?? CENTRO_FIJO;
  // Con origen y destino elegidos, el mapa se encuadra en ellos en vez de enseñar el mundo casi vacío.
  const encuadre = o.size && d.size ? [...o, ...d] : null;
  const mapa = crearMapa({ centro, alClicarPais, encuadre, ...opcionesMapa(fr) });

  const resumenNodo = el("p", { class: "muted small" });
  const tablaNodo = el("div");
  const pintarTexto = () => {
    const n = fr.todas.reduce((s, e) => s + e.n, 0);
    const dibujadas = fr.visibles.length === fr.todas.length ? "se dibujan todas"
      : `se ${fr.visibles.length === 1 ? "dibuja la" : "dibujan las"} ${fmt(fr.visibles.length)} con más asuntos o votos${libres ? `, como mucho ${tope} por país para que se vean más` : ""}; la tabla de abajo las tiene todas`;
    resumenNodo.textContent = `${textoAnios(fr.anios)}: ${cuenta(fr.todas.length, "par de países", "pares de países")} y ${cuenta(n, "relación", "relaciones")} con estos filtros; ${dibujadas}.`;
    tablaNodo.replaceChildren(tablaAristas(fr.todas.slice(0, 200), qq, fr.anios, { conOrigen: o.size !== 1, conDestino: d.size !== 1 || o.size === 1 }));
  };
  pintarTexto();
  const tiempo = lineaTiempo({
    desde, hasta, modo: fr.modo, anio: anioInicial, barras: porAnio,
    modos: [["", "Todo el periodo"], ["anio", "Año a año"], ["acum", "Acumulado"]],
    etiquetaBarra: (b) => textoSaldo(b.pos, b.neg, b.neu),
    alCambiar: (estado) => { fr = fotograma(estado); mapa.actualizar(opcionesMapa(fr)); pintarTexto(); },
  });

  const avisoOnu = hasta > ONU_HASTA && qq.via !== "ley" ? avisoCerrable("onu",
    `La ONU solo tiene datos hasta septiembre de ${ONU_HASTA}: después, las flechas son solo de leyes nacionales. `, enlaceAyuda("fuentes", "Por qué")) : null;
  // Un parlamento con datos pero sin relaciones por ley en esos años (Polonia: títulos en polaco sin ficha de la IA).
  const sinFiltros = !qq.via && !qq.ori && !qq.tema && !qq.tipo;
  const sinLeyes = sinFiltros ? [...o].filter((i) => CAT.fuentesDe[i] && !filas.some((f) => f.origen === i && f.leyes)) : [];
  const avisoLeyes = sinLeyes.length ? el("p", { class: "aviso-lectura" },
    `${sinLeyes.map(nombrePais).join(" y ")}: su parlamento todavía no tiene relaciones por ley con otros países en ${textoAnios([desde, hasta])}${sinLeyes.includes("POL") ? " (sus títulos están en polaco y aún no tienen ficha de la IA)" : ""}. Las flechas que se ven son sus votos en la ONU.`) : null;
  const leyenda = el("div", { class: "legend leyenda-mapa" },
    el("span", { class: "leyenda-titulo" }, "Color de la flecha:"),
    CLASES_SALDO.map(([, c, t]) => el("span", {}, el("i", { class: `fl-${c}` }), t)),
    el("span", { class: "leyenda-titulo" }, "Grosor:"), el("span", {}, "cuántos asuntos o votos hay detrás"),
    el("span", { class: "leyenda-titulo" }, "Países:"),
    el("span", {}, el("i", { style: "background:var(--mapa-origen)" }), "origen elegido"),
    el("span", {}, el("i", { style: "background:var(--mapa-destino)" }), "destino elegido"),
    lado ? el("span", {}, `los demás, con el color de su saldo como ${lado}`) : null,
    enlaceAyuda("glosario"));
  const accesos = el("div", { class: "segmentos" },
    el("span", { class: "muted small" }, "Al pulsar un país:"),
    ...[["o", "origen"], ["d", "destino"], ["p", "ver el país"]].map(([v, t]) =>
      el("button", { type: "button", class: "boton" + (clic === v ? " activo" : ""), onclick: () => cambiar({ clic: v === "o" ? "" : v }) }, t)),
    el("span", { class: "muted small" }, "·"),
    el("button", { type: "button", class: "boton", onclick: () => cambiar({ o: paisActual(), d: "" }) }, `Desde ${nombrePais(paisActual())}`),
    el("button", { type: "button", class: "boton", onclick: () => cambiar({ d: paisActual(), o: "" }) }, `Hacia ${nombrePais(paisActual())}`),
    (o.size || d.size) ? el("button", { type: "button", class: "boton", onclick: () => cambiar({ o: "", d: "" }) }, "Todo el mundo") : null);
  return el("div", {}, cab, filtros, accesos, avisoOnu, avisoLeyes, mapa.nodo, tiempo, leyenda, resumenNodo, tablaNodo);
}

// Aviso que el lector puede cerrar para no verlo en cada visita (se recuerda en este navegador).
function avisoCerrable(clave, ...contenido) {
  const k = "concordia.aviso." + clave;
  try { if (localStorage.getItem(k) === "visto") return null; } catch { /* sin almacenamiento */ }
  const nodo = el("div", { class: "aviso-lectura aviso-cerrable" }, el("span", {}, ...contenido),
    el("button", { type: "button", class: "boton-cerrar", title: "Entendido, no volver a mostrar", "aria-label": "Cerrar aviso",
      onclick: () => { try { localStorage.setItem(k, "visto"); } catch { /* sin almacenamiento */ } nodo.remove(); } }, "✕"));
  return nodo;
}

// conOrigen / conDestino: con un solo origen (o destino) elegido, esa columna repetiría el mismo país en cada fila.
function tablaAristas(filas, qq, anios, { conOrigen = true, conDestino = true } = {}) {
  if (!filas.length) return el("div", { class: "vacio" }, "No hay relaciones con estos filtros.");
  const barra = (e) => {
    const t = Math.max(1, e.pos + e.neg + e.neu);
    return el("div", { class: "barra", title: textoSaldo(e.pos, e.neg, e.neu) },
      el("span", { class: "si", style: `width:${(100 * e.pos) / t}%` }), el("span", { class: "abs", style: `width:${(100 * e.neu) / t}%` }),
      el("span", { class: "no", style: `width:${(100 * e.neg) / t}%` }));
  };
  const soloOrigen = !conOrigen && filas[0] ? nombrePais(filas[0].origen) : null, soloDestino = !conDestino && filas[0] ? nombrePais(filas[0].destino) : null;
  return el("section", { class: "card" },
    el("h3", {}, soloOrigen ? `Lo que vota ${soloOrigen} sobre cada país · ${textoAnios(anios)}` : soloDestino ? `Lo que vota cada país sobre ${soloDestino} · ${textoAnios(anios)}`
      : `Relaciones con estos filtros · ${textoAnios(anios)}`),
    el("p", { class: "muted small" }, "Pulsa una fila para ver las leyes y los votos que hay detrás."),
    el("div", { class: "tabla-scroll" }, el("table", { class: "tabla" },
      el("thead", {}, el("tr", {}, conOrigen ? el("th", {}, "Origen") : null, conDestino ? el("th", {}, "Destino") : null, el("th", { class: "num" }, "Total"),
        el("th", { class: "num" }, "Positivas"), el("th", { class: "num" }, "Negativas"), el("th", { class: "num" }, "Neutras"),
        el("th", { title: "Reparto entre positivas (azul), neutras (gris) y negativas (rojo)" }, "Saldo"), el("th", {}, "De dónde"))),
      el("tbody", {}, filas.map((e) => el("tr", { class: "clic", onclick: () => panelArista(e.origen, e.destino, qq, anios) },
        conOrigen ? el("td", {}, nombrePais(e.origen)) : null, conDestino ? el("td", {}, nombrePais(e.destino)) : null, el("td", { class: "num" }, fmt(e.n)),
        el("td", { class: "num" }, fmt(e.pos)), el("td", { class: "num" }, fmt(e.neg)), el("td", { class: "num" }, fmt(e.neu)),
        el("td", { style: "min-width:120px" }, barra(e)),
        el("td", { class: "small muted" }, unirPartes([e.leyes ? `Parlamento: ${fmt(e.leyes)}` : "", e.onu ? `ONU: ${fmt(e.onu)}` : ""]))))))));
}

// Quién decidió qué países trata un asunto y en qué sentido, dicho para cualquiera.
function badgeMetodo(metodo) {
  const reglas = !metodo || metodo === "reglas" || metodo === "escrutinio:reglas";
  return el("span", { class: "badge ia", title: reglas
    ? "Países y sentido deducidos automáticamente de las palabras del título, sin IA. Puede equivocarse: el texto oficial manda."
    : `Países y sentido propuestos por una IA (${origenFicha(metodo)}) a partir del título. Puede equivocarse: el texto oficial manda.` },
  reglas ? "clasificación automática" : "clasificado por IA");
}
let COLUMNA_RELACIONES = null; // ¿trae asunto_mundo las relaciones de cada asunto? (datos generados después de añadirla)
const conRelacionesMundo = () => (COLUMNA_RELACIONES ??= q("PRAGMA table_info(asunto_mundo)").some((c) => c.name === "relaciones"));

function panelArista(origen, destino, qq, anios = aniosActuales()) {
  const [w, a] = filtrosRelacion({ ...qq, o: origen, d: destino }, anios);
  const filas = q(`SELECT r.*, am.titulo, am.codigo, am.url, am.resumen, am.resultado${conRelacionesMundo() ? ", am.relaciones AS rels" : ""}
                   FROM relacion r LEFT JOIN asunto_mundo am ON am.id=r.asunto_id AND am.anio=r.anio
                   WHERE ${w} ORDER BY r.fecha DESC LIMIT 400`, a);
  const leyes = filas.filter((r) => r.via === "ley"), onu = filas.filter((r) => r.via === "onu");
  const fuenteDe = (f) => CAT.fuentes[f]?.corto || f;
  // En la ONU la relación es «sentido de la resolución hacia el destino × voto»: con el sentido se recupera el voto.
  const votoOnu = (r) => {
    const rel = jsonDe(r.rels, []).find((x) => x.pais === destino);
    const o = rel ? ORIENTACION_TXT[rel.orientacion] : 0;
    if (!o) return null;
    const si = Math.sign(r.orientacion) === Math.sign(o);
    return el("span", { class: `badge voto-onu ${si ? "si" : "no"}`, title: `La resolución es ${o > 0 ? "favorable" : "desfavorable"} a ${nombrePais(destino)}` },
      `${nombrePais(origen)} votó ${si ? "sí" : "no"}`);
  };
  const item = (r) => el("div", { class: "fila-rel" },
    el("div", { class: "fecha" }, fecha(r.fecha)),
    el("div", {},
      el("div", { class: "titulo" }, r.url ? enlace(r.url, recortar(r.titulo, 180)) : recortar(r.titulo, 180)),
      limpiarResumen(r.resumen) ? el("div", { class: "resumen" }, limpiarResumen(r.resumen)) : null,
      el("div", { class: "badges" },
        chipRelacion({ orientacion: r.orientacion, tipo: r.tipo }, false),
        r.via === "onu" ? votoOnu(r) : null,
        r.via === "ley" ? badgeResultado(r.resultado) : null,
        el("span", { class: "badge" }, fuenteDe(r.fuente)), r.codigo ? el("span", { class: "badge" }, r.codigo) : null,
        r.tema ? el("span", { class: "badge" }, temaNombre(r.tema)) : null,
        badgeMetodo(r.metodo))));
  const pos = filas.filter((r) => r.orientacion > 0).length, neg = filas.filter((r) => r.orientacion < 0).length;
  const neu = filas.length - pos - neg;
  const [O, D] = [nombrePais(origen), nombrePais(destino)];
  abrirPanel(el("div", {},
    el("h2", {}, `${O} → ${D}`),
    el("p", { class: "sub" }, `${textoAnios(anios)} · ${cuenta(filas.length, "relación", "relaciones")}: ${textoSaldo(pos, neg, neu)}.`),
    leyes.length ? el("section", {}, el("h3", {}, `Lo que vota el parlamento de ${O} sobre ${D}`),
      el("p", { class: "muted small" }, `Cada asunto, con su sentido hacia ${D} (positivo: ayuda, acuerdo, apoyo; negativo: sanción, condena, restricción) y el resultado de su votación final.`), leyes.map(item)) : null,
    onu.length ? el("section", {}, el("h3", {}, `Cómo vota ${O} en la ONU las resoluciones sobre ${D}`),
      el("p", { class: "muted small" }, `Positiva: ${O} votó a favor de ${D} (sí a una resolución que lo favorece, o no a una que lo condena). Negativa, al revés. Las abstenciones no cuentan.`),
      onu.map(item)) : null,
    filas.length >= 400 ? el("p", { class: "muted small" }, "Se muestran las 400 más recientes.") : null,
    el("p", { class: "muted small" }, "El sentido de cada asunto se deduce de su título y puede equivocarse; el enlace lleva al texto oficial. ", enlaceAyuda("calculo", "Cómo se calcula")),
    el("p", {}, el("button", { class: "boton", onclick: () => { cerrarPanel(); irA("mundo", { o: origen, d: destino, modo: "" }); } }, "Ver solo este par en el mapa"))),
  { par: `${origen}-${destino}` });
}

// ------------------------------------------------------------------ modo afinidad en la ONU

function afinidadCon(ref, [desde, hasta]) {
  return q(`SELECT CASE WHEN a=?1 THEN b ELSE a END AS otro, SUM(suma) AS s, SUM(total) AS t FROM afinidad_onu
            WHERE (a=?1 OR b=?1) AND anio BETWEEN ?2 AND ?3 GROUP BY otro HAVING t >= 5`, [ref, desde, hasta])
    .map((r) => ({ ...r, pct: (100 * r.s) / r.t }));
}

function pintarAfinidad(qq, cab) {
  const [desde, hasta] = aniosActuales();
  const hastaOnu = Math.min(hasta, ONU_HASTA);
  const ref = (qq.ref && CAT.paises[qq.ref]) ? qq.ref : paisActual();
  const cambiar = (c) => irA("mundo", c);
  const controles = filaFiltros([
    multiSelect("ref", opcionesPaises().filter(([i]) => CAT.paises[i].onu_desde), ref, "País de referencia", "países", { buscar: true, unico: true }),
    selectFiltro("n", [["5", "5 flechas por lado"], ["10", "10 flechas por lado"], ["20", "20 flechas por lado"], ["0", "Sin flechas"]], qq.n || "10"),
    checkFiltro("centro", "Mapa fijo (sin centrar en el país)", qq.centro),
  ], (c) => cambiar(c), { plegable: false });
  if (desde > hastaOnu) {
    return el("div", {}, cab, controles, el("div", { class: "vacio" }, `La ONU tiene datos hasta ${ONU_HASTA}: elige años anteriores.`));
  }
  // Por año y país: los fotogramas se agregan en el navegador.
  const filas = q(`SELECT anio, CASE WHEN a=?1 THEN b ELSE a END AS otro, suma AS s, total AS t FROM afinidad_onu
                   WHERE (a=?1 OR b=?1) AND anio BETWEEN ?2 AND ?3`, [ref, desde, hastaOnu]);
  if (!filas.length) {
    return el("div", {}, cab, controles, el("div", { class: "vacio" }, `${nombrePais(ref)} no tiene votos en la ONU en esos años.`));
  }
  const agregar = (dentro) => {
    const m = {};
    for (const f of filas) {
      if (!dentro(f.anio)) continue;
      const r = (m[f.otro] = m[f.otro] || { otro: f.otro, s: 0, t: 0 });
      r.s += f.s; r.t += f.t;
    }
    return Object.values(m).filter((r) => r.t >= 5).map((r) => ({ ...r, pct: (100 * r.s) / r.t }));
  };
  // Siete tramos por cuantiles de todos los años (comparables de un año a otro), redondeados, en una escala
  // divergente: rojo, los que menos coinciden con el país; gris, la mitad; azul, los que más.
  const valores = filas.filter((f) => f.t >= 5).map((f) => (100 * f.s) / f.t).sort((x, y) => x - y);
  const cortes = [...new Set([1, 2, 3, 4, 5, 6].map((i) => Math.round(valores[Math.floor((i * valores.length) / 7)])))];
  const tramo = (v) => cortes.filter((c) => Math.round(v) >= c).length;
  const RAMPA = ["--div-1", "--div-2", "--div-3", "--div-4", "--div-5", "--div-6", "--div-7"].slice(-(cortes.length + 1));
  const n = +(qq.n ?? 10);
  const media = {};
  for (let y = desde; y <= hastaOnu; y++) {
    const xs = filas.filter((f) => f.anio === y && f.t >= 5);
    if (xs.length) media[y] = { valor: xs.reduce((s, f) => s + (100 * f.s) / f.t, 0) / xs.length };
  }
  const fotograma = ({ modo, anio }) => {
    const anios = !modo ? [desde, hastaOnu] : modo === "acum" ? [desde, anio] : [anio, anio];
    const rs = agregar((y) => y >= anios[0] && y <= anios[1]);
    const orden = [...rs].sort((x, y) => y.pct - x.pct);
    return { modo, anio, anios, rs, orden, porPais: Object.fromEntries(rs.map((r) => [r.otro, r])) };
  };
  const opcionesMapa = (fr) => {
    // Flechas a los n más afines (azul) y a los n menos afines (rojo) de ese fotograma.
    const arriba = fr.orden.slice(0, n), abajo = fr.orden.slice(-n).filter((r) => !arriba.includes(r));
    const flechas = n ? [...arriba.map((r) => [r, "p2"]), ...abajo.map((r) => [r, "n2"])].filter(([r]) => puntoPais(r.otro)).map(([r, clase]) => ({
      desde: ref, hasta: r.otro, n: 1, ancho: 2, clase,
      tip: () => [`${nombrePais(ref)} y ${nombrePais(r.otro)}`, `${textoAnios(fr.anios)}: coinciden en el ${Math.round(r.pct)} % de ${fmt(r.t)} votos`],
      alClicar: () => cambiar({ ref: r.otro }),
    })) : [];
    return {
      rellenar: (iso3) => (iso3 === ref ? "var(--ink)" : fr.porPais[iso3] ? `var(${RAMPA[tramo(fr.porPais[iso3].pct)]})` : null),
      tipPais: (iso3) => iso3 === ref ? [nombrePais(iso3), "País de referencia"]
        : fr.porPais[iso3] ? [nombrePais(iso3), `${textoAnios(fr.anios)}: coincide con ${nombrePais(ref)} en el ${Math.round(fr.porPais[iso3].pct)} % de ${fmt(fr.porPais[iso3].t)} votos`, "Pulsa para compararlo con todos"]
        : [nombrePais(iso3), "Sin votos comunes en esos años"],
      flechas, maxN: 1, origenes: new Set([ref]),
      etiquetas: [ref, ...fr.orden.slice(0, 4).map((r) => r.otro), ...fr.orden.slice(-4).map((r) => r.otro)],
    };
  };
  const anioInicial = Math.min(hastaOnu, Math.max(desde, +qq.t || hastaOnu));
  let fr = fotograma({ modo: qq.tiempo === "anio" || qq.tiempo === "acum" ? qq.tiempo : "", anio: anioInicial });
  const centro = qq.centro === "1" ? CENTRO_FIJO : centroDe([ref]) ?? CENTRO_FIJO;
  const mapa = crearMapa({ centro, alClicarPais: (iso3) => { if (fr.porPais[iso3]) cambiar({ ref: iso3 }); }, ...opcionesMapa(fr) });
  const bordes = [Math.round(valores[0]), ...cortes, Math.round(valores[valores.length - 1])];
  const leyenda = el("div", { class: "legend leyenda-mapa" },
    el("span", {}, el("i", { style: "background:var(--ink)" }), nombrePais(ref)),
    el("span", { class: "leyenda-titulo" }, "Coincide con él en el…"),
    RAMPA.map((v, i) => el("span", {}, el("i", { style: `background:var(${v})` }), `${bordes[i]}–${bordes[i + 1]} %`)),
    el("span", { class: "leyenda-titulo" }, "de los votos."),
    n ? el("span", {}, el("i", { class: "fl-p2" }), "flecha: de los más afines") : null, n ? el("span", {}, el("i", { class: "fl-n2" }), "de los menos afines") : null,
    enlaceAyuda("glosario"));
  const aviso = hasta > ONU_HASTA ? avisoCerrable("afinidad", `La ONU tiene datos hasta septiembre de ${ONU_HASTA}: aquí se usan ${textoAnios([desde, hastaOnu])}.`) : null;
  const listas = el("div");
  const pintarListas = () => {
    const puntos = (xs, color) => puntosH(xs.map((r) => ({ etiqueta: nombrePais(r.otro), valor: r.pct, tip: `${cuenta(r.t, "votación", "votaciones")} en común · pulsa para compararlo con todos`, iso3: r.otro })),
      { color, alClicar: (i) => cambiar({ ref: i.iso3 }) });
    listas.replaceChildren(
      el("p", { class: "muted small" }, `${nombrePais(ref)} · ${textoAnios(fr.anios)} · coincidencia en las votaciones finales: 1 si votan igual, ½ si uno se abstiene, 0 si votan lo contrario. Los colores del mapa usan los mismos tramos en todos los años.`),
      el("div", { class: "grid g2" },
        el("section", { class: "card" }, el("h3", {}, `Los que más votan como ${nombrePais(ref)} · ${textoAnios(fr.anios)}`), puntos(fr.orden.slice(0, 15), "var(--rel-p2)")),
        el("section", { class: "card" }, el("h3", {}, `Los que menos · ${textoAnios(fr.anios)}`), puntos(fr.orden.slice(-15).reverse(), "var(--rel-n2)"))));
  };
  pintarListas();
  const tiempo = lineaTiempo({
    desde, hasta: hastaOnu, modo: fr.modo, anio: anioInicial, barras: media, sinBarras: true,
    modos: [["", "Todo el periodo"], ["anio", "Año a año"], ["acum", "Acumulado"]],
    etiquetaBarra: (b) => `Coincidencia media con los demás: ${Math.round(b.valor)} %`,
    alCambiar: (estado) => { fr = fotograma(estado); mapa.actualizar(opcionesMapa(fr)); pintarListas(); },
  });
  // Evolución con los países elegidos como destino en el otro modo (o con las grandes potencias).
  const comparar = lista(qq.d).length ? lista(qq.d) : COMPARAR_ONU.filter((x) => x !== ref).slice(0, 4);
  const series = comparar.map((otro, i) => ({
    nombre: nombrePais(otro), color: COLORES_SERIE[i % COLORES_SERIE.length],
    puntos: filas.filter((f) => f.otro === otro && f.t >= 5).map((f) => ({ x: f.anio, y: (100 * f.s) / f.t })),
  })).filter((s) => s.puntos.length);
  return el("div", {}, cab, controles, aviso, mapa.nodo, tiempo, leyenda, listas,
    el("section", { class: "card", style: "margin-top:16px" },
      el("h3", {}, `Evolución de la coincidencia de ${nombrePais(ref)}`),
      el("p", { class: "muted small" }, "Con las grandes potencias (o con los países elegidos como destino en «Qué vota cada país sobre otros»). Para elegir otros, usa «En la ONU»."),
      lineasAnio(series)));
}
// Con quién se compara la evolución por defecto, igual en el mapa y en «En la ONU».
const COMPARAR_ONU = ["USA", "CHN", "RUS", "ESP", "IND"];
const COLORES_SERIE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"];

// ------------------------------------------------------------------ el mapa (d3-geo)

let GEO = null;
function geometria() {
  if (!GEO) GEO = topojson.feature(window.MUNDO_TOPO, window.MUNDO_TOPO.objects.countries).features;
  return GEO;
}

// op: centro (longitud), rellenar(iso3) -> color|null, tipPais(iso3) -> [valor, etiqueta, extra], alClicarPais(iso3),
// flechas: [{desde, hasta, n, clase, ancho?, tip() -> [..], alClicar()}], maxN, origenes (Set), etiquetas ([iso3]).
// Devuelve {nodo, actualizar(op)}: la línea de tiempo cambia colores y flechas sin rehacer el mapa (ni perder el zoom).
function crearMapa(op) {
  const ancho = Math.max(320, esMovil() ? window.innerWidth - 24 : Math.min(1280, $("#vista").clientWidth || 1200));
  // Equal Earth centrada en el país de origen; se recorta el sur (sin Antártida) para no gastar alto en océano.
  const proy = d3.geoEqualEarth().rotate([-op.centro, 0]).fitWidth(ancho - 8, { type: "Sphere" });
  const yN = proy([op.centro, 84])[1], yS = proy([op.centro, -57])[1];
  const alto = Math.round(yS - yN + 10);
  const [t0x, t0y] = proy.translate();
  proy.translate([t0x + 4, t0y - yN + 5]);
  const ruta = d3.geoPath(proy);
  const svg = svgEl("svg", { viewBox: `0 0 ${ancho} ${alto}`, class: "mapa-svg", role: "img", "aria-label": "Mapa del mundo con relaciones entre países" });
  const capaPaises = svgEl("g", {});
  const capaEncima = svgEl("g", {});
  capaPaises.append(svgEl("path", { class: "oceano", d: ruta({ type: "Sphere" }) }));
  svg.append(capaPaises, capaEncima);
  const trazos = {};
  const conEventos = (nodo, iso3) => {
    nodo.addEventListener("pointermove", (e) => { if (arrastre?.movido) return; const [v, t, x] = op.tipPais(iso3); tip(e, v, t, x); });
    nodo.addEventListener("pointerenter", () => enfocar(iso3));
    nodo.addEventListener("pointerleave", () => { tipOff(); desenfocar(); });
    nodo.addEventListener("click", () => { if (!clicAnulado) op.alClicarPais(iso3); });
  };
  for (const f of geometria()) {
    const p = svgEl("path", { class: "pais", d: ruta(f) });
    conEventos(p, f.id);
    capaPaises.append(p);
    (trazos[f.id] = trazos[f.id] || []).push(p);
  }
  // Microestados que no están en la geometría 1:110m: un punto de tamaño fijo en su centroide.
  const micro = Object.values(CAT.paises).filter((p) => !p.en_mapa && p.lat != null && !p.sucesor && (p.onu_desde || CAT.fuentesDe[p.iso3]));
  const puntosMicro = micro.map((p) => {
    const c = svgEl("circle", { class: "pais micro", r: 2.8 });
    conEventos(c, p.iso3);
    (trazos[p.iso3] = trazos[p.iso3] || []).push(c);
    return [p.iso3, c];
  });
  const capaMicro = svgEl("g", {}, puntosMicro.map(([, c]) => c));
  const capaFlechas = svgEl("g", { class: "flechas" });
  const capaNodos = svgEl("g", { class: "nodos" });
  const capaRotulos = svgEl("g", { class: "rotulos" });
  capaEncima.append(capaMicro, capaFlechas, capaNodos, capaRotulos);

  let k = 1, tx = 0, ty = 0;
  const escalaGrosor = Math.min(1, Math.max(0.45, ancho / 1000));  // en un mapa estrecho, flechas más finas
  const escalaPunto = Math.max(0.6, escalaGrosor);                   // y puntos más pequeños
  const pantalla = (iso3) => {
    const p = puntoPais(iso3);
    if (!p) return null;
    const [x, y] = proy(p);
    return [x * k + tx, y * k + ty];
  };
  const pintarRellenos = () => {
    for (const [iso3, nodos] of Object.entries(trazos)) {
      const color = op.rellenar(iso3);
      for (const n of nodos) { n.style.fill = color || ""; n.classList.toggle("marcado", !!color); }
    }
  };
  const dibujar = () => {
    capaPaises.setAttribute("transform", `translate(${tx.toFixed(1)},${ty.toFixed(1)}) scale(${k.toFixed(3)})`);
    for (const [iso3, c] of puntosMicro) {
      const p = pantalla(iso3);
      c.setAttribute("r", (2.8 * escalaPunto).toFixed(1));
      c.setAttribute("cx", p[0].toFixed(1));
      c.setAttribute("cy", p[1].toFixed(1));
    }
    capaFlechas.replaceChildren();
    capaNodos.replaceChildren();
    capaRotulos.replaceChildren();
    const maxN = Math.max(1, op.maxN || Math.max(1, ...op.flechas.map((f) => f.n)));
    // Con muchas flechas, más finas: 60 flechas gruesas hacia un mismo país tapan el mapa.
    const densidad = Math.min(1, Math.sqrt(24 / Math.max(24, op.flechas.length)));
    // Nodos: un punto en cada extremo, mayor cuanto más relaciones pasan por él.
    const peso = {};
    for (const f of op.flechas) { peso[f.desde] = (peso[f.desde] || 0) + f.n; peso[f.hasta] = (peso[f.hasta] || 0) + f.n; }
    const maxPeso = Math.max(1, ...Object.values(peso));
    const radio = (iso3) => (2.2 + 3.2 * Math.sqrt((peso[iso3] || 0) / maxPeso)) * escalaPunto;
    const orden = [...op.flechas].sort((a, b) => b.n - a.n);
    for (const f of orden) {
      const p0 = pantalla(f.desde), p1 = pantalla(f.hasta);
      if (!p0 || !p1) continue;
      const dx = p1[0] - p0[0], dy = p1[1] - p0[1], dist = Math.hypot(dx, dy);
      if (dist < 4) continue;
      const w = (f.ancho || 1.2 + 5 * densidad * Math.sqrt(Math.min(1, f.n / maxN))) * escalaGrosor;
      // Curva hacia la derecha del sentido de la marcha (A->B y B->A no se pisan), acotada en las largas.
      const off = Math.min(dist * 0.22, 26 + dist * 0.09);
      const c = [(p0[0] + p1[0]) / 2 - (dy / dist) * off, (p0[1] + p1[1]) / 2 + (dx / dist) * off];
      const u0 = [(c[0] - p0[0]), (c[1] - p0[1])], l0 = Math.hypot(...u0) || 1;
      const ini = [p0[0] + (u0[0] / l0) * (radio(f.desde) + 1), p0[1] + (u0[1] / l0) * (radio(f.desde) + 1)];
      const u1 = [p1[0] - c[0], p1[1] - c[1]], l1 = Math.hypot(...u1) || 1;
      const ux = u1[0] / l1, uy = u1[1] / l1;
      const cabeza = 4 + w * 1.5;
      const punta = [p1[0] - ux * (radio(f.hasta) + 1), p1[1] - uy * (radio(f.hasta) + 1)];
      const fin = [punta[0] - ux * cabeza * 0.8, punta[1] - uy * cabeza * 0.8];
      const d = `M${ini[0].toFixed(1)},${ini[1].toFixed(1)} Q${c[0].toFixed(1)},${c[1].toFixed(1)} ${fin[0].toFixed(1)},${fin[1].toFixed(1)}`;
      const base = [punta[0] - ux * cabeza, punta[1] - uy * cabeza];
      const px = -uy * cabeza * 0.55, py = ux * cabeza * 0.55;
      const dCabeza = `M${punta[0].toFixed(1)},${punta[1].toFixed(1)} L${(base[0] + px).toFixed(1)},${(base[1] + py).toFixed(1)} L${(base[0] - px).toFixed(1)},${(base[1] - py).toFixed(1)} Z`;
      const g = svgEl("g", { class: `flecha fl-${f.clase}`, "data-o": f.desde, "data-d": f.hasta },
        svgEl("path", { class: "halo", d, "stroke-width": (w + 2.5).toFixed(2) }),
        svgEl("path", { class: "halo", d: dCabeza, "stroke-width": 2.5 }),
        svgEl("path", { class: "linea", d, "stroke-width": w.toFixed(2) }),
        svgEl("path", { class: "cabeza", d: dCabeza }),
        svgEl("path", { class: "hit-flecha", d, "stroke-width": (w + 10).toFixed(1) }));
      g.addEventListener("pointermove", (e) => { if (arrastre?.movido) return; const [v, t, x] = f.tip(); tip(e, v, t, x); });
      g.addEventListener("pointerenter", () => { svg.classList.add("enfoque"); g.classList.add("activa"); });
      g.addEventListener("pointerleave", () => { tipOff(); desenfocar(); });
      if (f.alClicar) g.addEventListener("click", (e) => { e.stopPropagation(); if (clicAnulado) return; tipOff(); f.alClicar(); });
      capaFlechas.append(g);
    }
    for (const iso3 of Object.keys(peso)) {
      const p = pantalla(iso3);
      if (!p) continue;
      const n = svgEl("circle", { class: "nodo" + (op.origenes?.has(iso3) ? " nodo-origen" : ""), cx: p[0].toFixed(1), cy: p[1].toFixed(1), r: radio(iso3).toFixed(1), "data-iso": iso3 });
      conEventos(n, iso3);
      capaNodos.append(n);
    }
    // Rótulos por orden de importancia, sin solaparse entre sí.
    const puestos = [];
    for (const iso3 of [...new Set(op.etiquetas || [])]) {
      if (puestos.length >= (esMovil() ? 6 : 14)) break;
      const p = pantalla(iso3);
      if (!p || p[0] < 0 || p[0] > ancho || p[1] < 0 || p[1] > alto) continue;
      const texto = nombrePais(iso3);
      const w = texto.length * 6.6 + 6, h = 15;
      const y = p[1] - radio(iso3) - 5;
      const caja = [p[0] - w / 2, y - h + 3, p[0] + w / 2, y + 3];
      if (puestos.some((b) => caja[0] < b[2] && caja[2] > b[0] && caja[1] < b[3] && caja[3] > b[1])) continue;
      puestos.push(caja);
      capaRotulos.append(svgEl("text", { class: "rotulo" + (op.origenes?.has(iso3) ? " rotulo-origen" : ""), x: p[0].toFixed(1), y: y.toFixed(1), "text-anchor": "middle" }, texto));
    }
  };
  // Al pasar por un país se resaltan sus flechas y se atenúan las demás.
  const enfocar = (iso3) => {
    const suyas = capaFlechas.querySelectorAll(`[data-o="${iso3}"], [data-d="${iso3}"]`);
    if (!suyas.length) return;
    svg.classList.add("enfoque");
    for (const g of suyas) g.classList.add("activa");
  };
  const desenfocar = () => {
    svg.classList.remove("enfoque");
    for (const g of capaFlechas.querySelectorAll(".activa")) g.classList.remove("activa");
  };

  // Zoom con la rueda (centrado en el puntero), doble clic, pellizco y botones; arrastrar para moverse.
  const limitar = () => {
    k = Math.min(16, Math.max(1, k));
    tx = Math.min(0, Math.max(ancho * (1 - k), tx));
    ty = Math.min(0, Math.max(alto * (1 - k), ty));
    svg.style.touchAction = k > 1 ? "none" : "pan-y";
    svg.classList.toggle("ampliado", k > 1);
  };
  let pendiente = null;
  const redibujar = () => { cancelAnimationFrame(pendiente); pendiente = requestAnimationFrame(dibujar); };
  const aSvg = (e) => { const r = svg.getBoundingClientRect(); return [((e.clientX - r.left) / r.width) * ancho, ((e.clientY - r.top) / r.height) * alto]; };
  const zoom = (factor, [cx, cy]) => {
    const nk = Math.min(16, Math.max(1, k * factor));
    tx = cx - ((cx - tx) * nk) / k; ty = cy - ((cy - ty) * nk) / k; k = nk;
    limitar(); redibujar();
  };
  // La rueda sola desplaza la página (el mapa ocupa casi toda la pantalla y no debe atraparla); con Ctrl
  // (o ⌘, o el pellizco del trackpad, que llega como Ctrl + rueda) amplía. Ya ampliado, la rueda también
  // amplía y reduce, y al volver al mundo entero deja pasar el desplazamiento.
  let avisoRueda = null;
  const aviso = el("div", { class: "mapa-aviso", "aria-hidden": "true" }, "Usa Ctrl + rueda para ampliar el mapa");
  svg.addEventListener("wheel", (e) => {
    const delta = e.deltaMode === 1 ? e.deltaY * 16 : e.deltaY;
    if (!(e.ctrlKey || e.metaKey) && k <= 1) {
      aviso.classList.add("visible");
      clearTimeout(avisoRueda);
      avisoRueda = setTimeout(() => aviso.classList.remove("visible"), 1400);
      return;
    }
    e.preventDefault();
    zoom(Math.exp(-delta * 0.0022), aSvg(e));
  }, { passive: false });
  svg.addEventListener("dblclick", (e) => { e.preventDefault(); zoom(e.shiftKey ? 0.5 : 2, aSvg(e)); });
  const punteros = new Map();
  let arrastre = null, pellizco = null, clicAnulado = false;
  svg.addEventListener("pointerdown", (e) => {
    if (e.pointerType === "mouse" && e.button !== 0) return;
    punteros.set(e.pointerId, aSvg(e));
    clicAnulado = false;
    if (punteros.size === 2) {
      const [a, b] = [...punteros.values()];
      pellizco = { dist: Math.hypot(a[0] - b[0], a[1] - b[1]), k };
      arrastre = null;
    } else {
      arrastre = { inicio: aSvg(e), tx, ty, movido: false };
    }
  });
  svg.addEventListener("pointermove", (e) => {
    if (!punteros.has(e.pointerId)) return;
    punteros.set(e.pointerId, aSvg(e));
    if (pellizco && punteros.size === 2) {
      const [a, b] = [...punteros.values()];
      const dist = Math.hypot(a[0] - b[0], a[1] - b[1]);
      zoom((pellizco.k * dist) / pellizco.dist / k, [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]);
      clicAnulado = true;
      return;
    }
    if (!arrastre || k === 1) return;
    const [x, y] = aSvg(e);
    if (!arrastre.movido && Math.abs(x - arrastre.inicio[0]) + Math.abs(y - arrastre.inicio[1]) > 4) {
      arrastre.movido = true;
      svg.setPointerCapture(e.pointerId);
      svg.classList.add("arrastrando");
      tipOff();
    }
    if (arrastre.movido) {
      tx = arrastre.tx + x - arrastre.inicio[0]; ty = arrastre.ty + y - arrastre.inicio[1];
      limitar(); redibujar();
    }
  });
  const soltar = (e) => {
    punteros.delete(e.pointerId);
    if (punteros.size < 2) pellizco = null;
    if (arrastre?.movido) clicAnulado = true;
    arrastre = null;
    svg.classList.remove("arrastrando");
  };
  svg.addEventListener("pointerup", soltar);
  svg.addEventListener("pointercancel", soltar);
  const botones = el("div", { class: "mapa-zoom" },
    el("button", { type: "button", class: "boton", title: "Acercar", "aria-label": "Acercar", onclick: () => zoom(1.6, [ancho / 2, alto / 2]) }, "+"),
    el("button", { type: "button", class: "boton", title: "Alejar", "aria-label": "Alejar", onclick: () => zoom(1 / 1.6, [ancho / 2, alto / 2]) }, "−"),
    el("button", { type: "button", class: "boton", title: "Ver el mundo entero", "aria-label": "Ver el mundo entero", onclick: () => { k = 1; tx = 0; ty = 0; limitar(); redibujar(); } }, "⟲"));
  // Encuadre: ampliar hasta que quepan los países pedidos (con margen para la curva de las flechas).
  const pts = (op.encuadre || []).map(puntoPais).filter(Boolean).map((p) => proy(p));
  if (pts.length >= 2) {
    const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
    const margen = Math.max(70, ancho * 0.08);
    const [x0, x1, y0, y1] = [Math.min(...xs) - margen, Math.max(...xs) + margen, Math.min(...ys) - margen, Math.max(...ys) + margen];
    k = Math.min(4, ancho / (x1 - x0), alto / (y1 - y0));
    if (k > 1.15) {
      tx = ancho / 2 - ((x0 + x1) / 2) * k;
      ty = alto / 2 - ((y0 + y1) / 2) * k;
    } else { k = 1; }
  }
  limitar();
  pintarRellenos();
  dibujar();
  return {
    nodo: el("div", { class: "mapa" }, svg, botones, esMovil() ? null : aviso),
    actualizar(nuevo) { op = { ...op, ...nuevo }; pintarRellenos(); dibujar(); },
  };
}
