"use strict";

// ------------------------------------------------------------------ utilidades

const $ = (sel, root = document) => root.querySelector(sel);

function el(tag, attrs, ...hijos) {
  const svg = tag.startsWith("svg:");
  const n = svg ? document.createElementNS("http://www.w3.org/2000/svg", tag.slice(4)) : document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") svg ? n.setAttribute("class", v) : (n.className = v);
    else if (k === "style") n.setAttribute("style", v);
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else if (k === "html") n.innerHTML = v; // solo para marcado propio, nunca datos
    else n.setAttribute(k, v === true ? "" : v);
  }
  for (const h of hijos.flat(Infinity)) {
    if (h === null || h === undefined || h === false) continue;
    n.appendChild(h instanceof Node ? h : document.createTextNode(String(h)));
  }
  return n;
}
const svgEl = (tag, attrs, ...hijos) => el("svg:" + tag, attrs, ...hijos);

// Móvil: pantalla estrecha o teléfono girado. La clase «movil» en <html> activa su interfaz (styles.css).
const MQ_MOVIL = matchMedia("(max-width: 700px), (pointer: coarse) and (max-height: 500px)");
const esMovil = () => MQ_MOVIL.matches;
document.documentElement.classList.toggle("movil", esMovil());
const anchoGrafico = (defecto) => (esMovil() ? Math.max(280, Math.min(defecto, window.innerWidth - 40)) : defecto);

const MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
const fmt = (n) => (n ?? 0).toLocaleString("es-ES");
const pct = (a, b) => (b ? Math.round((100 * a) / b) : 0);
function fecha(iso) {
  if (!iso) return "";
  const [y, m, d] = iso.slice(0, 10).split("-");
  return `${+d} ${MESES[+m - 1]} ${y}`;
}
const jsonDe = (v, d) => { try { return v ? JSON.parse(v) : d; } catch { return d; } };
const lista = (v) => String(v ?? "").split(",").map((s) => s.trim()).filter(Boolean);
const recortar = (t, max = 140) => (!t ? "" : t.length <= max ? t : t.slice(0, max - 1).replace(/\s+\S*$/, "") + "…");
const enlace = (href, texto) => el("a", { href, target: "_blank", rel: "noopener" }, texto);
// «1 ley», «2 leyes»: número con el sustantivo en singular o plural.
const cuenta = (n, uno, varios) => `${fmt(n)} ${n === 1 ? uno : varios}`;
const textoSaldo = (pos, neg, neu) =>
  [cuenta(pos, "positiva", "positivas"), cuenta(neg, "negativa", "negativas"), cuenta(neu, "neutra", "neutras")].join(" · ");
// Une trozos con « · » sin dejar «Punto 7. · …»: quita el punto final de cada trozo.
const unirPartes = (partes) => partes.filter(Boolean)
  .map((p) => String(p).trim().replace(/\.\s*·\s*/g, " · ").replace(/\.$/, "")).join(" · ");
// Las fichas de la IA a veces comentan el propio título («El título no detalla…»): eso no es un resumen.
function limpiarResumen(t) {
  if (!t) return "";
  return t.replace(/(?:^|\s)(?:El título|El enunciado|No se (?:detalla|especifica|indica|precisa))[^.]*\.(?=\s|$)/g, "").trim();
}
const enlaceAyuda = (sec, texto = "¿Qué significa?") =>
  el("a", { href: `#/ayuda?sec=${sec}`, class: "enlace-ayuda", onclick: (e) => { e.preventDefault(); irA("ayuda", { sec }); } }, texto);
// Escalas con marcas redondas (0, 1000, 2000, 3000 en vez de 0, 1401, 2801).
function marcasBonitas(max, n = 4) {
  const bruto = Math.max(1, max) / n;
  const pot = 10 ** Math.floor(Math.log10(bruto));
  const paso = [1, 2, 2.5, 5, 10].map((m) => m * pot).find((p) => p >= bruto);
  const tope = Math.ceil(max / paso) * paso || paso;
  const xs = [];
  for (let v = 0; v <= tope + paso / 2; v += paso) xs.push(v);
  return { tope, marcas: xs };
}
const ANIO_ACTUAL = new Date().getFullYear();

// ------------------------------------------------------------------ base de datos (sql.js)
// La SQLite viaja troceada y comprimida en datos/*.js (ver concordia/exportar_web.py): comun.js, un
// <fuente>/<año>.js por año de cada fuente y un mundo/<año>.js con las relaciones de ese año. Se cargan con
// <script> (funciona con file://) y se juntan en una sola base en memoria. Solo se descarga lo que pide
// cada vista (el país y los años elegidos); lo ya cargado se queda.

let SQL = null;
let DB = null;
let CAT = null;          // catálogo de comun.js: países, fuentes, partidos, temas, cobertura
let ONU_HASTA = null;    // último año con votaciones de la ONU (del catálogo)
const CARGADOS = new Set();

function b64aBytes(b64) {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}
async function descomprimir(b64) {
  const flujo = new Blob([b64aBytes(b64)]).stream().pipeThrough(new DecompressionStream("gzip"));
  return new Uint8Array(await new Response(flujo).arrayBuffer());
}
function cargarScript(src) {
  return new Promise((ok, mal) => {
    const s = document.createElement("script");
    s.src = src;
    s.onload = ok;
    s.onerror = () => mal(new Error(`no se pudo cargar ${src}`));
    document.head.appendChild(s);
  });
}
const INDICE = () => window.CONCORDIA_INDICE;
const DATOS = () => (window.CONCORDIA_DATOS = window.CONCORDIA_DATOS || {});
const conVersion = (f) => `datos/${f.nombre}.js${location.protocol.startsWith("http") ? `?v=${f.huella}` : ""}`;

