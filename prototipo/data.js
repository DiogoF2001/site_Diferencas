// Fictitious data for the prototype. All names and e-mails are invented.
// Dates are relative to the current week, so the demo never goes stale.
// `DIF_SEED(now)` returns a fresh object every time ("Repor dados" calls it again).
window.DIF_SEED = function (now) {
  const T = window.T;
  const today = T.date(now);
  const monday = T.monday(today);
  const at = (week, weekday, time) => T.combine(T.addDays(monday, week * 7 + weekday - 1), time);
  const holidayDate = T.addDays(monday, 7 + 2); // Wednesday of next week

  // The n-th working day after today, skipping the holiday.
  const nextWorkday = (n) => {
    let date = today;
    let left = n;
    while (left > 0) {
      date = T.addDays(date, 1);
      if (T.weekday(date) <= 5 && date !== holidayDate) left -= 1;
    }
    return date;
  };

  const locations = [
    { id: 'central', name: 'Polo Central', address: 'Rua das Acácias, 12 (fictícia)', active: true },
    { id: 'ribeira', name: 'Polo Ribeira', address: 'Largo do Cais, 3 (fictício)', active: true },
  ];

  const rooms = [];
  for (let i = 1; i <= 20; i += 1) {
    rooms.push({ id: `c${i}`, locationId: 'central', name: `Sala ${i}`, active: true });
  }
  for (let i = 1; i <= 6; i += 1) {
    rooms.push({ id: `r${i}`, locationId: 'ribeira', name: `Sala R${i}`, active: true });
  }

  const user = (id, name, extra) => ({
    id,
    name,
    email: `${T.slug(name)}@exemplo.pt`,
    status: 'active',
    twoFactor: true,
    ...extra,
  });
  const users = [
    user('marta', 'Marta Quintela'),
    user('rui', 'Rui Sardinha'),
    user('sofia', 'Sofia Brandão'),
    user('helena', 'Helena Vaz'),
    user('tomas', 'Tomás Reis'),
    user('joana', 'Joana Falcão'),
    user('andre', 'André Lobo'),
    user('carla', 'Carla Meireles'),
    user('nuno', 'Nuno Tavares'),
    user('beatriz', 'Beatriz Salgado'),
    user('pedro', 'Pedro Alvim'),
    user('filipa', 'Filipa Antunes', { twoFactor: false }),
    user('leonor', 'Leonor Pinho', { twoFactor: false }),
    user('tiago', 'Tiago Serrano', { twoFactor: false }),
    user('mariana', 'Mariana Cunha', { twoFactor: false }),
    user('daniel', 'Daniel Fontes', { twoFactor: false }),
    user('clara', 'Clara Moura', { twoFactor: false }),
    { id: 'admin', name: 'Administração técnica', email: 'admin@exemplo.pt', status: 'active', twoFactor: true, isSuperuser: true },
  ];

  const memberStart = T.addDays(today, -400);
  const internEnd = T.addDays(today, 200);
  let membershipSeq = 1;
  const membership = (userId, locationId, role, subrole, end) => ({
    id: `m${membershipSeq++}`,
    userId,
    locationId,
    role,
    subrole: subrole || null,
    start: memberStart,
    end: end || null,
    removedAt: null,
  });
  const memberships = [
    membership('marta', 'central', 'professional', 'resident'),
    membership('marta', 'ribeira', 'professional', 'resident'),
    // Rui has different roles in different locations.
    membership('rui', 'central', 'professional', 'resident'),
    membership('rui', 'ribeira', 'secretariat'),
    membership('sofia', 'central', 'secretariat'),
    membership('helena', 'central', 'coordination'),
    // Tomás has two roles in the same location: permissions add up.
    membership('tomas', 'ribeira', 'coordination'),
    membership('tomas', 'ribeira', 'professional', 'resident'),
    membership('joana', 'central', 'professional', 'resident'),
    membership('andre', 'central', 'professional', 'resident'),
    membership('carla', 'central', 'professional', 'resident'),
    membership('nuno', 'central', 'professional', 'resident'),
    membership('nuno', 'ribeira', 'professional', 'resident'),
    membership('beatriz', 'ribeira', 'professional', 'resident'),
    membership('pedro', 'central', 'professional', 'resident'),
    membership('filipa', 'central', 'professional', 'resident'),
    membership('leonor', 'central', 'professional', 'intern', internEnd),
    membership('tiago', 'central', 'professional', 'intern', internEnd),
    membership('mariana', 'central', 'professional', 'intern', internEnd),
    membership('daniel', 'ribeira', 'professional', 'intern', internEnd),
    membership('clara', 'central', 'professional', 'intern', T.addDays(today, 30)),
  ];

  const mentorships = [
    { id: 'o1', mentorId: 'marta', menteeId: 'leonor', locationId: 'central', start: memberStart, end: internEnd },
    { id: 'o2', mentorId: 'marta', menteeId: 'tiago', locationId: 'central', start: memberStart, end: internEnd },
    { id: 'o3', mentorId: 'joana', menteeId: 'mariana', locationId: 'central', start: memberStart, end: internEnd },
    { id: 'o4', mentorId: 'filipa', menteeId: 'clara', locationId: 'central', start: memberStart, end: T.addDays(today, 30) },
    { id: 'o5', mentorId: 'beatriz', menteeId: 'daniel', locationId: 'ribeira', start: memberStart, end: internEnd },
  ];

  const roomAssignments = [
    // Exclusive all the time.
    { id: 'a1', roomId: 'c3', userId: 'pedro', weekdays: [1, 2, 3, 4, 5], start: '08:00', end: '20:00', from: memberStart, to: null },
    // Exclusive some days, shared the others.
    { id: 'a2', roomId: 'c7', userId: 'carla', weekdays: [1, 2, 3], start: '08:00', end: '20:00', from: memberStart, to: null },
    { id: 'a3', roomId: 'r2', userId: 'beatriz', weekdays: [1, 4], start: '09:00', end: '18:00', from: memberStart, to: null },
  ];

  const closures = [
    { id: 'h1', locationId: 'central', roomId: null, start: T.combine(holidayDate, '00:00'), end: T.combine(holidayDate, '23:59'), source: 'holiday', reason: 'Feriado municipal (fictício)', overriddenBy: null, overriddenAt: null, events: [] },
    { id: 'h2', locationId: 'ribeira', roomId: null, start: T.combine(holidayDate, '00:00'), end: T.combine(holidayDate, '23:59'), source: 'holiday', reason: 'Feriado municipal (fictício)', overriddenBy: null, overriddenAt: null, events: [] },
    { id: 'k1', locationId: 'central', roomId: 'c20', start: at(1, 4, '09:00'), end: at(1, 4, '13:00'), source: 'manual', reason: 'Manutenção do ar condicionado', overriddenBy: null, overriddenAt: null, events: [
      { at: T.addMin(now, -3 * 1440), by: 'sofia', action: 'Bloqueio manual criado', detail: 'Sala 20' },
    ] },
  ];

  const defaultSettings = () => ({
    days: [1, 2, 3, 4, 5],
    open: '08:00',
    close: '20:00',
    blockMin: 15,
    minDurationMin: 30,
    maxDurationMin: 240,
    minAdvanceHours: 24,
    maxAdvanceWeeks: 8,
    lateCancelHours: 24,
    exceptionHours: 48,
    releaseEnabled: false,
  });
  const locationSettings = { central: defaultSettings(), ribeira: defaultSettings() };

  const secretaryOf = { central: 'sofia', ribeira: 'rui' };
  const locationOfRoom = (roomId) => (roomId[0] === 'c' ? 'central' : 'ribeira');
  const bookings = [];
  let bookingSeq = 1;

  const makeBooking = (o) => {
    const id = `b${bookingSeq++}`;
    const locationId = locationOfRoom(o.room);
    const participations = (o.parts || []).map((p) => ({
      userId: p[0],
      start: p[1] ? T.combine(T.date(o.start), p[1]) : o.start,
      end: p[2] ? T.combine(T.date(o.start), p[2]) : o.end,
    }));
    const booking = {
      id,
      locationId,
      roomId: o.room,
      ownerId: o.owner,
      start: o.start,
      end: o.end,
      status: o.status || 'approved',
      notes: o.notes || '',
      createdBy: o.owner,
      createdAt: o.createdAt,
      decidedAt: o.decidedAt || null,
      refusalReason: o.refusalReason || null,
      cancelledAt: null,
      cancelledBy: null,
      lateCancel: false,
      lateExempt: false,
      staffChangeWithinException: false,
      participations,
      events: [{ at: o.createdAt, by: o.owner, action: 'Pedido criado', detail: T.fmtRange(o.start, o.end) }],
    };
    participations.forEach((p) => {
      booking.events.push({ at: o.createdAt, by: o.owner, action: 'Participante adicionado', detail: `${users.find((u) => u.id === p.userId).name}, ${T.time(p.start)}–${T.time(p.end)}` });
    });
    bookings.push(booking);
    return booking;
  };

  const decide = (booking, decidedAt, by) => {
    booking.decidedAt = decidedAt;
    booking.events.push({ at: decidedAt, by, action: 'Pedido aprovado', detail: 'Nesta sala' });
  };

  // Weekly pattern: [room, owner, weekday, start, end, participants, notes].
  // Rooms c13–c20 stay out of it, for the scripted scenarios further down.
  const pattern = [
    ['c1', 'marta', 1, '09:00', '12:00', [['leonor', '09:00', '10:00'], ['tiago', '10:00', '12:00']], 'Mesa baixa e duas cadeiras pequenas'],
    ['c1', 'marta', 3, '14:00', '17:00', [['leonor']]],
    ['c2', 'joana', 1, '10:00', '13:00', [['mariana']]],
    ['c2', 'andre', 2, '09:00', '12:30'],
    ['c2', 'marta', 4, '09:00', '11:00', [['tiago']], 'Precisa de projetor portátil'],
    ['c4', 'filipa', 1, '14:00', '18:00', [['clara', '14:00', '16:00']]],
    ['c4', 'nuno', 3, '09:00', '12:00'],
    ['c5', 'marta', 2, '15:00', '18:00', [['tiago', '15:00', '16:30']]],
    ['c5', 'clara', 4, '10:00', '11:30'],
    ['c6', 'tiago', 5, '09:00', '10:30'],
    ['c6', 'marta', 5, '11:00', '13:00', [['leonor']]],
    ['c8', 'rui', 2, '10:00', '13:00'],
    ['c8', 'rui', 4, '14:00', '17:00'],
    ['c9', 'leonor', 3, '10:00', '11:00'],
    ['c9', 'joana', 4, '14:00', '18:00', [['mariana', '14:00', '16:00']]],
    ['c10', 'andre', 5, '14:00', '17:00'],
    ['c10', 'filipa', 3, '15:00', '18:30'],
    ['c11', 'mariana', 2, '16:00', '17:00'],
    ['c11', 'nuno', 1, '15:00', '17:30'],
    ['c12', 'andre', 4, '09:00', '12:00'],
    ['c12', 'joana', 2, '09:00', '10:00', [['marta']]],
    ['r1', 'marta', 5, '14:00', '17:00'],
    ['r1', 'beatriz', 2, '09:00', '12:00', [['daniel']]],
    ['r3', 'tomas', 3, '10:00', '13:00'],
    ['r4', 'nuno', 2, '14:00', '17:00'],
    ['r5', 'daniel', 4, '09:00', '10:30', [['beatriz']]],
  ];

  for (let week = -4; week <= 1; week += 1) {
    pattern.forEach((row, i) => {
      const [room, owner, weekday, startTime, endTime, parts, notes] = row;
      if (week === 1 && weekday === 3) return; // holiday
      if ((i + week * 3 + 40) % 9 === 0 && owner !== 'marta') return; // some variation between weeks
      const start = at(week, weekday, startTime);
      let createdAt = T.addMin(T.combine(T.date(start), `09:${String(10 + (i % 40)).padStart(2, '0')}`), -1440 * (3 + (i % 6)));
      if (createdAt > T.addMin(now, -1500)) createdAt = T.addMin(now, -1500 - i * 37);
      let decidedAt = T.addMin(createdAt, 60 * (1 + ((i * 7 + (week + 4) * 3) % 30)));
      if (decidedAt > T.addMin(now, -30)) decidedAt = T.addMin(now, -30);
      const booking = makeBooking({ room, owner, start, end: at(week, weekday, endTime), parts, notes, createdAt });
      decide(booking, decidedAt, secretaryOf[booking.locationId]);
    });
  }

  // Past refusals, late cancellations and an expired request: these feed the reports.
  const pastRequest = (room, owner, week, weekday, startTime, endTime, daysBefore) => {
    const start = at(week, weekday, startTime);
    return makeBooking({ room, owner, start, end: at(week, weekday, endTime), createdAt: T.addMin(start, -1440 * daysBefore) });
  };
  const refuse = (booking, reason, hoursLater) => {
    const when = T.addMin(booking.createdAt, 60 * hoursLater);
    booking.status = 'refused';
    booking.refusalReason = reason;
    booking.decidedAt = when;
    booking.events.push({ at: when, by: 'sofia', action: 'Pedido recusado', detail: reason });
  };
  const cancel = (booking, hoursBefore, late) => {
    const when = T.addMin(booking.start, -60 * hoursBefore);
    booking.status = 'cancelled';
    booking.cancelledAt = when;
    booking.cancelledBy = booking.ownerId;
    booking.lateCancel = late;
    booking.events.push({ at: when, by: booking.ownerId, action: late ? 'Cancelada (tardio)' : 'Cancelada', detail: `${hoursBefore} h antes do início` });
  };

  refuse(pastRequest('c18', 'clara', -1, 2, '10:00', '11:00', 4), 'Sala necessária para uma reunião de equipa.', 5);
  refuse(pastRequest('c18', 'andre', -2, 1, '09:00', '10:00', 6), 'Fora do horário combinado para esta sala.', 20);

  const late1 = pastRequest('c19', 'tiago', -1, 3, '15:00', '16:00', 5);
  decide(late1, T.addMin(late1.createdAt, 180), 'sofia');
  cancel(late1, 5, true);
  const late2 = pastRequest('c19', 'andre', -2, 4, '11:00', '12:00', 6);
  decide(late2, T.addMin(late2.createdAt, 300), 'helena');
  cancel(late2, 18, true);
  const late3 = pastRequest('c19', 'clara', -3, 5, '09:30', '10:30', 4);
  decide(late3, T.addMin(late3.createdAt, 90), 'sofia');
  cancel(late3, 3, true);
  const onTime = pastRequest('c18', 'joana', -1, 4, '14:00', '15:00', 7);
  decide(onTime, T.addMin(onTime.createdAt, 240), 'sofia');
  cancel(onTime, 72, false);

  // Staff moved it less than 48 h before, so the owner's cancellation is never late.
  const exempt = pastRequest('c17', 'marta', -2, 5, '14:00', '15:00', 6);
  decide(exempt, T.addMin(exempt.createdAt, 120), 'sofia');
  exempt.events.push({ at: T.addMin(exempt.start, -30 * 60), by: 'sofia', action: 'Sala alterada', before: 'Sala 16', after: 'Sala 17', onBehalfOf: 'marta' });
  exempt.staffChangeWithinException = true;
  cancel(exempt, 6, false);
  exempt.lateExempt = true;
  exempt.events[exempt.events.length - 1].detail = '6 h antes do início; não conta como tardio porque o secretariado alterou a sala há menos de 48 h';

  const expired = pastRequest('c20', 'mariana', -1, 3, '12:00', '13:00', 3);
  expired.status = 'expired';
  expired.events.push({ at: expired.start, by: 'system', action: 'Pedido expirado', detail: 'Sem decisão até à hora de início' });

  // Scripted queue scenarios. Each one relies on the room being otherwise free.
  const pending = (room, owner, date, startTime, endTime, ageMin, parts, notes) => makeBooking({
    room,
    owner,
    start: T.combine(date, startTime),
    end: T.combine(date, endTime),
    status: 'pending',
    createdAt: T.addMin(now, -ageMin),
    parts,
    notes,
  });

  // Two requests that overlap each other: approving one blocks the other.
  pending('c13', 'joana', nextWorkday(2), '10:00', '11:30', 2 * 1440 + 170, [['mariana']], 'Duas cadeiras extra');
  pending('c13', 'andre', nextWorkday(2), '11:00', '12:00', 1440 + 300);

  // Already conflicts with an approved booking: cancelling that one unblocks it.
  const blocker = makeBooking({
    room: 'c14',
    owner: 'filipa',
    start: T.combine(nextWorkday(3), '14:00'),
    end: T.combine(nextWorkday(3), '16:00'),
    createdAt: T.addMin(now, -4 * 1440),
  });
  decide(blocker, T.addMin(now, -3 * 1440), 'sofia');
  pending('c14', 'leonor', nextWorkday(3), '15:00', '16:30', 3 * 1440 + 40);

  // Conflict with the holiday: overriding the holiday unblocks it.
  pending('c15', 'nuno', holidayDate, '10:00', '11:00', 1440 + 45);
  // Conflict with an exclusive assignment (Carla, Monday to Wednesday).
  pending('c7', 'clara', T.addDays(monday, 7 + 1), '10:00', '11:00', 900);

  // Marta's own requests, with participants and a time split.
  pending('c16', 'marta', nextWorkday(4), '09:00', '10:30', 500, [['tiago', '09:00', '09:45'], ['leonor', '09:45', '10:30']], 'Sala sossegada, sem campainha');
  pending('r4', 'marta', nextWorkday(3), '09:00', '10:00', 300);
  pending('c17', 'mariana', nextWorkday(3), '16:00', '17:00', 120);

  // Ribeira queue.
  pending('r3', 'daniel', nextWorkday(2), '09:00', '10:00', 1440 + 100);
  pending('r3', 'nuno', nextWorkday(2), '09:30', '10:30', 600);

  const auditEvents = [
    { at: T.addMin(now, -6 * 1440), by: 'sofia', locationId: 'central', action: 'Convite enviado', target: 'clara', detail: 'Profissional · Estagiária' },
    { at: T.addMin(now, -5 * 1440), by: 'helena', locationId: 'central', action: 'Orientação criada', target: 'clara', detail: 'Orientadora: Filipa Antunes' },
    { at: T.addMin(now, -2 * 1440), by: 'rui', locationId: 'ribeira', action: 'Filiação criada', target: 'nuno', detail: 'Profissional · Residente' },
    { at: T.addMin(now, -1500), by: 'system', locationId: 'central', action: 'Login falhado', target: 'andre', detail: '3 tentativas' },
  ];

  return {
    locations,
    rooms,
    users,
    memberships,
    mentorships,
    roomAssignments,
    closures,
    locationSettings,
    bookings,
    auditEvents,
    // Person shown for each profile and location in the top selector.
    personas: {
      professional: { central: 'marta', ribeira: 'marta' },
      secretariat: { central: 'sofia', ribeira: 'rui' },
      coordination: { central: 'helena', ribeira: 'tomas' },
      admin: { central: 'admin', ribeira: 'admin' },
    },
  };
};
