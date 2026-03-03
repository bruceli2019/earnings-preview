"""Financial data extraction and analysis from SEC filings."""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class FinancialMetrics:
    """Key financial metrics extracted from filings."""

    revenue: str = ""
    net_income: str = ""
    eps: str = ""
    eps_diluted: str = ""
    gross_margin: str = ""
    operating_income: str = ""
    free_cash_flow: str = ""
    revenue_yoy_change: str = ""
    highlights: list[str] = field(default_factory=list)
    segment_data: dict[str, str] = field(default_factory=dict)
    raw_tables: list[str] = field(default_factory=list)


def extract_financial_metrics(text: str) -> FinancialMetrics:
    """Extract key financial metrics from filing text."""
    metrics = FinancialMetrics()

    # Revenue patterns
    rev_patterns = [
        r"(?:total\s+)?(?:net\s+)?revenue[s]?\s*(?:was|were|of)?\s*\$?([\d,]+\.?\d*)\s*(million|billion|M|B)",
        r"(?:total\s+)?(?:net\s+)?revenue[s]?\s*\$?([\d,]+\.?\d*)\s*(million|billion|M|B)",
        r"\$?([\d,]+\.?\d*)\s*(million|billion)\s*(?:in|of)\s*(?:total\s+)?(?:net\s+)?revenue",
    ]
    metrics.revenue = _match_first(rev_patterns, text)

    # Net income patterns
    ni_patterns = [
        r"net\s+income\s*(?:was|of)?\s*\$?([\d,]+\.?\d*)\s*(million|billion|M|B)",
        r"\$?([\d,]+\.?\d*)\s*(million|billion)\s*(?:in|of)\s*net\s+income",
    ]
    metrics.net_income = _match_first(ni_patterns, text)

    # EPS patterns
    eps_patterns = [
        r"(?:diluted\s+)?earnings?\s+per\s+share\s*(?:was|were|of)?\s*\$?([\d]+\.[\d]+)",
        r"(?:diluted\s+)?EPS\s*(?:was|were|of)?\s*\$?([\d]+\.[\d]+)",
        r"\$?([\d]+\.[\d]+)\s*per\s+(?:diluted\s+)?share",
    ]
    metrics.eps_diluted = _match_eps(eps_patterns, text)

    # Operating income
    oi_patterns = [
        r"operating\s+income\s*(?:was|of)?\s*\$?([\d,]+\.?\d*)\s*(million|billion|M|B)",
        r"income\s+from\s+operations\s*(?:was|of)?\s*\$?([\d,]+\.?\d*)\s*(million|billion|M|B)",
    ]
    metrics.operating_income = _match_first(oi_patterns, text)

    # Gross margin
    gm_patterns = [
        r"gross\s+margin\s*(?:was|of)?\s*([\d]+\.?\d*)\s*%",
        r"gross\s+profit\s+margin\s*(?:was|of)?\s*([\d]+\.?\d*)\s*%",
    ]
    gm = _match_pct(gm_patterns, text)
    if gm:
        metrics.gross_margin = gm

    # Free cash flow
    fcf_patterns = [
        r"free\s+cash\s+flow\s*(?:was|of)?\s*\$?([\d,]+\.?\d*)\s*(million|billion|M|B)",
    ]
    metrics.free_cash_flow = _match_first(fcf_patterns, text)

    # Extract highlights - sentences with strong financial language
    metrics.highlights = _extract_highlights(text)

    return metrics


def _match_first(patterns: list[str], text: str) -> str:
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            amount = m.group(1).replace(",", "")
            unit = m.group(2) if m.lastindex and m.lastindex >= 2 else ""
            unit_norm = _normalize_unit(unit)
            return f"${amount} {unit_norm}".strip()
    return ""


def _match_eps(patterns: list[str], text: str) -> str:
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return f"${m.group(1)}"
    return ""


def _match_pct(patterns: list[str], text: str) -> str:
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return f"{m.group(1)}%"
    return ""


def _normalize_unit(unit: str) -> str:
    u = unit.lower().strip()
    if u in ("b", "billion"):
        return "billion"
    if u in ("m", "million"):
        return "million"
    return unit


