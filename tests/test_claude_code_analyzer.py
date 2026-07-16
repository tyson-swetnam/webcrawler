"""Tests for the subscription-backed batch analyzer."""

import asyncio

import pytest

import crawler.ai.claude_code_analyzer as cca
from crawler.ai.claude_cli import ClaudeCLIError, ClaudeQuotaExhausted


def _articles(n):
    return [
        {"article_id": i, "title": f"Article {i}", "content": "AI " * 50, "url": f"https://u.edu/{i}"}
        for i in range(1, n + 1)
    ]


def _result(article_id, **overrides):
    base = {
        "article_id": article_id,
        "is_ai_related": True,
        "confidence": 0.9,
        "summary": f"Summary {article_id}",
        "key_points": ["a", "b"],
        "relevance_score": 7,
        "themes": [],
        "impact_scores": {"scientific": 5, "financial": 2, "partnership": 3},
    }
    base.update(overrides)
    return base


@pytest.fixture
def analyzer(monkeypatch):
    monkeypatch.setattr(cca, "preflight", lambda: (True, "ok"))
    return cca.ClaudeCodeAnalyzer()


def test_batches_and_reconciles(analyzer, monkeypatch):
    calls = []

    async def fake_run(prompt, schema, model=None, timeout=None, max_turns=2):
        ids = [int(line.split(":")[1]) for line in prompt.splitlines() if line.startswith("ARTICLE_ID:")]
        calls.append(ids)
        return {"results": [_result(i) for i in ids]}

    monkeypatch.setattr(cca, "run_structured_prompt", fake_run)
    monkeypatch.setattr(cca.settings, "ai_articles_per_prompt", 10)

    articles = _articles(25)
    results = asyncio.run(analyzer.batch_analyze(articles))

    assert len(calls) == 3  # 10 + 10 + 5
    assert len(results) == 25
    assert all(r is not None for r in results)
    # Results aligned with the input order
    assert [r["article_id"] for r in results] == [a["article_id"] for a in articles]
    assert results[0]["consensus"]["summary"] == "Summary 1"
    assert results[0]["consensus"]["providers_count"] == 1
    assert results[0]["openai"] is None


def test_missing_ids_stay_unanalyzed(analyzer, monkeypatch):
    async def fake_run(prompt, schema, model=None, timeout=None, max_turns=2):
        ids = [int(line.split(":")[1]) for line in prompt.splitlines() if line.startswith("ARTICLE_ID:")]
        # Model "forgets" the last article of every chunk
        return {"results": [_result(i) for i in ids[:-1]]}

    monkeypatch.setattr(cca, "run_structured_prompt", fake_run)
    monkeypatch.setattr(cca.settings, "ai_articles_per_prompt", 5)

    results = asyncio.run(analyzer.batch_analyze(_articles(5)))
    assert results[:4] == results[:4]
    assert all(r is not None for r in results[:4])
    assert results[4] is None  # stays resumable


def test_quota_exhaustion_returns_partial(analyzer, monkeypatch):
    call_count = {"n": 0}

    async def fake_run(prompt, schema, model=None, timeout=None, max_turns=2):
        call_count["n"] += 1
        if call_count["n"] > 1:
            raise ClaudeQuotaExhausted("hit your session limit")
        ids = [int(line.split(":")[1]) for line in prompt.splitlines() if line.startswith("ARTICLE_ID:")]
        return {"results": [_result(i) for i in ids]}

    monkeypatch.setattr(cca, "run_structured_prompt", fake_run)
    monkeypatch.setattr(cca.settings, "ai_articles_per_prompt", 5)

    results = asyncio.run(analyzer.batch_analyze(_articles(15), max_concurrent=1))
    analyzed = [r for r in results if r is not None]
    assert len(analyzed) == 5
    assert analyzer._quota_exhausted is True


def test_chunk_failure_isolated(analyzer, monkeypatch):
    call_count = {"n": 0}

    async def fake_run(prompt, schema, model=None, timeout=None, max_turns=2):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise ClaudeCLIError("boom")
        ids = [int(line.split(":")[1]) for line in prompt.splitlines() if line.startswith("ARTICLE_ID:")]
        return {"results": [_result(i) for i in ids]}

    monkeypatch.setattr(cca, "run_structured_prompt", fake_run)
    monkeypatch.setattr(cca.settings, "ai_articles_per_prompt", 5)

    results = asyncio.run(analyzer.batch_analyze(_articles(10), max_concurrent=1))
    assert [r is None for r in results[:5]] == [True] * 5
    assert all(r is not None for r in results[5:])


def test_message_budget_cap(analyzer, monkeypatch):
    async def fake_run(prompt, schema, model=None, timeout=None, max_turns=2):
        ids = [int(line.split(":")[1]) for line in prompt.splitlines() if line.startswith("ARTICLE_ID:")]
        return {"results": [_result(i) for i in ids]}

    monkeypatch.setattr(cca, "run_structured_prompt", fake_run)
    monkeypatch.setattr(cca.settings, "ai_articles_per_prompt", 5)
    monkeypatch.setattr(cca.settings, "ai_message_budget", 2)

    results = asyncio.run(analyzer.batch_analyze(_articles(20), max_concurrent=1))
    analyzed = [r for r in results if r is not None]
    assert len(analyzed) == 10  # 2 chunks of 5, budget stops the rest


def test_theme_validation_filters_unknown_ids(analyzer, monkeypatch):
    async def fake_run(prompt, schema, model=None, timeout=None, max_turns=2):
        return {"results": [_result(1, themes=["not_a_real_theme", "general_ai"])]}

    monkeypatch.setattr(cca, "run_structured_prompt", fake_run)
    results = asyncio.run(analyzer.batch_analyze(_articles(1)))
    themes = results[0]["claude"]["themes"]
    assert "not_a_real_theme" not in themes
