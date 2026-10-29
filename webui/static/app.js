// One page, one API client. Keep every HTTP call in this file's `api` object so the
// whole thing can be lifted into a Vue app when it moves into the OBG repo.
const api = {
  async marketLayout(gameId) {
    const response = await fetch(`/api/games/${gameId}/market-layout`);
    if (!response.ok) throw new Error('Could not load technology targets');
    return response.json();
  },
  async games() {
    const response = await fetch('/api/games');
    const data = await response.json();
    state.isDevMode = !!data.can_create;
    document.getElementById('new-game').classList.toggle('hidden', !data.can_create);
    return data.games || [];
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
  isDevMode: false,
  collapsedBoards: new Set(),
  seat: '',
  view: null,
  catalog: { techs: {}, parts: {} },
  boardVersion: null,
  boardLoaded: false,
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
  previewKey: null,
  previewRotation: 0,
  previewActions: [],
  previewRotations: [],
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
    .replace(/&lt;(a?):([\w]+):(\d+)&gt;/g, (_m, animated, name, id) => {
      const source = /^dice_(ion|plasma|antimatter|soliton|rift)_[1-6]$/.test(name)
        ? `/art/components/dice_faces/${name}.png`
        : `https://cdn.discordapp.com/emojis/${id}.${animated ? 'gif' : 'png'}`;
      return `<img class="emoji" alt=":${name}:" loading="lazy" src="${source}">`;
    });
}

function signed(value) {
  if (value === null || value === undefined) return '?';
  return value > 0 ? `+${value}` : `${value}`;
}

function roomName(room) {
  if (!room) return 'table';
  return room.replace(/^aeb\d+-?/, '').replace(/-actions$/, '') || 'table';
}

function selectedBattle(view) {
  return (view.battles || []).find((battle) =>
    location.hash === `#room=${encodeURIComponent(battle.room)}`);
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

const SHIP_SHORT = {
  interceptor: 'int', cruiser: 'cru', dreadnought: 'drd', dread: 'drd',
  starbase: 'sb', orbital: 'orb', monolith: 'mon', int: 'int', cru: 'cru',
  drd: 'drd', sb: 'sb', orb: 'orb', mon: 'mon',
};

function shipClass(name) {
  return SHIP_SHORT[name] || name;
}

// A custom id that names a board object becomes part of the board, not a text
// button. Everything else stays a normal choice in the dock. The engine still
// owns legality: the object only carries the button it was offered.
function objectAction(customId) {
  let match;
  if ((match = customId.match(/_moveFrom_(\d{3}[a-z]?)/))) {
    return { kind: 'move-from', tile: match[1] };
  }
  if ((match = customId.match(/_moveThisShip_(\d{3}[a-z]?)_([a-z]+)_/))) {
    return { kind: 'move-ship', tile: match[1], ship: shipClass(match[2]) };
  }
  if ((match = customId.match(/_moveTo_(\d{3}[a-z]?)_([a-z]+)_(\d{3}[a-z]?)/))) {
    return { kind: 'move-dest', from: match[1], ship: shipClass(match[2]), tile: match[3] };
  }
  if ((match = customId.match(/_moveQueueContinue_(\d{3}[a-z]?)_([a-z]+)_(\d{3}[a-z]?)_/))) {
    return { kind: 'move-dest', from: match[1], ship: shipClass(match[2]), tile: match[3],
             queue: true };
  }
  if ((match = customId.match(/_moveQueue(?:Add|Reset|Done)_(\d{3}[a-z]?)_([a-z]+)/))) {
    return { kind: 'move-queue', tile: match[1], ship: shipClass(match[2]) };
  }
  if ((match = customId.match(/_exploreTile_(\d{3})/))) {
    return { kind: 'explore', tile: match[1] };
  }
  if ((match = customId.match(/_placeTile_(\d{3})_([a-z0-9]+)_(\d+)/))) {
    return { kind: 'explore-place', tile: match[1], sector: match[2], rotation: Number(match[3]) };
  }
  if ((match = customId.match(/_placeWarpPortal_(\d{3})/))) {
    return { kind: 'explore', tile: match[1] };
  }
  if ((match = customId.match(/_addInfluenceFinish_(\d{3})/))) {
    return { kind: 'influence-add', tile: match[1] };
  }
  if ((match = customId.match(/_removeInfluenceFinish_(\d{3})/))) {
    return { kind: 'influence-remove', tile: match[1] };
  }
  if ((match = customId.match(/_fillPopulation_(\d{3})_([a-z]+)_(\d+)(?:_([a-z]+))?/))) {
    return { kind: 'population', tile: match[1], square: match[2], index: Number(match[3]),
             cube: match[4] };
  }
  if ((match = customId.match(/_ancientsCube_([a-z]+)_(\d{3})/))) {
    return { kind: 'population', tile: match[2], cube: match[1], disc: true };
  }
  if ((match = customId.match(/_buildIn_(\d{3})/))) {
    return { kind: 'build-tile', tile: match[1] };
  }
  if ((match = customId.match(/_buildShip_([^_]+)_(\d+)_(\d{3})_([A-Za-z]+)/))) {
    return { kind: 'build-unit', tile: match[3], ship: match[4], cost: Number(match[2]) };
  }
  if ((match = customId.match(/_upgradeShip_(\d+)_([a-z]+)_/))) {
    return { kind: 'upgrade-ship', ship: shipClass(match[2]) };
  }
  if ((match = customId.match(/_selectOldPart_(\d+)_([a-z]+)_([a-z0-9]+)_([^_]+)_(\d+)/))) {
    return { kind: 'upgrade-slot', ship: shipClass(match[2]), slot: Number(match[5]) };
  }
  if ((match = customId.match(/_assignHitTo_(\d{3}[a-z]?)_([a-z]+)_([a-z0-9-]+)_(\d+)_(\d+)/))) {
    return { kind: 'combat-hit', tile: match[1], unit: match[3] };
  }
  if ((match = customId.match(/_removeThisUnit_(\d{3}[a-z]?)_([a-z0-9-]+)/))) {
    return { kind: 'combat-remove', tile: match[1], unit: match[2] };
  }
  if ((match = customId.match(/_rollDice_(\d{3}[a-z]?)_/))) {
    return { kind: 'combat-roll', tile: match[1] };
  }
  if ((match = customId.match(/_ghostsRetreatTo_\d{3}[a-z]?_[a-z]+_\d+_(\d{3}[a-z]?)/))) {
    return { kind: 'retreat', tile: match[1] };
  }
  if ((match = customId.match(/_finishRetreatingUnits_\d{3}[a-z]?_[a-z]+_\d+_(\d{3}[a-z]?)/))) {
    return { kind: 'retreat', tile: match[1] };
  }
  if ((match = customId.match(/_phaseBombing_(\d{3}[a-z]?)_/))) {
    return { kind: 'combat-roll', tile: match[1] };
  }
  return null;
}

const DISCOVERY_RE = /_(usedDiscForAbility|selectDiscTile)_([a-z0-9]+)_(\d{3})/;

function discoveryChoice(customId) {
  const match = customId.match(DISCOVERY_RE);
  if (!match) return null;
  return { action: match[1], disc: match[2], tile: match[3] };
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
  // Labels and hit rings keep a usable screen size when the whole map is fitted.
  el.stage.style.setProperty('--ui', String(Math.min(3, 1 / state.zoom)));
  el.stage.style.setProperty('--ui-piece', String(Math.min(1.8, 1 / state.zoom)));
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
    if (event.target.closest('.drag-token') || event.target.closest('.hotspot')
        || event.target.closest('.piece') || event.target.closest('.move-count')
        || event.target.closest('.tile-preview')) return;
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
  let lastWheelTime = -Infinity;
  let isMapScroll = false;
  document.addEventListener('wheel', (event) => {
    const now = performance.now();
    // Keep a page scroll on the page when it brings the map under the pointer.
    if (now - lastWheelTime > 250) isMapScroll = el.viewport.contains(event.target);
    lastWheelTime = now;
  }, { capture: true, passive: true });
  el.viewport.addEventListener('wheel', (event) => {
    if (!isMapScroll) return;
    event.preventDefault();
    zoomAt(event.deltaY < 0 ? 1.12 : 1 / 1.12, event.clientX, event.clientY);
  }, { passive: false });
  document.getElementById('zoom-in').addEventListener('click', () => zoomAt(1.25));
  document.getElementById('zoom-out').addEventListener('click', () => zoomAt(1 / 1.25));
  document.getElementById('zoom-fit').addEventListener('click', fitBoard);
}

const PIECE_COLORS = {
  blue: '#6cb8ff', red: '#ff7b7b', green: '#6fd39a', yellow: '#f0c96b',
  purple: '#c48ef0', black: '#c9d3df', white: '#ffffff', ai: '#ff9d5c',
};

const TILE_PRIORITY = ['explore', 'influence-add', 'influence-remove', 'build-tile',
  'move-dest', 'retreat', 'combat-roll', 'population'];

const OBJECT_LABEL = {
  explore: (tile) => (tile.empty ? `Explore ${tile.position}` : `Explore ${tile.label}`),
  'influence-add': () => 'Place influence disc',
  'influence-remove': () => 'Remove influence disc',
  'build-tile': () => 'Build here',
  'move-dest': () => 'Move here',
  retreat: () => 'Retreat here',
  'combat-roll': () => 'Roll dice here',
  population: () => 'Place population',
};

function spatialActions(view) {
  const actions = [];
  const seen = new Set();
  for (const message of view.pending || []) {
    for (const button of message.buttons || []) {
      const customId = button.custom_id || '';
      const target = objectAction(customId);
      if (!target || seen.has(customId)) continue;
      seen.add(customId);
      actions.push({ ...target, button, message });
    }
  }
  return actions;
}

function pieceIndex(view) {
  const index = new Map();
  for (const piece of view.pieces || []) {
    if (!index.has(piece.position)) index.set(piece.position, []);
    index.get(piece.position).push(piece);
  }
  return index;
}

function tileLabel(tile) {
  return tile.empty ? `unexplored ${tile.position}` : tile.label || tile.position;
}

function pressNode(node, action, ship = null) {
  node.dataset.position = action.tile || '';
  node.dataset.customId = action.button.custom_id;
  node.dataset.messageId = action.message.id;
  const select = async () => {
    await press(action.message.id, action.button.custom_id, node);
    if (action.kind === 'move-from' && ship) {
      const next = spatialActions(state.view).find((entry) =>
        entry.kind === 'move-ship' && entry.tile === action.tile && entry.ship === ship);
      if (next) await press(next.message.id, next.button.custom_id, null);
    }
  };
  let dragged = false;
  if (['move-from', 'move-ship'].includes(action.kind)) {
    node.addEventListener('pointerdown', (event) => {
      const start = { x: event.clientX, y: event.clientY };
      dragged = false;
      window.addEventListener('pointerup', async (end) => {
        dragged = Math.hypot(end.clientX - start.x, end.clientY - start.y) > 5;
        if (!dragged) return;
        await select();
        const destination = hotspotAt(end.clientX, end.clientY, '.hotspot.move-dest');
        if (destination) await press(Number(destination.dataset.messageId), destination.dataset.customId, destination);
      }, { once: true });
    });
  }
  node.addEventListener('click', (event) => {
    event.stopPropagation();
    if (!dragged) select();
  });
}

function renderOverlay(view) {
  const meta = state.boardMeta;
  el.overlay.replaceChildren();
  if (!meta || !meta.tiles) return;
  const tiles = new Map(meta.tiles.map((tile) => [tile.position, tile]));
  const subsectors = new Map((meta.subsectors || []).map((tile) => [tile.position, tile]));
  const targetTile = (position) => tiles.get(position) || subsectors.get(position);
  const hitBox = (tile) => tile.hit || { x: tile.x + 36, y: tile.y + 28, width: 273, height: 244 };
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

  const actions = spatialActions(view);
  const pieces = pieceIndex(view);

  // A button that names a ship or a planet square lands on that exact object;
  // everything else lands on the whole world.
  const tileActions = new Map();
  const targetKeys = new Set();
  const shipTargets = [];
  for (const action of actions) {
    const candidates = pieces.get(action.tile) || [];
    if (action.kind === 'move-ship') {
      const ship = candidates.find((piece) => piece.kind === 'ship' && piece.class === action.ship);
      if (ship) { shipTargets.push({ piece: ship, action }); continue; }
    }
    if (action.kind === 'combat-hit' || action.kind === 'combat-remove') {
      const key = `${action.kind}:${action.tile}:${action.unit}`;
      const ship = candidates.find((piece) => piece.kind === 'ship' && piece.name === action.unit);
      if (ship && !targetKeys.has(key)) {
        targetKeys.add(key);
        shipTargets.push({ piece: ship, action });
        continue;
      }
    }
    if (action.kind === 'population' && action.square && !action.cube) {
      const planet = candidates.find((piece) => piece.kind === 'planet'
        && piece.square === action.square && piece.index === action.index);
      if (planet) { shipTargets.push({ piece: planet, action }); continue; }
    }
    if (action.kind === 'move-from') {
      // Any ship in the system selects that system; the engine then asks which type.
      const ships = candidates.filter((piece) => piece.kind === 'ship' && piece.color !== 'ai');
      if (ships.length) {
        ships.forEach((piece) => shipTargets.push({ piece, action }));
        continue;
      }
    }
    // Choices drawn as their own control (unit cards, quantity, blueprints) or as
    // the tile preview must not also become a world hotspot.
    if (['move-queue', 'build-unit', 'upgrade-ship', 'upgrade-slot', 'explore-place',
      'combat-roll', 'combat-hit', 'combat-remove'].includes(action.kind)
        || (action.kind === 'population' && action.cube)) {
      continue;
    }
    if (!tileActions.has(action.tile)) tileActions.set(action.tile, []);
    tileActions.get(action.tile).push(action);
  }

  for (const [position, choices] of tileActions) {
    const tile = targetTile(position);
    if (!tile) continue;
    const action = choices.sort((left, right) =>
      TILE_PRIORITY.indexOf(left.kind) - TILE_PRIORITY.indexOf(right.kind))[0];
    const target = hitBox(tile);
    const isInfluence = ['influence-add', 'influence-remove'].includes(action.kind);
    const box = isInfluence
      ? { x: target.x + target.width / 2 - 20, y: target.y + target.height / 2 - 20, width: 40, height: 40 }
      : target;
    const hotspot = document.createElement('button');
    hotspot.type = 'button';
    hotspot.className = `hotspot ${action.kind}${tile.empty ? ' empty' : ''}`;
    hotspot.title = `${tileLabel(tile)}: ${action.button.label || action.kind}`;
    hotspot.setAttribute('aria-label', `${tileLabel(tile)}: ${OBJECT_LABEL[action.kind]?.(tile) || action.kind}`);
    hotspot.style.left = `${box.x}px`;
    hotspot.style.top = `${box.y}px`;
    hotspot.style.width = `${box.width}px`;
    hotspot.style.height = `${box.height}px`;
    const tag = document.createElement('span');
    tag.className = 'tag';
    tag.textContent = OBJECT_LABEL[action.kind]?.(tile) || action.button.label || action.kind;
    hotspot.appendChild(tag);
    pressNode(hotspot, action);
    el.overlay.appendChild(hotspot);
  }

  // A chosen build system keeps a marker while its unit tray is open.
  for (const position of new Set(actions.filter((action) => action.kind === 'build-unit')
    .map((action) => action.tile))) {
    const tile = targetTile(position);
    if (!tile) continue;
    const box = hitBox(tile);
    const marker = document.createElement('div');
    marker.className = 'hotspot building';
    marker.style.left = `${box.x}px`;
    marker.style.top = `${box.y}px`;
    marker.style.width = `${box.width}px`;
    marker.style.height = `${box.height}px`;
    const tag = document.createElement('span');
    tag.className = 'tag';
    tag.textContent = `Building in ${tile.label || position}`;
    marker.appendChild(tag);
    el.overlay.appendChild(marker);
  }
  for (const position of new Set(actions.filter((action) => action.kind === 'combat-roll')
    .map((action) => action.tile))) {
    const tile = targetTile(position);
    if (!tile) continue;
    const box = hitBox(tile);
    const marker = document.createElement('div');
    marker.className = 'hotspot battle';
    marker.style.left = `${box.x}px`;
    marker.style.top = `${box.y}px`;
    marker.style.width = `${box.width}px`;
    marker.style.height = `${box.height}px`;
    const tag = document.createElement('span');
    tag.className = 'tag';
    tag.textContent = `Battle in ${tile.label || position}`;
    marker.appendChild(tag);
    el.overlay.appendChild(marker);
  }

  for (const { piece, action } of shipTargets) {
    const tile = tiles.get(piece.tile);
    if (!tile) continue;
    const where = subsectors.get(piece.position) || tile;
    const size = piece.kind === 'planet' ? 46 : 56;
    const node = document.createElement('button');
    node.type = 'button';
    node.className = `piece ${piece.kind} ${action.kind} ${piece.color || ''}`;
    node.style.left = `${tile.x + piece.x - size / 2}px`;
    node.style.top = `${tile.y + piece.y - size / 2}px`;
    node.style.width = `${size}px`;
    node.style.height = `${size}px`;
    node.style.setProperty('--ring', PIECE_COLORS[piece.color] || '#8fd8ff');
    const what = piece.kind === 'ship'
      ? `${piece.color} ${piece.class} in ${tileLabel(where)}`
      : `${piece.square} square in ${tileLabel(where)}`;
    node.title = `${what}: ${action.button.label || action.kind}`;
    node.setAttribute('aria-label', `${what}: ${OBJECT_LABEL[action.kind]?.() || action.button.label}`);
    const glyph = document.createElement('span');
    glyph.className = 'glyph';
    glyph.textContent = piece.kind === 'ship'
      ? (piece.class === 'int' ? '▲' : piece.class === 'cru' ? '◆' : piece.class === 'drd' ? '■' : '✚')
      : { money: '◉', science: '◈', material: '▣', neutral: '◇', orbital: '⬡' }[piece.square] || '◇';
    if (piece.kind !== 'planet') node.appendChild(glyph);
    const planetLabel = { money: 'Gold', moneyadv: 'Adv Gold', science: 'Science',
      scienceadv: 'Adv Science', material: 'Material', materialadv: 'Adv Material',
      neutral: 'Neutral', neutraladv: 'Adv Neutral', orbital: 'Orbital' }[piece.square] || piece.square;
    const shipName = SHIP_NAMES[piece.class] || piece.class;
    const marks = { population: planetLabel, 'move-from': shipName, 'move-ship': shipName,
      'combat-hit': 'Hit', 'combat-remove': 'Remove' };
    if (marks[action.kind]) {
      const tag = document.createElement('span');
      tag.className = 'tag';
      tag.textContent = marks[action.kind];
      node.appendChild(tag);
    }
    if (piece.count > 1) {
      const count = document.createElement('span');
      count.className = 'count';
      count.textContent = String(piece.count);
      node.appendChild(count);
    }
    pressNode(node, action, piece.class);
    el.overlay.appendChild(node);
  }

  for (const action of actions.filter((entry) => entry.button.counts?.length)) {
    const tile = targetTile(action.tile);
    const ship = (pieces.get(action.tile) || []).find((piece) =>
      piece.kind === 'ship' && piece.class === action.ship && piece.color === view.you?.color);
    if (!tile || !ship) continue;
    const choices = action.button.counts;
    choices.forEach((choice, index) => {
      const angle = choices.length === 1 ? -Math.PI / 2
        : -5 * Math.PI / 6 + 2 * Math.PI / 3 * index / (choices.length - 1);
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'move-count';
      button.textContent = choice.label.match(/\((\d+)\)/)?.[1];
      button.setAttribute('aria-label', `Move ${button.textContent} ${SHIP_NAMES[ship.class]}`);
      button.style.left = `${tile.x + ship.x + 65 * Math.cos(angle) - 16}px`;
      button.style.top = `${tile.y + ship.y + 65 * Math.sin(angle) - 16}px`;
      pressNode(button, { ...action, button: choice });
      el.overlay.appendChild(button);
    });
  }

  renderTilePreview(actions, tiles);
  renderDragToken(actions, targetTile, pieces);
}

function previewOptions(actions) {
  return actions.filter((action) => action.kind === 'explore-place')
    .sort((left, right) => left.rotation - right.rotation);
}

function renderTilePreview(actions, tiles) {
  const places = previewOptions(actions);
  if (!places.length) {
    state.previewKey = null;
    state.previewActions = [];
    state.previewRotations = [];
    return;
  }
  const key = `${places[0].tile}:${places[0].sector}`;
  const rotations = [...new Set(places.map((action) => action.rotation))];
  if (state.previewKey !== key || !rotations.includes(state.previewRotation)) {
    state.previewKey = key;
    state.previewRotation = places[0].rotation;
  }
  state.previewActions = places;
  state.previewRotations = rotations;
  const tile = tiles.get(places[0].tile);
  if (!tile) return;
  const preview = document.createElement('button');
  preview.type = 'button';
  preview.className = 'tile-preview';
  preview.style.left = `${tile.x}px`;
  preview.style.top = `${tile.y}px`;
  preview.style.width = '345px';
  preview.style.height = '300px';
  preview.title = 'Rotate this sector, then place it';
  preview.setAttribute('aria-label', 'Explored sector preview; activate to rotate');
  preview.addEventListener('click', (event) => {
    event.stopPropagation();
    rotatePreview(1);
  });
  const image = document.createElement('img');
  image.src = `/api/games/${encodeURIComponent(state.gameId)}/tile.webp`
    + `?sector=${encodeURIComponent(places[0].sector)}&rot=${state.previewRotation}`;
  image.alt = `Explored sector, rotation ${state.previewRotation} degrees`;
  image.draggable = false;
  preview.appendChild(image);
  el.overlay.appendChild(preview);
  const controls = document.createElement('div');
  controls.className = 'map-preview-tools';
  controls.style.left = `${tile.x + 172.5}px`;
  controls.style.top = `${tile.y + 270}px`;
  for (const [direction, label, glyph] of [[-1, 'Rotate left', '⟲'], [1, 'Rotate right', '⟳']]) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'icon';
    button.textContent = glyph;
    button.title = label;
    button.setAttribute('aria-label', label);
    button.addEventListener('click', () => rotatePreview(direction));
    controls.appendChild(button);
  }
  controls.addEventListener('pointerdown', (event) => event.stopPropagation());
  controls.addEventListener('click', (event) => event.stopPropagation());
  el.overlay.appendChild(controls);
}

function rotatePreview(direction) {
  if (!state.previewRotations || !state.previewRotations.length) return;
  const index = state.previewRotations.indexOf(state.previewRotation);
  const next = (index - direction + state.previewRotations.length) % state.previewRotations.length;
  state.previewRotation = state.previewRotations[next];
  document.querySelectorAll('.preview-tools .stack-row b').forEach((node) => {
    node.textContent = `${state.previewRotation}°`;
  });
  if (state.view) renderOverlay(state.view);
}

function placePreview() {
  const action = state.previewActions?.find((entry) => entry.rotation === state.previewRotation);
  if (action) press(action.message.id, action.button.custom_id, null);
}

function renderDragToken(actions, targetTile, pieces) {
  const destinations = actions.filter((action) => action.kind === 'move-dest');
  if (!destinations.length) return;
  const origin = destinations[0].from;
  const tile = targetTile(origin);
  if (!tile) return;
  const ship = (pieces.get(origin) || []).find((piece) =>
    piece.kind === 'ship' && piece.class === destinations[0].ship);
  const x = ship ? ship.x : 172;
  const y = ship ? ship.y : 150;
  const token = document.createElement('div');
  token.className = 'drag-token';
  token.style.left = `${tile.x + x - 34}px`;
  token.style.top = `${tile.y + y - 34}px`;
  token.style.width = '68px';
  token.style.height = '68px';
  token.textContent = '✥';
  token.title = `Drag this ${destinations[0].ship} onto a highlighted destination, or click one.`;
  el.overlay.appendChild(token);
  bindDragToken(token, destinations);
}

function bindDragToken(token, destinations) {
  let start = null;
  token.addEventListener('pointerdown', (event) => {
    event.stopPropagation();
    start = { x: event.clientX, y: event.clientY, left: token.offsetLeft, top: token.offsetTop,
              moved: false };
    token.setPointerCapture(event.pointerId);
  });
  token.addEventListener('pointermove', (event) => {
    if (!start) return;
    const dx = (event.clientX - start.x) / state.zoom;
    const dy = (event.clientY - start.y) / state.zoom;
    start.moved = start.moved || Math.abs(dx) + Math.abs(dy) > 3;
    token.style.left = `${start.left + dx}px`;
    token.style.top = `${start.top + dy}px`;
    const target = hotspotAt(event.clientX, event.clientY, '.hotspot.move-dest');
    document.querySelectorAll('.hotspot.drop-target').forEach((node) => node.classList.remove('drop-target'));
    if (target) target.classList.add('drop-target');
  });
  token.addEventListener('pointerup', (event) => {
    if (!start) return;
    const target = hotspotAt(event.clientX, event.clientY, '.hotspot.move-dest');
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

function hotspotAt(clientX, clientY, selector = '.hotspot') {
  const rect = el.viewport.getBoundingClientRect();
  if (clientX < rect.left || clientX > rect.right || clientY < rect.top || clientY > rect.bottom) {
    return null;
  }
  const x = (clientX - rect.left - state.panX) / state.zoom;
  const y = (clientY - rect.top - state.panY) / state.zoom;
  return [...document.querySelectorAll(selector)].find((node) =>
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
    el.boardEmpty.classList.toggle('hidden', state.boardLoaded || !!el.board.naturalWidth);
    el.boardNote.textContent = 'rendering…';
    el.board.onload = () => {
      state.boardLoaded = true;
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
      state.boardLoaded = true;
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

function panelImage(view, panel, seat, label) {
  const image = document.createElement('img');
  image.className = 'rendered-panel';
  image.alt = label;
  image.loading = 'lazy';
  image.src = `/api/games/${encodeURIComponent(view.game.id)}/${panel}.webp`
    + `?v=${encodeURIComponent(view.version)}&seat=${encodeURIComponent(seat || '')}`;
  image.title = ['ai', 'species', 'player'].includes(panel) ? label : 'Click to enlarge';
  if (panel === 'player') image.style.cursor = 'default';
  if (!['ai', 'species', 'player'].includes(panel)) image.addEventListener('click', () => {
    if (panel === 'market' && image.closest('.researching')) return;
    el.zoomImage.src = image.src;
    el.zoomImage.alt = label;
    el.zoomDialog.showModal();
  });
  return image;
}

function showTechTracks(techId, entries) {
  const dialog = document.getElementById('tech-track-dialog');
  const info = state.catalog.techs?.[techId];
  document.getElementById('tech-track-title').textContent = `${info?.name || 'Technology'} · choose track`;
  document.getElementById('tech-track-choices').replaceChildren(...entries.map((entry) => {
    const target = techButton(entry.button.custom_id) || freeTechChoice(entry.button.custom_id);
    const button = document.createElement('button');
    button.type = 'button';
    button.className = `tech-track-choice ${target.track}`;
    const cost = entry.button.label.match(/\((\d+)\)/)?.[1];
    button.textContent = `${trackLabel(target.track)}${cost ? ` · ${cost} science` : ''}`;
    button.addEventListener('click', () => {
      dialog.close();
      press(entry.message.id, entry.button.custom_id, null);
    });
    return button;
  }));
  if (!dialog.open) dialog.showModal();
}

function renderMarket(view) {
  const choices = new Map();
  for (const [id, entry] of buttonById(view)) {
    const target = techButton(id) || freeTechChoice(id);
    if (!target) continue;
    if (!choices.has(target.tech)) choices.set(target.tech, []);
    choices.get(target.tech).push(entry);
  }
  const choosing = choices.size > 0;
  if (!choosing) {
    document.getElementById('tech-track-dialog').close();
  }
  const card = el.market.closest('.market-card');
  const wasChoosing = card.classList.contains('researching');
  card.classList.toggle('researching', choosing);
  if (choosing) {
    if (!wasChoosing) document.querySelector('.table').insertBefore(card, document.querySelector('.players-card'));
    document.getElementById('market-toggle').setAttribute('aria-expanded', 'true');
    document.getElementById('market-content').classList.remove('collapsed');
    document.getElementById('market-content').inert = false;
  } else {
    const expanded = document.getElementById('market-toggle').getAttribute('aria-expanded') === 'true';
    const wide = expanded && !(view.battles || []).length;
    card.classList.toggle('expanded-market', wide);
    if (wide) document.querySelector('.table').insertBefore(card, document.querySelector('.players-card'));
    else if (card.parentElement !== document.querySelector('.right')) document.querySelector('.right').appendChild(card);
  }
  const stage = document.createElement('div');
  stage.className = 'market-stage';
  stage.style.aspectRatio = el.market.firstElementChild?.style.aspectRatio || '';
  const image = panelImage(view, 'market', '', 'Available technologies');
  if (choosing) {
    image.loading = 'eager';
    image.style.cursor = 'default';
    image.title = 'Choose a highlighted technology';
  }
  stage.appendChild(image);
  el.market.replaceChildren(stage);
  el.marketNote.textContent = choosing ? 'Choose a highlighted technology' : 'Click to enlarge';
  if (!choosing) return;
  api.marketLayout(view.game.id).then((layout) => {
    if (!stage.isConnected) return;
    image.width = layout.width;
    image.height = layout.height;
    stage.style.aspectRatio = `${layout.width} / ${layout.height}`;
    for (let index = 0; index < layout.regions.length; index += 1) {
      const region = layout.regions[index];
      const entries = choices.get(region.tech) || [];
      // Duplicate tiles overlap in the bot's market; expose only their visible area.
      const next = layout.regions[index + 1];
      const width = next && next.y === region.y ? Math.min(region.width, next.x - region.x) : region.width;
      if (!entries.length) continue;
      const trackEntries = entries.filter((entry) => techButton(entry.button.custom_id)?.track !== 'any');
      const tracks = trackEntries.length ? trackEntries : entries;
      const needsTrackChoice = tracks.length > 1 || (trackEntries.length && state.catalog.techs?.[region.tech]?.track === 'any');
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'market-target';
      button.style.left = `${100 * region.x / layout.width}%`;
      button.style.top = `${100 * region.y / layout.height}%`;
      button.style.width = `${100 * width / layout.width}%`;
      button.style.height = `${100 * region.height / layout.height}%`;
      button.title = needsTrackChoice ? 'Choose technology track' : tracks[0].button.label;
      button.setAttribute('aria-label', button.title);
      button.addEventListener('click', () => {
        if (needsTrackChoice) showTechTracks(region.tech, tracks);
        else press(tracks[0].message.id, tracks[0].button.custom_id, button);
      });
      stage.appendChild(button);
    }
    if (!wasChoosing) card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }).catch((error) => showToast(error.message, true));
}

// ------------------------------------------------------------------- players
function updatePlayerBoardsToggle() {
  const hasExpandedBoard = !!el.players.querySelector('.player-board-toggle[aria-expanded="true"]');
  const button = document.getElementById('toggle-player-boards');
  const label = hasExpandedBoard ? 'Collapse all player boards' : 'Expand all player boards';
  button.textContent = hasExpandedBoard ? '▴' : '▾';
  button.title = label;
  button.setAttribute('aria-label', label);
}

function renderPlayers(view) {
  const players = [...(view.game.players || [])].sort((left, right) =>
    Number(right.id === view.seat) - Number(left.id === view.seat));
  el.players.replaceChildren(...players.map((player) => {
    const article = document.createElement('article');
    article.className = `rendered-player${player.is_you ? ' you' : ''}`;
    const key = `${view.game.id}:${player.id}`;
    const isExpanded = !state.collapsedBoards.has(key);
    const header = document.createElement('div');
    header.className = 'player-board-head';
    const head = document.createElement('button');
    head.type = 'button';
    head.className = 'ghost player-board-toggle';
    const title = `${player.name}${player.is_you ? ' · you' : ''}${player.passed ? ' · passed' : ''}`;
    head.textContent = `${isExpanded ? '▾' : '▸'} ${title}`;
    head.setAttribute('aria-expanded', String(isExpanded));
    const content = document.createElement('div');
    content.className = `market-content${isExpanded ? '' : ' collapsed'}`;
    content.id = `player-board-${player.id}`;
    content.inert = !isExpanded;
    head.setAttribute('aria-controls', content.id);
    const body = document.createElement('div');
    body.className = 'market-clip';
    content.appendChild(body);
    head.addEventListener('click', () => {
      const expanded = head.getAttribute('aria-expanded') !== 'true';
      head.setAttribute('aria-expanded', String(expanded));
      head.textContent = `${expanded ? '▾' : '▸'} ${title}`;
      content.classList.toggle('collapsed', !expanded);
      content.inert = !expanded;
      if (expanded) state.collapsedBoards.delete(key);
      else state.collapsedBoards.add(key);
      updatePlayerBoardsToggle();
    });
    const reference = document.createElement('button');
    reference.type = 'button';
    reference.className = 'ghost small';
    reference.textContent = 'Faction';
    reference.addEventListener('click', () => {
      state.factionPlayer = player;
      renderFaction();
      el.factionDialog.showModal();
    });
    header.append(head, reference);
    article.append(header, content);
    if (player.color) {
      body.appendChild(panelImage(view, 'player', player.id, `${player.name} — player board`));
    } else {
      const note = document.createElement('p');
      note.className = 'note';
      note.textContent = 'Waiting for faction draft';
      body.appendChild(note);
    }
    return article;
  }));
  el.playersNote.textContent = `${players.length} seats`;
  updatePlayerBoardsToggle();
}

// ---------------------------------------------------------------------- dock
const FREE_TECH_RE = /_getFreeTech_([a-z0-9]+)(?:_(military|grid|nano))?$/;

function freeTechChoice(customId) {
  const match = customId.match(FREE_TECH_RE);
  if (!match) return null;
  return { tech: match[1], track: match[2] || 'any' };
}

function partChoices(message) {
  const entries = (message.buttons || []).map((button) =>
    ({ button, target: partButton(button.custom_id || '') }))
    .filter((entry) => entry.target?.kind === 'new');
  if (!entries.length) return null;
  const cards = entries.map(({ button, target }) => {
    const part = state.catalog.parts?.[target.part];
    return `<li><button type="button" class="part-option" data-custom="${escapeHtml(button.custom_id)}"
      ${button.disabled ? 'disabled' : ''} title="${escapeHtml(part?.description || button.label)}">
      ${part?.image ? `<img src="${part.image}" alt="" loading="lazy">` : ''}
      <span>${escapeHtml(button.label || part?.name || target.part)}</span>
    </button></li>`;
  }).join('');
  const ids = new Set(entries.map((entry) => entry.button.custom_id));
  return { html: `<ul class="upgrade-parts">${cards}</ul>`,
    other: (message.buttons || []).filter((button) => !ids.has(button.custom_id)) };
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

// ------------------------------------------------------------- direct choices
function boardPromptHint(buttons, message) {
  const wrap = document.createElement('div');
  wrap.className = 'object-hint';
  const label = document.createElement('span');
  label.className = 'hint-label';
  label.textContent = 'Pick it on the board';
  wrap.appendChild(label);
  const details = document.createElement('details');
  details.className = 'choice-fallback';
  details.innerHTML = '<summary>Or choose from a list</summary>';
  details.appendChild(genericChoices(buttons, message));
  wrap.appendChild(details);
  return wrap;
}

function upgradeBlueprint(message, choices) {
  const wrap = document.createElement('div');
  wrap.className = 'upgrade-blueprint market-stage';
  const first = choices[0];
  const ship = SHIP_NAMES[shipClass(first.target.ship)];
  const view = state.view;
  const url = `/api/games/${encodeURIComponent(view.game.id)}/blueprint-${ship}.webp`
    + `?seat=${encodeURIComponent(view.seat)}&v=${encodeURIComponent(view.version)}`;
  const image = document.createElement('img');
  image.alt = `${ship} blueprint`;
  image.src = url;
  wrap.appendChild(image);
  fetch(`${url}&layout=1`).then(async (response) => {
    if (!response.ok) throw new Error('Could not load blueprint slots');
    const layout = await response.json();
    if (!wrap.isConnected) return;
    image.width = layout.width;
    image.height = layout.height;
    wrap.style.aspectRatio = `${layout.width} / ${layout.height}`;
    for (const region of layout.regions) {
      const entry = choices.find((choice) => choice.target.slot === region.slot);
      if (!entry) continue;
      const isChoice = entry.target.kind !== 'new';
      const target = document.createElement(isChoice ? 'button' : 'span');
      target.className = 'market-target';
      target.style.left = `${100 * region.x / layout.width}%`;
      target.style.top = `${100 * region.y / layout.height}%`;
      target.style.width = `${100 * region.width / layout.width}%`;
      target.style.height = `${100 * region.height / layout.height}%`;
      if (isChoice) {
        target.type = 'button';
        target.title = entry.button.label;
        target.setAttribute('aria-label', `Slot ${region.slot + 1}: ${entry.button.label}`);
        target.disabled = !!entry.button.disabled;
        target.addEventListener('click', () => press(message.id, entry.button.custom_id, target));
      }
      wrap.appendChild(target);
    }
  }).catch((error) => showToast(error.message, true));
  return wrap;
}

const BUILD_ART = { Interceptor: 'int', Cruiser: 'cru', Dreadnought: 'drd',
  Starbase: 'sb', Orbital: 'orb', Monolith: 'mon' };
const SHIP_NAMES = { int: 'interceptor', cru: 'cruiser', drd: 'dreadnought',
  sb: 'starbase', orb: 'orbital', mon: 'monolith' };

function labelFor(position) {
  const tile = (state.boardMeta?.tiles || []).find((row) => row.position === position);
  return tile && !tile.empty ? (tile.label || position) : position;
}

function buildPanel(entries, message) {
  const wrap = document.createElement('div');
  wrap.className = 'build-tray';
  const tile = entries[0].target.tile;
  const materials = state.view?.you?.materials;
  const total = Number(((message.content || '').match(/Total cost so far of (\d+)/) || [])[1] || 0);
  const head = document.createElement('div');
  head.className = 'tray-head';
  const left = materials === undefined ? '' : (materials - total) >= 0
    ? ` · <span class="materials">${materials - total} materials left</span>`
    : ` · <span class="materials short">${total - materials} more material${total - materials === 1 ? '' : 's'} needed</span>`;
  head.innerHTML = `Building in <b>${escapeHtml(labelFor(tile))}</b>${left}`;
  wrap.appendChild(head);
  const cards = document.createElement('div');
  cards.className = 'build-cards';
  const color = state.view?.you?.color || '';
  for (const entry of entries) {
    const target = entry.target;
    const cost = Number(((entry.button.label || '').match(/\((\d+)\)/) || [])[1]);
    const short = BUILD_ART[target.ship] || target.ship.toLowerCase();
    const art = `/art/components/basic_ships/${['orb', 'mon'].includes(short) ? short : `${color}-${short}`}.png`;
    const card = document.createElement('button');
    card.type = 'button';
    card.className = 'build-card';
    card.title = (entry.button.label || target.ship)
      + (materials !== undefined && (materials - total) < cost
        ? ' — costs more than your materials; trade at the spend step' : '');
    card.classList.toggle('short', materials !== undefined && (materials - total) < cost);
    card.innerHTML = `<img src="${art}" alt="" loading="lazy">
      <span class="name">${escapeHtml(target.ship)}</span>
      <span class="cost">◉ ${Number.isNaN(cost) ? '?' : cost}</span>`;
    card.addEventListener('click', () => press(message.id, entry.button.custom_id, card));
    cards.appendChild(card);
  }
  wrap.appendChild(cards);
  return wrap;
}

function discoveryPanel(entries, keep, message) {
  const wrap = document.createElement('div');
  wrap.className = 'discovery-card';
  if (entries.length > 1 && entries.every((entry) => entry.action === 'selectDiscTile')) {
    // Two drawn tiles: each is its own card, with its own art.
    const grid = document.createElement('div');
    grid.className = 'discovery-choices';
    for (const entry of entries) {
      const info = state.catalog.discoveries?.[entry.disc];
      const card = document.createElement('button');
      card.type = 'button';
      card.className = 'discovery-choice';
      card.innerHTML = `${info?.image ? `<img src="${info.image}" alt="${escapeHtml(info.name)}">` : ''}
        <span>${escapeHtml(info?.name || entry.disc)}</span>`;
      card.addEventListener('click', () => press(message.id, entry.button.custom_id, card));
      grid.appendChild(card);
    }
    wrap.appendChild(grid);
    return wrap;
  }
  const source = entries[0]?.disc ? state.catalog.discoveries?.[entries[0].disc] : null;
  const image = source?.image || (message.attachments || [])[0]?.url;
  if (image) {
    const art = document.createElement('img');
    art.src = image;
    art.alt = source?.name || 'Discovery tile';
    wrap.appendChild(art);
  }
  const body = document.createElement('div');
  body.className = 'discovery-body';
  if (source?.name) body.innerHTML = `<b>${escapeHtml(source.name)}</b>`;
  for (const entry of entries) {
    const node = document.createElement('button');
    node.type = 'button';
    node.className = 'choice s3';
    node.textContent = 'Use it for its ability';
    node.addEventListener('click', () => press(message.id, entry.button.custom_id, node));
    body.appendChild(node);
  }
  if (keep) {
    const node = document.createElement('button');
    node.type = 'button';
    node.className = 'choice';
    node.textContent = 'Keep it for 2 points';
    node.addEventListener('click', () => press(message.id, keep.custom_id, node));
    body.appendChild(node);
  }
  wrap.appendChild(body);
  return wrap;
}

function previewPanel(entries, message) {
  const wrap = document.createElement('div');
  wrap.className = 'preview-tools';
  const head = document.createElement('div');
  head.className = 'tray-head';
  head.innerHTML = `Sector <b>${escapeHtml(entries[0].sector)}</b> for <b>${escapeHtml(entries[0].tile)}</b>`;
  wrap.appendChild(head);
  const row = document.createElement('div');
  row.className = 'stack-row';
  const left = document.createElement('button');
  left.type = 'button';
  left.className = 'icon';
  left.textContent = '⟲';
  left.title = 'Rotate left (←)';
  left.addEventListener('click', () => rotatePreview(-1));
  const deg = document.createElement('b');
  deg.textContent = `${state.previewRotation}°`;
  const right = document.createElement('button');
  right.type = 'button';
  right.className = 'icon';
  right.textContent = '⟳';
  right.title = 'Rotate right (→)';
  right.addEventListener('click', () => rotatePreview(1));
  const place = document.createElement('button');
  place.type = 'button';
  place.className = 'choice s3';
  place.textContent = 'Place tile here';
  place.title = 'Place the previewed sector (Enter)';
  place.addEventListener('click', () => placePreview());
  row.append(left, deg, right, place);
  wrap.appendChild(row);
  wrap.appendChild(Object.assign(document.createElement('div'), {
    className: 'note',
    textContent: 'Click the preview on the board to rotate. The engine only offers legal orientations.',
  }));
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
  // The engine's combined orientation image is replaced by the on-board preview,
  // and discovery cards carry their own art.
  const previewing = (message.buttons || [])
    .some((button) => objectAction(button.custom_id || '')?.kind === 'explore-place');
  const discovering = (message.buttons || []).some((button) =>
    discoveryChoice(button.custom_id || '') || /_keepDiscForPoints$/.test(button.custom_id || ''));
  const researching = (message.buttons || []).some((button) =>
    techButton(button.custom_id || '') || freeTechChoice(button.custom_id || ''));
  if (!previewing && !discovering && !researching) {
    for (const attachment of message.attachments || []) {
      const image = document.createElement('img');
      image.className = 'attachment';
      image.src = attachment.url;
      image.alt = attachment.name || '';
      image.loading = 'lazy';
      body.appendChild(image);
    }
  }

  const buttons = message.buttons || [];
  const spatial = isCombat(message) ? []
    : buttons.filter((button) => objectAction(button.custom_id || ''));
  const dockSpatial = (button) => {
    const target = objectAction(button.custom_id);
    return target.kind === 'combat-roll' || (target.kind === 'population' && target.cube);
  };
  const handled = new Set(spatial
    .filter((button) => !dockSpatial(button))
    .map((button) => button.custom_id));

  const tech = buttons.filter((button) => techButton(button.custom_id || '') || freeTechChoice(button.custom_id || ''));
  if (tech.length) {
    tech.forEach((button) => handled.add(button.custom_id));
    const hint = document.createElement('p');
    hint.className = 'note';
    hint.textContent = 'Choose a highlighted technology in the market above Players.';
    body.appendChild(hint);
  }
  const partButtons = buttons.map((button) => ({ button, target: partButton(button.custom_id || '') }))
    .filter((entry) => entry.target && entry.target.kind !== 'ship');
  const parts = partChoices(message);
  const upgradeParts = partButtons.filter((entry) => entry.target.kind === 'new');
  if (upgradeParts.length) body.appendChild(upgradeBlueprint(message, upgradeParts));
  if (parts) {
    buttons.filter((button) => !parts.other.includes(button))
      .forEach((button) => handled.add(button.custom_id));
    const holder = document.createElement('div');
    holder.innerHTML = parts.html;
    body.appendChild(holder);
    for (const node of holder.querySelectorAll('[data-custom]')) {
      node.addEventListener('click', () => {
        const entry = buttonById({ pending: [message] }).get(node.dataset.custom);
        if (entry) press(entry.message.id, entry.button.custom_id, node);
      });
    }
  }

  const places = buttons.map((button) => ({ button, target: objectAction(button.custom_id || '') }))
    .filter((entry) => entry.target?.kind === 'explore-place');
  if (places.length) body.appendChild(previewPanel(places.map((entry) => entry.target), message));

  const builds = buttons.map((button) => ({ button, target: objectAction(button.custom_id || '') }))
    .filter((entry) => entry.target?.kind === 'build-unit');
  if (builds.length) body.appendChild(buildPanel(builds, message));

  const queue = buttons.filter((button) => objectAction(button.custom_id || '')?.kind === 'move-queue');
  if (queue.length) {
    const hint = document.createElement('p');
    hint.className = 'hint';
    hint.textContent = 'Choose how many ships to move above the stack on the map.';
    body.appendChild(hint);
  }

  const discoveries = buttons.map((button) => ({ button, ...(discoveryChoice(button.custom_id || '') || {}) }))
    .filter((entry) => entry.action);
  const keep = buttons.find((button) => /_keepDiscForPoints$/.test(button.custom_id || ''));
  if (discoveries.length || keep) {
    discoveries.forEach((entry) => handled.add(entry.button.custom_id));
    if (keep) handled.add(keep.custom_id);
    body.appendChild(discoveryPanel(discoveries, keep, message));
  }

  const upgradeShips = spatial.filter((button) => objectAction(button.custom_id).kind === 'upgrade-ship');
  const upgradeSlots = spatial.filter((button) => objectAction(button.custom_id).kind === 'upgrade-slot');
  if (upgradeShips.length) {
    body.appendChild(genericChoices(upgradeShips, message));
  }
  if (upgradeSlots.length) {
    body.appendChild(upgradeBlueprint(message, upgradeSlots.map((button) =>
      ({ button, target: objectAction(button.custom_id) }))));
  }
  const boardSpatial = spatial.filter((button) => {
    const kind = objectAction(button.custom_id).kind;
    if (dockSpatial(button)) return false;
    if (kind === 'build-tile' && builds.length) return false;
    return !['upgrade-ship', 'upgrade-slot', 'explore-place', 'build-unit'].includes(kind);
  });
  if (boardSpatial.length) body.appendChild(boardPromptHint(boardSpatial, message));

  body.appendChild(genericChoices(buttons.filter((button) => !handled.has(button.custom_id)), message));
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
  if (view.game.setup) {
    const drafter = view.game.players.find((player) => player.id === view.game.drafting_seat);
    const instruction = view.authenticated
      ? (view.seat === view.game.drafting_seat
        ? 'It is your turn to choose a faction. Waiting for the draft choices.'
        : 'Waiting for the next player to choose a faction.')
      : `${escapeHtml(drafter ? drafter.name : 'The next player')} chooses next. Select their seat above to draft.`;
    card.innerHTML = `<b>Faction draft.</b><div class="row">${instruction}</div>`;
    return card;
  }
  if (you && you.is_your_turn) {
    card.innerHTML = '<b>Your move.</b><div class="row">Waiting for your next game prompt. Existing Discord prompts remain usable in Discord.</div>';
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

function battlePanel(battle, messages, view) {
  const section = document.createElement('section');
  section.className = 'battle-room';
  section.id = `battle-${battle.room.replace(/[^a-zA-Z0-9_-]/g, '-')}`;
  const playerName = (color) => color === 'ai' ? 'Guardians / AI'
    : (view.game.players.find((player) => player.color === color)?.name || color);
  const sideName = (side) => side.colors.map(playerName).join(' + ') || side.role;
  const header = document.createElement('header');
  header.innerHTML = `<span class="battle-mark">⚔</span><div><b>${escapeHtml(
    battle.room.replace(/^aeb\d+-/, ''))}</b></div>`;
  const backToIndex = document.createElement('a');
  backToIndex.className = 'battle-back';
  backToIndex.href = '#table';
  backToIndex.textContent = '↑';
  backToIndex.title = 'Back to Galaxy view';
  backToIndex.setAttribute('aria-label', 'Back to Galaxy view');
  header.appendChild(backToIndex);
  section.appendChild(header);
  const sides = document.createElement('div');
  sides.className = 'battle-sides';
  sides.innerHTML = battle.sides.map((side) => `<span>${escapeHtml(sideName(side))}</span>`).join('');
  section.appendChild(sides);
  const chat = document.createElement('div');
  chat.className = 'battle-chat';
  chat.dataset.room = battle.room;
  chat.setAttribute('role', 'log');
  chat.setAttribute('aria-label', `Combat history: ${battle.room}`);
  const active = new Map(messages.map((message) => [message.id, message]));
  const events = new Map(battle.messages.map((message) => [message.id, message]));
  messages.forEach((message) => events.set(message.id, {
    ...message, combat: message.combat?.color ? message.combat : events.get(message.id)?.combat,
  }));
  for (const message of [...events.values()].sort((a, b) => a.id - b.id)) {
    if (!message.content && !(message.attachments || []).length && !active.has(message.id)) continue;
    const event = document.createElement('div');
    const side = message.combat?.side;
    event.className = `battle-event ${side || 'neutral'}`;
    const color = message.combat?.color;
    if (color) {
      const author = document.createElement('div');
      author.className = 'battle-author';
      author.textContent = playerName(color);
      author.style.color = PIECE_COLORS[color] || 'var(--muted)';
      event.appendChild(author);
    }
    event.appendChild(active.has(message.id) ? promptCard(message, 0) : historyItem(message));
    event.querySelectorAll('img.attachment').forEach((image) => {
      const zoom = document.createElement('button');
      zoom.type = 'button';
      zoom.className = 'battle-image-zoom';
      zoom.setAttribute('aria-label', 'Enlarge combat image');
      image.replaceWith(zoom);
      zoom.appendChild(image);
      zoom.addEventListener('click', () => {
        el.zoomImage.src = image.src;
        el.zoomImage.alt = image.alt;
        el.zoomDialog.showModal();
      });
    });
    chat.appendChild(event);
  }
  section.appendChild(chat);
  return section;
}

function renderDock(view) {
  const pageScroll = { left: window.scrollX, top: window.scrollY };
  const scrolls = new Map([...el.dock.querySelectorAll('.battle-chat')].map((chat) =>
    [chat.dataset.room, { top: chat.scrollTop,
      followsLatest: chat.scrollHeight - chat.scrollTop - chat.clientHeight < 32 }]));
  const dockContent = document.createDocumentFragment();
  const battle = selectedBattle(view);
  const visibleBattles = battle ? [battle] : [];
  const pending = [...(view.pending || [])];
  if (!pending.length && !(view.battles || []).length) {
    el.dock.replaceChildren(waitingCard(view));
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
  for (const battle of visibleBattles) {
    const panel = battlePanel(battle, rooms.get(battle.room) || [], view);
    dockContent.appendChild(panel);
  }
  const table = unique.filter((message) => !isCombat(message));
  const primary = table.filter(isChoicePrompt).sort((a, b) => b.id - a.id);
  const secondary = table.filter((message) => !isChoicePrompt(message)).sort((a, b) => b.id - a.id);
  if (!battle) {
    if ((view.battles || []).length) {
      const notice = document.createElement('section');
      notice.className = 'card combat-notice';
      const heading = document.createElement('h2');
      heading.textContent = 'Resolve all combat before continuing';
      notice.append(heading, document.getElementById('battle-index'));
      dockContent.appendChild(notice);
    }
    [...primary, ...secondary].forEach((message, index) => dockContent.appendChild(promptCard(message, index)));
    if (!dockContent.childNodes.length) dockContent.appendChild(waitingCard(view));
  }
  el.dock.replaceChildren(dockContent);
  for (const battle of visibleBattles) {
    const panel = document.getElementById(`battle-${battle.room.replace(/[^a-zA-Z0-9_-]/g, '-')}`);
    const chat = panel.querySelector('.battle-chat');
    const previous = scrolls.get(battle.room);
    let followsLatest = !previous || previous.followsLatest;
    const restoreScroll = () => {
      chat.scrollTop = previous && !previous.followsLatest ? previous.top : chat.scrollHeight;
    };
    restoreScroll();
    chat.addEventListener('scroll', () => {
      followsLatest = chat.scrollHeight - chat.scrollTop - chat.clientHeight < 32;
    });
    chat.querySelectorAll('img').forEach((image) => image.addEventListener('load', () => {
      if (followsLatest) chat.scrollTop = chat.scrollHeight;
    }, { once: true }));
  }
  if (battle) window.scrollTo({ ...pageScroll, behavior: 'instant' });
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
    el.historyList.innerHTML = '<p class="note">No recorded history yet. Messages from Discord before the Web UI was enabled are not imported.</p>';
  }
}

// -------------------------------------------------------------------- faction
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
  el.factionBody.innerHTML = `<div class="faction-reference content">${bodyHtml(faction.reference)}</div>
    ${faction.image ? `<img id="faction-image" class="rendered-panel" src="${faction.image}" alt="${escapeHtml(faction.name)} board" title="Click to enlarge">` : ''}`;
  const image = document.getElementById('faction-image');
  if (image) {
    image.addEventListener('click', () => {
      el.zoomImage.src = image.src;
      el.zoomDialog.showModal();
    });
  }
}

async function followActiveSeat(view) {
  if (!state.isDevMode || view.error || view.game.ended) return view;
  const active = view.game.active || [];
  const seat = view.game.drafting_seat || (view.game.players || [])
    .find((player) => active.includes(player.color))?.id;
  if (!seat || seat === state.seat) return view;
  state.seat = seat;
  localStorage.setItem(`eclipse-seat-${state.gameId}`, seat);
  state.lastKey = null;
  state.history = [];
  state.historyLoaded = false;
  state.factionPlayer = null;
  return api.view(state.gameId, seat);
}

// ---------------------------------------------------------------------- press
async function press(messageId, customId, node) {
  if (!customId || state.rendering) return;
  state.rendering = true;
  if (node) node.disabled = true;
  showToast('Resolving…');
  try {
    const view = await followActiveSeat(await api.press(state.gameId, state.seat, customId, messageId));
    if (view.error) showToast(view.error, true);
    else el.toast.classList.remove('on');
    render(view, true);
    const selectedTech = techButton(customId);
    if (!view.error && selectedTech?.track === 'any') {
      const tracks = (view.tech_tracks || []).filter((button) => techButton(button.custom_id))
        .map((button) => ({ message: { id: messageId }, button }));
      if (tracks.length) showTechTracks(selectedTech.tech, tracks);
    }
    if (el.historyDialog.open) await loadHistory(true);
  } catch (error) {
    showToast(`press failed: ${error}`, true);
  } finally {
    state.rendering = false;
    if (node && node.isConnected) node.disabled = false;
  }
}

// ---------------------------------------------------------------------- seats
function renderSeats(view) {
  const options = (view.game.players || []).filter((player) => !view.authenticated || player.id === view.seat);
  el.seat.disabled = !!view.authenticated;
  if (view.authenticated) state.seat = view.seat;
  const wanted = [...(view.authenticated ? [] : [['', 'Spectator']]), ...options.map((player) => [player.id,
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
    battles: view.battles,
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
    : view.game.setup ? 'Setup' : `Round ${view.game.round ?? '?'} / ${view.game.round_max ?? 8}`;
  const activeNames = active.map((color) => {
    const player = (view.game.players || []).find((row) => row.color === color);
    return player ? player.name : color;
  });
  el.turn.textContent = view.game.ended ? 'Game over'
    : view.game.setup ? `Faction draft: ${(view.game.players.find((p) => p.id === view.game.drafting_seat) || {}).name || 'finishing setup'}`
    : activeNames.length ? `Active: ${activeNames.join(', ')}` : 'No active seat';
  el.turn.classList.toggle('pass', !activeNames.length);
  const order = document.getElementById('turn-order');
  order.classList.toggle('hidden', view.game.setup || !active.length);
  if (!view.game.setup && active.length) {
    order.src = `/api/games/${encodeURIComponent(view.game.id)}/turn-order.webp?v=${encodeURIComponent(view.version)}`;
  }
  document.getElementById('s3-remaining').textContent = `S3: ${view.game.s3_remaining} remaining`;
  el.boardNote.classList.toggle('hidden', false);
  renderSeats(view);
  el.mirror.checked = !!view.mirror_to_discord;
  el.boardHint.textContent = view.seat
    ? `Drag to pan · scroll to zoom · highlighted worlds are choices`
    : 'Drag to pan · scroll to zoom';

  const table = document.querySelector('.table');
  const inCombat = (view.battles || []).length > 0;
  const combatKey = inCombat ? `${view.game.id}:${view.game.round}` : '';
  const wasInCombat = !!table.dataset.combat;
  const combatChanged = table.dataset.combat !== combatKey;
  table.dataset.combat = combatKey;
  const room = selectedBattle(view);
  table.classList.toggle('room-layout', !!room);
  const index = document.getElementById('battle-index');
  table.prepend(index);
  index.classList.toggle('hidden', !inCombat);
  index.replaceChildren(...(view.battles || []).map((battle) => {
    const link = document.createElement('a');
    const tile = battle.room.match(/Tile (\d+[a-z]?)/)?.[1];
    const hasShips = !!view.you && (view.pieces || []).some((piece) =>
      piece.kind === 'ship' && piece.position === tile && piece.color === view.you.color);
    link.href = `#room=${encodeURIComponent(battle.room)}`;
    if (battle === room) link.setAttribute('aria-current', 'page');
    link.textContent = battle.room.replace(/^aeb\d+-/, '') + (hasShips ? ' · Your ships' : '');
    link.classList.toggle('your-battle', hasShips);
    if (hasShips) link.style.setProperty('--seat-color', PIECE_COLORS[view.you.color]);
    return link;
  }));
  if (inCombat) {
    const tableLink = document.createElement('a');
    tableLink.href = '#table';
    tableLink.textContent = 'Galaxy view';
    if (!room) tableLink.setAttribute('aria-current', 'page');
    index.prepend(tableLink);
  }
  if (inCombat !== wasInCombat) {
    const toggle = document.getElementById('market-toggle');
    if (inCombat) table.dataset.marketExpanded = toggle.getAttribute('aria-expanded');
    const expanded = !inCombat && table.dataset.marketExpanded !== 'false';
    toggle.setAttribute('aria-expanded', String(expanded));
    document.getElementById('market-content').classList.toggle('collapsed', !expanded);
    document.getElementById('market-content').inert = !expanded;
  }
  if (!room) {
    renderBoard(view);
    if (combatChanged && state.boardLoaded) fitBoard();
  }
  renderMarket(view);
  renderPlayers(view);
  renderDock(view);
  if (el.factionDialog.open) renderFaction();
  state.lastKey = nextKey;
}

async function loadView(shouldFollowActive = false) {
  if (!state.gameId) return;
  try {
    let view = await api.view(state.gameId, state.seat);
    if (shouldFollowActive) view = await followActiveSeat(view);
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
    option.textContent = `${game.name || game.id} (${game.id}) · round ${game.round ?? '?'} · ${game.players.join(', ')}`;
    return option;
  }));
  if (el.game.value !== state.gameId) el.game.value = state.gameId;
  const storedSeat = localStorage.getItem(`eclipse-seat-${state.gameId}`);
  state.seat = storedSeat || '';
}

function bind() {
  document.getElementById('toggle-player-boards').addEventListener('click', () => {
    const shouldCollapse = !!el.players.querySelector('.player-board-toggle[aria-expanded="true"]');
    el.players.querySelectorAll('.player-board-toggle').forEach((button) => {
      if ((button.getAttribute('aria-expanded') === 'true') === shouldCollapse) button.click();
    });
  });
  document.getElementById('market-toggle').addEventListener('click', (event) => {
    const toggle = event.currentTarget;
    const isExpanded = toggle.getAttribute('aria-expanded') !== 'true';
    toggle.setAttribute('aria-expanded', String(isExpanded));
    const content = document.getElementById('market-content');
    content.classList.toggle('collapsed', !isExpanded);
    content.inert = !isExpanded;
    if (state.view) render(state.view, true);
  });
  document.querySelectorAll('[data-reference]').forEach((button) => {
    button.addEventListener('click', () => {
      if (!state.view) return;
      const panel = button.dataset.reference;
      document.getElementById('reference-title').textContent = button.textContent;
      const body = document.getElementById('reference-body');
      if (panel === 'species' && !state.view.game.minor_species.length) {
        body.textContent = 'No minor species remaining.';
      } else {
        const image = panelImage(state.view, panel, '', button.textContent);
        if (['ai', 'species'].includes(panel)) {
          image.style.cursor = 'default';
        }
        body.replaceChildren(image);
      }
      document.getElementById('reference-dialog').showModal();
    });
  });
  document.getElementById('new-game').addEventListener('click', () => document.getElementById('new-game-dialog').showModal());
  document.getElementById('new-game-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const button = form.querySelector('[type="submit"]');
    button.disabled = true;
    try {
      const body = Object.fromEntries(new FormData(form));
      body.players = Number(body.players);
      form.querySelectorAll('[type="checkbox"]').forEach((input) => { body[input.name] = input.checked; });
      const response = await fetch('/api/games', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'Could not create game');
      localStorage.setItem('eclipse-game', result.id);
      location.href = '/?seat=1';
    } catch (error) {
      document.getElementById('new-game-error').textContent = error.message;
    } finally {
      button.disabled = false;
    }
  });
  el.game.addEventListener('change', async () => {
    state.gameId = el.game.value;
    state.boardVersion = null;
    state.boardLoaded = false;
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
  window.addEventListener('hashchange', () => {
    if (!state.view) return;
    render(state.view, true);
    window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
    if (!selectedBattle(state.view) && state.boardLoaded) fitBoard();
  });
  window.addEventListener('keydown', (event) => {
    if (!state.previewKey || event.target.closest('input,select,textarea')) return;
    if (event.key === 'ArrowLeft') {
      event.preventDefault();
      rotatePreview(-1);
    } else if (event.key === 'ArrowRight') {
      event.preventDefault();
      rotatePreview(1);
    } else if (event.key === 'Enter' && !event.target.closest('button,a,summary')) {
      event.preventDefault();
      placePreview();
    }
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
  await loadView(true);
  setInterval(() => {
    if (!state.rendering) loadView();
  }, 1500);
}

main();
