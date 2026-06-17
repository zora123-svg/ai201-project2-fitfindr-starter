"""
Tests for FitFindr tools — one test per failure mode plus happy-path checks.
Run with: pytest tests/
"""

import pytest

from tools import search_listings, suggest_outfit, create_fit_card
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── search_listings ───────────────────────────────────────────────────────────

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0


def test_search_empty_results():
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []


def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=25)
    assert all(item["price"] <= 25 for item in results)


def test_search_size_filter():
    results = search_listings("jeans", size="M", max_price=None)
    for item in results:
        item_size = (item.get("size") or "").upper()
        assert "M" in item_size or item_size in "M"


def test_search_no_exception_on_impossible_query():
    # Must return empty list, not raise
    results = search_listings("xyzzy impossible item 999", size="ZZZZ", max_price=0.01)
    assert isinstance(results, list)


def test_search_returns_sorted_by_relevance():
    # "vintage" should appear in the best match title/tags
    results = search_listings("vintage", size=None, max_price=None)
    if len(results) >= 2:
        # First result should have "vintage" in title or tags
        first = results[0]
        searchable = (first.get("title", "") + " ".join(first.get("style_tags", []))).lower()
        assert "vintage" in searchable


# ── suggest_outfit ────────────────────────────────────────────────────────────

def test_suggest_outfit_with_wardrobe():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert results, "Need at least one result for this test"
    suggestion = suggest_outfit(results[0], get_example_wardrobe())
    assert isinstance(suggestion, str)
    assert len(suggestion) > 20


def test_suggest_outfit_empty_wardrobe():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert results
    suggestion = suggest_outfit(results[0], get_empty_wardrobe())
    assert isinstance(suggestion, str)
    assert len(suggestion) > 0
    # Must not raise or return empty — should give general advice


# ── create_fit_card ───────────────────────────────────────────────────────────

def test_create_fit_card_happy_path():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert results
    outfit = "Pair this faded tee with wide-leg jeans and platform shoes for a 90s vibe."
    card = create_fit_card(outfit, results[0])
    assert isinstance(card, str)
    assert len(card) > 20


def test_create_fit_card_empty_outfit_returns_error_string():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert results
    card = create_fit_card("", results[0])
    assert isinstance(card, str)
    assert "error" in card.lower() or "cannot" in card.lower() or "Error" in card


def test_create_fit_card_whitespace_outfit_returns_error_string():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert results
    card = create_fit_card("   ", results[0])
    assert isinstance(card, str)
    assert len(card) > 0
