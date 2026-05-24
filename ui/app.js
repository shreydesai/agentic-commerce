// ── State ──────────────────────────────────────────────────────
let state = { running: false, consumers: [], businesses: [], stats: {}, transactions: [] };
let ws = null;
let allEvents = [];
let currentFilter = 'all';
const MAX_FEED = 200;

// Filter category → event type sets (mirrors simulation/events.py)
const FILTER_SETS = {
  all: null,
  transactions: new Set(['state_change','product_query','agent_question','agent_answer',
    'purchase_completed','purchase_passed','budget_exceeded','review_posted','transaction_update']),
  purchases: new Set(['purchase_completed']),
  supply: new Set(['supply_order_sent','supply_order_fulfilled','supply_received','out_of_stock']),
  reviews: new Set(['review_posted','review_received']),
};

// ── Network canvas ─────────────────────────────────────────────
const netNodes = {};   // agent_id → {x, y, type, name, label, state}
const netEdges = [];   // {from, to, type, color, alpha, ts}
let rafId = null;

function initCanvas() {
  const canvas = document.getElementById('network-canvas');
  const resize = () => {
    canvas.width = canvas.offsetWidth;
    canvas.height = canvas.offsetHeight;
    layoutNodes();
  };
  new ResizeObserver(resize).observe(canvas);
  resize();
  rafId = requestAnimationFrame(renderNetwork);

  canvas.addEventListener('click', (e) => {
    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    for (const [id, node] of Object.entries(netNodes)) {
      const dx = x - node.x, dy = y - node.y;
      if (Math.sqrt(dx*dx + dy*dy) <= 16) {
        window.location.href = node.type === 'consumer' ? `/consumer/${id}` : `/business/${id}`;
        return;
      }
    }
  });

  canvas.addEventListener('mousemove', (e) => {
    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    let onNode = false;
    for (const node of Object.values(netNodes)) {
      const dx = x - node.x, dy = y - node.y;
      if (Math.sqrt(dx*dx + dy*dy) <= 16) { onNode = true; break; }
    }
    canvas.style.cursor = onNode ? 'pointer' : 'default';
  });
}

function layoutNodes() {
  const canvas = document.getElementById('network-canvas');
  const W = canvas.width, H = canvas.height;
  const consumers = state.consumers || [];
  const b2c = (state.businesses || []).filter(b => b.business_type === 'B2C');
  const b2b = (state.businesses || []).filter(b => b.business_type === 'B2B');
  const businesses = [...b2c, ...b2b];
  const pad = 30;
  consumers.forEach((c, i) => {
    netNodes[c.agent_id] = {
      x: pad,
      y: H * (i + 1) / (consumers.length + 1),
      type: 'consumer', name: c.name.split(' ')[0], state: c.state,
    };
  });
  businesses.forEach((b, i) => {
    netNodes[b.agent_id] = {
      x: W - pad,
      y: H * (i + 1) / (businesses.length + 1),
      type: b.business_type === 'B2B' ? 'b2b' : 'b2c',
      name: b.name.split(' ')[0],
      state: b.business_type,
      quality: b.quality_score,
    };
  });
}

function addEdge(fromId, toId, msgType, color) {
  // Existing edge? refresh it
  const ex = netEdges.find(e => e.from === fromId && e.to === toId);
  if (ex) { ex.alpha = 1; ex.ts = Date.now(); return; }
  netEdges.push({ from: fromId, to: toId, type: msgType, color: color || '#58a6ff', alpha: 1, ts: Date.now() });
  updateEdgeCount();
}

function updateEdgeCount() {
  const active = netEdges.filter(e => e.alpha > 0.05).length;
  setText('net-edge-count', `${active} active connection${active !== 1 ? 's' : ''}`);
}

