"""
Tests for v0.2 scenario engine and speed control:
  - set_speed clamps to [0.25, 5.0] and updates config
  - each of the 6 scenario types produces the correct state mutations
  - reset restores original values
  - get_state() includes speed_factor and active_scenarios
  - multiple scenarios can be stacked before reset
"""
import asyncio
import pytest
import config
from simulation.engine import SimulationEngine


@pytest.fixture
def engine():
    e = SimulationEngine()
    e.initialize()
    return e


@pytest.fixture
def running_engine(event_loop):
    """Engine that has been started (agents running)."""
    e = SimulationEngine()
    e.initialize()
    event_loop.run_until_complete(e.start(mode="fresh"))
    yield e
    event_loop.run_until_complete(e.stop())


# ── Speed control ─────────────────────────────────────────────────────────────

def test_set_speed_applies_value(engine):
    engine.set_speed(2.5)
    assert engine.speed_factor == pytest.approx(2.5)


def test_set_speed_clamps_maximum(engine):
    engine.set_speed(99.0)
    assert engine.speed_factor == pytest.approx(5.0)


def test_set_speed_clamps_minimum(engine):
    engine.set_speed(0.0)
    assert engine.speed_factor == pytest.approx(0.25)


def test_set_speed_updates_config(engine):
    engine.set_speed(3.0)
    assert config.SIMULATION_SPEED_FACTOR == pytest.approx(3.0)
    # Restore
    config.SIMULATION_SPEED_FACTOR = 1.0


def test_default_speed_is_1(engine):
    assert engine.speed_factor == pytest.approx(1.0)


# ── State includes new fields ─────────────────────────────────────────────────

def test_get_state_includes_speed_factor(engine):
    engine.set_speed(2.0)
    state = engine.get_state()
    assert "speed_factor" in state
    assert state["speed_factor"] == pytest.approx(2.0)
    config.SIMULATION_SPEED_FACTOR = 1.0


def test_get_state_includes_active_scenarios(engine):
    state = engine.get_state()
    assert "active_scenarios" in state
    assert isinstance(state["active_scenarios"], list)


def test_get_state_active_scenarios_empty_initially(engine):
    state = engine.get_state()
    assert state["active_scenarios"] == []


# ── Scenario: recession ───────────────────────────────────────────────────────

def test_recession_reduces_consumer_budgets(running_engine):
    before = {cid: c.budget for cid, c in running_engine.consumers.items()}
    running_engine.apply_scenario("recession")
    for cid, c in running_engine.consumers.items():
        assert c.budget < before[cid]
        assert c.budget >= before[cid] * 0.55  # ~60% of original (±floor)


def test_recession_increases_price_sensitivity(running_engine):
    before = {cid: c.price_sensitivity for cid, c in running_engine.consumers.items()}
    running_engine.apply_scenario("recession")
    for cid, c in running_engine.consumers.items():
        assert c.price_sensitivity > before[cid]


def test_recession_added_to_active_scenarios(running_engine):
    running_engine.apply_scenario("recession")
    assert "recession" in running_engine.active_scenarios


def test_recession_price_sensitivity_clamped_to_1(running_engine):
    # Max out sensitivity first
    for c in running_engine.consumers.values():
        c.price_sensitivity = 0.95
    running_engine.apply_scenario("recession")
    for c in running_engine.consumers.values():
        assert c.price_sensitivity <= 1.0


# ── Scenario: black_friday ────────────────────────────────────────────────────

def test_black_friday_increases_consumer_budgets(running_engine):
    before = {cid: c.budget for cid, c in running_engine.consumers.items()}
    running_engine.apply_scenario("black_friday")
    for cid, c in running_engine.consumers.items():
        assert c.budget > before[cid]
        assert c.budget == pytest.approx(before[cid] * 1.30)


def test_black_friday_increases_impulse_tendency(running_engine):
    before = {cid: c.impulse_tendency for cid, c in running_engine.consumers.items()}
    running_engine.apply_scenario("black_friday")
    for cid, c in running_engine.consumers.items():
        assert c.impulse_tendency >= before[cid]


def test_black_friday_impulse_clamped_to_1(running_engine):
    for c in running_engine.consumers.values():
        c.impulse_tendency = 0.9
    running_engine.apply_scenario("black_friday")
    for c in running_engine.consumers.values():
        assert c.impulse_tendency <= 1.0


# ── Scenario: supply_shock ────────────────────────────────────────────────────

