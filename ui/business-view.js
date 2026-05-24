const agentId = location.pathname.split('/').pop();
function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function fmt(v,d=2){return typeof v==='number'?v.toFixed(d):v||'—';}
function money(v){return `$${(v||0).toLocaleString(undefined,{minimumFractionDigits:0,maximumFractionDigits:0})}`;}

async function load(){
  const res = await fetch(`/api/business/${agentId}`);
  const b = await res.json();
  if(b.error){document.getElementById('root').innerHTML='<div style="color:var(--red);padding:20px">Business not found</div>';return;}
  render(b);
}

function render(b){
  const root = document.getElementById('root');
  const qs = b.quality_score||0;
  const qClass = qs>=80?'quality-high':qs>=60?'quality-mid':'quality-low';
  const avatarClass = b.business_type==='B2B'?'b2b':'business';
  const initials = b.name.split(' ').map(w=>w[0]).join('').slice(0,2);
  document.title = `${b.name} — Business`;

  const vClass = `v-${b.vertical}`;
  const typeLabel = b.business_type==='B2B'?'B2B Supplier':b.vertical;

  // Quality ring (SVG circle)
  const r=28, circ=2*Math.PI*r, filled=circ*(qs/100);
  const qSvg=`<svg width="72" height="72" viewBox="0 0 72 72">
    <circle cx="36" cy="36" r="${r}" fill="none" stroke="var(--bg3)" stroke-width="6"/>
    <circle cx="36" cy="36" r="${r}" fill="none" stroke="${qs>=80?'#3fb950':qs>=60?'#d29922':'#f85149'}"
      stroke-width="6" stroke-dasharray="${filled} ${circ}" stroke-linecap="round"
      transform="rotate(-90 36 36)"/>
    <text x="36" y="40" text-anchor="middle" fill="${qs>=80?'#3fb950':qs>=60?'#d29922':'#f85149'}"
      font-size="14" font-weight="700" font-family="sans-serif">${qs}</text>
  </svg>`;

  const issuesHtml = (b.quality_issues||[]).length
    ? (b.quality_issues||[]).map(i=>`<div class="quality-issue">⚠️ ${esc(i)}</div>`).join('')
    : '<div style="font-size:12px;color:var(--green)">✅ No quality issues detected</div>';

  // Catalog table
  const catalogHtml = Object.entries(b.catalog||{}).map(([sku,p])=>{
    const priceCls = (!p.price||p.price<=0)?'price-zero':'price-ok';
    const priceStr = (!p.price||p.price<=0)?'⚠ $0.00':`$${p.price.toFixed(2)}`;
    const inv = (b.inventory||{})[sku]||0;
    const invColor = inv>10?'#3fb950':inv>4?'#d29922':'#f85149';
    const stars = '★'.repeat(Math.round(p.rating||4))+'☆'.repeat(5-Math.round(p.rating||4));
    return `<tr>
      <td>${esc(sku)}</td>
      <td>${esc(p.name)}</td>
      <td class="${priceCls}">${priceStr}</td>
      <td style="color:${invColor}">${inv}</td>
      <td style="color:var(--yellow);font-size:11px">${stars} (${p.review_count||0})</td>
    </tr>`;
  }).join('');

  // Recent orders
  const ordersHtml = (b.orders||[]).slice().reverse().slice(0,10).map(o=>`
    <div class="purchase-item">
      <strong>${esc(o.product_name)}</strong> → ${esc(o.consumer_name||'')}<br>
      <span style="color:var(--green)">$${fmt(o.total)}</span>
      <span style="color:var(--muted);font-size:11px"> · ${esc(o.order_id)}</span>
    </div>`).join('') || '<div style="color:var(--muted);font-size:12px">No orders yet</div>';

  const suppliersHtml = (b.supplier_ids||[]).map(id=>
    `<a href="/business/${id}" style="display:block;color:var(--accent);font-size:12px;padding:3px 0">${id}</a>`
  ).join('') || '<div style="color:var(--muted);font-size:12px">None</div>';

  const clientsHtml = (b.client_b2c_ids||[]).map(name=>
    `<span class="tag">${esc(name)}</span>`
  ).join('') || '<div style="color:var(--muted);font-size:12px">None yet</div>';

  root.innerHTML = `
    <div style="grid-column:1/-1;background:var(--bg2);border:1px solid var(--border);border-radius:8px;padding:16px 20px;display:flex;align-items:center;gap:16px">
      <div class="detail-avatar ${avatarClass}">${initials}</div>
      <div>
        <div class="detail-name">${esc(b.name)}</div>
        <div class="detail-sub">${esc(b.description||'').substring(0,100)}</div>
        ${b.tagline?`<div style="font-size:12px;color:var(--accent);margin-top:4px;font-style:italic">"${esc(b.tagline)}"</div>`:''}
      </div>
      <div style="margin-left:auto;display:flex;flex-direction:column;align-items:center;gap:4px">
        ${qSvg}
        <div style="font-size:10px;color:var(--muted)">Quality Score</div>
      </div>
    </div>

    <div class="detail-section">
      <h3>Company Info</h3>
      <div class="kv-grid">
        <span class="kv-label">Type</span><span class="kv-value"><span class="vtag ${vClass}">${typeLabel}</span></span>
        <span class="kv-label">Founded</span><span class="kv-value">${b.founded_year||'—'}</span>
        <span class="kv-label">Employees</span><span class="kv-value">${b.employee_count?b.employee_count.toLocaleString():'—'}</span>
        <span class="kv-label">Annual Revenue</span><span class="kv-value">${b.annual_revenue?money(b.annual_revenue):'—'}</span>
        <span class="kv-label">Headquarters</span><span class="kv-value">${esc(b.headquarters||'—')}</span>
      </div>
    </div>

    <div class="detail-section">
      <h3>Performance</h3>
      <div class="kv-grid">
        <span class="kv-label">Simulation Revenue</span><span class="kv-value" style="color:var(--green)">$${fmt(b.total_revenue)}</span>
        <span class="kv-label">Orders Fulfilled</span><span class="kv-value">${b.order_count}</span>
        <span class="kv-label">Products in Catalog</span><span class="kv-value">${Object.keys(b.catalog||{}).length}</span>
        <span class="kv-label">Suppliers</span><span class="kv-value">${(b.supplier_ids||[]).length}</span>
        ${b.business_type==='B2B'?`<span class="kv-label">MOQ</span><span class="kv-value">${b.minimum_order_qty} units</span>`:''}
        ${b.business_type==='B2B'?`<span class="kv-label">Wholesale Discount</span><span class="kv-value">${Math.round((b.wholesale_discount||0)*100)}%</span>`:''}
      </div>
      ${b.business_type==='B2C'?`<div style="margin-top:10px"><h3>Suppliers Used</h3>${suppliersHtml}</div>`:''}
      ${b.business_type==='B2B'?`<div style="margin-top:10px"><h3>Client Businesses</h3>${clientsHtml}</div>`:''}
    </div>

    <div class="detail-section">
      <h3>Quality Score: <span class="${qClass}">${qs}/100</span></h3>
      <div class="quality-issues-list">${issuesHtml}</div>
    </div>

    <div class="detail-section">
      <h3>Policies</h3>
      <div class="kv-grid">
        <span class="kv-label">Returns</span><span class="kv-value">${esc((b.policies||{}).return_policy||'⚠ Not specified')}</span>
        <span class="kv-label">Shipping</span><span class="kv-value">${esc((b.policies||{}).shipping_policy||'⚠ Not specified')}</span>
      </div>
      <div style="margin-top:10px"><h3>FAQs (${(b.faqs||[]).length})</h3>
      ${(b.faqs||[]).length
        ? (b.faqs||[]).map(f=>`<div style="margin-bottom:8px"><div style="font-size:12px;font-weight:600">Q: ${esc(f.question)}</div><div style="font-size:12px;color:var(--muted)">A: ${esc(f.answer)}</div></div>`).join('')
        : '<div style="font-size:12px;color:var(--red)">⚠ No FAQs — hurts quality score</div>'
      }</div>
    </div>

    <div class="detail-section" style="grid-column:1/-1">
      <h3>Product Catalog</h3>
      <table class="catalog-table">
        <thead><tr><th>SKU</th><th>Name</th><th>Price</th><th>Stock</th><th>Rating</th></tr></thead>
        <tbody>${catalogHtml}</tbody>
      </table>
    </div>

    <div class="detail-section" style="grid-column:1/-1">
      <h3>Recent Orders (${b.order_count})</h3>
      ${ordersHtml}
    </div>`;
}

load();
setInterval(load, 8000);
