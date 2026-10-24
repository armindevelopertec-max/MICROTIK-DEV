(() => {
  const CSRF = document.querySelector('meta[name="csrf-token"]')?.content || '';
  const estadoInicial = window.ESTADO_INICIAL || {};
  const configUi = window.CONFIG_UI || {};

  let estado = JSON.parse(JSON.stringify(estadoInicial));
  let tabActiva = 'tickets';
  let filtro = '';
  let lotes = [];

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

  function fmtDur(seg) {
    if (seg === null || seg === undefined) return '—';
    seg = Math.max(0, Math.floor(seg));
    if (seg <= 0) return '0s';
    const d = Math.floor(seg / 86400); seg %= 86400;
    const h = Math.floor(seg / 3600); seg %= 3600;
    const m = Math.floor(seg / 60); const s = seg % 60;
    const p = [];
    if (d) p.push(d + 'd');
    if (h) p.push(h + 'h');
    if (m && !d) p.push(m + 'm');
    if (s && !d && !h) p.push(s + 's');
    if (!p.length) p.push('0s');
    return p.join(' ');
  }

  function fmtBytes(v) {
    let n = Number(v || 0);
    if (!isFinite(n)) return '0 B';
    const units = ['B','KiB','MiB','GiB','TiB'];
    let i = 0;
    while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
    if (i === 0) return Math.floor(n) + ' ' + units[i];
    return n.toFixed(1) + ' ' + units[i];
  }

  function toast(msg, tipo = 'ok') {
    const c = $('#toast-container');
    const el = document.createElement('div');
    el.className = 'toast toast-' + tipo;
    el.textContent = msg;
    c.appendChild(el);
    setTimeout(() => el.remove(), 3200);
  }

  function setBanner(msg) {
    const b = $('#error-banner');
    if (msg) {
      b.textContent = msg;
      b.classList.remove('hidden');
    } else {
      b.classList.add('hidden');
    }
  }

  function liveSeg(item, isActive, field = 'usado_segundos') {
    let base = Number(item?.[field] || 0);
    if (!estado.ok || !isActive) return base;
    const extra = Math.max(0, Date.now() / 1000 - Number(estado.ts || Date.now()/1000));
    return base + extra;
  }

  function liveUptime(item) {
    let base = Number(item?.uptime_segundos || 0);
    if (!estado.ok) return base;
    const extra = Math.max(0, Date.now() / 1000 - Number(estado.ts || Date.now()/1000));
    return base + extra;
  }

  async function apiFetch(url, opts = {}) {
    const headers = Object.assign({}, opts.headers || {});
    if (opts.method && opts.method !== 'GET') {
      headers['X-CSRF-Token'] = CSRF;
      if (headers['Content-Type'] === undefined && !(opts.body instanceof FormData)) {
        headers['Content-Type'] = 'application/json';
      }
    }
    const res = await fetch(url, Object.assign({ cache: 'no-store' }, opts, { headers }));
    if (res.status === 401) {
      window.location.href = '/login';
      throw new Error('No autenticado');
    }
    return res;
  }

  function renderResumen() {
    const r = estado.resumen || {};
    $('#stat-tickets').textContent = r.tickets ?? '—';
    $('#stat-activos').textContent = r.activos ?? estado.activos?.length ?? '—';
    $('#stat-disponibles').textContent = r.disponibles ?? '—';
    $('#stat-agotados').textContent = r.agotados ?? '—';
    $('#stat-ssid').textContent = estado.ssid || configUi.ssid || '—';
    $('#stat-portal').textContent = estado.portal || configUi.portal || '';
  }

  function renderStatus() {
    const el = $('#api-status');
    el.classList.remove('pill-ok','pill-warn','pill-bad');
    if (estado.ok) {
      el.classList.add('pill-ok');
      el.textContent = `API OK · ${estado.identity || '?'}`;
    } else {
      el.classList.add('pill-bad');
      el.textContent = estado.error ? 'API error' : 'Sin conexión';
    }
    setBanner(estado.ok ? null : (estado.error || 'No se pudo conectar al router'));
  }

  function renderReloj() {
    const el = $('#server-clock');
    const base = Number(estado.ts || Date.now()/1000);
    const now = Date.now()/1000;
    const diff = Math.max(0, now - base);
    const d = new Date((base + diff) * 1000);
    el.textContent = d.toLocaleString('es-ES');
  }

  function renderActivos() {
    const list = estado.activos || [];
    const badge = $('#activos-badge');
    badge.textContent = String(list.length);
    const tbody = $('#tabla-activos tbody');
    if (!list.length) {
      tbody.innerHTML = '<tr><td colspan="7" class="empty">Sin sesiones activas</td></tr>';
      return;
    }
    tbody.innerHTML = list.map(a => {
      const up = liveUptime(a);
      const upTxt = fmtDur(up);
      const traf = fmtBytes(a.bytes_in) + ' ↓ / ' + fmtBytes(a.bytes_out) + ' ↑';
      const ticket = a.es_ticket ? '<span class="status-dot ok">sí</span>' : '<span class="muted">no</span>';
      return `<tr>
        <td><strong>${esc(a.usuario)}</strong></td>
        <td><div>${esc(a.ip || '—')}</div><small class="muted">${esc(a.mac || '')}</small></td>
        <td>${esc(upTxt)}</td>
        <td>${esc(traf)}</td>
        <td>${esc(a.login_by || '—')}</td>
        <td>${ticket}</td>
        <td><button class="ghost" data-action="desconectar" data-user="${esc(a.usuario)}">Desconectar</button></td>
      </tr>`;
    }).join('');
  }

  function getUsuariosFiltrados() {
    const q = filtro.toLowerCase().trim();
    let list = estado.usuarios || [];
    if (tabActiva === 'tickets') list = list.filter(u => u.es_ticket);
    if (!q) return list;
    return list.filter(u => {
      return [u.codigo, u.lote, u.nota, u.ip, u.mac, u.perfil, u.estado].some(v => String(v||'').toLowerCase().includes(q));
    });
  }

  function renderTickets() {
    const list = getUsuariosFiltrados();
    const tbody = $('#tabla-tickets tbody');
    if (!list.length) {
      tbody.innerHTML = '<tr><td colspan="8" class="empty">Sin tickets para mostrar</td></tr>';
      return;
    }
    tbody.innerHTML = list.map(u => {
      const usado = liveSeg(u, u.activo, 'usado_segundos');
      const limite = Number(u.limite_segundos || 0);
      let restanteTxt = u.restante || '—';
      if (limite > 0 && u.activo) {
        restanteTxt = fmtDur(Math.max(0, limite - usado));
      } else if (limite > 0) {
        restanteTxt = fmtDur(Math.max(0, limite - usado));
      }
      const sesion = u.activo ? `<div>${esc(u.ip||'—')}</div><small class="muted">${esc(u.mac||'')}</small>` : '<span class="muted">—</span>';
      const estadoTxt = u.estado === 'activo' ? '<span class="status-dot ok">activo</span>' 
        : u.estado === 'agotado' ? '<span class="status-dot bad">agotado</span>'
        : u.estado === 'deshabilitado' ? '<span class="status-dot warn">deshabilitado</span>'
        : '<span class="status-dot">libre</span>';
      return `<tr>
        <td><strong>${esc(u.codigo)}</strong></td>
        <td>${estadoTxt}</td>
        <td>${esc(u.perfil)}</td>
        <td><div>${esc(u.limite)}</div><small class="muted">usado ${esc(fmtDur(usado))} · restante ${esc(restanteTxt)}</small></td>
        <td>${sesion}</td>
        <td><div>${esc(u.lote)}</div><small class="muted">${esc(u.creado)}</small></td>
        <td><small class="muted">${esc(u.nota||'')}</small></td>
        <td>
          <div style="display:flex;gap:0.4rem;flex-wrap:wrap">
            <button class="ghost" data-action="qr" data-codigo="${esc(u.codigo)}">QR</button>
            ${u.activo ? `<button class="ghost" data-action="desconectar" data-user="${esc(u.codigo)}">Desconectar</button>` : ''}
            <button class="danger" data-action="eliminar" data-codigo="${esc(u.codigo)}">Eliminar</button>
          </div>
        </td>
      </tr>`;
    }).join('');
  }

  function renderUsuarios() {
    if (tabActiva !== 'usuarios') return;
    const list = getUsuariosFiltrados();
    const tbody = $('#tabla-usuarios tbody');
    if (!list.length) {
      tbody.innerHTML = '<tr><td colspan="8" class="empty">Sin usuarios</td></tr>';
      return;
    }
    tbody.innerHTML = list.map(u => {
      const usado = liveSeg(u, u.activo, 'usado_segundos');
      const estadoTxt = u.estado === 'activo' ? '<span class="status-dot ok">activo</span>' 
        : u.estado === 'agotado' ? '<span class="status-dot bad">agotado</span>'
        : u.estado === 'deshabilitado' ? '<span class="status-dot warn">deshabilitado</span>'
        : '<span class="status-dot">libre</span>';
      const sesion = u.activo ? `<div>${esc(u.ip||'—')}</div>` : '<span class="muted">—</span>';
      return `<tr>
        <td><strong>${esc(u.codigo)}</strong>${u.es_ticket ? ' <span class="badge">QR</span>' : ''}</td>
        <td>${esc(u.perfil)}</td>
        <td>${estadoTxt}</td>
        <td>${esc(u.limite)}</td>
        <td>${esc(fmtDur(usado))}</td>
        <td>${sesion}</td>
        <td><button class="ghost" data-action="qr" data-codigo="${esc(u.codigo)}">Generar / Ver QR</button></td>
        <td>
          <div style="display:flex;gap:0.4rem;flex-wrap:wrap">
            ${u.activo ? `<button class="ghost" data-action="desconectar" data-user="${esc(u.codigo)}">Desconectar</button>` : ''}
            ${u.es_ticket ? `<button class="danger" data-action="eliminar" data-codigo="${esc(u.codigo)}">Eliminar</button>` : ''}
          </div>
        </td>
      </tr>`;
    }).join('');
  }

  async function cargarLotes() {
    try {
      const res = await apiFetch('/api/lotes');
      const data = await res.json();
      if (data.ok) {
        lotes = data.lotes || [];
        renderLotes();
      }
    } catch (e) {
      // ignore
    }
  }

  function renderLotes() {
    if (tabActiva !== 'lotes') return;
    const tbody = $('#tabla-lotes tbody');
    if (!lotes.length) {
      tbody.innerHTML = '<tr><td colspan="5" class="empty">No hay lotes en tickets/</td></tr>';
      return;
    }
    tbody.innerHTML = lotes.map(l => {
      const fecha = l.mtime ? new Date(l.mtime * 1000).toLocaleString('es-ES') : '—';
      return `<tr>
        <td><strong>${esc(l.lote)}</strong></td>
        <td>${esc(l.tickets)}</td>
        <td>${esc(fecha)}</td>
        <td>
          <div style="display:flex;gap:0.4rem;flex-wrap:wrap">
            ${l.tiene_csv ? `<a class="ghost" href="/api/lotes/${encodeURIComponent(l.lote)}/tickets.csv">CSV</a>` : ''}
            ${l.tiene_html ? `<a class="ghost" href="/api/lotes/${encodeURIComponent(l.lote)}/tickets.html" target="_blank">HTML</a>` : ''}
            ${l.tiene_resumen ? `<a class="ghost" href="/api/lotes/${encodeURIComponent(l.lote)}/resumen.txt">Resumen</a>` : ''}
          </div>
        </td>
        <td><button class="danger" data-action="eliminar-lote" data-lote="${esc(l.lote)}">Eliminar tickets</button></td>
      </tr>`;
    }).join('');
  }

  function render() {
    renderStatus();
    renderResumen();
    renderActivos();
    if (tabActiva === 'tickets') renderTickets();
    if (tabActiva === 'usuarios') renderUsuarios();
    if (tabActiva === 'lotes') renderLotes();
    renderReloj();
  }

  async function cargarEstado() {
    try {
      const res = await apiFetch('/api/estado');
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const data = await res.json();
      estado = data;
      render();
    } catch (e) {
      renderStatus();
      setBanner('No se pudo actualizar el estado: ' + e.message);
    }
  }

  async function abrirQr(codigo) {
    const modal = $('#modal');
    const body = $('#modal-body');
    body.innerHTML = `<h2>Ticket ${esc(codigo)}</h2><p class="muted">Cargando información...</p>`;
    modal.classList.remove('hidden');
    try {
      const res = await apiFetch('/api/usuarios/' + encodeURIComponent(codigo));
      const data = await res.json();
      const creds = data.ok ? `
        <div class="creds">
          <div class="creds-item"><span>Usuario</span><strong>${esc(data.codigo)}</strong></div>
          <div class="creds-item"><span>Contraseña</span><strong>${esc(data.password || '—')}</strong></div>
          <div class="creds-item"><span>Perfil</span><strong>${esc(data.perfil)}</strong></div>
          <div class="creds-item"><span>Límite</span><strong>${esc(data.limite)}</strong></div>
          <div class="creds-item"><span>Lote</span><strong>${esc(data.lote)}</strong></div>
          <div class="creds-item"><span>Nota</span><strong>${esc(data.nota || '—')}</strong></div>
        </div>
      ` : '';
      const t = Date.now();
      const base = '/api/tickets/' + encodeURIComponent(codigo) + '/qr';
      body.innerHTML = `
        <h2>QR · ${esc(codigo)}</h2>
        ${creds}
        <div class="qr-grid">
          <div>
            <h3>Tarjeta completa</h3>
            <img class="qr-card-img" src="${base}/ticket?t=${t}" alt="Tarjeta QR ${esc(codigo)}">
          </div>
          <div>
            <h3>QR WiFi</h3>
            <img class="qr-card-img" src="${base}/wifi?t=${t}" alt="QR WiFi ${esc(codigo)}">
            <p class="small muted">SSID: ${esc(estado.ssid || configUi.ssid)} · WPA2</p>
          </div>
          <div>
            <h3>QR Acceso / Login</h3>
            <img class="qr-card-img" src="${base}/login?t=${t}" alt="QR Login ${esc(codigo)}">
            <p class="small muted">Escanear tras conectarse al WiFi</p>
          </div>
        </div>
        <div class="modal-actions">
          <a class="button" href="${base}/ticket?t=${t}" download="${esc(codigo)}_ticket.png">Descargar tarjeta</a>
          <a class="button ghost" href="${base}/wifi?t=${t}" download="${esc(codigo)}_wifi.png">Descargar QR WiFi</a>
          <a class="button ghost" href="${base}/login?t=${t}" download="${esc(codigo)}_login.png">Descargar QR login</a>
          ${data.es_ticket ? `<button class="danger" data-action="eliminar" data-codigo="${esc(codigo)}">Eliminar ticket</button>` : ''}
        </div>
        <p class="small muted">Flujo: 1) Conectarse al WiFi con QR WiFi o manualmente 2) Escanear QR de acceso para loguearse automáticamente.</p>
      `;
    } catch (e) {
      body.innerHTML = `<h2>Error</h2><p>${esc(e.message)}</p>`;
    }
  }

  function cerrarModal() {
    $('#modal').classList.add('hidden');
  }

  function mostrarResultado(data) {
    const modal = $('#modal');
    const body = $('#modal-body');
    const lista = (data.tickets || []).map(t => `
      <tr>
        <td><strong>${esc(t.codigo)}</strong></td>
        <td>${esc(t.password)}</td>
        <td>${esc(t.limite_uptime)}</td>
        <td><a href="${t.card_url}" target="_blank">Tarjeta</a> · <a href="${t.login_qr_url}" target="_blank">Login</a> · <a href="${t.wifi_qr_url}" target="_blank">WiFi</a></td>
      </tr>
    `).join('');
    body.innerHTML = `
      <h2>Lote creado: ${esc(data.lote)}</h2>
      <p class="muted">Guardado en ${esc(data.carpeta)}</p>
      <div class="modal-actions">
        <a class="button" href="${data.csv_url}">Descargar CSV</a>
        <a class="button ghost" href="${data.html_url}" target="_blank">Abrir HTML imprimible</a>
      </div>
      <div class="table-wrap" style="margin-top:1rem">
        <table>
          <thead><tr><th>Código</th><th>Contraseña</th><th>Vigencia</th><th>QR</th></tr></thead>
          <tbody>${lista}</tbody>
        </table>
      </div>
      <p class="small muted">Puedes ver todos los tickets en la pestaña "Tickets".</p>
    `;
    modal.classList.remove('hidden');
  }

  // Events
  $$('.presets .chip').forEach(btn => {
    btn.addEventListener('click', () => {
      const target = btn.parentElement.dataset.target;
      const input = document.getElementById(target);
      if (input) input.value = btn.textContent.trim();
    });
  });

  $$('.tabs .tab').forEach(btn => {
    btn.addEventListener('click', () => {
      $$('.tabs .tab').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      tabActiva = btn.dataset.tab;
      $$('.tab-panel').forEach(p => p.classList.add('hidden'));
      const panel = document.getElementById('tab-' + tabActiva);
      if (panel) panel.classList.remove('hidden');
      if (tabActiva === 'lotes' && !lotes.length) cargarLotes();
      render();
    });
  });

  $('#buscador').addEventListener('input', e => {
    filtro = e.target.value;
    render();
  });

  $('#btn-refrescar-lotes').addEventListener('click', cargarLotes);

  const chkMismo = document.getElementById('usar-mismo-login');
  const wrapDisp = document.getElementById('wrap-dispositivos');
  if (chkMismo && wrapDisp) {
    chkMismo.addEventListener('change', () => {
      wrapDisp.style.display = chkMismo.checked ? 'flex' : 'none';
    });
  }

  $('#form-crear').addEventListener('submit', async e => {
    e.preventDefault();
    const mismoLogin = document.getElementById('usar-mismo-login')?.checked || false;
    const dispositivos = Number(document.getElementById('dispositivos-simultaneos')?.value || 5);
    const cantidadInput = Number($('#crear-cantidad').value || 1);
    const payload = {
      cantidad: mismoLogin ? 1 : cantidadInput,
      tiempo: $('#crear-tiempo').value.trim() || '1h',
      lote: $('#crear-lote').value.trim(),
      nota: $('#crear-nota').value.trim(),
      limite_bytes: $('#crear-bytes').value.trim(),
      rate_limit: $('#crear-rate').value.trim(),
      mismo_login: mismoLogin,
      dispositivos_simultaneos: mismoLogin ? dispositivos : 1,
    };
    const btn = $('#form-crear button[type=submit]');
    const old = btn.textContent;
    btn.disabled = true;
    btn.textContent = 'Generando...';
    try {
      const res = await apiFetch('/api/tickets', { method: 'POST', body: JSON.stringify(payload) });
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.error || 'Error al crear tickets');
      toast('Tickets creados correctamente');
      $('#crear-lote').value = '';
      $('#crear-nota').value = '';
      mostrarResultado(data);
      await cargarEstado();
      await cargarLotes();
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      btn.disabled = false;
      btn.textContent = old;
    }
  });

  document.addEventListener('click', async e => {
    const close = e.target.closest('[data-close]');
    if (close) { cerrarModal(); return; }
    const qr = e.target.closest('[data-action="qr"]');
    if (qr) { abrirQr(qr.dataset.codigo); return; }
    const disc = e.target.closest('[data-action="desconectar"]');
    if (disc) {
      const user = disc.dataset.user;
      if (!confirm('¿Desconectar a ' + user + '?')) return;
      try {
        const res = await apiFetch('/api/activos/' + encodeURIComponent(user) + '/desconectar', { method: 'POST' });
        const data = await res.json();
        if (!data.ok) throw new Error(data.error);
        toast('Sesión desconectada');
        await cargarEstado();
      } catch (err) { toast(err.message, 'error'); }
      return;
    }
    const del = e.target.closest('[data-action="eliminar"]');
    if (del) {
      const cod = del.dataset.codigo;
      if (!confirm('¿Eliminar el ticket ' + cod + '? Se borrará el usuario, sesiones y cookies.')) return;
      try {
        const res = await apiFetch('/api/tickets/' + encodeURIComponent(cod) + '/eliminar', { method: 'POST' });
        const data = await res.json();
        if (!data.ok) throw new Error(data.error);
        toast('Ticket eliminado');
        await cargarEstado();
        await cargarLotes();
        cerrarModal();
      } catch (err) { toast(err.message, 'error'); }
      return;
    }
    const dellote = e.target.closest('[data-action="eliminar-lote"]');
    if (dellote) {
      const lote = dellote.dataset.lote;
      if (!confirm('¿Eliminar TODOS los tickets QR del lote ' + lote + ' del router? Los archivos en disco se mantienen.')) return;
      try {
        const res = await apiFetch('/api/lotes/' + encodeURIComponent(lote) + '/eliminar', { method: 'POST' });
        const data = await res.json();
        if (!data.ok) throw new Error(data.error);
        toast('Lote eliminado: ' + data.eliminados + ' ticket(s)');
        await cargarEstado();
        await cargarLotes();
      } catch (err) { toast(err.message, 'error'); }
      return;
    }
  });

  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') cerrarModal();
  });

  // Init
  render();
  setInterval(cargarEstado, 2000);
  setInterval(render, 1000);
  cargarLotes();
})();
