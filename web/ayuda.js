"use strict";

// ------------------------------------------------------------------ Ayuda

// Qué publica cada parlamento, según «Votaciones parlamentarias en el mundo: qué datos hay por país»
// (septiembre de 2026). Solo los países sin conector todavía; dificultad de 1 (API o descarga masiva) a 5.
const DISPONIBILIDAD = {
  SWE: { voto: "voto nominal (solo votaciones con recuento)", fuente: "data.riksdagen.se, XML/JSON/CSV desde 1993", dificultad: "1" },
  IRL: { voto: "voto nominal en el Dáil y el Seanad", fuente: "API del Oireachtas, JSON", dificultad: "1" },
  FRA: { voto: "voto nominal en los scrutins publics; nada en mano alzada", fuente: "datos abiertos de la Asamblea Nacional, JSON/XML", dificultad: "1-2" },
  NLD: { voto: "voto por grupo, a veces nominal", fuente: "OData de la Tweede Kamer, desde 2008", dificultad: "1 (por grupo)" },
  CZE: { voto: "voto nominal", fuente: "ZIP diarios del Parlamento, desde 1993", dificultad: "2" },
  DNK: { voto: "voto nominal", fuente: "API OData oda.ft.dk", dificultad: "2" },
  EST: { voto: "voto nominal", fuente: "API del Riigikogu, desde 2012", dificultad: "2" },
  SVN: { voto: "voto nominal", fuente: "dataset de votaciones en XML, desde 2000", dificultad: "2" },
  FIN: { voto: "voto nominal", fuente: "API del Eduskunta, JSON", dificultad: "2" },
  LUX: { voto: "voto nominal", fuente: "data.public.lu, CSV/XML", dificultad: "2" },
  ITA: { voto: "voto nominal en la Cámara y el Senado", fuente: "dati.camera.it y dati.senato.it (bloqueaban la lectura automática)", dificultad: "2" },
  DEU: { voto: "voto por grupo; nominal solo en votaciones nominales", fuente: "listas del Bundestag en XLSX y API DIP; abgeordnetenwatch", dificultad: "2-3" },
  PRT: { voto: "voto por grupo", fuente: "datos abiertos del Parlamento, JSON/XML", dificultad: "2" },
  AUT: { voto: "voto por grupo; nominal muy rara vez", fuente: "API de datos abiertos del Parlamento", dificultad: "3" },
  HUN: { voto: "voto nominal", fuente: "parlament.hu (API limitada); Parlamonitor", dificultad: "3" },
  ROU: { voto: "voto nominal en la Cámara y el Senado", fuente: "páginas HTML por votación", dificultad: "3" },
  SVK: { voto: "voto nominal", fuente: "HTML en nrsr.sk y API desde 2023", dificultad: "3" },
  LTU: { voto: "voto nominal", fuente: "servicio XML en lrs.lt (bloqueado)", dificultad: "3" },
  LVA: { voto: "voto nominal", fuente: "titania.saeima.lv y dataset 2016-2019", dificultad: "3-4" },
  BEL: { voto: "voto nominal", fuente: "anexo de votos del acta, HTML/PDF", dificultad: "4" },
  BGR: { voto: "voto nominal y por grupo", fuente: "junto a las actas en parliament.bg", dificultad: "4" },
  GRC: { voto: "voto por declaración de grupo", fuente: "actas en PDF/DOC", dificultad: "4-5" },
  MLT: { voto: "viva voz; divisiones raras", fuente: "actas, sin datos abiertos", dificultad: "4-5" },
  HRV: { voto: "solo totales", fuente: "actas del Sabor", dificultad: "5" },
  CYP: { voto: "mano alzada", fuente: "sin datos", dificultad: "5" },
  CHE: { voto: "voto nominal", fuente: "OData del Parlamento, desde 2007", dificultad: "2" },
  NOR: { voto: "voto nominal", fuente: "data.stortinget.no, XML desde 2011", dificultad: "2" },
  CAN: { voto: "voto nominal", fuente: "ourcommons.ca en XML/CSV y openparliament.ca, desde 2004", dificultad: "2" },
  UKR: { voto: "voto nominal", fuente: "dataset de la Rada y rada4you, desde 2001", dificultad: "2-3" },
  ISL: { voto: "voto nominal", fuente: "XML del Althingi (bloqueado)", dificultad: "2-3" },
  AUS: { voto: "voto nominal en divisiones", fuente: "TheyVoteForYou, API JSON con clave, desde 2006", dificultad: "3" },
  NZL: { voto: "voto por partido; nominal solo en votos de conciencia", fuente: "Hansard", dificultad: "4" },
  SRB: { voto: "voto nominal en un proyecto cívico", fuente: "Otvoreni Parlament, sin API", dificultad: "4" },
  GEO: { voto: "probablemente nominal", fuente: "resultados por sesión cargados con JavaScript", dificultad: "4" },
  TUR: { voto: "mano alzada; nominal solo en algunas votaciones", fuente: "actas, sin datos abiertos", dificultad: "5" },
  MDA: { voto: "sin verificar", fuente: "sin datos abiertos de votaciones", dificultad: "4-5" },
  ALB: { voto: "sin verificar", fuente: "sin datos abiertos de votaciones", dificultad: "4-5" },
  MKD: { voto: "sin verificar", fuente: "sin datos abiertos de votaciones", dificultad: "4-5" },
  BIH: { voto: "sin verificar", fuente: "sin datos abiertos de votaciones", dificultad: "4-5" },
  MNE: { voto: "sin verificar", fuente: "sin datos abiertos de votaciones", dificultad: "4-5" },
  RUS: { voto: "voto nominal (técnicamente); parlamento no competitivo", fuente: "API de la Duma, inaccesible desde fuera", dificultad: "2-3, relevancia baja" },
  BLR: { voto: "nada; parlamento no competitivo", fuente: "—", dificultad: "excluido" },
  BRA: { voto: "voto nominal y orientación de bancada en la Cámara y el Senado", fuente: "API de la Câmara y servicios del Senado", dificultad: "1" },
  CHL: { voto: "voto nominal en la Cámara y el Senado", fuente: "servicios SOAP/XML; libre-camara", dificultad: "2" },
  ARG: { voto: "voto nominal", fuente: "dataset de Diputados; actas PDF del Senado", dificultad: "2 (Diputados), 3 (Senado)" },
  MEX: { voto: "voto nominal en Diputados", fuente: "SITL en HTML por legislatura", dificultad: "3" },
  CRI: { voto: "voto nominal a través de un medio", fuente: "Delfino.cr, desde 2018", dificultad: "3" },
  GTM: { voto: "probablemente nominal", fuente: "páginas por votación (bloqueadas)", dificultad: "3" },
  ECU: { voto: "sin verificar", fuente: "portal dinámico de votaciones", dificultad: "3" },
  PRY: { voto: "sin verificar", fuente: "API de SILpy", dificultad: "3-4" },
  COL: { voto: "voto nominal por ley desde 2011", fuente: "Cámara por sesión; Senado en actas PDF; Congreso Visible", dificultad: "4" },
  PER: { voto: "voto nominal y por grupo", fuente: "PDF escaneados del pleno", dificultad: "4" },
  URY: { voto: "voto nominal en los diarios de sesiones", fuente: "datos abiertos sin votaciones", dificultad: "4" },
  PAN: { voto: "sin verificar", fuente: "actas y decretos en PDF", dificultad: "4" },
  SLV: { voto: "sin verificar", fuente: "actas y decretos en PDF", dificultad: "4" },
  DOM: { voto: "sin verificar", fuente: "actas y decretos en PDF", dificultad: "4" },
  BOL: { voto: "nada encontrado", fuente: "proyectos en PDF", dificultad: "5" },
  HND: { voto: "mano alzada", fuente: "sistema electrónico sin funcionar", dificultad: "5" },
  VEN: { voto: "unanimidad; parlamento no competitivo", fuente: "solo interesan los textos", dificultad: "excluido" },
  NIC: { voto: "unanimidad; parlamento no competitivo", fuente: "solo interesan los textos", dificultad: "excluido" },
  CUB: { voto: "unanimidad; parlamento no competitivo", fuente: "solo interesan los textos", dificultad: "excluido" },
  KOR: { voto: "voto nominal", fuente: "API de la Asamblea Nacional, con clave gratuita", dificultad: "1-2" },
  ISR: { voto: "voto nominal", fuente: "API OData de la Knesset", dificultad: "2" },
  TWN: { voto: "voto nominal en votaciones registradas", fuente: "Gaceta del Yuan Legislativo y ly.govapi.tw", dificultad: "2-3" },
  JPN: { voto: "voto nominal en la Cámara de Consejeros; por partido en la de Representantes", fuente: "HTML del Senado y datos de SmartNews", dificultad: "3" },
  THA: { voto: "voto nominal", fuente: "PDF oficiales pasados a datos por WeVis", dificultad: "3" },
  ZAF: { voto: "voto por partido; nominal en divisiones", fuente: "actas del Parlamento y PMG", dificultad: "3" },
  PHL: { voto: "voto nominal en tercera lectura", fuente: "journals en PDF/HTML", dificultad: "3-4" },
  KEN: { voto: "voto nominal en divisiones", fuente: "Hansard en PDF; Mzalendo", dificultad: "3-4" },
  TUN: { voto: "voto nominal en 2014-2021", fuente: "Marsad Majles (Al Bawsala)", dificultad: "3" },
  MYS: { voto: "viva voz; nominal en divisiones", fuente: "Hansard en PDF", dificultad: "4" },
  MAR: { voto: "totales y a veces por grupo", fuente: "web de la Cámara", dificultad: "4" },
  IDN: { voto: "consenso; posición de cada facción", fuente: "proyectos en PDF", dificultad: "4-5" },
  IND: { voto: "viva voz; menos de 50 divisiones por legislatura", fuente: "textos en inglés bien seguidos por PRS", dificultad: "5 (votos), 1 (textos)" },
  PAK: { voto: "viva voz, totales o nada", fuente: "actas en PDF", dificultad: "5" },
  BGD: { voto: "viva voz; la Constitución prohíbe votar contra el partido", fuente: "actas en PDF", dificultad: "5" },
  NGA: { voto: "viva voz, totales o nada", fuente: "actas en PDF", dificultad: "5" },
  GHA: { voto: "viva voz, totales o nada", fuente: "actas en PDF", dificultad: "5" },
  EGY: { voto: "viva voz, totales o nada", fuente: "actas en PDF", dificultad: "5" },
  CHN: { voto: "totales; parlamento no competitivo", fuente: "NPC Observer recoge los totales", dificultad: "excluido" },
  IRN: { voto: "totales o nada; no competitivo", fuente: "—", dificultad: "excluido" },
  SAU: { voto: "consultivo", fuente: "—", dificultad: "excluido" },
  ARE: { voto: "consultivo", fuente: "—", dificultad: "excluido" },
  QAT: { voto: "consultivo", fuente: "—", dificultad: "excluido" },
  KWT: { voto: "totales o nada", fuente: "—", dificultad: "excluido" },
  BHR: { voto: "totales o nada", fuente: "—", dificultad: "excluido" },
  OMN: { voto: "consultivo", fuente: "—", dificultad: "excluido" },
  ETH: { voto: "totales o nada; no competitivo", fuente: "—", dificultad: "excluido" },
};