function renderNetwork() {
  const canvas = document.getElementById('network-canvas');
  const ctx = canvas.getContext('2d');
  const W = canvas.width, H = canvas.height;
  const now = Date.now();
  const EDGE_TTL = 4000;

  ctx.clearRect(0, 0, W, H);

  // Update & draw edges
  for (let i = netEdges.length - 1; i >= 0; i--) {
    const e = netEdges[i];
    e.alpha = Math.max(0, 1 - (now - e.ts) / EDGE_TTL);
    if (e.alpha < 0.01) { netEdges.splice(i, 1); updateEdgeCount(); continue; }
    const fn = netNodes[e.from], tn = netNodes[e.to];
    if (!fn || !tn) continue;

    ctx.save();
    ctx.globalAlpha = e.alpha;
    ctx.strokeStyle = e.color;
    ctx.lineWidth = 1.5;

    // B2B (same side): curve outward to the right
    const sameSide = (fn.x > W * 0.5) === (tn.x > W * 0.5);
    const cpx = sameSide ? W + 40 : (fn.x + tn.x) / 2;
    const cpy = (fn.y + tn.y) / 2 - (sameSide ? 0 : 20);

    // Animated dash
    ctx.setLineDash([5, 4]);
    ctx.lineDashOffset = -((now / 35) % 9);
    ctx.beginPath();
    ctx.moveTo(fn.x, fn.y);
    ctx.quadraticCurveTo(cpx, cpy, tn.x, tn.y);
    ctx.stroke();

    // Arrow at destination
    ctx.setLineDash([]);
    const t = 0.92;
    const ax = (1-t)*(1-t)*fn.x + 2*(1-t)*t*cpx + t*t*tn.x;
    const ay = (1-t)*(1-t)*fn.y + 2*(1-t)*t*cpy + t*t*tn.y;
    const angle = Math.atan2(tn.y - ay, tn.x - ax);
    ctx.beginPath();
    ctx.moveTo(tn.x, tn.y);
    ctx.lineTo(tn.x - 7*Math.cos(angle-0.4), tn.y - 7*Math.sin(angle-0.4));
    ctx.lineTo(tn.x - 7*Math.cos(angle+0.4), tn.y - 7*Math.sin(angle+0.4));
    ctx.closePath();
    ctx.fillStyle = e.color;
    ctx.fill();
    ctx.restore();
  }

  // Draw nodes
  const STATE_COLORS_NODE = {
    idle: '#21262d', discovering: '#1e3a5f', considering: '#3d2a00',
    converting: '#1a4a2e', post_purchase: '#3d1a3d',
  };
  const BORDER_COLORS = {
    consumer: '#58a6ff', b2c: '#3fb950', b2b: '#ffa657',
  };
  const LABEL_ICONS = { consumer: '👤', b2c: '🏪', b2b: '🏭' };

  for (const [id, node] of Object.entries(netNodes)) {
    const r = 12;
    ctx.save();
    ctx.fillStyle = STATE_COLORS_NODE[node.state] || '#21262d';
    ctx.beginPath(); ctx.arc(node.x, node.y, r, 0, Math.PI*2); ctx.fill();
    ctx.strokeStyle = BORDER_COLORS[node.type] || '#30363d';
    ctx.lineWidth = 2;
    ctx.stroke();

    // Pulse for active consumers
    if (node.type === 'consumer' && node.state && node.state !== 'idle') {
      ctx.strokeStyle = BORDER_COLORS.consumer + '55';
      ctx.lineWidth = 1;
      const pr = r + 4 + 2*Math.sin(now / 400);
      ctx.beginPath(); ctx.arc(node.x, node.y, pr, 0, Math.PI*2); ctx.stroke();
    }

    // Name label
    ctx.fillStyle = '#e6edf3';
    ctx.font = '9px -apple-system, sans-serif';
    ctx.textAlign = 'center';
    const align = node.x < W/2 ? 'left' : 'right';
    ctx.textAlign = align;
    const lx = node.x < W/2 ? node.x + r + 4 : node.x - r - 4;
    ctx.fillText(node.name.substring(0, 10), lx, node.y + 3);
    ctx.restore();
  }

  rafId = requestAnimationFrame(renderNetwork);
}

