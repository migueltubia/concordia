"use strict";

// ------------------------------------------------------------------ arranque

function iniciarTema() {
  const guardado = (() => { try { return localStorage.getItem("tema"); } catch { return null; } })();
  if (guardado) document.documentElement.dataset.theme = guardado;
  $("#toggleTema").addEventListener("click", () => {
    const oscuro = document.documentElement.dataset.theme ? document.documentElement.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
    document.documentElement.dataset.theme = oscuro ? "light" : "dark";
    try { localStorage.setItem("tema", document.documentElement.dataset.theme); } catch { /* sin almacenamiento */ }
    render(); // los colores del mapa salen de variables CSS, pero los gráficos se redibujan igual
  });
}

(async function () {
  iniciarTema();
  $("#vista").replaceChildren(el("div", { class: "vacio" }, "Abriendo la base de datos…"));
  try {
    await abrirBase();
  } catch (e) {
    $("#vista").replaceChildren(el("div", { class: "vacio" }, "No se pudo abrir la base de datos: " + e.message));
    return;
  }
  $("#panelFondo").addEventListener("click", cerrarPanel);
  $("#dialogoFondo").addEventListener("click", cerrarDialogo);
  $("#botonPais").addEventListener("click", abrirSelectorPais);
  $("#botonAnios").addEventListener("click", abrirSelectorAnios);
  document.addEventListener("click", (e) => {
    for (const d of document.querySelectorAll("details.ms[open]")) if (!d.contains(e.target)) d.open = false;
  });
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    for (const d of document.querySelectorAll("details.ms[open]")) d.open = false;
    cerrarPanel();
    cerrarDialogo();
  });
  window.addEventListener("hashchange", () => render()); // render cierra el detalle y lo reabre si la URL lo pide
  // Al pasar de móvil a escritorio (o al girar el teléfono) se redibuja con el nuevo tamaño.
  MQ_MOVIL.addEventListener("change", () => { document.documentElement.classList.toggle("movil", esMovil()); render(); });
  let ancho = window.innerWidth, espera = null;
  window.addEventListener("resize", () => {
    clearTimeout(espera);
    espera = setTimeout(() => { if (Math.abs(window.innerWidth - ancho) > 80) { ancho = window.innerWidth; render(); } }, 300);
  });
  window.addEventListener("scroll", tipOff, { passive: true });
  render();
})();
