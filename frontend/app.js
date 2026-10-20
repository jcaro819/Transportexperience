const vehicles = [
  { id: 1, type: 'Cicla', icon: '🚲', name: 'Urban Ride 3', mode: ['Alquiler'], price: 12000, available: true, location: 'Cabecera', battery: null, description: 'Cicla urbana cómoda y ligera para trayectos cortos.' },
  { id: 2, type: 'Monopatín', icon: '🛴', name: 'Volt City S2', mode: ['Alquiler'], price: 18000, available: true, location: 'Centro', battery: 92, description: 'Monopatín eléctrico compacto, ideal para recorridos urbanos rápidos.' },
  { id: 3, type: 'Patines', icon: '🛼', name: 'Street Glide', mode: ['Alquiler', 'Venta'], price: 10000, salePrice: 265000, available: true, location: 'San Alonso', battery: null, description: 'Patines recreativos ajustables, pensados para desplazamientos y ocio.' },
  { id: 4, type: 'Cicla', icon: '🚲', name: 'Eco Motion E1', mode: ['Alquiler', 'Venta'], price: 28000, salePrice: 2400000, available: false, location: 'Cabecera', battery: 76, description: 'Bicicleta eléctrica asistida para recorridos más largos con menor esfuerzo.' },
  { id: 5, type: 'Monopatín', icon: '🛴', name: 'Pulse Mini', mode: ['Venta'], price: 68000, salePrice: 1350000, available: true, location: 'Provenza', battery: 84, description: 'Monopatín eléctrico liviano para movilidad cotidiana.' },
  { id: 6, type: 'Cicla', icon: '🚲', name: 'City Basic', mode: ['Alquiler'], price: 15000, available: true, location: 'Real de Minas', battery: null, description: 'Bicicleta convencional de mantenimiento simple y uso versátil.' },
];

const views = [...document.querySelectorAll('[data-view]')];
const navLinks = [...document.querySelectorAll('[data-view-link]')];
const footer = document.getElementById('siteFooter');
const header = document.querySelector('.site-header');
const mainNav = document.getElementById('mainNav');
const menuToggle = document.getElementById('menuToggle');

