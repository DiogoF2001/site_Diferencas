// Secretariat screens (coordination and admin also have them): queue, direct booking,
// closures, location members and location rules.
(() => {
  const loc = () => Store.session.locationId;

  // ---- Queue ----

  const openOtherRoom = (b) => {
    const free = Store.freeRooms(b.locationId, b.start, b.end, { excludeId: b.id, ownerId: b.ownerId }).filter((r) => r.id !== b.roomId);
    UI.open({
      title: 'Aprovar noutra sala',
      subtitle: `${Store.userName(b.ownerId)}, ${T.fmtRange(b.start, b.end)}`,
      html: free.length ? `
        <form id="other-room" novalidate>
          <div id="other-errors"></div>
          <fieldset>
            <legend>Salas livres durante todo o intervalo</legend>
            <ul class="room-pick">
              ${free.map((r, i) => `<li><label class="check"><input type="radio" name="room" value="${esc(r.id)}"${i === 0 ? ' checked' : ''}> ${esc(r.name)}</label></li>`).join('')}
            </ul>
          </fieldset>
          <p class="hint">A reserva fica logo feita e o requerente é notificado (simulado). Depois, pode pedir para alterar a hora ou a sala, ou cancelar.</p>
          <div class="actions"><button type="submit" class="btn btn-primary">Aprovar na sala escolhida</button></div>
        </form>` : '<div class="alert alert-info"><p>Não há nenhuma sala livre durante todo este intervalo. Só resta recusar o pedido.</p></div>',
      onReady: (root) => {
        const form = root.querySelector('#other-room');
        if (!form) return;
        form.addEventListener('submit', (e) => {
          e.preventDefault();
          const result = Store.approveInRoom(b.id, form.elements.room.value);
          if (!result.ok) {
            UI.showErrors(root.querySelector('#other-errors'), result.errors);
            return;
          }
          UI.close();
          App.render();
          UI.bookingToast(result.booking, `Aprovado em ${Store.roomName(result.booking.roomId)}.`);
        });
      },
    });
  };

  const openRefuse = (b) => {
    UI.open({
      title: 'Recusar pedido',
      subtitle: `${Store.userName(b.ownerId)}, ${T.fmtRange(b.start, b.end)}`,
      html: `
        <form id="refuse-form" novalidate>
          <div id="refuse-errors"></div>
          <div class="field" style="margin-bottom:1rem">
            <label for="refuse-reason">Motivo (obrigatório)</label>
            <textarea id="refuse-reason" required aria-describedby="refuse-hint"></textarea>
            <span class="hint" id="refuse-hint">O requerente vê este motivo. Não escrevas dados de utentes.</span>
          </div>
          <div class="actions"><button type="submit" class="btn btn-danger">Recusar pedido</button></div>
        </form>`,
      onReady: (root) => {
        root.querySelector('#refuse-reason').focus();
        root.querySelector('#refuse-form').addEventListener('submit', (e) => {
          e.preventDefault();
          const result = Store.refuseBooking(b.id, root.querySelector('#refuse-reason').value);
          if (!result.ok) {
            UI.showErrors(root.querySelector('#refuse-errors'), result.errors);
            return;
          }
          UI.close();
          App.render();
          UI.bookingToast(result.booking, 'Pedido recusado.');
        });
      },
    });
  };

  const queueItem = (b, position) => {
    const conflicts = Store.conflictsFor(b.roomId, b.start, b.end, { excludeId: b.id, ownerId: b.ownerId });
    const overlaps = Store.pendingOverlaps(b);
    const free = Store.freeRooms(b.locationId, b.start, b.end, { excludeId: b.id, ownerId: b.ownerId }).filter((r) => r.id !== b.roomId);
    const blocked = conflicts.length > 0;
    return `<li class="card queue-item">
      <div class="queue-pos"><span class="sr-only">Posição na fila: </span>${position}.º</div>
      <div>
        <div class="queue-head">
          <h2>${esc(Store.userName(b.ownerId))}</h2>
          <span class="queue-wait">Pedido ${esc(T.since(b.createdAt))}</span>
        </div>
        <p class="meta"><strong>${esc(Store.roomName(b.roomId))}</strong> · ${esc(T.fmtRange(b.start, b.end))}</p>
        ${b.notes ? `<p class="meta">Notas: ${esc(b.notes)}</p>` : ''}
        ${b.participations.length ? `<p class="meta">Participantes: ${b.participations.map((p) => `${esc(Store.userName(p.userId))} (${T.time(p.start)}–${T.time(p.end)})`).join(', ')}</p>` : ''}
        ${blocked ? `<div class="alert alert-error"><span class="alert-icon" aria-hidden="true">!</span>
          <div><p><strong>Em conflito:</strong> ${conflicts.map((c) => esc(Store.describeConflict(c))).join('; ')}.</p>
          <p>${free.length ? `${free.length} ${free.length === 1 ? 'sala livre' : 'salas livres'} em todo o intervalo.` : 'Não há salas livres em todo o intervalo.'}</p></div></div>` : ''}
        ${!blocked && overlaps.length ? `<div class="alert alert-warn"><span class="alert-icon" aria-hidden="true">!</span>
          <p>Sobrepõe-se a ${overlaps.map((o) => `pedido de ${esc(Store.userName(o.ownerId))} (${T.time(o.start)}–${T.time(o.end)})`).join(', ')}. Ao aprovar um, o outro fica bloqueado nesta sala.</p></div>` : ''}
        <div class="actions">
          <button type="button" class="btn btn-primary" data-approve="${esc(b.id)}"${blocked ? ' disabled' : ''}>Aprovar nesta sala</button>
          <button type="button" class="btn" data-other="${esc(b.id)}">Aprovar noutra sala</button>
          <button type="button" class="btn btn-danger" data-refuse="${esc(b.id)}">Recusar</button>
          <button type="button" class="btn" data-act="open-booking" data-id="${esc(b.id)}">Detalhes e histórico</button>
          <button type="button" class="btn" data-show-day="${esc(T.date(b.start))}">Ver o dia na grelha</button>
        </div>
      </div>
    </li>`;
  };

  Views.fila = (el) => {
    const locationId = loc();
    const queue = Store.queue(locationId);
    const recent = Store.recentlyDecided(locationId, 5);
    el.innerHTML = `
      <div class="page-head">
        <h1>Fila de pedidos</h1>
        <p class="lead">Por ordem de chegada. A ordem é indicativa: podes decidir por qualquer ordem. Os conflitos são calculados no momento.</p>
      </div>
      ${queue.length ? `<ol style="list-style:none;margin:0;padding:0">${queue.map((b, i) => queueItem(b, i + 1)).join('')}</ol>`
    : '<div class="alert alert-ok"><p>A fila está vazia. Podes usar "Repor dados" para voltar a ter pedidos.</p></div>'}
      <section>
        <h2>Decididos há menos tempo</h2>
        ${UI.tableWrap('Pedidos decididos há menos tempo', `<table>
          <thead><tr><th scope="col">Titular</th><th scope="col">Quando</th><th scope="col">Sala</th><th scope="col">Estado</th><th scope="col">Decisão</th><th scope="col">Ações</th></tr></thead>
          <tbody>${recent.map((b) => `<tr><th scope="row">${esc(Store.userName(b.ownerId))}</th>
            <td>${esc(T.fmtRange(b.start, b.end))}</td><td>${esc(Store.roomName(b.roomId))}</td>
            <td>${UI.statusBadge(b.status)}</td><td>${esc(T.fmtDateTime(b.decidedAt))}</td>
            <td><button type="button" class="btn btn-small" data-act="open-booking" data-id="${esc(b.id)}">Histórico</button></td></tr>`).join('')}</tbody>
        </table>`)}
      </section>`;

    el.querySelectorAll('[data-approve]').forEach((button) => button.addEventListener('click', () => {
      const result = Store.approve(button.dataset.approve);
      App.render();
      if (result.ok) UI.bookingToast(result.booking, 'Pedido aprovado.');
      else UI.toast('Não foi possível aprovar.', { line: result.errors.join(' '), error: true });
    }));
    el.querySelectorAll('[data-other]').forEach((button) => button.addEventListener('click', () => openOtherRoom(Store.booking(button.dataset.other))));
    el.querySelectorAll('[data-refuse]').forEach((button) => button.addEventListener('click', () => openRefuse(Store.booking(button.dataset.refuse))));
    el.querySelectorAll('[data-show-day]').forEach((button) => button.addEventListener('click', () => {
      App.view.grid.date = button.dataset.showDay;
      App.go('grelha');
    }));
  };

  // ---- Direct booking ----

  Views.marcacao = (el) => Views.bookingForm(el, 'direct');

  // ---- Closures ----

  const closureHistory = (c) => (c.events.length ? `<ul style="margin:.25rem 0 0;padding-left:1.1rem">${[...c.events].reverse().map((ev) => `<li class="hint">${esc(T.fmtDateTime(ev.at))} · ${esc(Store.userName(ev.by))} · ${esc(ev.action)}</li>`).join('')}</ul>` : '');

  const closureRange = (c) => (c.source === 'holiday'
    ? esc(T.fmtDate(T.date(c.start)))
    : esc(T.fmtRange(c.start, c.end)));

  const confirmManualClosure = (draft) => {
    const affected = Store.closureAffected(draft.locationId, draft.roomId, draft.start, draft.end);
    UI.open({
      title: 'Confirmar bloqueio',
      subtitle: `${draft.roomId ? Store.roomName(draft.roomId) : 'Todas as salas'}, ${T.fmtRange(draft.start, draft.end)}`,
      html: `
        ${affected.length ? `<div class="alert alert-warn"><span class="alert-icon" aria-hidden="true">!</span>
          <div><p><strong>${affected.length} ${affected.length === 1 ? 'reserva afetada' : 'reservas afetadas'}.</strong> Os titulares são notificados (simulado). As reservas não são canceladas automaticamente.</p>
          <ul>${affected.map((b) => `<li>${esc(Store.userName(b.ownerId))}, ${esc(Store.roomName(b.roomId))}, ${T.time(b.start)}–${T.time(b.end)}</li>`).join('')}</ul></div></div>`
    : '<div class="alert alert-ok"><p>Não há reservas aprovadas neste intervalo.</p></div>'}
        <div class="actions"><button type="button" class="btn btn-primary" id="confirm-closure">Criar bloqueio</button></div>`,
      onReady: (root) => {
        root.querySelector('#confirm-closure').addEventListener('click', () => {
          const result = Store.addClosure(draft);
          UI.close();
          App.render();
          if (result.ok) UI.toast('Bloqueio criado.', { line: `${T.fmtDateTime(T.now())} · ${Store.currentUser().name}` });
          else UI.toast('Não foi possível criar o bloqueio.', { line: result.errors.join(' '), error: true });
        });
      },
    });
  };

  Views.bloqueios = (el) => {
    const locationId = loc();
    const rules = Store.settings(locationId);
    const closures = Store.closures.filter((c) => c.locationId === locationId && T.date(c.end) >= T.date(T.now()))
      .sort((a, b) => a.start.localeCompare(b.start));
    const holidays = closures.filter((c) => c.source === 'holiday');
    const manual = closures.filter((c) => c.source === 'manual');

    el.innerHTML = `
      <div class="page-head">
        <h1>Bloqueios</h1>
        <p class="lead">Os feriados bloqueiam o polo automaticamente. Podes anular o bloqueio de um dia concreto, e a anulação fica no histórico. Os pedidos e reservas nesses dias voltam logo a ser possíveis.</p>
      </div>
      <section class="card">
        <h2>Feriados</h2>
        ${UI.tableWrap('Feriados', `<table>
          <thead><tr><th scope="col">Dia</th><th scope="col">Feriado</th><th scope="col">Estado e histórico</th><th scope="col">Ações</th></tr></thead>
          <tbody>${holidays.map((c) => `<tr><th scope="row">${closureRange(c)}</th><td>${esc(c.reason)}</td>
            <td>${c.overriddenBy ? '<span class="badge badge-muted">Anulado neste dia</span>' : '<span class="badge badge-cancelled">A bloquear</span>'}${closureHistory(c)}</td>
            <td>${c.overriddenBy
    ? `<button type="button" class="btn btn-small" data-restore="${esc(c.id)}">Repor feriado</button>`
    : `<button type="button" class="btn btn-small" data-override="${esc(c.id)}">Anular neste dia</button>`}</td></tr>`).join('')}</tbody>
        </table>`)}
      </section>
      <section class="card">
        <h2>Bloqueios manuais</h2>
        ${manual.length ? UI.tableWrap('Bloqueios manuais', `<table>
          <thead><tr><th scope="col">Quando</th><th scope="col">Sala</th><th scope="col">Motivo e histórico</th><th scope="col">Ações</th></tr></thead>
          <tbody>${manual.map((c) => `<tr><th scope="row">${closureRange(c)}</th><td>${c.roomId ? esc(Store.roomName(c.roomId)) : 'Todas'}</td>
            <td>${esc(c.reason)}${closureHistory(c)}</td>
            <td><button type="button" class="btn btn-small btn-danger" data-remove="${esc(c.id)}">Remover</button></td></tr>`).join('')}</tbody>
        </table>`) : '<p>Sem bloqueios manuais.</p>'}
        <form id="closure-form" novalidate>
          <h3>Novo bloqueio manual</h3>
          <div id="closure-errors"></div>
          <div class="form-grid">
            <div class="field"><label for="k-room">Sala</label><select id="k-room"><option value="">Todas as salas</option>
              ${Store.roomsOf(locationId).map((r) => `<option value="${esc(r.id)}">${esc(r.name)}</option>`).join('')}</select></div>
            <div class="field"><label for="k-date">Dia</label><input type="date" id="k-date" value="${esc(T.addDays(T.date(T.now()), 1))}"></div>
            <div class="field"><label for="k-start">Início</label><input type="time" id="k-start" step="${rules.blockMin * 60}" value="14:00"></div>
            <div class="field"><label for="k-end">Fim</label><input type="time" id="k-end" step="${rules.blockMin * 60}" value="16:00"></div>
            <div class="field field-wide"><label for="k-reason">Motivo</label><input type="text" id="k-reason"></div>
          </div>
          <div class="form-actions"><button type="submit" class="btn btn-primary">Continuar</button></div>
        </form>
      </section>`;

    const after = (result, text) => {
      App.render();
      if (result.ok) UI.toast(text, { line: `${T.fmtDateTime(T.now())} · ${Store.currentUser().name}` });
      else UI.toast('Não foi possível concluir.', { line: result.errors.join(' '), error: true });
    };
    el.querySelectorAll('[data-override]').forEach((b) => b.addEventListener('click', () => after(Store.overrideClosure(b.dataset.override), 'Feriado anulado neste dia.')));
    el.querySelectorAll('[data-restore]').forEach((b) => b.addEventListener('click', () => after(Store.restoreClosure(b.dataset.restore), 'O feriado volta a bloquear este dia.')));
    el.querySelectorAll('[data-remove]').forEach((b) => b.addEventListener('click', () => after(Store.removeClosure(b.dataset.remove), 'Bloqueio removido.')));
    el.querySelector('#closure-form').addEventListener('submit', (e) => {
      e.preventDefault();
      const date = el.querySelector('#k-date').value;
      const startTime = el.querySelector('#k-start').value;
      const endTime = el.querySelector('#k-end').value;
      const reason = el.querySelector('#k-reason').value.trim();
      if (!date || !startTime || !endTime || startTime >= endTime) {
        UI.showErrors(el.querySelector('#closure-errors'), ['Indica um intervalo válido.']);
        return;
      }
      if (!reason) {
        UI.showErrors(el.querySelector('#closure-errors'), ['Indica o motivo do bloqueio.']);
        return;
      }
      confirmManualClosure({ locationId, roomId: el.querySelector('#k-room').value || null, start: T.combine(date, startTime), end: T.combine(date, endTime), reason });
    });
  };

  // ---- Members ----

  const roleFields = (locationId, prefix) => `
    <div class="field"><label for="${prefix}-role">Papel</label>
      <select id="${prefix}-role">${Store.assignableRoles(locationId).map((r) => `<option value="${r}">${esc(Store.ROLE_LABEL[r])}</option>`).join('')}</select>
      <span class="hint">Só podes atribuir papéis até ao teu próprio nível neste polo.</span></div>
    <div class="field" data-subrole><label for="${prefix}-subrole">Subpapel</label>
      <select id="${prefix}-subrole"><option value="resident">Residente</option><option value="intern">Estagiária</option></select></div>
    <div class="field"><label for="${prefix}-end">Data de fim</label>
      <input type="date" id="${prefix}-end"><span class="hint">Obrigatória para estagiárias.</span></div>`;

  const wireRoleFields = (root, prefix) => {
    const role = root.querySelector(`#${prefix}-role`);
    const subrole = root.querySelector('[data-subrole]');
    const sync = () => { subrole.hidden = role.value !== 'professional'; };
    role.addEventListener('change', sync);
    sync();
  };

  const memberResult = (root, result, text) => {
    if (!result.ok) {
      UI.showErrors(root.querySelector('#member-errors'), result.errors);
      return;
    }
    UI.close();
    App.render();
    UI.toast(text, { line: `${T.fmtDateTime(T.now())} · ${Store.currentUser().name} · registado na auditoria` });
  };

  const openInvite = (locationId) => {
    UI.open({
      title: 'Convidar pessoa',
      subtitle: 'A pessoa recebe um link de uso único, válido durante 48 h, para definir a palavra-passe (simulado).',
      html: `<form id="invite-form" novalidate>
        <div id="member-errors"></div>
        <div class="form-grid">
          <div class="field"><label for="i-name">Nome</label><input type="text" id="i-name" autocomplete="off"></div>
          <div class="field"><label for="i-email">E-mail</label><input type="email" id="i-email" autocomplete="off"></div>
          ${roleFields(locationId, 'i')}
        </div>
        <p class="hint">Se o e-mail já estiver registado, cria-se apenas a filiação neste polo.</p>
        <div class="actions"><button type="submit" class="btn btn-primary">Enviar convite</button></div>
      </form>`,
      onReady: (root) => {
        wireRoleFields(root, 'i');
        root.querySelector('#invite-form').addEventListener('submit', (e) => {
          e.preventDefault();
          const result = Store.inviteOrAdd(locationId, {
            name: root.querySelector('#i-name').value,
            email: root.querySelector('#i-email').value,
            role: root.querySelector('#i-role').value,
            subrole: root.querySelector('#i-subrole').value,
            end: root.querySelector('#i-end').value,
          });
          memberResult(root, result, result.existing ? 'E-mail já registado: criou-se apenas a filiação.' : 'Convite enviado (simulado).');
        });
      },
    });
  };

  const openAddExisting = (locationId) => {
    const example = Store.users.find((u) => !u.isSuperuser && u.status === 'active' && !Store.activeMemberships(u.id, locationId).length);
    UI.open({
      title: 'Adicionar conta existente',
      subtitle: 'Cria-se apenas a filiação neste polo. Não vês as reservas nem a atividade da pessoa noutros polos.',
      html: `<form id="existing-form" novalidate>
        <div id="member-errors"></div>
        <div class="form-grid">
          <div class="field field-wide"><label for="x-email">E-mail da conta</label><input type="email" id="x-email" autocomplete="off">
            ${example ? `<span class="hint">Para testar no protótipo: ${esc(example.email)}</span>` : ''}</div>
          ${roleFields(locationId, 'x')}
        </div>
        <div class="actions"><button type="submit" class="btn btn-primary">Adicionar ao polo</button></div>
      </form>`,
      onReady: (root) => {
        wireRoleFields(root, 'x');
        root.querySelector('#existing-form').addEventListener('submit', (e) => {
          e.preventDefault();
          const result = Store.inviteOrAdd(locationId, {
            email: root.querySelector('#x-email').value,
            role: root.querySelector('#x-role').value,
            subrole: root.querySelector('#x-subrole').value,
            end: root.querySelector('#x-end').value,
            mustExist: true,
          });
          memberResult(root, result, result.ok ? `Filiação criada para ${result.user.name}.` : '');
        });
      },
    });
  };

  const openManage = (target, locationId) => {
    const canManage = Store.canManageMember(target, locationId);
    const canAccount = Store.canActOnAccount(target);
    const accountNote = canAccount ? '' : `<p class="hint">Desativar a conta ou repor o 2FA exige um nível igual ou superior ao desta pessoa em todos os polos dela. Neste caso, só podes removê-la deste polo.</p>`;
    UI.open({
      title: target.name,
      subtitle: `${target.email} · ${Store.rolesText(target.id, locationId) || 'Sem filiação ativa'}`,
      html: `
        <div id="member-errors"></div>
        <h3>Neste polo</h3>
        <div class="actions" style="margin-bottom:1rem">
          <button type="button" class="btn" id="m-recovery">Enviar link de recuperação</button>
          <button type="button" class="btn btn-danger" id="m-remove"${canManage ? '' : ' disabled'}>Remover do polo</button>
        </div>
        ${canManage ? '' : '<p class="hint">Só podes remover pessoas até ao teu próprio nível neste polo.</p>'}
        <p class="hint">Ninguém define a palavra-passe de outra pessoa: só se envia um link de recuperação para o e-mail dela.</p>
        <h3>Conta inteira</h3>
        <div class="actions" style="margin-bottom:.5rem">
          ${target.status === 'inactive'
    ? `<button type="button" class="btn" id="m-reactivate"${canAccount ? '' : ' disabled'}>Reativar conta</button>`
    : `<button type="button" class="btn btn-danger" id="m-deactivate"${canAccount ? '' : ' disabled'}>Desativar conta</button>`}
          <button type="button" class="btn" id="m-2fa"${canAccount ? '' : ' disabled'}>Repor 2FA</button>
        </div>
        ${accountNote}`,
      onReady: (root) => {
        const on = (selector, handler) => {
          const node = root.querySelector(selector);
          if (node) node.addEventListener('click', handler);
        };
        on('#m-recovery', () => memberResult(root, Store.sendRecovery(target.id, locationId), 'Link de recuperação enviado (simulado).'));
        on('#m-remove', () => memberResult(root, Store.removeFromLocation(target.id, locationId), `Filiação de ${target.name} removida deste polo.`));
        on('#m-deactivate', () => memberResult(root, Store.deactivateAccount(target.id, locationId), 'Conta desativada.'));
        on('#m-reactivate', () => memberResult(root, Store.reactivateAccount(target.id, locationId), 'Conta reativada.'));
        on('#m-2fa', () => memberResult(root, Store.resetTwoFactor(target.id, locationId), '2FA reposto.'));
      },
    });
  };

  const openMentorship = (locationId) => {
    const members = Store.membersOf(locationId);
    const professionals = members.filter((u) => Store.activeMemberships(u.id, locationId).some((m) => m.role === 'professional'));
    const interns = members.filter((u) => Store.activeMemberships(u.id, locationId).some((m) => m.subrole === 'intern'));
    UI.open({
      title: 'Nova orientação',
      subtitle: `Em ${Store.location(locationId).name}. A orientadora passa a ver o horário e as horas da orientanda neste polo.`,
      html: `<form id="mentor-form" novalidate>
        <div id="member-errors"></div>
        <div class="form-grid">
          <div class="field"><label for="o-mentor">Orientadora</label><select id="o-mentor"><option value="">Escolher…</option>
            ${professionals.map((u) => `<option value="${esc(u.id)}">${esc(u.name)}</option>`).join('')}</select></div>
          <div class="field"><label for="o-mentee">Orientanda</label><select id="o-mentee"><option value="">Escolher…</option>
            ${interns.map((u) => `<option value="${esc(u.id)}">${esc(u.name)}</option>`).join('')}</select></div>
          <div class="field"><label for="o-end">Data de fim</label><input type="date" id="o-end" value="${esc(T.addDays(T.date(T.now()), 180))}"></div>
        </div>
        <div class="actions"><button type="submit" class="btn btn-primary">Criar orientação</button></div>
      </form>`,
      onReady: (root) => {
        root.querySelector('#mentor-form').addEventListener('submit', (e) => {
          e.preventDefault();
          memberResult(root, Store.addMentorship(locationId, root.querySelector('#o-mentor').value, root.querySelector('#o-mentee').value, root.querySelector('#o-end').value), 'Orientação criada.');
        });
      },
    });
  };

  const STATUS_TEXT = { active: 'Ativa', invited: 'Convite enviado', inactive: 'Desativada' };

  Views.membros = (el) => {
    const locationId = loc();
    const today = T.date(T.now());
    const members = Store.membersOf(locationId);
    const mentorships = Store.mentorships.filter((o) => o.locationId === locationId && o.start <= today && (!o.end || o.end >= today));
    const audit = Store.can('core.audit_view', locationId)
      ? Store.auditEvents.filter((a) => a.locationId === locationId).slice().sort((a, b) => b.at.localeCompare(a.at)).slice(0, 12)
      : null;

    el.innerHTML = `
      <div class="page-head">
        <h1>Membros do polo</h1>
        <p class="lead">Quem tem acesso a ${esc(Store.location(locationId).name)} e com que papel.</p>
      </div>
      <div class="actions" style="margin-bottom:1rem">
        <button type="button" class="btn btn-primary" id="invite">Convidar pessoa</button>
        <button type="button" class="btn" id="add-existing">Adicionar conta existente</button>
      </div>
      ${UI.tableWrap('Membros do polo', `<table>
        <thead><tr><th scope="col">Nome</th><th scope="col">E-mail</th><th scope="col">Papel neste polo</th><th scope="col">Fim</th><th scope="col">Estado</th><th scope="col">Ações</th></tr></thead>
        <tbody>${members.map((u) => {
    const memberships = Store.activeMemberships(u.id, locationId);
    const end = memberships.map((m) => m.end).filter(Boolean).sort()[0];
    return `<tr><th scope="row">${esc(u.name)}</th><td>${esc(u.email)}</td>
      <td>${esc(Store.rolesText(u.id, locationId))}</td><td>${end ? esc(T.fmtDate(end)) : '—'}</td>
      <td>${esc(STATUS_TEXT[u.status])}</td>
      <td><button type="button" class="btn btn-small" data-manage="${esc(u.id)}">Gerir</button></td></tr>`;
  }).join('')}</tbody>
      </table>`)}
      <section class="card">
        <h2>Orientações</h2>
        ${UI.tableWrap('Orientações', `<table>
          <thead><tr><th scope="col">Orientadora</th><th scope="col">Orientanda</th><th scope="col">Fim</th><th scope="col">Ações</th></tr></thead>
          <tbody>${mentorships.map((o) => `<tr><th scope="row">${esc(Store.userName(o.mentorId))}</th><td>${esc(Store.userName(o.menteeId))}</td>
            <td>${o.end ? esc(T.fmtDate(o.end)) : '—'}</td>
            <td><button type="button" class="btn btn-small" data-end-mentorship="${esc(o.id)}">Terminar</button></td></tr>`).join('')}</tbody>
        </table>`)}
        <button type="button" class="btn" id="add-mentorship">Nova orientação</button>
      </section>
      ${audit ? `<section class="card">
        <h2>Auditoria de contas</h2>
        <p class="hint">Só de acrescentar: não se edita nem se apaga.</p>
        ${UI.tableWrap('Auditoria de contas', `<table>
          <thead><tr><th scope="col">Data e hora</th><th scope="col">Utilizador</th><th scope="col">Ação</th><th scope="col">Pessoa</th><th scope="col">Detalhe</th></tr></thead>
          <tbody>${audit.map((a) => `<tr><th scope="row">${esc(T.fmtDateTime(a.at))}</th><td>${esc(Store.userName(a.by))}</td><td>${esc(a.action)}</td><td>${esc(Store.userName(a.target))}</td><td>${esc(a.detail)}</td></tr>`).join('')}</tbody>
        </table>`)}
      </section>` : ''}`;

    el.querySelector('#invite').addEventListener('click', () => openInvite(locationId));
    el.querySelector('#add-existing').addEventListener('click', () => openAddExisting(locationId));
    el.querySelector('#add-mentorship').addEventListener('click', () => openMentorship(locationId));
    el.querySelectorAll('[data-manage]').forEach((b) => b.addEventListener('click', () => openManage(Store.user(b.dataset.manage), locationId)));
    el.querySelectorAll('[data-end-mentorship]').forEach((b) => b.addEventListener('click', () => {
      const result = Store.endMentorship(b.dataset.endMentorship);
      App.render();
      if (result.ok) UI.toast('Orientação terminada.', { line: `${T.fmtDateTime(T.now())} · ${Store.currentUser().name} · registado na auditoria` });
    }));
  };

  // ---- Location rules ----

  const ESTIMATE = '<span class="badge badge-muted">estimativa</span>';
  const WEEKDAYS = [[1, 'Seg'], [2, 'Ter'], [3, 'Qua'], [4, 'Qui'], [5, 'Sex'], [6, 'Sáb'], [7, 'Dom']];

  Views.regras = (el) => {
    const locationId = loc();
    const rules = Store.settings(locationId);
    const isAdmin = Store.currentUser().isSuperuser;
    const number = (id, label, value, unit, estimate) => `
      <div class="field"><label for="${id}">${esc(label)} ${estimate ? ESTIMATE : ''}</label>
        <input type="number" id="${id}" min="0" value="${value}" aria-describedby="${id}-u"><span class="hint" id="${id}-u">${esc(unit)}</span></div>`;

    el.innerHTML = `
      <div class="page-head">
        <h1>Regras do polo</h1>
        <p class="lead">Valores de ${esc(Store.location(locationId).name)}. Aplicam-se logo: experimenta mudar os blocos e vê a grelha, ou a antecedência e faz um pedido.</p>
      </div>
      <form id="rules-form" class="card" novalidate>
        <div id="rules-errors"></div>
        <fieldset>
          <legend>Horário de funcionamento ${ESTIMATE}</legend>
          <div class="check-row" style="margin-bottom:.75rem">
            ${WEEKDAYS.map(([value, label]) => `<label class="check"><input type="checkbox" name="day" value="${value}"${rules.days.includes(value) ? ' checked' : ''}> ${label}</label>`).join('')}
          </div>
          <div class="form-grid">
            <div class="field"><label for="r-open">Abre às</label><input type="time" id="r-open" value="${esc(rules.open)}"></div>
            <div class="field"><label for="r-close">Fecha às</label><input type="time" id="r-close" value="${esc(rules.close)}"></div>
            <div class="field"><label for="r-block">Blocos de tempo ${ESTIMATE}</label>
              <select id="r-block">${[15, 30, 60].map((m) => `<option value="${m}"${rules.blockMin === m ? ' selected' : ''}>${m} min</option>`).join('')}</select></div>
          </div>
        </fieldset>
        <fieldset>
          <legend>Pedidos</legend>
          <div class="form-grid">
            ${number('r-min', 'Duração mínima', rules.minDurationMin, 'minutos', true)}
            ${number('r-max', 'Duração máxima', rules.maxDurationMin, 'minutos', true)}
            ${number('r-adv', 'Antecedência mínima', rules.minAdvanceHours, 'horas', true)}
            ${number('r-adv-max', 'Antecedência máxima', rules.maxAdvanceWeeks, 'semanas', true)}
          </div>
        </fieldset>
        <fieldset>
          <legend>Cancelamento tardio</legend>
          <div class="form-grid">
            ${number('r-late', 'Tardio a menos de', rules.lateCancelHours, 'horas antes do início')}
            ${number('r-exc', 'Exceção: alteração pelo staff a menos de', rules.exceptionHours, 'horas de antecedência')}
          </div>
        </fieldset>
        <fieldset>
          <legend>Salas exclusivas</legend>
          <label class="check"><input type="checkbox" id="r-release"${rules.releaseEnabled ? ' checked' : ''}${isAdmin ? '' : ' disabled'}> Libertação de períodos</label>
          <p class="hint">${isAdmin ? 'Prevista no modelo de dados. Só o admin a pode ligar, por polo.' : 'Desligada. Só o admin a pode ligar.'}</p>
        </fieldset>
        <details style="margin-bottom:1rem">
          <summary>Regras fixas deste protótipo</summary>
          <ul>
            <li>Um pedido sem decisão expira à hora de início.</li>
            <li>Editar um pedido pendente: mudar a hora ou a sala faz perder o lugar na fila; participantes e notas não.</li>
            <li>Editar uma reserva aprovada: mudar a hora ou a sala cria um pedido de alteração; a reserva atual mantém-se até haver decisão.</li>
            <li>Pedidos recorrentes: até ao fim do ano letivo.</li>
          </ul>
        </details>
        <div class="form-actions"><button type="submit" class="btn btn-primary">Guardar regras</button></div>
      </form>`;

    el.querySelector('#rules-form').addEventListener('submit', (e) => {
      e.preventDefault();
      const value = (id) => Number(el.querySelector(id).value);
      const result = Store.saveSettings(locationId, {
        days: [...el.querySelectorAll('input[name="day"]:checked')].map((c) => Number(c.value)),
        open: el.querySelector('#r-open').value,
        close: el.querySelector('#r-close').value,
        blockMin: value('#r-block'),
        minDurationMin: value('#r-min'),
        maxDurationMin: value('#r-max'),
        minAdvanceHours: value('#r-adv'),
        maxAdvanceWeeks: value('#r-adv-max'),
        lateCancelHours: value('#r-late'),
        exceptionHours: value('#r-exc'),
        releaseEnabled: el.querySelector('#r-release').checked,
      });
      if (!result.ok) {
        UI.showErrors(el.querySelector('#rules-errors'), result.errors);
        return;
      }
      App.render();
      UI.toast('Regras guardadas.', { line: `${T.fmtDateTime(T.now())} · ${Store.currentUser().name}` });
    });
  };
})();
