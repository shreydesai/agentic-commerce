// ── State ──────────────────────────────────────────────────────
let state = { running: false, consumers: [], businesses: [], stats: {}, transactions: [] };
let ws = null;
let allEvents = [];
let allMessages = [];
let currentFilter = 'all';
const MAX_FEED = 200;
const MAX_MSGS = 300;
const revenueHistory = [];  // {t: timestamp_ms, v: cumulative_revenue}
const MAX_REVENUE_POINTS = 60;

// Filter category → event type sets (mirrors simulation/events.py)
const FILTER_SETS = {
  all: null,
  transactions: new Set(['state_change','product_query','agent_question','agent_answer',
    'purchase_completed','purchase_passed','budget_exceeded','review_posted','transaction_update']),
  purchases: new Set(['purchase_completed']),
  reviews: new Set(['review_posted','review_received']),
};

// Tracks which transaction cards the user has expanded (persists across re-renders)
const expandedTxns = new Set();

// ── Network canvas ─────────────────────────────────────────────
const netNodes = {};   // agent_id → {x, y, type, name, label, state}
const netEdges = [];   // {from, to, type, color, alpha, ts}
let rafId = null;

function initCanvas() {
  const canvas = document.getElementById('network-canvas');
  const resize = () => {
    const dpr = window.devicePixelRatio || 1;
    canvas.width = canvas.offsetWidth * dpr;
    canvas.height = canvas.offsetHeight * dpr;
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
  const W = canvas.offsetWidth, H = canvas.offsetHeight;
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
  const dpr = window.devicePixelRatio || 1;
  const W = canvas.offsetWidth, H = canvas.offsetHeight;
  const now = Date.now();
  const EDGE_TTL = 4000;

  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.save();
  ctx.scale(dpr, dpr);

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

  ctx.restore(); // undo DPR scale
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
    else if (msg.type === 'history') hydrateHistory(msg.data);
    else if (msg.type === 'msg') handleMessage(msg.data);
    else if (msg.type === 'msg_history') hydrateMessages(msg.data);
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
      supply_confirmation: '#a3e635', review: '#f472b6', order_rejected: '#f85149',
    };
    addEdge(ev.from_agent_id, ev.to_agent_id, ev.data?.message_type,
      colors[ev.data?.message_type] || ev.color);
  }

  if (ev.event_type === 'purchase_completed' && ev.data?.price) {
    const lastRev = revenueHistory.length > 0 ? revenueHistory[revenueHistory.length-1].v : 0;
    revenueHistory.push({t: Date.now(), v: lastRev + (ev.data.price || 0)});
    if (revenueHistory.length > MAX_REVENUE_POINTS) revenueHistory.shift();
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
  if (currentFilter === 'analytics') renderAnalytics();
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
      <span class="card-hq">${esc(b.headquarters||'')}</span>
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
  const analyticsEl = document.getElementById('analytics-view');
  feedEl.style.display = 'none';
  txnEl.style.display = 'none';
  analyticsEl.style.display = 'none';
  if (f === 'transactions') {
    txnEl.style.display = 'flex';
    renderTxnView(state.transactions || []);
  } else if (f === 'analytics') {
    analyticsEl.style.display = 'flex';
    renderAnalytics();
  } else {
    feedEl.style.display = 'flex';
    renderFeed();
  }
}

