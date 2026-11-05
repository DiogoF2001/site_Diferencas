// Coordination screens (reports, professionals) and the admin technical area.
(() => {
  const loc = () => Store.session.locationId;

  // ---- Reports ----

  let reportPeriod = '4w';
  const PERIODS = {
    '1w': { label: 'Última semana', days: 7 },
    '4w': { label: 'Últimas 4 semanas', days: 28 },
  };

  const percent = (value) => `${Math.round(value * 100)} %`;

  Views.relatorios = (el) => {
    const locationId = loc();
    const from = T.addDays(T.date(T.now()), -PERIODS[reportPeriod].days);
    const data = Store.report(locationId, from);
    const maxHours = Math.max(1, ...data.hours.map((row) => row.minutes));

    el.innerHTML = `
      <div class="page-head">
        <h1>Relatórios</h1>
        <p class="lead">${esc(Store.location(locationId).name)}, desde ${esc(T.fmtDate(from))}. Só contam os dias completos de funcionamento.</p>
      </div>
      <div class="toolbar">
        <div class="field"><label for="report-period">Período</label>
          <select id="report-period">${Object.entries(PERIODS).map(([id, p]) => `<option value="${id}"${id === reportPeriod ? ' selected' : ''}>${esc(p.label)}</option>`).join('')}</select></div>
      </div>
      <div class="kpis">
        <div class="kpi"><b>${percent(data.averageOccupancy)}</b><span>Ocupação média</span></div>
        <div class="kpi"><b>${esc(T.fmtMinutes(data.totalHoursMinutes))}</b><span>Horas de profissionais</span></div>
        <div class="kpi"><b>${esc(T.fmtMinutes(Math.round(data.averageDecisionMinutes)))}</b><span>Tempo médio até à decisão</span></div>
        <div class="kpi"><b>${data.refused.length}</b><span>Recusas</span></div>
        <div class="kpi"><b>${data.late.length}</b><span>Cancelamentos tardios</span></div>
      </div>

      <section class="card">
        <div class="toolbar"><h2 style="margin:0">Ocupação por sala</h2><span class="spacer"></span><button type="button" class="btn btn-small" id="csv-occupancy">Exportar CSV</button></div>
        <p class="hint">Horas aprovadas e horário de salas exclusivas, face ao horário de funcionamento.</p>
        ${UI.tableWrap('Ocupação por sala', `<table>
          <thead><tr><th scope="col">Sala</th><th scope="col" class="num">Ocupação</th><th scope="col">Proporção</th><th scope="col" class="num">Horas</th></tr></thead>
          <tbody>${data.occupancy.map((row) => `<tr title="${esc(row.room.name)}: ${percent(row.rate)}"><th scope="row">${esc(row.room.name)}</th>
            <td class="num">${percent(row.rate)}</td>
            <td class="bar-cell"><span class="bar" aria-hidden="true"><span style="width:${Math.round(row.rate * 100)}%"></span></span></td>
            <td class="num">${esc(T.fmtMinutes(row.minutes))}</td></tr>`).join('')}</tbody>
        </table>`)}
      </section>

      <section class="card">
        <div class="toolbar"><h2 style="margin:0">Horas por profissional e estagiária</h2><span class="spacer"></span><button type="button" class="btn btn-small" id="csv-hours">Exportar CSV</button></div>
        ${UI.tableWrap('Horas por profissional', `<table>
          <thead><tr><th scope="col">Pessoa</th><th scope="col">Subpapel</th><th scope="col" class="num">Horas</th><th scope="col">Proporção</th></tr></thead>
          <tbody>${data.hours.map((row) => `<tr title="${esc(row.user.name)}: ${esc(T.fmtMinutes(row.minutes))}"><th scope="row">${esc(row.user.name)}</th>
            <td>${esc(row.subrole || '—')}</td><td class="num">${esc(T.fmtMinutes(row.minutes))}</td>
            <td class="bar-cell"><span class="bar" aria-hidden="true"><span style="width:${Math.round((row.minutes / maxHours) * 100)}%"></span></span></td></tr>`).join('')}</tbody>
        </table>`)}
      </section>

      <section class="card">
        <div class="toolbar"><h2 style="margin:0">Cancelamentos tardios</h2><span class="spacer"></span><button type="button" class="btn btn-small" id="csv-late">Exportar CSV</button></div>
        ${data.late.length ? UI.tableWrap('Cancelamentos tardios', `<table>
          <thead><tr><th scope="col">Pessoa</th><th scope="col">Reserva</th><th scope="col">Sala</th><th scope="col">Cancelada em</th><th scope="col">Ações</th></tr></thead>
          <tbody>${data.late.map((b) => `<tr><th scope="row">${esc(Store.userName(b.ownerId))}</th><td>${esc(T.fmtRange(b.start, b.end))}</td>
            <td>${esc(Store.roomName(b.roomId))}</td><td>${esc(T.fmtDateTime(b.cancelledAt))}</td>
            <td><button type="button" class="btn btn-small" data-act="open-booking" data-id="${esc(b.id)}">Histórico</button></td></tr>`).join('')}</tbody>
        </table>`) : '<p>Sem cancelamentos tardios neste período.</p>'}
      </section>`;

    el.querySelector('#report-period').addEventListener('change', (e) => {
      reportPeriod = e.target.value;
      App.render();
    });
    el.querySelector('#csv-occupancy').addEventListener('click', () => UI.downloadCsv('ocupacao-por-sala.csv', [
      ['Sala', 'Ocupação (%)', 'Minutos'],
      ...data.occupancy.map((row) => [row.room.name, Math.round(row.rate * 100), row.minutes]),
    ]));
    el.querySelector('#csv-hours').addEventListener('click', () => UI.downloadCsv('horas-por-profissional.csv', [
      ['Pessoa', 'Subpapel', 'Minutos'],
      ...data.hours.map((row) => [row.user.name, row.subrole || '', row.minutes]),
    ]));
    el.querySelector('#csv-late').addEventListener('click', () => UI.downloadCsv('cancelamentos-tardios.csv', [
      ['Pessoa', 'Início', 'Fim', 'Sala', 'Cancelada em'],
      ...data.late.map((b) => [Store.userName(b.ownerId), b.start.replace('T', ' '), b.end.replace('T', ' '), Store.roomName(b.roomId), b.cancelledAt.replace('T', ' ')]),
    ]));
  };

  // ---- Professionals ----

  let showOtherRoles = true;

  Views.profissionais = (el) => {
    const locationId = loc();
    const rows = Store.membersOf(locationId)
      .filter((u) => Store.activeMemberships(u.id, locationId).length)
      .map((u) => ({
        user: u,
        roles: Store.rolesText(u.id, locationId),
        others: Store.otherLocationRoles(u.id, locationId),
      }));

    el.innerHTML = `
      <div class="page-head">
        <h1>Profissionais</h1>
        <p class="lead">Pessoas de ${esc(Store.location(locationId).name)}, com os papéis neste polo. Os papéis noutros polos são opcionais e nunca mostram a atividade lá.</p>
      </div>
      <div class="toolbar">
        <label class="check"><input type="checkbox" id="other-roles"${showOtherRoles ? ' checked' : ''}> Mostrar papéis noutros polos</label>
        <span class="spacer"></span>
        <button type="button" class="btn" id="people-csv">Exportar CSV</button>
      </div>
      ${UI.tableWrap('Profissionais', `<table>
        <thead><tr><th scope="col">Nome</th><th scope="col">E-mail</th><th scope="col">Papéis neste polo</th>${showOtherRoles ? '<th scope="col">Noutros polos</th>' : ''}</tr></thead>
        <tbody>${rows.map((r) => `<tr><th scope="row">${esc(r.user.name)}</th><td>${esc(r.user.email)}</td><td>${esc(r.roles)}</td>
          ${showOtherRoles ? `<td>${r.others.length ? r.others.map((o) => `<span class="badge badge-loc">${esc(o.location)}</span> ${esc(o.role)}`).join('<br>') : '—'}</td>` : ''}</tr>`).join('')}</tbody>
      </table>`)}`;

    el.querySelector('#other-roles').addEventListener('change', (e) => {
      showOtherRoles = e.target.checked;
      App.render();
      document.getElementById('other-roles').focus();
    });
    el.querySelector('#people-csv').addEventListener('click', () => UI.downloadCsv('profissionais.csv', [
      ['Nome', 'E-mail', 'Papéis neste polo', ...(showOtherRoles ? ['Noutros polos'] : [])],
      ...rows.map((r) => [r.user.name, r.user.email, r.roles, ...(showOtherRoles ? [r.others.map((o) => `${o.location}: ${o.role}`).join(' | ')] : [])]),
    ]));
  };

  // ---- Technical area (sample content) ----

  const flags = { ical: false, mail: true };

  Views.tecnica = (el) => {
    const now = T.now();
    const services = [
      ['proxy', 'Caddy', 'Em funcionamento'],
      ['app', 'Gunicorn', 'Em funcionamento'],
      ['worker', 'Tarefas agendadas', 'Em funcionamento'],
      ['db', 'PostgreSQL', 'Em funcionamento'],
      ['backup', `Última cópia: ${T.fmtDateTime(T.combine(T.date(now), '03:00'))}`, 'Concluída'],
    ];
    const logs = [
      [T.addMin(now, -12), 'INFO', 'worker', 'Pedidos expirados: 0'],
      [T.addMin(now, -60), 'INFO', 'worker', 'Ocorrências de séries geradas'],
      [T.addMin(now, -190), 'AVISO', 'app', 'Pedido lento: /salas/grelha (1,2 s)'],
      [T.addMin(now, -1500), 'ERRO', 'app', 'SMTP: tempo limite excedido; nova tentativa com sucesso'],
    ];
    const accounts = Store.users.filter((u) => !u.isSuperuser);

    el.innerHTML = `
      <div class="page-head">
        <h1>Área técnica</h1>
        <p class="lead">Só para o admin. Conteúdo de exemplo: neste protótipo, nada aqui liga a um servidor real.</p>
      </div>
      <div class="cards">
        <section class="card">
          <h2>Estado do sistema</h2>
          ${UI.tableWrap('Estado dos serviços', `<table>
            <thead><tr><th scope="col">Serviço</th><th scope="col">Detalhe</th><th scope="col">Estado</th></tr></thead>
            <tbody>${services.map(([name, detail, status]) => `<tr><th scope="row">${esc(name)}</th><td>${esc(detail)}</td><td class="status-ok">✓ ${esc(status)}</td></tr>`).join('')}</tbody>
          </table>`)}
        </section>
        <section class="card">
          <h2>SMTP e segredos</h2>
          <dl class="def">
            <dt>Servidor</dt><dd>smtp.exemplo.pt:587</dd>
            <dt>Remetente</dt><dd>portal@exemplo.pt</dd>
            <dt>Palavra-passe</dt><dd>•••••••• <span class="hint">(só em variáveis de ambiente)</span></dd>
            <dt>SECRET_KEY</dt><dd>•••••••• <span class="hint">(só em variáveis de ambiente)</span></dd>
          </dl>
          <button type="button" class="btn" id="test-mail">Enviar e-mail de teste</button>
        </section>
      </div>
      <div class="cards">
        <section class="card">
          <h2>Polos</h2>
          <ul style="padding-left:1.1rem">${Store.locations.map((l) => `<li><strong>${esc(l.name)}</strong> · ${esc(l.address)} · ${Store.roomsOf(l.id).length} salas</li>`).join('')}</ul>
          <button type="button" class="btn" id="new-location">Criar polo</button>
        </section>
        <section class="card">
          <h2>Funcionalidades</h2>
          <label class="check"><input type="checkbox" id="flag-ical"${flags.ical ? ' checked' : ''}> Feed iCal</label>
          <label class="check"><input type="checkbox" id="flag-mail"${flags.mail ? ' checked' : ''}> Notificações por e-mail</label>
          <p class="hint">A libertação de salas exclusivas liga-se por polo, em "Regras do polo".</p>
        </section>
        <section class="card">
          <h2>Ver como utilizador</h2>
          <p class="hint">Só de leitura, e fica registado na auditoria.</p>
          <div class="field" style="margin-bottom:.75rem"><label for="view-as">Pessoa</label>
            <select id="view-as">${accounts.map((u) => `<option value="${esc(u.id)}">${esc(u.name)}</option>`).join('')}</select></div>
          <button type="button" class="btn" id="view-as-go">Iniciar</button>
        </section>
      </div>
      <section class="card">
        <h2>Logs técnicos</h2>
        ${UI.tableWrap('Logs técnicos', `<table>
          <thead><tr><th scope="col">Data e hora</th><th scope="col">Nível</th><th scope="col">Serviço</th><th scope="col">Mensagem</th></tr></thead>
          <tbody>${logs.map(([at, level, service, message]) => `<tr><th scope="row">${esc(T.fmtDateTime(at))}</th><td>${esc(level)}</td><td>${esc(service)}</td><td>${esc(message)}</td></tr>`).join('')}</tbody>
        </table>`)}
      </section>`;

    const sample = (selector, text) => el.querySelector(selector).addEventListener('click', () => UI.toast(text, { line: 'Exemplo: no protótipo não acontece nada.' }));
    sample('#test-mail', 'E-mail de teste enviado.');
    sample('#new-location', 'A criação de polos fica para o portal real.');
    sample('#view-as-go', 'Modo "ver como utilizador" iniciado.');
    el.querySelector('#flag-ical').addEventListener('change', (e) => { flags.ical = e.target.checked; });
    el.querySelector('#flag-mail').addEventListener('change', (e) => { flags.mail = e.target.checked; });
  };
})();
