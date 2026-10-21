const API_BASE = window.TRANSPORT_API_BASE || 'http://127.0.0.1:8000';

const mockVehicles = [
  { id: 1, type: 'Cicla', icon: '🚲', name: 'Urban Ride 3', mode: ['Alquiler'], price: 12000, available: true, location: 'Cabecera', battery: null, description: 'Cicla urbana cómoda y ligera para trayectos cortos.' },
  { id: 2, type: 'Monopatín', icon: '🛴', name: 'Volt City S2', mode: ['Alquiler'], price: 18000, available: true, location: 'Centro', battery: 92, description: 'Monopatín eléctrico compacto, ideal para recorridos urbanos rápidos.' },
  { id: 3, type: 'Patines', icon: '🛼', name: 'Street Glide', mode: ['Alquiler', 'Venta'], price: 10000, salePrice: 265000, available: true, location: 'San Alonso', battery: null, description: 'Patines recreativos ajustables, pensados para desplazamientos y ocio.' },
  { id: 4, type: 'Cicla', icon: '🚲', name: 'Eco Motion E1', mode: ['Alquiler', 'Venta'], price: 28000, salePrice: 2400000, available: false, location: 'Cabecera', battery: 76, description: 'Bicicleta eléctrica asistida para recorridos más largos con menor esfuerzo.' },
  { id: 5, type: 'Monopatín', icon: '🛴', name: 'Pulse Mini', mode: ['Venta'], price: 68000, salePrice: 1350000, available: true, location: 'Provenza', battery: 84, description: 'Monopatín eléctrico liviano para movilidad cotidiana.' },
  { id: 6, type: 'Cicla', icon: '🚲', name: 'City Basic', mode: ['Alquiler'], price: 15000, available: true, location: 'Real de Minas', battery: null, description: 'Bicicleta convencional de mantenimiento simple y uso versátil.' },
];

const state = {
  apiOnline: false,
  token: sessionStorage.getItem('transport_token') || localStorage.getItem('transport_token') || null,
  user: null,
  catalogUsesApi: false,
  catalog: [],
  fleet: [],
  users: [],
};

const views = [...document.querySelectorAll('[data-view]')];
const navLinks = [...document.querySelectorAll('[data-view-link]')];
const footer = document.getElementById('siteFooter');
const header = document.querySelector('.site-header');
const mainNav = document.getElementById('mainNav');
const menuToggle = document.getElementById('menuToggle');

const formatCOP = value => Number(value || 0).toLocaleString('es-CO', {
  style: 'currency',
  currency: 'COP',
  maximumFractionDigits: 0,
});

const esc = value => String(value ?? '')
  .replaceAll('&', '&amp;')
  .replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;')
  .replaceAll("'", '&#039;');

function iconForType(typeName = '') {
  const name = typeName.toLowerCase();
  if (name.includes('patín') || name.includes('patin')) return '🛼';
  if (name.includes('monopat') || name.includes('scooter')) return '🛴';
  return '🚲';
}

function labelRole(role = '') {
  return ({
    administrador: 'Administrador',
    operador: 'Operador',
    cliente: 'Cliente',
    domiciliario: 'Domiciliario',
  })[role] || role;
}

function roleClass(role = '') {
  return ({
    administrador: 'admin',
    operador: 'operator',
    cliente: 'client',
    domiciliario: 'delivery',
  })[role] || 'client';
}

