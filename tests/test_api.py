"""
End-to-end API tests — protect against route/schema regressions.

These tests use FastAPI's TestClient against the real app with a fresh
SimulationEngine, isolated from any live server instance.  They guard
against the class of breakages discovered in phase 2:

  - /consumer/{id} and /business/{id} returning 404 (old server had no routes)
  - Consumer state dict missing age/occupation/location (causes "undefinedyo")
  - State returning "merchants"/"suppliers" keys instead of "businesses"
  - business_type missing from business objects (breaks B2C/B2B filtering)
"""
import pytest
import api.app as app_module
from simulation.engine import SimulationEngine
from fastapi.testclient import TestClient


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    """
    Module-scoped TestClient with a fresh SimulationEngine.
    Replacing app_module.sim before entering the context ensures the
    lifespan's sim.initialize() and the event forwarder both use the
    isolated instance, not any state from a concurrently running server.
    """
    app_module.sim = SimulationEngine()
    with TestClient(app_module.app) as c:
        yield c


@pytest.fixture
def started_client(client):
    """Start the simulation for tests that need it running; stop on teardown."""
    client.post("/api/start?mode=fresh")
    yield client
    client.post("/api/stop")


# ── Page routes ───────────────────────────────────────────────────────────────

class TestPageRoutes:
    """
    Verify all HTML shell routes exist and return 200.
    The old Phase-1 server had no /consumer or /business routes —
    clicking a card returned {"detail":"Not Found"} (FastAPI 404).
    """

    def test_root_returns_200(self, client):
        assert client.get("/").status_code == 200

    def test_root_is_html(self, client):
        r = client.get("/")
        assert "text/html" in r.headers["content-type"]

    def test_consumer_page_not_404(self, client):
        r = client.get("/consumer/consumer_alex")
        assert r.status_code == 200, (
            f"Got {r.status_code}; old server had no /consumer/{{id}} route"
        )

    def test_consumer_page_is_html(self, client):
        r = client.get("/consumer/consumer_alex")
        assert "text/html" in r.headers["content-type"]

    def test_business_page_not_404(self, client):
        r = client.get("/business/biz_techzone")
        assert r.status_code == 200, (
            f"Got {r.status_code}; old server had no /business/{{id}} route"
        )

    def test_business_page_is_html(self, client):
        r = client.get("/business/biz_techzone")
        assert "text/html" in r.headers["content-type"]

    def test_unknown_consumer_page_still_serves_shell(self, client):
        # The HTML shell is always served; the JS handles 404 internally
        r = client.get("/consumer/does_not_exist")
        assert r.status_code == 200

    def test_unknown_business_page_still_serves_shell(self, client):
        r = client.get("/business/does_not_exist")
        assert r.status_code == 200


# ── Static assets ─────────────────────────────────────────────────────────────

class TestStaticAssets:
    """All JS and CSS files the detail pages depend on must be served."""

    def test_style_css(self, client):
        assert client.get("/static/style.css").status_code == 200

    def test_app_js(self, client):
        assert client.get("/static/app.js").status_code == 200

    def test_consumer_view_js(self, client):
        assert client.get("/static/consumer-view.js").status_code == 200

    def test_business_view_js(self, client):
        assert client.get("/static/business-view.js").status_code == 200

    def test_consumer_html_shell(self, client):
        assert client.get("/static/consumer.html").status_code == 200

    def test_business_html_shell(self, client):
        assert client.get("/static/business.html").status_code == 200


# ── /api/state structure ──────────────────────────────────────────────────────

class TestStateStructure:
    """
    Guard the shape of GET /api/state — the frontend's primary data source.
    Old code returned 'merchants'/'suppliers'; new code must return 'businesses'.
    """

    def test_state_200(self, client):
        assert client.get("/api/state").status_code == 200

    def test_state_has_businesses_key(self, client):
        s = client.get("/api/state").json()
        assert "businesses" in s, "Key 'businesses' missing — UI B2C/B2B filter will break"

    def test_state_no_merchants_key(self, client):
        s = client.get("/api/state").json()
        assert "merchants" not in s, "Old 'merchants' key found — remove it"

    def test_state_no_suppliers_key(self, client):
        s = client.get("/api/state").json()
        assert "suppliers" not in s, "Old 'suppliers' key found — remove it"

    def test_state_has_consumers_key(self, client):
        s = client.get("/api/state").json()
        assert "consumers" in s
        assert isinstance(s["consumers"], list)

    def test_state_has_stats_key(self, client):
        s = client.get("/api/state").json()
        assert "stats" in s

    def test_state_has_transactions_key(self, client):
        s = client.get("/api/state").json()
        assert "transactions" in s

    def test_state_stats_fields(self, client):
        stats = client.get("/api/state").json()["stats"]
        for field in ("total_revenue", "total_orders", "active_consumers",
                      "active_transactions", "total_events"):
            assert field in stats, f"stats.{field} missing"

    def test_state_consumer_count(self, client):
        s = client.get("/api/state").json()
        assert len(s["consumers"]) == 5

    def test_state_business_count(self, client):
        s = client.get("/api/state").json()
        assert len(s["businesses"]) == 12

    def test_state_b2c_count(self, client):
        s = client.get("/api/state").json()
        b2c = [b for b in s["businesses"] if b.get("business_type") == "B2C"]
        assert len(b2c) == 8

    def test_state_b2b_count(self, client):
        s = client.get("/api/state").json()
        b2b = [b for b in s["businesses"] if b.get("business_type") == "B2B"]
        assert len(b2b) == 4

    def test_state_running_is_bool(self, client):
        s = client.get("/api/state").json()
        assert isinstance(s["running"], bool)