function q(sql, params = []) {
  const st = DB.prepare(sql);
  st.bind(params.map((v) => (v === undefined ? null : v)));
  const filas = [];
  while (st.step()) filas.push(st.getAsObject());
  st.free();
  return filas;
}
const q1 = (sql, params) => q(sql, params)[0] || {};
const marcas = (xs) => xs.map(() => "?").join(",");

async function abrirBase() {
  // El índice cambia con cada publicación de datos: se pide siempre de nuevo, para no mezclar un índice viejo
  // de la caché con ficheros nuevos (en file:// no hay caché que saltar).
  await cargarScript(`datos/indice.js${location.protocol.startsWith("http") ? `?v=${Date.now()}` : ""}`).catch(() => {});
  if (!INDICE()) throw new Error("Falta web/datos/indice.js. Genéralo con: python -m concordia web");
  SQL = await initSqlJs({ wasmBinary: b64aBytes(window.SQL_WASM_B64) });
  delete window.SQL_WASM_B64;
  const comun = INDICE().ficheros.find((f) => f.nombre === "comun");
  await cargarScript(conVersion(comun));
  DB = new SQL.Database(await descomprimir(DATOS().comun));
  delete DATOS().comun;
  CARGADOS.add("comun");
  leerCatalogo();
}

function leerCatalogo() {
  const paises = Object.fromEntries(q("SELECT * FROM pais").map((p) => [p.iso3, p]));
  const fuentes = Object.fromEntries(q("SELECT * FROM fuente ORDER BY orden").map((f) => [f.codigo, f]));
  const fuentesDe = {};
  for (const f of Object.values(fuentes)) if (f.pais && f.votaciones) (fuentesDe[f.pais] = fuentesDe[f.pais] || []).push(f);
  const partidos = {};
  for (const p of q("SELECT * FROM partido")) partidos[`${p.fuente}|${p.codigo}`] = p;
  const anios = q1("SELECT MIN(anio) AS a, MAX(anio) AS b FROM cobertura");
  CAT = {
    paises, fuentes, fuentesDe, partidos,
    temas: q("SELECT * FROM tema ORDER BY rowid"),
    tiposRel: Object.fromEntries(q("SELECT * FROM tipo_relacion").map((t) => [t.codigo, t.nombre])),
    camaras: Object.fromEntries(q("SELECT * FROM camara").map((c) => [c.codigo, c])),
    cobertura: q("SELECT * FROM cobertura ORDER BY fuente, anio"),
    // Eurodiputados de cada país por año: [{fuente, anio, pais, miembros}] (datos anteriores al Parlamento Europeo: vacío).
    delegaciones: q("SELECT name FROM sqlite_master WHERE name='delegacion'").length ? q("SELECT * FROM delegacion") : [],
    anioMin: anios.a || 1946, anioMax: Math.max(anios.b || 0, new Date().getFullYear()),
    ficheros: Object.fromEntries(INDICE().ficheros.map((f) => [f.nombre, f])),
  };
  ONU_HASTA = fuentes.onu?.anio_max || CAT.anioMax;
}
// La Unión Europea está en el catálogo de países para ser origen de lo que vota el Parlamento Europeo, pero no es un Estado.
const esOrganismo = (iso3) => !!CAT.paises[iso3]?.organismo;
// Eurodiputados de un país en unos años (0 si no era de la UE).
const eurodiputados = (iso3, [a, b]) => Math.max(0, ...CAT.delegaciones.filter((d) => d.pais === iso3 && d.anio >= a && d.anio <= b).map((d) => d.miembros));

// Descarga (si hace falta) y junta en la base los ficheros pedidos.
async function asegurar(nombres, avisar = () => {}) {
  const faltan = nombres.filter((n) => !CARGADOS.has(n) && CAT.ficheros[n]);
  if (!faltan.length) return;
  const bajar = faltan.filter((n) => !DATOS()[n]);
  if (bajar.length) {
    const mb = bajar.reduce((a, n) => a + CAT.ficheros[n].bytes, 0) / 1e6;
    avisar(`Descargando ${bajar.length} fichero${bajar.length === 1 ? "" : "s"} de datos (${mb.toLocaleString("es-ES", { maximumFractionDigits: 1 })} MB)…`);
    await Promise.all(bajar.map((n) => cargarScript(conVersion(CAT.ficheros[n]))));
  }
  avisar(`Abriendo ${faltan.length} fichero${faltan.length === 1 ? "" : "s"}…`);
  for (const n of faltan) {
    const trozo = new SQL.Database(await descomprimir(DATOS()[n]));
    delete DATOS()[n];
    DB.exec(`ATTACH DATABASE '/${trozo.filename}' AS l`);
    DB.exec("BEGIN");
    for (const { name } of q("SELECT name FROM l.sqlite_master WHERE type = 'table'")) {
      DB.exec(`INSERT OR IGNORE INTO main."${name}" SELECT * FROM l."${name}"`);
    }
    DB.exec("COMMIT");
    DB.exec("DETACH DATABASE l");
    trozo.close();
    CARGADOS.add(n);
  }
}
const nombresFuente = (fuente, [desde, hasta]) =>
  Object.values(CAT.ficheros).filter((f) => f.tipo === "fuente" && f.fuente === fuente && f.anio >= desde && f.anio <= hasta).map((f) => f.nombre);
const nombresMundo = ([desde, hasta]) =>
  Object.values(CAT.ficheros).filter((f) => f.tipo === "mundo" && f.anio >= desde && f.anio <= hasta).map((f) => f.nombre);
const pesoDe = (nombres) => nombres.filter((n) => !CARGADOS.has(n)).reduce((a, n) => a + (CAT.ficheros[n]?.bytes || 0), 0);

// ------------------------------------------------------------------ catálogo: nombres y colores

