const API_BASE = window.TRANSPORT_API_BASE || "http://127.0.0.1:8000";

const MOCK_VEHICLES = [
  { id: 1, type: "Cicla", icon: "🚲", name: "Urban Ride 3", mode: ["Alquiler"], price: 12000, available: true, availableCount: 3, location: "Cabecera", description: "Cicla urbana cómoda y ligera para trayectos cortos." },
  { id: 2, type: "Monopatín", icon: "🛴", name: "Volt City S2", mode: ["Alquiler"], price: 18000, available: true, availableCount: 2, location: "Centro", description: "Monopatín eléctrico compacto, ideal para recorridos urbanos rápidos." },
  { id: 3, type: "Patines", icon: "🛼", name: "Street Glide", mode: ["Alquiler", "Venta"], price: 10000, salePrice: 265000, available: true, availableCount: 2, location: "San Alonso", description: "Patines recreativos ajustables, pensados para desplazamientos y ocio." },
  { id: 4, type: "Cicla", icon: "🚲", name: "Eco Motion E1", mode: ["Alquiler", "Venta"], price: 28000, salePrice: 2400000, available: false, availableCount: 0, location: "Cabecera", description: "Bicicleta eléctrica asistida para recorridos más largos con menor esfuerzo." },
  { id: 5, type: "Monopatín", icon: "🛴", name: "Pulse Mini", mode: ["Venta"], price: 0, salePrice: 1350000, available: true, availableCount: 1, location: "Provenza", description: "Monopatín eléctrico liviano para movilidad cotidiana." },
  { id: 6, type: "Cicla", icon: "🚲", name: "City Basic", mode: ["Alquiler"], price: 15000, available: true, availableCount: 4, location: "Real de Minas", description: "Bicicleta convencional de mantenimiento simple y uso versátil." },
];

const state = {
  apiOnline: false,
  usingMockCatalog: false,
  token: sessionStorage.getItem("transport_token") || localStorage.getItem("transport_token") || null,
  user: null,
  catalog: [],
  typesFromApi: false,
  rentals: [],
  fleet: [],
  users: [],
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatCOP(value) {
  return Number(value || 0).toLocaleString("es-CO", {
    style: "currency",
    currency: "COP",
    maximumFractionDigits: 0,
  });
}

function iconForType(name = "") {
  const lower = name.toLowerCase();
  if (lower.includes("patín") || lower.includes("patin")) return "🛼";
  if (lower.includes("monopat") || lower.includes("scooter")) return "🛴";
  return "🚲";
}

function roleLabel(role = "") {
  return ({
    cliente: "Cliente",
    administrador: "Administrador",
    operador: "Operador",
    domiciliario: "Domiciliario",
  })[role] || role;
}

function rentalStatusLabel(status = "") {
  return ({
    pendiente_pago: "Pendiente de pago",
    confirmado: "Confirmado",
    en_curso: "En curso",
    finalizado: "Finalizado",
    cancelado: "Cancelado",
    expirado: "Expirado",
  })[status] || status.replaceAll("_", " ");
}

function rentalStatusClass(status = "") {
  if (["confirmado", "en_curso", "finalizado"].includes(status)) return "tx-status-ok";
  if (["cancelado", "expirado"].includes(status)) return "tx-status-off";
  return "tx-status-pending";
}

function colombiaDateISO(date = new Date()) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Bogota",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(date);
  const get = type => parts.find(p => p.type === type)?.value;
  return `${get("year")}-${get("month")}-${get("day")}`;
}

function addDaysISO(iso, days) {
  const [y, m, d] = iso.split("-").map(Number);
  const date = new Date(Date.UTC(y, m - 1, d + days));
  return date.toISOString().slice(0, 10);
}

function humanDateTime(value) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("es-CO", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "America/Bogota",
  }).format(new Date(value));
}

function apiErrorMessage(payload, fallback) {
  if (payload?.error) {
    const action = payload.error.accion ? ` ${payload.error.accion}` : "";
    return `${payload.error.mensaje || fallback}${action}`;
  }
  if (typeof payload?.detail === "string") return payload.detail;
  return fallback;
}

