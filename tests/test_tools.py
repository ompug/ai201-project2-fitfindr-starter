from agent import run_agent
from tools import (
    compare_price,
    create_fit_card,
    get_trend_signal,
    search_listings,
    suggest_outfit,
    update_style_profile,
)
from utils.data_loader import get_empty_wardrobe, get_example_wardrobe


def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0
    assert all("title" in item and "price" in item for item in results)


def test_search_empty_results():
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []


def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=45)
    assert results
    assert all(item["price"] <= 45 for item in results)


def test_suggest_outfit_empty_wardrobe_returns_general_advice():
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    suggestion = suggest_outfit(item, get_empty_wardrobe())
    assert isinstance(suggestion, str)
    assert suggestion.strip()
    assert "No saved wardrobe" in suggestion or "wardrobe" in suggestion.lower()


def test_create_fit_card_empty_outfit_returns_actionable_error():
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    card = create_fit_card("", item)
    assert "outfit suggestion" in card
    assert "fit card" in card


def test_compare_price_returns_assessment_with_reasoning():
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    assessment = compare_price(item)
    assert assessment["assessment"] in {"good deal", "fair price", "pricey"}
    assert assessment["comparable_count"] >= 1
    assert "Average comparable price" in assessment["reasoning"]


def test_trend_signal_returns_styling_note():
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    trend = get_trend_signal(item, size=None)
    assert trend["trend"]
    assert trend["styling_note"]
    assert trend["source"]


def test_style_profile_memory_persists_preferences(tmp_path):
    profile_path = tmp_path / "profile.json"
    first = update_style_profile(
        "vintage graphic tee with baggy jeans and chunky sneakers",
        {"items": []},
        str(profile_path),
    )
    second = update_style_profile("shirt under $30", {"items": []}, str(profile_path))
    assert first["interaction_count"] == 1
    assert second["interaction_count"] == 2
    assert "vintage" in second["preferred_tags"]
    assert "baggy" in second["preferred_tags"]


def test_agent_happy_path_uses_all_tool_state(monkeypatch, tmp_path):
    monkeypatch.setattr("agent.PROFILE_PATH", str(tmp_path / "profile.json"))
    session = run_agent(
        "vintage graphic tee under $30",
        get_example_wardrobe(),
    )
    assert session["error"] is None
    assert session["search_results"]
    assert session["selected_item"] is session["search_results"][0]
    assert session["price_assessment"]["assessment"]
    assert session["trend_signal"]["styling_note"] in session["outfit_suggestion"]
    assert session["outfit_suggestion"] in session["fit_card"]


def test_agent_no_results_stops_before_outfit(monkeypatch, tmp_path):
    monkeypatch.setattr("agent.PROFILE_PATH", str(tmp_path / "profile.json"))
    session = run_agent(
        "designer ballgown size XXS under $5",
        get_example_wardrobe(),
    )
    assert session["error"]
    assert session["selected_item"] is None
    assert session["outfit_suggestion"] is None
    assert session["fit_card"] is None
    assert "tried" in session["retry_note"]


def test_agent_style_memory_second_interaction(monkeypatch, tmp_path):
    monkeypatch.setattr("agent.PROFILE_PATH", str(tmp_path / "profile.json"))
    run_agent(
        "vintage graphic tee under $30 with baggy streetwear",
        {"items": []},
    )
    session = run_agent("shirt under $30", {"items": []})
    assert session["style_profile"]["interaction_count"] == 2
    assert session["memory_note"]