const nombrePais = (iso3) => CAT.paises[iso3]?.nombre || iso3;
function puntoPais(iso3) {
  let p = CAT.paises[iso3];
  if (p && p.lat == null && p.sucesor) p = CAT.paises[p.sucesor];
  return p && p.lat != null ? [p.lon, p.lat] : null;
}
const temaNombre = (c) => CAT.temas.find((t) => t.codigo === c)?.nombre || c || "Sin tema";
function partido(fuente, codigo) {
  return CAT.partidos[`${fuente}|${codigo}`] || { codigo, siglas: codigo, nombre: codigo, color: "#898781" };
}
const colorPartido = (fuente, codigo) => partido(fuente, codigo).color || "#898781";
const TIPOS_ASUNTO = { ley: "Ley", resolucion: "Resolución", mocion: "Moción", tratado: "Tratado", nombramiento: "Nombramiento",
  procedimiento: "Procedimiento", otro: "Otro" };
const TIPOS_VOTACION = { final: "Votación final", enmienda: "Enmienda", parcial: "Votación separada", procedimiento: "Procedimiento",
  nombramiento: "Nombramiento", otra: "Otra" };
const SENTIDO = { si: ["✓", "Sí"], no: ["✗", "No"], abstencion: ["~", "Abstención"], dividido: ["±", "Dividido"], no_vota: ["·", "No vota"] };
const ORIENTACION = { 1: ["+", "positiva"], "-1": ["−", "negativa"], 0: ["○", "neutra"] };
const ORIENTACION_TXT = { positiva: 1, negativa: -1, neutra: 0 };
function origenFicha(o) {
  if (!o) return "sin ficha";
  if (o === "reglas" || o === "escrutinio:reglas") return "reglas (sin IA)";
  if (o.startsWith("escrutinio:")) return "Escrutinio";
  if (o.startsWith("deepseek:")) return "IA (" + o.slice(9) + ")";
  return o;
}

// ------------------------------------------------------------------ ruta y selección global
// #/<vista>?p=ESP&a=2021-2026&... El país (p) y los años (a) se conservan al cambiar de vista.