async function api(path, options = {}) {
  const {
    method = "GET",
    auth = false,
    body,
    headers = {},
    timeout = 7000,
  } = options;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  const requestHeaders = { ...headers };

  if (auth) {
    if (!state.token) throw new Error("Debes iniciar sesión.");
    requestHeaders.Authorization = `Bearer ${state.token}`;
  }

  try {
    const response = await fetch(`${API_BASE}${path}`, {
      method,
      body,
      headers: requestHeaders,
      signal: controller.signal,
    });

    const contentType = response.headers.get("content-type") || "";
    const payload = contentType.includes("application/json")
      ? await response.json()
      : await response.text();

    if (!response.ok) {
      const error = new Error(apiErrorMessage(payload, `Error HTTP ${response.status}.`));
      error.status = response.status;
      error.payload = payload;
      throw error;
    }

    state.apiOnline = true;
    return payload;
  } catch (error) {
    if (error.name === "AbortError") {
      throw new Error("El backend tardó demasiado en responder.");
    }
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

function saveSession(token, user, remember) {
  state.token = token;
  state.user = user;
  sessionStorage.removeItem("transport_token");
  localStorage.removeItem("transport_token");

  if (remember) localStorage.setItem("transport_token", token);
  else sessionStorage.setItem("transport_token", token);
}

function clearSession() {
  state.token = null;
  state.user = null;
  state.rentals = [];
  sessionStorage.removeItem("transport_token");
  localStorage.removeItem("transport_token");
  updateSessionUi();
}

function injectClientUi() {
  const main = document.querySelector("main");
  if (!main || document.getElementById("view-cuenta")) return;

  const headerActions = document.querySelector(".header-actions");
  if (headerActions && !document.getElementById("txPendingShortcut")) {
    headerActions.insertAdjacentHTML("afterbegin", `
      <button class="btn btn-soft tx-pending-shortcut" id="txPendingShortcut" type="button" hidden>
        💳 Pendientes <span id="txPendingShortcutCount">0</span>
      </button>
    `);
  }

  main.insertAdjacentHTML("beforeend", `
    <section class="view tx-account-view" id="view-cuenta" data-view="cuenta">
      <section class="page-hero compact tx-account-hero">
        <div>
          <span class="eyebrow">MI CUENTA</span>
          <h1 id="txAccountGreeting">Tu cuenta</h1>
          <p>Consulta tus reservas y, más adelante, administra aquí tus datos, preferencias y ajustes.</p>
          <div class="tx-account-actions">
            <button class="btn btn-primary" data-view-button="catalogo">+ Nuevo alquiler</button>
            <button class="btn btn-ghost" id="txRefreshRentals">Actualizar</button>
            <button class="btn btn-ghost" id="txLogoutClient">Cerrar sesión</button>
          </div>
        </div>
      </section>

      <section class="section tx-rentals-section">
        <div class="section-heading"><div><span class="eyebrow">RESERVAS</span><h2>Tus alquileres</h2></div><p>Gestiona pagos pendientes y revisa el estado de tus reservas.</p></div>
        <div class="tx-account-summary">
          <article><span>Reservas</span><strong id="txRentalTotal">0</strong><small>Total de alquileres</small></article>
          <article><span>Pendientes</span><strong id="txRentalPending">0</strong><small>Esperando pago</small></article>
          <article><span>Activos</span><strong id="txRentalActive">0</strong><small>Confirmados o en curso</small></article>
        </div>
        <div id="txRentalsList" class="tx-rentals-list">
          <div class="empty-state"><div>🧾</div><h3>Inicia sesión para ver tus alquileres</h3></div>
        </div>
      </section>
    </section>
  `);

  const style = document.createElement("style");
  style.id = "tx-v2-styles";
  style.textContent = `
    .tx-account-actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:24px}
    .tx-rentals-section{padding-top:40px;background:#f6f9f7;min-height:55vh}
    .tx-account-summary{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-bottom:20px}
    .tx-account-summary article{display:grid;gap:6px;background:#fff;border:1px solid var(--line);border-radius:16px;padding:20px}
    .tx-account-summary span,.tx-account-summary small{color:var(--muted);font-size:12px}
    .tx-account-summary strong{font-size:32px}
    .tx-rentals-list{display:grid;gap:14px}
    .tx-rental-card{background:#fff;border:1px solid var(--line);border-radius:18px;padding:20px;display:grid;grid-template-columns:1.2fr .9fr auto;gap:18px;align-items:center}
    .tx-rental-main{display:flex;gap:14px;align-items:center}
    .tx-rental-icon{width:56px;height:56px;border-radius:14px;background:#edf7f2;display:grid;place-items:center;font-size:30px}
    .tx-rental-main h3{margin:3px 0 7px}
    .tx-rental-main small,.tx-rental-dates small{color:var(--muted)}
    .tx-rental-dates{display:grid;gap:6px}
    .tx-rental-actions{display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end}
    .tx-status{display:inline-block;padding:6px 9px;border-radius:999px;font-size:10px;font-weight:800}
    .tx-status-ok{background:#e8f7ef;color:#0d7a50}
    .tx-status-pending{background:#fff1d9;color:#996008}
    .tx-status-off{background:#f1f2f2;color:#65746f}
    .tx-reservation-form{display:grid;gap:14px;margin-top:18px;padding-top:18px;border-top:1px solid var(--line)}
    .tx-date-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
    .tx-reservation-form label{display:grid;gap:6px;font-size:12px;font-weight:700}
    .tx-reservation-form input{padding:11px;border:1px solid var(--line);border-radius:10px}
    .tx-availability{padding:12px;border-radius:12px;background:var(--bg);font-size:12px;line-height:1.55}
    .tx-availability.ok{background:#eaf8f1;color:#145f43}
    .tx-availability.no{background:#fff1e8;color:#9a4d21}
    .tx-api-badge{display:inline-flex;align-items:center;gap:6px;font-size:10px;font-weight:800;padding:6px 9px;border-radius:999px;background:#e8f7ef;color:#0d7a50;margin-left:8px}
    .tx-api-badge.off{background:#fff1d9;color:#996008}
    .tx-payment-note{font-size:11px;color:var(--muted);margin-top:8px}
    .tx-account-button{display:inline-flex;align-items:center;gap:7px;white-space:nowrap}
    .tx-account-button span{font-size:16px;line-height:1}
    .tx-pending-shortcut{white-space:nowrap}
    .tx-pending-shortcut span{display:inline-grid;place-items:center;min-width:20px;height:20px;padding:0 6px;margin-left:3px;border-radius:999px;background:#fff;color:#8a5900;font-size:10px;font-weight:800}
    .tx-availability.checking{display:flex;align-items:center;gap:10px;color:var(--muted)}
    .tx-spinner{width:18px;height:18px;border:2px solid rgba(18,86,61,.18);border-top-color:#12563d;border-radius:50%;animation:tx-spin .72s linear infinite;flex:0 0 auto}
    .tx-rental-card.tx-pending-focus{outline:2px solid rgba(217,151,36,.5);box-shadow:0 0 0 5px rgba(217,151,36,.10)}
    @keyframes tx-spin{to{transform:rotate(360deg)}}
    button:disabled{opacity:.55;cursor:not-allowed;transform:none!important}
    @media(max-width:760px){
      .tx-account-summary{grid-template-columns:1fr}
      .tx-rental-card{grid-template-columns:1fr}
      .tx-rental-actions{justify-content:flex-start}
      .tx-date-grid{grid-template-columns:1fr}
    }
  `;
  document.head.appendChild(style);

  document.getElementById("txRefreshRentals")?.addEventListener("click", loadMyRentals);
  document.getElementById("txLogoutClient")?.addEventListener("click", () => {
    clearSession();
    showView("inicio");
    showToast("Sesión cerrada.");
  });

  document.getElementById("txPendingShortcut")?.addEventListener("click", async () => {
    showView("cuenta");
    await loadMyRentals();
    focusFirstPendingRental();
  });
}

injectClientUi();

let views = [...document.querySelectorAll("[data-view]")];
let navLinks = [...document.querySelectorAll("[data-view-link]")];
const footer = document.getElementById("siteFooter");
const header = document.querySelector(".site-header");
const mainNav = document.getElementById("mainNav");
const menuToggle = document.getElementById("menuToggle");
const headerLoginButton = document.querySelector(".header-actions [data-view-button='login']");

function refreshViewCollections() {
  views = [...document.querySelectorAll("[data-view]")];
  navLinks = [...document.querySelectorAll("[data-view-link]")];
}

function showView(name) {
  refreshViewCollections();
  views.forEach(v => v.classList.toggle("active", v.dataset.view === name));
  navLinks.forEach(a => a.classList.toggle("active", a.dataset.viewLink === name));

  const special = name === "login" || name === "admin";
  if (footer) footer.style.display = special ? "none" : "";
  if (header) header.style.display = name === "admin" ? "none" : "";
  mainNav?.classList.remove("open");
  menuToggle?.setAttribute("aria-expanded", "false");
  window.scrollTo({ top: 0, behavior: "auto" });

  if (name === "catalogo") refreshCatalog();
  if (name === "cuenta") loadMyRentals();
  if (name === "admin") loadAdminData();
  if (name === "entregas") loadCourierPanel(); // paneles.js
  if (name === "mis-actas") loadMyActas(); // paneles.js
}

document.querySelectorAll("[data-view-button], [data-view-link]").forEach(el => {
  el.addEventListener("click", e => {
    e.preventDefault();
    const target = el.dataset.viewButton || el.dataset.viewLink;
    if (!target) return;
    history.replaceState(null, "", `#${target}`);
    showView(target);
  });
});

document.querySelectorAll("[data-anchor-link]").forEach(el => {
  el.addEventListener("click", e => {
    e.preventDefault();
    const id = el.dataset.anchorLink;
    showView("inicio");
    setTimeout(() => document.getElementById(id)?.scrollIntoView({ behavior: "smooth" }), 50);
  });
});

menuToggle?.addEventListener("click", () => {
  const open = mainNav.classList.toggle("open");
  menuToggle.setAttribute("aria-expanded", String(open));
});

function syncPendingShortcut(count = 0) {
  const shortcut = document.getElementById("txPendingShortcut");
  const badge = document.getElementById("txPendingShortcutCount");
  if (!shortcut || !badge) return;

  badge.textContent = String(count);
  shortcut.hidden = !(state.user?.rol === "cliente" && count > 0);
}

async function refreshPendingShortcut() {
  if (!state.token || state.user?.rol !== "cliente") {
    syncPendingShortcut(0);
    return;
  }

  try {
    const data = await api("/alquileres/mios?estado=pendiente_pago&tamano=100", { auth: true });
    syncPendingShortcut(data.total ?? data.elementos?.length ?? 0);
  } catch (error) {
    console.warn("No se pudo actualizar el contador de pendientes.", error);
  }
}

function focusFirstPendingRental() {
  const first = document.querySelector('[data-rental-status="pendiente_pago"]');
  if (!first) return;
  first.classList.add("tx-pending-focus");
  first.scrollIntoView({ behavior: "smooth", block: "center" });
  setTimeout(() => first.classList.remove("tx-pending-focus"), 1800);
}

function updateSessionUi() {
  syncRoleLinks(); // paneles.js
  if (!headerLoginButton) return;

  if (!state.user) {
    headerLoginButton.innerHTML = '<span aria-hidden="true">👤</span> Tú';
    headerLoginButton.setAttribute("aria-label", "Iniciar sesión o abrir tu cuenta");
    headerLoginButton.classList.add("tx-account-button");
    headerLoginButton.dataset.viewButton = "login";
    syncPendingShortcut(0);
    return;
  }

  if (state.user.rol === "cliente") {
    headerLoginButton.innerHTML = '<span aria-hidden="true">👤</span> Tú';
    headerLoginButton.setAttribute("aria-label", "Abrir tu cuenta");
    headerLoginButton.classList.add("tx-account-button");
    headerLoginButton.dataset.viewButton = "cuenta";
  } else if (["administrador", "operador"].includes(state.user.rol)) {
    headerLoginButton.textContent = "Panel";
    headerLoginButton.removeAttribute("aria-label");
    headerLoginButton.classList.remove("tx-account-button");
    headerLoginButton.dataset.viewButton = "admin";
  } else {
    headerLoginButton.innerHTML = '<span aria-hidden="true">👤</span> Tú';
    headerLoginButton.setAttribute("aria-label", "Abrir tu cuenta");
    headerLoginButton.classList.add("tx-account-button");
    headerLoginButton.dataset.viewButton = state.user.rol === "domiciliario" ? "entregas" : "inicio";
  }

  const greeting = document.getElementById("txAccountGreeting");
  if (greeting) greeting.textContent = `Hola, ${state.user.nombre_completo.split(" ")[0]}. Esta es tu cuenta.`;
}

// ---------------------------------------------------------
// Portal institucional
// ---------------------------------------------------------

async function loadPortal() {
  try {
    const data = await api("/portal");
    const sections = Object.fromEntries((data.secciones || []).map(s => [s.seccion, s]));

    const cards = document.querySelectorAll(".institutional-card");
    if (sections.mision && cards[0]) {
      cards[0].querySelector("h2").textContent = sections.mision.titulo;
      cards[0].querySelector("p").textContent = sections.mision.contenido;
    }
    if (sections.vision && cards[1]) {
      cards[1].querySelector("h2").textContent = sections.vision.titulo;
      cards[1].querySelector("p").textContent = sections.vision.contenido;
    }
    if (sections.contacto) {
      const contact = document.querySelector(".contact > div:first-child");
      if (contact) {
        contact.querySelector("h2").textContent = sections.contacto.titulo;
        contact.querySelector("p").textContent = sections.contacto.contenido;
      }
    }
  } catch (error) {
    console.warn("Portal API no disponible.", error);
  }
}

// ---------------------------------------------------------
// Catálogo real
// ---------------------------------------------------------

const catalogGrid = document.getElementById("catalogGrid");
const typeFilter = document.getElementById("typeFilter");
const modeFilter = document.getElementById("modeFilter");
const priceFilter = document.getElementById("priceFilter");
const priceLabel = document.getElementById("priceLabel");
const availableFilter = document.getElementById("availableFilter");
const resultCount = document.getElementById("resultCount");
const emptyState = document.getElementById("emptyState");
const dialog = document.getElementById("vehicleDialog");

function normalizeModel(m) {
  return {
    id: m.id,
    type: m.tipo?.nombre || "Vehículo",
    icon: iconForType(m.tipo?.nombre),
    name: m.nombre,
    brand: m.marca,
    mode: [m.se_alquila ? "Alquiler" : null, m.se_vende ? "Venta" : null].filter(Boolean),
    price: m.tarifa_diaria || 0,
    salePrice: m.precio_venta,
    available: Number(m.disponibles_hoy) > 0,
    availableCount: Number(m.disponibles_hoy || 0),
    location: null,
    description: m.descripcion || "Sin descripción.",
    imageUrl: m.imagen_url,
    raw: m,
  };
}

function catalogCard(model) {
  const primaryPrice = model.price
    ? `${formatCOP(model.price)} <small>/día</small>`
    : model.salePrice
      ? formatCOP(model.salePrice)
      : "Consultar";

  return `
    <article class="catalog-card">
      <div class="catalog-card-media">
        <span class="availability ${model.available ? "ok" : "no"}">
          ${model.available ? `● ${model.availableCount} disponible${model.availableCount === 1 ? "" : "s"} hoy` : "● Sin disponibilidad hoy"}
        </span>
        ${model.imageUrl
          ? `<img src="${escapeHtml(model.imageUrl)}" alt="${escapeHtml(model.name)}" style="max-width:82%;max-height:150px;object-fit:contain">`
          : model.icon}
      </div>
      <div class="catalog-card-body">
        <small>${escapeHtml(model.type)}</small>
        <h3>${escapeHtml(model.name)}</h3>
        <div class="catalog-card-meta">
          <span>${escapeHtml(model.mode.join(" · ") || "Consultar")}</span>
          ${model.brand ? `<span>${escapeHtml(model.brand)}</span>` : ""}
        </div>
        <div class="catalog-card-footer">
          <div>
            <div class="price">${primaryPrice}</div>
            ${model.salePrice && model.price ? `<small>Venta: ${formatCOP(model.salePrice)}</small>` : ""}
          </div>
          <button data-detail="${model.id}">Ver detalle</button>
        </div>
      </div>
    </article>
  `;
}

function renderCatalog(items, total = items.length) {
  if (!catalogGrid) return;
  state.catalog = items;
  resultCount.textContent = total;
  emptyState.hidden = items.length !== 0;
  catalogGrid.innerHTML = items.map(catalogCard).join("");

  catalogGrid.querySelectorAll("[data-detail]").forEach(btn => {
    btn.addEventListener("click", () => openVehicle(Number(btn.dataset.detail)));
  });
}

function renderMockCatalog() {
  state.usingMockCatalog = true;

  const max = Number(priceFilter.value);
  const filtered = MOCK_VEHICLES.filter(v =>
    (typeFilter.value === "todos" || v.type === typeFilter.value) &&
    (modeFilter.value === "todos" || v.mode.includes(modeFilter.value)) &&
    (!v.price || v.price <= max) &&
    (!availableFilter.checked || v.available)
  );

  renderCatalog(filtered);
  markCatalogSource(false);
}

function markCatalogSource(real) {
  const heroText = document.querySelector("#view-catalogo .page-hero p");
  if (!heroText) return;

  heroText.innerHTML = real
    ? `Filtra por tipo, modalidad y tarifa. <span class="tx-api-badge">● API conectada</span>`
    : `Mostrando datos de demostración. <span class="tx-api-badge off">● API sin conexión</span>`;
}

async function loadTypes() {
  try {
    const data = await api("/catalogo/tipos?tamano=100");
    typeFilter.innerHTML = `<option value="todos">Todos</option>` +
      data.elementos.map(t => `<option value="${t.id}">${escapeHtml(t.nombre)}</option>`).join("");
    typeFilter.dataset.api = "true";
    state.typesFromApi = true;
  } catch {
    state.typesFromApi = false;
    typeFilter.dataset.api = "false";
  }
}

async function refreshCatalog() {
  if (!catalogGrid) return;

  priceLabel.textContent = formatCOP(Number(priceFilter.value));
  const params = new URLSearchParams({ tamano: "100" });

  if (state.typesFromApi && typeFilter.value !== "todos") params.set("tipo_id", typeFilter.value);
  if (modeFilter.value !== "todos") params.set("modalidad", modeFilter.value.toLowerCase());
  if (modeFilter.value !== "Venta") params.set("tarifa_max", priceFilter.value);
  if (availableFilter.checked) params.set("solo_disponibles", "true");

  try {
    catalogGrid.innerHTML = `<div class="empty-state"><div>⏳</div><h3>Cargando catálogo</h3><p>Consultando el backend...</p></div>`;
    const data = await api(`/catalogo/modelos?${params.toString()}`);
    state.usingMockCatalog = false;
    renderCatalog(data.elementos.map(normalizeModel), data.total);
    markCatalogSource(true);
  } catch (error) {
    console.warn("Catálogo real no disponible; fallback mock.", error);
    renderMockCatalog();
  }
}

let catalogTimer;
[typeFilter, modeFilter, priceFilter, availableFilter].forEach(el => el?.addEventListener("input", () => {
  clearTimeout(catalogTimer);
  catalogTimer = setTimeout(refreshCatalog, 180);
}));

document.getElementById("clearFilters")?.addEventListener("click", () => {
  typeFilter.value = "todos";
  modeFilter.value = "todos";
  priceFilter.value = "80000";
  availableFilter.checked = false;
  refreshCatalog();
});

// ---------------------------------------------------------
// Detalle + disponibilidad + creación de alquiler
// ---------------------------------------------------------

function reservationBlock(model, detail) {
  if (!detail?.se_alquila) {
    return `<div class="tx-availability">Este modelo no está habilitado para alquiler.</div>`;
  }

  const today = colombiaDateISO();
  const tomorrow = addDaysISO(today, 1);

  return `
    <div class="tx-reservation-form">
      <strong>Reservar este modelo</strong>
      <div class="tx-date-grid">
        <label>Fecha de inicio
          <input type="date" id="txStartDate" min="${today}" value="${today}">
        </label>
        <label>Fecha de fin
          <input type="date" id="txEndDate" min="${today}" value="${tomorrow}">
        </label>
      </div>
      <div id="txAvailability" class="tx-availability checking">
        <span class="tx-spinner" aria-hidden="true"></span>
        <span>Verificando disponibilidad para estas fechas...</span>
      </div>
      <button class="btn btn-primary" id="txCreateRental" disabled>Verificando disponibilidad...</button>
    </div>
  `;
}

async function openVehicle(id) {
  const local = state.catalog.find(x => x.id === id) || MOCK_VEHICLES.find(x => x.id === id);
  if (!local) return;

  if (state.usingMockCatalog) {
    document.getElementById("dialogContent").innerHTML = `
      <div class="dialog-hero">${local.icon}</div>
      <div class="dialog-body">
        <span class="eyebrow">${escapeHtml(local.type.toUpperCase())}</span>
        <h2>${escapeHtml(local.name)}</h2>
        <p>${escapeHtml(local.description)}</p>
        <div class="tx-availability">El backend está desconectado. Puedes explorar el catálogo, pero no crear una reserva real.</div>
      </div>`;
    dialog.showModal();
    return;
  }

  try {
    const raw = await api(`/catalogo/modelos/${id}`);
    const model = normalizeModel(raw);

    document.getElementById("dialogContent").innerHTML = `
      <div class="dialog-hero">${model.icon}</div>
      <div class="dialog-body">
        <span class="eyebrow">${escapeHtml(model.type.toUpperCase())}</span>
        <h2>${escapeHtml(model.name)}</h2>
        <p>${escapeHtml(model.description)}</p>
        <div class="dialog-specs">
          <div><small>TARIFA</small><strong>${model.price ? `${formatCOP(model.price)}/día` : "No alquila"}</strong></div>
          <div><small>VENTA</small><strong>${model.salePrice ? formatCOP(model.salePrice) : "No disponible"}</strong></div>
          <div><small>LIBRES HOY</small><strong>${raw.disponibles_hoy}</strong></div>
        </div>
        ${reservationBlock(model, raw)}
      </div>`;

    dialog.showModal();

    if (raw.se_alquila) {
      setupReservationForm(model);
    }
  } catch (error) {
    showToast(error.message);
  }
}

function setupReservationForm(model) {
  const start = document.getElementById("txStartDate");
  const end = document.getElementById("txEndDate");
  const availabilityBox = document.getElementById("txAvailability");
  const createButton = document.getElementById("txCreateRental");

  // Delay mínimo intencional para que en la demo se perciba la validación.
  const DEMO_AVAILABILITY_DELAY_MS = 900;
  const INPUT_DEBOUNCE_MS = 350;

  let availabilityTimer;
  let requestVersion = 0;

  function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  function showCheckingState() {
    createButton.disabled = true;
    createButton.dataset.ready = "false";
    createButton.textContent = "Verificando disponibilidad...";
    availabilityBox.className = "tx-availability checking";
    availabilityBox.innerHTML = `
      <span class="tx-spinner" aria-hidden="true"></span>
      <span>Verificando disponibilidad para estas fechas...</span>
    `;
  }

  async function checkAvailability() {
    if (!start.value || !end.value) {
      createButton.disabled = true;
      availabilityBox.className = "tx-availability no";
      availabilityBox.textContent = "Selecciona ambas fechas.";
      return;
    }

    const currentVersion = ++requestVersion;
    showCheckingState();

    try {
      const params = new URLSearchParams({
        fecha_inicio: start.value,
        fecha_fin: end.value,
      });

      // La consulta real y el delay artificial ocurren en paralelo:
      // nunca ralentiza más de 900 ms si el backend ya tarda más que eso.
      const [data] = await Promise.all([
        api(`/catalogo/modelos/${model.id}/disponibilidad?${params}`),
        sleep(DEMO_AVAILABILITY_DELAY_MS),
      ]);

      // Si el usuario cambió fechas mientras esperaba, ignoramos la respuesta vieja.
      if (currentVersion !== requestVersion) return;

      if (data.disponible) {
        const subtotal = model.price * data.dias;
        availabilityBox.className = "tx-availability ok";
        availabilityBox.innerHTML = `
          <strong>${data.unidades_libres} unidad${data.unidades_libres === 1 ? "" : "es"} libre${data.unidades_libres === 1 ? "" : "s"}.</strong>
          ${data.dias} día${data.dias === 1 ? "" : "s"} × ${formatCOP(model.price)}
          = <strong>${formatCOP(subtotal)}</strong>.
        `;
        createButton.disabled = false;
        createButton.dataset.ready = "true";
        createButton.textContent = `Reservar por ${formatCOP(subtotal)}`;
      } else {
        availabilityBox.className = "tx-availability no";
        availabilityBox.textContent = "No hay unidades libres durante todo ese rango.";
        createButton.disabled = true;
        createButton.textContent = "Sin disponibilidad";
      }
    } catch (error) {
      if (currentVersion !== requestVersion) return;
      availabilityBox.className = "tx-availability no";
      availabilityBox.textContent = error.message;
      createButton.disabled = true;
      createButton.textContent = "No se pudo verificar";
    }
  }

  function scheduleAvailabilityCheck() {
    requestVersion += 1;
    clearTimeout(availabilityTimer);
    showCheckingState();
    availabilityTimer = setTimeout(checkAvailability, INPUT_DEBOUNCE_MS);
  }

  start.addEventListener("change", () => {
    end.min = start.value;
    if (end.value < start.value) end.value = start.value;
    scheduleAvailabilityCheck();
  });

  end.addEventListener("change", scheduleAvailabilityCheck);

  createButton.addEventListener("click", async () => {
    if (createButton.dataset.ready !== "true") return;

    if (!state.user) {
      dialog.close();
      showView("login");
      showToast("Inicia sesión como cliente para reservar.");
      return;
    }

    if (state.user.rol !== "cliente") {
      showToast("Las reservas desde el catálogo se crean con una cuenta de cliente.");
      return;
    }

    createButton.disabled = true;
    createButton.textContent = "Creando reserva...";

    try {
      const rental = await api("/alquileres", {
        method: "POST",
        auth: true,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          modelo_id: model.id,
          fecha_inicio: start.value,
          fecha_fin: end.value,
        }),
      });

      dialog.close();
      showToast(`Reserva #${rental.id} creada. Tienes 15 minutos para pagar.`);
      showView("cuenta");
      await loadMyRentals();
      await refreshPendingShortcut();
      focusFirstPendingRental();
      await refreshCatalog();
    } catch (error) {
      if (error.status === 401) handleExpiredSession();
      else showToast(error.message);
      scheduleAvailabilityCheck();
    }
  });

  // Primera validación automática al abrir la ficha.
  scheduleAvailabilityCheck();
}

