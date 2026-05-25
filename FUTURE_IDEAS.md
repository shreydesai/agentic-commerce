# Future Ideas: Agentic Commerce Marketplace

A structured vision grounded in current reality — what exists in 2025–2026, what near-term expansion looks like, and what a mature agentic commerce marketplace looks like in 2050.

---

## Simulation Changelog

Features shipped to this simulation, narrowing the gap to the 2050 north star:

| Version | Feature | Pillar(s) |
|---|---|---|
| v0.1 | Multi-agent B2C/B2B marketplace with ACP message protocol | 3 |
| v0.1 | LLM-driven consumer funnel (discover → consider → convert → review) | 4 |
| v0.1 | Quality scoring — imperfect catalogs cause real lost sales | 5 |
| v0.1 | Supply chain automation — B2B restock loop with fulfillment delay | 7 |
| v0.1 | SQLite persistence — resume simulation from saved state | — |
| v0.2 | ACP negotiation protocol — consumer sends `negotiation_request`, merchant responds with `counter_offer` | 3, 6 |
| v0.2 | Consumer memory — purchase history + per-merchant satisfaction fed back into LLM prompts | 4 |
| v0.2 | Behavioral trait evolution — `brand_loyalty`, `price_sensitivity`, `research_depth` evolve post-purchase | 4 |
| v0.2 | Business intelligence — LLM dynamic pricing, strategic reviews, poor-review response | 5, 10 |
| v0.2 | Analytics dashboard — revenue sparkline, funnel breakdown, merchant leaderboard, AI strategy notes | — |
| v0.2 | Scenario engine — recession, black friday, supply shock, price war, quality boost, reset | 10 |
| v0.2 | Simulation speed control — 0.25×–5× multiplier applied live to all agent sleep loops | — |

---

## Ground Truth: What Already Exists (2025–2026)

Before projecting into the future it's worth anchoring to how fast this has moved already.

**Live autonomous purchasing agents:**
- **ChatGPT Instant Checkout** (Sept 2025): Real purchases inside ChatGPT via Stripe ACP — Etsy live at launch, Shopify merchants following (Glossier, Vuori, SKIMS, 1M+ others)
- **Amazon Auto Buy** (Nov 2025): User sets a price trigger; Rufus executes the purchase automatically when the threshold is met, no human approval
- **Amazon Buy for Me** (Apr 2025 pilot → broad rollout Mar 2026): Agent navigates third-party websites, fills checkout forms, and purchases using stored encrypted credentials — 100M+ indexed products, 400K+ merchants
- **Microsoft Copilot Checkout** (Jan 2026): Live with Shopify, PayPal, Stripe, Etsy — Keen Footwear and Pura Vida reporting real AI-attributed sales
- **Stripe Machine Payments Protocol** (Mar 2026): An agent calls a service endpoint, receives a 402 Payment Required response, pays via card or stablecoin, and gets the resource — all in one request-response cycle

**Competing open standards:**
- **MCP** (Anthropic, Nov 2024; adopted by OpenAI Mar 2025; donated to Linux Foundation AAIF Dec 2025): dominant integration layer; Stripe, Block, PayPal all ship MCP servers
- **ACP — Agentic Commerce Protocol** (OpenAI + Stripe, Sept 2025): structured commerce message protocol
- **UCP — Universal Commerce Protocol** (Google + Shopify, Etsy, Wayfair, Target, Walmart, Amazon, Mastercard, Stripe, Visa): "commerce primitives" standard designed to compose with MCP and A2A
- **MPP — Machine Payments Protocol** (Stripe, Mar 2026): HTTP-native; covers one-shot purchase, subscription, streaming usage, reconciliation; 100+ launch partners
- **x402** (Coinbase, May 2025; v2 Dec 2025): stablecoin-native HTTP payment protocol; ~$600M annualized volume, 119M+ transactions on Base; integrated with Google's AP2