def test_supply_shock_reduces_b2b_inventory(running_engine):
    b2b_before = {
        bid: dict(b.inventory)
        for bid, b in running_engine.businesses.items()
        if b.business_type == "B2B"
    }
    running_engine.apply_scenario("supply_shock")
    for bid, b in running_engine.businesses.items():
        if b.business_type == "B2B":
            for sku, qty in b.inventory.items():
                assert qty <= max(2, b2b_before[bid][sku] // 10 + 1)


def test_supply_shock_does_not_affect_b2c_inventory(running_engine):
    b2c_before = {
        bid: dict(b.inventory)
        for bid, b in running_engine.businesses.items()
        if b.business_type == "B2C"
    }
    running_engine.apply_scenario("supply_shock")
    for bid, b in running_engine.businesses.items():
        if b.business_type == "B2C":
            assert b.inventory == b2c_before[bid]


# ── Scenario: price_war ───────────────────────────────────────────────────────

def test_price_war_reduces_b2c_prices(running_engine):
    b2c_before = {
        bid: {sku: p["price"] for sku, p in b.catalog.items()}
        for bid, b in running_engine.businesses.items()
        if b.business_type == "B2C"
    }
    running_engine.apply_scenario("price_war")
    for bid, b in running_engine.businesses.items():
        if b.business_type == "B2C":
            for sku, product in b.catalog.items():
                expected = round(b2c_before[bid][sku] * 0.80, 2)
                assert product["price"] == pytest.approx(expected)


def test_price_war_does_not_affect_b2b_prices(running_engine):
    b2b_before = {
        bid: {sku: p["price"] for sku, p in b.catalog.items()}
        for bid, b in running_engine.businesses.items()
        if b.business_type == "B2B"
    }
    running_engine.apply_scenario("price_war")
    for bid, b in running_engine.businesses.items():
        if b.business_type == "B2B":
            for sku, product in b.catalog.items():
                assert product["price"] == pytest.approx(b2b_before[bid][sku])


# ── Scenario: quality_boost ───────────────────────────────────────────────────

def test_quality_boost_adds_faqs_to_imperfect_businesses(running_engine):
    """Imperfect merchants (quality_score < 65) get FAQs added."""
    imperfect = [b for b in running_engine.businesses.values()
                 if b.business_type == "B2C" and b.quality_score < 65]
    # Ensure there are imperfect businesses in seed data
    if not imperfect:
        pytest.skip("No imperfect B2C businesses in seed data")

    # Clear their FAQs first
    for b in imperfect:
        b.faqs = []

    running_engine.apply_scenario("quality_boost")
    for b in imperfect:
        assert len(b.faqs) > 0


def test_quality_boost_does_not_downgrade_good_businesses(running_engine):
    """Quality boost should not change quality businesses (score >= 65)."""
    good = [b for b in running_engine.businesses.values()
            if b.business_type == "B2C" and b.quality_score >= 65]
    before_faqs = {b.agent_id: list(b.faqs) for b in good}
    running_engine.apply_scenario("quality_boost")
    for b in good:
        assert b.faqs == before_faqs[b.agent_id]


# ── Scenario: reset ───────────────────────────────────────────────────────────

def test_reset_restores_consumer_budgets(running_engine):
    before = {cid: c.budget for cid, c in running_engine.consumers.items()}
    running_engine.apply_scenario("recession")
    running_engine.apply_scenario("reset")
    for cid, c in running_engine.consumers.items():
        assert c.budget == pytest.approx(before[cid])


def test_reset_restores_b2c_prices(running_engine):
    before = {
        bid: {sku: p["price"] for sku, p in b.catalog.items()}
        for bid, b in running_engine.businesses.items()
        if b.business_type == "B2C"
    }
    running_engine.apply_scenario("price_war")
    running_engine.apply_scenario("reset")
    for bid, b in running_engine.businesses.items():
        if b.business_type == "B2C":
            for sku, product in b.catalog.items():
                assert product["price"] == pytest.approx(before[bid][sku])


def test_reset_clears_active_scenarios(running_engine):
    running_engine.apply_scenario("recession")
    running_engine.apply_scenario("price_war")
    assert len(running_engine.active_scenarios) >= 2
    running_engine.apply_scenario("reset")
    assert running_engine.active_scenarios == []


def test_reset_clears_scenario_originals(running_engine):
    running_engine.apply_scenario("recession")
    running_engine.apply_scenario("reset")
    assert running_engine._scenario_originals == {}


def test_reset_without_prior_scenario_is_safe(running_engine):
    """Reset when no scenario was applied should not raise."""
    result = running_engine.apply_scenario("reset")
    assert result is not None  # returns a string message


# ── Multiple scenarios stacked ────────────────────────────────────────────────

def test_multiple_scenarios_tracked_in_active_list(running_engine):
    running_engine.apply_scenario("recession")
    running_engine.apply_scenario("price_war")
    assert "recession" in running_engine.active_scenarios
    assert "price_war" in running_engine.active_scenarios


def test_originals_saved_only_on_first_scenario(running_engine):
    """_scenario_originals captures state before any mutation — only once."""
    initial_budgets = {cid: c.budget for cid, c in running_engine.consumers.items()}
    running_engine.apply_scenario("recession")
    # After recession, budgets are lower
    for cid, c in running_engine.consumers.items():
        assert c.budget < initial_budgets[cid]

    # Apply another scenario — originals should not be overwritten
    running_engine.apply_scenario("black_friday")
    running_engine.apply_scenario("reset")

    # After reset, budgets should be back to ORIGINAL (pre-recession) values
    for cid, c in running_engine.consumers.items():
        assert c.budget == pytest.approx(initial_budgets[cid])


# ── Unknown scenario ──────────────────────────────────────────────────────────

def test_unknown_scenario_returns_error_message(running_engine):
    result = running_engine.apply_scenario("__nonexistent__")
    assert "Unknown" in result or "unknown" in result.lower()