document.getElementById("closeDialog")?.addEventListener("click", () => dialog.close());
dialog?.addEventListener("click", e => {
  if (e.target === dialog) dialog.close();
});

// ---------------------------------------------------------
// Login real
// ---------------------------------------------------------

const loginForm = document.getElementById("loginForm");
const emailInput = loginForm?.querySelector('input[type="email"]');
const passwordInput = document.getElementById("passwordInput");
const rememberInput = loginForm?.querySelector('input[type="checkbox"]');
const loginButton = loginForm?.querySelector('button[type="submit"]');
const demoNote = document.querySelector(".demo-note");

if (emailInput && emailInput.value === "admin@transportexperience.test") {
  emailInput.value = "cliente@transportexperience.test";
}

if (demoNote) {
  demoNote.innerHTML = `
    <strong>Backend real</strong>
    <p id="txBackendStatus">Comprobando conexión...</p>
    <p><strong>Cliente de prueba:</strong> cliente@transportexperience.test · Desarrollo2026!</p>
  `;
}

document.getElementById("togglePassword")?.addEventListener("click", e => {
  const show = passwordInput.type === "password";
  passwordInput.type = show ? "text" : "password";
  e.target.textContent = show ? "Ocultar" : "Mostrar";
});

loginForm?.addEventListener("submit", async e => {
  e.preventDefault();

  loginButton.disabled = true;
  const original = loginButton.textContent;
  loginButton.textContent = "Ingresando...";

  try {
    const body = new URLSearchParams({
      username: emailInput.value.trim(),
      password: passwordInput.value,
    });

    const data = await api("/autenticacion/token", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    });

    saveSession(data.access_token, data.usuario, rememberInput.checked);
    updateSessionUi();

    if (data.usuario.rol === "cliente") {
      await refreshPendingShortcut();
      showView("cuenta");
      showToast("Sesión iniciada. Ya puedes reservar y pagar alquileres.");
    } else if (["administrador", "operador"].includes(data.usuario.rol)) {
      showView("admin");
      showToast(`Sesión iniciada como ${roleLabel(data.usuario.rol)}.`);
    } else {
      showView(data.usuario.rol === "domiciliario" ? "entregas" : "inicio");
      showToast(`Sesión iniciada como ${roleLabel(data.usuario.rol)}.`);
    }
  } catch (error) {
    showToast(error.message);
  } finally {
    loginButton.disabled = false;
    loginButton.textContent = original;
  }
});