# ── Consumer state dict fields ────────────────────────────────────────────────

# Fields the god-view card and consumer detail page render directly.
# Any missing field shows as "undefined" in the browser.
CONSUMER_CARD_FIELDS = [
    "agent_id", "name", "age", "occupation", "location",   # card-meta: "28yo Engineer · SF"
    "state", "total_spent", "purchase_count", "budget",    # card-stats
]
CONSUMER_DETAIL_FIELDS = CONSUMER_CARD_FIELDS + [
    "gender", "annual_income", "education", "household_size", "credit_score",
    "price_sensitivity", "brand_loyalty", "impulse_tendency", "research_depth",
    "shopping_interests", "preferred_channels", "persona",
]


class TestConsumerStateFields:
    """
    Every field the UI renders must be present in the state dict.
    Absence causes the literal string 'undefined' in the browser.
    """

    def test_consumer_card_fields_present(self, client):
        consumers = client.get("/api/state").json()["consumers"]
        for c in consumers:
            missing = [f for f in CONSUMER_CARD_FIELDS if f not in c]
            assert missing == [], f"{c.get('name')} missing card fields: {missing}"

    def test_consumer_detail_fields_present(self, client):
        consumers = client.get("/api/state").json()["consumers"]
        for c in consumers:
            missing = [f for f in CONSUMER_DETAIL_FIELDS if f not in c]
            assert missing == [], f"{c.get('name')} missing detail fields: {missing}"

    def test_consumer_age_is_int(self, client):
        for c in client.get("/api/state").json()["consumers"]:
            assert isinstance(c["age"], int), f"{c['name']}: age must be int, got {type(c['age'])}"

    def test_consumer_location_is_nonempty_string(self, client):
        for c in client.get("/api/state").json()["consumers"]:
            assert isinstance(c["location"], str) and c["location"], \
                f"{c['name']}: location is empty or not a string"

    def test_consumer_occupation_is_nonempty_string(self, client):
        for c in client.get("/api/state").json()["consumers"]:
            assert isinstance(c["occupation"], str) and c["occupation"], \
                f"{c['name']}: occupation is empty or not a string"

    def test_consumer_total_spent_is_number(self, client):
        for c in client.get("/api/state").json()["consumers"]:
            assert isinstance(c["total_spent"], (int, float)), \
                f"{c['name']}: total_spent must be numeric"

    def test_consumer_budget_is_positive(self, client):
        for c in client.get("/api/state").json()["consumers"]:
            assert c["budget"] > 0, f"{c['name']}: budget must be > 0"

    def test_consumer_state_is_valid_value(self, client):
        valid = {"idle", "discovering", "considering", "converting", "post_purchase"}
        for c in client.get("/api/state").json()["consumers"]:
            assert c["state"] in valid, f"{c['name']}: unknown state '{c['state']}'"

    def test_consumer_traits_are_0_to_1(self, client):
        for c in client.get("/api/state").json()["consumers"]:
            for trait in ("price_sensitivity", "brand_loyalty", "impulse_tendency", "research_depth"):
                v = c[trait]
                assert 0.0 <= v <= 1.0, f"{c['name']}.{trait} = {v}, expected 0-1"

    def test_consumer_shopping_interests_is_list(self, client):
        for c in client.get("/api/state").json()["consumers"]:
            assert isinstance(c["shopping_interests"], list) and c["shopping_interests"], \
                f"{c['name']}: shopping_interests must be non-empty list"


# ── Business state dict fields ────────────────────────────────────────────────

