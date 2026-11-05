// Screens shared by several profiles: grid, schedule, free room, request form, hours, booking detail.
(() => {
  const { view } = App;
  const loc = () => Store.session.locationId;
  const hasCalendarLib = () => typeof window.EventCalendar !== 'undefined';
  const CDN_WARNING = `<div class="alert alert-warn" role="alert"><span class="alert-icon" aria-hidden="true">!</span>
    <p>Não foi possível carregar o calendário (EventCalendar) pela CDN. Está a ser usada a vista em tabela, que tem a mesma informação.</p></div>`;

  // First working day from today, so the grid does not open empty on a weekend.
  const defaultDay = () => {
    let date = T.date(T.now());
    const { days } = Store.settings(loc());
    for (let i = 0; i < 7 && !days.includes(T.weekday(date)); i += 1) date = T.addDays(date, 1);
    return date;
  };

  const blockClasses = (b) => {
    if (b.kind === 'busy') return ['ev-busy'];
    if (b.kind === 'exclusive') return ['ev-exclusive'];
    const classes = [b.kind === 'pending' ? 'ev-pending' : 'ev-approved'];
    if (b.mine) classes.push('ev-mine');
    return classes;
  };
  const blockStatusText = (b) => {
    if (b.kind === 'busy') return 'Ocupado';
    if (b.kind === 'exclusive') return b.label;
    return `${b.kind === 'pending' ? 'Pendente' : 'Aprovada'} · ${b.label}`;
  };

  const ecTime = (s) => `${s.replace('T', ' ')}:00`;
  const localIso = (d) => `${d.getFullYear()}-${T.pad(d.getMonth() + 1)}-${T.pad(d.getDate())}T${T.pad(d.getHours())}:${T.pad(d.getMinutes())}`;

  const participantRow = (candidates, rowId) => `
    <div class="part-row" data-part-row>
      <div class="field">
        <label for="part-user-${rowId}">Pessoa</label>
        <select id="part-user-${rowId}" data-part-user>
          <option value="">Escolher…</option>
          ${candidates.map((u) => `<option value="${esc(u.id)}">${esc(u.name)}</option>`).join('')}
        </select>
      </div>
      <div class="field">
        <label for="part-start-${rowId}">De</label>
        <input type="time" id="part-start-${rowId}" data-part-start>
      </div>
      <div class="field">
        <label for="part-end-${rowId}">Até</label>
        <input type="time" id="part-end-${rowId}" data-part-end>
      </div>
      <button type="button" class="btn btn-small" data-part-remove>Retirar</button>
    </div>`;

  // ---- Grid ----

  const gridLegend = (details) => (details ? `
    <ul class="legend" aria-label="Legenda">
      <li><span class="swatch ev-approved"></span>Aprovada</li>
      <li><span class="swatch ev-pending"></span>Pendente</li>
      <li><span class="swatch ev-exclusive"></span>Sala exclusiva</li>
      <li><span class="swatch ev-closed"></span>Bloqueada</li>
    </ul>` : `
    <ul class="legend" aria-label="Legenda">
      <li><span class="swatch ev-mine"></span>As minhas reservas</li>
      <li><span class="swatch ev-pending ev-mine"></span>Os meus pedidos pendentes</li>
      <li><span class="swatch ev-busy"></span>Ocupado</li>
      <li><span class="swatch ev-closed"></span>Bloqueada</li>
    </ul>`);

  const closureBanner = (locationId, date) => {
    const closures = Store.closuresOn(locationId, date);
    return closures.map((c) => `
      <div class="alert alert-warn"><span class="alert-icon" aria-hidden="true">!</span>
        <p><strong>${esc(c.reason)}</strong> · ${c.roomId ? esc(Store.roomName(c.roomId)) : 'todas as salas'}${c.source === 'manual' ? `, ${T.time(c.start)}–${T.time(c.end)}` : ''}</p>
      </div>`).join('');
  };

  const gridTable = (locationId, date, blocks) => {
    const closures = Store.closuresOn(locationId, date);
    const rows = Store.roomsOf(locationId).map((room) => {
      const own = blocks.filter((b) => b.roomId === room.id).sort((a, b) => a.start.localeCompare(b.start));
      const closed = closures.filter((c) => !c.roomId || c.roomId === room.id);
      const items = [
        ...closed.map((c) => `<li>Bloqueada: ${esc(c.reason)}</li>`),
        ...own.map((b) => {
          const text = `${T.time(b.start)}–${T.time(b.end)} · ${esc(blockStatusText(b))}`;
          return b.bookingId
            ? `<li><button type="button" class="btn btn-small" data-act="open-booking" data-id="${esc(b.bookingId)}">${text}</button></li>`
            : `<li>${text}</li>`;
        }),
      ];
      return `<tr><th scope="row">${esc(room.name)}</th><td>${items.length ? `<ul style="margin:0;padding-left:1rem">${items.join('')}</ul>` : 'Livre'}</td></tr>`;
    }).join('');
    return UI.tableWrap('Ocupação por sala', `<table>
      <caption>Ocupação em ${esc(T.fmtDateLong(date))}</caption>
      <thead><tr><th scope="col">Sala</th><th scope="col">Blocos</th></tr></thead>
      <tbody>${rows}</tbody></table>`);
  };

  const mountGridCalendar = (host, locationId, date, blocks) => {
    const rules = Store.settings(locationId);
    const details = Store.can('salas.view_details', locationId);
    const canDrag = Store.can('salas.edit_any', locationId);
    const roomIds = Store.roomsOf(locationId).map((r) => r.id);
    const events = blocks.map((b, i) => ({
      id: b.bookingId || `block-${i}`,
      resourceIds: [b.roomId],
      start: ecTime(b.start),
      end: ecTime(b.end),
      title: blockStatusText(b),
      classNames: blockClasses(b),
      startEditable: canDrag && b.kind === 'approved',
      durationEditable: false,
      extendedProps: { bookingId: b.bookingId || null, text: blockStatusText(b), range: `${T.time(b.start)}–${T.time(b.end)}`, label: b.label },
    }));
    Store.closuresOn(locationId, date).forEach((c, i) => {
      events.push({
        id: `closure-${i}`,
        resourceIds: c.roomId ? [c.roomId] : roomIds,
        start: ecTime(c.source === 'holiday' ? T.combine(date, rules.open) : c.start),
        end: ecTime(c.source === 'holiday' ? T.combine(date, rules.close) : c.end),
        display: 'background',
        classNames: ['ev-closed'],
      });
    });

    const calendar = window.EventCalendar.create(host, {
      view: 'resourceTimelineDay',
      date,
      locale: 'pt-PT',
      headerToolbar: { start: '', center: '', end: '' },
      resources: Store.roomsOf(locationId).map((r) => ({ id: r.id, title: r.name })),
      events,
      height: 'auto',
      nowIndicator: true,
      slotMinTime: rules.open,
      slotMaxTime: rules.close,
      slotDuration: { minutes: rules.blockMin },
      slotLabelInterval: { hours: 1 },
      slotLabelFormat: { hour: '2-digit', minute: '2-digit', hour12: false },
      slotWidth: rules.blockMin === 15 ? 24 : 48,
      snapDuration: { minutes: rules.blockMin },
      editable: false,
      eventContent: (info) => {
        const { label, range } = info.event.extendedProps;
        if (!range) return undefined;
        const pendingPrefix = info.event.classNames.includes('ev-pending') ? 'Pendente · ' : '';
        return { html: `<span class="ev-text"><b>${esc(pendingPrefix + label)}</b><span>${esc(range)}</span></span>` };
      },
      eventDidMount: (info) => {
        const { bookingId, text, range } = info.event.extendedProps;
        if (!range) return;
        info.el.setAttribute('aria-label', `${text}, ${range}`);
        info.el.title = `${text}, ${range}`;
        if (bookingId) {
          info.el.setAttribute('tabindex', '0');
          info.el.setAttribute('role', 'button');
          info.el.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              Views.openBooking(bookingId);
            }
          });
        } else {
          info.el.removeAttribute('tabindex');
          info.el.removeAttribute('role');
        }
      },
      eventClick: (info) => {
        const { bookingId } = info.event.extendedProps;
        if (bookingId) Views.openBooking(bookingId);
      },
      eventDrop: (info) => {
        const { bookingId } = info.event.extendedProps;
        const result = Store.moveBooking(bookingId, {
          roomId: info.newResource ? String(info.newResource.id) : Store.booking(bookingId).roomId,
          start: localIso(info.event.start),
          end: localIso(info.event.end),
        });
        if (!result.ok) {
          info.revert();
          UI.toast('Não foi possível mover a reserva.', { line: result.errors.join(' '), error: true });
          return;
        }
        App.render();
        UI.bookingToast(result.booking, 'Reserva movida.');
      },
      dateClick: (info) => {
        if (!info.resource) return;
        const start = localIso(info.date);
        view.prefill = { roomId: String(info.resource.id), date: T.date(start), start: T.time(start), end: T.time(T.addMin(start, 60)) };
        App.go(Store.can('salas.direct_booking', locationId) ? 'marcacao' : 'pedido');
      },
    });
    App.registerCalendar(calendar);
  };

  Views.grelha = (el) => {
    const locationId = loc();
    if (!view.grid.date) view.grid.date = defaultDay();
    const { date } = view.grid;
    const details = Store.can('salas.view_details', locationId);
    const canUseCalendar = hasCalendarLib();
    const mode = canUseCalendar ? view.grid.mode : 'table';
    const blocks = Store.gridBlocks(locationId, date);

    el.innerHTML = `
      <div class="page-head">
        <h1>Grelha do polo</h1>
        <p class="lead">${details
    ? 'Salas nas linhas e horas nas colunas, com nomes e pedidos pendentes. Arrasta uma reserva aprovada para a mover, ou clica numa zona livre para marcar diretamente.'
    : 'Salas nas linhas e horas nas colunas. As reservas dos outros aparecem como "Ocupado". Clica numa zona livre para fazer um pedido.'}</p>
      </div>
      ${canUseCalendar ? '' : CDN_WARNING}
      <div class="toolbar">
        <button type="button" class="btn" data-day="-1">Dia anterior</button>
        <button type="button" class="btn" data-day="0">Hoje</button>
        <button type="button" class="btn" data-day="1">Dia seguinte</button>
        <div class="field">
          <label for="grid-date">Dia</label>
          <input type="date" id="grid-date" value="${esc(date)}">
        </div>
        <span class="spacer"></span>
        ${canUseCalendar ? `<div class="segmented" role="group" aria-label="Forma de ver">
          <button type="button" data-mode="grid" aria-pressed="${mode === 'grid'}">Grelha</button>
          <button type="button" data-mode="table" aria-pressed="${mode === 'table'}">Tabela</button>
        </div>` : ''}
      </div>
      <h2>${esc(T.fmtDateLong(date))}</h2>
      ${closureBanner(locationId, date)}
      ${mode === 'grid' ? '<div class="cal-host" id="grid-cal"></div>' : gridTable(locationId, date, blocks)}
      ${gridLegend(details)}`;

    el.querySelectorAll('[data-day]').forEach((button) => button.addEventListener('click', () => {
      const delta = Number(button.dataset.day);
      view.grid.date = delta === 0 ? defaultDay() : T.addDays(date, delta);
      App.render();
    }));
    el.querySelector('#grid-date').addEventListener('change', (e) => {
      if (e.target.value) {
        view.grid.date = e.target.value;
        App.render();
      }
    });
    el.querySelectorAll('[data-mode]').forEach((button) => button.addEventListener('click', () => {
      view.grid.mode = button.dataset.mode;
      App.render();
    }));
    if (mode === 'grid') mountGridCalendar(el.querySelector('#grid-cal'), locationId, date, blocks);
  };

  // ---- My schedule ----

  const scheduleRole = (b, userId) => (b.ownerId === userId ? 'Titular' : 'Participante');

  Views.horario = (el) => {
    const me = Store.currentUser();
    if (!view.schedule.date) view.schedule.date = defaultDay();
    const { date, mode } = view.schedule;
    const from = mode === 'week' ? T.monday(date) : date;
    const to = mode === 'week' ? T.addDays(from, 6) : date;
    const items = Store.scheduleFor(me.id, from, to);
    const useCalendar = hasCalendarLib() && window.matchMedia('(min-width: 721px)').matches;

    const rows = items.map((b) => `<tr>
      <th scope="row">${esc(T.fmtDate(T.date(b.start)))}<br>${T.time(b.start)}–${T.time(b.end)}</th>
      <td>${esc(Store.roomName(b.roomId))}</td>
      <td><span class="badge badge-loc">${esc(Store.location(b.locationId).name)}</span></td>
      <td>${UI.statusBadge(b.status)}</td>
      <td>${scheduleRole(b, me.id)}</td>
      <td><button type="button" class="btn btn-small" data-act="open-booking" data-id="${esc(b.id)}">Detalhes</button></td>
    </tr>`).join('');

    el.innerHTML = `
      <div class="page-head">
        <h1>O meu horário</h1>
        <p class="lead">Todas as tuas reservas e pedidos, em todos os polos, sem divisão por sala. Os pedidos pendentes estão marcados à parte.</p>
      </div>
      <div class="toolbar">
        <button type="button" class="btn" data-move="-1">${mode === 'week' ? 'Semana anterior' : 'Dia anterior'}</button>
        <button type="button" class="btn" data-move="0">Hoje</button>
        <button type="button" class="btn" data-move="1">${mode === 'week' ? 'Semana seguinte' : 'Dia seguinte'}</button>
        <span class="spacer"></span>
        <div class="segmented" role="group" aria-label="Período">
          <button type="button" data-sched="day" aria-pressed="${mode === 'day'}">Dia</button>
          <button type="button" data-sched="week" aria-pressed="${mode === 'week'}">Semana</button>
        </div>
      </div>
      <h2>${mode === 'week' ? `Semana de ${esc(T.fmtDate(from))} a ${esc(T.fmtDate(T.addDays(from, 4)))}` : esc(T.fmtDateLong(date))}</h2>
      ${useCalendar ? '<div class="cal-host" id="sched-cal" style="margin-bottom:1rem"></div>' : ''}
      ${items.length
    ? UI.tableWrap('Lista do horário', `<table><caption>Lista</caption>
        <thead><tr><th scope="col">Quando</th><th scope="col">Sala</th><th scope="col">Polo</th><th scope="col">Estado</th><th scope="col">Papel</th><th scope="col">Ações</th></tr></thead>
        <tbody>${rows}</tbody></table>`)
    : '<div class="alert alert-info"><p>Sem reservas nem pedidos neste período.</p></div>'}`;

    el.querySelectorAll('[data-move]').forEach((button) => button.addEventListener('click', () => {
      const delta = Number(button.dataset.move);
      view.schedule.date = delta === 0 ? defaultDay() : T.addDays(date, delta * (mode === 'week' ? 7 : 1));
      App.render();
    }));
    el.querySelectorAll('[data-sched]').forEach((button) => button.addEventListener('click', () => {
      view.schedule.mode = button.dataset.sched;
      App.render();
    }));

    if (useCalendar) {
      const calendar = window.EventCalendar.create(el.querySelector('#sched-cal'), {
        view: mode === 'week' ? 'timeGridWeek' : 'timeGridDay',
        date,
        locale: 'pt-PT',
        firstDay: 1,
        hiddenDays: [0, 6],
        allDaySlot: false,
        headerToolbar: { start: '', center: '', end: '' },
        slotMinTime: '08:00',
        slotMaxTime: '20:00',
        slotDuration: '00:30',
        slotHeight: 22,
        nowIndicator: true,
        height: 'auto',
        slotLabelFormat: { hour: '2-digit', minute: '2-digit', hour12: false },
        dayHeaderFormat: { weekday: 'short', day: 'numeric', month: 'short' },
        events: items.map((b) => ({
          id: b.id,
          start: ecTime(b.start),
          end: ecTime(b.end),
          title: Store.roomName(b.roomId),
          classNames: [b.status === 'pending' ? 'ev-pending' : 'ev-approved', 'ev-mine'],
          extendedProps: { locationName: Store.location(b.locationId).name, status: b.status },
        })),
        eventContent: (info) => {
          const { locationName, status } = info.event.extendedProps;
          return { html: `<span class="ev-text"><b>${esc(info.event.title)}</b><span>${esc(locationName)}${status === 'pending' ? ' · Pendente' : ''}</span></span>` };
        },
        eventDidMount: (info) => {
          const { locationName, status } = info.event.extendedProps;
          info.el.setAttribute('aria-label', `${info.event.title}, ${locationName}, ${Store.STATUS_LABEL[status]}`);
          info.el.setAttribute('tabindex', '0');
          info.el.setAttribute('role', 'button');
          info.el.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              Views.openBooking(String(info.event.id));
            }
          });
        },
        eventClick: (info) => Views.openBooking(String(info.event.id)),
      });
      App.registerCalendar(calendar);
    }
  };

  // ---- Find a free room ----

  // The day after the advance limit, so the suggested morning time is valid straight away.
  const firstRequestDay = (locationId) => {
    const rules = Store.settings(locationId);
    let date = T.addDays(T.date(T.addMin(T.now(), rules.minAdvanceHours * 60)), 1);
    for (let i = 0; i < 14; i += 1) {
      if (rules.days.includes(T.weekday(date)) && !Store.closuresOn(locationId, date).some((c) => !c.roomId)) break;
      date = T.addDays(date, 1);
    }
    return date;
  };

  Views['sala-livre'] = (el) => {
    const locationId = loc();
    const rules = Store.settings(locationId);
    const durations = [30, 45, 60, 90, 120, 180, 240].filter((m) => m >= rules.minDurationMin && m <= rules.maxDurationMin && m % rules.blockMin === 0);
    el.innerHTML = `
      <div class="page-head">
        <h1>Encontrar sala livre</h1>
        <p class="lead">Procura em ${esc(Store.location(locationId).name)} as salas livres durante todo o intervalo e faz logo o pedido.</p>
      </div>
      <form class="card" id="find-form" novalidate>
        <div class="form-grid">
          <div class="field"><label for="find-date">Dia</label><input type="date" id="find-date" value="${esc(firstRequestDay(locationId))}" required></div>
          <div class="field"><label for="find-time">Hora de início</label><input type="time" id="find-time" value="10:00" step="${rules.blockMin * 60}" required></div>
          <div class="field"><label for="find-duration">Duração</label>
            <select id="find-duration">${durations.map((m) => `<option value="${m}"${m === 60 ? ' selected' : ''}>${esc(T.fmtMinutes(m))}</option>`).join('')}</select>
          </div>
        </div>
        <div class="form-actions"><button type="submit" class="btn btn-primary">Procurar</button></div>
      </form>
      <div id="find-results" aria-live="polite"></div>`;

    const results = el.querySelector('#find-results');
    const search = (e) => {
      if (e) e.preventDefault();
      const date = el.querySelector('#find-date').value;
      const time = el.querySelector('#find-time').value;
      const duration = Number(el.querySelector('#find-duration').value);
      if (!date || !time) {
        UI.showErrors(results, ['Indica o dia e a hora de início.']);
        return;
      }
      const start = T.combine(date, time);
      const end = T.addMin(start, duration);
      const problems = Store.validateBooking({ locationId, start, end, ownerId: Store.currentUser().id, participants: [] }, { mode: 'request' })
        .filter((text) => !text.startsWith('Escolhe'));
      if (problems.length) {
        UI.showErrors(results, problems);
        return;
      }
      const free = Store.freeRooms(locationId, start, end, { ownerId: Store.currentUser().id });
      results.innerHTML = free.length ? `
        <h2>${free.length} ${free.length === 1 ? 'sala livre' : 'salas livres'} em ${esc(T.fmtRange(start, end))}</h2>
        ${UI.tableWrap('Salas livres', `<table>
          <thead><tr><th scope="col">Sala</th><th scope="col">Ações</th></tr></thead>
          <tbody>${free.map((r) => `<tr><th scope="row">${esc(r.name)}</th>
            <td><button type="button" class="btn btn-small btn-primary" data-room="${esc(r.id)}">Pedir esta sala</button></td></tr>`).join('')}</tbody>
        </table>`)}` : '<div class="alert alert-info"><p>Não há salas livres durante todo este intervalo. Experimenta outra hora ou uma duração mais curta.</p></div>';
      results.querySelectorAll('[data-room]').forEach((button) => button.addEventListener('click', () => {
        view.prefill = { roomId: button.dataset.room, date, start: time, end: T.time(end) };
        App.go('pedido');
      }));
    };
    el.querySelector('#find-form').addEventListener('submit', search);
  };

  // ---- Request and direct booking form ----

  Views.bookingForm = (el, mode) => {
    const locationId = loc();
    const rules = Store.settings(locationId);
    const me = Store.currentUser();
    const isDirect = mode === 'direct';
    const prefill = view.prefill || {};
    view.prefill = null;
    const members = Store.membersOf(locationId).filter((u) => Store.activeMemberships(u.id, locationId).length && u.status !== 'inactive');
    let rowSeq = 0;

    el.innerHTML = `
      <div class="page-head">
        <h1>${isDirect ? 'Marcação direta' : 'Novo pedido'}</h1>
        <p class="lead">${isDirect
    ? 'A reserva fica logo aprovada, sem passar pela fila e sem o limite de antecedência. Mesmo assim, não é possível criar conflitos.'
    : `O pedido entra na fila de ${esc(Store.location(locationId).name)}, por ordem de chegada. Precisa de ${rules.minAdvanceHours} h de antecedência e pode durar de ${esc(T.fmtMinutes(rules.minDurationMin))} a ${esc(T.fmtMinutes(rules.maxDurationMin))}.`}</p>
      </div>
      <form id="booking-form" class="card" novalidate>
        <div id="form-errors"></div>
        <div class="form-grid">
          ${isDirect ? `<div class="field"><label for="f-owner">Titular</label>
            <select id="f-owner" required><option value="">Escolher…</option>
            ${members.map((u) => `<option value="${esc(u.id)}">${esc(u.name)}</option>`).join('')}</select></div>` : ''}
          <div class="field"><label for="f-room">Sala</label>
            <select id="f-room" required><option value="">Escolher…</option>
            ${Store.roomsOf(locationId).map((r) => `<option value="${esc(r.id)}"${prefill.roomId === r.id ? ' selected' : ''}>${esc(r.name)}</option>`).join('')}</select></div>
          <div class="field"><label for="f-date">Dia</label><input type="date" id="f-date" required value="${esc(prefill.date || firstRequestDay(locationId))}"></div>
          <div class="field"><label for="f-start">Início</label><input type="time" id="f-start" required step="${rules.blockMin * 60}" value="${esc(prefill.start || '10:00')}"></div>
          <div class="field"><label for="f-end">Fim</label><input type="time" id="f-end" required step="${rules.blockMin * 60}" value="${esc(prefill.end || '11:00')}"></div>
          <div class="field field-wide"><label for="f-notes">Notas logísticas</label>
            <textarea id="f-notes" aria-describedby="f-notes-hint"></textarea>
            <span class="hint" id="f-notes-hint">Só notas logísticas (material, disposição da sala). Não escrevas dados de utentes.</span></div>
        </div>
        <fieldset>
          <legend>Participantes e divisão do tempo</legend>
          <p class="hint">Os participantes entram logo e recebem uma notificação (simulada). Se deixares as horas em branco, a pessoa fica a reserva toda. Os intervalos podem sobrepor-se.</p>
          <div id="part-rows"></div>
          <button type="button" class="btn btn-small" id="part-add">Adicionar participante</button>
        </fieldset>
        <div class="form-actions actions"><button type="submit" class="btn btn-primary">${isDirect ? 'Marcar' : 'Submeter pedido'}</button></div>
      </form>`;

    const form = el.querySelector('#booking-form');
    const rowsHost = el.querySelector('#part-rows');
    const ownerSelect = el.querySelector('#f-owner');
    const candidates = () => {
      const ownerId = isDirect ? ownerSelect.value : me.id;
      return members.filter((u) => u.id !== ownerId);
    };
    const addRow = () => {
      rowSeq += 1;
      rowsHost.insertAdjacentHTML('beforeend', participantRow(candidates(), rowSeq));
      const row = rowsHost.lastElementChild;
      row.querySelector('[data-part-remove]').addEventListener('click', () => row.remove());
      row.querySelector('select').focus();
    };
    el.querySelector('#part-add').addEventListener('click', addRow);

    form.addEventListener('submit', (e) => {
      e.preventDefault();
      const date = el.querySelector('#f-date').value;
      const startTime = el.querySelector('#f-start').value;
      const endTime = el.querySelector('#f-end').value;
      const start = date && startTime ? T.combine(date, startTime) : '';
      const end = date && endTime ? T.combine(date, endTime) : '';
      const participants = [...rowsHost.querySelectorAll('[data-part-row]')].map((row) => {
        const from = row.querySelector('[data-part-start]').value;
        const to = row.querySelector('[data-part-end]').value;
        return {
          userId: row.querySelector('[data-part-user]').value,
          start: from ? T.combine(date, from) : start,
          end: to ? T.combine(date, to) : end,
        };
      }).filter((p) => p.userId);
      const draft = {
        locationId,
        roomId: el.querySelector('#f-room').value,
        ownerId: isDirect ? ownerSelect.value : me.id,
        start,
        end,
        notes: el.querySelector('#f-notes').value.trim(),
        participants,
      };
      const result = isDirect ? Store.directBooking(draft) : Store.submitRequest(draft);
      if (!result.ok) {
        UI.showErrors(el.querySelector('#form-errors'), result.errors);
        return;
      }
      App.render();
      UI.bookingToast(result.booking, isDirect ? 'Marcação feita.' : 'Pedido submetido.');
      Views.openBooking(result.booking.id);
    });
  };

  Views.pedido = (el) => Views.bookingForm(el, 'request');

  // ---- My hours ----

  const hoursFromDate = (period) => {
    const today = T.date(T.now());
    if (period === 'week') return T.monday(today);
    if (period === '4w') return T.addDays(T.monday(today), -28);
    return null;
  };

  let hoursPeriod = '4w';

  const openMenteeSchedule = (mentee, locationId) => {
    const today = T.date(T.now());
    const items = Store.scheduleFor(mentee.id, today, T.addDays(today, 56)).filter((b) => b.locationId === locationId);
    UI.open({
      title: `Horário de ${mentee.name}`,
      subtitle: `Só em ${Store.location(locationId).name}, porque é aí que a orientação existe.`,
      html: items.length ? UI.tableWrap('Horário da orientanda', `<table>
        <thead><tr><th scope="col">Quando</th><th scope="col">Sala</th><th scope="col">Estado</th></tr></thead>
        <tbody>${items.map((b) => `<tr><th scope="row">${esc(T.fmtRange(b.start, b.end))}</th><td>${esc(Store.roomName(b.roomId))}</td><td>${UI.statusBadge(b.status)}</td></tr>`).join('')}</tbody>
      </table>`) : '<p>Sem reservas futuras neste polo.</p>',
    });
  };

  Views.horas = (el) => {
    const me = Store.currentUser();
    const locationId = loc();
    const from = hoursFromDate(hoursPeriod);
    const items = Store.hoursItems(me.id, { from });
    const mentees = Store.menteesOf(me.id, locationId);
    const participants = Store.participantHours(me.id, { locationId, from });

    const byLocation = Store.locations.map((l) => ({
      location: l,
      minutes: Store.totalMinutes(items.filter((i) => i.booking.locationId === l.id)),
    })).filter((row) => row.minutes > 0);

    el.innerHTML = `
      <div class="page-head">
        <h1>As minhas horas</h1>
        <p class="lead">Soma dos intervalos de participação em reservas aprovadas que já passaram.</p>
      </div>
      <div class="toolbar">
        <div class="field"><label for="hours-period">Período</label>
          <select id="hours-period">
            <option value="week"${hoursPeriod === 'week' ? ' selected' : ''}>Esta semana</option>
            <option value="4w"${hoursPeriod === '4w' ? ' selected' : ''}>Últimas 4 semanas</option>
            <option value="all"${hoursPeriod === 'all' ? ' selected' : ''}>Tudo</option>
          </select></div>
        <span class="spacer"></span>
        <button type="button" class="btn" id="hours-csv">Exportar CSV</button>
      </div>
      <div class="kpis">
        <div class="kpi"><b>${esc(T.fmtMinutes(Store.totalMinutes(items)))}</b><span>Total no período</span></div>
        ${byLocation.map((row) => `<div class="kpi"><b>${esc(T.fmtMinutes(row.minutes))}</b><span>${esc(row.location.name)}</span></div>`).join('')}
      </div>
      ${mentees.length ? `<section class="card">
        <h2>Orientandas em ${esc(Store.location(locationId).name)}</h2>
        ${UI.tableWrap('Horas das orientandas', `<table>
          <thead><tr><th scope="col">Pessoa</th><th scope="col" class="num">Horas</th><th scope="col">Horário</th></tr></thead>
          <tbody>${mentees.map((o) => `<tr><th scope="row">${esc(Store.userName(o.menteeId))}</th>
            <td class="num">${esc(T.fmtMinutes(Store.totalMinutes(Store.hoursItems(o.menteeId, { locationId, from }))))}</td>
            <td><button type="button" class="btn btn-small" data-mentee="${esc(o.menteeId)}">Ver horário</button></td></tr>`).join('')}</tbody>
        </table>`)}
      </section>` : ''}
      ${participants.length ? `<section class="card">
        <h2>Participantes nas minhas reservas</h2>
        ${UI.tableWrap('Horas dos participantes', `<table>
          <thead><tr><th scope="col">Pessoa</th><th scope="col" class="num">Horas nas minhas reservas</th></tr></thead>
          <tbody>${participants.map((p) => `<tr><th scope="row">${esc(Store.userName(p.userId))}</th><td class="num">${esc(T.fmtMinutes(p.minutes))}</td></tr>`).join('')}</tbody>
        </table>`)}
      </section>` : ''}
      <section>
        <h2>Detalhe</h2>
        ${items.length ? UI.tableWrap('Detalhe das horas', `<table>
          <thead><tr><th scope="col">Quando</th><th scope="col">Sala</th><th scope="col">Polo</th><th scope="col">Papel</th><th scope="col" class="num">Horas</th><th scope="col">Ações</th></tr></thead>
          <tbody>${items.map((i) => `<tr><th scope="row">${esc(T.fmtRange(i.start, i.end))}</th>
            <td>${esc(Store.roomName(i.booking.roomId))}</td>
            <td><span class="badge badge-loc">${esc(Store.location(i.booking.locationId).name)}</span></td>
            <td>${esc(i.role)}</td>
            <td class="num">${esc(T.fmtMinutes(i.minutes))}</td>
            <td><button type="button" class="btn btn-small" data-act="open-booking" data-id="${esc(i.booking.id)}">Detalhes</button></td></tr>`).join('')}</tbody>
        </table>`) : '<div class="alert alert-info"><p>Sem horas neste período.</p></div>'}
      </section>`;

    el.querySelector('#hours-period').addEventListener('change', (e) => {
      hoursPeriod = e.target.value;
      App.render();
    });
    el.querySelectorAll('[data-mentee]').forEach((button) => button.addEventListener('click', () => {
      openMenteeSchedule(Store.user(button.dataset.mentee), locationId);
    }));
    el.querySelector('#hours-csv').addEventListener('click', () => {
      UI.downloadCsv('as-minhas-horas.csv', [
        ['Início', 'Fim', 'Sala', 'Polo', 'Papel', 'Minutos'],
        ...items.map((i) => [i.start.replace('T', ' '), i.end.replace('T', ' '), Store.roomName(i.booking.roomId), Store.location(i.booking.locationId).name, i.role, i.minutes]),
      ]);
    });
  };

  // ---- Booking detail and history ----

  const historyList = (b) => `
    <ol class="timeline">
      ${[...b.events].reverse().map((ev) => `<li>
        <span class="when">${esc(T.fmtDateTime(ev.at))} · ${esc(Store.userName(ev.by))}${ev.onBehalfOf ? ` · em nome de ${esc(Store.userName(ev.onBehalfOf))}` : ''}</span>
        <strong>${esc(ev.action)}</strong>
        ${ev.detail ? `<span class="change">${esc(ev.detail)}</span>` : ''}
        ${ev.before ? `<span class="change">Antes: ${esc(ev.before)} → Depois: ${esc(ev.after)}</span>` : ''}
      </li>`).join('')}
    </ol>`;

  const openCancel = (b) => {
    const preview = Store.cancelPreview(b);
    let notice = '<div class="alert alert-info"><p>A sala fica livre e os pedidos em fila para esse horário voltam a poder ser aprovados.</p></div>';
    if (preview.late) {
      notice = `<div class="alert alert-warn"><span class="alert-icon" aria-hidden="true">!</span><p>Faltam menos de ${preview.rules.lateCancelHours} h para o início: este cancelamento conta como <strong>tardio</strong>.</p></div>`;
    } else if (preview.exempt) {
      notice = '<div class="alert alert-ok"><p>Faltam poucas horas, mas não conta como tardio, porque o secretariado ou a coordenação alteraram esta reserva em cima da hora.</p></div>';
    }
    UI.open({
      title: 'Cancelar reserva',
      subtitle: `${Store.roomName(b.roomId)}, ${T.fmtRange(b.start, b.end)}`,
      html: `${notice}<div id="cancel-errors"></div><div class="actions">
        <button type="button" class="btn btn-danger" id="confirm-cancel">Confirmar cancelamento</button>
        <button type="button" class="btn" id="keep-booking">Manter a reserva</button></div>`,
      onReady: (root) => {
        root.querySelector('#keep-booking').addEventListener('click', () => Views.openBooking(b.id));
        root.querySelector('#confirm-cancel').addEventListener('click', () => {
          const result = Store.cancelBooking(b.id);
          if (!result.ok) {
            UI.showErrors(root.querySelector('#cancel-errors'), result.errors);
            return;
          }
          App.render();
          UI.bookingToast(result.booking, result.booking.lateCancel ? 'Reserva cancelada (tardio).' : 'Reserva cancelada.');
          Views.openBooking(b.id);
        });
      },
    });
  };

  const openEdit = (b) => {
    const rules = Store.settings(b.locationId);
    UI.open({
      title: 'Alterar sala ou hora',
      subtitle: `Reserva de ${Store.userName(b.ownerId)}`,
      html: `
        <form id="edit-form" novalidate>
          <div id="edit-errors"></div>
          <div class="form-grid">
            <div class="field"><label for="e-room">Sala</label><select id="e-room">
              ${Store.roomsOf(b.locationId).map((r) => `<option value="${esc(r.id)}"${r.id === b.roomId ? ' selected' : ''}>${esc(r.name)}</option>`).join('')}</select></div>
            <div class="field"><label for="e-date">Dia</label><input type="date" id="e-date" value="${esc(T.date(b.start))}"></div>
            <div class="field"><label for="e-start">Início</label><input type="time" id="e-start" step="${rules.blockMin * 60}" value="${esc(T.time(b.start))}"></div>
            <div class="field"><label for="e-end">Fim</label><input type="time" id="e-end" step="${rules.blockMin * 60}" value="${esc(T.time(b.end))}"></div>
          </div>
          <p class="hint">Se mudares a duração, os intervalos dos participantes voltam à reserva toda. Uma alteração com menos de ${rules.exceptionHours} h de antecedência faz com que o cancelamento pelo requerente nunca conte como tardio.</p>
          <div class="actions">
            <button type="submit" class="btn btn-primary">Guardar alteração</button>
            <button type="button" class="btn" id="edit-back">Voltar</button>
          </div>
        </form>`,
      onReady: (root) => {
        root.querySelector('#edit-back').addEventListener('click', () => Views.openBooking(b.id));
        root.querySelector('#edit-form').addEventListener('submit', (e) => {
          e.preventDefault();
          const date = root.querySelector('#e-date').value;
          const result = Store.moveBooking(b.id, {
            roomId: root.querySelector('#e-room').value,
            start: T.combine(date, root.querySelector('#e-start').value),
            end: T.combine(date, root.querySelector('#e-end').value),
          });
          if (!result.ok) {
            UI.showErrors(root.querySelector('#edit-errors'), result.errors);
            return;
          }
          App.render();
          UI.bookingToast(result.booking, 'Reserva alterada.');
          Views.openBooking(b.id);
        });
      },
    });
  };

  Views.openBooking = (id) => {
    const b = Store.booking(id);
    if (!b || !Store.canViewBooking(b)) return;
    const canEditParts = Store.canEditParticipants(b);
    const isStaff = Store.can('salas.view_details', b.locationId);
    const conflicts = b.status === 'pending' && isStaff ? Store.conflictsFor(b.roomId, b.start, b.end, { excludeId: b.id, ownerId: b.ownerId }) : [];
    const candidates = Store.membersOf(b.locationId)
      .filter((u) => !Store.isParty(b, u.id) && Store.activeMemberships(u.id, b.locationId).length);

    const participantsHtml = b.participations.length ? `<ul style="padding-left:1.1rem;margin:0 0 .75rem">
      ${b.participations.map((p) => `<li>${esc(Store.userName(p.userId))}, ${T.time(p.start)}–${T.time(p.end)}
        ${canEditParts ? `<button type="button" class="btn btn-small" data-remove-part="${esc(p.userId)}">Retirar</button>` : ''}</li>`).join('')}
    </ul>` : '<p class="hint">Sem participantes.</p>';

    UI.open({
      title: `${Store.roomName(b.roomId)} · ${T.fmtDate(T.date(b.start))}`,
      html: `
        <dl class="def">
          <dt>Estado</dt><dd>${UI.statusBadge(b.status)} ${b.lateCancel ? '<span class="badge badge-late">Cancelamento tardio</span>' : ''}</dd>
          <dt>Polo</dt><dd><span class="badge badge-loc">${esc(Store.location(b.locationId).name)}</span></dd>
          <dt>Horário</dt><dd>${T.time(b.start)}–${T.time(b.end)}</dd>
          <dt>Titular</dt><dd>${esc(Store.userName(b.ownerId))}</dd>
          ${b.notes ? `<dt>Notas</dt><dd>${esc(b.notes)}</dd>` : ''}
          ${b.refusalReason ? `<dt>Motivo da recusa</dt><dd>${esc(b.refusalReason)}</dd>` : ''}
        </dl>
        ${conflicts.length ? `<div class="alert alert-error"><span class="alert-icon" aria-hidden="true">!</span><ul>${conflicts.map((c) => `<li>Em conflito com ${esc(Store.describeConflict(c))}.</li>`).join('')}</ul></div>` : ''}
        <h3>Participantes</h3>
        ${participantsHtml}
        ${canEditParts ? `<form id="add-part" class="card" novalidate>
          <div id="part-errors"></div>
          <div class="part-row">
            <div class="field"><label for="dp-user">Pessoa</label><select id="dp-user"><option value="">Escolher…</option>
              ${candidates.map((u) => `<option value="${esc(u.id)}">${esc(u.name)}</option>`).join('')}</select></div>
            <div class="field"><label for="dp-start">De</label><input type="time" id="dp-start" value="${T.time(b.start)}"></div>
            <div class="field"><label for="dp-end">Até</label><input type="time" id="dp-end" value="${T.time(b.end)}"></div>
            <button type="submit" class="btn btn-small">Adicionar</button>
          </div>
        </form>` : ''}
        <div class="actions" style="margin-bottom:1rem">
          ${b.status === 'pending' && Store.can('salas.approve', b.locationId) ? '<button type="button" class="btn btn-primary" id="to-queue">Decidir na fila</button>' : ''}
          ${b.status === 'approved' && b.end > T.now() && Store.can('salas.edit_any', b.locationId) ? '<button type="button" class="btn" id="edit-booking">Alterar sala ou hora</button>' : ''}
          ${Store.canCancel(b) ? '<button type="button" class="btn btn-danger" id="cancel-booking">Cancelar</button>' : ''}
        </div>
        <h3>Histórico</h3>
        ${historyList(b)}`,
      onReady: (root) => {
        const on = (selector, handler) => {
          const node = root.querySelector(selector);
          if (node) node.addEventListener('click', handler);
        };
        on('#to-queue', () => {
          UI.close();
          App.go('fila');
        });
        on('#edit-booking', () => openEdit(b));
        on('#cancel-booking', () => openCancel(b));
        root.querySelectorAll('[data-remove-part]').forEach((button) => button.addEventListener('click', () => {
          const result = Store.removeParticipant(b.id, button.dataset.removePart);
          App.render();
          if (result.ok) UI.bookingToast(result.booking, 'Participante retirado.');
          Views.openBooking(b.id);
        }));
        const addForm = root.querySelector('#add-part');
        if (addForm) {
          addForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const date = T.date(b.start);
            const result = Store.addParticipant(
              b.id,
              root.querySelector('#dp-user').value,
              T.combine(date, root.querySelector('#dp-start').value),
              T.combine(date, root.querySelector('#dp-end').value),
            );
            if (!result.ok) {
              UI.showErrors(root.querySelector('#part-errors'), result.errors);
              return;
            }
            App.render();
            UI.bookingToast(result.booking, 'Participante adicionado (notificação simulada).');
            Views.openBooking(b.id);
          });
        }
      },
    });
  };
})();