const CLAVE_PAIS = "concordia.pais";
function leerRuta() {
  const h = location.hash.replace(/^#\/?/, "");
  const [vista, qs] = h.split("?");
  return { vista: vista || "mundo", q: Object.fromEntries(new URLSearchParams(qs || "")) };
}
function hashDe(vista, qobj) {
  const limpio = Object.fromEntries(Object.entries(qobj).filter(([, v]) => v !== "" && v !== null && v !== undefined));
  const s = new URLSearchParams(limpio).toString();
  return `#/${vista}${s ? "?" + s : ""}`;
}
// Al cambiar filtros se cierra el detalle abierto (v: votación, par: flecha), salvo que se pida otro.
// arriba: volver al principio de la página al pintar (paginación, atajos que cambian de contenido).
let SUBIR = false;
function irA(vista, cambios = {}, { reemplazar = false, arriba = false } = {}) {
  const r = leerRuta();
  const base = vista === r.vista ? { ...r.q, v: "", par: "", sec: "" } : { p: r.q.p, a: r.q.a };
  const h = hashDe(vista, { ...base, ...cambios });
  SUBIR = SUBIR || arriba;
  if (reemplazar) history.replaceState(null, "", h);
  else location.hash = h;
  if (reemplazar) render();
}
// Cambia la URL sin volver a pintar (enlace permanente al detalle abierto).
function marcarEnUrl(cambios) {
  const r = leerRuta();
  history.replaceState(null, "", hashDe(r.vista, { ...r.q, ...cambios }));
}
// El país de la URL o, si no hay, el último elegido en este navegador. Con p=todos, o si nunca se ha
// elegido ninguno, devuelve null: la foto global.
const TODOS = "todos";
function paisActual() {
  const r = leerRuta();
  if (r.q.p === TODOS) return null;
  if (r.q.p && CAT.paises[r.q.p]) return r.q.p;
  try { const g = localStorage.getItem(CLAVE_PAIS); if (g && CAT.paises[g]) return g; } catch { /* sin almacenamiento */ }
  return null;
}
function aniosActuales() {
  const r = leerRuta();
  const m = /^(\d{4})(?:-(\d{4}))?$/.exec(r.q.a || "");
  if (m) {
    const a = Math.max(CAT.anioMin, +m[1]), b = Math.min(CAT.anioMax, +(m[2] || m[1]));
    if (a <= b) return [a, b];
  }
  return [CAT.anioMax - 5, CAT.anioMax];
}
const textoAnios = ([a, b]) => (a === b ? String(a) : `${a}–${b}`);

// ------------------------------------------------------------------ cabecera: país y años

function pintarCabecera() {
  const iso = paisActual();
  $("#botonPais .sel-texto").textContent = iso ? nombrePais(iso) : "Todos los países";
  $("#botonAnios .sel-texto").textContent = textoAnios(aniosActuales());
  const r = leerRuta();
  for (const a of document.querySelectorAll("[data-tab]")) {
    a.classList.toggle("activo", a.dataset.tab === r.vista);
    if (a.tagName === "A") a.setAttribute("href", hashDe(a.dataset.tab, { p: r.q.p, a: r.q.a }));
  }
}

function abrirDialogo(contenido, titulo) {
  const fondo = $("#dialogoFondo"), caja = $("#dialogo");
  caja.replaceChildren(el("div", { class: "dlg-cab" }, el("h3", {}, titulo),
    el("button", { type: "button", class: "boton", onclick: cerrarDialogo, "aria-label": "Cerrar" }, "✕")), contenido);
  fondo.classList.add("abierto");
  caja.classList.add("abierto");
  caja.setAttribute("aria-hidden", "false");
}
function cerrarDialogo() {
  $("#dialogoFondo").classList.remove("abierto");
  $("#dialogo").classList.remove("abierto");
  $("#dialogo").setAttribute("aria-hidden", "true");
}

// iso3 null: ningún país (la foto global).
function elegirPais(iso3) {
  const p = iso3 || TODOS;
  try { localStorage.setItem(CLAVE_PAIS, p); } catch { /* sin almacenamiento */ }
  cerrarDialogo();
  const r = leerRuta();
  if (r.vista === "mundo") {
    // En el mapa, el país elegido pasa a ser el origen (o la referencia, en el modo de afinidad); sin país, se ve todo.
    location.hash = hashDe("mundo", r.q.modo === "afinidad" ? { ...r.q, p, ref: iso3 || "" } : { ...r.q, p, o: iso3 || "", d: "" });
    return;
  }
  location.hash = hashDe(r.vista === "ayuda" ? "resumen" : r.vista, { p, a: r.q.a });
}

// Nombre propio de lo que vota en cada fuente, con su artículo, para las frases sobre un país concreto
// («lo que vota el Bundestag…»). Un conector nuevo sin entrada aquí sale como «el parlamento de <país>».
const ORGANOS = {
  usa: "el Congreso", gbr: "la Cámara de los Comunes", pol: "el Sejm", esp: "el Congreso de los Diputados",
  irl: "el Oireachtas", che: "el Consejo Nacional", can: "la Cámara de los Comunes", bra: "el Congreso Nacional",
  swe: "el Riksdag", fra: "la Asamblea Nacional", nld: "la Tweede Kamer", dnk: "el Folketing",
  cze: "la Cámara de Diputados", arg: "el Congreso", fin: "el Eduskunta", est: "el Riigikogu", deu: "el Bundestag",
  chl: "el Congreso Nacional", mex: "la Cámara de Diputados", ukr: "la Verjovna Rada", nor: "el Storting", isr: "la Knesset",
  eup: "el Parlamento Europeo",
};
// «el Bundestag», «el Bundestag de Alemania» (conPais) o «Bundestag» (sinArticulo, para etiquetas).
function organo(iso3, { conPais = false, sinArticulo = false } = {}) {
  const propio = ORGANOS[(CAT.fuentesDe[iso3] || [])[0]?.codigo];
  // Un organismo (la Unión Europea) no lleva «de <país>»: «el Parlamento Europeo», no «… de Unión Europea».
  const texto = propio ? (conPais && !esOrganismo(iso3) ? `${propio} de ${nombrePais(iso3)}` : propio) : `el parlamento de ${nombrePais(iso3)}`;
  if (!sinArticulo) return texto;
  const sin = (propio || "el parlamento").replace(/^(el|la) /, "");
  return sin[0].toUpperCase() + sin.slice(1);
}

// Nombre de las cámaras con datos de un país: «Bundestag», «Congreso de los Diputados», «Cámara y Senado»...
function camarasDe(iso3) {
  return (CAT.fuentesDe[iso3] || []).map((f) => {
    const cs = Object.values(CAT.camaras).filter((c) => c.fuente === f.codigo);
    return cs.length === 1 ? cs[0].nombre.replace(/\s*\(.*\)$/, "") : cs.map((c) => c.corto || c.nombre).join(" y ");
  }).join(" · ");
}

function abrirSelectorPais() {
  const actual = paisActual();
  const conParlamento = Object.keys(CAT.fuentesDe).sort((a, b) => nombrePais(a).localeCompare(nombrePais(b), "es"));
  const todos = Object.values(CAT.paises).filter((p) => p.onu_desde || CAT.fuentesDe[p.iso3])
    .sort((a, b) => a.nombre.localeCompare(b.nombre, "es"));
  const listaNodo = el("div", { class: "pais-lista" });
  const fila = (p) => el("button", { type: "button", class: "pais-op" + (p.iso3 === actual ? " activo" : ""), onclick: () => elegirPais(p.iso3) },
    el("span", {}, p.nombre),
    CAT.fuentesDe[p.iso3] ? el("span", { class: "badge ok", title: CAT.fuentesDe[p.iso3].map((f) => f.nombre).join(" · ") }, camarasDe(p.iso3)) : null,
    p.sucesor ? el("span", { class: "muted small" }, `hasta ${p.onu_hasta}`) : null);
  const pintar = (texto) => {
    const t = texto.trim().toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
    const casa = (p) => !t || p.nombre.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").includes(t) || p.iso3.toLowerCase() === t;
    const regiones = {};
    for (const p of todos.filter(casa)) (regiones[p.region || "Otros"] = regiones[p.region || "Otros"] || []).push(p);
    // replaceChildren no aplana listas ni ignora null: se le pasan los nodos sueltos.
    const grupos = Object.entries(regiones).sort(([a], [b]) => a.localeCompare(b, "es")).map(([reg, ps]) =>
      el("div", { class: "pais-grupo" }, el("h4", {}, reg), ps.map(fila)));
    listaNodo.replaceChildren(
      ...(!t ? [el("div", { class: "pais-grupo" },
        el("button", { type: "button", class: "pais-op" + (!actual ? " activo" : ""), onclick: () => elegirPais(null) },
          el("span", {}, "Todos los países"), el("span", { class: "badge" }, "foto global, sin ninguno elegido"))),
      el("div", { class: "pais-grupo" }, el("h4", {}, "Con votaciones de su parlamento"),
        conParlamento.map((i) => fila(CAT.paises[i])))] : []),
      ...grupos,
      ...(!grupos.length ? [el("p", { class: "muted" }, "Ningún país con ese nombre.")] : []));
  };
  const buscador = el("input", { type: "search", placeholder: "Buscar país…", class: "pais-buscar", oninput: (e) => pintar(e.target.value) });
  pintar("");
  abrirDialogo(el("div", {},
    el("p", { class: "muted small" }, `Junto a cada país, la cámara de la que se recogen las votaciones; todos tienen su voto en la ONU (1946–${ONU_HASTA}) y lo que otros votan sobre ellos.`),
    buscador, listaNodo), "Elegir país");
  setTimeout(() => buscador.focus(), 50);
}

function abrirSelectorAnios() {
  const [a, b] = aniosActuales();
  const opciones = [];
  for (let y = CAT.anioMax; y >= CAT.anioMin; y--) opciones.push(y);
  const sel = (v) => el("select", {}, opciones.map((y) => el("option", { value: y, selected: y === v }, y)));
  const desde = sel(a), hasta = sel(b);
  const aplicar = (x, y) => { cerrarDialogo(); irA(leerRuta().vista, { a: x === y ? String(x) : `${Math.min(x, y)}-${Math.max(x, y)}`, pagina: "" }); };
  const max = CAT.anioMax;
  const atajo = (texto, x, y) => el("button", { type: "button", class: "boton", onclick: () => aplicar(x, y) }, texto);
  abrirDialogo(el("div", { class: "anios" },
    el("div", { class: "segmentos" },
      atajo("Este año", max, max), atajo("Últimos 3", max - 2, max), atajo("Últimos 6", max - 5, max),
      atajo("Últimos 10", max - 9, max), atajo("Desde 2001", 2001, max), atajo("Guerra Fría (1946–1991)", 1946, 1991), atajo("Todo", CAT.anioMin, max)),
    el("div", { class: "filtros" }, el("label", {}, "Desde ", desde), el("label", {}, "Hasta ", hasta),
      el("button", { type: "button", class: "boton primario", onclick: () => aplicar(+desde.value, +hasta.value) }, "Aplicar")),
    el("p", { class: "muted small" }, `Cada país legisla por legislaturas distintas, así que todo se filtra por años naturales. La ONU tiene datos de 1946 a ${ONU_HASTA}; los parlamentos, desde el año de la tabla de cobertura.`)),
  "Años");
}

// ------------------------------------------------------------------ panel lateral de detalle

// enlace: lo que se añade a la URL para poder compartir el detalle ({v: id} o {par: "ESP-PSE"}).
function abrirPanel(contenido, enlaceUrl) {
  const panel = $("#panel");
  if (enlaceUrl) marcarEnUrl({ v: "", par: "", ...enlaceUrl });
  const copiar = enlaceUrl ? el("button", { type: "button", class: "boton copiar-enlace", title: "Copiar el enlace a este detalle",
    onclick: async (e) => {
      try { await navigator.clipboard.writeText(location.href); e.target.textContent = "Enlace copiado ✓"; }
      catch { e.target.textContent = "Copia la dirección de la barra"; }
    } }, "Copiar enlace") : null;
  panel.replaceChildren(el("div", { class: "panel-acciones" }, copiar, el("button", { class: "cerrar", onclick: () => cerrarPanel() }, "Cerrar ✕")), contenido);
  panel.classList.add("abierto");
  panel.setAttribute("aria-hidden", "false");
  $("#panelFondo").classList.add("abierto");
  panel.scrollTop = 0;
}
function cerrarPanel({ url = true } = {}) {
  const abierto = $("#panel").classList.contains("abierto");
  $("#panel").classList.remove("abierto");
  $("#panel").setAttribute("aria-hidden", "true");
  $("#panelFondo").classList.remove("abierto");
  const q = leerRuta().q;
  if (abierto && url && (q.v || q.par)) marcarEnUrl({ v: "", par: "" });
}

// ------------------------------------------------------------------ tooltip

const TT = () => $("#tooltip");
function tip(evt, valor, etiqueta, extra) {
  const t = TT();
  t.replaceChildren(el("div", { class: "tv" }, valor), etiqueta ? el("div", { class: "tl" }, etiqueta) : null,
    extra ? el("div", { class: "tl small" }, extra) : null);
  t.style.display = "block";
  const x = Math.min(evt.clientX + 14, window.innerWidth - t.offsetWidth - 8);
  const y = evt.clientY + 14 + t.offsetHeight > window.innerHeight ? evt.clientY - t.offsetHeight - 10 : evt.clientY + 14;
  t.style.left = `${Math.max(8, x)}px`;
  t.style.top = `${Math.max(8, y)}px`;
}
const tipOff = () => (TT().style.display = "none");
function conTip(nodo, valor, etiqueta, extra) {
  nodo.addEventListener("pointermove", (e) => tip(e, typeof valor === "function" ? valor() : valor, etiqueta, extra));
  nodo.addEventListener("pointerleave", tipOff);
  return nodo;
}

// ------------------------------------------------------------------ componentes

function stat(label, valor, nota) {
  return el("div", { class: "card stat" }, el("div", { class: "label" }, label), el("div", { class: "value" }, valor),
    nota ? el("div", { class: "nota" }, nota) : null);
}

// Selector desplegable con varias opciones (casillas). Se aplica al cerrar o con «Aplicar».
// unico: una sola opción (elegirla cierra el desplegable), con el mismo aspecto y buscador.
function multiSelect(nombre, opciones, valor, etiquetaVacia, plural = "seleccionados", { buscar = false, unico = false } = {}) {
  const elegidos = new Set(lista(valor));
  const textoDe = new Map(opciones.map(([v, t]) => [String(v), t]));
  const texto = el("span", { class: "ms-texto" });
  const det = el("details", { class: "ms", "data-nombre": nombre }, el("summary", { title: etiquetaVacia }, texto));
  const pintar = () => {
    const xs = [...elegidos];
    texto.textContent = !xs.length ? etiquetaVacia : xs.length === 1 ? textoDe.get(xs[0]) || xs[0]
      : xs.length === 2 ? xs.map((x) => textoDe.get(x) || x).join(" + ") : `${xs.length} ${plural}`;
    det.classList.toggle("activo", xs.length > 0);
  };
  const sinTildes = (s) => String(s).toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
  const cajas = opciones.map(([v, t]) => el("label", { class: "ms-op", "data-t": sinTildes(t) },
    el("input", { type: unico ? "radio" : "checkbox", name: unico ? `ms-${nombre}` : null, class: "ms-cb", value: v, checked: elegidos.has(String(v)),
      onchange: (e) => {
        if (unico) { elegidos.clear(); elegidos.add(String(v)); pintar(); det.open = false; return; }
        e.target.checked ? elegidos.add(String(v)) : elegidos.delete(String(v)); pintar();
      } }), t));
  const listaNodo = el("div", { class: "ms-lista" }, cajas);
  const filtro = buscar ? el("input", { type: "search", class: "ms-buscar", placeholder: "Buscar…",
    oninput: (e) => { const t = sinTildes(e.target.value); for (const c of cajas) c.style.display = c.dataset.t.includes(t) ? "" : "none"; } }) : null;
  det.append(el("div", { class: "ms-panel" },
    el("div", { class: "ms-titulo" }, etiquetaVacia),
    unico ? null : el("div", { class: "ms-acciones" },
      el("button", { type: "button", class: "boton", onclick: () => { for (const c of det.querySelectorAll(".ms-cb")) c.checked = false; elegidos.clear(); pintar(); } }, "Ninguno"),
      el("button", { type: "button", class: "boton", onclick: () => { det.open = false; } }, "Aplicar")),
    filtro, listaNodo));
  if (filtro) det.addEventListener("toggle", () => { if (det.open && !esMovil()) setTimeout(() => filtro.focus(), 30); });
  let aplicado = [...elegidos].sort().join(",");
  det.valor = () => [...elegidos].join(",");
  det.addEventListener("toggle", () => {
    if (det.open) { for (const o of document.querySelectorAll("details.ms[open]")) if (o !== det) o.open = false; return; }
    const ahora = [...elegidos].sort().join(",");
    if (ahora !== aplicado) { aplicado = ahora; det.dispatchEvent(new CustomEvent("ms-cambio", { bubbles: true, detail: { nombre, valor: det.valor() } })); }
  });
  pintar();
  return det;
}

// Fila de filtros: cada control lleva data-nombre; al cambiar, se llama a onCambio({nombre: valor}).
// En el móvil, con muchos controles, se pliegan tras un botón «Filtros» (con cuántos hay puestos).
function filaFiltros(controles, onCambio, { plegable = true } = {}) {
  const f = el("div", { class: "filtros" }, controles);
  const nodos = controles.flat(Infinity).filter(Boolean);
  if (plegable && nodos.length > 3) {
    const activos = nodos.filter((n) => (n.matches?.("details.ms.activo"))
      || (n.tagName === "SELECT" && n.value !== "" && !["n", "orden", "ref"].includes(n.dataset.nombre))
      || (n.matches?.("label.check") && n.querySelector("input")?.checked)).length;
    const boton = el("button", { type: "button", class: "boton filtros-boton", "aria-expanded": "false",
      onclick: () => { const d = f.classList.toggle("desplegado"); boton.setAttribute("aria-expanded", String(d)); } },
    "Filtros", activos ? el("span", { class: "cuenta" }, activos) : null);
    f.classList.add("plegable");
    f.prepend(boton);
  }
  const leer = (n) => {
    if (n.matches("details.ms")) return n.valor();
    if (n.type === "checkbox") return n.checked ? "1" : "";
    return n.value;
  };
  f.addEventListener("change", (e) => {
    const n = e.target.closest("[data-nombre]");
    if (n && !e.target.classList.contains("ms-cb") && e.target.type !== "search") onCambio({ [n.dataset.nombre]: leer(n) });
  });
  f.addEventListener("ms-cambio", (e) => onCambio({ [e.detail.nombre]: e.detail.valor }));
  f.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && e.target.type === "search") { e.preventDefault(); onCambio({ [e.target.dataset.nombre]: e.target.value }); }
  });
  f.addEventListener("search", (e) => onCambio({ [e.target.dataset.nombre]: e.target.value }));
  return f;
}
const selectFiltro = (nombre, opciones, valor) =>
  el("select", { "data-nombre": nombre }, opciones.map(([v, t]) => el("option", { value: v, selected: String(v) === String(valor ?? "") }, t)));