BUSINESS_CARD_FIELDS = [
    "agent_id", "name", "business_type",   # business_type drives B2C/B2B filter
    "vertical", "quality_score", "total_revenue", "order_count",
    "inventory", "catalog", "headquarters",
]
BUSINESS_DETAIL_FIELDS = BUSINESS_CARD_FIELDS + [
    "quality_issues", "faqs", "policies", "founded_year", "employee_count",
    "supplier_ids", "client_b2c_ids", "minimum_order_qty", "wholesale_discount",
]


class TestBusinessStateFields:
    """
    business_type is the field the frontend filters on to split B2C/B2B panels.
    Missing it means both grids stay empty.
    """

    def test_all_businesses_have_business_type(self, client):
        for b in client.get("/api/state").json()["businesses"]:
            assert "business_type" in b, f"{b.get('name')} missing business_type"

    def test_business_type_is_b2c_or_b2b(self, client):
        for b in client.get("/api/state").json()["businesses"]:
            assert b["business_type"] in ("B2C", "B2B"), \
                f"{b['name']}: unexpected business_type '{b['business_type']}'"

    def test_business_card_fields_present(self, client):
        for b in client.get("/api/state").json()["businesses"]:
            missing = [f for f in BUSINESS_CARD_FIELDS if f not in b]
            assert missing == [], f"{b.get('name')} missing fields: {missing}"

    def test_business_detail_fields_present(self, client):
        for b in client.get("/api/state").json()["businesses"]:
            missing = [f for f in BUSINESS_DETAIL_FIELDS if f not in b]
            assert missing == [], f"{b.get('name')} missing fields: {missing}"

    def test_quality_score_is_number_in_range(self, client):
        for b in client.get("/api/state").json()["businesses"]:
            qs = b["quality_score"]
            assert isinstance(qs, (int, float)), f"{b['name']}: quality_score not numeric"
            assert 0 <= qs <= 100, f"{b['name']}: quality_score {qs} out of 0-100"

    def test_total_revenue_is_number(self, client):
        for b in client.get("/api/state").json()["businesses"]:
            assert isinstance(b["total_revenue"], (int, float)), \
                f"{b['name']}: total_revenue not numeric"

    def test_imperfect_businesses_have_lower_scores(self, client):
        businesses = {b["agent_id"]: b for b in client.get("/api/state").json()["businesses"]}
        for imperfect_id in ("biz_pixeldrop", "biz_vaguefashion", "biz_quickbyte"):
            b = businesses[imperfect_id]
            assert b["quality_score"] < 80, \
                f"{b['name']} should score < 80 due to missing prices/FAQs/policies"

    def test_high_quality_businesses_have_higher_scores(self, client):
        businesses = {b["agent_id"]: b for b in client.get("/api/state").json()["businesses"]}
        for quality_id in ("biz_techzone", "biz_stylehub", "biz_gamevault"):
            b = businesses[quality_id]
            assert b["quality_score"] >= 80, \
                f"{b['name']} should score >= 80 with complete catalog"

    def test_inventory_is_dict(self, client):
        for b in client.get("/api/state").json()["businesses"]:
            assert isinstance(b["inventory"], dict), f"{b['name']}: inventory not a dict"

    def test_catalog_is_dict(self, client):
        for b in client.get("/api/state").json()["businesses"]:
            assert isinstance(b["catalog"], dict), f"{b['name']}: catalog not a dict"


# ── /api/consumer/{id} ───────────────────────────────────────────────────────

class TestConsumerDetailEndpoint:

    def test_known_consumer_returns_200(self, client):
        r = client.get("/api/consumer/consumer_alex")
        assert r.status_code == 200

    def test_known_consumer_no_error_key(self, client):
        r = client.get("/api/consumer/consumer_alex")
        assert "error" not in r.json()

    def test_known_consumer_has_all_detail_fields(self, client):
        c = client.get("/api/consumer/consumer_alex").json()
        missing = [f for f in CONSUMER_DETAIL_FIELDS if f not in c]
        assert missing == [], f"Consumer API missing fields: {missing}"

    def test_known_consumer_has_purchase_history(self, client):
        c = client.get("/api/consumer/consumer_alex").json()
        assert "purchase_history" in c
        assert isinstance(c["purchase_history"], list)

    def test_known_consumer_has_transactions(self, client):
        c = client.get("/api/consumer/consumer_alex").json()
        assert "transactions" in c
        assert isinstance(c["transactions"], list)

    def test_all_consumers_accessible(self, client):
        ids = ["consumer_alex", "consumer_sarah", "consumer_mike",
               "consumer_emma", "consumer_tom"]
        for cid in ids:
            r = client.get(f"/api/consumer/{cid}")
            assert r.status_code == 200 and "error" not in r.json(), \
                f"/api/consumer/{cid} failed"

    def test_unknown_consumer_returns_error_not_404(self, client):
        r = client.get("/api/consumer/nobody")
        assert r.status_code == 200
        assert r.json().get("error") == "not found"