// ---------------------------------------------------------
// Mis alquileres + pago + cancelación
// ---------------------------------------------------------

function rentalCard(rental) {
  const canPay = rental.estado === "pendiente_pago";
  const canCancel = rental.estado === "pendiente_pago";
  const icon = iconForType(rental.vehiculo?.modelo?.nombre || "");

  return `
    <article class="tx-rental-card" data-rental-status="${escapeHtml(rental.estado)}">
      <div class="tx-rental-main">
        <div class="tx-rental-icon">${icon}</div>
        <div>
          <small>Reserva #${rental.id} · ${escapeHtml(rental.vehiculo?.codigo || "")}</small>
          <h3>${escapeHtml(rental.vehiculo?.modelo?.nombre || "Vehículo")}</h3>
          <span class="tx-status ${rentalStatusClass(rental.estado)}">${escapeHtml(rentalStatusLabel(rental.estado))}</span>
        </div>
      </div>
      <div class="tx-rental-dates">
        <strong>${escapeHtml(rental.fecha_inicio)} → ${escapeHtml(rental.fecha_fin)}</strong>
        <span>${rental.dias} día${rental.dias === 1 ? "" : "s"} · ${formatCOP(rental.total)}</span>
        ${rental.expira_en && rental.estado === "pendiente_pago"
          ? `<small>Reserva válida hasta ${escapeHtml(humanDateTime(rental.expira_en))}</small>`
          : ""}
      </div>
      <div class="tx-rental-actions">
        ${canPay ? `<button class="btn btn-primary small-btn" data-pay-rental="${rental.id}">Pagar</button>` : ""}
        ${canCancel ? `<button class="outline-danger" data-cancel-rental="${rental.id}">Cancelar</button>` : ""}
      </div>
    </article>
  `;
}