function renderFeed() {
  if (currentFilter === 'transactions' || currentFilter === 'analytics') return;
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

  // Agent name lookup for message thread display
  const agentNames = {};
  (state.consumers||[]).forEach(c => { agentNames[c.agent_id] = c.name; });
  (state.businesses||[]).forEach(b => { agentNames[b.agent_id] = b.name; });

  sorted.forEach(txn => {
    const card = document.createElement('div');
    card.className = 'txn-card';
    const isSupply = txn.type === 'supply';
    const statusClass = txn.status === 'completed' ? 'txn-completed'
      : txn.status === 'abandoned' ? 'txn-abandoned' : 'txn-active';
    const statusLabel = (txn.status || '').replace(/_/g, ' ');
    const totalStr = txn.total ? `<span class="txn-total">$${txn.total.toFixed(2)}</span>` : '';

    // Header label: supply transactions show both parties
    const consumerLabel = isSupply
      ? `<span class="txn-supply-badge">📦 Supply</span>${esc(txn.consumer_name)} → ${esc(txn.supplier_name || txn.supplier_id || '?')}`
      : esc(txn.consumer_name || '?');

    const stepsHtml = (txn.funnel_steps||[]).map(s =>
      `<div class="txn-step"><span class="txn-step-stage">${esc(s.stage)}</span>&nbsp;${esc(s.details||'')}</div>`
    ).join('');

    // Inline message thread for this transaction
    const txnMsgs = allMessages.filter(m => m.transaction_id === txn.transaction_id);
    let msgsHtml = '';
    if (txnMsgs.length > 0) {
      const rows = txnMsgs.map(m => {
        const mt = m.data?.message_type || '?';
        const color = MSG_TYPE_COLORS[mt] || '#58a6ff';
        const fromId = m.from_agent_id || m.agent_id || '?';
        const toId   = m.to_agent_id || '?';
        const fromName = agentNames[fromId] || fromId.replace(/^(consumer_|biz_)/, '');
        const toName   = agentNames[toId]   || toId.replace(/^(consumer_|biz_)/, '');
        const ts = new Date(m.timestamp);
        const t  = ts.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit', second:'2-digit'});
        const content = m.data?.content || {};
        const dc = JSON.parse(JSON.stringify(content));
        if (Array.isArray(dc.products)) dc.products = `[${dc.products.length} item(s)]`;
        const prettyJson = JSON.stringify(dc, null, 2);
        const pid = `mp-${m.event_id || Math.random().toString(36).slice(2)}`;
        return `
          <div class="txn-msg-row">
            <div class="txn-msg-header" onclick="toggleMsgPayload('${pid}')">
              <span class="txn-msg-from">${esc(fromName)}</span>
              <span class="txn-msg-arrow">→</span>
              <span class="txn-msg-to">${esc(toName)}</span>
              <span class="txn-msg-type" style="border-color:${color};color:${color}">${esc(mt)}</span>
              <span class="txn-msg-time">${t}</span>
            </div>
            <div class="txn-msg-payload" id="${pid}"><pre>${esc(prettyJson)}</pre></div>
          </div>`;
      }).join('');
      msgsHtml = `
        <div class="txn-msgs">
          <div class="txn-msgs-label">Agent Messages (${txnMsgs.length})</div>
          ${rows}
        </div>`;
    }

    const tid = txn.transaction_id;
    const isOpen = expandedTxns.has(tid);
    card.innerHTML = `
      <div class="txn-header" onclick="toggleTxnCard(this,'${tid}')">
        <span class="txn-consumer">${consumerLabel}</span>
        <span class="txn-status ${statusClass}">${statusLabel}</span>
        ${totalStr}
        <span class="txn-chevron">${isOpen ? '▾' : '▸'}</span>
      </div>
      <div class="txn-body${isOpen ? ' open' : ''}">
        <div class="txn-steps">${stepsHtml || '<div style="font-size:11px;color:var(--muted);padding:4px 0">No steps recorded yet</div>'}</div>
        ${msgsHtml}
      </div>`;
    el.appendChild(card);
  });
  if (!sorted.length) {
    el.innerHTML = '<div style="padding:16px;color:var(--muted);font-size:12px">No transactions yet — start the simulation.</div>';
  }
}

function toggleTxnCard(headerEl, txnId) {
  const body = headerEl.nextElementSibling;
  const nowOpen = body.classList.toggle('open');
  if (nowOpen) expandedTxns.add(txnId);
  else expandedTxns.delete(txnId);
  // Flip chevron
  const chev = headerEl.querySelector('.txn-chevron');
  if (chev) chev.textContent = nowOpen ? '▾' : '▸';
}

function toggleMsgPayload(id) {
  const el = document.getElementById(id);
  if (el) el.classList.toggle('open');
}