const checkFiltro = (nombre, texto, valor) =>
  el("label", { class: "check" }, el("input", { type: "checkbox", "data-nombre": nombre, checked: valor === "1" }), texto);
const buscarFiltro = (nombre, valor, placeholder) =>
  el("input", { type: "search", "data-nombre": nombre, value: valor || "", placeholder });

function segmentos(opciones, valor, onClic) {
  return el("div", { class: "segmentos", role: "group" }, opciones.map(([v, t]) =>
    el("button", { type: "button", class: "boton" + (String(v) === String(valor) ? " activo" : ""), "aria-pressed": String(String(v) === String(valor)),
      onclick: () => onClic(v) }, t)));
}

// Barras horizontales: [{etiqueta, valor, color, nota, onclick}]. Marca <= 14px con extremo redondeado.
function barrasH(items, { max, formato = fmt, alClicar } = {}) {
  const m = max ?? Math.max(1, ...items.map((i) => i.valor));
  return el("div", { class: "barrash" }, items.flatMap((i) => [
    el("div", { class: "bh-label", title: i.etiqueta }, i.etiqueta, i.nota ? el("span", { class: "muted small" }, " " + i.nota) : null),
    conTip(el("div", { class: "bh-pista" + (alClicar ? " clic" : ""), onclick: alClicar ? () => alClicar(i) : null },
      el("div", { class: "bh-barra", style: `width:${Math.max(1, (100 * i.valor) / m)}%;background:${i.color || "var(--accent)"}` }),
      el("b", {}, formato(i.valor))), formato(i.valor), i.etiqueta, i.tip),
  ]));
}