VISTAS.ayuda = {
  titulo: "Ayuda",
  pintar: pintarAyuda,
};

function pintarAyuda(qq) {
  const secciones = [
    ["que", "Qué es"], ["mapa", "Cómo se lee el mapa"], ["fuentes", "Fuentes y cobertura"], ["calculo", "Cómo se calcula"],
    ["paises", "Qué datos hay de cada país"], ["actualizar", "Actualización"], ["limites", "Limitaciones"]];
  const ir = (id) => { const n = document.getElementById("ay-" + id); if (n) n.scrollIntoView({ behavior: "smooth" }); };
  const cobertura = Object.values(CAT.fuentes).filter((f) => f.votaciones).map((f) => {
    const filas = CAT.cobertura.filter((c) => c.fuente === f.codigo);
    const suma = (k) => filas.reduce((s, c) => s + (c[k] || 0), 0);
    return el("tr", {}, el("td", {}, f.nombre), el("td", {}, `${f.anio_min}–${f.anio_max}`), el("td", { class: "num" }, fmt(f.votaciones)),
      el("td", { class: "num" }, fmt(suma("asuntos"))), el("td", { class: "num" }, `${pct(suma("fichas_ia"), suma("asuntos"))} %`),
      el("td", { class: "num" }, fmt(suma("relaciones"))), el("td", {}, f.detalle === "estado" ? "voto de cada Estado" : f.detalle === "nominal" ? "voto de cada legislador" : f.detalle),
      el("td", { class: "small" }, f.licencia, " · ", enlace(f.web, "web")));
  });
  const avisos = Object.entries(INDICE().avisos || {});
  const buscador = el("input", { type: "search", placeholder: "Buscar país…", class: "pais-buscar" });
  const filasPaises = Object.entries(DISPONIBILIDAD).map(([iso3, d]) => ({ iso3, nombre: nombrePais(iso3), ...d }))
    .sort((a, b) => a.nombre.localeCompare(b.nombre, "es"));
  const cuerpo = el("tbody");
  const pintarPaises = () => {
    const t = buscador.value.trim().toLowerCase();
    cuerpo.replaceChildren(...filasPaises.filter((p) => !t || p.nombre.toLowerCase().includes(t)).map((p) =>
      el("tr", {}, el("td", {}, p.nombre), el("td", {}, p.voto), el("td", {}, p.fuente), el("td", {}, p.dificultad))));
  };
  buscador.addEventListener("input", pintarPaises);
  pintarPaises();
  const nodo = el("div", { class: "ayuda" },
    el("h2", {}, "Ayuda"),
    el("div", { class: "subnav" }, secciones.map(([id, t]) => el("a", { onclick: () => ir(id) }, t))),
    el("section", { class: "ayuda-seccion card", id: "ay-que" }, el("h3", {}, "Qué es"),
      el("p", {}, "Concordia reúne votaciones parlamentarias de varios países y el voto de cada Estado en la Asamblea General de la ONU, con una ficha de cada asunto votado (resumen neutro, tema y qué otros países son objeto del asunto y en qué sentido). Es la versión mundial de ", enlace("https://migueltubia.github.io/escrutinio/", "Escrutinio"), ", que hace lo mismo con el Congreso y las instituciones españolas; de España aquí solo se usa el Congreso."),
      el("p", {}, "Tiene dos partes: el mapa de relaciones entre países (pestaña Mundo) y las vistas de cada país (Resumen, Votaciones, Partidos y En la ONU), que usan el país y los años elegidos en la cabecera. Todo se filtra por años naturales: cada país tiene legislaturas distintas.")),
    el("section", { class: "ayuda-seccion card", id: "ay-mapa" }, el("h3", {}, "Cómo se lee el mapa"),
      el("ul", {},
        el("li", {}, el("b", {}, "Una flecha de A a B"), " reúne lo que A ha votado sobre B en esos años: los asuntos aprobados por el parlamento de A que tratan de B (vía «leyes») y el voto de A en las resoluciones de la ONU sobre B (vía «ONU»)."),
        el("li", {}, el("b", {}, "El color es el saldo"), ": azul si casi todo es positivo (acuerdos, ayuda, cooperación, reconocimiento, votar a favor de B en la ONU), rojo si casi todo es negativo (sanciones, condenas, restricciones, votar contra B), gris si está repartido o es neutro. El grosor, cuántos asuntos o votos hay."),
        el("li", {}, el("b", {}, "Origen y destino"), ": se eligen en los filtros o pulsando países en el mapa (el botón «Al pulsar un país» dice qué hace el clic). Sin origen ni destino se dibujan las relaciones más frecuentes del mundo."),
        el("li", {}, el("b", {}, "Afinidad en la ONU"), ": colorea cada país según cuánto coincide su voto con el del país de referencia y dibuja flechas hacia los más y los menos afines."),
        el("li", {}, "Pulsa una flecha o una fila de la tabla para ver los asuntos que hay detrás, con su resumen, su enlace a la fuente y quién decidió la orientación (la IA o las reglas)."),
        el("li", {}, el("b", {}, "Línea de tiempo"), ": debajo del mapa, «Todo el periodo» suma todos los años elegidos; «Año a año» enseña uno solo y «Acumulado», desde el primero hasta el elegido. El botón ▶ lo reproduce. Las barras dicen cuántas relaciones positivas, neutras y negativas hay cada año, y el grosor de las flechas es comparable entre años."),
        el("li", {}, el("b", {}, "El mapa se centra en el origen"), " (o en el país de referencia) para que las flechas vayan por el camino corto: desde EEUU, Asia queda a la izquierda. «Mapa fijo» lo deja con Europa en el centro."),
        el("li", {}, "La rueda del ratón amplía y reduce donde está el puntero; doble clic amplía (con Mayúsculas, reduce); en el móvil, pellizca. Arrastra para moverte. Al pasar por un país o una flecha se resaltan sus relaciones."))),
    el("section", { class: "ayuda-seccion card", id: "ay-fuentes" }, el("h3", {}, "Fuentes y cobertura"),
      el("div", { class: "tabla-scroll" }, el("table", { class: "tabla" },
        el("thead", {}, el("tr", {}, ["Fuente", "Años", "Votaciones", "Asuntos", "Con ficha IA", "Relaciones", "Detalle", "Licencia"].map((t) => el("th", {}, t)))),
        el("tbody", {}, cobertura))),
      avisos.length ? el("div", { class: "aviso-lectura" }, el("b", {}, "Fuentes que no se pudieron actualizar en la última recogida: "),
        avisos.map(([f, a]) => el("div", {}, `${CAT.fuentes[f]?.corto || f}: ${a.motivo === "bloqueada" ? "la web responde con un reto anti-robots, que no se intenta saltar" : a.detalle} (últimos datos: ${fecha(a.ultimos_datos)}).`))) : null,
      el("p", {}, el("b", {}, "ONU. "), "Hasta septiembre de 2023, el dataset de Erik Voeten y otros (Harvard Dataverse, CC0), con el voto de cada Estado en cada votación registrada desde 1946. El fichero oficial y actualizado de la Biblioteca Digital de la ONU está detrás de un reto anti-robots: se puede descargar a mano y la actualización lo importa (ver el README)."),
      el("p", {}, el("b", {}, "EEUU. "), "Voteview (UCLA): cada votación nominal de la Cámara y el Senado desde 2001. ", el("b", {}, "Reino Unido. "), "Commons Votes API: divisiones de los Comunes desde 2016. ", el("b", {}, "Polonia. "), "API del Sejm: legislaturas IX y X (desde 2019). ", el("b", {}, "España. "), "El Congreso tal como lo recoge Escrutinio, con sus fichas, desde 2011.")),
    el("section", { class: "ayuda-seccion card", id: "ay-calculo" }, el("h3", {}, "Cómo se calcula"),
      el("ul", {},
        el("li", {}, el("b", {}, "Votación decisiva"), ": la votación final de cada asunto en cada cámara (paso de un proyecto, votación de conjunto, resolución). Las listas y la relación entre países usan esa; las enmiendas y los trámites se ven al abrir un asunto."),
        el("li", {}, el("b", {}, "Ficha"), ": resumen neutro en español, tema (23 temas cerrados, los mismos de Escrutinio) y relaciones con otros países, hechos por una IA (DeepSeek) solo a partir del título y los metadatos, sin ver votos ni resultados, y validados contra listas cerradas. Mientras no hay ficha de la IA se usan reglas: tema por palabras clave (o los temas del dataset de la ONU) y países nombrados en el título, con orientación por palabras como «sanctions», «agreement», «condena», «convenio»… La ficha dice siempre de dónde sale."),
        el("li", {}, el("b", {}, "Relación por ley"), ": asuntos del parlamento del país de origen cuya ficha nombra otro país, con la orientación del asunto hacia él. Por defecto solo cuentan los aprobados en su votación decisiva (en EEUU, en al menos una cámara)."),
        el("li", {}, el("b", {}, "Relación por la ONU"), ": en cada resolución sobre un país, votar sí a una resolución negativa para él (por ejemplo, sobre la situación de los derechos humanos en su territorio) cuenta como relación negativa; votar no, como positiva. Las abstenciones y ausencias no cuentan."),
        el("li", {}, el("b", {}, "Afinidad en la ONU"), ": en las votaciones finales de cada año, 1 punto si dos Estados votan igual, medio si uno se abstiene y el otro no, 0 si votan lo contrario; las ausencias no cuentan. Es la medida habitual en los estudios sobre la Asamblea."),
        el("li", {}, el("b", {}, "Afinidad entre partidos"), ": porcentaje de votaciones (salvo trámites) en que dos partidos adoptan la misma posición, que es la de al menos dos tercios de sus miembros; si no la hay, el partido está dividido."))),
    el("section", { class: "ayuda-seccion card", id: "ay-paises" }, el("h3", {}, "Qué datos hay de cada país"),
      el("p", {}, "Resumen del estudio de fuentes que acompaña al proyecto: qué detalle de voto publica cada parlamento y lo difícil que es sacarlo (1: API o descarga masiva; 5: no hay datos o hay que leer PDF escaneados). Son los candidatos a los próximos conectores. Los parlamentos no competitivos solo interesan por el texto de sus leyes."),
      buscador, el("div", { class: "tabla-scroll" }, el("table", { class: "tabla" },
        el("thead", {}, el("tr", {}, el("th", {}, "País"), el("th", {}, "Voto que publica"), el("th", {}, "Fuente"), el("th", {}, "Dificultad"))), cuerpo))),
    el("section", { class: "ayuda-seccion card", id: "ay-actualizar" }, el("h3", {}, "Actualización"),
      el("p", {}, `Cada día, GitHub Actions trae las votaciones nuevas de cada fuente, hace las fichas de lo nuevo con la IA, recalcula relaciones y afinidades y publica la web. Datos generados el ${fecha(INDICE().generado)}.`)),
    el("section", { class: "ayuda-seccion card", id: "ay-limites" }, el("h3", {}, "Limitaciones"),
      el("ul", {},
        el("li", {}, "Pocos parlamentos todavía: la relación «por ley» solo existe como origen para los países con conector. El resto aparece como destino y en la ONU."),
        el("li", {}, "La ONU llega hasta septiembre de 2023 mientras la fuente oficial no deje descargar los datos a programas."),
        el("li", {}, "Solo cuenta lo que se vota con votación registrada: lo que se aprueba por consenso o a mano alzada no aparece (en la ONU, la mayoría de las resoluciones se adoptan sin votación)."),
        el("li", {}, "La orientación sale del título del asunto: la IA puede equivocarse con títulos poco informativos y las reglas solo ven lo que el título dice. Cada relación dice quién la decidió y enlaza al texto oficial."),
        el("li", {}, "Los títulos de Polonia están en polaco: sin ficha de la IA no tienen relaciones."),
        el("li", {}, "Un voto en la ONU o una ley no es toda la relación entre dos países: es lo que queda registrado en votaciones."))));
  if (qq.sec) setTimeout(() => ir(qq.sec), 50);
  return nodo;
}
