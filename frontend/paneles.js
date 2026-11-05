// Paneles del personal. Se carga después de app.js y reutiliza su cliente:
// api(), escapeHtml(), humanDateTime(), showToast(), handleExpiredSession() y state.

const PANEL_POLL_MS = 5000;
const STAFF_ROLES = ["administrador", "operador"];

Object.assign(adminTitles, {
  operacion: "Mostrador y despacho",
  inventario: "Inventario",
  actas: "Reportes: actas de entrega y recepción",
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
    .tx-panel-stack{display:grid;gap:18px}
    .tx-panel-stack td small,#txInvPanel td small,#txFleetRows td small,.tx-cell-note{display:block;color:var(--muted);font-size:11px;margin-top:3px}
    .tx-panel-stack td:first-child,#txInvPanel td:first-child,#txFleetRows td:first-child{display:table-cell}
    .tx-panel-stack td strong,#txInvPanel td strong,#txFleetRows td strong{display:block}
    #txInvPanel td .status-chip{margin-top:4px}
    .tx-row-actions{display:flex;gap:6px;flex-wrap:wrap}
    .tx-reservation-form select,.tx-reservation-form textarea{padding:11px;border:1px solid var(--line);border-radius:10px;font:inherit;background:#fff}
    .tx-reservation-form textarea{min-height:84px;resize:vertical}
    .tx-form-actions{display:flex;gap:10px;justify-content:flex-end;flex-wrap:wrap}
    .dialog-body .tx-form-actions .btn{width:auto}
    .tx-dialog-error{margin-top:14px}
    .tx-reservation-form label.check-row{display:flex;align-items:center;gap:8px}
    .tx-field-help{font-weight:500;color:var(--muted);font-size:11px}
    .tx-subtabs{display:flex;gap:6px;flex-wrap:wrap;margin:18px 0 14px}
    .tx-subtabs button{border:1px solid var(--line);background:#fff;border-radius:999px;padding:8px 14px;font-weight:700;font-size:12px;color:#42554f}
    .tx-subtabs button.active{background:var(--ink);border-color:var(--ink);color:#fff}
    .tx-subtabs button span{display:inline-grid;place-items:center;min-width:18px;height:18px;padding:0 5px;margin-left:4px;border-radius:999px;background:#fde8e8;color:#a33232;font-size:10px}
    .tx-dialog-scroll{display:grid;gap:14px;max-height:62vh;overflow:auto;padding-right:4px}
    .nav [hidden]{display:none!important}
    .tx-actas-filters{display:flex;gap:10px;align-items:flex-end;flex-wrap:wrap;margin-bottom:14px}
    .tx-actas-filters label{display:grid;gap:5px;font-size:11px;font-weight:700}
    .tx-actas-filters input,.tx-actas-filters select{padding:9px;border:1px solid var(--line);border-radius:10px;font:inherit;font-size:12px;background:#fff}
    .tx-pager{display:flex;gap:10px;align-items:center;justify-content:flex-end;margin-top:14px;font-size:12px;color:var(--muted)}
    .tx-hash{font-family:ui-monospace,Consolas,monospace;font-size:10px;word-break:break-all}
    #txActasRows td small{display:block;color:var(--muted);font-size:11px;margin-top:3px}
    #txActasRows td:first-child{display:table-cell}
    #txActasRows td strong{display:block}
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

  if (tab === "operacion") loadOperatorPanel();
  if (tab === "inventario") loadInventoryPanel();
  if (tab === "actas") loadActasPanel();
}

// Enlaces del sitio que dependen del rol (p. ej. "Mis actas" del cliente). app.js lo
// llama en cada cambio de sesión.
function syncRoleLinks() {
  document.querySelectorAll(".nav [data-roles]").forEach(link => {
    link.hidden = !link.dataset.roles.split(",").includes(state.user?.rol);
  });
}

// Descarga un archivo (PDF o Excel) con la sesión. api() de app.js lee como texto todo lo
// que no es JSON, así que aquí se pide el binario directamente. Los errores llegan con el
// mismo formato uniforme.
async function downloadFile(path, filename) {
  if (!state.token) throw new Error("Debes iniciar sesión.");
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 20000);

  try {
    const response = await fetch(`${API_BASE}${path}`, {
      headers: { Authorization: `Bearer ${state.token}` },
      signal: controller.signal,
    });

    if (!response.ok) {
      const contentType = response.headers.get("content-type") || "";
      const payload = contentType.includes("application/json") ? await response.json() : await response.text();
      const error = new Error(apiErrorMessage(payload, `Error HTTP ${response.status}.`));
      error.status = response.status;
      throw error;
    }

    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (error) {
    if (error.name === "AbortError") throw new Error("El backend tardó demasiado en generar el archivo. Inténtalo de nuevo.");
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

async function postJson(path, body, method = "POST") {
  return api(path, {
    method,
    auth: true,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });
}

// Maneja el error de una acción: sesión vencida o mensaje y acción del backend.
function handlePanelActionError(error) {
  if (error.status === 401) handleExpiredSession();
  else showToast(panelErrorMessage(error));
}

// Reutiliza el <dialog> de app.js para los formularios de los paneles.
function openPanelDialog(html) {
  const content = document.getElementById("dialogContent");
  content.innerHTML = `<div class="dialog-body">${html}<div class="tx-availability no tx-dialog-error" data-dialog-error hidden></div></div>`;
  dialog.showModal();
  content.querySelector("[data-dialog-cancel]")?.addEventListener("click", () => dialog.close());
  return content;
}

// El toast queda detrás del modal: los errores de un formulario se muestran dentro del diálogo.
function handleDialogError(content, error) {
  if (error.status === 401) {
    dialog.close();
    handleExpiredSession();
    return;
  }
  showPanelError(content.querySelector("[data-dialog-error]"), error);
}

// Deshabilita el botón mientras corre la acción, para no enviarla dos veces.
async function runWithButton(button, busyText, action) {
  const original = button.textContent;
  button.disabled = true;
  button.textContent = busyText;
  try {
    return await action();
  } finally {
    button.disabled = false;
    button.textContent = original;
  }
}

function vehicleCell(vehicle) {
  return `<strong>${escapeHtml(vehicle?.codigo || "")}</strong><small>${escapeHtml(vehicle?.modelo?.nombre || "Modelo")}</small>`;
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

// ---------------------------------------------------------
// Panel del operador: mostrador (HU-03) y despacho de domicilios (HU-06)
// ---------------------------------------------------------

const ACTIVE_DELIVERY_STATES = ["pendiente", "asignado", "recogido", "en_camino"];

const ops = {
  toDeliver: [],
  toReceive: [],
  pendingDeliveries: [],
  activeByRental: new Map(),
  paidSales: new Set(),
};

function deliveryStatusLabel(status = "") {
  return ({
    pendiente: "Pendiente",
    asignado: "Asignado",
    recogido: "Recogido",
    en_camino: "En camino",
    entregado: "Entregado",
    cancelado: "Cancelado",
  })[status] || status.replaceAll("_", " ");
}

function messageRow(columns, text) {
  return `<tr><td colspan="${columns}">${escapeHtml(text)}</td></tr>`;
}

async function loadOperatorPanel() {
  if (!userHasRole(STAFF_ROLES)) return;
  const errorBox = document.getElementById("txOpsError");
  ["txDeliverRows", "txReceiveRows", "txAssignRows"].forEach(id => {
    const tbody = document.getElementById(id);
    if (tbody && !tbody.children.length) tbody.innerHTML = messageRow(5, "Cargando...");
  });

  try {
    const [toDeliver, toReceive, ...deliveriesByState] = await Promise.all([
      fetchAllPages("/alquileres?estado=confirmado"),
      fetchAllPages("/alquileres?estado=en_curso"),
      ...ACTIVE_DELIVERY_STATES.map(s => fetchAllPages(`/domicilios?estado=${s}`)),
    ]);

    ops.toDeliver = toDeliver;
    ops.toReceive = toReceive;
    ops.pendingDeliveries = deliveriesByState[0];
    ops.activeByRental = new Map(deliveriesByState.flat().filter(d => d.alquiler_id).map(d => [d.alquiler_id, d]));

    // Un alquiler confirmado ya está pagado; de las compras se consulta su estado.
    const saleIds = [...new Set(ops.pendingDeliveries.filter(d => d.venta_id).map(d => d.venta_id))];
    const sales = await Promise.all(saleIds.map(id => api(`/ventas/${id}`, { auth: true })));
    ops.paidSales = new Set(sales.filter(v => v.estado === "pagada").map(v => v.id));

    hidePanelError(errorBox);
    renderOperatorPanel();
  } catch (error) {
    if (error.status === 401) handleExpiredSession();
    else showPanelError(errorBox, error);
  }
}

function isDeliveryPaid(delivery) {
  if (delivery.alquiler_id) return ops.toDeliver.some(r => r.id === delivery.alquiler_id);
  return ops.paidSales.has(delivery.venta_id);
}

function deliverRow(rental) {
  const today = colombiaDateISO();
  const delivery = ops.activeByRental.get(rental.id);
  const note = rental.fecha_inicio > today
    ? `Inicia el ${rental.fecha_inicio}`
    : rental.fecha_fin < today ? "Ya pasó la fecha de fin" : "Se puede entregar hoy";

  return `
    <tr>
      <td><strong>#${Number(rental.id)}</strong><small>Cliente #${Number(rental.cliente_id)}</small></td>
      <td>${vehicleCell(rental.vehiculo)}</td>
      <td>${escapeHtml(rental.fecha_inicio)} → ${escapeHtml(rental.fecha_fin)}<small>${escapeHtml(note)}</small></td>
      <td>${formatCOP(rental.total)}</td>
      <td>${delivery
        ? `<span class="status-chip maintenance-chip">Por domicilio · ${escapeHtml(deliveryStatusLabel(delivery.estado))}</span>`
        : `<button class="btn btn-primary small-btn" data-deliver-rental="${Number(rental.id)}">Entregar</button>`}</td>
    </tr>
  `;
}

function receiveRow(rental) {
  const today = colombiaDateISO();
  const note = rental.fecha_fin < today ? `Debió volver el ${rental.fecha_fin}` : `Vuelve el ${rental.fecha_fin}`;

  return `
    <tr>
      <td><strong>#${Number(rental.id)}</strong><small>Cliente #${Number(rental.cliente_id)}</small></td>
      <td>${vehicleCell(rental.vehiculo)}</td>
      <td>${escapeHtml(rental.fecha_inicio)} → ${escapeHtml(rental.fecha_fin)}<small>${escapeHtml(note)}</small></td>
      <td>${formatCOP(rental.total)}</td>
      <td><button class="btn btn-primary small-btn" data-receive-rental="${Number(rental.id)}">Recibir</button></td>
    </tr>
  `;
}

function assignRow(delivery) {
  const paid = isDeliveryPaid(delivery);
  const operation = delivery.alquiler_id ? `Alquiler #${Number(delivery.alquiler_id)}` : `Compra #${Number(delivery.venta_id)}`;

  return `
    <tr>
      <td><strong>${escapeHtml(delivery.codigo_rastreo)}</strong><small>${operation}</small></td>
      <td>
        <strong>${escapeHtml(delivery.cliente?.nombre_completo || "Cliente")}</strong>
        <small>${escapeHtml(delivery.direccion)}</small>
        ${delivery.indicaciones ? `<small>${escapeHtml(delivery.indicaciones)}</small>` : ""}
        ${delivery.cliente?.telefono ? `<small>Tel. ${escapeHtml(delivery.cliente.telefono)}</small>` : ""}
      </td>
      <td>${escapeHtml(delivery.zona?.nombre || "")}<small>Envío ${formatCOP(delivery.valor_envio)}</small></td>
      <td><span class="status-chip ${paid ? "active-chip" : "maintenance-chip"}">${paid ? "Pagado" : "Esperando pago"}</span></td>
      <td>${paid
        ? `<button class="btn btn-primary small-btn" data-assign-delivery="${Number(delivery.id)}">Asignar</button>`
        : `<span class="tx-cell-note">Se asigna cuando el cliente pague</span>`}</td>
    </tr>
  `;
}

function renderOperatorPanel() {
  const deliverRows = document.getElementById("txDeliverRows");
  const receiveRows = document.getElementById("txReceiveRows");
  const assignRows = document.getElementById("txAssignRows");

  deliverRows.innerHTML = ops.toDeliver.length
    ? ops.toDeliver.map(deliverRow).join("")
    : messageRow(5, "No hay alquileres confirmados por entregar.");
  receiveRows.innerHTML = ops.toReceive.length
    ? ops.toReceive.map(receiveRow).join("")
    : messageRow(5, "No hay vehículos alquilados por recibir.");
  assignRows.innerHTML = ops.pendingDeliveries.length
    ? ops.pendingDeliveries.map(assignRow).join("")
    : messageRow(5, "No hay domicilios esperando domiciliario.");

  deliverRows.querySelectorAll("[data-deliver-rental]").forEach(btn => {
    btn.addEventListener("click", () => openRentalActaDialog(Number(btn.dataset.deliverRental), "entrega"));
  });
  receiveRows.querySelectorAll("[data-receive-rental]").forEach(btn => {
    btn.addEventListener("click", () => openRentalActaDialog(Number(btn.dataset.receiveRental), "devolucion"));
  });
  assignRows.querySelectorAll("[data-assign-delivery]").forEach(btn => {
    btn.addEventListener("click", () => runWithButton(btn, "Cargando...", () => openAssignDialog(Number(btn.dataset.assignDelivery))));
  });
}

// Formulario del acta (HU-11) que acompaña una entrega o una recepción. Todo es opcional.
function actaFormHtml(confirmText) {
  return `
    <form class="tx-reservation-form" id="txActaForm">
      <label>Estado del vehículo
        <textarea name="estado_vehiculo" minlength="3" maxlength="1000" placeholder="Sin rayones. Frenos y luces funcionando."></textarea>
      </label>
      <label>Nivel de batería (%)
        <input name="nivel_bateria" type="number" min="0" max="100" placeholder="Solo si el vehículo usa batería">
      </label>
      <small class="tx-payment-note">Si no anotas nada, el acta dice "Sin observaciones.".</small>
      <div class="tx-form-actions">
        <button type="button" class="btn btn-ghost" data-dialog-cancel>Cancelar</button>
        <button type="submit" class="btn btn-primary">${escapeHtml(confirmText)}</button>
      </div>
    </form>
  `;
}

function readActaForm(form) {
  const acta = {};
  const text = form.estado_vehiculo.value.trim();
  if (text) acta.estado_vehiculo = text;
  if (form.nivel_bateria.value !== "") acta.nivel_bateria = Number(form.nivel_bateria.value);
  return acta;
}

function openRentalActaDialog(rentalId, action) {
  const delivering = action === "entrega";
  const rental = (delivering ? ops.toDeliver : ops.toReceive).find(r => r.id === rentalId);
  if (!rental) return;

  const content = openPanelDialog(`
    <span class="eyebrow">${delivering ? "ENTREGA EN EL LOCAL" : "RECEPCIÓN EN EL LOCAL"}</span>
    <h2>Reserva #${Number(rental.id)} · ${escapeHtml(rental.vehiculo?.codigo || "")}</h2>
    <p>${escapeHtml(rental.vehiculo?.modelo?.nombre || "")} · ${escapeHtml(rental.fecha_inicio)} → ${escapeHtml(rental.fecha_fin)}.
      Queda registrada el acta de ${delivering ? "entrega" : "recepción"}.</p>
    ${actaFormHtml(delivering ? "Entregar vehículo" : "Recibir vehículo")}
  `);

  const form = content.querySelector("#txActaForm");
  form.addEventListener("submit", async e => {
    e.preventDefault();
    await runWithButton(form.querySelector('[type="submit"]'), "Guardando...", async () => {
      try {
        await postJson(`/alquileres/${rental.id}/${action}`, readActaForm(form));
        dialog.close();
        showToast(delivering
          ? `Reserva #${rental.id} entregada. Quedó el acta de entrega.`
          : `Reserva #${rental.id} recibida. Quedó el acta de recepción.`);
        await loadOperatorPanel();
      } catch (error) {
        handleDialogError(content, error);
      }
    });
  });
}

async function openAssignDialog(deliveryId) {
  const delivery = ops.pendingDeliveries.find(d => d.id === deliveryId);
  if (!delivery) return;

  let couriers;
  let vehicles;
  try {
    [couriers, vehicles] = await Promise.all([
      fetchAllPages("/domicilios/domiciliarios-disponibles"),
      fetchAllPages("/vehiculos?estado=disponible"),
    ]);
  } catch (error) {
    handlePanelActionError(error);
    return;
  }

  if (!couriers.length) {
    showToast("No hay domiciliarios disponibles: todos tienen una entrega en ruta. Intenta de nuevo cuando alguno termine.");
    return;
  }

  // La unidad que se entrega no puede ser también el vehículo del domiciliario.
  const deliveredUnit = ops.toDeliver.find(r => r.id === delivery.alquiler_id)?.vehiculo?.id;
  const transport = vehicles.filter(v => v.id !== deliveredUnit);

  const content = openPanelDialog(`
    <span class="eyebrow">ASIGNAR DOMICILIO</span>
    <h2>${escapeHtml(delivery.codigo_rastreo)}</h2>
    <p>${escapeHtml(delivery.cliente?.nombre_completo || "")} · ${escapeHtml(delivery.direccion)} (${escapeHtml(delivery.zona?.nombre || "")})</p>
    <form class="tx-reservation-form" id="txAssignForm">
      <label>Domiciliario
        <select name="domiciliario_id" required>
          ${couriers.map(c => `<option value="${Number(c.id)}">${escapeHtml(c.nombre_completo)}${c.telefono ? ` · ${escapeHtml(c.telefono)}` : ""}</option>`).join("")}
        </select>
      </label>
      <label>Vehículo de transporte (opcional)
        <select name="vehiculo_transporte_id">
          <option value="">Sin vehículo de la flota</option>
          ${transport.map(v => `<option value="${Number(v.id)}">${escapeHtml(v.codigo)} · ${escapeHtml(v.modelo?.nombre || "")}</option>`).join("")}
        </select>
      </label>
      <div class="tx-form-actions">
        <button type="button" class="btn btn-ghost" data-dialog-cancel>Cancelar</button>
        <button type="submit" class="btn btn-primary">Asignar</button>
      </div>
    </form>
  `);

  const form = content.querySelector("#txAssignForm");
  form.addEventListener("submit", async e => {
    e.preventDefault();
    await runWithButton(form.querySelector('[type="submit"]'), "Asignando...", async () => {
      try {
        const result = await postJson(`/domicilios/${delivery.id}/asignacion`, {
          domiciliario_id: Number(form.domiciliario_id.value),
          vehiculo_transporte_id: form.vehiculo_transporte_id.value ? Number(form.vehiculo_transporte_id.value) : null,
        });
        dialog.close();
        showToast(`${result.codigo_rastreo} asignado a ${result.domiciliario?.nombre_completo || "el domiciliario"}.`);
        await loadOperatorPanel();
      } catch (error) {
        handleDialogError(content, error);
      }
    });
  });
}

document.getElementById("txOpsRefresh")?.addEventListener("click", e => {
  runWithButton(e.currentTarget, "Actualizando...", loadOperatorPanel);
});

// ---------------------------------------------------------
// Panel del domiciliario (HU-07): sus entregas en ruta
// ---------------------------------------------------------

// asignado → recogido → en_camino → entregado, sin saltar pasos.
const NEXT_DELIVERY_STEP = {
  asignado: { estado: "recogido", label: "Marcar recogido" },
  recogido: { estado: "en_camino", label: "Salir en camino" },
  en_camino: { estado: "entregado", label: "Marcar entregado" },
};

let courierDeliveries = [];

function courierCard(delivery) {
  const next = NEXT_DELIVERY_STEP[delivery.estado];
  const operation = delivery.alquiler_id ? `Alquiler #${Number(delivery.alquiler_id)}` : `Compra #${Number(delivery.venta_id)}`;
  const lat = Number(delivery.latitud);
  const lon = Number(delivery.longitud);
  const phone = delivery.cliente?.telefono;

  return `
    <article class="tx-rental-card">
      <div class="tx-rental-main">
        <div class="tx-rental-icon">📦</div>
        <div>
          <small>${escapeHtml(delivery.codigo_rastreo)} · ${operation}</small>
          <h3>${escapeHtml(delivery.cliente?.nombre_completo || "Cliente")}</h3>
          <span class="tx-status ${delivery.estado === "asignado" ? "tx-status-pending" : "tx-status-ok"}">${escapeHtml(deliveryStatusLabel(delivery.estado))}</span>
        </div>
      </div>
      <div class="tx-rental-dates">
        <strong>${escapeHtml(delivery.direccion)}</strong>
        ${delivery.indicaciones ? `<span>${escapeHtml(delivery.indicaciones)}</span>` : ""}
        <small>${escapeHtml(delivery.zona?.nombre || "")}${phone ? ` · <a href="tel:${escapeHtml(phone)}">Tel. ${escapeHtml(phone)}</a>` : ""}</small>
        ${delivery.vehiculo_transporte ? `<small>Vas en ${escapeHtml(delivery.vehiculo_transporte.codigo)}</small>` : ""}
        <small><a href="https://www.openstreetmap.org/?mlat=${lat}&amp;mlon=${lon}#map=18/${lat}/${lon}" target="_blank" rel="noopener">Ver el punto en el mapa</a></small>
      </div>
      <div class="tx-rental-actions">
        ${next ? `<button class="btn btn-primary small-btn" data-advance-delivery="${Number(delivery.id)}">${escapeHtml(next.label)}</button>` : ""}
      </div>
    </article>
  `;
}

async function loadCourierPanel() {
  const list = document.getElementById("txCourierList");
  const errorBox = document.getElementById("txCourierError");
  if (!list) return;

  if (!userHasRole(["domiciliario"])) {
    list.innerHTML = `<div class="empty-state"><div>🔐</div><h3>Inicia sesión como domiciliario</h3><p>Esta sección muestra las entregas asignadas a un domiciliario.</p></div>`;
    return;
  }

  const greeting = document.getElementById("txCourierGreeting");
  if (greeting) greeting.textContent = `Hola, ${state.user.nombre_completo.split(" ")[0]}. Estas son tus entregas.`;
  // Si la lista es de otra sesión, no se muestra mientras carga.
  if (list.dataset.owner !== String(state.user.id)) {
    list.dataset.owner = String(state.user.id);
    list.innerHTML = `<div class="empty-state"><div>⏳</div><h3>Cargando tus entregas</h3></div>`;
  }

  try {
    courierDeliveries = await fetchAllPages("/domicilios/asignados");
    hidePanelError(errorBox);
  } catch (error) {
    if (error.status === 401) handleExpiredSession();
    else showPanelError(errorBox, error);
    return;
  }

  if (!courierDeliveries.length) {
    list.innerHTML = `<div class="empty-state"><div>🛵</div><h3>No tienes entregas en ruta</h3><p>Cuando el despacho te asigne un domicilio aparecerá aquí. Usa "Actualizar" para revisar.</p></div>`;
    return;
  }

  list.innerHTML = courierDeliveries.map(courierCard).join("");
  list.querySelectorAll("[data-advance-delivery]").forEach(btn => {
    btn.addEventListener("click", () => advanceDelivery(Number(btn.dataset.advanceDelivery), btn));
  });
}

async function advanceDelivery(id, button) {
  const delivery = courierDeliveries.find(d => d.id === id);
  const next = delivery && NEXT_DELIVERY_STEP[delivery.estado];
  if (!next) return;

  // Al entregar queda el acta (HU-11): se pide el estado en que se entrega.
  if (next.estado === "entregado") {
    openDeliveredDialog(delivery);
    return;
  }

  await runWithButton(button, "Guardando...", async () => {
    try {
      await postJson(`/domicilios/${id}/estado`, { estado: next.estado });
      showToast(`${delivery.codigo_rastreo}: ${deliveryStatusLabel(next.estado).toLowerCase()}.`);
      await loadCourierPanel();
    } catch (error) {
      handlePanelActionError(error);
    }
  });
}

function openDeliveredDialog(delivery) {
  const content = openPanelDialog(`
    <span class="eyebrow">ENTREGA A DOMICILIO</span>
    <h2>${escapeHtml(delivery.codigo_rastreo)}</h2>
    <p>${escapeHtml(delivery.cliente?.nombre_completo || "")} · ${escapeHtml(delivery.direccion)}. Queda registrada el acta de entrega.</p>
    ${actaFormHtml("Confirmar entrega")}
  `);

  const form = content.querySelector("#txActaForm");
  form.addEventListener("submit", async e => {
    e.preventDefault();
    await runWithButton(form.querySelector('[type="submit"]'), "Guardando...", async () => {
      try {
        await postJson(`/domicilios/${delivery.id}/estado`, { estado: "entregado", acta: readActaForm(form) });
        dialog.close();
        showToast(`${delivery.codigo_rastreo} entregado. Quedó el acta de entrega.`);
        await loadCourierPanel();
      } catch (error) {
        handleDialogError(content, error);
      }
    });
  });
}

document.getElementById("txCourierRefresh")?.addEventListener("click", e => {
  runWithButton(e.currentTarget, "Actualizando...", loadCourierPanel);
});

document.getElementById("txCourierLogout")?.addEventListener("click", () => {
  clearSession();
  showView("inicio");
  showToast("Sesión cerrada.");
});

// ---------------------------------------------------------
// Formularios genéricos de los paneles
// ---------------------------------------------------------

// Un campo: { name, label, type, value, required, options, numeric, attrs, help }.
function formFieldHtml(field) {
  const value = field.value ?? "";
  const common = `name="${escapeHtml(field.name)}" ${field.required ? "required" : ""} ${field.attrs || ""}`;
  const help = field.help ? `<span class="tx-field-help">${escapeHtml(field.help)}</span>` : "";

  if (field.type === "checkbox") {
    return `<label class="check-row"><input type="checkbox" ${common} ${value ? "checked" : ""}> ${escapeHtml(field.label)}</label>`;
  }
  if (field.type === "select") {
    const options = field.options.map(o => `
      <option value="${escapeHtml(o.value)}" ${String(o.value) === String(value) ? "selected" : ""}>${escapeHtml(o.label)}</option>
    `).join("");
    return `<label>${escapeHtml(field.label)}<select ${common}>${options}</select>${help}</label>`;
  }
  if (field.type === "textarea") {
    return `<label>${escapeHtml(field.label)}<textarea ${common}>${escapeHtml(value)}</textarea>${help}</label>`;
  }
  return `<label>${escapeHtml(field.label)}<input type="${field.type || "text"}" ${common} value="${escapeHtml(value)}">${help}</label>`;
}

// Vacío es null; los números y las selecciones de ids se envían como número.
function readFormValues(form, fields) {
  const values = {};
  fields.forEach(field => {
    const input = form.elements[field.name];
    if (field.type === "checkbox") {
      values[field.name] = input.checked;
    } else {
      const raw = input.value.trim();
      values[field.name] = raw === "" ? null : (field.type === "number" || field.numeric ? Number(raw) : raw);
    }
  });
  return values;
}

// Para los PATCH parciales: solo lo que cambió respecto al original.
function changedFields(values, original) {
  return Object.fromEntries(Object.entries(values).filter(([key, value]) => value !== (original[key] ?? null)));
}

// onSubmit devuelve el texto del toast; si lanza un error, se muestra en el diálogo.
function openFormDialog({ eyebrow, title, subtitle, fields, submitText, onSubmit, onDone }) {
  const content = openPanelDialog(`
    <span class="eyebrow">${escapeHtml(eyebrow)}</span>
    <h2>${escapeHtml(title)}</h2>
    ${subtitle ? `<p>${escapeHtml(subtitle)}</p>` : ""}
    <form class="tx-reservation-form" id="txPanelForm">
      <div class="tx-dialog-scroll">${fields.map(formFieldHtml).join("")}</div>
      <div class="tx-form-actions">
        <button type="button" class="btn btn-ghost" data-dialog-cancel>Cancelar</button>
        <button type="submit" class="btn btn-primary">${escapeHtml(submitText)}</button>
      </div>
    </form>
  `);

  const form = content.querySelector("#txPanelForm");
  form.addEventListener("submit", async e => {
    e.preventDefault();
    await runWithButton(form.querySelector('[type="submit"]'), "Guardando...", async () => {
      try {
        const message = await onSubmit(readFormValues(form, fields));
        dialog.close();
        if (message) showToast(message);
        await onDone?.();
      } catch (error) {
        handleDialogError(content, error);
      }
    });
  });
}

// ---------------------------------------------------------
// Inventario del administrador (HU-10)
// ---------------------------------------------------------

const ADMIN_ONLY = ["administrador"];

const inventory = {
  tab: "alertas",
  summary: null,
  alerts: [],
  types: [],
  models: [],
  units: [],
  products: [],
};

function categoryLabel(category) {
  return ({ accesorio: "Accesorio", repuesto: "Repuesto" })[category] || category;
}

function activeChip(active) {
  return `<span class="status-chip ${active ? "active-chip" : "inactive-chip"}">${active ? "Activo" : "Inactivo"}</span>`;
}

function unitStatusChip(status) {
  const css = status === "disponible" ? "active-chip" : status === "mantenimiento" ? "maintenance-chip" : "inactive-chip";
  return `<span class="status-chip ${css}">${escapeHtml(status.replaceAll("_", " "))}</span>`;
}

function priceOrDash(value) {
  return value ? formatCOP(value) : "—";
}

async function loadInventoryPanel() {
  if (!userHasRole(ADMIN_ONLY)) return;
  const errorBox = document.getElementById("txInvError");

  try {
    const [summary, alerts, types, models, units, products] = await Promise.all([
      api("/inventario/resumen", { auth: true }),
      fetchAllPages("/inventario/alertas-stock"),
      fetchAllPages("/inventario/tipos"),
      fetchAllPages("/inventario/modelos"),
      fetchAllPages("/vehiculos"),
      fetchAllPages("/inventario/productos"),
    ]);
    Object.assign(inventory, { summary, alerts, types, models, units, products });
    hidePanelError(errorBox);
    renderInventory();
  } catch (error) {
    if (error.status === 401) handleExpiredSession();
    else showPanelError(errorBox, error);
  }
}

function renderInventory() {
  const s = inventory.summary;
  const byStatus = s.unidades_por_estado || {};
  document.getElementById("txInvMetrics").innerHTML = `
    <article><span>Unidades</span><strong>${Number(s.total_unidades)}</strong><small>en la flota</small></article>
    <article><span>Disponibles</span><strong>${Number(byStatus.disponible || 0)}</strong><small>listas para alquilar o vender</small></article>
    <article><span>En mantenimiento</span><strong>${Number(byStatus.mantenimiento || 0)}</strong><small>fuera del catálogo</small></article>
    <article><span>Bajo stock</span><strong>${Number(s.productos_bajo_stock)}</strong><small>de ${Number(s.productos_activos)} productos activos</small></article>
  `;
  document.getElementById("txInvAlertCount").textContent = inventory.alerts.length;
  document.querySelectorAll("[data-inv-tab]").forEach(btn => btn.classList.toggle("active", btn.dataset.invTab === inventory.tab));

  const panel = document.getElementById("txInvPanel");
  const views = {
    alertas: inventoryAlertsHtml,
    modelos: inventoryModelsHtml,
    unidades: inventoryUnitsHtml,
    productos: inventoryProductsHtml,
  };
  panel.innerHTML = views[inventory.tab]();

  panel.querySelector("[data-inv-new]")?.addEventListener("click", () => {
    ({ modelos: openModelForm, unidades: openUnitForm, productos: openProductForm })[inventory.tab]();
  });
  panel.querySelectorAll("[data-edit-model]").forEach(btn => btn.addEventListener("click", () => openModelForm(Number(btn.dataset.editModel))));
  panel.querySelectorAll("[data-edit-unit]").forEach(btn => btn.addEventListener("click", () => openUnitForm(Number(btn.dataset.editUnit))));
  panel.querySelectorAll("[data-edit-product]").forEach(btn => btn.addEventListener("click", () => openProductForm(Number(btn.dataset.editProduct))));
  panel.querySelectorAll("[data-adjust-product]").forEach(btn => btn.addEventListener("click", () => openStockAdjustment(Number(btn.dataset.adjustProduct))));
}

function inventoryPanelHtml(title, newLabel, head, rows, empty) {
  return `
    <div class="panel-heading">
      <div><small>HU-10</small><h3>${escapeHtml(title)}</h3></div>
      ${newLabel ? `<button class="btn btn-primary small-btn" data-inv-new>${escapeHtml(newLabel)}</button>` : ""}
    </div>
    <div class="table-wrap"><table>
      <thead><tr>${head.map(h => `<th>${escapeHtml(h)}</th>`).join("")}</tr></thead>
      <tbody>${rows.length ? rows.join("") : messageRow(head.length, empty)}</tbody>
    </table></div>
  `;
}

function stockCell(product) {
  return `<strong>${Number(product.stock)}</strong><small>mínimo ${Number(product.stock_minimo)}</small>
    ${product.bajo_stock ? `<span class="status-chip tx-chip-danger">Bajo stock</span>` : ""}`;
}

function inventoryAlertsHtml() {
  const rows = inventory.alerts.map(p => `
    <tr>
      <td><strong>${escapeHtml(p.nombre)}</strong><small>${escapeHtml(p.codigo)}</small></td>
      <td>${escapeHtml(categoryLabel(p.categoria))}</td>
      <td>${stockCell(p)}</td>
      <td><button class="btn btn-primary small-btn" data-adjust-product="${Number(p.id)}">Ajustar stock</button></td>
    </tr>
  `);
  return inventoryPanelHtml("Productos en o bajo su stock mínimo", null,
    ["Producto", "Categoría", "Stock", "Acción"], rows, "Ningún producto está en o bajo su stock mínimo.");
}

function inventoryModelsHtml() {
  const rows = inventory.models.map(m => `
    <tr>
      <td><strong>${escapeHtml(m.nombre)}</strong><small>${escapeHtml(m.marca || "Sin marca")}</small></td>
      <td>${escapeHtml(m.tipo?.nombre || "")}</td>
      <td>${priceOrDash(m.tarifa_diaria)}<small>${m.tarifa_diaria ? "por día" : "no se alquila"}</small></td>
      <td>${priceOrDash(m.precio_venta)}<small>${m.precio_venta ? "venta" : "no se vende"}</small></td>
      <td>${activeChip(m.activo)}</td>
      <td><button class="table-action" data-edit-model="${Number(m.id)}">Editar</button></td>
    </tr>
  `);
  return inventoryPanelHtml("Modelos del catálogo", "+ Nuevo modelo",
    ["Modelo", "Tipo", "Tarifa", "Precio", "Estado", "Acción"], rows, "No hay modelos registrados.");
}

function inventoryUnitsHtml() {
  const rows = inventory.units.map(u => `
    <tr>
      <td><strong>${escapeHtml(u.codigo)}</strong><small>${escapeHtml(u.modelo?.nombre || "")}</small></td>
      <td>${unitStatusChip(u.estado)}</td>
      <td>${u.nivel_bateria != null ? `${Number(u.nivel_bateria)}%` : "—"}</td>
      <td>${escapeHtml(u.ubicacion || "—")}${u.observaciones ? `<small>${escapeHtml(u.observaciones)}</small>` : ""}</td>
      <td>${u.estado === "vendido"
        ? `<span class="tx-cell-note">Vendida: no se edita</span>`
        : `<button class="table-action" data-edit-unit="${Number(u.id)}">Editar</button>`}</td>
    </tr>
  `);
  return inventoryPanelHtml("Unidades de la flota", "+ Registrar unidad",
    ["Unidad", "Estado", "Batería", "Ubicación", "Acción"], rows, "No hay unidades registradas.");
}

function inventoryProductsHtml() {
  const rows = inventory.products.map(p => `
    <tr>
      <td><strong>${escapeHtml(p.nombre)}</strong><small>${escapeHtml(p.codigo)}</small></td>
      <td>${escapeHtml(categoryLabel(p.categoria))}</td>
      <td>${formatCOP(p.precio_venta)}</td>
      <td>${stockCell(p)}</td>
      <td>${activeChip(p.activo)}</td>
      <td><div class="tx-row-actions">
        <button class="table-action" data-edit-product="${Number(p.id)}">Editar</button>
        <button class="table-action" data-adjust-product="${Number(p.id)}">Ajustar stock</button>
      </div></td>
    </tr>
  `);
  return inventoryPanelHtml("Accesorios y repuestos", "+ Nuevo producto",
    ["Producto", "Categoría", "Precio", "Stock", "Estado", "Acciones"], rows, "No hay productos registrados.");
}

// --- Formularios del inventario -------------------------------------------

function openModelForm(modelId) {
  const model = inventory.models.find(m => m.id === modelId);
  const original = model ? {
    tipo_vehiculo_id: model.tipo?.id,
    nombre: model.nombre,
    marca: model.marca,
    descripcion: model.descripcion,
    imagen_url: model.imagen_url,
    tarifa_diaria: model.tarifa_diaria,
    precio_venta: model.precio_venta,
    activo: model.activo,
  } : {};

  const fields = [
    { name: "tipo_vehiculo_id", label: "Tipo de vehículo", type: "select", numeric: true, required: true, value: original.tipo_vehiculo_id,
      options: inventory.types.map(t => ({ value: t.id, label: t.nombre })) },
    { name: "nombre", label: "Nombre", required: true, value: original.nombre, attrs: 'minlength="2" maxlength="100"' },
    { name: "marca", label: "Marca", value: original.marca, attrs: 'maxlength="60"' },
    { name: "descripcion", label: "Descripción", type: "textarea", value: original.descripcion, attrs: 'maxlength="2000"' },
    { name: "imagen_url", label: "URL de la imagen", type: "url", value: original.imagen_url, attrs: 'maxlength="500"' },
    { name: "tarifa_diaria", label: "Tarifa diaria (pesos)", type: "number", value: original.tarifa_diaria, attrs: 'min="1" step="1"', help: "Vacía: el modelo no se alquila." },
    { name: "precio_venta", label: "Precio de venta (pesos)", type: "number", value: original.precio_venta, attrs: 'min="1" step="1"', help: "Vacío: el modelo no se vende." },
  ];
  if (model) fields.push({ name: "activo", label: "Activo (visible en el catálogo)", type: "checkbox", value: original.activo });

  openFormDialog({
    eyebrow: model ? "EDITAR MODELO" : "NUEVO MODELO",
    title: model ? model.nombre : "Nuevo modelo",
    subtitle: model ? "Las operaciones ya hechas conservan el precio del momento." : "Necesita tarifa diaria, precio de venta o ambos.",
    fields,
    submitText: model ? "Guardar cambios" : "Crear modelo",
    onDone: loadInventoryPanel,
    onSubmit: async values => {
      if (!model) {
        const created = await postJson("/inventario/modelos", values);
        return `Modelo "${created.nombre}" creado.`;
      }
      const changes = changedFields(values, original);
      if (!Object.keys(changes).length) return "No había cambios para guardar.";
      await postJson(`/inventario/modelos/${model.id}`, changes, "PATCH");
      return `Modelo "${values.nombre}" actualizado.`;
    },
  });
}

function openUnitForm(unitId) {
  const unit = inventory.units.find(u => u.id === unitId);
  const original = unit ? {
    nivel_bateria: unit.nivel_bateria,
    ubicacion: unit.ubicacion,
    observaciones: unit.observaciones,
  } : {};

  // El código y el modelo son la identidad de la unidad: solo se escogen al registrarla.
  const fields = unit ? [] : [
    { name: "codigo", label: "Código", required: true, attrs: 'pattern="[A-Za-z0-9][A-Za-z0-9\\-]{2,19}" maxlength="20"', help: "Letras, números y guiones (3 a 20). Se guarda en mayúsculas." },
    { name: "modelo_id", label: "Modelo", type: "select", numeric: true, required: true,
      options: inventory.models.filter(m => m.activo).map(m => ({ value: m.id, label: `${m.nombre} · ${m.tipo?.nombre || ""}` })) },
  ];
  fields.push(
    { name: "nivel_bateria", label: "Nivel de batería (%)", type: "number", value: original.nivel_bateria, attrs: 'min="0" max="100" step="1"', help: "Solo si el tipo de vehículo usa batería." },
    { name: "ubicacion", label: "Ubicación", value: original.ubicacion, attrs: 'maxlength="150"' },
    { name: "observaciones", label: "Observaciones", type: "textarea", value: original.observaciones, attrs: 'maxlength="2000"' },
  );

  openFormDialog({
    eyebrow: unit ? "EDITAR UNIDAD" : "REGISTRAR UNIDAD",
    title: unit ? unit.codigo : "Nueva unidad",
    subtitle: unit ? "El estado cambia con sus flujos (alquiler, venta, mantenimiento), no aquí." : "La unidad entra disponible.",
    fields,
    submitText: unit ? "Guardar cambios" : "Registrar unidad",
    onDone: loadInventoryPanel,
    onSubmit: async values => {
      if (!unit) {
        const created = await postJson("/inventario/unidades", values);
        return `Unidad ${created.codigo} registrada.`;
      }
      const changes = changedFields(values, original);
      if (!Object.keys(changes).length) return "No había cambios para guardar.";
      await postJson(`/inventario/unidades/${unit.id}`, changes, "PATCH");
      return `Unidad ${unit.codigo} actualizada.`;
    },
  });
}

function openProductForm(productId) {
  const product = inventory.products.find(p => p.id === productId);
  const original = product ? {
    nombre: product.nombre,
    categoria: product.categoria,
    descripcion: product.descripcion,
    imagen_url: product.imagen_url,
    precio_venta: product.precio_venta,
    stock_minimo: product.stock_minimo,
    activo: product.activo,
  } : {};

  const fields = product ? [] : [
    { name: "codigo", label: "Código", required: true, attrs: 'pattern="[A-Za-z0-9][A-Za-z0-9\\-]{2,19}" maxlength="20"', help: "Letras, números y guiones (3 a 20). Se guarda en mayúsculas." },
  ];
  fields.push(
    { name: "nombre", label: "Nombre", required: true, value: original.nombre, attrs: 'minlength="2" maxlength="120"' },
    { name: "categoria", label: "Categoría", type: "select", required: true, value: original.categoria,
      options: [{ value: "accesorio", label: "Accesorio" }, { value: "repuesto", label: "Repuesto" }] },
    { name: "descripcion", label: "Descripción", type: "textarea", value: original.descripcion, attrs: 'maxlength="2000"' },
    { name: "imagen_url", label: "URL de la imagen", type: "url", value: original.imagen_url, attrs: 'maxlength="500"' },
    { name: "precio_venta", label: "Precio de venta (pesos)", type: "number", required: true, value: original.precio_venta, attrs: 'min="1" step="1"' },
  );
  // El stock no se edita: entra al crear y luego se mueve con ajustes.
  if (!product) fields.push({ name: "stock", label: "Stock inicial", type: "number", required: true, value: 0, attrs: 'min="0" step="1"' });
  fields.push({ name: "stock_minimo", label: "Stock mínimo", type: "number", required: true, value: original.stock_minimo ?? 0, attrs: 'min="0" step="1"', help: "En o bajo este número aparece en las alertas." });
  if (product) fields.push({ name: "activo", label: "Activo (a la venta)", type: "checkbox", value: original.activo });

  openFormDialog({
    eyebrow: product ? "EDITAR PRODUCTO" : "NUEVO PRODUCTO",
    title: product ? product.nombre : "Nuevo producto",
    subtitle: product ? `${product.codigo} · el stock se cambia con "Ajustar stock".` : null,
    fields,
    submitText: product ? "Guardar cambios" : "Crear producto",
    onDone: loadInventoryPanel,
    onSubmit: async values => {
      if (!product) {
        const created = await postJson("/inventario/productos", values);
        return `Producto "${created.nombre}" creado.`;
      }
      const changes = changedFields(values, original);
      if (!Object.keys(changes).length) return "No había cambios para guardar.";
      await postJson(`/inventario/productos/${product.id}`, changes, "PATCH");
      return `Producto "${values.nombre}" actualizado.`;
    },
  });
}

function openStockAdjustment(productId) {
  const product = inventory.products.find(p => p.id === productId) || inventory.alerts.find(p => p.id === productId);
  if (!product) return;

  openFormDialog({
    eyebrow: "AJUSTE DE STOCK",
    title: product.nombre,
    subtitle: `Stock actual: ${product.stock} (mínimo ${product.stock_minimo}). Positivo para una entrada, negativo para una salida.`,
    fields: [
      { name: "cantidad", label: "Cantidad", type: "number", required: true, attrs: 'step="1" placeholder="+5 si llegaron 5, -2 si se dañaron 2"' },
      { name: "motivo", label: "Motivo", required: true, attrs: 'minlength="5" maxlength="300" placeholder="Llegó el pedido del proveedor (factura 1234)."' },
    ],
    submitText: "Aplicar ajuste",
    onDone: loadInventoryPanel,
    onSubmit: async values => {
      const updated = await postJson(`/inventario/productos/${product.id}/ajustes`, values);
      return `Stock de "${updated.nombre}": ${updated.stock}.`;
    },
  });
}

document.querySelectorAll("[data-inv-tab]").forEach(btn => {
  btn.addEventListener("click", () => {
    inventory.tab = btn.dataset.invTab;
    if (inventory.summary) renderInventory();
  });
});

// ---------------------------------------------------------
// Actas (HU-11): reportes del personal y conformidad del cliente
// ---------------------------------------------------------

const ACTAS_PAGE_SIZE = 20;
const actas = { page: 1, pages: 0, total: 0, items: [] };

function actaTypeLabel(type) {
  return ({ entrega: "Entrega", recepcion: "Recepción" })[type] || type;
}

function actaOrigin(acta) {
  const operation = acta.alquiler_id ? `Alquiler #${Number(acta.alquiler_id)}` : `Compra #${Number(acta.venta_id)}`;
  return `${operation} · ${acta.domicilio_id ? "por domicilio" : "en el local"}`;
}

function actaPdfName(acta) {
  return `${acta.numero}.pdf`;
}

function actasFilters() {
  const form = document.getElementById("txActasFilters");
  return { desde: form.desde.value, hasta: form.hasta.value, tipo: form.tipo.value };
}

function actasQuery(extra = {}) {
  const { desde, hasta, tipo } = actasFilters();
  const params = new URLSearchParams({ desde, hasta, ...extra });
  if (tipo) params.set("tipo", tipo);
  return params.toString();
}

// Por defecto, los últimos 30 días de Colombia (lo mismo que usa el backend).
function initActasFilters() {
  const form = document.getElementById("txActasFilters");
  if (!form || form.hasta.value) return;
  const today = colombiaDateISO();
  form.hasta.value = today;
  form.desde.value = addDaysISO(today, -29);
}

async function loadActasPanel(page = actas.page) {
  if (!userHasRole(STAFF_ROLES)) return;
  initActasFilters();
  const errorBox = document.getElementById("txActasError");
  const tbody = document.getElementById("txActasRows");
  if (!tbody.children.length) tbody.innerHTML = messageRow(6, "Cargando...");

  try {
    const data = await api(`/actas?${actasQuery({ pagina: page, tamano: ACTAS_PAGE_SIZE })}`, { auth: true });
    Object.assign(actas, { page: data.pagina, pages: data.paginas, total: data.total, items: data.elementos || [] });
    hidePanelError(errorBox);
    renderActas();
  } catch (error) {
    if (error.status === 401) handleExpiredSession();
    else showPanelError(errorBox, error);
  }
}

function conformityCell(acta) {
  if (!acta.conformidad) return `<span class="status-chip maintenance-chip">Pendiente</span>`;
  return `<span class="status-chip active-chip">Conforme</span>
    <small>${escapeHtml(acta.conformidad.conforme_por)} · ${escapeHtml(humanDateTime(acta.conformidad.conforme_en))}</small>`;
}

function renderActas() {
  const tbody = document.getElementById("txActasRows");
  tbody.innerHTML = actas.items.length ? actas.items.map(acta => `
    <tr>
      <td><strong>${escapeHtml(acta.numero)}</strong><small>${escapeHtml(actaTypeLabel(acta.tipo))} · ${actaOrigin(acta)}</small></td>
      <td><strong>${escapeHtml(acta.vehiculo_codigo)}</strong><small>${escapeHtml(acta.modelo)}</small></td>
      <td>${escapeHtml(acta.cliente)}</td>
      <td>${escapeHtml(humanDateTime(acta.creado_en))}<small>Registró ${escapeHtml(acta.registrada_por)}</small><small>${escapeHtml(acta.estado_vehiculo)}${acta.nivel_bateria != null ? ` · batería ${Number(acta.nivel_bateria)}%` : ""}</small></td>
      <td>${conformityCell(acta)}</td>
      <td><div class="tx-row-actions">
        <button class="table-action" data-acta-pdf="${Number(acta.id)}">PDF</button>
        ${acta.conformidad ? `<button class="table-action" data-acta-verify="${Number(acta.id)}">Verificar</button>` : ""}
      </div></td>
    </tr>
  `).join("") : messageRow(6, "No hay actas en ese rango de fechas.");

  const pager = document.getElementById("txActasPager");
  pager.innerHTML = actas.pages > 1 ? `
    <span>Página ${actas.page} de ${actas.pages} · ${actas.total} actas</span>
    <button class="table-action" data-actas-page="${actas.page - 1}" ${actas.page <= 1 ? "disabled" : ""}>Anterior</button>
    <button class="table-action" data-actas-page="${actas.page + 1}" ${actas.page >= actas.pages ? "disabled" : ""}>Siguiente</button>
  ` : `<span>${actas.total} acta${actas.total === 1 ? "" : "s"}</span>`;

  pager.querySelectorAll("[data-actas-page]").forEach(btn => {
    btn.addEventListener("click", () => loadActasPanel(Number(btn.dataset.actasPage)));
  });
  tbody.querySelectorAll("[data-acta-pdf]").forEach(btn => {
    const acta = actas.items.find(a => a.id === Number(btn.dataset.actaPdf));
    btn.addEventListener("click", () => downloadActaPdf(acta, btn));
  });
  tbody.querySelectorAll("[data-acta-verify]").forEach(btn => {
    const acta = actas.items.find(a => a.id === Number(btn.dataset.actaVerify));
    btn.addEventListener("click", () => verifyActa(acta, btn));
  });
}

async function downloadActaPdf(acta, button) {
  await runWithButton(button, "Descargando...", async () => {
    try {
      await downloadFile(`/actas/${acta.id}/pdf`, actaPdfName(acta));
    } catch (error) {
      handlePanelActionError(error);
    }
  });
}

async function verifyActa(acta, button) {
  await runWithButton(button, "Verificando...", async () => {
    try {
      const result = await api(`/actas/${acta.id}/verificacion`, { auth: true });
      if (result.coincide === true) {
        showToast(`${acta.numero}: el PDF de hoy es el mismo que aceptó el cliente (SHA-256 ${result.hash_pdf.slice(0, 12)}…).`);
      } else if (result.coincide === false) {
        showToast(`${acta.numero}: el PDF de hoy NO coincide con el que aceptó el cliente. Revisa el acta con el equipo.`);
      } else {
        showToast(`${acta.numero} todavía no tiene la conformidad del cliente.`);
      }
    } catch (error) {
      handlePanelActionError(error);
    }
  });
}

document.getElementById("txActasFilters")?.addEventListener("submit", e => {
  e.preventDefault();
  loadActasPanel(1);
});

document.getElementById("txActasExcel")?.addEventListener("click", e => {
  const { desde, hasta } = actasFilters();
  runWithButton(e.currentTarget, "Generando...", async () => {
    try {
      await downloadFile(`/actas/exportacion/excel?${actasQuery()}`, `actas-${desde}-a-${hasta}.xlsx`);
      showToast("Reporte de actas descargado en Excel.");
    } catch (error) {
      handlePanelActionError(error);
    }
  });
});

// --- Mis actas (cliente) ---------------------------------------------------

let myActas = [];

function myActaCard(acta) {
  const conformity = acta.conformidad;
  return `
    <article class="tx-rental-card">
      <div class="tx-rental-main">
        <div class="tx-rental-icon">📄</div>
        <div>
          <small>${escapeHtml(acta.numero)} · ${actaOrigin(acta)}</small>
          <h3>${escapeHtml(actaTypeLabel(acta.tipo))} de ${escapeHtml(acta.vehiculo_codigo)}</h3>
          <span class="tx-status ${conformity ? "tx-status-ok" : "tx-status-pending"}">${conformity ? "Conforme" : "Pendiente de tu conformidad"}</span>
        </div>
      </div>
      <div class="tx-rental-dates">
        <strong>${escapeHtml(acta.modelo)} · ${escapeHtml(humanDateTime(acta.creado_en))}</strong>
        <span>${escapeHtml(acta.estado_vehiculo)}${acta.nivel_bateria != null ? ` · batería ${Number(acta.nivel_bateria)}%` : ""}</span>
        <small>Registró ${escapeHtml(acta.registrada_por)}</small>
        ${conformity ? `<small>Diste tu conformidad el ${escapeHtml(humanDateTime(conformity.conforme_en))}</small>
          <small class="tx-hash">SHA-256 ${escapeHtml(conformity.hash_pdf)}</small>` : ""}
      </div>
      <div class="tx-rental-actions">
        <button class="btn btn-ghost small-btn" data-my-acta-pdf="${Number(acta.id)}">Descargar PDF</button>
        ${conformity ? "" : `<button class="btn btn-primary small-btn" data-my-acta-accept="${Number(acta.id)}">Dar conformidad</button>`}
      </div>
    </article>
  `;
}

async function loadMyActas() {
  const list = document.getElementById("txMyActasList");
  const errorBox = document.getElementById("txMyActasError");
  if (!list) return;

  if (!userHasRole(["cliente"])) {
    list.innerHTML = `<div class="empty-state"><div>🔐</div><h3>Inicia sesión como cliente</h3><p>Aquí aparecen las actas de tus alquileres y compras.</p></div>`;
    return;
  }

  if (list.dataset.owner !== String(state.user.id)) {
    list.dataset.owner = String(state.user.id);
    list.innerHTML = `<div class="empty-state"><div>⏳</div><h3>Cargando tus actas</h3></div>`;
  }

  try {
    myActas = await fetchAllPages("/actas/mias");
    hidePanelError(errorBox);
  } catch (error) {
    if (error.status === 401) handleExpiredSession();
    else showPanelError(errorBox, error);
    return;
  }

  if (!myActas.length) {
    list.innerHTML = `<div class="empty-state"><div>📄</div><h3>Aún no tienes actas</h3><p>Se generan cuando te entregan o recibes de vuelta un vehículo.</p></div>`;
    return;
  }

  list.innerHTML = myActas.map(myActaCard).join("");
  list.querySelectorAll("[data-my-acta-pdf]").forEach(btn => {
    const acta = myActas.find(a => a.id === Number(btn.dataset.myActaPdf));
    btn.addEventListener("click", () => downloadActaPdf(acta, btn));
  });
  list.querySelectorAll("[data-my-acta-accept]").forEach(btn => {
    const acta = myActas.find(a => a.id === Number(btn.dataset.myActaAccept));
    btn.addEventListener("click", () => openConformityDialog(acta));
  });
}

function openConformityDialog(acta) {
  const content = openPanelDialog(`
    <span class="eyebrow">CONFORMIDAD DEL ACTA</span>
    <h2>${escapeHtml(acta.numero)}</h2>
    <p>Vas a aceptar el acta de ${escapeHtml(actaTypeLabel(acta.tipo).toLowerCase())} de ${escapeHtml(acta.vehiculo_codigo)} tal como está en su PDF.
      Queda registrada con tu usuario, la fecha y la huella del PDF, y solo se da una vez. Revisa el PDF antes de aceptar.</p>
    <div class="tx-form-actions">
      <button type="button" class="btn btn-ghost" data-conformity-pdf>Descargar PDF</button>
      <button type="button" class="btn btn-primary" data-conformity-accept>Doy mi conformidad</button>
    </div>
  `);

  content.querySelector("[data-conformity-pdf]").addEventListener("click", async e => {
    await runWithButton(e.currentTarget, "Descargando...", async () => {
      try {
        await downloadFile(`/actas/${acta.id}/pdf`, actaPdfName(acta));
      } catch (error) {
        handleDialogError(content, error);
      }
    });
  });

  content.querySelector("[data-conformity-accept]").addEventListener("click", async e => {
    await runWithButton(e.currentTarget, "Registrando...", async () => {
      try {
        await postJson(`/actas/${acta.id}/conformidad`);
        dialog.close();
        showToast(`Registramos tu conformidad con ${acta.numero}.`);
        await loadMyActas();
      } catch (error) {
        handleDialogError(content, error);
      }
    });
  });
}

// Si este archivo carga después del arranque de app.js, los enlaces por rol se ponen al día.
syncRoleLinks();
