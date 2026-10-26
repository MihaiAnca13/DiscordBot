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
  status: document.getElementById('status'),
  mirror: document.getElementById('mirror'),
  turnMenu: document.getElementById('turn-menu'),
  board: document.getElementById('board'),
  boardNote: document.getElementById('board-note'),
  banner: document.getElementById('banner'),
  messages: document.getElementById('messages'),
  error: document.getElementById('error'),
};

const state = { gameId: null, seat: '', view: null, boardVersion: null, rendering: false };

function showError(text) {
  if (!text) {
    el.error.classList.remove('on');
    return;
  }
  el.error.textContent = text;
  el.error.classList.add('on');
  setTimeout(() => el.error.classList.remove('on'), 8000);
}

const escapeHtml = (text) => (text || '')
  .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');

// Discord-flavoured text. Custom emoji are public CDN images, so show them.
function bodyHtml(content) {
  return escapeHtml(content || '')
    .replace(/^\s*##\s+(.*)$/gm, '<h3>$1</h3>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/&lt;(a?):([\w]+):(\d+)&gt;/g, (_m, animated, name, id) =>
      `<img class="emoji" alt=":${name}:" loading="lazy" `
      + `src="https://cdn.discordapp.com/emojis/${id}.${animated ? 'gif' : 'png'}">`);
}

function styleClass(style) {
  return `s${[1, 2, 3, 4, 5].includes(style) ? style : 2}`;
}

function renderMessage(message) {
  const node = document.createElement('div');
  node.className = `message${message.private ? ' private' : ''}`;
  const meta = document.createElement('div');
  meta.className = 'meta';
  const room = message.room && !message.room.endsWith('-actions') ? ` · ${message.room}` : '';
  meta.textContent = `#${message.id}${room}${message.private ? ' · private' : ''}`;
  node.appendChild(meta);

  const body = document.createElement('div');
  body.className = 'body';
  body.innerHTML = bodyHtml(message.content);
  node.appendChild(body);

  if (message.buttons && message.buttons.length) {
    const row = document.createElement('div');
    row.className = 'buttons';
    for (const button of message.buttons) {
      if (button.url) {
        const link = document.createElement('a');
        link.href = button.url;
        link.target = '_blank';
        link.textContent = button.label || 'link';
        row.appendChild(link);
        continue;
      }
      const pressable = document.createElement('button');
      pressable.className = styleClass(button.style);
      pressable.textContent = button.label || button.custom_id;
      pressable.disabled = !!button.disabled;
      pressable.title = button.custom_id || '';
      pressable.addEventListener('click', () => press(message.id, button.custom_id, pressable));
      row.appendChild(pressable);
    }
    node.appendChild(row);
  }

  for (const attachment of message.attachments || []) {
    const image = document.createElement('img');
    image.src = attachment.url;
    image.alt = attachment.name || '';
    image.loading = 'lazy';
    node.appendChild(image);
  }
  return node;
}

function signature(view) {
  return JSON.stringify({ seat: view.seat, version: view.version, messages: view.messages,
                          mirror: view.mirror_to_discord, you: view.you });
}

function renderFeed(view) {
  const feed = el.messages;
  const atBottom = feed.scrollHeight - feed.scrollTop - feed.clientHeight < 80;
  feed.replaceChildren(...view.messages.map(renderMessage));
  if (atBottom) feed.scrollTop = feed.scrollHeight;
}

function renderSeats(view) {
  const options = view.game.players;
  const wanted = [['', 'spectator'], ...options.map((p) => [p.id, `${p.name} (${p.color})`])];
  const current = viewedSeat(view);
  if (el.seat.dataset.for === options.map((p) => p.id).join(',')) {
    if (el.seat.value !== current) el.seat.value = current;
    return;
  }
  el.seat.dataset.for = options.map((p) => p.id).join(',');
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

function render(view) {
  state.view = view;
  if (view.error) showError(view.error);

  const active = view.game.active || [];
  el.status.textContent = `Round ${view.game.round ?? '?'} · active: ${active.join(', ') || 'nobody'}`
    + (view.you ? ` · you: ${view.you.name}` : ' · spectator');

  el.banner.classList.toggle('on', !!(view.you && view.you.is_your_turn));
  el.banner.textContent = view.you && view.you.is_your_turn
    ? "It's your turn."
    : '';

  renderSeats(view);
  el.mirror.checked = !!view.mirror_to_discord;

  const hasPrompt = view.messages.some((m) => m.buttons && m.buttons.length);
  el.turnMenu.style.display = view.you && !hasPrompt ? '' : 'none';

  if (state.boardVersion !== view.version) {
    state.boardVersion = view.version;
    el.board.src = view.board;
    el.boardNote.textContent = 'rendering board…';
    el.board.onload = () => { el.boardNote.textContent = ''; };
    el.board.onerror = () => { el.boardNote.textContent = 'board render failed (see bot log)'; };
  }

  const key = signature(view);
  if (state.lastKey !== key) {
    state.lastKey = key;
    renderFeed(view);
  }
}

async function loadView() {
  if (!state.gameId) return;
  try {
    const view = await api.view(state.gameId, state.seat);
    render(view);
  } catch (error) {
    showError(`cannot load game: ${error}`);
  }
}

async function press(messageId, customId, button) {
  if (!customId || state.rendering) return;
  state.rendering = true;
  button.disabled = true;
  try {
    const view = await api.press(state.gameId, state.seat, customId, messageId);
    render(view);
  } catch (error) {
    showError(`press failed: ${error}`);
  } finally {
    state.rendering = false;
  }
}

async function loadGames() {
  const games = await api.games();
  const stored = localStorage.getItem('eclipse-game');
  state.gameId = games.some((g) => g.id === stored) ? stored : (games[0] && games[0].id);
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
    await loadView();
  });

  el.seat.addEventListener('change', async () => {
    state.seat = el.seat.value;
    localStorage.setItem(`eclipse-seat-${state.gameId}`, state.seat);
    state.lastKey = null;
    await loadView();
  });

  el.turnMenu.addEventListener('click', async () => {
    if (!state.seat) return;
    try {
      render(await api.turnMenu(state.gameId, state.seat));
    } catch (error) {
      showError(`cannot open turn menu: ${error}`);
    }
  });

  el.mirror.addEventListener('change', async () => {
    try {
      render(await api.mirror(state.gameId, state.seat, el.mirror.checked));
    } catch (error) {
      showError(`cannot change mirror: ${error}`);
    }
  });
}

async function main() {
  bind();
  await loadGames();
  // A seat can come from a link (`?seat=<id>`), which is handy before logins exist.
  const fromUrl = new URLSearchParams(location.search).get('seat');
  if (fromUrl) state.seat = fromUrl;
  await loadView();
  setInterval(loadView, 1500);
}

main();
