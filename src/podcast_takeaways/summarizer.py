"""Summarize podcast transcripts using Gemini (free tier)."""

from __future__ import annotations

import os
import time

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


def _get_client():
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
    max_retries: int = 3,
) -> str:
    """Send a message to Gemini with retry on rate limits."""
    for attempt in range(1, max_retries + 1):
        try:
            resp = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=user_message,
                config={
                    "system_instruction": system,
                    "max_output_tokens": 4096,
                },
            )
            return resp.text
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                wait = 30 * attempt
                print(f"  Rate limited, waiting {wait}s (attempt {attempt}/{max_retries})...")
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("Gemini rate limit exceeded after retries. Try again in a minute.")


def summarize(transcript: str, episode_title: str) -> str:
    """Produce structured takeaways from a transcript.

    Uses Gemini 2.0 Flash (free tier). Set GEMINI_API_KEY env var.
    For very long transcripts (>100k chars), chunks and merges.
    """
    client = _get_client()

    if len(transcript) <= _CHUNK_SIZE + _CHUNK_OVERLAP:
        prompt = (
            f"Episode title: {episode_title}\n\n"
            f"Transcript:\n{transcript}"
        )
        print("  Summarizing with Gemini...")
        return _call_gemini(client, _SYSTEM_PROMPT, prompt)

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
        print(f"  Summarizing chunk {i}/{len(chunks)} with Gemini...")
        prompt = (
            f"Episode title: {episode_title}\n"
            f"(Part {i} of {len(chunks)})\n\n"
            f"Transcript:\n{chunk}"
        )
        summary = _call_gemini(client, _SYSTEM_PROMPT, prompt)
        partial_summaries.append(summary)

    print("  Merging partial summaries...")
    merge_prompt = (
        f"Episode title: {episode_title}\n\n"
        f"Partial summaries to merge:\n\n"
        + "\n\n---\n\n".join(partial_summaries)
    )
    return _call_gemini(client, _MERGE_SYSTEM, merge_prompt)