# ── /api/business/{id} ───────────────────────────────────────────────────────

class TestBusinessDetailEndpoint:

    def test_known_b2c_returns_200(self, client):
        assert client.get("/api/business/biz_techzone").status_code == 200

    def test_known_b2b_returns_200(self, client):
        assert client.get("/api/business/biz_componentscorp").status_code == 200

    def test_known_business_no_error_key(self, client):
        b = client.get("/api/business/biz_techzone").json()
        assert "error" not in b

    def test_known_business_has_all_detail_fields(self, client):
        b = client.get("/api/business/biz_techzone").json()
        missing = [f for f in BUSINESS_DETAIL_FIELDS if f not in b]
        assert missing == [], f"Business API missing fields: {missing}"

    def test_known_business_has_orders(self, client):
        b = client.get("/api/business/biz_techzone").json()
        assert "orders" in b
        assert isinstance(b["orders"], list)

    def test_known_business_has_ratings(self, client):
        b = client.get("/api/business/biz_techzone").json()
        assert "ratings" in b

    def test_all_b2c_businesses_accessible(self, client):
        ids = ["biz_techzone", "biz_stylehub", "biz_freshmart",
               "biz_homenest", "biz_gamevault",
               "biz_pixeldrop", "biz_vaguefashion", "biz_quickbyte"]
        for bid in ids:
            r = client.get(f"/api/business/{bid}")
            assert r.status_code == 200 and "error" not in r.json(), \
                f"/api/business/{bid} failed"

    def test_all_b2b_businesses_accessible(self, client):
        ids = ["biz_componentscorp", "biz_fabricworld",
               "biz_materialshub", "biz_freshfarmsupply"]
        for bid in ids:
            r = client.get(f"/api/business/{bid}")
            assert r.status_code == 200 and "error" not in r.json(), \
                f"/api/business/{bid} failed"

    def test_unknown_business_returns_error_not_404(self, client):
        r = client.get("/api/business/ghost")
        assert r.status_code == 200
        assert r.json().get("error") == "not found"


# ── /api/start and /api/stop ─────────────────────────────────────────────────

class TestSimulationLifecycle:

    def test_start_returns_200(self, client):
        r = client.post("/api/start?mode=fresh")
        assert r.status_code == 200
        client.post("/api/stop")

    def test_start_returns_running_true(self, client):
        r = client.post("/api/start?mode=fresh")
        assert r.json()["state"]["running"] is True
        client.post("/api/stop")

    def test_start_state_has_all_agents(self, client):
        r = client.post("/api/start?mode=fresh")
        s = r.json()["state"]
        assert len(s["consumers"]) == 5
        assert len(s["businesses"]) == 12
        client.post("/api/stop")

    def test_start_state_has_businesses_not_merchants(self, client):
        r = client.post("/api/start?mode=fresh")
        s = r.json()["state"]
        assert "businesses" in s
        assert "merchants" not in s
        client.post("/api/stop")

    def test_stop_sets_running_false(self, started_client):
        r = started_client.post("/api/stop")
        assert r.json()["state"]["running"] is False

    def test_double_start_idempotent(self, client):
        client.post("/api/start?mode=fresh")
        r = client.post("/api/start?mode=fresh")
        assert r.status_code == 200
        assert r.json()["state"]["running"] is True
        client.post("/api/stop")

    def test_stop_when_not_running_safe(self, client):
        r = client.post("/api/stop")
        assert r.status_code == 200


# ── /api/db-status ───────────────────────────────────────────────────────────

class TestDbStatus:

    def test_returns_200(self, client):
        assert client.get("/api/db-status").status_code == 200

    def test_has_saved_state_bool(self, client):
        d = client.get("/api/db-status").json()
        assert "has_saved_state" in d
        assert isinstance(d["has_saved_state"], bool)

    def test_meta_when_present_has_required_keys(self, client):
        d = client.get("/api/db-status").json()
        if d["has_saved_state"] and d.get("meta"):
            meta = d["meta"]
            for key in ("saved_at", "consumers", "merchants", "suppliers", "total_orders"):
                assert key in meta, f"db-status meta missing '{key}'"


# ── /api/transactions ─────────────────────────────────────────────────────────

class TestTransactionsEndpoint:

    def test_returns_200(self, client):
        assert client.get("/api/transactions").status_code == 200

    def test_has_transactions_list(self, client):
        d = client.get("/api/transactions").json()
        assert "transactions" in d
        assert isinstance(d["transactions"], list)
