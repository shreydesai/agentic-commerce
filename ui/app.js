// ── State ──────────────────────────────────────────────────────
let state = { running: false, consumers: [], merchants: [], suppliers: [], stats: {}, recent_events: [] };
let ws = null;
let feedItems = [];
const MAX_FEED = 150;

const VERTICAL_CLASSES = {
  electronics: 'v-electronics', gaming: 'v-gaming', fashion: 'v-fashion',
  grocery: 'v-grocery', home: 'v-home', wholesale: 'v-wholesale',
};

const STATE_CLASSES = {
  idle: 'state-idle', discovering: 'state-discovering', considering: 'state-considering',
  converting: 'state-converting', post_purchase: 'state-post_purchase',
};

const STATE_LABELS = {
  idle: 'Idle', discovering: 'Discovering', considering: 'Considering',
  converting: 'Converting', post_purchase: 'Post-Purchase',
};

// ── WebSocket ───────────────────────────────────────────────────
function connectWS() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(`${proto}://${location.host}/ws`);
  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    if (msg.type === 'state') applyState(msg.data);
    else if (msg.type === 'event') addFeedItem(msg.data);
  };
  ws.onclose = () => setTimeout(connectWS, 2000);
}

// ── State Application ───────────────────────────────────────────
function applyState(s) {
  state = s;
  updateStats(s.stats);
  updateSimStatus(s.running);
  renderConsumers(s.consumers);
  renderMerchants(s.merchants);
  renderSuppliers(s.suppliers);
}

function updateStats(stats) {
  if (!stats) return;
  setText('stat-revenue', `💰 $${(stats.total_revenue || 0).toFixed(2)}`);
  setText('stat-orders', `📦 ${stats.total_orders || 0} orders`);
  setText('stat-active', `👤 ${stats.active_consumers || 0} active`);
  setText('stat-events', `📡 ${stats.total_events || 0} events`);
}

function updateSimStatus(running) {
  const dot = document.querySelector('.status-dot');
  const label = document.getElementById('status-label');
  const btnStart = document.getElementById('btn-start');
  const btnStop = document.getElementById('btn-stop');
  if (running) {
    dot.className = 'status-dot running';
    label.textContent = 'Running';
    btnStart.disabled = true;
    btnStop.disabled = false;
  } else {
    dot.className = 'status-dot idle';
    label.textContent = 'Stopped';
    btnStart.disabled = false;
    btnStop.disabled = true;
  }
}

// ── Consumers ──────────────────────────────────────────────────
function renderConsumers(consumers) {
  const grid = document.getElementById('consumers-grid');
  consumers.forEach(c => {
    let card = document.getElementById(`consumer-${c.agent_id}`);
    const isNew = !card;
    if (isNew) {
      card = document.createElement('div');
      card.id = `consumer-${c.agent_id}`;
      card.className = 'agent-card';
      grid.appendChild(card);
    }
    const budgetPct = Math.max(0, ((c.budget - c.total_spent) / c.budget) * 100);
    const budgetColor = budgetPct > 60 ? '#3fb950' : budgetPct > 25 ? '#d29922' : '#f85149';
    const stateClass = STATE_CLASSES[c.state] || 'state-idle';
    const stateLabel = STATE_LABELS[c.state] || c.state;
    const isActive = c.state !== 'idle';
    card.className = `agent-card${isActive ? ' active' : ''}${c.state === 'converting' ? ' purchasing' : ''}`;
    card.innerHTML = `
      <div class="agent-card-header">
        <div class="agent-name">${c.name}</div>
        <div class="state-badge ${stateClass}">${stateLabel}</div>
      </div>
      <div class="agent-meta" title="${c.persona}">${c.persona.substring(0, 60)}…</div>
      <div class="agent-stats">
        <div class="agent-stat">Spent: <span>$${c.total_spent.toFixed(2)}</span></div>
        <div class="agent-stat">Bought: <span>${c.purchase_count}</span></div>
        <div class="agent-stat">Budget: <span>$${(c.budget - c.total_spent).toFixed(0)}</span></div>
      </div>
      <div class="budget-bar">
        <div class="budget-fill" style="width:${budgetPct}%;background:${budgetColor}"></div>
      </div>
    `;
    if (!isNew) card.classList.add('card-updated');
  });
}

