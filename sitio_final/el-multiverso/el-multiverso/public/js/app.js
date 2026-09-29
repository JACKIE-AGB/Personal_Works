// ============================================================
//  Utilidades compartidas + barra superior de "El Multiverso"
// ============================================================
async function api(url, opciones = {}) {
  const cfg = { credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, method: opciones.method || 'GET' };
  if (opciones.body) cfg.body = JSON.stringify(opciones.body);
  const r = await fetch(url, cfg);
  let datos = {};
  try { datos = await r.json(); } catch (e) {}
  if (!r.ok) throw new Error(datos.error || 'Error del servidor');
  return datos;
}

const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const dinero = n => '$' + Number(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

function mostrarAlerta(el, mensaje, tipo = 'error') {
  el.className = 'alerta ' + tipo;
  el.textContent = mensaje;
  el.classList.remove('oculto');
}

// Barra superior: siempre la misma; cambian las opciones según el usuario activo
async function iniciarBarra() {
  let u = null;
  try { u = (await api('/api/me')).usuario; } catch (e) {}
  const actual = location.pathname.split('/').pop() || 'index.html';

  const enlaces = [['index.html', 'Inicio']];
  if (u) {
    enlaces.push(['registrar-pedido.html', 'Registrar pedido'], ['consultar-pedidos.html', 'Consultar pedidos']);
    if (u.tipo === 'PT') enlaces.push(['administrar-pedidos.html', 'Administrar Pedidos (PT)']);
  }
  const izq = enlaces.map(([href, txt]) =>
    `<a class="enlace ${href === 'index.html' ? 'inicio' : ''} ${actual === href ? 'activo' : ''}" href="/${href === 'index.html' ? '' : href}">${txt}</a>`).join('');

  const der = u
    ? `<span class="usuario-activo" title="Usuario activo">&#9679; ${esc(u.id)} (${u.tipo})</span>
       <button class="btn-salir" id="btnSalir" type="button">Cerrar Sesión</button>`
    : `<a class="btn-barra" href="/registro.html">Registrarse</a>
       <a class="btn-barra lleno" href="/login.html">Iniciar Sesión</a>`;

  const cont = document.getElementById('barra');
  cont.className = 'barra';
  cont.innerHTML = `<div class="barra-izq"><a class="marca" href="/">El Multiverso</a>${izq}</div><div class="barra-der">${der}</div>`;

  const salir = document.getElementById('btnSalir');
  if (salir) salir.addEventListener('click', async () => { await api('/api/logout', { method: 'POST' }); location.href = '/'; });
  return u;
}