function renderRentals() {
  const list = document.getElementById("txRentalsList");
  const total = document.getElementById("txRentalTotal");
  const pending = document.getElementById("txRentalPending");
  const active = document.getElementById("txRentalActive");

  const pendingCount = state.rentals.filter(r => r.estado === "pendiente_pago").length;
  total.textContent = state.rentals.length;
  pending.textContent = pendingCount;
  active.textContent = state.rentals.filter(r => ["confirmado", "en_curso"].includes(r.estado)).length;
  syncPendingShortcut(pendingCount);

  if (!state.rentals.length) {
    list.innerHTML = `
      <div class="empty-state">
        <div>🚲</div>
        <h3>Aún no tienes alquileres</h3>
        <p>Explora el catálogo y crea tu primera reserva.</p>
        <button class="btn btn-primary" data-view-button="catalogo">Ir al catálogo</button>
      </div>`;
    list.querySelector("[data-view-button]")?.addEventListener("click", () => showView("catalogo"));
    return;
  }

  list.innerHTML = state.rentals.map(rentalCard).join("");

  list.querySelectorAll("[data-pay-rental]").forEach(btn => {
    btn.addEventListener("click", () => payRental(Number(btn.dataset.payRental)));
  });

  list.querySelectorAll("[data-cancel-rental]").forEach(btn => {
    btn.addEventListener("click", () => cancelRental(Number(btn.dataset.cancelRental)));
  });
}