// ── Merchants ──────────────────────────────────────────────────
function renderMerchants(merchants) {
  const grid = document.getElementById('merchants-grid');
  merchants.forEach(m => {
    let card = document.getElementById(`merchant-${m.agent_id}`);
    const isNew = !card;
    if (isNew) {
      card = document.createElement('div');
      card.id = `merchant-${m.agent_id}`;
      card.className = 'agent-card';
      grid.appendChild(card);
    }
    const vClass = VERTICAL_CLASSES[m.vertical] || 'v-wholesale';

    // Build inventory rows
    const invRows = Object.entries(m.inventory || {}).map(([sku, qty]) => {
      const product = (m.catalog || {})[sku];
      const name = product ? product.name : sku;
      const maxStock = 30;
      const pct = Math.min(100, (qty / maxStock) * 100);
      const color = qty > 10 ? '#3fb950' : qty > 4 ? '#d29922' : '#f85149';
      return `
        <div class="inv-row">
          <div class="inv-label" title="${name}">${name}</div>
          <div class="inv-bar"><div class="inv-fill" style="width:${pct}%;background:${color}"></div></div>
          <div class="inv-count">${qty}</div>
        </div>`;
    }).join('');

    card.innerHTML = `
      <div class="agent-card-header">
        <div class="agent-name">${m.name}</div>
        <div class="vertical-tag ${vClass}">${m.vertical}</div>
      </div>
      <div class="agent-meta">${m.description.substring(0, 55)}…</div>
      <div class="agent-stats">
        <div class="agent-stat">Revenue: <span>$${m.total_revenue.toFixed(2)}</span></div>
        <div class="agent-stat">Orders: <span>${m.order_count}</span></div>
      </div>
      <div class="inventory-list">${invRows}</div>
    `;
    if (!isNew) card.classList.add('card-updated');
  });
}

// ── Suppliers ─────────────────────────────────────────────────
function renderSuppliers(suppliers) {
  const grid = document.getElementById('suppliers-grid');
  suppliers.forEach(s => {
    let card = document.getElementById(`supplier-${s.agent_id}`);
    const isNew = !card;
    if (isNew) {
      card = document.createElement('div');
      card.id = `supplier-${s.agent_id}`;
      card.className = 'supplier-card';
      grid.appendChild(card);
    }
    const clients = (s.clients || []).join(', ') || 'No clients yet';
    card.innerHTML = `
      <div class="agent-card-header">
        <div class="supplier-name">🏭 ${s.name}</div>
        <div class="vertical-tag v-wholesale">B2B</div>
      </div>
      <div class="supplier-meta">${s.description.substring(0, 55)}…</div>
      <div class="agent-stats" style="margin-top:4px">
        <div class="agent-stat">Fulfilled: <span>${s.orders_fulfilled}</span></div>
        <div class="agent-stat">Clients: <span>${(s.clients||[]).length}</span></div>
      </div>
    `;
  });
}

// ── Feed ───────────────────────────────────────────────────────
function addFeedItem(event) {
  if (!event.message) return;
  feedItems.unshift(event);
  if (feedItems.length > MAX_FEED) feedItems = feedItems.slice(0, MAX_FEED);

  const feed = document.getElementById('feed');
  const item = document.createElement('div');
  item.className = 'feed-item';
  item.style.borderLeftColor = event.color || '#30363d';

  const ts = new Date(event.timestamp);
  const time = ts.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  const agentLabel = event.agent_name || '';

  item.innerHTML = `
    <div class="feed-time">${time}</div>
    <div class="feed-msg">${escapeHtml(event.message)}</div>
    <div class="feed-agent">${escapeHtml(agentLabel)}</div>
  `;

  feed.insertBefore(item, feed.firstChild);

  // Trim old items from DOM
  while (feed.children.length > MAX_FEED) feed.removeChild(feed.lastChild);
}

function clearFeed() {
  feedItems = [];
  document.getElementById('feed').innerHTML = '';
}

// ── Controls ───────────────────────────────────────────────────
async function startSim() {
  document.getElementById('btn-start').disabled = true;
  const res = await fetch('/api/start', { method: 'POST' });
  const data = await res.json();
  applyState(data.state);
}

async function stopSim() {
  document.getElementById('btn-stop').disabled = true;
  const res = await fetch('/api/stop', { method: 'POST' });
  const data = await res.json();
  applyState(data.state);
}

// ── Helpers ────────────────────────────────────────────────────
function setText(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

// ── Init ───────────────────────────────────────────────────────
connectWS();