// ── WebSocket ───────────────────────────────────────────────────
function connectWS() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(`${proto}://${location.host}/ws`);
  ws.onmessage = e => {
    const msg = JSON.parse(e.data);
    if (msg.type === 'state') applyState(msg.data);
    else if (msg.type === 'event') handleEvent(msg.data);
  };
  ws.onclose = () => setTimeout(connectWS, 2000);
}

function handleEvent(ev) {
  allEvents.unshift(ev);
  if (allEvents.length > MAX_FEED) allEvents = allEvents.slice(0, MAX_FEED);

  // Network visualization
  if (ev.from_agent_id && ev.to_agent_id && ev.event_type === 'network_message') {
    const colors = {
      product_query: '#8b5cf6', place_order: '#22c55e', question: '#f59e0b',
      supply_order: '#ffa657', product_response: '#a78bfa',
      order_confirmation: '#3fb950', question_answer: '#fbbf24',
    };
    addEdge(ev.from_agent_id, ev.to_agent_id, ev.data?.message_type,
      colors[ev.data?.message_type] || ev.color);
  }

  renderFeed();

  // Quick-patch stats without waiting for full state
  if (ev.event_type === 'purchase_completed') {
    const rev = parseFloat((document.getElementById('stat-revenue').textContent.replace(/[^0-9.]/g,''))) + (ev.data?.price||0);
    setText('stat-revenue', `💰 $${rev.toFixed(2)}`);
  }
}

// ── State ───────────────────────────────────────────────────────
function applyState(s) {
  state = s;
  updateStats(s.stats);
  updateSimStatus(s.running);
  layoutNodes();
  renderConsumers(s.consumers || []);
  renderB2C((s.businesses||[]).filter(b=>b.business_type==='B2C'));
  renderB2B((s.businesses||[]).filter(b=>b.business_type==='B2B'));
  if (currentFilter === 'transactions') renderTxnView(s.transactions||[]);
}

function updateStats(stats) {
  if (!stats) return;
  setText('stat-revenue', `💰 $${(stats.total_revenue||0).toFixed(2)}`);
  setText('stat-orders', `📦 ${stats.total_orders||0} orders`);
  setText('stat-active', `👤 ${stats.active_consumers||0} active`);
  setText('stat-txn', `🔁 ${stats.active_transactions||0} transactions`);
  setText('stat-events', `📡 ${stats.total_events||0} events`);
}

function updateSimStatus(running) {
  const dot = document.getElementById('status-dot');
  const label = document.getElementById('status-label');
  const btnStop = document.getElementById('btn-stop');
  if (running) {
    dot.className = 'status-dot running';
    label.textContent = 'Running';
    btnStop.disabled = false;
  } else {
    dot.className = 'status-dot';
    label.textContent = 'Stopped';
    btnStop.disabled = true;
  }
}

// ── Consumers ──────────────────────────────────────────────────
function renderConsumers(consumers) {
  const grid = document.getElementById('consumers-grid');
  consumers.forEach(c => {
    let card = document.getElementById(`c-${c.agent_id}`);
    if (!card) {
      card = document.createElement('a');
      card.id = `c-${c.agent_id}`;
      card.href = `/consumer/${c.agent_id}`;
      grid.appendChild(card);
    }
    const budPct = Math.max(0, ((c.budget - c.total_spent) / c.budget) * 100);
    const budColor = budPct > 60 ? '#3fb950' : budPct > 25 ? '#d29922' : '#f85149';
    const sClass = `s-${c.state}`;
    const isActive = c.state !== 'idle';
    card.className = `agent-card${isActive ? ' state-active' : ''}${c.state === 'converting' ? ' state-converting' : ''}`;
    card.innerHTML = `
      <div class="card-row">
        <div class="card-name">${c.name}</div>
        <div class="state-badge ${sClass}">${c.state.replace('_',' ')}</div>
      </div>
      <div class="card-meta">${c.age}yo ${c.occupation} · ${c.location}</div>
      <div class="card-stats">
        <span class="cs">Spent: <span>$${c.total_spent.toFixed(2)}</span></span>
        <span class="cs">Buys: <span>${c.purchase_count}</span></span>
        <span class="cs">Left: <span>$${(c.budget-c.total_spent).toFixed(0)}</span></span>
      </div>
      <div class="mini-bar"><div class="mini-fill" style="width:${budPct}%;background:${budColor}"></div></div>`;
  });
}