async function loadMyRentals() {
  const list = document.getElementById("txRentalsList");
  if (!list) return;

  if (!state.user || state.user.rol !== "cliente") {
    list.innerHTML = `<div class="empty-state"><div>🔐</div><h3>Inicia sesión como cliente</h3><p>Necesitas una sesión de cliente para consultar tus alquileres.</p></div>`;
    return;
  }

  list.innerHTML = `<div class="empty-state"><div>⏳</div><h3>Cargando tus alquileres</h3></div>`;

  try {
    const data = await api("/alquileres/mios?tamano=100", { auth: true });
    state.rentals = [...(data.elementos || [])].sort((a, b) => {
      const aPending = a.estado === "pendiente_pago" ? 0 : 1;
      const bPending = b.estado === "pendiente_pago" ? 0 : 1;
      if (aPending !== bPending) return aPending - bPending;
      return new Date(b.creado_en) - new Date(a.creado_en);
    });
    renderRentals();
  } catch (error) {
    if (error.status === 401) handleExpiredSession();
    else {
      list.innerHTML = `<div class="empty-state"><div>⚠️</div><h3>No se pudieron cargar</h3><p>${escapeHtml(error.message)}</p></div>`;
    }
  }
}

async function payRental(id) {
  const rental = state.rentals.find(r => r.id === id);
  if (!rental) return;

  const confirmed = window.confirm(`Vas a pagar ${formatCOP(rental.total)} por la reserva #${id}. ¿Continuar?`);
  if (!confirmed) return;

  try {
    const config = await api("/pagos/configuracion");
    if (!config.metodos?.length) {
      showToast("No hay métodos de pago habilitados.");
      return;
    }

    if (config.proveedor !== "falso") {
      showToast("La UI de tokenización Wompi todavía no está implementada. Para pruebas locales usa PAGOS_PROVEEDOR=falso.");
      return;
    }

    const method = config.metodos[0];
    const result = await api(`/alquileres/${id}/pago`, {
      method: "POST",
      auth: true,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ metodo_pago: method }),
    });

    const status = result.pago?.estado || "desconocido";
    showToast(status === "aprobado"
      ? `Pago aprobado. La reserva #${id} quedó confirmada.`
      : `Pago registrado con estado: ${status}.`);

    await loadMyRentals();
    await refreshPendingShortcut();
    await refreshCatalog();
  } catch (error) {
    if (error.status === 401) handleExpiredSession();
    else showToast(error.message);
  }
}

