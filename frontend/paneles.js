// Paneles del personal. Se carga después de app.js y reutiliza su cliente:
// api(), escapeHtml(), humanDateTime(), showToast(), handleExpiredSession() y state.

const PANEL_POLL_MS = 5000;
const STAFF_ROLES = ["administrador", "operador"];

Object.assign(adminTitles, {
  rastreo: "Rastreo de la flota",
});

function injectPanelStyles() {
  if (document.getElementById("tx-panels-styles")) return;

  const style = document.createElement("style");
  style.id = "tx-panels-styles";
  style.textContent = `
    .admin-nav [hidden]{display:none!important}
    .dot.tx-dot-off{background:var(--danger)}
    .tx-chip-danger{background:#fde8e8;color:#a33232}
    .tx-fleet-legend{display:flex;gap:14px;align-items:center;flex-wrap:wrap;font-size:12px;font-weight:600}
    .tx-fleet-legend small{color:var(--muted);font-weight:500}
    .tx-fleet-map{height:460px;border:1px solid var(--line);border-radius:14px;margin-bottom:18px;isolation:isolate;background:var(--bg)}
    .tx-panel-error{margin-bottom:14px}
    .tx-popup{display:grid;gap:3px;font-family:Inter,system-ui,sans-serif;font-size:12px}
    .tx-popup small{color:var(--muted)}
    @media(max-width:760px){.tx-fleet-map{height:340px}}
  `;
  document.head.appendChild(style);
}

injectPanelStyles();

// ---------------------------------------------------------
// Utilidades compartidas por los paneles
// ---------------------------------------------------------

function userHasRole(roles) {
  return roles.includes(state.user?.rol);
}

// Recorre todas las páginas de una lista (la API devuelve máximo 100 por página).
async function fetchAllPages(path, maxPages = 20) {
  const items = [];
  const separator = path.includes("?") ? "&" : "?";
  let page = 1;
  let pages = 1;

  do {
    const data = await api(`${path}${separator}tamano=100&pagina=${page}`, { auth: true });
    items.push(...(data.elementos || []));
    pages = data.paginas || 1;
    page += 1;
  } while (page <= pages && page <= maxPages);

  return items;
}

// El mensaje ya trae la causa y la acción que manda el backend (apiErrorMessage en app.js).
function panelErrorMessage(error) {
  if (error instanceof TypeError) {
    return `No se pudo conectar con el backend en ${API_BASE}. Verifica que la API esté encendida e inténtalo de nuevo.`;
  }
  return error.message;
}

function showPanelError(element, error) {
  if (!element) return;
  element.textContent = panelErrorMessage(error);
  element.hidden = false;
}

function hidePanelError(element) {
  if (element) element.hidden = true;
}

function isAdminTabVisible(tab) {
  return document.getElementById("view-admin")?.classList.contains("active")
    && document.querySelector(`[data-admin-content="${tab}"]`)?.classList.contains("active");
}

// Oculta las pestañas que el rol no puede usar y reanuda la pestaña activa.
function syncPanelTabs() {
  document.querySelectorAll(".admin-nav [data-roles]").forEach(btn => {
    btn.hidden = !btn.dataset.roles.split(",").includes(state.user?.rol);
  });

  const active = document.querySelector(".admin-nav [data-admin-tab].active");
  if (active?.hidden) {
    document.querySelector('.admin-nav [data-admin-tab="resumen"]')?.click();
  } else if (active) {
    onPanelTabShown(active.dataset.adminTab);
  }
}

// app.js lo llama cada vez que se cambia de pestaña en el panel.
function onPanelTabShown(tab) {
  if (tab === "rastreo") startFleetMap();
  else stopFleetMap();
}

// ---------------------------------------------------------
// Mapa de la flota (HU-08): GET /rastreo/flota cada 5 segundos
// ---------------------------------------------------------

const BUCARAMANGA = [7.1193, -73.1227];

const fleetMap = {
  map: null,
  markers: new Map(),
  timer: null,
  generation: 0,
  fitted: false,
};

function signalLabel(signal) {
  return ({
    en_linea: "En línea",
    sin_senal: "Sin señal",
    sin_datos: "Sin datos",
  })[signal] || signal;
}

function signalChipClass(signal) {
  if (signal === "en_linea") return "active-chip";
  if (signal === "sin_senal") return "tx-chip-danger";
  return "inactive-chip";
}

function signalColor(signal) {
  const css = getComputedStyle(document.documentElement);
  const variable = signal === "en_linea" ? "--brand" : "--danger";
  return css.getPropertyValue(variable).trim() || (signal === "en_linea" ? "#16a36a" : "#d84c4c");
}

function lastReportText(vehicle) {
  if (!vehicle.posicion) return "Nunca ha reportado";
  const seconds = vehicle.segundos_sin_reportar;
  if (seconds != null && seconds < 120) return `Hace ${seconds} s`;
  return humanDateTime(vehicle.posicion.recibido_en);
}

function fleetPopup(vehicle) {
  const p = vehicle.posicion;
  const details = [
    p.velocidad_kmh != null ? `${escapeHtml(Number(p.velocidad_kmh).toFixed(1))} km/h` : null,
    p.nivel_bateria != null ? `Batería ${escapeHtml(p.nivel_bateria)}%` : null,
    p.precision_metros != null ? `±${escapeHtml(Number(p.precision_metros).toFixed(0))} m` : null,
  ].filter(Boolean).join(" · ");

  return `
    <div class="tx-popup">
      <strong>${escapeHtml(vehicle.codigo)}</strong>
      <span>${escapeHtml(vehicle.modelo?.nombre || "Modelo")} · ${escapeHtml(vehicle.estado.replaceAll("_", " "))}</span>
      <span>Señal: ${escapeHtml(signalLabel(vehicle.senal))}</span>
      ${details ? `<span>${details}</span>` : ""}
      <small>Último reporte: ${escapeHtml(lastReportText(vehicle))}</small>
    </div>
  `;
}

