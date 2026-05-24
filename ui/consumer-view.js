const agentId = location.pathname.split('/').pop();

const STATE_LABELS = {
  idle:'Idle', discovering:'Discovering', considering:'Considering',
  converting:'Converting', post_purchase:'Post-Purchase',
};
const FUNNEL_STAGES = ['discovering','considering','converting','post_purchase'];

function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function fmt(v,d=2){return typeof v==='number'?v.toFixed(d):v||'—';}
function pct(v){return `${Math.round(v*100)}%`;}
function bar(val,color){return `<div class="trait-bar"><div class="trait-fill" style="width:${Math.round(val*100)}%;background:${color}"></div></div>`;}

async function load(){
  const res = await fetch(`/api/consumer/${agentId}`);
  const c = await res.json();
  if(c.error){document.getElementById('root').innerHTML='<div style="color:var(--red);padding:20px">Consumer not found</div>';return;}
  render(c);
}

function render(c){
  const root = document.getElementById('root');
  const initials = c.name.split(' ').map(w=>w[0]).join('').slice(0,2);

  // Update page title and header
  document.title = `${c.name} — Consumer`;
  document.querySelector('header').insertAdjacentHTML('beforeend',
    `<div style="margin-left:8px;font-size:14px;font-weight:700">${c.name}</div>`);

  const funnelHtml = FUNNEL_STAGES.map(s=>{
    const stages = FUNNEL_STAGES.slice(0, FUNNEL_STAGES.indexOf(c.state)+1);
    const cls = c.state===s ? 'active' : stages.includes(s) ? 'done' : '';
    return `<div class="funnel-stage ${cls}">${s.replace('_','<br>')}</div>`;
  }).join('');

  const interests = (c.shopping_interests||[]).map(i=>`<span class="tag">${i}</span>`).join('');
  const channels = (c.preferred_channels||[]).map(i=>`<span class="tag">${i}</span>`).join('');

  const budPct = Math.max(0,((c.budget-c.total_spent)/c.budget)*100);
  const budColor = budPct>60?'#3fb950':budPct>25?'#d29922':'#f85149';

  const purchasesHtml = (c.purchase_history||[]).slice().reverse().map(p=>`
    <div class="purchase-item">
      <strong>${esc(p.name)}</strong> from ${esc(p.merchant||'')}<br>
      <span style="color:var(--green)">$${fmt(p.price)}</span>
      ${p.order_id?`<span style="color:var(--muted);font-size:11px"> · ${p.order_id}</span>`:''}
    </div>`).join('') || '<div style="color:var(--muted);font-size:12px">No purchases yet</div>';

  const txnHtml = (c.transactions||[]).slice(0,10).map(t=>{
    const sc = t.status==='completed'?'txn-completed':t.status==='abandoned'?'txn-abandoned':'txn-active';
    const steps = (t.funnel_steps||[]).map(s=>
      `<div class="txn-step"><span class="txn-step-stage">${s.stage}</span>&nbsp;${esc(s.details||'')}</div>`
    ).join('');
    return `<div class="txn-card">
      <div class="txn-header" onclick="this.nextElementSibling.classList.toggle('open')">
        <span class="txn-consumer">${esc(t.transaction_id)}</span>
        <span class="txn-status ${sc}">${t.status}</span>
        ${t.total?`<span class="txn-total">$${t.total.toFixed(2)}</span>`:''}
      </div>
      <div class="txn-steps">${steps}</div>
    </div>`;
  }).join('') || '<div style="color:var(--muted);font-size:12px">No transactions yet</div>';

  root.innerHTML = `
    <div style="grid-column:1/-1;background:var(--bg2);border:1px solid var(--border);border-radius:8px;padding:16px 20px;display:flex;align-items:center;gap:16px">
      <div class="detail-avatar consumer">${initials}</div>
      <div>
        <div class="detail-name">${esc(c.name)}</div>
        <div class="detail-sub">${esc(c.occupation)} · ${esc(c.location)}</div>
      </div>
      <div style="margin-left:auto;text-align:right">
        <div class="state-badge s-${c.state}" style="font-size:12px;padding:4px 10px">${STATE_LABELS[c.state]||c.state}</div>
        <div style="margin-top:4px;font-size:11px;color:var(--muted)">${c.purchase_count} purchases · $${fmt(c.total_spent)} spent</div>
      </div>
    </div>

    <div class="detail-section">
      <h3>Demographics</h3>
      <div class="kv-grid">
        <span class="kv-label">Age</span><span class="kv-value">${c.age}</span>
        <span class="kv-label">Gender</span><span class="kv-value">${c.gender}</span>
        <span class="kv-label">Occupation</span><span class="kv-value">${esc(c.occupation)}</span>
        <span class="kv-label">Annual Income</span><span class="kv-value">$${(c.annual_income||0).toLocaleString()}</span>
        <span class="kv-label">Education</span><span class="kv-value">${esc(c.education)}</span>
        <span class="kv-label">Location</span><span class="kv-value">${esc(c.location)}</span>
        <span class="kv-label">Household</span><span class="kv-value">${c.household_size} person${c.household_size!==1?'s':''}</span>
        <span class="kv-label">Credit Score</span><span class="kv-value">${c.credit_score}</span>
      </div>
    </div>

    <div class="detail-section">
      <h3>Behavior Profile</h3>
      <div class="trait-row">
        <span class="trait-label">Price sensitivity</span>
        ${bar(c.price_sensitivity,'#f85149')}
        <span class="trait-val">${pct(c.price_sensitivity)}</span>
      </div>
      <div class="trait-row">
        <span class="trait-label">Brand loyalty</span>
        ${bar(c.brand_loyalty,'#58a6ff')}
        <span class="trait-val">${pct(c.brand_loyalty)}</span>
      </div>
      <div class="trait-row">
        <span class="trait-label">Impulse tendency</span>
        ${bar(c.impulse_tendency,'#ffa657')}
        <span class="trait-val">${pct(c.impulse_tendency)}</span>
      </div>
      <div class="trait-row">
        <span class="trait-label">Research depth</span>
        ${bar(c.research_depth,'#3fb950')}
        <span class="trait-val">${pct(c.research_depth)}</span>
      </div>
      <div style="margin-top:10px">
        <div style="font-size:11px;color:var(--muted);margin-bottom:4px">Shopping interests</div>
        ${interests}
      </div>
      <div style="margin-top:8px">
        <div style="font-size:11px;color:var(--muted);margin-bottom:4px">Preferred channels</div>
        ${channels}
      </div>
    </div>

    <div class="detail-section">
      <h3>Budget</h3>
      <div class="kv-grid" style="margin-bottom:10px">
        <span class="kv-label">Total budget</span><span class="kv-value">$${fmt(c.budget)}</span>
        <span class="kv-label">Total spent</span><span class="kv-value" style="color:var(--green)">$${fmt(c.total_spent)}</span>
        <span class="kv-label">Remaining</span><span class="kv-value" style="color:${budColor}">$${fmt(c.budget-c.total_spent)}</span>
      </div>
      <div class="mini-bar" style="height:8px">
        <div class="mini-fill" style="width:${100-budPct}%;background:${budColor}"></div>
      </div>
      <div style="font-size:11px;color:var(--muted);margin-top:4px">${Math.round(100-budPct)}% of budget used</div>
      <h3 style="margin-top:14px">Current Funnel</h3>
      <div class="funnel-bar">${funnelHtml}</div>
    </div>

    <div class="detail-section">
      <h3>Persona</h3>
      <p style="font-size:12px;line-height:1.6;color:var(--muted)">${esc(c.persona)}</p>
    </div>

    <div class="detail-section" style="grid-column:1/-1">
      <h3>Purchase History (${(c.purchase_history||[]).length})</h3>
      ${purchasesHtml}
    </div>

    <div class="detail-section" style="grid-column:1/-1">
      <h3>Shopping Sessions</h3>
      <div class="txn-list" style="max-height:300px;overflow-y:auto">${txnHtml}</div>
    </div>`;
}

load();
setInterval(load, 8000);
