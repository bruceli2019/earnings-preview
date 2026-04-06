"""Summarize podcast transcripts using Gemini (free) or Anthropic API."""

from __future__ import annotations

import os

_SYSTEM_PROMPT = """\
You are an expert podcast analyst. Given a podcast transcript, produce \
structured takeaways that capture the most valuable insights. Be specific \
and concrete — include names, numbers, frameworks, and actionable details. \
Skip filler, pleasantries, and ad reads.

Output format:

# [Episode Title]

## TL;DR
[2-3 sentence summary of the episode's core thesis]

## Key Takeaways
- [Specific, actionable insight #1]
- [Specific, actionable insight #2]
- [Continue for all major insights, typically 5-10]

## Notable Quotes
- "[Exact or near-exact memorable quote]" — [Speaker if identifiable]
- [2-4 quotes max]

## People & Resources Mentioned
- [Person, company, book, paper, tool mentioned with brief context]

## My Assessment
[1-2 sentences: what's novel/contrarian here vs. consensus view, \
and who would find this most valuable]"""

_MERGE_SYSTEM = """\
You are merging multiple partial summaries of a single podcast episode \
into one cohesive set of takeaways. Deduplicate insights, keep the best \
quotes, and produce a single output following the exact same format."""

_CHUNK_SIZE = 90_000  # characters per chunk
_CHUNK_OVERLAP = 5_000  # overlap between chunks


# ---------------------------------------------------------------------------
# Gemini backend (free tier, default)
# ---------------------------------------------------------------------------

def _get_gemini_client():
    """Return a Gemini client, raising a clear error if no API key."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY environment variable is not set.\n"
            "Get a FREE key at https://aistudio.google.com/apikey\n"
            "Then:  set GEMINI_API_KEY=your-key-here"
        )
    try:
        from google import genai
    except ImportError:
        raise RuntimeError(
            "google-genai package is not installed.\n"
            "Install it:  pip install google-genai"
        )
    return genai.Client(api_key=api_key)


def _call_gemini(
    client,
    system: str,
    user_message: str,
) -> str:
    """Send a message to Gemini and return the text response."""
    resp = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=user_message,
        config={
            "system_instruction": system,
            "max_output_tokens": 4096,
        },
    )
    return resp.text


# ---------------------------------------------------------------------------
# Anthropic backend (paid, optional)
# ---------------------------------------------------------------------------

def _get_anthropic_client():
    """Return an Anthropic client."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY environment variable is not set.\n"
            "Get a key at https://console.anthropic.com/settings/keys"
        )
    try:
        import anthropic
    except ImportError:
        raise RuntimeError(
            "anthropic package is not installed.\n"
            "Install it:  pip install anthropic"
        )
    return anthropic.Anthropic(api_key=api_key)


def _call_anthropic(
    client,
    system: str,
    user_message: str,
) -> str:
    """Send a message to Claude and return the text response."""
    resp = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": user_message}],
    )
    return resp.content[0].text


# ---------------------------------------------------------------------------
# Unified interface
# ---------------------------------------------------------------------------

def _detect_backend() -> str:
    """Pick the best available backend based on environment variables."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.environ.get("GEMINI_API_KEY"):
        return "gemini"
    # Default to Gemini (free) — will raise a clear error with instructions
    return "gemini"


def _get_backend(backend: str):
    """Return (client, call_fn) for the chosen backend."""
    if backend == "anthropic":
        return _get_anthropic_client(), _call_anthropic
    return _get_gemini_client(), _call_gemini


def summarize(
    transcript: str,
    episode_title: str,
    backend: str | None = None,
) -> str:
    """Produce structured takeaways from a transcript.

    Uses Gemini (free) by default. Set ANTHROPIC_API_KEY to use Claude instead.
    For very long transcripts (>100k chars), chunks and merges.
    """
    if backend is None:
        backend = _detect_backend()

    client, call_fn = _get_backend(backend)
    label = "Gemini" if backend == "gemini" else "Claude"

    if len(transcript) <= _CHUNK_SIZE + _CHUNK_OVERLAP:
        prompt = (
            f"Episode title: {episode_title}\n\n"
            f"Transcript:\n{transcript}"
        )
        print(f"  Summarizing with {label}...")
        return call_fn(client, _SYSTEM_PROMPT, prompt)

    # Multi-pass: chunk → summarize each → merge
    chunks: list[str] = []
    start = 0
    while start < len(transcript):
        end = start + _CHUNK_SIZE
        chunks.append(transcript[start:end])
        start = end - _CHUNK_OVERLAP

    print(f"  Long transcript ({len(transcript)} chars) — "
          f"splitting into {len(chunks)} chunks...")

    partial_summaries: list[str] = []
    for i, chunk in enumerate(chunks, 1):
        print(f"  Summarizing chunk {i}/{len(chunks)} with {label}...")
        prompt = (
            f"Episode title: {episode_title}\n"
            f"(Part {i} of {len(chunks)})\n\n"
            f"Transcript:\n{chunk}"
        )
        summary = call_fn(client, _SYSTEM_PROMPT, prompt)
        partial_summaries.append(summary)

    print("  Merging partial summaries...")
    merge_prompt = (
        f"Episode title: {episode_title}\n\n"
        f"Partial summaries to merge:\n\n"
        + "\n\n---\n\n".join(partial_summaries)
    )
    return call_fn(client, _MERGE_SYSTEM, merge_prompt)