// Columnas por año (una serie). datos: [{x, y, tip}]. ancho: el del hueco donde va (el texto no se encoge).
// El año en curso va más claro y con asterisco: todavía no está completo.
function columnasAnio(datos, { alto = 160, ancho: anchoPedido = 900, formato = fmt, color = "var(--accent)" } = {}) {
  const ancho = anchoGrafico(anchoPedido), mi = 44, mb = 22, mt = 10;
  const { tope, marcas } = marcasBonitas(Math.max(1, ...datos.map((d) => d.y)));
  const bw = (ancho - mi) / Math.max(1, datos.length);
  const y = (v) => mt + (alto - mt - mb) * (1 - v / tope);
  const svg = svgEl("svg", { viewBox: `0 0 ${ancho} ${alto}`, role: "img" });
  for (const t of marcas) {
    svg.append(svgEl("line", { class: t ? "gridline" : "baseline", x1: mi, x2: ancho, y1: y(t), y2: y(t) }),
      svgEl("text", { x: mi - 6, y: y(t) + 4, "text-anchor": "end" }, formato(t)));
  }
  const paso = Math.ceil(datos.length / Math.floor((ancho - mi) / 40));
  let enCurso = false;
  datos.forEach((d, i) => {
    const x = mi + i * bw, h = y(0) - y(d.y), w = Math.max(1, bw - 4);
    const actual = +d.x === ANIO_ACTUAL;
    enCurso = enCurso || actual;
    const g = svgEl("g", {});
    if (d.y > 0) g.append(svgEl("path", { class: "mark", fill: color, "fill-opacity": actual ? 0.45 : 1,
      d: `M${x + 2},${y(0)} v${-Math.max(0, h - 4)} q0,-4 4,-4 h${Math.max(0, w - 8)} q4,0 4,4 v${Math.max(0, h - 4)} z` }));
    g.append(svgEl("rect", { class: "hit", x, y: mt, width: bw, height: alto - mt - mb }));
    conTip(g, formato(d.y), actual ? `${d.x} (año en curso)` : String(d.x), d.tip);
    if (i % paso === 0) svg.append(svgEl("text", { x: x + bw / 2, y: alto - 6, "text-anchor": "middle" }, actual ? `${d.x}*` : String(d.x)));
    svg.append(g);
  });
  return el("div", { class: "chart" }, svg,
    enCurso ? el("div", { class: "muted small nota-grafico" }, `* ${ANIO_ACTUAL}: año en curso, todavía incompleto.`) : null);
}

