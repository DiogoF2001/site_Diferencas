// Shell of the prototype: routes, profile selector, dialog, toasts and small helpers.
window.Views = {};

window.esc = (value) => String(value ?? '').replace(/[&<>"']/g, (ch) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
}[ch]));

window.UI = (() => {
  const dialog = () => document.getElementById('dialog');

  const open = ({ title, html, onReady, subtitle }) => {
    const el = dialog();
    el.innerHTML = `
      <div class="dialog-head">
        <div>
          <h2 id="dialog-title">${esc(title)}</h2>
          ${subtitle ? `<p class="hint">${esc(subtitle)}</p>` : ''}
        </div>
        <button type="button" class="btn btn-small" data-dialog-close>Fechar</button>
      </div>
      <div class="dialog-body">${html}</div>`;
    el.querySelector('[data-dialog-close]').addEventListener('click', close);
    if (!el.open) el.showModal();
    el.scrollTop = 0;
    if (onReady) onReady(el.querySelector('.dialog-body'));
  };

  function close() {
    if (dialog().open) dialog().close();
  }

  const toast = (text, { line, bookingId, error } = {}) => {
    const box = document.getElementById('toasts');
    const item = document.createElement('div');
    item.className = `toast${error ? ' toast-error' : ''}`;
    item.innerHTML = `
      <p><strong>${esc(text)}</strong></p>
      ${line ? `<p class="toast-line">${esc(line)}</p>` : ''}
      <div class="actions">
        ${bookingId ? `<button type="button" class="btn btn-small" data-act="open-booking" data-id="${esc(bookingId)}">Ver histórico</button>` : ''}
        <button type="button" class="btn btn-small" data-toast-close>Fechar</button>
      </div>`;
    const remove = () => item.remove();
    item.querySelector('[data-toast-close]').addEventListener('click', remove);
    item.addEventListener('click', (e) => {
      if (e.target.closest('[data-act="open-booking"]')) remove();
    });
    while (box.children.length >= 2) box.firstChild.remove();
    box.appendChild(item);
    setTimeout(remove, 15000);
  };

  const clearToasts = () => {
    document.getElementById('toasts').innerHTML = '';
  };

  // Every booking action reports its latest history entry: date and time, and who did it.
  const bookingToast = (booking, text) => {
    const last = booking.events[booking.events.length - 1];
    toast(text, {
      line: `${T.fmtDateTime(last.at)} · ${Store.userName(last.by)} · ${last.action}`,
      bookingId: booking.id,
    });
  };

  const errors = (list) => `
    <div class="alert alert-error" role="alert" tabindex="-1">
      <span class="alert-icon" aria-hidden="true">!</span>
      <div>${list.length === 1 ? `<p>${esc(list[0])}</p>` : `<ul>${list.map((e) => `<li>${esc(e)}</li>`).join('')}</ul>`}</div>
    </div>`;

  const showErrors = (host, list) => {
    host.innerHTML = errors(list);
    host.querySelector('.alert').focus();
  };

  const statusBadge = (status) => `<span class="badge badge-${esc(status)}">${esc(Store.STATUS_LABEL[status])}</span>`;

  const tableWrap = (label, html) => `<div class="table-wrap" role="region" aria-label="${esc(label)}" tabindex="0">${html}</div>`;

  const downloadCsv = (filename, rows) => {
    const cell = (value) => `"${String(value ?? '').replace(/"/g, '""')}"`;
    const text = rows.map((row) => row.map(cell).join(';')).join('\r\n');
    const url = URL.createObjectURL(new Blob([`﻿${text}`], { type: 'text/csv;charset=utf-8' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    toast(`Ficheiro ${filename} criado.`);
  };

  return { open, close, toast, clearToasts, bookingToast, errors, showErrors, statusBadge, tableWrap, downloadCsv };
})();

window.App = (() => {
  const PROFILES = [
    { id: 'professional', label: 'Profissional' },
    { id: 'secretariat', label: 'Secretariado' },
    { id: 'coordination', label: 'Coordenação' },
    { id: 'admin', label: 'Admin' },
  ];

  // Each screen declares the permission it needs; the menu follows from it.
  const ROUTES = [
    { id: 'grelha', label: 'Grelha do polo', perm: 'salas.view_occupancy' },
    { id: 'horario', label: 'O meu horário', perm: 'salas.schedule' },
    { id: 'sala-livre', label: 'Encontrar sala livre', perm: 'salas.request' },
    { id: 'pedido', label: 'Novo pedido', perm: 'salas.request' },
    { id: 'horas', label: 'As minhas horas', perm: 'salas.own_hours' },
    { id: 'fila', label: 'Fila de pedidos', perm: 'salas.approve', count: () => Store.queue(Store.session.locationId).length },
    { id: 'marcacao', label: 'Marcação direta', perm: 'salas.direct_booking' },
    { id: 'bloqueios', label: 'Bloqueios', perm: 'salas.manage_closures' },
    { id: 'membros', label: 'Membros do polo', perm: 'core.manage_members' },
    { id: 'regras', label: 'Regras do polo', perm: 'salas.manage_rules' },
    { id: 'relatorios', label: 'Relatórios', perm: 'salas.reports' },
    { id: 'profissionais', label: 'Profissionais', perm: 'core.list_professionals' },
    { id: 'tecnica', label: 'Área técnica', perm: 'core.technical' },
  ];

  const view = {
    prefill: null,
    grid: { date: null, mode: 'grid' },
    schedule: { date: null, mode: 'week' },
  };
  const calendars = [];

  const allowedRoutes = () => ROUTES.filter((r) => Store.can(r.perm));
  const currentRouteId = () => {
    const match = location.hash.match(/^#\/([\w-]+)/);
    return match ? match[1] : null;
  };

  const registerCalendar = (calendar) => calendars.push(calendar);
  const destroyCalendars = () => {
    while (calendars.length) window.EventCalendar.destroy(calendars.pop());
  };

  const renderHeader = (routeId) => {
    const me = Store.currentUser();
    const { locationId } = Store.session;
    const roles = me.isSuperuser ? 'Admin (global)' : Store.rolesText(me.id, locationId);
    document.getElementById('persona').innerHTML = `A ver como <strong>${esc(me.name)}</strong> · ${esc(roles)} · ${esc(Store.location(locationId).name)}`;
    document.getElementById('main-nav').innerHTML = `<ul>${allowedRoutes().map((r) => {
      const count = r.count ? r.count() : 0;
      const current = r.id === routeId ? ' aria-current="page"' : '';
      const countText = count ? ` <span class="count"><span class="sr-only">por decidir: </span>${count}</span>` : '';
      return `<li><a href="#/${r.id}"${current}>${esc(r.label)}${countText}</a></li>`;
    }).join('')}</ul>`;
  };

  const render = ({ focus = false } = {}) => {
    Store.expireDue();
    const routes = allowedRoutes();
    let routeId = currentRouteId();
    if (!routes.some((r) => r.id === routeId)) {
      routeId = routes[0].id;
      history.replaceState(null, '', `#/${routeId}`);
    }
    destroyCalendars();
    renderHeader(routeId);
    const main = document.getElementById('main');
    const route = routes.find((r) => r.id === routeId);
    document.title = `${route.label} — Portal Diferenças (protótipo)`;
    main.innerHTML = '';
    window.Views[routeId](main);
    // Re-rendering removes the focused control: keep keyboard users inside the page content.
    if (!focus && document.activeElement === document.body) main.focus({ preventScroll: true });
    if (focus) {
      const heading = main.querySelector('h1');
      if (heading) {
        heading.setAttribute('tabindex', '-1');
        heading.focus();
      }
      window.scrollTo(0, 0);
    }
  };

  const go = (routeId) => {
    if (currentRouteId() === routeId) render({ focus: true });
    else location.hash = `#/${routeId}`;
  };

  const boot = () => {
    const profile = document.getElementById('profile-select');
    const loc = document.getElementById('location-select');
    profile.innerHTML = PROFILES.map((p) => `<option value="${p.id}">${esc(p.label)}</option>`).join('');
    loc.innerHTML = Store.locations.map((l) => `<option value="${l.id}">${esc(l.name)}</option>`).join('');
    profile.value = Store.session.profile;
    loc.value = Store.session.locationId;

    const onSwitch = () => {
      Store.session.profile = profile.value;
      Store.session.locationId = loc.value;
      view.prefill = null;
      UI.close();
      UI.clearToasts();
      render();
    };
    profile.addEventListener('change', onSwitch);
    loc.addEventListener('change', onSwitch);

    document.getElementById('reset-data').addEventListener('click', () => {
      Store.reset();
      view.prefill = null;
      view.grid.date = null;
      view.schedule.date = null;
      UI.close();
      render();
      UI.toast('Dados repostos.', { line: 'Voltaram os dados fictícios iniciais.' });
    });

    const logo = document.getElementById('brand-logo');
    const showText = () => {
      logo.hidden = true;
      document.getElementById('brand-text').hidden = false;
    };
    logo.addEventListener('error', showText);
    if (logo.complete && logo.naturalWidth === 0) showText();

    document.getElementById('skip-link').addEventListener('click', (e) => {
      e.preventDefault();
      document.getElementById('main').focus();
    });

    window.addEventListener('hashchange', () => {
      UI.close();
      UI.clearToasts();
      render({ focus: true });
    });

    // Shared by the views and the toasts.
    document.addEventListener('click', (e) => {
      const trigger = e.target.closest('[data-act="open-booking"]');
      if (trigger) window.Views.openBooking(trigger.dataset.id);
    });

    render();
  };

  return { view, render, go, boot, registerCalendar };
})();

document.addEventListener('DOMContentLoaded', () => window.App.boot());