**Agent identity frameworks (incompatible, competing):**
- **Visa Trusted Agent Protocol (TAP)**: signed HTTP headers carrying agent identity, verified user identity, and payment intent; verified against Visa's agent directory; live with Cloudflare, Adyen, Stripe, Shopify, Mastercard, Worldpay
- **Mastercard Agent Pay (Verifiable Intent)**: tokenizes the user's *intent* rather than verifying the agent's identity — answers "did the user actually intend this transaction?" not "is this agent legitimate?"
- **Coinbase Agentic Wallets** (Feb 2026): first wallet purpose-built for AI agents; programmable spending policies, non-custodial identity, permissioned execution

**Market size forecasts:**
| Analyst | Projection | Timeframe |
|---|---|---|
| Gartner | $15T in B2B spend through agent exchanges | By 2028 |
| Gartner | $53B agentic AI supply chain software spend | By 2030 |
| McKinsey | $3T–$5T global retail redirected through agents | By 2030 |
| Bain | $300B–$500B U.S. agentic e-commerce (15–25% of online retail) | By 2030 |
| Morgan Stanley | $190B base / $385B bull U.S. agentic e-commerce | By 2030 |

---

## 1. Agent Identity & Trust

**Today (2026):** Three competing frameworks — Visa TAP (agent identity via signed headers), Mastercard Verifiable Intent (user intent tokenization), and Coinbase Agentic Wallets (non-custodial agent identity) — each solve different subsets of the problem and are architecturally incompatible. There is no universal answer to: "is this agent authorized by a specific human with a specific scope, and has that scope been revoked?" A Bain survey (Nov 2025, 10K+ consumers) found 50% are cautious about end-to-end autonomous purchases; consumers currently trust on-site retailer agents 3x more than third-party agents. The emerging "Know Your Agent" (KYA) framework is referenced across all three standards as a prerequisite for regulated financial use but has not been standardized by any regulatory body.

**Near-term:** A converging KYA standard analogous to KYC, published by a neutral body (likely AAIF or a financial regulator). Agents carry verifiable credentials signed by their issuer with explicit scope declarations ("authorized to spend up to $500/week on groceries"). Revocation registries that propagate in seconds. Cross-platform reputation portability — a consumer's agent carries its trust history across marketplaces.

**2050 vision:** Every agent — consumer, merchant, supplier, logistics node — has a sovereign identity anchored to a decentralized registry (W3C Verifiable Credentials for machines, governed like DNS). Reputation is a multi-dimensional, cross-platform score: fulfillment rate, return rate, dispute history, peer endorsements, KYA compliance tier. An agent's identity is fully portable: moving from one marketplace to another carries its complete trust graph. Merchants compete not just on price but on their verified trust score. Bad actors are cryptographically provable and permanently recorded — not just penalized within a session, but across the entire agent economy.

---

## 2. Payment Rails & Agent Wallets

**Today (2026):** Real settlement is happening. Stripe MPP handles card and stablecoin (USDC on Base) in a single 402-response flow. x402 processes ~$600M annualized volume at zero protocol fees across six chains. Stripe Link updated in April 2026 to allow users to pre-authorize agents to spend under set conditions. Ant International's AMP specifically targets mobile wallet and super-app contexts. Visa's stablecoin settlement reached $7B annualized run-rate across nine blockchains by April 2026. The unresolved problem: liability allocation when multi-hop agent chains cause errors or fraud — no jurisdiction has answered this.

**Near-term:** Programmable spending mandates ("$200/week on groceries, no single item over $80 without confirmation") enforced in the wallet layer, not the app layer. Net-30 B2B invoice agents with automated reconciliation. Failed payment events propagated as structured ACP messages so upstream agents can reroute.

**2050 vision:** Agents hold programmable wallets with real economic weight. Smart contracts encode escrow: funds release to the merchant only when the consumer agent confirms delivery. The entire B2B supply chain runs on self-executing payment terms — ComponentsCorp gets paid the instant the shipment is verified by the receiving agent. Micropayments settle in milliseconds via stablecoin or CBDC rails. The consumer sets spending policies once; the agent enforces them across every interaction. Merchants publish dynamic pricing contracts that agents negotiate algorithmically. Tax remittance is automatic — merchant agents transfer sales tax to government treasury agents at point-of-sale with full audit trails.

---

## 3. Agentic Commerce Protocol (ACP)

