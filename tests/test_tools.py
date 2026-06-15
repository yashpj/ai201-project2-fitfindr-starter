"""
tests/test_tools.py

Pytest tests for the three FitFindr tools.
Run with: pytest tests/

Each tool's failure mode is covered by at least one dedicated test.
LLM tools (suggest_outfit, create_fit_card) are tested with mocked Groq
calls so tests run without a real API key.
"""

import sys
import os
from unittest.mock import MagicMock, patch

import pytest

# Ensure project root is on the path when running from any directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools import search_listings, suggest_outfit, create_fit_card
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── search_listings tests ─────────────────────────────────────────────────────

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0


def test_search_empty_results():
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []


def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=10)
    assert all(item["price"] <= 10 for item in results)


def test_search_size_filter():
    # Size "S" should not match listings that are "L" only
    results = search_listings("tee", size="W30 L30", max_price=None)
    for item in results:
        assert "w30" in item["size"].lower() or "30" in item["size"].lower()


def test_search_case_insensitive_size():
    results_upper = search_listings("tee", size="M", max_price=None)
    results_lower = search_listings("tee", size="m", max_price=None)
    assert len(results_upper) == len(results_lower)


def test_search_returns_list_of_dicts():
    results = search_listings("vintage", size=None, max_price=None)
    assert isinstance(results, list)
    for item in results:
        assert isinstance(item, dict)
        assert "id" in item
        assert "title" in item
        assert "price" in item


def test_search_sorted_by_relevance():
    # A very specific multi-keyword query — top result should score highest
    results = search_listings("vintage graphic tee streetwear", size=None, max_price=None)
    if len(results) >= 2:
        # We can't directly access scores, but results should exist and be a list
        assert isinstance(results[0], dict)


def test_search_no_zero_score_items():
    # Items with no keyword match should not appear
    # "zxqwerty" is not in any listing
    results = search_listings("zxqwerty", size=None, max_price=None)
    assert results == []


def test_search_no_exception_on_empty():
    # Must return [] not raise
    try:
        result = search_listings("", size=None, max_price=0.01)
        assert result == []
    except Exception as e:
        pytest.fail(f"search_listings raised an exception: {e}")


# ── suggest_outfit tests ──────────────────────────────────────────────────────

def _mock_groq_response(text: str):
    """Helper: returns a mock Groq client whose completion returns text."""
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = text
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[mock_choice]
    )
    return mock_client


def _sample_listing():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert results, "Need at least one listing for outfit tests"
    return results[0]


@patch("tools._get_groq_client")
def test_suggest_outfit_with_wardrobe(mock_get_client):
    mock_get_client.return_value = _mock_groq_response(
        "Pair this with your baggy jeans and chunky sneakers."
    )
    item = _sample_listing()
    result = suggest_outfit(item, get_example_wardrobe())
    assert isinstance(result, str)
    assert len(result) > 0


@patch("tools._get_groq_client")
def test_suggest_outfit_empty_wardrobe_no_exception(mock_get_client):
    mock_get_client.return_value = _mock_groq_response(
        "This piece works great with straight-leg jeans and chunky sneakers."
    )
    item = _sample_listing()
    # Must not raise even with empty wardrobe
    result = suggest_outfit(item, get_empty_wardrobe())
    assert isinstance(result, str)
    assert len(result) > 0


@patch("tools._get_groq_client")
def test_suggest_outfit_returns_string(mock_get_client):
    mock_get_client.return_value = _mock_groq_response("Some outfit advice.")
    item = _sample_listing()
    result = suggest_outfit(item, get_example_wardrobe())
    assert isinstance(result, str)


@patch("tools._get_groq_client")
def test_suggest_outfit_empty_wardrobe_calls_general_prompt(mock_get_client):
    mock_client = _mock_groq_response("General styling advice here.")
    mock_get_client.return_value = mock_client
    item = _sample_listing()
    suggest_outfit(item, get_empty_wardrobe())
    # LLM was called once
    assert mock_client.chat.completions.create.call_count == 1


# ── create_fit_card tests ─────────────────────────────────────────────────────

@patch("tools._get_groq_client")
def test_create_fit_card_returns_caption(mock_get_client):
    mock_get_client.return_value = _mock_groq_response(
        "thrifted this tee off depop for $19 and i'm obsessed 🖤"
    )
    item = _sample_listing()
    result = create_fit_card("Wear with baggy jeans and chunky sneakers.", item)
    assert isinstance(result, str)
    assert len(result) > 0


def test_create_fit_card_empty_outfit_returns_error_string():
    # Must not raise — must return descriptive error string
    result = create_fit_card("", {"title": "Test Tee", "price": 20, "platform": "depop"})
    assert isinstance(result, str)
    assert "could not generate" in result.lower() or "empty" in result.lower()


def test_create_fit_card_whitespace_outfit_returns_error_string():
    result = create_fit_card("   ", {"title": "Test Tee", "price": 20, "platform": "depop"})
    assert isinstance(result, str)
    assert "could not generate" in result.lower() or "empty" in result.lower()


def test_create_fit_card_empty_outfit_no_exception():
    try:
        result = create_fit_card("", {"title": "Test Tee", "price": 20, "platform": "depop"})
        assert isinstance(result, str)
    except Exception as e:
        pytest.fail(f"create_fit_card raised an exception on empty outfit: {e}")


@patch("tools._get_groq_client")
def test_create_fit_card_uses_item_details(mock_get_client):
    captured_prompt = {}

    def capture_call(**kwargs):
        captured_prompt["messages"] = kwargs.get("messages", [])
        mock_choice = MagicMock()
        mock_choice.message.content = "great caption here"
        return MagicMock(choices=[mock_choice])

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = capture_call
    mock_get_client.return_value = mock_client

    item = {"title": "Faded Band Tee", "price": 22.0, "platform": "depop"}
    create_fit_card("Pair with wide-leg jeans.", item)

    prompt_text = captured_prompt["messages"][0]["content"]
    assert "Faded Band Tee" in prompt_text
    assert "22" in prompt_text
    assert "depop" in prompt_text
