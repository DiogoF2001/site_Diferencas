// In-memory state and domain rules. Everything a future server would enforce
// lives here (permissions, free/busy projection, conflicts), not in the views.

// Times are Europe/Lisbon wall-clock strings: 'YYYY-MM-DDTHH:mm'. They sort as text.
window.T = {
  pad: (n) => String(n).padStart(2, '0'),
  toMs(s) {
    const [y, m, d, hh = 0, mm = 0] = s.split(/[-T:]/).map(Number);
    return Date.UTC(y, m - 1, d, hh, mm);
  },
  fromMs(ms) {
    return new Date(ms).toISOString().slice(0, 16);
  },
  now() {
    const parts = new Intl.DateTimeFormat('en-CA', {
      timeZone: 'Europe/Lisbon', hourCycle: 'h23', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
    }).formatToParts(new Date());
    const get = (type) => parts.find((p) => p.type === type).value;
    return `${get('year')}-${get('month')}-${get('day')}T${get('hour')}:${get('minute')}`;
  },
  date: (s) => s.slice(0, 10),
  time: (s) => s.slice(11, 16),
  combine: (date, time) => `${date}T${time}`,
  addMin: (s, minutes) => T.fromMs(T.toMs(s) + minutes * 60000),
  addDays: (date, days) => T.fromMs(T.toMs(date) + days * 86400000).slice(0, 10),
  diffMin: (a, b) => (T.toMs(a) - T.toMs(b)) / 60000,
  weekday(date) {
    const day = new Date(T.toMs(date)).getUTCDay();
    return day === 0 ? 7 : day;
  },
  monday: (date) => T.addDays(date, 1 - T.weekday(date)),
  overlaps: (aStart, aEnd, bStart, bEnd) => aStart < bEnd && bStart < aEnd,
  fmtDate(date) {
    return new Intl.DateTimeFormat('pt-PT', { timeZone: 'UTC', weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' }).format(new Date(T.toMs(date)));
  },
  fmtDateLong(date) {
    return new Intl.DateTimeFormat('pt-PT', { timeZone: 'UTC', weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }).format(new Date(T.toMs(date)));
  },
  fmtDateTime(s) {
    const [y, m, d] = T.date(s).split('-');
    return `${d}/${m}/${y}, ${T.time(s)}`;
  },
  fmtRange: (start, end) => `${T.fmtDate(T.date(start))}, ${T.time(start)}–${T.time(end)}`,
  fmtMinutes(total) {
    const h = Math.floor(total / 60);
    const m = Math.round(total - h * 60);
    if (!h) return `${m} min`;
    return m ? `${h} h ${m} min` : `${h} h`;
  },
  since(s) {
    const minutes = Math.max(0, T.diffMin(T.now(), s));
    if (minutes < 60) return `há ${Math.round(minutes)} min`;
    const days = Math.floor(minutes / 1440);
    const hours = Math.floor((minutes - days * 1440) / 60);
    if (!days) return `há ${hours} h`;
    const dayText = days === 1 ? '1 dia' : `${days} dias`;
    return hours ? `há ${dayText} e ${hours} h` : `há ${dayText}`;
  },
  slug(name) {
    return name.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/\s+/g, '.');
  },
};

window.Store = (() => {
  const T = window.T;
  let state = null;

  const session = { profile: 'professional', locationId: 'central' };

  const LEVEL = { professional: 1, secretariat: 2, coordination: 3 };
  const ROLE_LABEL = { professional: 'Profissional', secretariat: 'Secretariado', coordination: 'Coordenação' };
  const SUBROLE_LABEL = { resident: 'Residente', intern: 'Estagiária' };
  const STATUS_LABEL = { pending: 'Pendente', approved: 'Aprovada', refused: 'Recusada', cancelled: 'Cancelada', expired: 'Expirada' };

  const STAFF_PERMS = [
    'salas.view_occupancy', 'salas.schedule', 'salas.own_hours', 'salas.view_details', 'salas.approve', 'salas.edit_any',
    'salas.direct_booking', 'salas.manage_closures', 'salas.manage_rules', 'core.manage_members',
  ];
  const ROLE_PERMS = {
    professional: ['salas.view_occupancy', 'salas.schedule', 'salas.own_hours', 'salas.request'],
    secretariat: STAFF_PERMS,
    coordination: [...STAFF_PERMS, 'salas.reports', 'core.list_professionals', 'core.audit_view'],
  };
  // Tied to a person's own activity, which the global admin account does not have.
  const PERSONAL_PERMS = ['salas.request', 'salas.schedule', 'salas.own_hours'];

  const reset = () => {
    state = window.DIF_SEED(T.now());
  };

  const byId = (list, id) => list.find((item) => item.id === id);
  const user = (id) => byId(state.users, id);
  const userName = (id) => {
    if (id === 'system') return 'Sistema';
    const found = user(id);
    return found ? found.name : id;
  };
  const room = (id) => byId(state.rooms, id);
  const roomName = (id) => room(id).name;
  const location = (id) => byId(state.locations, id);
  const booking = (id) => byId(state.bookings, id);
  const settings = (locationId) => state.locationSettings[locationId];
  const roomsOf = (locationId) => state.rooms.filter((r) => r.locationId === locationId && r.active);

  const currentUser = () => user(state.personas[session.profile][session.locationId]);

  const activeMemberships = (userId, locationId) => {
    const today = T.date(T.now());
    return state.memberships.filter((m) => m.userId === userId
      && (!locationId || m.locationId === locationId)
      && !m.removedAt
      && m.start <= today
      && (!m.end || m.end >= today));
  };

  // The single permission check. Views never look at role names.
  const hasPermIn = (u, perm, locationId) => {
    if (u.isSuperuser) return !PERSONAL_PERMS.includes(perm);
    if (u.status !== 'active') return false;
    return activeMemberships(u.id, locationId).some((m) => ROLE_PERMS[m.role].includes(perm));
  };
  const can = (perm, locationId) => hasPermIn(currentUser(), perm, locationId || session.locationId);

  const levelIn = (u, locationId) => {
    if (u.isSuperuser) return 99;
    return Math.max(0, ...activeMemberships(u.id, locationId).map((m) => LEVEL[m.role]));
  };

  const membersOf = (locationId) => {
    const ids = [];
    state.memberships.forEach((m) => {
      if (m.locationId === locationId && !m.removedAt && !ids.includes(m.userId)) ids.push(m.userId);
    });
    return ids.map(user).filter(Boolean).sort((a, b) => a.name.localeCompare(b.name, 'pt'));
  };
  const roleLabel = (m) => (m.subrole ? `${ROLE_LABEL[m.role]} · ${SUBROLE_LABEL[m.subrole]}` : ROLE_LABEL[m.role]);
  const rolesText = (userId, locationId) => activeMemberships(userId, locationId).map(roleLabel).join(' + ');

  const assignableRoles = (locationId) => {
    const level = levelIn(currentUser(), locationId);
    return Object.keys(LEVEL).filter((role) => can('core.manage_members', locationId) && LEVEL[role] <= level);
  };
  const canManageMember = (target, locationId) => can('core.manage_members', locationId) && levelIn(target, locationId) <= levelIn(currentUser(), locationId);
  // Whole-account actions need a level >= the target's in every location of the target.
  const canActOnAccount = (target) => {
    const actor = currentUser();
    if (actor.isSuperuser) return true;
    if (target.isSuperuser || target.id === actor.id) return false;
    const locations = [...new Set(activeMemberships(target.id).map((m) => m.locationId))];
    return locations.length > 0 && locations.every((loc) => levelIn(actor, loc) >= levelIn(target, loc) && hasPermIn(actor, 'core.manage_members', loc));
  };

  const isParty = (b, userId) => b.ownerId === userId || b.participations.some((p) => p.userId === userId);
  const canViewBooking = (b) => isParty(b, currentUser().id) || can('salas.view_details', b.locationId);
  const canEditParticipants = (b) => (b.ownerId === currentUser().id || can('salas.edit_any', b.locationId))
    && ['pending', 'approved'].includes(b.status) && b.end > T.now();
  const canCancel = (b) => (b.ownerId === currentUser().id || can('salas.edit_any', b.locationId))
    && ['pending', 'approved'].includes(b.status) && b.end > T.now();

  // ---- Conflicts: always computed on demand, never stored ----

  const assignmentsOn = (roomId, date) => {
    const weekday = T.weekday(date);
    return state.roomAssignments.filter((a) => a.roomId === roomId
      && a.weekdays.includes(weekday)
      && a.from <= date
      && (!a.to || a.to >= date));
  };

  const closuresOn = (locationId, date) => state.closures.filter((c) => c.locationId === locationId
    && !c.overriddenBy
    && T.date(c.start) <= date
    && T.date(c.end) >= date);

  const conflictsFor = (roomId, start, end, { excludeId = null, ownerId = null } = {}) => {
    const result = [];
    const date = T.date(start);
    const { locationId } = room(roomId);
    state.bookings.forEach((b) => {
      if (b.id !== excludeId && b.roomId === roomId && b.status === 'approved' && T.overlaps(start, end, b.start, b.end)) {
        result.push({ type: 'booking', bookingId: b.id, start: b.start, end: b.end, ownerId: b.ownerId });
      }
    });
    assignmentsOn(roomId, date).forEach((a) => {
      const aStart = T.combine(date, a.start);
      const aEnd = T.combine(date, a.end);
      if (a.userId !== ownerId && T.overlaps(start, end, aStart, aEnd)) {
        result.push({ type: 'assignment', start: aStart, end: aEnd, ownerId: a.userId });
      }
    });
    closuresOn(locationId, date).forEach((c) => {
      if ((!c.roomId || c.roomId === roomId) && T.overlaps(start, end, c.start, c.end)) {
        result.push({ type: 'closure', start: c.start, end: c.end, reason: c.reason });
      }
    });
    return result;
  };

  const freeRooms = (locationId, start, end, opts = {}) => roomsOf(locationId)
    .filter((r) => conflictsFor(r.id, start, end, opts).length === 0);

  const pendingOverlaps = (b) => state.bookings.filter((o) => o.id !== b.id
    && o.roomId === b.roomId && o.status === 'pending' && T.overlaps(b.start, b.end, o.start, o.end));

  // ---- Free/busy projection: what would leave the server for this person ----

  const gridBlocks = (locationId, date) => {
    const me = currentUser();
    const details = can('salas.view_details', locationId);
    const blocks = [];
    state.bookings.forEach((b) => {
      if (b.locationId !== locationId || T.date(b.start) !== date) return;
      if (!['approved', 'pending'].includes(b.status)) return;
      if (details || isParty(b, me.id)) {
        blocks.push({
          kind: b.status,
          mine: isParty(b, me.id),
          bookingId: b.id,
          roomId: b.roomId,
          start: b.start,
          end: b.end,
          ownerId: b.ownerId,
          label: details ? userName(b.ownerId) : (b.ownerId === me.id ? 'A minha reserva' : `Com ${userName(b.ownerId)}`),
        });
      } else if (b.status === 'approved') {
        blocks.push({ kind: 'busy', roomId: b.roomId, start: b.start, end: b.end, label: 'Ocupado' });
      }
    });
    roomsOf(locationId).forEach((r) => {
      assignmentsOn(r.id, date).forEach((a) => {
        const start = T.combine(date, a.start);
        const end = T.combine(date, a.end);
        if (details || a.userId === me.id) {
          blocks.push({ kind: 'exclusive', roomId: r.id, start, end, label: `Exclusiva · ${userName(a.userId)}` });
        } else {
          blocks.push({ kind: 'busy', roomId: r.id, start, end, label: 'Ocupado' });
        }
      });
    });
    return blocks;
  };

  const scheduleFor = (userId, fromDate, toDate) => state.bookings
    .filter((b) => isParty(b, userId)
      && ['approved', 'pending'].includes(b.status)
      && T.date(b.start) >= fromDate
      && T.date(b.start) <= toDate)
    .sort((a, b) => a.start.localeCompare(b.start));

  // ---- Hours ----

  const hoursItems = (userId, { locationId = null, from = null } = {}) => {
    const now = T.now();
    const items = [];
    state.bookings.forEach((b) => {
      if (b.status !== 'approved' || b.end > now) return;
      if (locationId && b.locationId !== locationId) return;
      if (from && T.date(b.start) < from) return;
      if (b.ownerId === userId) {
        items.push({ booking: b, start: b.start, end: b.end, minutes: T.diffMin(b.end, b.start), role: 'Titular' });
      }
      b.participations.filter((p) => p.userId === userId).forEach((p) => {
        items.push({ booking: b, start: p.start, end: p.end, minutes: T.diffMin(p.end, p.start), role: 'Participante' });
      });
    });
    return items.sort((a, b) => b.start.localeCompare(a.start));
  };
  const totalMinutes = (items) => items.reduce((sum, item) => sum + item.minutes, 0);

  const menteesOf = (mentorId, locationId) => {
    const today = T.date(T.now());
    return state.mentorships.filter((o) => o.mentorId === mentorId && o.locationId === locationId && o.start <= today && (!o.end || o.end >= today));
  };

  // Hours of the people taking part in bookings owned by this person.
  const participantHours = (ownerId, { locationId, from }) => {
    const now = T.now();
    const totals = new Map();
    state.bookings.forEach((b) => {
      if (b.ownerId !== ownerId || b.status !== 'approved' || b.end > now || b.locationId !== locationId) return;
      if (from && T.date(b.start) < from) return;
      b.participations.forEach((p) => {
        totals.set(p.userId, (totals.get(p.userId) || 0) + T.diffMin(p.end, p.start));
      });
    });
    return [...totals.entries()].map(([userId, minutes]) => ({ userId, minutes })).sort((a, b) => b.minutes - a.minutes);
  };

  // ---- Validation ----

  const validateBooking = (draft, { mode }) => {
    const errors = [];
    const rules = settings(draft.locationId);
    const { start, end, roomId } = draft;
    if (!roomId) errors.push('Escolhe uma sala.');
    if (!start || !end || start.length < 16 || end.length < 16) {
      errors.push('Indica o dia, a hora de início e a hora de fim.');
      return errors;
    }
    if (start >= end) {
      errors.push('A hora de fim tem de ser depois da hora de início.');
      return errors;
    }
    const now = T.now();
    if (start <= now) errors.push('O início tem de ser no futuro.');
    if (!rules.days.includes(T.weekday(T.date(start)))) errors.push('O polo não funciona nesse dia da semana.');
    if (T.time(start) < rules.open || T.time(end) > rules.close) errors.push(`O horário de funcionamento é ${rules.open}–${rules.close}.`);
    const onBlock = (time) => {
      const [h, m] = time.split(':').map(Number);
      return (h * 60 + m) % rules.blockMin === 0;
    };
    if (!onBlock(T.time(start)) || !onBlock(T.time(end))) errors.push(`As horas têm de seguir blocos de ${rules.blockMin} min.`);

    if (mode === 'request') {
      const duration = T.diffMin(end, start);
      if (duration < rules.minDurationMin) errors.push(`A duração mínima de um pedido é ${T.fmtMinutes(rules.minDurationMin)}.`);
      if (duration > rules.maxDurationMin) errors.push(`A duração máxima de um pedido é ${T.fmtMinutes(rules.maxDurationMin)}.`);
      if (start > now && T.diffMin(start, now) < rules.minAdvanceHours * 60) {
        errors.push(`Os pedidos precisam de ${rules.minAdvanceHours} h de antecedência. Para menos do que isso, fala com o secretariado, que marca diretamente.`);
      }
      if (T.date(start) > T.addDays(T.date(now), rules.maxAdvanceWeeks * 7)) errors.push(`Só podes pedir com ${rules.maxAdvanceWeeks} semanas de antecedência, no máximo.`);
    }

    if (roomId) {
      const conflicts = conflictsFor(roomId, start, end, { ownerId: draft.ownerId });
      if (conflicts.length) {
        if (can('salas.view_details', draft.locationId)) {
          conflicts.forEach((c) => errors.push(`Conflito: ${describeConflict(c)}.`));
        } else {
          errors.push('A sala não está livre nesse intervalo. Experimenta "Encontrar sala livre".');
        }
      }
    }

    const seen = new Set();
    (draft.participants || []).forEach((p) => {
      if (!p.userId) return;
      if (seen.has(p.userId)) errors.push(`${userName(p.userId)} aparece mais do que uma vez nos participantes.`);
      seen.add(p.userId);
      if (p.start >= p.end || p.start < start || p.end > end) errors.push(`O intervalo de ${userName(p.userId)} tem de ficar dentro da reserva.`);
    });
    return errors;
  };

  const describeConflict = (c) => {
    if (c.type === 'closure') return `bloqueio "${c.reason}"`;
    if (c.type === 'assignment') return `sala exclusiva de ${userName(c.ownerId)}, ${T.time(c.start)}–${T.time(c.end)}`;
    return `reserva aprovada de ${userName(c.ownerId)}, ${T.time(c.start)}–${T.time(c.end)}`;
  };

  // ---- Commands ----

  const log = (b, action, extra = {}) => {
    const entry = { at: T.now(), by: currentUser().id, action, ...extra };
    b.events.push(entry);
    return entry;
  };
  const audit = (locationId, action, target, detail) => {
    state.auditEvents.push({ at: T.now(), by: currentUser().id, locationId, action, target, detail });
  };
  const fail = (message) => ({ ok: false, errors: [message] });
  const newId = (prefix) => `${prefix}${Date.now().toString(36)}${Math.floor(Math.random() * 1000)}`;

  const createBooking = (draft, { status, mode }) => {
    const errors = validateBooking(draft, { mode });
    if (errors.length) return { ok: false, errors };
    const now = T.now();
    const me = currentUser();
    const b = {
      id: newId('b'),
      locationId: draft.locationId,
      roomId: draft.roomId,
      ownerId: draft.ownerId,
      start: draft.start,
      end: draft.end,
      status,
      notes: draft.notes || '',
      createdBy: me.id,
      createdAt: now,
      decidedAt: status === 'approved' ? now : null,
      refusalReason: null,
      cancelledAt: null,
      cancelledBy: null,
      lateCancel: false,
      lateExempt: false,
      staffChangeWithinException: false,
      participations: [],
      events: [],
    };
    state.bookings.push(b);
    const behalf = draft.ownerId !== me.id ? { onBehalfOf: draft.ownerId } : {};
    log(b, status === 'approved' ? 'Marcação direta' : 'Pedido criado', { detail: `${roomName(b.roomId)}, ${T.fmtRange(b.start, b.end)}`, ...behalf });
    (draft.participants || []).filter((p) => p.userId).forEach((p) => {
      b.participations.push({ userId: p.userId, start: p.start, end: p.end });
      log(b, 'Participante adicionado', { detail: `${userName(p.userId)}, ${T.time(p.start)}–${T.time(p.end)}`, ...behalf });
    });
    return { ok: true, booking: b };
  };

  const submitRequest = (draft) => {
    if (!can('salas.request', draft.locationId)) return fail('Não tens permissão para submeter pedidos neste polo.');
    return createBooking({ ...draft, ownerId: currentUser().id }, { status: 'pending', mode: 'request' });
  };

  const directBooking = (draft) => {
    if (!can('salas.direct_booking', draft.locationId)) return fail('Não tens permissão para marcar diretamente neste polo.');
    if (!draft.ownerId) return fail('Escolhe o titular da reserva.');
    return createBooking(draft, { status: 'approved', mode: 'direct' });
  };

  const approve = (id) => {
    const b = booking(id);
    if (!can('salas.approve', b.locationId)) return fail('Não tens permissão para aprovar neste polo.');
    const conflicts = conflictsFor(b.roomId, b.start, b.end, { excludeId: b.id, ownerId: b.ownerId });
    if (conflicts.length) return fail(`Não é possível aprovar nesta sala: ${describeConflict(conflicts[0])}.`);
    b.status = 'approved';
    b.decidedAt = T.now();
    log(b, 'Pedido aprovado', { detail: `Nesta sala (${roomName(b.roomId)})` });
    return { ok: true, booking: b };
  };

  const staffChangeMark = (b) => {
    const rules = settings(b.locationId);
    if (T.diffMin(b.start, T.now()) < rules.exceptionHours * 60) b.staffChangeWithinException = true;
  };

  const approveInRoom = (id, roomId) => {
    const b = booking(id);
    if (!can('salas.approve', b.locationId)) return fail('Não tens permissão para aprovar neste polo.');
    const conflicts = conflictsFor(roomId, b.start, b.end, { excludeId: b.id, ownerId: b.ownerId });
    if (conflicts.length) return fail(`${roomName(roomId)} já não está livre: ${describeConflict(conflicts[0])}.`);
    const before = roomName(b.roomId);
    b.roomId = roomId;
    b.status = 'approved';
    b.decidedAt = T.now();
    staffChangeMark(b);
    log(b, 'Pedido aprovado noutra sala', { before, after: roomName(roomId), detail: 'O requerente é notificado (simulado)' });
    return { ok: true, booking: b };
  };

  const refuseBooking = (id, reason) => {
    const b = booking(id);
    if (!can('salas.approve', b.locationId)) return fail('Não tens permissão para recusar neste polo.');
    if (!reason || !reason.trim()) return fail('Indica o motivo da recusa.');
    b.status = 'refused';
    b.refusalReason = reason.trim();
    b.decidedAt = T.now();
    log(b, 'Pedido recusado', { detail: b.refusalReason });
    return { ok: true, booking: b };
  };

  const cancelPreview = (b) => {
    const rules = settings(b.locationId);
    const hoursBefore = T.diffMin(b.start, T.now()) / 60;
    const byOwner = b.ownerId === currentUser().id;
    const within = b.status === 'approved' && byOwner && hoursBefore < rules.lateCancelHours;
    return { within, exempt: within && b.staffChangeWithinException, late: within && !b.staffChangeWithinException, rules };
  };

  const cancelBooking = (id) => {
    const b = booking(id);
    if (!canCancel(b)) return fail('Não tens permissão para cancelar esta reserva.');
    const { late, exempt } = cancelPreview(b);
    b.status = 'cancelled';
    b.cancelledAt = T.now();
    b.cancelledBy = currentUser().id;
    b.lateCancel = late;
    b.lateExempt = exempt;
    let action = 'Cancelada';
    let detail = 'A sala ficou livre; os pedidos em fila voltam a poder ser aprovados';
    if (late) action = 'Cancelada (tardio)';
    if (exempt) detail = 'Não conta como tardio: o secretariado ou a coordenação alteraram a sala ou a hora em cima da hora';
    log(b, action, { detail });
    return { ok: true, booking: b };
  };

  const moveBooking = (id, { roomId, start, end }) => {
    const b = booking(id);
    if (!can('salas.edit_any', b.locationId)) return fail('Não tens permissão para alterar reservas neste polo.');
    const errors = validateBooking({ locationId: b.locationId, roomId, start, end, ownerId: b.ownerId }, { mode: 'direct' })
      .filter((e) => !e.startsWith('Conflito'));
    const conflicts = conflictsFor(roomId, start, end, { excludeId: b.id, ownerId: b.ownerId });
    conflicts.forEach((c) => errors.push(`Conflito: ${describeConflict(c)}.`));
    if (errors.length) return { ok: false, errors };
    const behalf = b.ownerId !== currentUser().id ? { onBehalfOf: b.ownerId } : {};
    if (roomId !== b.roomId) {
      log(b, 'Sala alterada', { before: roomName(b.roomId), after: roomName(roomId), ...behalf });
      b.roomId = roomId;
    }
    if (start !== b.start || end !== b.end) {
      log(b, 'Hora alterada', { before: T.fmtRange(b.start, b.end), after: T.fmtRange(start, end), ...behalf });
      // Same duration: the time split moves along. New duration: back to the whole booking.
      const sameDuration = T.diffMin(end, start) === T.diffMin(b.end, b.start);
      const shift = T.diffMin(start, b.start);
      b.participations.forEach((p) => {
        p.start = sameDuration ? T.addMin(p.start, shift) : start;
        p.end = sameDuration ? T.addMin(p.end, shift) : end;
      });
      b.start = start;
      b.end = end;
    }
    staffChangeMark(b);
    return { ok: true, booking: b };
  };

  const addParticipant = (id, userId, start, end) => {
    const b = booking(id);
    if (!canEditParticipants(b)) return fail('Não podes alterar os participantes desta reserva.');
    if (!userId) return fail('Escolhe a pessoa.');
    if (isParty(b, userId)) return fail(`${userName(userId)} já faz parte desta reserva.`);
    if (!activeMemberships(userId, b.locationId).length) return fail('Só podes adicionar membros deste polo.');
    if (start >= end || start < b.start || end > b.end) return fail('O intervalo tem de ficar dentro da reserva.');
    b.participations.push({ userId, start, end });
    log(b, 'Participante adicionado', { detail: `${userName(userId)}, ${T.time(start)}–${T.time(end)}` });
    return { ok: true, booking: b };
  };

  const removeParticipant = (id, userId) => {
    const b = booking(id);
    if (!canEditParticipants(b)) return fail('Não podes alterar os participantes desta reserva.');
    b.participations = b.participations.filter((p) => p.userId !== userId);
    log(b, 'Participante removido', { detail: userName(userId) });
    return { ok: true, booking: b };
  };

  const expireDue = () => {
    const now = T.now();
    state.bookings.forEach((b) => {
      if (b.status === 'pending' && b.start <= now) {
        b.status = 'expired';
        b.events.push({ at: now, by: 'system', action: 'Pedido expirado', detail: 'Sem decisão até à hora de início' });
      }
    });
  };

  const queue = (locationId) => state.bookings
    .filter((b) => b.locationId === locationId && b.status === 'pending')
    .sort((a, b) => a.createdAt.localeCompare(b.createdAt));

  const recentlyDecided = (locationId, limit) => state.bookings
    .filter((b) => b.locationId === locationId && b.decidedAt && ['approved', 'refused'].includes(b.status))
    .sort((a, b) => b.decidedAt.localeCompare(a.decidedAt))
    .slice(0, limit);

  // ---- Closures ----

  const closureAffected = (locationId, roomId, start, end) => state.bookings.filter((b) => b.locationId === locationId
    && b.status === 'approved'
    && (!roomId || b.roomId === roomId)
    && T.overlaps(start, end, b.start, b.end));

  const overrideClosure = (id) => {
    const c = byId(state.closures, id);
    if (!can('salas.manage_closures', c.locationId)) return fail('Não tens permissão para gerir bloqueios neste polo.');
    c.overriddenBy = currentUser().id;
    c.overriddenAt = T.now();
    c.events.push({ at: c.overriddenAt, by: c.overriddenBy, action: 'Feriado anulado neste dia' });
    return { ok: true };
  };

  const restoreClosure = (id) => {
    const c = byId(state.closures, id);
    if (!can('salas.manage_closures', c.locationId)) return fail('Não tens permissão para gerir bloqueios neste polo.');
    c.overriddenBy = null;
    c.overriddenAt = null;
    c.events.push({ at: T.now(), by: currentUser().id, action: 'Anulação retirada; o feriado volta a bloquear' });
    return { ok: true };
  };

  const addClosure = ({ locationId, roomId, start, end, reason }) => {
    if (!can('salas.manage_closures', locationId)) return fail('Não tens permissão para gerir bloqueios neste polo.');
    if (!start || !end || start >= end) return fail('Indica um intervalo válido.');
    if (!reason || !reason.trim()) return fail('Indica o motivo do bloqueio.');
    const closure = {
      id: newId('k'), locationId, roomId: roomId || null, start, end, source: 'manual', reason: reason.trim(), overriddenBy: null, overriddenAt: null,
      events: [{ at: T.now(), by: currentUser().id, action: 'Bloqueio manual criado', detail: roomId ? roomName(roomId) : 'Todas as salas' }],
    };
    state.closures.push(closure);
    return { ok: true, closure };
  };

  const removeClosure = (id) => {
    const c = byId(state.closures, id);
    if (c.source !== 'manual' || !can('salas.manage_closures', c.locationId)) return fail('Este bloqueio não pode ser removido.');
    state.closures = state.closures.filter((x) => x.id !== id);
    return { ok: true };
  };

  // ---- Accounts ----

  const addMembership = (target, locationId, { role, subrole, end }) => {
    state.memberships.push({
      id: newId('m'),
      userId: target.id,
      locationId,
      role,
      subrole: role === 'professional' ? (subrole || 'resident') : null,
      start: T.date(T.now()),
      end: end || null,
      removedAt: null,
    });
  };

  const validateMembership = (locationId, { role, subrole, end }) => {
    if (!assignableRoles(locationId).includes(role)) return 'Só podes atribuir papéis até ao teu próprio nível neste polo.';
    if (role === 'professional' && subrole === 'intern' && !end) return 'As filiações de estagiárias têm data de fim.';
    return null;
  };

  const inviteOrAdd = (locationId, { name, email, role, subrole, end, mustExist }) => {
    const cleanEmail = (email || '').trim().toLowerCase();
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(cleanEmail)) return fail('Indica um e-mail válido.');
    const problem = validateMembership(locationId, { role, subrole, end });
    if (problem) return fail(problem);
    const existing = state.users.find((u) => u.email === cleanEmail);
    if (existing) {
      if (activeMemberships(existing.id, locationId).some((m) => m.role === role)) return fail('Esta pessoa já tem esse papel neste polo.');
      addMembership(existing, locationId, { role, subrole, end });
      const detail = role === 'professional' ? `${ROLE_LABEL[role]} · ${SUBROLE_LABEL[subrole || 'resident']}` : ROLE_LABEL[role];
      audit(locationId, 'Filiação criada', existing.id, detail);
      return { ok: true, existing: true, user: existing };
    }
    if (mustExist) return fail('Não existe nenhuma conta com esse e-mail. Usa "Convidar pessoa".');
    if (!name || !name.trim()) return fail('Indica o nome da pessoa.');
    const created = { id: newId('u'), name: name.trim(), email: cleanEmail, status: 'invited', twoFactor: false };
    state.users.push(created);
    addMembership(created, locationId, { role, subrole, end });
    audit(locationId, 'Convite enviado', created.id, `${ROLE_LABEL[role]}; link de uso único, válido 48 h (simulado)`);
    return { ok: true, existing: false, user: created };
  };

  const removeFromLocation = (userId, locationId) => {
    const target = user(userId);
    if (!canManageMember(target, locationId)) return fail('Só podes remover pessoas até ao teu próprio nível neste polo.');
    const now = T.date(T.now());
    state.memberships.forEach((m) => {
      if (m.userId === userId && m.locationId === locationId && !m.removedAt) m.removedAt = now;
    });
    audit(locationId, 'Filiação removida', userId, '');
    return { ok: true };
  };

  const sendRecovery = (userId, locationId) => {
    if (!can('core.manage_members', locationId)) return fail('Não tens permissão.');
    audit(locationId, 'Link de recuperação enviado', userId, 'Simulado: ninguém define a palavra-passe de outra pessoa');
    return { ok: true };
  };

  const deactivateAccount = (userId, locationId) => {
    const target = user(userId);
    if (!canActOnAccount(target)) return fail('Precisas de um nível igual ou superior ao desta pessoa em todos os polos dela.');
    target.status = 'inactive';
    audit(locationId, 'Conta desativada', userId, 'A conta fica guardada, para manter o histórico');
    return { ok: true };
  };

  const reactivateAccount = (userId, locationId) => {
    const target = user(userId);
    if (!canActOnAccount(target)) return fail('Precisas de um nível igual ou superior ao desta pessoa em todos os polos dela.');
    target.status = 'active';
    audit(locationId, 'Conta reativada', userId, '');
    return { ok: true };
  };

  const resetTwoFactor = (userId, locationId) => {
    const target = user(userId);
    if (!canActOnAccount(target)) return fail('Precisas de um nível igual ou superior ao desta pessoa em todos os polos dela.');
    target.twoFactor = false;
    audit(locationId, '2FA reposto', userId, '');
    return { ok: true };
  };

  const addMentorship = (locationId, mentorId, menteeId, end) => {
    if (!can('core.manage_members', locationId)) return fail('Não tens permissão.');
    if (!mentorId || !menteeId || mentorId === menteeId) return fail('Escolhe a orientadora e a orientanda.');
    if (!end) return fail('Indica a data de fim.');
    state.mentorships.push({ id: newId('o'), mentorId, menteeId, locationId, start: T.date(T.now()), end });
    audit(locationId, 'Orientação criada', menteeId, `Orientadora: ${userName(mentorId)}`);
    return { ok: true };
  };

  const endMentorship = (id) => {
    const o = byId(state.mentorships, id);
    if (!can('core.manage_members', o.locationId)) return fail('Não tens permissão.');
    o.end = T.addDays(T.date(T.now()), -1);
    audit(o.locationId, 'Orientação terminada', o.menteeId, `Orientadora: ${userName(o.mentorId)}`);
    return { ok: true };
  };

  const saveSettings = (locationId, values) => {
    if (!can('salas.manage_rules', locationId)) return fail('Não tens permissão para editar as regras deste polo.');
    const errors = [];
    if (!values.days.length) errors.push('Escolhe pelo menos um dia de funcionamento.');
    if (values.open >= values.close) errors.push('A hora de fecho tem de ser depois da hora de abertura.');
    if (values.minDurationMin > values.maxDurationMin) errors.push('A duração mínima não pode ser maior do que a máxima.');
    ['minDurationMin', 'maxDurationMin', 'minAdvanceHours', 'maxAdvanceWeeks', 'lateCancelHours', 'exceptionHours'].forEach((key) => {
      if (!Number.isFinite(values[key]) || values[key] < 0) errors.push('Os valores numéricos têm de ser zero ou superiores.');
    });
    if (errors.length) return { ok: false, errors: [...new Set(errors)] };
    if (!currentUser().isSuperuser) values.releaseEnabled = settings(locationId).releaseEnabled;
    state.locationSettings[locationId] = values;
    audit(locationId, 'Regras do polo alteradas', currentUser().id, '');
    return { ok: true };
  };

  // ---- Reports ----

  const report = (locationId, fromDate) => {
    const today = T.date(T.now());
    const rules = settings(locationId);
    const dailyMinutes = T.diffMin(T.combine(today, rules.close), T.combine(today, rules.open));
    const days = [];
    for (let d = fromDate; d < today; d = T.addDays(d, 1)) {
      if (rules.days.includes(T.weekday(d)) && !closuresOn(locationId, d).some((c) => !c.roomId)) days.push(d);
    }
    const inPeriod = state.bookings.filter((b) => b.locationId === locationId && T.date(b.start) >= fromDate && T.date(b.start) <= today);
    const past = inPeriod.filter((b) => T.date(b.start) < today);

    const occupancy = roomsOf(locationId).map((r) => {
      let used = 0;
      past.forEach((b) => {
        if (b.roomId === r.id && b.status === 'approved') used += T.diffMin(b.end, b.start);
      });
      days.forEach((d) => {
        assignmentsOn(r.id, d).forEach((a) => { used += T.diffMin(T.combine(d, a.end), T.combine(d, a.start)); });
      });
      const available = days.length * dailyMinutes;
      return { room: r, minutes: used, rate: available ? Math.min(1, used / available) : 0 };
    }).sort((a, b) => b.rate - a.rate);

    const hours = membersOf(locationId).map((u) => {
      const professional = activeMemberships(u.id, locationId).find((m) => m.role === 'professional');
      return { user: u, subrole: professional ? SUBROLE_LABEL[professional.subrole] : null, minutes: totalMinutes(hoursItems(u.id, { locationId, from: fromDate })) };
    }).filter((row) => row.subrole || row.minutes > 0).sort((a, b) => b.minutes - a.minutes);

    const decided = inPeriod.filter((b) => b.decidedAt);
    const decisionMinutes = decided.reduce((sum, b) => sum + T.diffMin(b.decidedAt, b.createdAt), 0);
    const late = inPeriod.filter((b) => b.lateCancel).sort((a, b) => b.cancelledAt.localeCompare(a.cancelledAt));
    const refused = inPeriod.filter((b) => b.status === 'refused');
    const usedTotal = occupancy.reduce((sum, row) => sum + row.minutes, 0);
    const availableTotal = occupancy.length * days.length * dailyMinutes;

    return {
      occupancy,
      hours,
      late,
      refused,
      averageOccupancy: availableTotal ? usedTotal / availableTotal : 0,
      averageDecisionMinutes: decided.length ? decisionMinutes / decided.length : 0,
      totalHoursMinutes: hours.reduce((sum, row) => sum + row.minutes, 0),
    };
  };

  const otherLocationRoles = (userId, locationId) => activeMemberships(userId)
    .filter((m) => m.locationId !== locationId)
    .map((m) => ({ location: location(m.locationId).name, role: roleLabel(m) }));

  reset();

  return {
    session,
    reset,
    get locations() { return state.locations; },
    get closures() { return state.closures; },
    get mentorships() { return state.mentorships; },
    get auditEvents() { return state.auditEvents; },
    get users() { return state.users; },
    ROLE_LABEL,
    SUBROLE_LABEL,
    STATUS_LABEL,
    user,
    userName,
    room,
    roomName,
    location,
    booking,
    settings,
    roomsOf,
    currentUser,
    activeMemberships,
    hasPermIn,
    can,
    levelIn,
    membersOf,
    roleLabel,
    rolesText,
    assignableRoles,
    canManageMember,
    canActOnAccount,
    isParty,
    canViewBooking,
    canEditParticipants,
    canCancel,
    conflictsFor,
    describeConflict,
    freeRooms,
    pendingOverlaps,
    closuresOn,
    gridBlocks,
    scheduleFor,
    hoursItems,
    totalMinutes,
    menteesOf,
    participantHours,
    validateBooking,
    submitRequest,
    directBooking,
    approve,
    approveInRoom,
    refuseBooking,
    cancelPreview,
    cancelBooking,
    moveBooking,
    addParticipant,
    removeParticipant,
    expireDue,
    queue,
    recentlyDecided,
    closureAffected,
    overrideClosure,
    restoreClosure,
    addClosure,
    removeClosure,
    inviteOrAdd,
    removeFromLocation,
    sendRecovery,
    deactivateAccount,
    reactivateAccount,
    resetTwoFactor,
    addMentorship,
    endMentorship,
    saveSettings,
    report,
    otherLocationRoles,
  };
})();