function ensureFleetMap() {
  if (fleetMap.map) return true;

  const container = document.getElementById("txFleetMap");
  if (typeof L === "undefined") {
    showPanelError(document.getElementById("txFleetError"), new Error(
      "No se pudo cargar la librería del mapa (Leaflet). Revisa tu conexión a internet y recarga la página."
    ));
    return false;
  }

  fleetMap.map = L.map(container).setView(BUCARAMANGA, 13);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  }).addTo(fleetMap.map);
  return true;
}

function startFleetMap() {
  if (!userHasRole(STAFF_ROLES)) return;
  if (!ensureFleetMap()) return;

  // El contenedor estaba oculto: Leaflet necesita recalcular su tamaño.
  setTimeout(() => fleetMap.map?.invalidateSize(), 0);

  if (fleetMap.timer !== null) return;
  pollFleet(++fleetMap.generation);
}

function stopFleetMap() {
  fleetMap.generation += 1;
  clearTimeout(fleetMap.timer);
  fleetMap.timer = null;
}

async function pollFleet(generation) {
  if (generation !== fleetMap.generation) return;
  if (!state.token || !isAdminTabVisible("rastreo")) {
    stopFleetMap();
    return;
  }

  // Marca el ciclo como activo antes de esperar la respuesta.
  fleetMap.timer = 0;
  const errorBox = document.getElementById("txFleetError");

  if (!document.hidden) {
    try {
      const vehicles = await fetchAllPages("/rastreo/flota");
      if (generation !== fleetMap.generation) return;
      renderFleet(vehicles);
      hidePanelError(errorBox);
    } catch (error) {
      if (generation !== fleetMap.generation) return;
      if (error.status === 401) {
        stopFleetMap();
        handleExpiredSession();
        return;
      }
      // Se conservan las últimas posiciones y se sigue intentando.
      showPanelError(errorBox, error);
      if (error.status === 403) {
        stopFleetMap();
        return;
      }
    }
  }

  fleetMap.timer = setTimeout(() => pollFleet(generation), PANEL_POLL_MS);
}

function renderFleet(vehicles) {
  const seen = new Set();
  const withPosition = vehicles.filter(v => v.posicion);

  withPosition.forEach(vehicle => {
    const latLng = [Number(vehicle.posicion.latitud), Number(vehicle.posicion.longitud)];
    const color = signalColor(vehicle.senal);
    const style = {
      radius: 9,
      color,
      fillColor: color,
      fillOpacity: vehicle.senal === "en_linea" ? 0.85 : 0.45,
      weight: 2,
      dashArray: vehicle.senal === "en_linea" ? null : "4 3",
    };

    let marker = fleetMap.markers.get(vehicle.vehiculo_id);
    if (marker) {
      marker.setLatLng(latLng).setStyle(style);
      marker.setPopupContent(fleetPopup(vehicle));
    } else {
      marker = L.circleMarker(latLng, style).bindPopup(fleetPopup(vehicle)).addTo(fleetMap.map);
      fleetMap.markers.set(vehicle.vehiculo_id, marker);
    }
    seen.add(vehicle.vehiculo_id);
  });

  fleetMap.markers.forEach((marker, id) => {
    if (!seen.has(id)) {
      marker.remove();
      fleetMap.markers.delete(id);
    }
  });

  if (!fleetMap.fitted && withPosition.length) {
    const bounds = L.latLngBounds(withPosition.map(v => [Number(v.posicion.latitud), Number(v.posicion.longitud)]));
    fleetMap.map.fitBounds(bounds, { padding: [40, 40], maxZoom: 15 });
    fleetMap.fitted = true;
  }

  renderFleetRows(vehicles);

  const offline = vehicles.filter(v => v.senal === "sin_senal").length;
  const updated = document.getElementById("txFleetUpdated");
  if (updated) {
    const time = new Intl.DateTimeFormat("es-CO", { timeStyle: "medium", timeZone: "America/Bogota" }).format(new Date());
    updated.textContent = `${vehicles.length} unidades · ${offline} sin señal · actualizado ${time}`;
  }
}

function renderFleetRows(vehicles) {
  const tbody = document.getElementById("txFleetRows");
  if (!tbody) return;

  if (!vehicles.length) {
    tbody.innerHTML = `<tr><td colspan="4">Ninguna unidad tiene GPS todavía. Emite su clave GPS o inicia el simulador.</td></tr>`;
    return;
  }

  tbody.innerHTML = vehicles.map(v => `
    <tr>
      <td><strong>${escapeHtml(v.codigo)}</strong><small>${escapeHtml(v.modelo?.nombre || "Modelo")}</small></td>
      <td>${escapeHtml(v.estado.replaceAll("_", " "))}</td>
      <td><span class="status-chip ${signalChipClass(v.senal)}">${escapeHtml(signalLabel(v.senal))}</span></td>
      <td>
        ${escapeHtml(lastReportText(v))}
        ${v.posicion ? `<button class="table-action" data-fleet-focus="${Number(v.vehiculo_id)}">Ver en el mapa</button>` : ""}
      </td>
    </tr>
  `).join("");

  tbody.querySelectorAll("[data-fleet-focus]").forEach(btn => {
    btn.addEventListener("click", () => {
      const marker = fleetMap.markers.get(Number(btn.dataset.fleetFocus));
      if (!marker) return;
      fleetMap.map.setView(marker.getLatLng(), Math.max(fleetMap.map.getZoom(), 16));
      marker.openPopup();
      document.getElementById("txFleetMap")?.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  });
}