// Puntos sobre una escala recortada: para comparar valores muy parecidos (96 %, 97 %, 98 %) que en barras
// desde cero parecerían iguales. items: [{etiqueta, valor, color, tip, iso3}]
function puntosH(items, { min, max, formato = (v) => `${Math.round(v)} %`, alClicar, color = "var(--accent)" } = {}) {
  if (!items.length) return el("p", { class: "muted" }, "Sin datos.");
  const vs = items.map((i) => i.valor);
  const lo = min ?? Math.max(0, Math.floor((Math.min(...vs) - 1) / 5) * 5);
  const hi = max ?? Math.min(100, Math.ceil((Math.max(...vs) + 1) / 5) * 5);
  const pos = (v) => `${(100 * (v - lo)) / Math.max(1, hi - lo)}%`;
  return el("div", { class: "puntosh" },
    el("div", {}), el("div", { class: "ph-escala" }, el("span", {}, formato(lo)), el("span", {}, formato(hi))),
    items.flatMap((i) => [
      el("div", { class: "bh-label", title: i.etiqueta }, i.etiqueta),
      conTip(el("div", { class: "ph-pista" + (alClicar ? " clic" : ""), onclick: alClicar ? () => alClicar(i) : null },
        el("div", { class: "ph-linea", style: `width:${pos(i.valor)};background:${i.color || color}` }),
        el("div", { class: "ph-punto", style: `left:${pos(i.valor)};background:${i.color || color}` }),
        el("b", {}, formato(i.valor))), formato(i.valor), i.etiqueta, i.tip),
    ]));
}

// Líneas por año, varias series: series = [{nombre, color, puntos: [{x, y}]}]; y en 0-100.
function lineasAnio(series, { alto = 220, formato = (v) => `${Math.round(v)} %`, min = 0, max = 100 } = {}) {
  const ancho = anchoGrafico(900), mi = 40, mb = 22, mt = 10, md = 12;
  const xs = [...new Set(series.flatMap((s) => s.puntos.map((p) => p.x)))].sort((a, b) => a - b);
  if (!xs.length) return el("div", { class: "vacio" }, "Sin datos en esos años");
  const x0 = xs[0], x1 = xs[xs.length - 1] === x0 ? x0 + 1 : xs[xs.length - 1];
  const X = (v) => mi + ((ancho - mi - md) * (v - x0)) / (x1 - x0);
  const Y = (v) => mt + ((alto - mt - mb) * (max - v)) / (max - min);
  const svg = svgEl("svg", { viewBox: `0 0 ${ancho} ${alto}`, role: "img" });
  for (let t = min; t <= max; t += (max - min) / 4) {
    svg.append(svgEl("line", { class: t === min ? "baseline" : "gridline", x1: mi, x2: ancho - md, y1: Y(t), y2: Y(t) }),
      svgEl("text", { x: mi - 6, y: Y(t) + 4, "text-anchor": "end" }, formato(t)));
  }
  const paso = Math.ceil(xs.length / Math.floor((ancho - mi) / 46));
  xs.forEach((v, i) => { if (i % paso === 0) svg.append(svgEl("text", { x: X(v), y: alto - 6, "text-anchor": "middle" }, String(v))); });
  for (const s of series) {
    let d = "", seguido = false;
    const pts = [...s.puntos].sort((a, b) => a.x - b.x);
    pts.forEach((p, i) => {
      d += `${seguido && pts[i - 1].x === p.x - 1 ? "L" : "M"}${X(p.x).toFixed(1)},${Y(p.y).toFixed(1)}`;
      seguido = true;
    });
    svg.append(svgEl("path", { d, fill: "none", stroke: s.color, "stroke-width": 2, "stroke-linejoin": "round" }));
    for (const p of pts) if (pts.length < 40) svg.append(svgEl("circle", { cx: X(p.x), cy: Y(p.y), r: 3, fill: s.color }));
  }
  // Capa de lectura: línea vertical y valores del año bajo el puntero.
  const cruz = svgEl("line", { class: "baseline", y1: mt, y2: alto - mb, style: "display:none" });
  const capa = svgEl("rect", { class: "hit", x: mi, y: mt, width: ancho - mi - md, height: alto - mt - mb });
  svg.append(cruz, capa);
  capa.addEventListener("pointermove", (e) => {
    const r = svg.getBoundingClientRect();
    const vx = ((e.clientX - r.left) / r.width) * ancho;
    const anio = xs.reduce((a, b) => (Math.abs(X(b) - vx) < Math.abs(X(a) - vx) ? b : a), xs[0]);
    cruz.setAttribute("x1", X(anio)); cruz.setAttribute("x2", X(anio)); cruz.style.display = "";
    const valores = series.map((s) => [s.nombre, s.puntos.find((p) => p.x === anio)]).filter(([, p]) => p);
    tip(e, String(anio), valores.map(([n, p]) => `${n}: ${formato(p.y)}`).join(" · "));
  });
  capa.addEventListener("pointerleave", () => { cruz.style.display = "none"; tipOff(); });
  return el("div", { class: "chart" },
    el("div", { class: "legend" }, series.map((s) => el("span", {}, el("i", { style: `background:${s.color}` }), s.nombre))), svg);
}