function statusLabel(status = '') {
  return status.replaceAll('_', ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function errorMessage(payload, fallback = 'No se pudo completar la operación.') {
  return payload?.error?.mensaje || payload?.detail || fallback;
}

async function apiRequest(path, options = {}) {
  const {
    method = 'GET',
    body,
    headers = {},
    auth = false,
    timeout = 6500,
  } = options;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  const requestHeaders = { ...headers };

  if (auth && state.token) requestHeaders.Authorization = `Bearer ${state.token}`;

  try {
    const response = await fetch(`${API_BASE}${path}`, {
      method,
      headers: requestHeaders,
      body,
      signal: controller.signal,
    });

    const contentType = response.headers.get('content-type') || '';
    const payload = contentType.includes('application/json')
      ? await response.json()
      : await response.text();

    if (!response.ok) {
      const error = new Error(errorMessage(payload, `Error HTTP ${response.status}`));
      error.status = response.status;
      error.payload = payload;
      throw error;
    }

    state.apiOnline = true;
    return payload;
  } catch (error) {
    if (error.name === 'AbortError') {
      throw new Error('El backend tardó demasiado en responder.');
    }
    if (error instanceof TypeError) {
      throw new Error(`No se pudo conectar con el backend en ${API_BASE}.`);
    }
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

function saveSession(token, user, remember) {
  state.token = token;
  state.user = user;
  sessionStorage.removeItem('transport_token');
  localStorage.removeItem('transport_token');

  if (remember) localStorage.setItem('transport_token', token);
  else sessionStorage.setItem('transport_token', token);
}

function clearSession() {
  state.token = null;
  state.user = null;
  sessionStorage.removeItem('transport_token');
  localStorage.removeItem('transport_token');
}

function updateAdminIdentity() {
  const name = document.querySelector('.admin-user strong');
  const role = document.querySelector('.admin-user small');
  const avatar = document.querySelector('.admin-user .avatar');
  if (!state.user) return;

  if (name) name.textContent = state.user.nombre_completo;
  if (role) role.textContent = labelRole(state.user.rol);
  if (avatar) {
    avatar.textContent = state.user.nombre_completo
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map(x => x[0])
      .join('')
      .toUpperCase();
  }
}

function showView(name) {
  if (name === 'admin' && (!state.token || !state.user)) name = 'login';
  views.forEach(v => v.classList.toggle('active', v.dataset.view === name));
  navLinks.forEach(a => a.classList.toggle('active', a.dataset.viewLink === name));
  const special = name === 'login' || name === 'admin';
  footer.style.display = special ? 'none' : '';
  header.style.display = name === 'admin' ? 'none' : '';
  mainNav.classList.remove('open');
  menuToggle.setAttribute('aria-expanded', 'false');
  window.scrollTo({ top: 0, behavior: 'auto' });

  if (name === 'catalogo') refreshCatalog();
  if (name === 'admin' && state.token) loadAdminData();
}

document.querySelectorAll('[data-view-button], [data-view-link]').forEach(el => {
  el.addEventListener('click', e => {
    e.preventDefault();
    const name = el.dataset.viewButton || el.dataset.viewLink;
    history.replaceState(null, '', `#${name}`);
    showView(name);
  });
});

document.querySelectorAll('[data-anchor-link]').forEach(el => {
  el.addEventListener('click', e => {
    e.preventDefault();
    const id = el.dataset.anchorLink;
    showView('inicio');
    setTimeout(() => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' }), 50);
  });
});

menuToggle.addEventListener('click', () => {
  const open = mainNav.classList.toggle('open');
  menuToggle.setAttribute('aria-expanded', String(open));
});

// ------------------------------
// Portal institucional (HU-01)
// ------------------------------

function formatSchedule(horarios = []) {
  const open = horarios.filter(h => h.abierto && h.hora_apertura && h.hora_cierre);
  if (!open.length) return 'Sin horario publicado';

  const groups = new Map();
  for (const h of open) {
    const key = `${h.hora_apertura.slice(0, 5)}–${h.hora_cierre.slice(0, 5)}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(h.dia);
  }

  if (groups.size === 1) {
    const [[hours, days]] = [...groups.entries()];
    const first = days[0];
    const last = days[days.length - 1];
    const cap = s => s.charAt(0).toUpperCase() + s.slice(1);
    return days.length === 1 ? `${cap(first)} · ${hours}` : `${cap(first)}–${cap(last)} · ${hours}`;
  }

  return `${open.length} días con atención`;
}

async function loadPortal() {
  try {
    const data = await apiRequest('/portal');
    const sections = Object.fromEntries(data.secciones.map(s => [s.seccion, s]));

    const cards = document.querySelectorAll('.institutional-card');
    const mission = sections.mision;
    const vision = sections.vision;

    if (mission && cards[0]) {
      cards[0].querySelector('h2').textContent = mission.titulo;
      cards[0].querySelector('p').textContent = mission.contenido;
    }

    if (vision && cards[1]) {
      cards[1].querySelector('h2').textContent = vision.titulo;
      cards[1].querySelector('p').textContent = vision.contenido;
    }

    const contact = sections.contacto;
    const contactBlock = document.querySelector('.contact > div:first-child');
    if (contact && contactBlock) {
      contactBlock.querySelector('h2').textContent = contact.titulo;
      contactBlock.querySelector('p').textContent = contact.contenido;
    }

    const scheduleStrong = document.querySelector('.contact-grid > div:nth-child(3) strong');
    if (scheduleStrong) scheduleStrong.textContent = formatSchedule(data.horarios);
  } catch (error) {
    console.warn('Portal API no disponible; se conserva el contenido local.', error);
  }
}

// ------------------------------
// Catálogo real + fallback mock (HU-02)
// ------------------------------

const catalogGrid = document.getElementById('catalogGrid');
const typeFilter = document.getElementById('typeFilter');
const modeFilter = document.getElementById('modeFilter');
const priceFilter = document.getElementById('priceFilter');
const priceLabel = document.getElementById('priceLabel');
const availableFilter = document.getElementById('availableFilter');
const resultCount = document.getElementById('resultCount');
const emptyState = document.getElementById('emptyState');
const dialog = document.getElementById('vehicleDialog');

function normalizeApiModel(model) {
  return {
    id: model.id,
    type: model.tipo?.nombre || 'Vehículo',
    icon: iconForType(model.tipo?.nombre),
    name: model.nombre,
    brand: model.marca,
    mode: [
      model.se_alquila ? 'Alquiler' : null,
      model.se_vende ? 'Venta' : null,
    ].filter(Boolean),
    price: model.tarifa_diaria ?? 0,
    salePrice: model.precio_venta,
    available: model.disponibles_hoy > 0,
    availableCount: model.disponibles_hoy,
    location: null,
    battery: null,
    description: model.descripcion || 'Sin descripción.',
    imageUrl: model.imagen_url,
  };
}

function renderCatalogCards(items) {
  if (!catalogGrid) return;

  resultCount.textContent = items.length;
  emptyState.hidden = items.length !== 0;

  catalogGrid.innerHTML = items.map(v => {
    const displayPrice = v.price
      ? `${formatCOP(v.price)} <small>/día</small>`
      : v.salePrice
        ? `${formatCOP(v.salePrice)}`
        : 'Consultar';

    const availability = state.catalogUsesApi
      ? `${v.available ? '● Disponible hoy' : '● Sin unidades hoy'}`
      : `${v.available ? '● Disponible hoy' : '● No disponible'}`;

    const locationOrCount = state.catalogUsesApi
      ? `${v.availableCount ?? 0} unidad${v.availableCount === 1 ? '' : 'es'} disponible${v.availableCount === 1 ? '' : 's'}`
      : `📍 ${v.location}`;

    return `
      <article class="catalog-card">
        <div class="catalog-card-media">
          <span class="availability ${v.available ? 'ok' : 'no'}">${esc(availability)}</span>
          ${v.imageUrl
            ? `<img src="${esc(v.imageUrl)}" alt="${esc(v.name)}" style="max-width:82%;max-height:150px;object-fit:contain" onerror="this.replaceWith(document.createTextNode('${v.icon}'))">`
            : v.icon}
        </div>
        <div class="catalog-card-body">
          <small>${esc(v.type)}</small>
          <h3>${esc(v.name)}</h3>
          <div class="catalog-card-meta">
            <span>${esc(v.mode.join(' · ') || 'Consultar')}</span>
            <span>${esc(locationOrCount)}</span>
          </div>
          <div class="catalog-card-footer">
            <div>
              <div class="price">${displayPrice}</div>
              ${v.salePrice && v.price ? `<small>Venta: ${formatCOP(v.salePrice)}</small>` : ''}
            </div>
            <button data-detail="${v.id}">Ver detalle</button>
          </div>
        </div>
      </article>`;
  }).join('');

  document.querySelectorAll('[data-detail]').forEach(btn => {
    btn.addEventListener('click', () => openVehicle(Number(btn.dataset.detail)));
  });
}

function renderMockCatalog() {
  state.catalogUsesApi = false;
  const maxPrice = Number(priceFilter.value);
  const filtered = mockVehicles.filter(v =>
    (typeFilter.value === 'todos' || v.type === typeFilter.value) &&
    (modeFilter.value === 'todos' || v.mode.includes(modeFilter.value)) &&
    (!v.price || v.price <= maxPrice) &&
    (!availableFilter.checked || v.available)
  );

  priceLabel.textContent = formatCOP(maxPrice);
  state.catalog = filtered;
  renderCatalogCards(filtered);
}

async function loadTypes() {
  try {
    const data = await apiRequest('/catalogo/tipos?tamano=100');
    typeFilter.innerHTML = '<option value="todos">Todos</option>' +
      data.elementos.map(t => `<option value="${t.id}">${esc(t.nombre)}</option>`).join('');
    typeFilter.dataset.source = 'api';
  } catch (error) {
    typeFilter.dataset.source = 'mock';
  }
}

async function refreshCatalog() {
  if (!catalogGrid) return;

  const maxPrice = Number(priceFilter.value);
  priceLabel.textContent = formatCOP(maxPrice);

  const params = new URLSearchParams({ tamano: '100' });

  if (typeFilter.dataset.source === 'api' && typeFilter.value !== 'todos') {
    params.set('tipo_id', typeFilter.value);
  }

  if (modeFilter.value !== 'todos') {
    params.set('modalidad', modeFilter.value.toLowerCase());
  }

  // La tarifa máxima es una tarifa de alquiler. Para "Venta" no se envía.
  if (modeFilter.value !== 'Venta') {
    params.set('tarifa_max', String(maxPrice));
  }

  if (availableFilter.checked) params.set('solo_disponibles', 'true');

  try {
    catalogGrid.innerHTML = '<div class="empty-state"><div>⏳</div><h3>Cargando catálogo</h3><p>Consultando disponibilidad del backend...</p></div>';
    const data = await apiRequest(`/catalogo/modelos?${params}`);
    state.catalogUsesApi = true;
    state.catalog = data.elementos.map(normalizeApiModel);
    renderCatalogCards(state.catalog);
    resultCount.textContent = data.total;
  } catch (error) {
    console.warn('Catálogo API no disponible; se usan datos de demostración.', error);
    renderMockCatalog();
  }
}

let catalogDebounce;
[typeFilter, modeFilter, priceFilter, availableFilter].forEach(el => el?.addEventListener('input', () => {
  clearTimeout(catalogDebounce);
  catalogDebounce = setTimeout(refreshCatalog, 220);
}));

document.getElementById('clearFilters')?.addEventListener('click', () => {
  typeFilter.value = 'todos';
  modeFilter.value = 'todos';
  priceFilter.value = '80000';
  availableFilter.checked = false;
  refreshCatalog();
});

function renderVehicleDialog(v, detail = null) {
  const units = detail?.unidades_disponibles || [];
  const unitLocation = units.find(u => u.ubicacion)?.ubicacion || v.location || 'Por confirmar';
  const batteryValues = units.map(u => u.nivel_bateria).filter(x => x !== null);
  const battery = batteryValues.length ? `${batteryValues[0]}%` : 'No aplica';

  const actionText = detail
    ? (detail.se_alquila ? 'Alquiler: disponible en Sprint 2' : 'Venta: disponible en Sprint 2')
    : (v.available ? 'Solicitar alquiler' : 'Consultar disponibilidad');

  document.getElementById('dialogContent').innerHTML = `
    <div class="dialog-hero">${v.icon}</div>
    <div class="dialog-body">
      <span class="eyebrow">${esc(v.type.toUpperCase())}</span>
      <h2>${esc(v.name)}</h2>
      <p>${esc(v.description)}</p>
      <div class="dialog-specs">
        <div><small>TARIFA</small><strong>${v.price ? `${formatCOP(v.price)}/día` : (v.salePrice ? formatCOP(v.salePrice) : 'Consultar')}</strong></div>
        <div><small>UBICACIÓN</small><strong>${esc(unitLocation)}</strong></div>
        <div><small>ESTADO</small><strong>${detail ? `${detail.disponibles_hoy} libre(s) hoy` : (v.available ? 'Disponible' : 'No disponible')}</strong></div>
      </div>
      ${detail && units.length ? `<p><strong>Unidad:</strong> ${esc(units[0].codigo)} · Batería: ${esc(battery)}</p>` : ''}
      <button class="btn btn-primary" id="vehicleAction">${esc(actionText)}</button>
    </div>`;

  document.getElementById('vehicleAction')?.addEventListener('click', () => {
    showToast(detail
      ? 'El backend actual llega hasta Sprint 1. La creación de alquileres/ventas todavía no tiene endpoint.'
      : 'Modo demo: esta acción se conectará cuando exista el endpoint de alquiler.');
  });

  dialog.showModal();
}

async function openVehicle(id) {
  const current = state.catalog.find(x => x.id === id) || mockVehicles.find(x => x.id === id);
  if (!current) return;

  if (!state.catalogUsesApi) {
    renderVehicleDialog(current);
    return;
  }

  try {
    const detail = await apiRequest(`/catalogo/modelos/${id}`);
    renderVehicleDialog(normalizeApiModel(detail), detail);
  } catch (error) {
    showToast(error.message);
  }
}

document.getElementById('closeDialog')?.addEventListener('click', () => dialog.close());
dialog?.addEventListener('click', e => { if (e.target === dialog) dialog.close(); });

// ------------------------------
// Autenticación real (HU-12)
// ------------------------------

const passwordInput = document.getElementById('passwordInput');
const loginForm = document.getElementById('loginForm');
const loginEmail = loginForm?.querySelector('input[type="email"]');
const rememberInput = loginForm?.querySelector('input[type="checkbox"]');
const loginButton = loginForm?.querySelector('button[type="submit"]');
const loginNote = document.querySelector('.demo-note p');

document.getElementById('togglePassword')?.addEventListener('click', e => {
  const show = passwordInput.type === 'password';
  passwordInput.type = show ? 'text' : 'password';
  e.target.textContent = show ? 'Ocultar' : 'Mostrar';
});

loginForm?.addEventListener('submit', async e => {
  e.preventDefault();

  const originalText = loginButton.textContent;
  loginButton.disabled = true;
  loginButton.textContent = 'Ingresando...';

  try {
    const body = new URLSearchParams({
      username: loginEmail.value.trim(),
      password: passwordInput.value,
    });

    const data = await apiRequest('/autenticacion/token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body,
    });

    saveSession(data.access_token, data.usuario, rememberInput.checked);
    updateAdminIdentity();

    if (['administrador', 'operador'].includes(data.usuario.rol)) {
      showView('admin');
      showToast(`Sesión iniciada como ${labelRole(data.usuario.rol)}.`);
    } else {
      showView('inicio');
      showToast(`Sesión iniciada como ${labelRole(data.usuario.rol)}. El panel de cliente/domiciliario aún no está implementado.`);
    }
  } catch (error) {
    showToast(error.message);
  } finally {
    loginButton.disabled = false;
    loginButton.textContent = originalText;
  }
});

document.querySelector('.logout')?.addEventListener('click', () => {
  clearSession();
  showToast('Sesión cerrada.');
});

// ------------------------------
// Administración real: usuarios y flota
// ------------------------------

const adminTitles = {
  resumen: 'Resumen',
  usuarios: 'Usuarios y roles',
  flota: 'Gestión de flota',
  mantenimiento: 'Mantenimiento',
};

document.querySelectorAll('[data-admin-tab]').forEach(btn => btn.addEventListener('click', async () => {
  const tab = btn.dataset.adminTab;
  if (!tab) return;

  if (tab === 'usuarios' && state.user?.rol !== 'administrador') {
    showToast('Solo un administrador puede consultar usuarios.');
    return;
  }

  document.querySelectorAll('.admin-nav [data-admin-tab]').forEach(b => {
    b.classList.toggle('active', b.dataset.adminTab === tab);
  });
  document.querySelectorAll('[data-admin-content]').forEach(c => {
    c.classList.toggle('active', c.dataset.adminContent === tab);
  });
  document.getElementById('adminTitle').textContent = adminTitles[tab] || tab;

  if (tab === 'usuarios') await loadUsers();
  if (tab === 'flota') await loadFleet();
  if (tab === 'mantenimiento') await loadMaintenance();
}));

function renderUsers(users) {
  const tbody = document.querySelector('[data-admin-content="usuarios"] tbody');
  if (!tbody) return;

  tbody.innerHTML = users.map(u => `
    <tr>
      <td><strong>${esc(u.nombre_completo)}</strong><small>${esc(u.correo)}</small></td>
      <td><span class="role ${roleClass(u.rol)}">${esc(labelRole(u.rol))}</span></td>
      <td><span class="status-chip ${u.activo ? 'active-chip' : 'inactive-chip'}">${u.activo ? 'Activo' : 'Inactivo'}</span></td>
      <td><button class="table-action" data-user-id="${u.id}" disabled title="Edición visual pendiente">Editar</button></td>
    </tr>`).join('');
}

async function loadUsers() {
  if (!state.token || state.user?.rol !== 'administrador') return;

  try {
    const data = await apiRequest('/usuarios?tamano=100', { auth: true });
    state.users = data.elementos;
    renderUsers(state.users);
    updateMetrics();
  } catch (error) {
    if (error.status === 401) handleExpiredSession();
    else showToast(error.message);
  }
}

function fleetIcon(vehicle) {
  return iconForType(vehicle.modelo?.tipo?.nombre || vehicle.modelo?.nombre || '');
}

function renderFleet(fleet) {
  const grid = document.querySelector('[data-admin-content="flota"] .fleet-grid');
  if (!grid) return;

  if (!fleet.length) {
    grid.innerHTML = '<div class="empty-state"><div>🛴</div><h3>No hay unidades</h3><p>El backend no devolvió vehículos.</p></div>';
    return;
  }

  grid.innerHTML = fleet.map(v => {
    const isMaintenance = v.estado === 'mantenimiento';
    const canInactivate = !['mantenimiento', 'vendido'].includes(v.estado);

    return `
      <article>
        <div class="vehicle-icon">${fleetIcon(v)}</div>
        <div>
          <small>${esc(v.codigo)}</small>
          <h4>${esc(v.modelo?.nombre || 'Modelo')}</h4>
          <span class="status-chip ${isMaintenance ? 'maintenance-chip' : 'active-chip'}">${esc(statusLabel(v.estado))}</span>
          ${v.ubicacion ? `<small> · ${esc(v.ubicacion)}</small>` : ''}
          ${v.nivel_bateria !== null ? `<small> · ⚡ ${v.nivel_bateria}%</small>` : ''}
        </div>
        ${canInactivate
          ? `<button class="outline-danger" data-inactivate-id="${v.id}" data-code="${esc(v.codigo)}">Inactivar</button>`
          : `<button class="table-action" data-open-issues="${v.id}">Ver novedades</button>`}
      </article>`;
  }).join('');
}

async function loadFleet() {
  if (!state.token || !['administrador', 'operador'].includes(state.user?.rol)) return;

  try {
    const data = await apiRequest('/vehiculos?tamano=100', { auth: true });
    state.fleet = data.elementos;
    renderFleet(state.fleet);
    updateMetrics();
  } catch (error) {
    if (error.status === 401) handleExpiredSession();
    else showToast(error.message);
  }
}

function updateMetrics() {
  const metricValues = document.querySelectorAll('[data-admin-content="resumen"] .metric-grid article strong');
  const metricNotes = document.querySelectorAll('[data-admin-content="resumen"] .metric-grid article small');

  const available = state.fleet.filter(v => v.estado === 'disponible').length;
  const maintenance = state.fleet.filter(v => v.estado === 'mantenimiento').length;
  const reserved = state.fleet.filter(v => v.estado === 'reservado').length;
  const activeUsers = state.users.filter(u => u.activo).length;

  if (metricValues[0]) metricValues[0].textContent = state.fleet.length ? available : '—';
  if (metricValues[1]) metricValues[1].textContent = state.fleet.length ? maintenance : '—';
  if (metricValues[2]) metricValues[2].textContent = state.user?.rol === 'administrador' ? activeUsers : '—';
  if (metricValues[3]) metricValues[3].textContent = '—';

  if (metricNotes[0]) metricNotes[0].textContent = state.fleet.length ? `de ${state.fleet.length} unidades` : 'Sin datos';
  if (metricNotes[1]) metricNotes[1].textContent = state.fleet.length ? `${maintenance} fuera de catálogo` : 'Sin datos';
  if (metricNotes[2]) metricNotes[2].textContent = state.user?.rol === 'administrador' ? 'dato del backend' : 'solo administradores';
  if (metricNotes[3]) metricNotes[3].textContent = 'requiere Sprint 2';

  const statusRows = document.querySelectorAll('[data-admin-content="resumen"] .status-list strong');
  if (statusRows[0]) statusRows[0].textContent = available;
  if (statusRows[1]) statusRows[1].textContent = maintenance;
  if (statusRows[2]) statusRows[2].textContent = reserved;

  const activity = document.querySelector('[data-admin-content="resumen"] .activity-list');
  if (activity) {
    activity.innerHTML = `
      <p><span>🔄</span><span><strong>Datos sincronizados</strong><small>La flota y los usuarios se consultan desde la API.</small></span></p>
      <p><span>ℹ️</span><span>El historial de actividad general aún no tiene endpoint.<small>Se deja para un sprint posterior.</small></span></p>`;
  }
}

async function inactivateVehicle(vehicleId, code) {
  const reason = window.prompt(`Motivo para inactivar ${code}:`, 'Mantenimiento preventivo');
  if (reason === null) return;
  if (reason.trim().length < 5) {
    showToast('El motivo debe tener al menos 5 caracteres.');
    return;
  }

  try {
    const result = await apiRequest(`/vehiculos/${vehicleId}/inactivacion`, {
      method: 'POST',
      auth: true,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ motivo: reason.trim() }),
    });

    const affected = result.alquileres_afectados?.length || 0;
    showToast(`${code} pasó a mantenimiento.${affected ? ` Hay ${affected} alquiler(es) afectado(s).` : ''}`);
    await Promise.all([loadFleet(), refreshCatalog()]);
    await loadMaintenance();
  } catch (error) {
    if (error.status === 401) handleExpiredSession();
    else showToast(error.message);
  }
}

document.querySelector('[data-admin-content="flota"] .fleet-grid')?.addEventListener('click', async e => {
  const inactivate = e.target.closest('[data-inactivate-id]');
  if (inactivate) {
    await inactivateVehicle(Number(inactivate.dataset.inactivateId), inactivate.dataset.code);
    return;
  }

  const issues = e.target.closest('[data-open-issues]');
  if (issues) {
    document.querySelector('[data-admin-tab="mantenimiento"]')?.click();
  }
});

async function loadMaintenance() {
  if (!state.fleet.length) await loadFleet();

  const container = document.querySelector('[data-admin-content="mantenimiento"] .maintenance-list');
  if (!container) return;

  const maintenanceVehicles = state.fleet.filter(v => v.estado === 'mantenimiento');
  if (!maintenanceVehicles.length) {
    container.innerHTML = '<div class="empty-state"><div>✅</div><h3>Sin novedades críticas</h3><p>No hay unidades en mantenimiento.</p></div>';
    return;
  }

  container.innerHTML = '<div class="empty-state"><div>⏳</div><h3>Cargando novedades</h3><p>Consultando el backend...</p></div>';

  const results = await Promise.allSettled(
    maintenanceVehicles.map(async vehicle => {
      const data = await apiRequest(`/vehiculos/${vehicle.id}/novedades?estado=abierta&tamano=100`, { auth: true });
      return data.elementos.map(issue => ({ issue, vehicle }));
    })
  );

  const issues = results
    .filter(r => r.status === 'fulfilled')
    .flatMap(r => r.value);

  if (!issues.length) {
    container.innerHTML = maintenanceVehicles.map(v => `
      <article>
        <span class="warning-icon soft">!</span>
        <div>
          <small>${esc(v.codigo)} · Mantenimiento</small>
          <h4>${esc(v.modelo?.nombre || 'Vehículo')}</h4>
          <p>${esc(v.observaciones || 'Sin novedad abierta detallada.')}</p>
        </div>
      </article>`).join('');
    return;
  }

  container.innerHTML = issues.map(({ issue, vehicle }) => `
    <article>
      <span class="warning-icon ${issue.es_critica ? '' : 'soft'}">!</span>
      <div>
        <small>${esc(vehicle.codigo)} · ${issue.es_critica ? 'Crítica' : 'No crítica'}</small>
        <h4>${esc(statusLabel(issue.tipo))}</h4>
        <p>${esc(issue.descripcion)}</p>
      </div>
      <span class="status-chip maintenance-chip">${esc(statusLabel(issue.estado))}</span>
    </article>`).join('');
}

async function loadAdminData() {
  if (!state.token || !state.user) return;
  updateAdminIdentity();

  const tasks = [loadFleet()];
  if (state.user.rol === 'administrador') tasks.push(loadUsers());
  await Promise.all(tasks);
}

function handleExpiredSession() {
  clearSession();
  showView('login');
  showToast('La sesión expiró. Inicia sesión nuevamente.');
}

// ------------------------------
// Salud y restauración de sesión
// ------------------------------

async function checkHealth() {
  try {
    const health = await apiRequest('/salud', { timeout: 3500 });
    state.apiOnline = health?.estado === 'ok';

    if (loginNote) {
      loginNote.textContent = state.apiOnline
        ? `Backend conectado en ${API_BASE}. Las credenciales de desarrollo se validan contra la API real.`
        : `El backend respondió con estado ${health?.estado || 'desconocido'}.`;
    }
  } catch (error) {
    state.apiOnline = false;
    if (loginNote) {
      loginNote.textContent = `Backend sin conexión en ${API_BASE}. Levántalo con uvicorn para probar autenticación, usuarios y flota.`;
    }
  }
}

async function restoreSession() {
  if (!state.token) return;

  try {
    state.user = await apiRequest('/usuarios/yo', { auth: true });
    updateAdminIdentity();
  } catch (error) {
    clearSession();
  }
}

let toastTimer;
function showToast(message) {
  const toast = document.getElementById('toast');
  toast.textContent = message;
  toast.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove('show'), 4200);
}
window.showToast = showToast;

(async function init() {
  await Promise.allSettled([
    checkHealth(),
    loadPortal(),
    loadTypes(),
    restoreSession(),
  ]);

  const initial = location.hash.replace('#', '');
  showView(['inicio', 'catalogo', 'login', 'admin'].includes(initial) ? initial : 'inicio');

  if (initial !== 'catalogo') refreshCatalog();
})();