function showView(name) {
  views.forEach(v => v.classList.toggle('active', v.dataset.view === name));
  navLinks.forEach(a => a.classList.toggle('active', a.dataset.viewLink === name));
  const special = name === 'login' || name === 'admin';
  footer.style.display = special ? 'none' : '';
  header.style.display = name === 'admin' ? 'none' : '';
  mainNav.classList.remove('open');
  menuToggle.setAttribute('aria-expanded', 'false');
  window.scrollTo({ top: 0, behavior: 'instant' });
  if (name === 'catalogo') renderCatalog();
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

const formatCOP = value => value.toLocaleString('es-CO', { style: 'currency', currency: 'COP', maximumFractionDigits: 0 });
const catalogGrid = document.getElementById('catalogGrid');
const typeFilter = document.getElementById('typeFilter');
const modeFilter = document.getElementById('modeFilter');
const priceFilter = document.getElementById('priceFilter');
const priceLabel = document.getElementById('priceLabel');
const availableFilter = document.getElementById('availableFilter');
const resultCount = document.getElementById('resultCount');
const emptyState = document.getElementById('emptyState');

function renderCatalog() {
  if (!catalogGrid) return;
  const maxPrice = Number(priceFilter.value);
  const filtered = vehicles.filter(v =>
    (typeFilter.value === 'todos' || v.type === typeFilter.value) &&
    (modeFilter.value === 'todos' || v.mode.includes(modeFilter.value)) &&
    v.price <= maxPrice &&
    (!availableFilter.checked || v.available)
  );
  priceLabel.textContent = formatCOP(maxPrice);
  resultCount.textContent = filtered.length;
  emptyState.hidden = filtered.length !== 0;
  catalogGrid.innerHTML = filtered.map(v => `
    <article class="catalog-card">
      <div class="catalog-card-media"><span class="availability ${v.available ? 'ok' : 'no'}">${v.available ? '● Disponible hoy' : '● No disponible'}</span>${v.icon}</div>
      <div class="catalog-card-body">
        <small>${v.type}</small><h3>${v.name}</h3>
        <div class="catalog-card-meta"><span>${v.mode.join(' · ')}</span><span>📍 ${v.location}</span>${v.battery !== null ? `<span>⚡ ${v.battery}%</span>` : ''}</div>
        <div class="catalog-card-footer"><div><div class="price">${formatCOP(v.price)} <small>/día</small></div>${v.salePrice ? `<small>Venta: ${formatCOP(v.salePrice)}</small>` : ''}</div><button data-detail="${v.id}">Ver detalle</button></div>
      </div>
    </article>`).join('');
  document.querySelectorAll('[data-detail]').forEach(btn => btn.addEventListener('click', () => openVehicle(Number(btn.dataset.detail))));
}

[typeFilter, modeFilter, priceFilter, availableFilter].forEach(el => el?.addEventListener('input', renderCatalog));
document.getElementById('clearFilters')?.addEventListener('click', () => { typeFilter.value='todos'; modeFilter.value='todos'; priceFilter.value='80000'; availableFilter.checked=false; renderCatalog(); });

const dialog = document.getElementById('vehicleDialog');
function openVehicle(id) {
  const v = vehicles.find(x => x.id === id); if (!v) return;
  document.getElementById('dialogContent').innerHTML = `<div class="dialog-hero">${v.icon}</div><div class="dialog-body"><span class="eyebrow">${v.type.toUpperCase()}</span><h2>${v.name}</h2><p>${v.description}</p><div class="dialog-specs"><div><small>TARIFA</small><strong>${formatCOP(v.price)}/día</strong></div><div><small>UBICACIÓN</small><strong>${v.location}</strong></div><div><small>ESTADO</small><strong>${v.available ? 'Disponible' : 'No disponible'}</strong></div></div><button class="btn btn-primary" onclick="showToast('Prototipo: la reserva se conectará al backend en la siguiente versión.')">${v.available ? 'Solicitar alquiler' : 'Consultar disponibilidad'}</button></div>`;
  dialog.showModal();
}
document.getElementById('closeDialog')?.addEventListener('click', () => dialog.close());
dialog?.addEventListener('click', e => { if (e.target === dialog) dialog.close(); });

const passwordInput = document.getElementById('passwordInput');
document.getElementById('togglePassword')?.addEventListener('click', e => { const show = passwordInput.type === 'password'; passwordInput.type = show ? 'text' : 'password'; e.target.textContent = show ? 'Ocultar' : 'Mostrar'; });
document.getElementById('loginForm')?.addEventListener('submit', e => { e.preventDefault(); showView('admin'); });

const adminTitles = { resumen:'Resumen', usuarios:'Usuarios y roles', flota:'Gestión de flota', mantenimiento:'Mantenimiento' };
document.querySelectorAll('[data-admin-tab]').forEach(btn => btn.addEventListener('click', () => {
  const tab = btn.dataset.adminTab;
  document.querySelectorAll('.admin-nav [data-admin-tab]').forEach(b => b.classList.toggle('active', b.dataset.adminTab === tab));
  document.querySelectorAll('[data-admin-content]').forEach(c => c.classList.toggle('active', c.dataset.adminContent === tab));
  document.getElementById('adminTitle').textContent = adminTitles[tab] || tab;
}));

document.querySelectorAll('[data-inactivate]').forEach(btn => btn.addEventListener('click', () => showToast(`Demo: ${btn.dataset.inactivate} se marcaría como en mantenimiento.`)));
let toastTimer;
function showToast(message){ const toast=document.getElementById('toast'); toast.textContent=message; toast.classList.add('show'); clearTimeout(toastTimer); toastTimer=setTimeout(()=>toast.classList.remove('show'),3200); }
window.showToast = showToast;

const initial = location.hash.replace('#','');
showView(['inicio','catalogo','login','admin'].includes(initial) ? initial : 'inicio');
renderCatalog();
