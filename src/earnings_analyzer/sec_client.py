"""SEC EDGAR client for fetching 8-K and 10-Q filings."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime

import httpx
from bs4 import BeautifulSoup

EDGAR_BASE = "https://efts.sec.gov/LATEST"
EDGAR_ARCHIVES = "https://www.sec.gov/Archives/edgar/data"
EDGAR_COMPANY = "https://data.sec.gov/submissions"

HEADERS = {
    "User-Agent": "EarningsAnalyzer/0.1 (earnings-analyzer@example.com)",
    "Accept-Encoding": "gzip, deflate",
}


@dataclass
class Filing:
    form_type: str
    filed_date: date
    accession_number: str
    primary_document: str
    cik: str
    description: str = ""
    html_url: str = ""
    items: list[str] = field(default_factory=list)
    text_content: str = ""


class SECClient:
    """Fetch and parse SEC EDGAR filings."""

    def __init__(self) -> None:
        self._client = httpx.Client(headers=HEADERS, timeout=30, follow_redirects=True)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> SECClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def resolve_cik(self, ticker: str) -> str:
        """Resolve a ticker symbol to a CIK number."""
        resp = self._client.get(
            f"{EDGAR_BASE}/search-index",
            params={"q": ticker, "dateRange": "custom", "startdt": "2024-01-01"},
        )
        # Try the company tickers JSON endpoint instead
        resp = self._client.get(
            "https://www.sec.gov/files/company_tickers.json"
        )
        resp.raise_for_status()
        tickers = resp.json()
        ticker_upper = ticker.upper()
        for entry in tickers.values():
            if entry.get("ticker", "").upper() == ticker_upper:
                return str(entry["cik_str"])
        raise ValueError(f"Could not resolve ticker '{ticker}' to a CIK")

    def get_recent_filings(
        self,
        cik: str,
        form_types: list[str] | None = None,
        count: int = 10,
    ) -> list[Filing]:
        """Fetch recent filings for a CIK from the submissions endpoint."""
        padded_cik = cik.zfill(10)
        resp = self._client.get(f"{EDGAR_COMPANY}/CIK{padded_cik}.json")
        resp.raise_for_status()
        data = resp.json()

        recent = data.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        dates = recent.get("filingDate", [])
        accessions = recent.get("accessionNumber", [])
        primary_docs = recent.get("primaryDocument", [])
        descriptions = recent.get("primaryDocDescription", [])

        form_types_upper = (
            {ft.upper() for ft in form_types} if form_types else None
        )

        filings: list[Filing] = []
        for i in range(len(forms)):
            if form_types_upper and forms[i].upper() not in form_types_upper:
                continue
            accession_clean = accessions[i].replace("-", "")
            filing = Filing(
                form_type=forms[i],
                filed_date=date.fromisoformat(dates[i]),
                accession_number=accessions[i],
                primary_document=primary_docs[i],
                cik=cik,
                description=descriptions[i] if i < len(descriptions) else "",
                html_url=(
                    f"{EDGAR_ARCHIVES}/{cik}/{accession_clean}/{primary_docs[i]}"
                ),
            )
            filings.append(filing)
            if len(filings) >= count:
                break

        return filings

    def get_latest_8k(self, cik: str) -> Filing | None:
        """Get the most recent 8-K filing (earnings announcement)."""
        filings = self.get_recent_filings(cik, form_types=["8-K"], count=5)
        # Look for earnings-related 8-K (Item 2.02 - Results of Operations)
        for f in filings:
            content = self._fetch_filing_text(f)
            if "2.02" in content or "Results of Operations" in content:
                f.text_content = content
                f.items = self._extract_8k_items(content)
                return f
        # Fall back to most recent 8-K
        if filings:
            filings[0].text_content = self._fetch_filing_text(filings[0])
            filings[0].items = self._extract_8k_items(filings[0].text_content)
            return filings[0]
        return None

    def get_latest_10q(self, cik: str) -> Filing | None:
        """Get the most recent 10-Q filing."""
        filings = self.get_recent_filings(cik, form_types=["10-Q"], count=3)
        if filings:
            filings[0].text_content = self._fetch_filing_text(filings[0])
            return filings[0]
        return None

    def _fetch_filing_text(self, filing: Filing) -> str:
        """Download and extract text content from a filing."""
        try:
            resp = self._client.get(filing.html_url)
            resp.raise_for_status()
        except httpx.HTTPError:
            return ""

        content_type = resp.headers.get("content-type", "")
        raw = resp.text

        if "html" in content_type or raw.strip().startswith("<"):
            soup = BeautifulSoup(raw, "lxml")
            # Remove script and style elements
            for tag in soup(["script", "style"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)
        else:
            text = raw

        return text[:200_000]  # Cap to avoid memory issues

    def _extract_8k_items(self, text: str) -> list[str]:
        """Extract reported Item numbers from an 8-K filing."""
        pattern = r"Item\s+(\d+\.\d+)"
        matches = re.findall(pattern, text, re.IGNORECASE)
        return sorted(set(matches))
