"""Tests for financial data extraction."""

from earnings_analyzer.financials import (
    extract_analyst_questions,
    extract_financial_metrics,
    extract_guidance,
)


SAMPLE_8K_TEXT = """
CUPERTINO, CALIFORNIA - Apple today announced financial results for its fiscal
2024 first quarter ended December 30, 2023.

The Company posted quarterly revenue of $119.6 billion, up 2 percent year over
year, and quarterly earnings per share of $2.18.

"Today Apple is reporting revenue growth and an all-time revenue record in
Services," said Tim Cook, Apple's CEO. "We are pleased to announce that our
installed base of active devices has now surpassed 2.2 billion."

"Our record revenue and strong operating performance drove EPS to a new
December quarter record," said Luca Maestri, Apple's CFO. "We returned over
$27 billion to shareholders during the quarter."

Gross margin was 45.9% compared to 43.0% in the year-ago quarter.
Operating income was $40.4 billion.
Free cash flow was $30.6 billion.

For the March quarter, the Company expects revenue between $90 billion and
$94 billion. The Company expects EPS of $1.50.
"""


SAMPLE_QA_TEXT = """
Q: Can you talk about the trajectory of services revenue and what's driving
the acceleration there?

Q: On the gross margin front, how sustainable is this level going forward?

John Smith - Morgan Stanley
What are your expectations for the China market in the coming quarters given
the competitive dynamics?
"""


def test_extract_revenue():
    metrics = extract_financial_metrics(SAMPLE_8K_TEXT)
    assert metrics.revenue
    assert "119.6" in metrics.revenue
    assert "billion" in metrics.revenue


def test_extract_eps():
    metrics = extract_financial_metrics(SAMPLE_8K_TEXT)
    assert metrics.eps_diluted == "$2.18"


def test_extract_operating_income():
    metrics = extract_financial_metrics(SAMPLE_8K_TEXT)
    assert metrics.operating_income
    assert "40.4" in metrics.operating_income


def test_extract_gross_margin():
    metrics = extract_financial_metrics(SAMPLE_8K_TEXT)
    assert metrics.gross_margin == "45.9%"


def test_extract_free_cash_flow():
    metrics = extract_financial_metrics(SAMPLE_8K_TEXT)
    assert metrics.free_cash_flow
    assert "30.6" in metrics.free_cash_flow


def test_extract_highlights():
    metrics = extract_financial_metrics(SAMPLE_8K_TEXT)
    assert len(metrics.highlights) > 0
    # Should pick up "record" and "growth" mentions
    highlight_text = " ".join(metrics.highlights).lower()
    assert "record" in highlight_text or "growth" in highlight_text


def test_extract_guidance():
    guidance = extract_guidance(SAMPLE_8K_TEXT)
    assert "eps_guidance" in guidance
    assert "$1.50" in guidance["eps_guidance"]


def test_extract_analyst_questions():
    questions = extract_analyst_questions(SAMPLE_QA_TEXT)
    assert len(questions) >= 2


def test_empty_text():
    metrics = extract_financial_metrics("")
    assert metrics.revenue == ""
    assert metrics.eps_diluted == ""
    guidance = extract_guidance("")
    assert guidance == {} or "outlook_statements" not in guidance