def _extract_highlights(text: str) -> list[str]:
    """Extract notable sentences that describe financial performance."""
    highlight_keywords = [
        "record", "exceeded", "surpassed", "grew", "growth",
        "increased", "declined", "decreased", "beat", "missed",
        "strong", "robust", "ahead of", "above expectations",
        "below expectations", "guidance", "outlook",
    ]
    sentences = re.split(r"(?<=[.!])\s+", text[:50_000])
    highlights: list[str] = []
    seen = set()
    for sentence in sentences:
        s = sentence.strip()
        if len(s) < 20 or len(s) > 500:
            continue
        lower = s.lower()
        if any(kw in lower for kw in highlight_keywords):
            # Deduplicate similar highlights
            key = lower[:60]
            if key not in seen:
                seen.add(key)
                highlights.append(s)
        if len(highlights) >= 10:
            break
    return highlights


def extract_guidance(text: str) -> dict[str, str]:
    """Extract forward guidance from filing text."""
    guidance: dict[str, str] = {}

    # Revenue guidance
    rev_guide = re.search(
        r"(?:expect|anticipate|project|forecast|guide)[^\n.]*revenue[^\n.]*\$?([\d,]+\.?\d*)\s*(million|billion|M|B)",
        text,
        re.IGNORECASE,
    )
    if rev_guide:
        guidance["revenue_guidance"] = f"${rev_guide.group(1)} {_normalize_unit(rev_guide.group(2))}"

    # EPS guidance
    eps_guide = re.search(
        r"(?:expect|anticipate|project|forecast|guide)[^\n.]*(?:EPS|earnings per share)[^\n.]*\$?([\d]+\.[\d]+)",
        text,
        re.IGNORECASE,
    )
    if eps_guide:
        guidance["eps_guidance"] = f"${eps_guide.group(1)}"

    # General outlook sentences
    outlook_patterns = [
        r"(?:for\s+(?:the\s+)?(?:full\s+year|fiscal\s+year|FY|next\s+quarter|Q[1-4])[^\n.]*(?:expect|anticipate|guide)[^\n.]*\.)",
        r"(?:(?:we|the company)\s+(?:expect|anticipate|project|forecast)[^\n.]*\.)",
        r"(?:outlook[^\n.]*\.)",
    ]
    outlook_statements: list[str] = []
    for pat in outlook_patterns:
        matches = re.findall(pat, text[:80_000], re.IGNORECASE)
        for m in matches:
            s = m.strip()
            if 20 < len(s) < 500:
                outlook_statements.append(s)
            if len(outlook_statements) >= 5:
                break

    if outlook_statements:
        guidance["outlook_statements"] = "\n".join(outlook_statements)

    return guidance


def extract_analyst_questions(text: str) -> list[dict[str, str]]:
    """Extract analyst Q&A from earnings call transcript text."""
    questions: list[dict[str, str]] = []

    # Common patterns in earnings call transcripts
    # Pattern: "Analyst Name - Firm" or "Q:" or "Question:" followed by text
    qa_blocks = re.split(
        r"\n\s*(?=(?:Q:|Question:|(?:[A-Z][a-z]+ [A-Z][a-z]+)\s*[-\u2014]\s*(?:[A-Z][a-zA-Z &]+)))",
        text,
    )

    for block in qa_blocks:
        block = block.strip()
        if not block:
            continue

        # Try to identify analyst name and firm
        header_match = re.match(
            r"(?:Q:\s*)?(?:([A-Z][a-z]+ [A-Z][a-z]+)\s*[-\u2014]\s*([A-Za-z &]+?))\s*\n(.*)",
            block,
            re.DOTALL,
        )
        if header_match:
            questions.append({
                "analyst": header_match.group(1).strip(),
                "firm": header_match.group(2).strip(),
                "question": header_match.group(3).strip()[:500],
            })
        elif block.startswith("Q:") or block.startswith("Question:"):
            q_text = re.sub(r"^(?:Q:|Question:)\s*", "", block)
            questions.append({
                "analyst": "Unknown",
                "firm": "",
                "question": q_text.strip()[:500],
            })

        if len(questions) >= 15:
            break

    return questions
