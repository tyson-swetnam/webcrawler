"""Tests for editorial pick validation and theme helpers."""

from crawler.ai.editor import EditorialCurator
from crawler.ai.themes import THEME_IDS, validate_themes


def test_validate_picks_filters_unknown_ids_and_reranks():
    curator = EditorialCurator()
    output = {
        "picks": [
            {"rank": 2, "article_id": 20, "editorial_note": "b", "impact_category": "Major Funding"},
            {"rank": 1, "article_id": 10, "editorial_note": "a", "impact_category": "Policy Impact"},
            {"rank": 3, "article_id": 999, "editorial_note": "ghost", "impact_category": "Major Funding"},
            {"rank": 4, "article_id": 10, "editorial_note": "dup", "impact_category": "Major Funding"},
        ]
    }
    picks = curator._validate_picks(output, valid_ids={10, 20, 30}, max_picks=10)
    assert [p["article_id"] for p in picks] == [10, 20]
    assert [p["rank"] for p in picks] == [1, 2]


def test_validate_picks_caps_and_defaults_category():
    curator = EditorialCurator()
    output = {
        "picks": [
            {"rank": i, "article_id": i, "editorial_note": "", "impact_category": "Bogus Category"}
            for i in range(1, 6)
        ]
    }
    picks = curator._validate_picks(output, valid_ids=set(range(1, 6)), max_picks=3)
    assert len(picks) == 3
    assert all(p["impact_category"] == "Scientific Breakthrough" for p in picks)


def test_validate_themes_accepts_list_and_string():
    known = next(iter(THEME_IDS))
    assert validate_themes([known, "nonsense"]) == [known]
    assert validate_themes(f"{known}, nonsense") == [known]
    assert validate_themes(None) == []
    assert validate_themes([]) == []


def test_validate_themes_caps_at_five():
    ids = list(THEME_IDS)[:7]
    assert len(validate_themes(ids)) <= 5