async function cancelRental(id) {
  const rental = state.rentals.find(r => r.id === id);
  if (!rental) return;

  const reason = window.prompt("Motivo de cancelación (opcional):", "Cambio de planes");
  if (reason === null) return;

  try {
    await api(`/alquileres/${id}/cancelacion`, {
      method: "POST",
      auth: true,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ motivo: reason.trim() || null }),
    });

    showToast(`Reserva #${id} cancelada.`);
    await loadMyRentals();
    await refreshPendingShortcut();
    await refreshCatalog();
  } catch (error) {
    if (error.status === 401) handleExpiredSession();
    else showToast(error.message);
  }
}

// ---------------------------------------------------------
// Panel administrativo: conserva la UI y trae datos reales
// ---------------------------------------------------------

const adminTitles = {
  resumen: "Resumen",
  usuarios: "Usuarios y roles",
  flota: "Gestión de flota",
  mantenimiento: "Mantenimiento",
};

document.querySelectorAll("[data-admin-tab]").forEach(btn => {
  btn.addEventListener("click", async () => {
    const tab = btn.dataset.adminTab;
    if (!tab) return;

    if (tab === "usuarios" && state.user?.rol !== "administrador") {
      showToast("Solo un administrador puede consultar usuarios.");
      return;
    }

    if (btn.dataset.roles && !btn.dataset.roles.split(",").includes(state.user?.rol)) {
      showToast("Tu rol no tiene acceso a esta sección.");
      return;
    }

    document.querySelectorAll(".admin-nav [data-admin-tab]").forEach(b => {
      b.classList.toggle("active", b.dataset.adminTab === tab);
    });

    document.querySelectorAll("[data-admin-content]").forEach(c => {
      c.classList.toggle("active", c.dataset.adminContent === tab);
    });

    document.getElementById("adminTitle").textContent = adminTitles[tab] || tab;

    if (tab === "usuarios") await loadAdminUsers();
    if (tab === "flota") await loadAdminFleet();
    onPanelTabShown(tab); // paneles.js
  });
});

function updateAdminIdentity() {
  if (!state.user) return;
  const strong = document.querySelector(".admin-user strong");
  const small = document.querySelector(".admin-user small");
  const avatar = document.querySelector(".admin-user .avatar");

  if (strong) strong.textContent = state.user.nombre_completo;
  if (small) small.textContent = roleLabel(state.user.rol);
  if (avatar) {
    avatar.textContent = state.user.nombre_completo
      .split(/\s+/)
      .slice(0, 2)
      .map(x => x[0])
      .join("")
      .toUpperCase();
  }
}

