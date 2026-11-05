// Paneles del personal. Se carga después de app.js y reutiliza su cliente:
// api(), escapeHtml(), humanDateTime(), showToast(), handleExpiredSession() y state.

const PANEL_POLL_MS = 5000;
const STAFF_ROLES = ["administrador", "operador"];

Object.assign(adminTitles, {
  operacion: "Mostrador y despacho",
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
    .tx-panel-stack td small,.tx-cell-note{display:block;color:var(--muted);font-size:11px;margin-top:3px}
    .tx-row-actions{display:flex;gap:6px;flex-wrap:wrap}
    .tx-reservation-form select,.tx-reservation-form textarea{padding:11px;border:1px solid var(--line);border-radius:10px;font:inherit;background:#fff}
    .tx-reservation-form textarea{min-height:84px;resize:vertical}
    .tx-form-actions{display:flex;gap:10px;justify-content:flex-end;flex-wrap:wrap}
    .dialog-body .tx-form-actions .btn{width:auto}
    .tx-dialog-error{margin-top:14px}
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
}

async function postJson(path, body) {
  return api(path, {
    method: "POST",
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