// ── Startup modal ──────────────────────────────────────────────
async function initModal() {
  // If the simulation is already running (e.g. user navigated back from a
  // detail page), skip the modal entirely and show the live state instead.
  try {
    const stateRes = await fetch('/api/state');
    const currentState = await stateRes.json();
    if (currentState.running) {
      document.getElementById('startup-modal').classList.add('hidden');
      applyState(currentState);
      return;
    }
  } catch (e) { /* network error — fall through to modal */ }

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
  revenueHistory.splice(0);
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

function hydrateHistory(events) {
  // Server sends events oldest→newest; allEvents is newest→oldest (unshift order)
  const reversed = [...events].reverse();
  allEvents = reversed.concat(allEvents);
  if (allEvents.length > MAX_FEED) allEvents = allEvents.slice(0, MAX_FEED);
  renderFeed();
  updateEdgeCount();
}

function hydrateMessages(events) {
  allMessages = [...events].reverse().concat(allMessages);
  if (allMessages.length > MAX_MSGS) allMessages = allMessages.slice(0, MAX_MSGS);
  if (currentFilter === 'transactions') renderTxnView(state.transactions || []);
}

function handleMessage(ev) {
  allMessages.unshift(ev);
  if (allMessages.length > MAX_MSGS) allMessages = allMessages.slice(0, MAX_MSGS);
  if (currentFilter === 'transactions') renderTxnView(state.transactions || []);
}

// ── ACP Message colours (mirrors canvas edge colours) ─────────
const MSG_TYPE_COLORS = {
  product_query:    '#8b5cf6',
  product_response: '#a78bfa',
  place_order:      '#22c55e',
  order_confirmation:'#3fb950',
  order_rejected:   '#f85149',
  question:         '#f59e0b',
  question_answer:  '#fbbf24',
  supply_order:     '#ffa657',
  supply_confirmation:'#a3e635',
  review:           '#f472b6',
};

function clearFeed() { allEvents = []; renderFeed(); }

// ── Helpers ────────────────────────────────────────────────────
function setText(id, t) { const e = document.getElementById(id); if(e) e.textContent = t; }
function esc(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

// ── Analytics ──────────────────────────────────────────────────
function buildSparkline(data, width, height) {
  if (data.length < 2) return '';
  const pad = 4;
  const w = width - pad*2, h = height - pad*2;
  const minV = 0, maxV = Math.max(1, data[data.length-1].v);
  const pts = data.map((d, i) => {
    const x = pad + (i / (data.length-1)) * w;
    const y = pad + h - ((d.v - minV) / (maxV - minV)) * h;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  const lastPt = pts.split(' ').slice(-1)[0].split(',');
  return `<svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
    <polyline points="${pts}" fill="none" stroke="var(--accent)" stroke-width="1.5" stroke-linejoin="round"/>
    <circle cx="${lastPt[0]}" cy="${lastPt[1]}" r="3" fill="var(--accent)"/>
    <text x="${width-pad}" y="${height-1}" fill="var(--muted)" font-size="9" text-anchor="end">$${data[data.length-1].v.toFixed(0)}</text>
  </svg>`;
}

function renderAnalytics() {
  const el = document.getElementById('analytics-view');
  if (!el) return;

  const stats = state.stats || {};
  const businesses = state.businesses || [];
  const consumers = state.consumers || [];
  const transactions = state.transactions || [];

  // Compute derived stats
  const totalRevenue = stats.total_revenue || 0;
  const totalOrders = stats.total_orders || 0;
  const completedTxns = transactions.filter(t => t.status === 'completed').length;
  const abandonedTxns = transactions.filter(t => t.status === 'abandoned').length;
  const activeTxns = transactions.filter(t => !['completed','abandoned'].includes(t.status)).length;
  const convRate = transactions.length > 0
    ? Math.round(completedTxns / transactions.length * 100) : 0;

  // Top businesses by revenue
  const topBiz = [...businesses]
    .filter(b => b.business_type === 'B2C')
    .sort((a, b) => b.total_revenue - a.total_revenue)
    .slice(0, 5);

  // Consumer spending summary
  const consumerSpend = [...consumers]
    .sort((a, b) => b.total_spent - a.total_spent)
    .slice(0, 5);

  // Strategy notes (businesses with strategy_notes)
  const strategyInsights = businesses
    .filter(b => b.strategy_notes && b.strategy_notes.length > 0)
    .flatMap(b => b.strategy_notes.slice(-1).map(n => `${b.name}: ${n}`))
    .slice(0, 4);

  // Revenue sparkline SVG
  const sparkSVG = buildSparkline(revenueHistory, 280, 50);

  el.innerHTML = `
    <div class="analytics-grid">
      <!-- KPI row -->
      <div class="analytics-kpi-row">
        <div class="kpi-card">
          <div class="kpi-val">$${totalRevenue.toFixed(2)}</div>
          <div class="kpi-label">Total Revenue</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-val">${totalOrders}</div>
          <div class="kpi-label">Orders</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-val">${convRate}%</div>
          <div class="kpi-label">Conv. Rate</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-val">${activeTxns}</div>
          <div class="kpi-label">Active Txns</div>
        </div>
      </div>

      <!-- Revenue chart -->
      <div class="analytics-section">
        <div class="analytics-section-title">Revenue Over Time</div>
        ${revenueHistory.length > 1 ? `<div class="sparkline-wrap">${sparkSVG}</div>` : '<div class="analytics-empty">Purchases will appear here</div>'}
      </div>

      <!-- Funnel breakdown -->
      <div class="analytics-section">
        <div class="analytics-section-title">Transaction Funnel</div>
        <div class="funnel-stats">
          <div class="funnel-stat"><span class="funnel-dot" style="background:#3b82f6"></span>${transactions.length} started</div>
          <div class="funnel-stat"><span class="funnel-dot" style="background:#22c55e"></span>${completedTxns} completed</div>
          <div class="funnel-stat"><span class="funnel-dot" style="background:#6b7280"></span>${abandonedTxns} abandoned</div>
          <div class="funnel-stat"><span class="funnel-dot" style="background:#f59e0b"></span>${activeTxns} in-progress</div>
        </div>
      </div>

      <!-- Top merchants -->
      <div class="analytics-section">
        <div class="analytics-section-title">Merchant Leaderboard</div>
        ${topBiz.length ? topBiz.map((b, i) => `
          <div class="leaderboard-row">
            <span class="lb-rank">#${i+1}</span>
            <span class="lb-name">${esc(b.name)}</span>
            <span class="lb-conv">${b.conversion_rate != null ? Math.round(b.conversion_rate*100)+'% conv' : ''}</span>
            <span class="lb-rev">$${b.total_revenue.toFixed(0)}</span>
          </div>`).join('') : '<div class="analytics-empty">No sales yet</div>'}
      </div>

      <!-- Consumer spending -->
      <div class="analytics-section">
        <div class="analytics-section-title">Consumer Spending</div>
        ${consumerSpend.map(c => {
          const pct = Math.max(2, Math.round((c.total_spent / c.budget) * 100));
          return `<div class="consumer-spend-row">
            <span class="cs-name">${esc(c.name.split(' ')[0])}</span>
            <div class="cs-bar-wrap"><div class="cs-bar-fill" style="width:${pct}%;background:${pct>75?'var(--red)':pct>40?'var(--yellow)':'var(--green)'}"></div></div>
            <span class="cs-amt">$${c.total_spent.toFixed(0)}/$${c.budget.toFixed(0)}</span>
          </div>`;
        }).join('')}
      </div>

      <!-- Strategy insights -->
      ${strategyInsights.length ? `<div class="analytics-section">
        <div class="analytics-section-title">🧠 AI Strategy Notes</div>
        ${strategyInsights.map(s => `<div class="strategy-note">${esc(s)}</div>`).join('')}
      </div>` : ''}
    </div>`;
}

// ── Scenario engine ────────────────────────────────────────────
function openScenarios() {
  document.getElementById('scenario-modal').classList.remove('hidden');
}
function closeScenarios() {
  document.getElementById('scenario-modal').classList.add('hidden');
}

async function triggerScenario(type) {
  const statusEl = document.getElementById('scenario-status');
  statusEl.textContent = `Applying ${type}…`;
  try {
    const r = await fetch(`/api/scenario`, {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({type}),
    });
    const d = await r.json();
    statusEl.textContent = d.message || `✅ ${type} applied`;
    // Refresh state
    const stateRes = await fetch('/api/state');
    applyState(await stateRes.json());
  } catch(e) {
    statusEl.textContent = `❌ Error: ${e.message}`;
  }
}

async function updateSpeed(val) {
  document.getElementById('speed-label').textContent = `${val}×`;
  try {
    await fetch(`/api/speed?factor=${val}`, {method:'POST'});
  } catch(e) { /* ignore */ }
}

// ── Init ───────────────────────────────────────────────────────
connectWS();
initCanvas();
initModal();