async function loadAdminUsers() {
  if (!state.token || state.user?.rol !== "administrador") return;

  try {
    const data = await api("/usuarios?tamano=100", { auth: true });
    state.users = data.elementos || [];
    const tbody = document.querySelector('[data-admin-content="usuarios"] tbody');
    if (!tbody) return;

    tbody.innerHTML = state.users.map(u => `
      <tr>
        <td><strong>${escapeHtml(u.nombre_completo)}</strong><small>${escapeHtml(u.correo)}</small></td>
        <td>${escapeHtml(roleLabel(u.rol))}</td>
        <td><span class="status-chip ${u.activo ? "active-chip" : "inactive-chip"}">${u.activo ? "Activo" : "Inactivo"}</span></td>
        <td><button class="table-action" disabled>Editar</button></td>
      </tr>
    `).join("");
  } catch (error) {
    showToast(error.message);
  }
}

async function loadAdminFleet() {
  if (!state.token || !["administrador", "operador"].includes(state.user?.rol)) return;

  try {
    const data = await api("/vehiculos?tamano=100", { auth: true });
    state.fleet = data.elementos || [];
    const grid = document.querySelector('[data-admin-content="flota"] .fleet-grid');
    if (!grid) return;

    grid.innerHTML = state.fleet.map(v => `
      <article>
        <div class="vehicle-icon">${iconForType(v.modelo?.nombre || "")}</div>
        <div>
          <small>${escapeHtml(v.codigo)}</small>
          <h4>${escapeHtml(v.modelo?.nombre || "Modelo")}</h4>
          <span class="status-chip ${v.estado === "mantenimiento" ? "maintenance-chip" : "active-chip"}">${escapeHtml(v.estado.replaceAll("_", " "))}</span>
        </div>
        ${["disponible", "reservado", "alquilado"].includes(v.estado)
          ? `<button class="outline-danger" data-inactivate-real="${v.id}" data-code="${escapeHtml(v.codigo)}">Inactivar</button>`
          : `<button class="table-action" disabled>${escapeHtml(v.estado)}</button>`}
      </article>
    `).join("");

    grid.querySelectorAll("[data-inactivate-real]").forEach(btn => {
      btn.addEventListener("click", () => inactivateVehicle(Number(btn.dataset.inactivateReal), btn.dataset.code));
    });

    updateAdminMetrics();
  } catch (error) {
    showToast(error.message);
  }
}

async function inactivateVehicle(id, code) {
  const reason = window.prompt(`Motivo para inactivar ${code}:`, "Mantenimiento preventivo");
  if (reason === null) return;
  if (reason.trim().length < 5) {
    showToast("El motivo debe tener al menos 5 caracteres.");
    return;
  }

  try {
    await api(`/vehiculos/${id}/inactivacion`, {
      method: "POST",
      auth: true,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ motivo: reason.trim() }),
    });
    showToast(`${code} pasó a mantenimiento.`);
    await Promise.all([loadAdminFleet(), refreshCatalog()]);
  } catch (error) {
    showToast(error.message);
  }
}

function updateAdminMetrics() {
  const values = document.querySelectorAll('[data-admin-content="resumen"] .metric-grid strong');
  const available = state.fleet.filter(v => v.estado === "disponible").length;
  const maintenance = state.fleet.filter(v => v.estado === "mantenimiento").length;
  if (values[0]) values[0].textContent = available;
  if (values[1]) values[1].textContent = maintenance;
}

async function loadAdminData() {
  if (!state.user || !["administrador", "operador"].includes(state.user.rol)) return;
  updateAdminIdentity();
  syncPanelTabs(); // paneles.js
  await loadAdminFleet();
  if (state.user.rol === "administrador") await loadAdminUsers();
}

document.querySelector(".logout")?.addEventListener("click", () => {
  clearSession();
  showView("inicio");
  showToast("Sesión cerrada.");
});

// ---------------------------------------------------------
// Salud y sesión
// ---------------------------------------------------------

async function checkHealth() {
  const status = document.getElementById("txBackendStatus");
  try {
    const health = await api("/salud", { timeout: 3500 });
    state.apiOnline = health?.estado === "ok";
    if (status) status.textContent = state.apiOnline
      ? `Backend conectado en ${API_BASE}.`
      : `Backend respondió: ${health?.estado || "estado desconocido"}.`;
  } catch {
    state.apiOnline = false;
    if (status) status.textContent = `Backend sin conexión en ${API_BASE}. El catálogo usará datos demo y no se podrán crear reservas reales.`;
  }
}

async function restoreSession() {
  if (!state.token) return;
  try {
    state.user = await api("/usuarios/yo", { auth: true });
    updateSessionUi();
    if (state.user.rol === "cliente") await refreshPendingShortcut();
  } catch {
    clearSession();
  }
}

function handleExpiredSession() {
  clearSession();
  showView("login");
  showToast("La sesión expiró. Inicia sesión nuevamente.");
}

let toastTimer;
function showToast(message) {
  const toast = document.getElementById("toast");
  if (!toast) return;
  toast.textContent = message;
  toast.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("show"), 4500);
}
window.showToast = showToast;

(async function init() {
  await Promise.allSettled([
    checkHealth(),
    loadPortal(),
    loadTypes(),
    restoreSession(),
  ]);

  updateSessionUi();

  const initial = location.hash.replace("#", "");
  const allowed = ["inicio", "catalogo", "login", "admin", "cuenta", "entregas", "mis-actas"];
  const target = allowed.includes(initial) ? initial : "inicio";

  if (target === "admin" && !["administrador", "operador"].includes(state.user?.rol)) {
    showView("inicio");
  } else if (target === "cuenta" && state.user?.rol !== "cliente") {
    showView("inicio");
  } else if (target === "entregas" && state.user?.rol !== "domiciliario") {
    showView("inicio");
  } else if (target === "mis-actas" && state.user?.rol !== "cliente") {
    showView("inicio");
  } else {
    showView(target);
  }

  if (target !== "catalogo") refreshCatalog();
})();