// ── Businesses ─────────────────────────────────────────────────
function renderB2C(businesses) {
  const grid = document.getElementById('b2c-grid');
  setText('b2c-count', businesses.length);
  businesses.forEach(b => renderBizCard(grid, b, 'b2c'));
}

function renderB2B(businesses) {
  const grid = document.getElementById('b2b-grid');
  setText('b2b-count', businesses.length);
  businesses.forEach(b => renderBizCard(grid, b, 'b2b'));
}

function renderBizCard(grid, b, typeClass) {
  let card = document.getElementById(`b-${b.agent_id}`);
  if (!card) {
    card = document.createElement('a');
    card.id = `b-${b.agent_id}`;
    card.href = `/business/${b.agent_id}`;
    grid.appendChild(card);
  }
  const qs = b.quality_score || 0;
  const qClass = qs >= 80 ? 'quality-high' : qs >= 60 ? 'quality-mid' : 'quality-low';
  const cardQClass = qs >= 80 ? '' : qs >= 60 ? ' quality-mid' : ' quality-low';
  const vClass = `v-${b.vertical}`;

  // Inventory dots (top 4 products)
  const invItems = Object.entries(b.inventory || {}).slice(0, 4).map(([sku, qty]) => {
    const pName = (b.catalog||{})[sku]?.name || sku;
    const col = qty > 10 ? '#3fb950' : qty > 4 ? '#d29922' : '#f85149';
    return `<div class="inv-item"><div class="inv-dot" style="background:${col}"></div><div class="inv-name" title="${pName}">${pName}</div><div class="inv-qty">${qty}</div></div>`;
  }).join('');

  const typeLabel = b.business_type === 'B2B' ? 'B2B' : b.vertical;
  card.className = `agent-card${cardQClass}`;
  card.innerHTML = `
    <div class="card-row">
      <div class="card-name" style="max-width:150px">${b.name}</div>
      <div class="quality-ring ${qClass}">★${qs}</div>
    </div>
    <div class="card-row" style="margin-bottom:4px">
      <div class="vtag ${vClass}">${typeLabel}</div>
      <span style="font-size:11px;color:var(--muted)">${b.headquarters||''}</span>
    </div>
    <div class="card-stats">
      <span class="cs">Rev: <span>$${b.total_revenue.toFixed(0)}</span></span>
      <span class="cs">Orders: <span>${b.order_count}</span></span>
    </div>
    <div class="inv-grid">${invItems}</div>`;
}

// ── Feed ───────────────────────────────────────────────────────
function setFilter(f) {
  currentFilter = f;
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.toggle('active', b.dataset.filter === f));
  const feedEl = document.getElementById('feed');
  const txnEl = document.getElementById('txn-view');
  if (f === 'transactions') {
    feedEl.style.display = 'none';
    txnEl.style.display = 'flex';
    renderTxnView(state.transactions || []);
  } else {
    feedEl.style.display = 'flex';
    txnEl.style.display = 'none';
    renderFeed();
  }
}

function renderFeed() {
  if (currentFilter === 'transactions') return;
  const filterSet = FILTER_SETS[currentFilter];
  const visible = filterSet ? allEvents.filter(e => filterSet.has(e.event_type)) : allEvents;
  const feed = document.getElementById('feed');
  feed.innerHTML = '';
  visible.slice(0, 120).forEach(ev => {
    if (!ev.message) return;
    const item = document.createElement('div');
    item.className = 'feed-item';
    item.style.borderLeftColor = ev.color || '#30363d';
    const ts = new Date(ev.timestamp);
    const t = ts.toLocaleTimeString([],{hour:'2-digit',minute:'2-digit',second:'2-digit'});
    item.innerHTML = `
      <div class="feed-time">${t}</div>
      <div class="feed-msg">${esc(ev.message)}</div>
      <div class="feed-agent">${esc(ev.agent_name||'')}</div>`;
    feed.appendChild(item);
  });
}

