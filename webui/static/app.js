// One page, one API client. Keep every HTTP call in this file's `api` object so the
// whole thing can be lifted into a Vue app when it moves into the OBG repo.
const api = {
  async games() {
    const response = await fetch('/api/games');
    return (await response.json()).games || [];
  },
  async view(gameId, seat) {
    const response = await fetch(`/api/games/${gameId}/view?seat=${encodeURIComponent(seat)}`);
    return response.json();
  },
  async history(gameId, seat, before) {
    const suffix = before ? `&before=${encodeURIComponent(before)}` : '';
    const response = await fetch(`/api/games/${gameId}/history?seat=${encodeURIComponent(seat)}${suffix}`);
    return response.json();
  },
  async catalog() {
    const response = await fetch('/api/catalog');
    return response.json();
  },
  async press(gameId, seat, customId, messageId) {
    const response = await fetch(`/api/games/${gameId}/press`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ seat, custom_id: customId, message_id: messageId }),
    });
    return response.json();
  },
  async turnMenu(gameId, seat) {
    const response = await fetch(`/api/games/${gameId}/turn-menu?seat=${encodeURIComponent(seat)}`,
      { method: 'POST' });
    return response.json();
  },
  async mirror(gameId, seat, on) {
    const response = await fetch(`/api/games/${gameId}/mirror`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ seat, mirror_to_discord: on }),
    });
    return response.json();
  },
};

const el = {
  game: document.getElementById('game'),
  seat: document.getElementById('seat'),
  round: document.getElementById('round'),
  turn: document.getElementById('turn'),
  mirror: document.getElementById('mirror'),
  turnMenu: document.getElementById('turn-menu'),
  board: document.getElementById('board'),
  stage: document.getElementById('board-stage'),
  viewport: document.getElementById('board-viewport'),
  overlay: document.getElementById('board-overlay'),
  boardNote: document.getElementById('board-note'),
  boardEmpty: document.getElementById('board-empty'),
  boardHint: document.getElementById('board-hint'),
  market: document.getElementById('tech-market'),
  marketNote: document.getElementById('market-note'),
  dock: document.getElementById('action-dock'),
  players: document.getElementById('players'),
  playersNote: document.getElementById('players-note'),
  historyDialog: document.getElementById('history-dialog'),
  historyList: document.getElementById('history-list'),
  historyNote: document.getElementById('history-note'),
  historyMore: document.getElementById('history-more'),
  historyRoom: document.getElementById('history-room'),
  factionDialog: document.getElementById('faction-dialog'),
  factionTitle: document.getElementById('faction-title'),
  factionSub: document.getElementById('faction-sub'),
  factionBody: document.getElementById('faction-body'),
  zoomDialog: document.getElementById('zoom-dialog'),
  zoomImage: document.getElementById('zoom-image'),
  toast: document.getElementById('toast'),
};

const state = {
  gameId: null,
  seat: '',
  view: null,
  catalog: { techs: {}, parts: {} },
  boardVersion: null,
  boardMeta: null,
  zoom: 1,
  panX: 0,
  panY: 0,
  fitPending: true,
  rendering: false,
  lastKey: null,
  history: [],
  historyHasMore: false,
  historyLoaded: false,
  historyRoom: '',
  factionPlayer: null,
  toastTimer: null,
  drag: null,
};

// ------------------------------------------------------------------ helpers
const escapeHtml = (text) => (text || '')
  .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;');