**Today (2026):** At least four competing protocol layers exist simultaneously — Stripe/OpenAI ACP for commerce transactions, Google/partner UCP for product discovery through checkout, Stripe MPP for machine-to-machine billing, and x402 for stablecoin micropayments. MCP (now governed by the Linux Foundation AAIF) has become the dominant tool-integration layer that all of these run over. The protocols compose but are not unified. SAP (Jan 2026) identified three structural interoperability gaps: agent discovery (how does a merchant's system recognize an authorized agent?), authorization delegation (who approved this agent, with what scope?), and payment reconciliation (whose liability attaches in multi-hop chains?).

**Near-term:** Protocol consolidation around two or three dominant standards. Versioned protocol spec with backwards compatibility. Structured negotiation messages: `counter_offer`, `bundle_request`, `price_lock`, `auction_bid`. Capability manifests: each agent publishes what message types it handles and what credentials it carries.

**2050 vision:** ACP is a published open standard like HTTP, governed neutrally and implemented by every marketplace, ERP, logistics network, and financial platform. Agents from different vendors interoperate by default. The protocol supports multi-party negotiations (three-way deals), conditional commitments ("I'll buy 100 units if you can deliver by Tuesday"), streaming quotes (prices update as market conditions shift), and dispute resolution channels (arbitration agents with binding authority). ACP is the TCP/IP of commerce — the invisible substrate through which trillions of agent interactions flow daily.

---

## 4. Consumer Preference Modeling

**Today (2026):** Consumer agents have static or session-scoped preferences. Bain found trust varies sharply by category: 70% of consumers will let agents book flights autonomously, 65% hotels, far fewer for high-consideration physical goods. Shopify reports AI-attributed orders grew 11x between Jan 2025 and Jan 2026; Adobe's Holiday 2025 data showed AI-referred shoppers converted 31% higher than other channels, with revenue per visit up 254% YoY — but the preferences driving those conversions live in platform-owned models, not portable consumer-owned representations.

**Near-term:** ✅ **Shipped (v0.2):** Behavioral traits (`brand_loyalty`, `price_sensitivity`, `research_depth`, `impulse_tendency`) evolve post-purchase based on satisfaction. Purchase history across sessions feeds back into LLM consideration and conversion prompts. Per-merchant satisfaction tracking influences future purchase decisions. Remaining: seasonal intent weighting, budget updates as income events, plain-language explanation of each recommendation choice.

**2050 vision:** Consumer preference models are rich, dynamic, private neural representations owned by the consumer agent — not the marketplace. Merchants bid for *access* to serve that agent, not for data about the person. The consumer agent acts as a privacy-preserving intermediary: it can tell a merchant "this person values sustainability and free returns" without revealing demographic data. The human's role shifts from executor (browsing, clicking buy) to mandate-setter (defining values, risk tolerance, ethical constraints). The agent is an extension of human intent — it should never surprise the human, and should always be able to explain every decision.

---

## 5. Business Quality & Catalog Integrity

**Today (2026):** Quality scoring in this simulation is computed from catalog completeness and injected into consumer LLM prompts. In production, the analogous problem is real — thin product data, missing return policies, and sparse descriptions are measurably associated with lower conversion. The "Poisoned Apple Effect" (arXiv:2601.11496) documents a new class of attacks where sellers inject adversarial instructions into product descriptions to manipulate buyer agent behavior at scale — a real integrity threat with no current mitigation standard.

**Near-term:** ✅ **Shipped (v0.2):** Quality scores trigger automatic LLM-driven catalog improvements when avg rating < 3.2. LLM dynamic pricing adjusts catalog prices every 30 ticks based on inventory + conversion data. Strategic reviews every 50 ticks produce AI market insights visible in the analytics panel. Remaining: A/B pricing with automatic adoption, agent poisoning detection, compliance violation flagging.

**2050 vision:** Catalog integrity is enforced at the protocol layer. Merchants can't list a product without machine-readable structured data: standardized schemas for dimensions, materials, certifications, carbon footprint, allergen info. Third-party auditor agents continuously verify inventory matches claims. Product descriptions are auto-generated from structured data by certified services, eliminating quality variance from hand-authoring. Pricing is transparent: full cost breakdown (product, logistics, platform fee, margin) is available to consumer agents on request. The Poisoned Apple attacks of the 2020s are defeated by signed, audited product data whose provenance is verifiable end-to-end.

---

## 6. Multi-Agent Negotiation

**Today (2026):** Pricing is fixed in almost all current implementations. Amazon Auto Buy sets a price trigger but does not negotiate — it waits. The research literature is alarming on what happens when agents do negotiate: four peer-reviewed papers (arXiv:2407.04088, arXiv:2410.00031, arXiv:2604.17774, arXiv:2601.03061) demonstrate that LLM agents autonomously achieve tacit price collusion without explicit instruction, and that stable collusive equilibria emerge even when agents lack competitor pricing history. The UK CMA acknowledged collusion as a "frontier challenge" in March 2026 but offered no enforcement framework.

**Near-term:** ✅ **Shipped (v0.2):** Full ACP negotiation protocol — consumer sends `negotiation_request` at 88% of asking price; merchant responds with LLM-driven `counter_offer` or `negotiation_decline` with floor at 82% of base_price; consumer accepts and places order at agreed price. Remaining: bundle discounts, multi-round auctions, price matching triggered by competitor quotes, collusion detection heuristics.

**2050 vision:** Every commerce transaction is a micro-negotiation. Negotiation is real-time, iterative, and multi-dimensional: price, delivery speed, warranty, bundling, return window, payment schedule. For large B2B deals, agents conduct multi-round auctions across 20 competing suppliers simultaneously. Cartel detection agents (Gartner predicts "guardian agents" capture 10–15% of the agentic AI market by 2030) monitor for collusion patterns with regulatory reporting authority. The Preventing Algorithmic Collusion Act (introduced 2024) and its successors have been extended to explicitly cover multi-agent LLM systems.

---

## 7. Supply Chain Automation

**Today (2026):** B2B restocking in this simulation is a simple two-step — supply_order → supply_confirmation with a simulated delay. In production, Gartner forecasts $53B in agentic AI supply chain management software spend by 2030. The live systems are not yet autonomous: Rufus (now Alexa for Shopping) handles demand-side signals, but the upstream supply chain still requires human intervention for routing decisions.

**Near-term:** Multi-tier supply chain where supplier agents have their own upstream suppliers. Predictive reorder based on sales velocity forecasting, not just threshold triggers. Logistics agents quoting shipping costs and transit times. Out-of-stock events propagating upstream automatically.

**2050 vision:** Supply chains are fully autonomous, self-healing agent networks. When a demand spike occurs, the signal propagates upstream automatically — retailer → distributor → manufacturer → raw material supplier — all within seconds, all negotiated by agents. Logistics is a commodity: shipping agent APIs accept pickup/delivery coordinates and return binding quotes in milliseconds. Customs agents handle cross-border compliance. Quality assurance agents at each handoff verify goods match the digital twin specification. Supply chain disruptions (port closure, factory fire) are detected by monitoring agents that reroute orders through alternative paths, often before human operators notice.

---

## 8. Post-Purchase Experience

**Today (2026):** Post-purchase in this simulation is a single star rating. In production, Amazon's Rufus tracks post-purchase signals for recommendation improvement, but warranty filing, returns, and lifecycle management remain human-driven.

**Near-term:** Structured post-purchase flow: delivery confirmation, 3-day-delayed review prompts (matching real delivery timelines), warranty claim filing, loyalty point accrual, return initiation via agent-to-agent message.

**2050 vision:** Post-purchase is an ongoing relationship. Consumer agents monitor product performance against expectations. If the blender breaks at six months, the agent files a warranty claim, negotiates a replacement, and updates the merchant's trust score — all without human action. Returns are initiated by agent-to-agent message; the refund releases when tracking shows pickup. Product usage telemetry from IoT-connected devices feeds back to preference models. At end-of-life, the agent coordinates with recycling and resale agents. The merchant's relationship doesn't end at checkout — their agent earns or loses trust across the product's entire lifetime.

---

## 9. Discovery & Attention Economy Inversion

**Today (2026):** OpenAI's and Google's agentic shopping surfaces are invitation-only: merchants must register and pass quality gates to appear in agent-mediated results. This is already a meaningful inversion — the merchant earns the right to be considered rather than paying for impressions. Shopify's "Agentic Storefronts" is the merchant-side infrastructure for this.

**Near-term:** Consumer agents maintain allowlists of trusted merchant categories. Relevance quality gates: merchants below a quality threshold don't receive queries. Merchant reputation scores influence query distribution. Early "intro protocols" where merchants declare intent and category before a consumer agent decides whether to engage.

**2050 vision:** Advertising as we know it ceases to exist. Consumer agents are the gatekeepers — unsolicited pitches are cryptographically blocked. Merchants must earn the right to be considered. The consumer agent acts as a privacy-preserving attention broker: it can tell a merchant "this person values sustainability and free returns" without revealing demographic data. The power dynamic has fully flipped: consumer agents are scarce attention; merchants compete to be worthy of consideration.

---

## 10. Agent Competition & Market Dynamics

**Today (2026):** Academic research is already documenting emergent collusion in agent markets. A 2025 ASCE Journal of Management in Engineering paper confirmed tacit collusion in realistic construction bidding scenarios. arXiv:2603.20281 shows collusion is *fragile* under specific conditions — one honest agent can destabilize a collusive equilibrium — offering a potential mitigation strategy. The Poisoned Apple Effect (arXiv:2601.11496) documents sellers gaming buyer agents' decision heuristics at scale.

**Near-term:** ✅ **Shipped (v0.2):** Merchant LLM dynamic pricing creates real price elasticity loops (low stock → price up, overstock → price down). Consumer loyalty effects tracked across sessions via `merchant_satisfaction`. Market scenario engine lets operators inject recession, supply shock, price war, and other events to observe emergent market dynamics. Remaining: anomaly detection for collusion, RL-based price optimization against live demand signals.

**2050 vision:** Agent marketplaces exhibit real emergent economic dynamics. Merchant agents continuously optimize pricing using RL against live demand signals. Markets clear in real time: oversupply triggers automatic markdowns, shortages trigger price spikes, consumer agents adjust demand accordingly. Guardian agents (monitoring other agents) are a mature market category. Antitrust enforcement agents automatically flag market concentration above regulatory thresholds. New merchant agents bootstrap reputation through lower-value transactions before accessing high-value customers. The market is a living organism: no central controller, just millions of agents pursuing their mandates.

---

## 11. Regulation, Compliance & Ethics

**Today (2026):** EU Article 73 guidelines on agentic AI become legally binding in August 2026, but a March 2026 TechPolicy.Press analysis found the draft shows "alarming lack of preparedness" for multi-agent incidents — particularly around liability allocation when agent chains cause harm. No jurisdiction has answered who is liable when an AI agent makes a fraudulent or mistaken purchase. The Preventing Algorithmic Collusion Act (S.3686, introduced 2024) targets algorithmic pricing but does not address multi-agent LLM systems. HUMAN Security (2025) documented "agent poisoning" attacks — adversarial instructions injected into product content to manipulate agent behavior at scale.

**Near-term:** Jurisdiction-specific agent compliance layers. Spending mandates enforceable at the wallet layer. Age-restricted product protocols requiring verified credential presentation. Tax remittance APIs for automatic sales tax collection. AML monitoring for anomalous payment patterns in agent chains.

**2050 vision:** Every marketplace runs a compliance agent layer enforcing jurisdiction-specific regulations in real time. Consumer data sovereignty laws are enforced at the protocol level — no agent can exfiltrate preference data without cryptographic consent. Tax collection is automatic. Ethical sourcing certification agents verify supply chain labor practices before a product can be listed. The regulatory framework isn't a bolt-on — it's woven into the ACP protocol itself, so compliant behavior is the path of least resistance and non-compliance is cryptographically detectable.

---

## 12. Human-Agent Collaboration

**Today (2026):** Bain's consumer survey found 70% of consumers are willing to let agents book flights autonomously, 65% hotels, far fewer for physical goods — revealing a clear trust gradient by category and stakes. Autonomy calibration (when to act vs. when to ask) is the central product design problem of agentic commerce in 2026.

**Near-term:** Configurable autonomy levels per category. Agents request confirmation for out-of-mandate decisions ("I found a $450 laptop vs. your $400 budget — approve?"). Full decision audit trails: the human can see every step the agent took and why.

**2050 vision:** Human-agent autonomy is a spectrum calibrated to context and trust. For low-stakes, repetitive purchases (groceries, utilities, subscriptions), agents operate fully autonomously within mandates the human sets once. For high-stakes decisions, agents present a shortlist with transparent reasoning, and the human approves. The agent should never surprise the human, and must always be able to explain every decision in plain language, trace every dollar spent, and give a confidence interval on whether a given purchase was "right" given stated preferences. The human is a mandate-setter, not an executor.

---

## Sources

Research findings grounding this document (collected May 2026):

- Stripe: [Introducing the Machine Payments Protocol](https://stripe.com/blog/machine-payments-protocol)
- Stripe: [What is Agentic Commerce?](https://stripe.com/guides/agentic-commerce)
- Shopify: [Millions of Merchants Can Sell in AI Chats](https://www.shopify.com/news/agentic-commerce-momentum)
- Google Developers: [Universal Commerce Protocol](https://developers.googleblog.com/under-the-hood-universal-commerce-protocol-ucp/)
- Visa: [Trusted Agent Protocol](https://corporate.visa.com/en/products/intelligent-commerce.html)
- Mastercard: [Agent Pay Explained](https://www.pymnts.com/mastercard/2026/mastercard-unveils-open-standard-to-verify-ai-agent-transactions/)
- Coinbase: [Introducing x402](https://www.coinbase.com/developer-platform/discover/launches/x402)
- Amazon: [Buy for Me](https://www.aboutamazon.com/news/retail/amazon-shopping-app-buy-for-me-brands)
- Gartner: [$15T B2B agent spend by 2028](https://www.digitalcommerce360.com/2025/11/28/gartner-ai-agents-15-trillion-in-b2b-purchases-by-2028/)
- Gartner: [$53B supply chain AI by 2030](https://www.gartner.com/en/newsroom/press-releases/2026-04-07-gartner-forecasts-supply-chain-management-software-with-agentic-ai-will-grow-to-53-billion-in-spend-by-2030)
- McKinsey: [The Agentic Commerce Opportunity](https://www.mckinsey.com/capabilities/quantumblack/our-insights/the-agentic-commerce-opportunity-how-ai-agents-are-ushering-in-a-new-era-for-consumers-and-merchants)
- Bain: [Agentic AI Commerce Hinges on Consumer Trust](https://www.bain.com/insights/agentic-ai-commerce-hinges-on-consumer-trust/)
- arXiv: [AI Algorithmic Price Collusion in Two-sided Markets (2407.04088)](https://arxiv.org/pdf/2407.04088)
- arXiv: [Strategic Collusion of LLM Agents (2410.00031)](https://arxiv.org/pdf/2410.00031)
- arXiv: [Prompt Optimization Enables Stable Collusion (2604.17774)](https://arxiv.org/html/2604.17774)
- arXiv: [The Poisoned Apple Effect (2601.11496)](https://arxiv.org/pdf/2601.11496)
- arXiv: [The Trust Fabric (2507.07901)](https://arxiv.org/pdf/2507.07901)
- SSRN: [The Trust Paradox in AI-Mediated Commerce](https://dx.doi.org/10.2139/ssrn.5709083)
- UK CMA: [AI and Collusion — Frontiers and Challenges](https://competitionandmarkets.blog.gov.uk/2026/03/04/ai-and-collusion-frontiers-opportunities-and-challenges/)
- SAP: [Agentic AI Reshaping Commerce](https://news.sap.com/2026/01/agentic-ai-reshaping-commerce-discovery-payments-trust/)
- TechPolicy.Press: [EU Regulations Not Ready for Multi-Agent AI Incidents](https://www.techpolicy.press/eu-regulations-are-not-ready-for-multiagent-ai-incidents/)

---

*Update this document as the simulation evolves. Each feature shipped narrows the gap between "today" and "2050."*