function renderTxnView(transactions) {
  const el = document.getElementById('txn-view');
  el.innerHTML = '';
  const sorted = [...transactions].sort((a,b) => (b.started_at||'').localeCompare(a.started_at||''));
  sorted.forEach(txn => {
    const card = document.createElement('div');
    card.className = 'txn-card';
    const statusClass = txn.status === 'completed' ? 'txn-completed'
      : txn.status === 'abandoned' ? 'txn-abandoned' : 'txn-active';
    const totalStr = txn.total ? `<span class="txn-total">$${txn.total.toFixed(2)}</span>` : '';
    const stepsHtml = (txn.funnel_steps||[]).map(s =>
      `<div class="txn-step"><span class="txn-step-stage">${s.stage}</span>&nbsp;${esc(s.details||'')}</div>`
    ).join('');

    card.innerHTML = `
      <div class="txn-header" onclick="this.nextElementSibling.classList.toggle('open')">
        <span class="txn-consumer">${esc(txn.consumer_name)}</span>
        <span class="txn-status ${statusClass}">${txn.status}</span>
        ${totalStr}
        <span style="font-size:10px;color:var(--muted)">${txn.transaction_id}</span>
      </div>
      <div class="txn-steps">${stepsHtml || '<div style="font-size:11px;color:var(--muted);padding:6px 0">No steps recorded yet</div>'}</div>`;
    el.appendChild(card);
  });
  if (!sorted.length) {
    el.innerHTML = '<div style="padding:16px;color:var(--muted);font-size:12px">No transactions yet — start the simulation.</div>';
  }
}

// ── Startup modal ──────────────────────────────────────────────
async function initModal() {
  const res = await fetch('/api/db-status');
  const data = await res.json();
  const body = document.getElementById('modal-body');
  if (data.has_saved_state && data.meta) {
    const m = data.meta;
    body.innerHTML = `
      <div class="modal-desc">A previous simulation was found. Load it to resume, or start fresh.</div>
      <div class="modal-meta">
        <div>Saved: <span>${new Date(m.saved_at).toLocaleString()}</span></div>
        <div>Consumers: <span>${m.consumers}</span> · B2C: <span>${m.merchants}</span> · B2B: <span>${m.suppliers}</span></div>
        <div>Orders completed: <span>${m.total_orders}</span></div>
      </div>
      <div class="modal-buttons">
        <button class="modal-btn modal-btn-primary" onclick="startSim('load')">📂 Load Previous</button>
        <button class="modal-btn modal-btn-secondary" onclick="startSim('fresh')">🌱 Start Fresh</button>
      </div>`;
  } else {
    body.innerHTML = `
      <div class="modal-desc">5 consumer agents · 8 B2C businesses · 4 B2B suppliers<br>All powered by Claude Haiku.</div>
      <div class="modal-buttons">
        <button class="modal-btn modal-btn-primary" onclick="startSim('fresh')">▶ Start Simulation</button>
      </div>`;
  }
}

async function startSim(mode) {
  document.getElementById('startup-modal').classList.add('hidden');
  const res = await fetch(`/api/start?mode=${mode}`, {method:'POST'});
  const data = await res.json();
  applyState(data.state);
}

async function stopSim() {
  document.getElementById('btn-stop').disabled = true;
  const res = await fetch('/api/stop', {method:'POST'});
  const data = await res.json();
  applyState(data.state);
}

function clearFeed() { allEvents = []; renderFeed(); }

// ── Helpers ────────────────────────────────────────────────────
function setText(id, t) { const e = document.getElementById(id); if(e) e.textContent = t; }
function esc(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

// ── Init ───────────────────────────────────────────────────────
connectWS();
initCanvas();
initModal();