function bodyHtml(content) {
  return escapeHtml(content || '')
    .replace(/^\s*##\s+(.*)$/gm, '<h3>$1</h3>')
    .replace(/^\s*#\s+(.*)$/gm, '<h3>$1</h3>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/&lt;(a?):([\w]+):(\d+)&gt;/g, (_m, animated, name, id) =>
      `<img class="emoji" alt=":${name}:" loading="lazy" `
      + `src="https://cdn.discordapp.com/emojis/${id}.${animated ? 'gif' : 'png'}">`);
}

function signed(value) {
  if (value === null || value === undefined) return '?';
  return value > 0 ? `+${value}` : `${value}`;
}

function roomName(room) {
  if (!room) return 'table';
  return room.replace(/^aeb\d+-?/, '').replace(/-actions$/, '') || 'table';
}

function isCombat(message) {
  return /combat|battle|bombing/i.test(message.room || '');
}

function showToast(text, bad = false) {
  if (!text) return;
  el.toast.textContent = text;
  el.toast.classList.toggle('bad', bad);
  el.toast.classList.add('on');
  clearTimeout(state.toastTimer);
  state.toastTimer = setTimeout(() => el.toast.classList.remove('on'), 7000);
}

function closeDialog(id) {
  const dialog = document.getElementById(id);
  if (dialog && dialog.open) dialog.close();
}

// --------------------------------------------------------------- button map
function buttonById(view) {
  const map = new Map();
  for (const message of view.pending || []) {
    for (const button of message.buttons || []) {
      if (button.custom_id && !map.has(button.custom_id)) {
        map.set(button.custom_id, { button, message });
      }
    }
  }
  return map;
}

const TECH_RE = /(?:^|_)getTech_([a-z0-9]+)_(military|grid|nano|any)(_setup)?$/;
const SHIP_UPGRADE_RE = /_upgradeShip_(\d+)_([a-z]+)_(\S+)$/;
const OLD_PART_RE = /_selectOldPart_(\d+)_([a-z]+)_([a-z0-9]+)_([^_]+)_(\d+)(_partsShown)?$/;
const NEW_PART_RE = /_chooseUpgrade_(\d+)_([a-z]+)_([a-z0-9]+)_([a-z0-9]+)_(\d+)_([^_]+)$/;
const TECHNO_SHIP_RE = /_technoMagic_(\d{3})_([a-z]+)$/;

function techButton(customId) {
  const match = customId.match(TECH_RE);
  if (!match) return null;
  return { tech: match[1], track: match[2], setup: !!match[3] };
}

function partButton(customId) {
  if (customId.endsWith('_partsShown')) return null;
  let match = customId.match(OLD_PART_RE);
  if (match) {
    return { kind: 'old', actions: match[1], ship: match[2], part: match[3],
             disc: match[4], slot: Number(match[5]) };
  }
  match = customId.match(NEW_PART_RE);
  if (match) {
    return { kind: 'new', actions: match[1], ship: match[2], oldPart: match[3],
             part: match[4], slot: Number(match[5]), disc: match[6] };
  }
  match = customId.match(SHIP_UPGRADE_RE) || customId.match(TECHNO_SHIP_RE);
  if (match) {
    return { kind: 'ship', actions: match[1], ship: match[2] };
  }
  return null;
}

function tileAction(customId) {
  let match;
  if ((match = customId.match(/_buildIn_(\d{3})/))) return { position: match[1], kind: 'build' };
  if ((match = customId.match(/_exploreTile_(\d{3})/))) return { position: match[1], kind: 'explore' };
  if ((match = customId.match(/_moveFrom_(\d{3})/))) return { position: match[1], kind: 'move' };
  if ((match = customId.match(/_moveTo_\d{3}_([a-z]+)_(\d{3})/))) {
    return { position: match[2], kind: 'move', to: true, ship: match[1] };
  }
  if ((match = customId.match(/_addInfluenceFinish_(\d{3})/))) {
    return { position: match[1], kind: 'influence' };
  }
  if ((match = customId.match(/_removeInfluenceFinish_(\d{3})/))) {
    return { position: match[1], kind: 'influence' };
  }
  if ((match = customId.match(/_placeWarpPortal_(\d{3})/))) {
    return { position: match[1], kind: 'explore' };
  }
  if ((match = customId.match(/_placeTile_(\d{3})/))) return { position: match[1], kind: 'explore' };
  if ((match = customId.match(/_fillPopulation_(\d{3})/))) {
    return { position: match[1], kind: 'population' };
  }
  if ((match = customId.match(/_ancientsCube_[a-z]+_(\d{3})/))) {
    return { position: match[1], kind: 'population' };
  }
  return null;
}

// --------------------------------------------------------------------- board
function fitBoard() {
  const meta = state.boardMeta;
  if (!meta || !meta.width) return;
  const box = el.viewport.getBoundingClientRect();
  const zoom = Math.min(box.width / meta.width, box.height / meta.height);
  state.zoom = Math.max(0.05, zoom);
  state.panX = (box.width - meta.width * state.zoom) / 2;
  state.panY = (box.height - meta.height * state.zoom) / 2;
  applyTransform();
}

function applyTransform() {
  el.stage.style.transform = `translate(${state.panX}px, ${state.panY}px) scale(${state.zoom})`;
  el.stage.style.setProperty('--inv', String(1 / state.zoom));
}

function zoomAt(factor, clientX, clientY) {
  const box = el.viewport.getBoundingClientRect();
  const x = (clientX ?? box.left + box.width / 2) - box.left;
  const y = (clientY ?? box.top + box.height / 2) - box.top;
  const next = Math.min(3, Math.max(0.05, state.zoom * factor));
  const ratio = next / state.zoom;
  state.panX = x - (x - state.panX) * ratio;
  state.panY = y - (y - state.panY) * ratio;
  state.zoom = next;
  applyTransform();
}

function bindBoardPan() {
  let panning = null;
  el.viewport.addEventListener('pointerdown', (event) => {
    if (event.target.closest('.drag-token') || event.target.closest('.hotspot')) return;
    panning = { x: event.clientX, y: event.clientY, panX: state.panX, panY: state.panY };
    el.viewport.classList.add('grabbing');
    el.viewport.setPointerCapture(event.pointerId);
  });
  el.viewport.addEventListener('pointermove', (event) => {
    if (!panning) return;
    state.panX = panning.panX + event.clientX - panning.x;
    state.panY = panning.panY + event.clientY - panning.y;
    applyTransform();
  });
  const end = () => { panning = null; el.viewport.classList.remove('grabbing'); };
  el.viewport.addEventListener('pointerup', end);
  el.viewport.addEventListener('pointercancel', end);
  el.viewport.addEventListener('wheel', (event) => {
    event.preventDefault();
    zoomAt(event.deltaY < 0 ? 1.12 : 1 / 1.12, event.clientX, event.clientY);
  }, { passive: false });
  document.getElementById('zoom-in').addEventListener('click', () => zoomAt(1.25));
  document.getElementById('zoom-out').addEventListener('click', () => zoomAt(1 / 1.25));
  document.getElementById('zoom-fit').addEventListener('click', fitBoard);
}

function boardActions(view) {
  const actions = [];
  const seen = new Set();
  for (const message of view.pending || []) {
    for (const button of message.buttons || []) {
      const target = tileAction(button.custom_id || '');
      if (!target) continue;
      const key = `${target.position}:${target.kind}:${button.custom_id}`;
      if (seen.has(key)) continue;
      seen.add(key);
      actions.push({ ...target, button, message });
    }
  }
  return actions;
}

function renderOverlay(view) {
  const meta = state.boardMeta;
  el.overlay.replaceChildren();
  if (!meta || !meta.tiles) return;
  const byPosition = new Map(meta.tiles.map((tile) => [tile.position, tile]));
  // Unexplored ring slots: the board's shape stays readable between real tiles.
  for (const tile of meta.tiles) {
    if (!tile.empty) continue;
    const slot = document.createElement('div');
    slot.className = 'empty-slot';
    slot.style.left = `${tile.x}px`;
    slot.style.top = `${tile.y}px`;
    slot.style.width = '345px';
    slot.style.height = '300px';
    slot.title = `Unexplored position ${tile.position}`;
    el.overlay.appendChild(slot);
  }
  const actions = boardActions(view);
  const byTile = new Map();
  for (const action of actions) {
    if (!byTile.has(action.position)) byTile.set(action.position, []);
    byTile.get(action.position).push(action);
  }
  for (const [position, choices] of byTile) {
    const tile = byPosition.get(position);
    if (!tile) continue;
    // Several buttons on one world (tile rotations, resource types) need their
    // labels: a single hotspot would silently choose one of them.
    if (choices.length > 1) continue;
    const action = choices[0];
    const hotspot = document.createElement('button');
    hotspot.type = 'button';
    hotspot.className = `hotspot ${action.kind}${tile.empty ? ' empty' : ''}`;
    hotspot.dataset.position = position;
    hotspot.dataset.customId = action.button.custom_id;
    hotspot.dataset.messageId = action.message.id;
    hotspot.title = `${tile.label}: ${action.button.label || action.kind}`;
    hotspot.style.left = `${tile.x + 36}px`;
    hotspot.style.top = `${tile.y + 28}px`;
    hotspot.style.width = '273px';
    hotspot.style.height = '244px';
    const tag = document.createElement('span');
    tag.className = 'tag';
    tag.textContent = tile.empty
      ? `? ${position}`
      : action.kind === 'move' && action.to
        ? `Move → ${action.button.label || position}`
        : `${action.kind} ${tile.label}`;
    hotspot.appendChild(tag);
    hotspot.addEventListener('click', (event) => {
      event.stopPropagation();
      press(action.message.id, action.button.custom_id, hotspot);
    });
    el.overlay.appendChild(hotspot);
  }
  // Drag a ship from its origin onto a legal destination; clicking works the same.
  const destinations = actions.filter((action) => action.kind === 'move' && action.to);
  if (!destinations.length) return;
  const origin = destinations[0].button.custom_id.match(/_moveTo_(\d{3})/)[1];
  const originTile = byPosition.get(origin);
  if (!originTile) return;
  const token = document.createElement('div');
  token.className = 'drag-token';
  token.style.left = `${originTile.x + 172}px`;
  token.style.top = `${originTile.y + 150}px`;
  token.textContent = `⇢ ${destinations[0].ship}`;
  token.title = 'Drag onto a highlighted destination, or click the destination.';
  el.overlay.appendChild(token);
  bindDragToken(token, destinations);
}

function bindDragToken(token, destinations) {
  let start = null;
  token.addEventListener('pointerdown', (event) => {
    event.stopPropagation();
    const rect = el.viewport.getBoundingClientRect();
    start = { x: event.clientX, y: event.clientY, left: token.offsetLeft, top: token.offsetTop,
              rect, moved: false };
    token.setPointerCapture(event.pointerId);
  });
  token.addEventListener('pointermove', (event) => {
    if (!start) return;
    const dx = (event.clientX - start.x) / state.zoom;
    const dy = (event.clientY - start.y) / state.zoom;
    start.moved = start.moved || Math.abs(dx) + Math.abs(dy) > 3;
    token.style.left = `${start.left + dx}px`;
    token.style.top = `${start.top + dy}px`;
    const target = hotspotAt(event.clientX, event.clientY);
    document.querySelectorAll('.hotspot.drop-target').forEach((node) => node.classList.remove('drop-target'));
    if (target) target.classList.add('drop-target');
  });
  token.addEventListener('pointerup', (event) => {
    if (!start) return;
    const target = hotspotAt(event.clientX, event.clientY);
    token.style.left = `${start.left}px`;
    token.style.top = `${start.top}px`;
    document.querySelectorAll('.hotspot.drop-target').forEach((node) => node.classList.remove('drop-target'));
    start = null;
    if (target) {
      press(Number(target.dataset.messageId), target.dataset.customId, target);
    }
  });
  token.addEventListener('pointercancel', () => {
    if (start) {
      token.style.left = `${start.left}px`;
      token.style.top = `${start.top}px`;
    }
    start = null;
  });
}

function hotspotAt(clientX, clientY) {
  const rect = el.viewport.getBoundingClientRect();
  if (clientX < rect.left || clientX > rect.right || clientY < rect.top || clientY > rect.bottom) {
    return null;
  }
  const x = (clientX - rect.left - state.panX) / state.zoom;
  const y = (clientY - rect.top - state.panY) / state.zoom;
  return [...document.querySelectorAll('.hotspot')].find((node) =>
    x >= parseFloat(node.style.left) && x <= parseFloat(node.style.left) + parseFloat(node.style.width)
    && y >= parseFloat(node.style.top) && y <= parseFloat(node.style.top) + parseFloat(node.style.height)) || null;
}

function renderBoard(view) {
  if (state.boardVersion !== view.version) {
    const first = state.boardVersion === null;
    state.boardVersion = view.version;
    state.boardMeta = view.board_meta;
    state.fitPending = first;
    el.stage.style.width = `${view.board_meta.width}px`;
    el.stage.style.height = `${view.board_meta.height}px`;
    el.board.width = view.board_meta.width;
    el.board.height = view.board_meta.height;
    el.board.style.width = `${view.board_meta.width}px`;
    el.board.style.height = `${view.board_meta.height}px`;
    el.boardEmpty.classList.remove('hidden');
    el.boardNote.textContent = 'rendering…';
    el.board.onload = () => {
      el.boardEmpty.classList.add('hidden');
      el.boardNote.textContent = '';
      if (state.fitPending) { state.fitPending = false; fitBoard(); }
    };
    el.board.onerror = () => {
      el.boardEmpty.textContent = 'Board render failed — see the server log';
      el.boardNote.textContent = 'render failed';
    };
    el.board.src = view.board;
    if (el.board.complete && el.board.naturalWidth) {
      el.boardEmpty.classList.add('hidden');
      el.boardNote.textContent = '';
      if (state.fitPending) { state.fitPending = false; fitBoard(); }
    }
  }
  renderOverlay(view);
}

// -------------------------------------------------------------------- market
function trackLabel(track) {
  return { military: 'Military', grid: 'Grid', nano: 'Nano', any: 'Rare' }[track] || track;
}

function renderMarket(view) {
  const offers = view.tech_market || [];
  const choices = buttonById(view);
  const actionable = new Map();
  for (const [customId, entry] of choices) {
    const tech = techButton(customId);
    if (tech) actionable.set(tech.tech, entry);
  }
  if (!offers.length) {
    el.market.replaceChildren();
    el.marketNote.textContent = 'empty';
    return;
  }
  el.marketNote.textContent = view.you ? 'cost for you' : 'base costs';
  const byTrack = new Map();
  for (const offer of offers) {
    const track = offer.track || 'any';
    if (!byTrack.has(track)) byTrack.set(track, []);
    byTrack.get(track).push(offer);
  }
  const rows = [];
  for (const track of ['military', 'grid', 'nano', 'any']) {
    if (!byTrack.has(track)) continue;
    const row = document.createElement('div');
    row.className = 'track-row';
    row.innerHTML = `<div class="track-label ${track}">${trackLabel(track)}</div>`;
    const cards = document.createElement('div');
    cards.className = 'track-cards';
    for (const offer of byTrack.get(track)) {
      const entry = actionable.get(offer.id);
      const card = document.createElement('button');
      card.type = 'button';
      card.className = `tech-chip${entry ? ' playable' : ''}`;
      card.title = `${offer.name}${offer.description ? ` — ${offer.description}` : ''}`;
      card.dataset.tech = offer.id;
      const cost = offer.your_cost ?? offer.cost;
      card.innerHTML = `${offer.image
        ? `<img src="${offer.image}" alt="${escapeHtml(offer.name)}" loading="lazy">`
        : '<div class="no-art">◇</div>'}
        <span class="tc-name">${escapeHtml(offer.name)}</span>
        <span class="tc-cost">${cost ?? '?'}</span>`;
      if (entry) {
        card.addEventListener('click', () => press(entry.message.id, entry.button.custom_id, card));
      }
      cards.appendChild(card);
    }
    row.appendChild(cards);
    rows.push(row);
  }
  el.market.replaceChildren(...rows);
}

// ------------------------------------------------------------------- players
function techTracksHtml(player) {
  const rows = ['military', 'grid', 'nano'].map((track) => {
    const techs = player.techs?.[track] || [];
    const slots = [];
    for (let index = 0; index < 7; index += 1) {
      const tech = techs[index];
      slots.push(tech
        ? `<span class="tech-slot filled" title="${escapeHtml(tech.name)}">${
            tech.image ? `<img src="${tech.image}" alt="${escapeHtml(tech.name)}" loading="lazy">`
              : `<span class="initial">${escapeHtml((tech.name || '?').slice(0, 1))}</span>`}</span>`
        : '<span class="tech-slot"></span>');
    }
    return `<div class="tech-row ${track}"><span class="label">${track.slice(0, 3).toUpperCase()}</span>${slots.join('')}</div>`;
  });
  return rows.join('');
}

function blueprintHtml(blueprint) {
  const slots = blueprint.slots.map((slot) => {
    const part = slot.part || {};
    if (!part.id || part.id === 'empty') return '<span class="slot-empty"></span>';
    return `<span class="slot-img" title="${escapeHtml(part.name || part.id)}">${
      part.image ? `<img src="${part.image}" alt="${escapeHtml(part.name || part.id)}" loading="lazy">` : ''}</span>`;
  }).join('');
  const stats = blueprint.stats || {};
  const bits = [
    stats.range !== undefined ? `R${stats.range}` : null,
    stats.speed !== undefined ? `S${stats.speed}` : null,
    stats.energy !== undefined ? `E${stats.energy}` : null,
    stats.computer !== undefined ? `C${stats.computer}` : null,
    stats.hull !== undefined ? `H${stats.hull}` : null,
  ].filter(Boolean).map((text) => `<span>${text}</span>`).join('');
  return `<div class="ship-mini">
    <div class="ship-mini-head"><b>${escapeHtml(blueprint.ship)}</b><span>${
      stats.cost !== undefined ? stats.cost : ''}</span></div>
    <div class="slots">${slots}</div>
    <div class="ship-stats">${bits}</div>
  </div>`;
}

function playerHtml(player) {
  const actions = player.actions || {};
  const actionRows = ['build', 'move', 'research', 'upgrade', 'explore', 'influence'].map((key) =>
    `<span class="action-chip ${actions[key] ? 'on' : 'zero'}" title="${key}">
       <span>${key.slice(0, 3).toUpperCase()}</span>
       <b>${actions[key] ?? '—'}${
         player.counters?.[key] ? `<span class="counter">·${player.counters[key]}</span>` : ''}</b>
     </span>`).join('');
  const portrait = player.portrait
    ? `<img class="portrait" src="${player.portrait}" alt="${escapeHtml(player.faction_name || player.name)}">`
    : `<span class="portrait-fallback">${escapeHtml((player.faction_name || player.name || '?').slice(0, 1))}</span>`;
  const rep = (player.reputation || []).map((tile) => {
    const label = typeof tile === 'string' ? tile : `#${tile}`;
    return `<span class="rep-chip ${String(label).toLowerCase().includes('amb') ? 'amb' : ''}">${escapeHtml(String(label))}</span>`;
  }).join('');
  const owned = (player.owned_tiles || []).map((tile) =>
    `<b>${escapeHtml(tile.name || tile.position)}</b>`).join(' · ');
  const techs = player.techs || {};
  const counts = ['military', 'grid', 'nano'].map((track) =>
    `${track.slice(0, 3).toUpperCase()} ${(techs[track] || []).length}`).join(' · ');
  return `<article class="player ${player.is_you ? 'you' : ''} ${player.passed ? 'passed' : ''}">
    <div class="player-head">
      ${portrait}
      <div class="player-title">
        <b>${escapeHtml(player.name)}</b>
        <small>${escapeHtml(player.faction_name || player.color || '')} · ${escapeHtml(String(player.color || ''))}</small>
      </div>
      <div class="player-flags">
        <span class="mini ${player.is_you ? 'on' : ''}">${player.is_you ? 'you' : ''}</span>
        <span class="mini ${player.passed ? 'on' : ''}">${player.passed ? 'passed' : ''}</span>
      </div>
      <div class="vp" title="Public victory points">${player.points ?? '?'}</div>
    </div>
    <div class="resources">
      <span class="res money"><span class="dot"></span>${player.money ?? '?'}</span>
      <span class="res science"><span class="dot"></span>${player.science ?? '?'}</span>
      <span class="res materials"><span class="dot"></span>${player.materials ?? '?'}</span>
      <span class="res discs"><span class="dot"></span>${player.influence_discs ?? '?'}</span>
      <span class="res colony"><span class="dot"></span>${player.colony_ships ?? '?'}</span>
      ${player.disc_tiles ? `<span class="res points" title="Discovery tiles kept for points"><span class="dot"></span>${player.disc_tiles}</span>` : ''}
    </div>
    <div class="player-grid">
      <div>
        <div class="panel-label">Actions</div>
        <div class="action-chips">${actionRows}</div>
        <div class="panel-label" style="margin-top:7px">Income · upkeep</div>
        <div class="note">+${player.income?.money ?? '?'}◉ +${player.income?.science ?? '?'}◈ +${player.income?.materials ?? '?'}▣ · upkeep ${player.upkeep ?? '?'}</div>
        <div class="panel-label" style="margin-top:7px">Technology · ${counts}</div>
        <div class="tech-tracks">${techTracksHtml(player)}</div>
      </div>
      <div>
        <div class="panel-label">Blueprints</div>
        <div class="blueprints">${(player.blueprints || []).map(blueprintHtml).join('')}</div>
      </div>
    </div>
    ${rep ? `<div class="reputation">${rep}</div>` : ''}
    ${owned ? `<div class="owned">Systems: ${owned}</div>` : ''}
  </article>`;
}

function renderPlayers(view) {
  const players = view.game.players || [];
  el.players.innerHTML = players.map(playerHtml).join('');
  el.playersNote.textContent = `${players.length} seats`;
  [...el.players.querySelectorAll('.player')].forEach((node, index) => {
    const head = node.querySelector('.player-head');
    head.title = 'Open faction reference';
    head.addEventListener('click', () => {
      state.factionPlayer = players[index];
      renderFaction();
      el.factionDialog.showModal();
    });
  });
}

// ---------------------------------------------------------------------- dock
function techChoices(message, choices) {
  const techs = [];
  const other = [];
  for (const button of message.buttons || []) {
    const target = techButton(button.custom_id || '');
    if (!target) { other.push(button); continue; }
    techs.push({ button, target });
  }
  if (!techs.length) return null;
  const groups = new Map();
  for (const entry of techs) {
    const track = entry.target.track;
    if (!groups.has(track)) groups.set(track, []);
    groups.get(track).push(entry);
  }
  const sections = [];
  for (const track of ['military', 'grid', 'nano', 'any']) {
    if (!groups.has(track)) continue;
    const cards = groups.get(track).map(({ button, target }) => {
      const info = state.catalog.techs?.[target.tech] || { name: button.label, image: null };
      const cost = (button.label || '').match(/\((\d+)\)/);
      return `<button type="button" class="tech-card ${track}" data-custom="${escapeHtml(button.custom_id)}">
        ${info.image ? `<img src="${info.image}" alt="${escapeHtml(info.name)}" loading="lazy">` : '<div class="no-art">◇</div>'}
        <span class="name">${escapeHtml(info.name)}</span>
        <span class="cost-line">${cost ? cost[1] : info.cost ?? ''}</span>
      </button>`;
    }).join('');
    sections.push(`<div class="subgroup"><div class="subgroup-title">${trackLabel(track)}</div>
      <div class="tech-choices">${cards}</div></div>`);
  }
  return { html: sections.join(''), other };
}
function partChoices(message) {
  const groups = new Map();
  const other = [];
  let count = 0;
  for (const button of message.buttons || []) {
    const target = partButton(button.custom_id || '');
    if (!target) { other.push(button); continue; }
    count += 1;
    if (target.kind === 'ship') {
      if (!groups.has('Upgrade which ship')) groups.set('Upgrade which ship', []);
      groups.get('Upgrade which ship').push({ button, target });
      continue;
    }
    const part = state.catalog.parts?.[target.part] || { name: target.part, image: null };
    const title = target.kind === 'old' ? `Slot ${target.slot} · replace ${part.name}`
      : `Install ${part.name}`;
    if (!groups.has(target.ship)) groups.set(target.ship, []);
    groups.get(target.ship).push({ button, target, part, title });
  }
  if (!count) return null;
  const sections = [];
  for (const [group, entries] of groups) {
    const cards = entries.map(({ button, target, part, title }) => {
      if (target.kind === 'ship') {
        return `<button type="button" class="ship-card" data-custom="${escapeHtml(button.custom_id)}">
          <span class="name">${escapeHtml(button.label || target.ship)}</span>
          <span class="meta">blueprint</span></button>`;
      }
      const info = part || {};
      const bits = [
        info.nrg_src ? `⚡+${info.nrg_src}` : null,
        info.nrg_use ? `⚡−${info.nrg_use}` : null,
        info.range ? `R${info.range}` : null,
        info.speed ? `S${info.speed}` : null,
        info.comp ? `C${info.comp}` : null,
        info.shield ? `Sh${info.shield}` : null,
        info.hull ? `H${info.hull}` : null,
      ].filter(Boolean).map((text) => `<b>${text}</b>`).join(' ');
      return `<button type="button" class="part-card" data-custom="${escapeHtml(button.custom_id)}"
        title="${escapeHtml([title, info.description].filter(Boolean).join(' — '))}">
        ${info.image ? `<img src="${info.image}" alt="${escapeHtml(info.name)}" loading="lazy">` : '<div class="no-art">◇</div>'}
        <span class="name">${escapeHtml(info.name || target.part)}</span>
        <span class="meta">${target.kind === 'old' ? `slot ${target.slot}` : 'install'}</span>
        <span class="statline">${bits}</span>
      </button>`;
    }).join('');
    sections.push(`<div class="subgroup"><div class="subgroup-title">${escapeHtml(group)}</div>
      <div class="part-choices">${cards}</div></div>`);
  }
  return { html: sections.join(''), other };
}

function genericChoices(buttons, message) {
  const wrap = document.createElement('div');
  wrap.className = 'choices';
  for (const button of buttons) {
    if (button.url) {
      const link = document.createElement('a');
      link.href = button.url;
      link.target = '_blank';
      link.rel = 'noopener';
      link.className = 'choice';
      link.textContent = button.label || 'link';
      wrap.appendChild(link);
      continue;
    }
    const node = document.createElement('button');
    node.type = 'button';
    node.className = `choice s${[1, 2, 3, 4].includes(button.style) ? button.style : 2}`;
    node.textContent = button.label || button.custom_id || '?';
    node.title = button.custom_id || '';
    node.disabled = !!button.disabled;
    node.addEventListener('click', () => press(message.id, button.custom_id, node));
    wrap.appendChild(node);
  }
  return wrap;
}

function promptCard(message, index) {
  const card = document.createElement('section');
  card.className = `prompt${message.private ? ' private' : ''}${isCombat(message) ? ' combat' : ''}${index > 0 ? ' older' : ''}`;
  card.dataset.messageId = message.id;
  const tags = [];
  if (index === 0) tags.push('<span class="tag turn">current</span>');
  if (message.private) tags.push('<span class="tag private">private</span>');
  if (isCombat(message)) tags.push('<span class="tag combat">battle</span>');
  const head = document.createElement('div');
  head.className = 'prompt-head';
  head.innerHTML = `${tags.join('')}<span class="room">${escapeHtml(
    isCombat(message) ? message.room.replace(/^aeb\d+-/, '') : roomName(message.room))}</span>
    <span>#${message.id}</span>`;
  card.appendChild(head);

  const body = document.createElement('div');
  body.className = 'prompt-body';
  const content = document.createElement('div');
  content.className = 'content';
  content.innerHTML = bodyHtml(message.content);
  body.appendChild(content);
  for (const attachment of message.attachments || []) {
    const image = document.createElement('img');
    image.className = 'attachment';
    image.src = attachment.url;
    image.alt = attachment.name || '';
    image.loading = 'lazy';
    body.appendChild(image);
  }

  const choices = buttonById({ pending: [message] });
  const enriched = techChoices(message) || partChoices(message);
  if (enriched) {
    const holder = document.createElement('div');
    holder.innerHTML = enriched.html;
    body.appendChild(holder);
    for (const node of holder.querySelectorAll('[data-custom]')) {
      node.addEventListener('click', () => {
        const entry = choices.get(node.dataset.custom);
        if (entry) press(entry.message.id, entry.button.custom_id, node);
      });
    }
    // Buttons already drawn as cards must not also appear as plain choices.
    body.appendChild(genericChoices(enriched.other, message));
  } else {
    const tiles = (message.buttons || []).map((button) => ({ button, target: tileAction(button.custom_id || '') }))
      .filter((entry) => entry.target);
    if (tiles.length) {
      const row = document.createElement('div');
      row.className = 'tile-choices';
      for (const { button, target } of tiles) {
        const chip = document.createElement('button');
        chip.type = 'button';
        chip.className = 'tile-chip';
        chip.textContent = `${button.label || target.position}`;
        chip.title = 'Highlighted on the galaxy board';
        chip.addEventListener('click', () => press(message.id, button.custom_id, chip));
        row.appendChild(chip);
      }
      body.appendChild(row);
    }
    const plain = (message.buttons || []).filter((button) => !tileAction(button.custom_id || ''));
    body.appendChild(genericChoices(plain, message));
  }
  card.appendChild(body);
  return card;
}

function waitingCard(view) {
  const active = view.game.active || [];
  const names = active.map((color) => {
    const player = (view.game.players || []).find((row) => row.color === color);
    return player ? player.name : color;
  });
  const card = document.createElement('div');
  card.className = 'waiting';
  const you = view.you;
  if (view.game.ended) {
    const rows = (view.result || []).map((row, index) => `
      <div class="final-row ${index === 0 ? 'winner' : ''}">
        <span class="final-rank">${index + 1}</span>
        <span class="final-name">${escapeHtml(row.name)}</span>
        <span class="muted">${escapeHtml(row.faction_name || row.color || '')}</span>
        <b>${row.points ?? '?'}</b>
      </div>`).join('');
    card.classList.add('final');
    card.innerHTML = `<b>The game has ended.</b>
      <div class="final-list">${rows}</div>
      <div class="row">The full combat and action record is in History.</div>`;
    return card;
  }
  if (!view.seat) {
    card.innerHTML = '<b>Spectator.</b> Choose a seat to play. The history records every action.';
    return card;
  }
  if (you && you.is_your_turn) {
    card.innerHTML = '<b>Your move.</b> Pick an action from your turn menu.';
    const row = document.createElement('div');
    row.className = 'row';
    const menu = document.createElement('button');
    menu.type = 'button';
    menu.className = 'primary';
    menu.textContent = 'Show my turn menu';
    menu.addEventListener('click', () => openTurnMenu());
    row.appendChild(menu);
    card.appendChild(row);
    return card;
  }
  card.innerHTML = `<b>${names.length ? `${escapeHtml(names.join(', '))} ${names.length === 1 ? 'is' : 'are'}` : 'Nobody is'} acting.</b>
    <div class="row">New prompts appear here; finished actions move to History.</div>`;
  return card;
}

const UTILITY_BUTTONS = /(^|_)(refreshImage|removeUnits|showGame|showReputation|undoLastTurn)(_|$)/;

function isUtilityPrompt(message) {
  const buttons = (message.buttons || []).filter((button) => button.custom_id);
  return buttons.length > 0 && buttons.every((button) => UTILITY_BUTTONS.test(button.custom_id));
}

const NAV_BUTTONS = /(^|_)(finishAction|restartTurn|deleteMsg|showGame|showReputation|startMinorRelations|startDiplomaticRelations|undoLastTurn|refreshCombatPrompt|refreshImage)(_|$)/;

function isChoicePrompt(message) {
  const buttons = message.buttons || [];
  return buttons.some((button) => button.custom_id && !NAV_BUTTONS.test(button.custom_id));
}

function battlePanel(room, messages, view) {
  const section = document.createElement('section');
  section.className = 'battle-room';
  const log = (view.history || []).filter((message) => message.room === room
    && (message.content || (message.attachments || []).length))
    .sort((a, b) => a.id - b.id);
  section.innerHTML = `<header><span class="battle-mark">⚔</span>
    <div><b>${escapeHtml(room.replace(/^aeb\d+-/, ''))}</b>
    <small>${messages.length} open order${messages.length === 1 ? '' : 's'} · room ${escapeHtml(room)}</small></div></header>`;
  messages.sort((a, b) => a.id - b.id).forEach((message, index) =>
    section.appendChild(promptCard(message, index)));
  if (log.length) {
    const details = document.createElement('details');
    details.className = 'battle-log';
    details.innerHTML = `<summary>Battle log · ${log.length} records</summary>`;
    const list = document.createElement('div');
    list.className = 'history-list';
    list.append(...log.map(historyItem));
    details.appendChild(list);
    section.appendChild(details);
  }
  return section;
}

function renderDock(view) {
  el.dock.replaceChildren();
  const pending = [...(view.pending || [])];
  if (!pending.length) {
    el.dock.appendChild(waitingCard(view));
    return;
  }
  // The engine sometimes offers the same menu twice (a second research pick, for
  // example). Keep the newest copy; the other is still in the feed if it becomes live.
  const seen = new Map();
  for (const message of pending) {
    if (isUtilityPrompt(message)) continue;
    const techIds = (message.buttons || []).map((button) => techButton(button.custom_id || ''))
      .filter(Boolean).map((entry) => entry.tech).sort();
    const key = techIds.length
      ? `tech:${techIds.join(',')}`
      : (message.buttons || []).map((button) => button.custom_id).sort().join('|');
    if (key) seen.set(key, message);
  }
  const unique = [...seen.values()];
  // Every battle keeps its own room: its orders, and its own log.
  const rooms = new Map();
  for (const message of unique.filter(isCombat)) {
    if (!rooms.has(message.room)) rooms.set(message.room, []);
    rooms.get(message.room).push(message);
  }
  for (const [room, messages] of rooms) {
    el.dock.appendChild(battlePanel(room, messages, view));
  }
  const table = unique.filter((message) => !isCombat(message));
  const primary = table.filter(isChoicePrompt).sort((a, b) => b.id - a.id);
  const secondary = table.filter((message) => !isChoicePrompt(message)).sort((a, b) => b.id - a.id);
  [...primary, ...secondary].forEach((message, index) => el.dock.appendChild(promptCard(message, index)));
}

// -------------------------------------------------------------------- history
function historyItem(message) {
  const wrap = document.createElement('article');
  wrap.className = 'history-item';
  const meta = document.createElement('div');
  meta.className = 'history-meta';
  const when = message.created ? new Date(message.created * 1000).toLocaleTimeString([], {
    hour: '2-digit', minute: '2-digit' }) : '';
  meta.innerHTML = `<span class="room">${escapeHtml(roomName(message.room))}</span>
    <span>#${message.id}</span><span>${when}</span>
    ${message.private ? '<span>private</span>' : ''}
    ${message.deleted || (message.buttons && message.buttons.length === 0 && message.content) ? '<span class="used">resolved</span>' : ''}
    ${message.for_you === false ? '<span>another seat</span>' : ''}`;
  wrap.appendChild(meta);
  if (message.content) {
    const body = document.createElement('div');
    body.className = 'history-content';
    body.innerHTML = bodyHtml(message.content);
    wrap.appendChild(body);
  }
  for (const attachment of message.attachments || []) {
    const image = document.createElement('img');
    image.className = 'attachment';
    image.src = attachment.url;
    image.alt = attachment.name || '';
    image.loading = 'lazy';
    wrap.appendChild(image);
  }
  return wrap;
}

async function loadHistory(reset = false) {
  if (!state.gameId) return;
  try {
    const before = reset || !state.history.length ? null : state.history[state.history.length - 1].id;
    const page = await api.history(state.gameId, state.seat, before);
    if (reset) state.history = [];
    state.history = state.history.concat(page.messages || []);
    state.historyHasMore = !!page.has_more;
    renderHistory();
  } catch (error) {
    showToast(`cannot load history: ${error}`, true);
  }
}

function renderHistory() {
  const rooms = [...new Set(state.history.map((message) => message.room))];
  const selected = state.historyRoom;
  el.historyRoom.replaceChildren(...[['', 'All rooms'], ...rooms.map((room) => [room, roomName(room)])]
    .map(([value, label]) => {
      const option = document.createElement('option');
      option.value = value;
      option.textContent = label;
      return option;
    }));
  el.historyRoom.value = rooms.includes(selected) ? selected : '';
  const visible = state.history
    .filter((message) => !state.historyRoom || message.room === state.historyRoom)
    .filter((message) => message.content || (message.attachments || []).length);
  el.historyList.replaceChildren(...visible.map(historyItem));
  el.historyNote.textContent = `${visible.length}/${state.history.length} records`
    + ' · unresolved prompts stay in the action dock';
  el.historyMore.classList.toggle('hidden', !state.historyHasMore);
  if (!state.history.length) {
    el.historyList.innerHTML = '<p class="note">No history yet.</p>';
  }
}

// -------------------------------------------------------------------- faction
function prettifyAbility(name) {
  return name.replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function renderFaction() {
  const view = state.view;
  if (!view) return;
  const player = state.factionPlayer || view.you
    || (view.game.players || []).find((row) => row.is_you)
    || (view.game.players || [])[0];
  if (!player || !player.faction) {
    el.factionTitle.textContent = 'Faction';
    el.factionSub.textContent = 'Choose a seat to see its faction.';
    el.factionBody.innerHTML = '';
    return;
  }
  const faction = player.faction;
  el.factionTitle.textContent = faction.name;
  el.factionSub.textContent = `${player.name} · ${player.color || ''}`;
  const start = faction.start || {};
  const facts = [
    ['Money', start.money], ['Science', start.science], ['Materials', start.materials],
    ['Colony ships', start.colony_ships], ['Trade', start.trade_value],
    ['Explore', start.explore_apt], ['Research', start.research_apt], ['Build', start.build_apt],
    ['Upgrade', start.upgrade_apt], ['Move', start.move_apt], ['Influence', start.influence_apt],
  ].filter(([, value]) => value !== null && value !== undefined)
    .map(([label, value]) => `<span class="fact">${label} <b>${value}</b></span>`).join('');
  const abilities = (faction.abilities || []).map((ability) =>
    `<div class="ability"><b>${escapeHtml(prettifyAbility(ability))}</b> — the full rule text is printed on the faction board below.</div>`).join('');
  el.factionBody.innerHTML = `<div class="faction-hero">
      ${faction.image ? `<img id="faction-image" src="${faction.image}" alt="${escapeHtml(faction.name)} board">` : ''}
      <div class="faction-facts">
        <div><div class="panel-label">Starting setup</div><div class="fact-row">${facts}</div></div>
        <div><div class="panel-label">Abilities</div><div class="ability-list">${abilities || '<span class="note">No special abilities.</span>'}</div></div>
        <p class="note">The faction board is the rules reference; click it to enlarge.</p>
      </div>
    </div>`;
  const image = document.getElementById('faction-image');
  if (image) {
    image.addEventListener('click', () => {
      el.zoomImage.src = image.src;
      el.zoomDialog.showModal();
    });
  }
}

// ---------------------------------------------------------------------- press
async function press(messageId, customId, node) {
  if (!customId || state.rendering) return;
  state.rendering = true;
  if (node) node.disabled = true;
  showToast('Resolving…');
  try {
    const view = await api.press(state.gameId, state.seat, customId, messageId);
    if (view.error) showToast(view.error, true);
    else if (view.messages) showToast('Done');
    render(view, true);
    if (el.historyDialog.open) await loadHistory(true);
  } catch (error) {
    showToast(`press failed: ${error}`, true);
  } finally {
    state.rendering = false;
    if (node && node.isConnected) node.disabled = false;
  }
}

async function openTurnMenu() {
  if (!state.seat) return;
  try {
    const view = await api.turnMenu(state.gameId, state.seat);
    if (view.error) showToast(view.error, true);
    render(view, true);
  } catch (error) {
    showToast(`cannot open turn menu: ${error}`, true);
  }
}

// ---------------------------------------------------------------------- seats
function renderSeats(view) {
  const options = view.game.players || [];
  const wanted = [['', 'Spectator'], ...options.map((player) => [player.id,
    `${player.name}${player.color ? ` (${player.color})` : ''}`])];
  const current = viewedSeat(view);
  const key = options.map((player) => player.id).join(',');
  if (el.seat.dataset.for === key) {
    if (el.seat.value !== current) el.seat.value = current;
    return;
  }
  el.seat.dataset.for = key;
  el.seat.replaceChildren(...wanted.map(([value, label]) => {
    const option = document.createElement('option');
    option.value = value;
    option.textContent = label;
    return option;
  }));
  el.seat.value = current;
}

function viewedSeat(view) {
  return view.seat || '';
}

// --------------------------------------------------------------------- render
function viewSignature(view) {
  return JSON.stringify({
    seat: view.seat,
    version: view.version,
    pending: view.pending,
    game: view.game,
    you: view.you,
    market: view.tech_market,
    mirror: view.mirror_to_discord,
    board: view.board_meta,
  });
}

function render(view, force = false) {
  const nextKey = viewSignature(view);
  if (!force && nextKey === state.lastKey) return;
  state.view = view;
  if (view.error) showToast(view.error, true);
  const active = view.game.active || [];
  el.round.textContent = view.game.ended ? 'Final scores'
    : `Round ${view.game.round ?? '?'} / ${view.game.round_max ?? 8}`;
  const activeNames = active.map((color) => {
    const player = (view.game.players || []).find((row) => row.color === color);
    return player ? player.name : color;
  });
  el.turn.textContent = view.game.ended ? 'Game over'
    : activeNames.length ? `Active: ${activeNames.join(', ')}` : 'No active seat';
  el.turn.classList.toggle('pass', !activeNames.length);
  el.boardNote.classList.toggle('hidden', false);
  renderSeats(view);
  el.mirror.checked = !!view.mirror_to_discord;
  const hasPrompt = (view.pending || []).length > 0;
  el.turnMenu.classList.toggle('hidden', view.game.ended || !(view.you && !hasPrompt));
  el.boardHint.textContent = view.seat
    ? `Drag to pan · scroll to zoom · highlighted worlds are choices`
    : 'Drag to pan · scroll to zoom';

  renderBoard(view);
  renderMarket(view);
  renderPlayers(view);
  renderDock(view);
  if (el.factionDialog.open) renderFaction();
  state.lastKey = nextKey;
}

async function loadView() {
  if (!state.gameId) return;
  try {
    const view = await api.view(state.gameId, state.seat);
    if (view.error) { showToast(view.error, true); return; }
    render(view);
  } catch (error) {
    showToast(`cannot load game: ${error}`, true);
  }
}

// ----------------------------------------------------------------------- boot
async function loadGames() {
  const games = await api.games();
  const stored = localStorage.getItem('eclipse-game');
  state.gameId = games.some((game) => game.id === stored) ? stored : (games[0] && games[0].id);
  el.game.replaceChildren(...games.map((game) => {
    const option = document.createElement('option');
    option.value = game.id;
    option.textContent = `${game.id} · round ${game.round ?? '?'} · ${game.players.join(', ')}`;
    return option;
  }));
  if (el.game.value !== state.gameId) el.game.value = state.gameId;
  const storedSeat = localStorage.getItem(`eclipse-seat-${state.gameId}`);
  state.seat = storedSeat || '';
}

function bind() {
  el.game.addEventListener('change', async () => {
    state.gameId = el.game.value;
    state.boardVersion = null;
    state.lastKey = null;
    localStorage.setItem('eclipse-game', state.gameId);
    state.seat = localStorage.getItem(`eclipse-seat-${state.gameId}`) || '';
    state.history = [];
    state.historyLoaded = false;
    state.factionPlayer = null;
    await loadView();
  });

  el.seat.addEventListener('change', async () => {
    state.seat = el.seat.value;
    localStorage.setItem(`eclipse-seat-${state.gameId}`, state.seat);
    state.lastKey = null;
    state.history = [];
    state.historyLoaded = false;
    state.factionPlayer = null;
    await loadView();
  });

  el.turnMenu.addEventListener('click', openTurnMenu);

  el.mirror.addEventListener('change', async () => {
    try {
      render(await api.mirror(state.gameId, state.seat, el.mirror.checked));
    } catch (error) {
      showToast(`cannot change mirror: ${error}`, true);
    }
  });

  document.getElementById('open-history').addEventListener('click', async () => {
    el.historyDialog.showModal();
    state.history = [];
    state.historyRoom = '';
    await loadHistory(true);
  });
  el.historyMore.addEventListener('click', () => loadHistory(false));
  el.historyRoom.addEventListener('change', () => {
    state.historyRoom = el.historyRoom.value;
    renderHistory();
  });

  document.getElementById('open-faction').addEventListener('click', () => {
    state.factionPlayer = null;
    renderFaction();
    el.factionDialog.showModal();
  });

  document.querySelectorAll('[data-close]').forEach((button) => {
    button.addEventListener('click', () => closeDialog(button.dataset.close));
  });
  [el.historyDialog, el.factionDialog, el.zoomDialog].forEach((dialog) => {
    dialog.addEventListener('click', (event) => {
      if (event.target === dialog) dialog.close();
    });
  });

  window.addEventListener('resize', () => {
    if (state.fitPending) fitBoard();
  });
  bindBoardPan();
}

async function main() {
  bind();
  try {
    state.catalog = await api.catalog();
  } catch (error) {
    showToast(`cannot load catalog: ${error}`, true);
  }
  await loadGames();
  const fromUrl = new URLSearchParams(location.search).get('seat');
  if (fromUrl) state.seat = fromUrl;
  await loadView();
  setInterval(() => {
    if (!state.rendering) loadView();
  }, 1500);
}

main();