function paginacion(total, pagina, tam, ir) {
  const paginas = Math.max(1, Math.ceil(total / tam));
  return el("div", { class: "paginacion" },
    el("button", { disabled: pagina <= 1, onclick: () => { SUBIR = true; ir(pagina - 1); } }, "‹ Anterior"),
    el("span", { class: "muted" }, `Página ${pagina} de ${fmt(paginas)} · ${fmt(total)} en total`),
    el("button", { disabled: pagina >= paginas, onclick: () => { SUBIR = true; ir(pagina + 1); } }, "Siguiente ›"));
}

// Barra de resultado: sí | abstención | no.
function barraVotos(v) {
  const t = (v.a_favor || 0) + (v.en_contra || 0) + (v.abstenciones || 0);
  if (!t) return el("div", { class: "muted small" }, "Sin totales");
  return el("div", {},
    el("div", { class: "barra" },
      el("span", { class: "si", style: `width:${(100 * (v.a_favor || 0)) / t}%` }),
      el("span", { class: "abs", style: `width:${(100 * (v.abstenciones || 0)) / t}%` }),
      el("span", { class: "no", style: `width:${(100 * (v.en_contra || 0)) / t}%` })),
    el("div", { class: "totales" }, el("span", {}, "Sí ", el("b", {}, fmt(v.a_favor))), el("span", {}, "Abst. ", el("b", {}, fmt(v.abstenciones))),
      el("span", {}, "No ", el("b", {}, fmt(v.en_contra)))));
}
function badgeResultado(r) {
  if (r === "aprobada" || r === "aprobado") return el("span", { class: "badge ok" }, el("span", { class: "ic" }, "✓"), r === "aprobado" ? "Aprobado" : "Aprobada");
  if (r === "rechazada" || r === "rechazado") return el("span", { class: "badge ko" }, el("span", { class: "ic" }, "✗"), r === "rechazado" ? "Rechazado" : "Rechazada");
  return null;
}
function chipRelacion(r, conPais = true) {
  const o = typeof r.orientacion === "string" ? ORIENTACION_TXT[r.orientacion] : r.orientacion;
  const [ic, txt] = ORIENTACION[o] || ORIENTACION[0];
  return el("span", { class: `chip rel rel${o}`, title: [txt, CAT.tiposRel[r.tipo], r.motivo].filter(Boolean).join(" · ") },
    el("span", { class: "s" }, ic), conPais ? nombrePais(r.pais || r.destino) : txt, r.tipo && r.tipo !== "otro" ? el("span", { class: "muted" }, " · " + (CAT.tiposRel[r.tipo] || r.tipo).toLowerCase()) : null);
}

// ------------------------------------------------------------------ vistas y render

const VISTAS = {};
let renderEnCurso = 0;
let VISTA_PINTADA = null;

async function render() {
  const yo = ++renderEnCurso;
  tipOff();
  const r = leerRuta();
  cerrarPanel({ url: false });
  const vista = VISTAS[r.vista] ? r.vista : "mundo";
  // Otra sección (o una página nueva de la lista): se empieza por arriba, no donde se quedó la anterior.
  const subir = vista !== VISTA_PINTADA || SUBIR;
  SUBIR = false;
  pintarCabecera();
  document.title = `Concordia · ${VISTAS[vista].titulo || ""}`;
  const main = $("#vista");
  const avisar = (texto) => { if (yo === renderEnCurso) main.replaceChildren(el("div", { class: "vacio" }, texto)); };
  try {
    if (VISTAS[vista].datos) await asegurar(VISTAS[vista].datos(r.q), avisar);
    if (yo !== renderEnCurso) return;
    const nodo = await VISTAS[vista].pintar(r.q);
    if (yo !== renderEnCurso) return;
    main.replaceChildren(nodo);
    VISTA_PINTADA = vista;
    if (subir) window.scrollTo(0, 0);
    // Enlace permanente a un detalle: se vuelve a abrir.
    if (r.q.v && typeof panelVotacion === "function") panelVotacion(r.q.v);
    else if (r.q.par && typeof panelArista === "function") {
      const [o, d] = r.q.par.split("-");
      if (CAT.paises[o] && CAT.paises[d]) panelArista(o, d, r.q);
    }
  } catch (e) {
    console.error(e);
    main.replaceChildren(el("div", { class: "vacio" }, "Error al pintar la vista: " + e.message));
  }
}
