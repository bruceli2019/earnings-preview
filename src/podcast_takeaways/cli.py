"""CLI entry point for podcast-takeaways."""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="podcast-takeaways",
        description="Fetch, transcribe, and summarize podcast episodes.",
    )

    src = p.add_mutually_exclusive_group()
    src.add_argument("--rss", help="RSS feed URL")
    src.add_argument("--url", help="Direct audio URL (MP3)")

    p.add_argument(
        "--episode", type=int, default=None,
        help="Episode number (1 = latest). Use with --rss.",
    )
    p.add_argument(
        "--search", default=None,
        help="Search episode by title keyword. Use with --rss.",
    )
    p.add_argument(
        "--list", action="store_true", dest="list_episodes",
        help="List all episodes in the feed and exit.",
    )
    p.add_argument(
        "--model", default="base",
        choices=["tiny", "base", "small", "medium", "turbo"],
        help="Whisper model size (default: base).",
    )
    p.add_argument(
        "--output", default=None,
        help="Write takeaways to this file (default: stdout).",
    )
    p.add_argument(
        "--transcript-only", action="store_true",
        help="Only transcribe, skip summarization.",
    )
    p.add_argument(
        "--keep-transcript", action="store_true",
        help="Save transcript alongside takeaways.",
    )
    p.add_argument(
        "--max-length", type=int, default=None,
        help="Skip episodes longer than N minutes.",
    )
    return p


def main(argv: list[str] | None = None) -> None:
    args = _build_parser().parse_args(argv)

    if not args.rss and not args.url:
        print("Error: Provide --rss <feed-url> or --url <audio-url>.", file=sys.stderr)
        sys.exit(1)

    from podcast_takeaways.fetcher import (
        download_audio,
        parse_feed,
        select_episode,
        Episode,
    )

    episode_title = "Unknown Episode"
    audio_url = ""

    # --- RSS feed path ---
    if args.rss:
        print(f"Parsing feed: {args.rss}")
        episodes = parse_feed(args.rss)

        if not episodes:
            print("Error: No episodes with audio found in this feed.", file=sys.stderr)
            sys.exit(1)

        if args.list_episodes:
            print(f"\n{len(episodes)} episodes:\n")
            for i, ep in enumerate(episodes, 1):
                dur = f" [{ep.duration}]" if ep.duration else ""
                print(f"  {i:3d}. {ep.title}{dur}")
                if ep.published:
                    print(f"       {ep.published}")
            return

        ep = select_episode(episodes, number=args.episode, search=args.search)
        episode_title = ep.title
        audio_url = ep.url
        print(f"Selected: {ep.title}")
        if ep.published:
            print(f"  Published: {ep.published}")

        # Check max-length
        if args.max_length and ep.duration:
            try:
                parts = ep.duration.split(":")
                if len(parts) == 3:
                    mins = int(parts[0]) * 60 + int(parts[1])
                elif len(parts) == 2:
                    mins = int(parts[0])
                else:
                    mins = int(parts[0]) // 60
                if mins > args.max_length:
                    print(
                        f"  Skipping: {mins}min exceeds --max-length {args.max_length}min."
                    )
                    return
            except (ValueError, IndexError):
                pass

    # --- Direct URL path ---
    if args.url:
        audio_url = args.url
        episode_title = Path(args.url).stem

    # --- Download audio ---
    slug = Episode(title=episode_title, url="", published="", description="").slug
    tmp_dir = Path(tempfile.gettempdir()) / "podcast-takeaways"
    audio_path = tmp_dir / f"{slug}.mp3"

    if audio_path.exists() and audio_path.stat().st_size > 0:
        print(f"  Audio already downloaded: {audio_path}")
    else:
        print(f"  Downloading audio...")
        download_audio(audio_url, audio_path)

    # --- Transcribe ---
    from podcast_takeaways.transcriber import transcribe

    print("Transcribing...")
    transcript = transcribe(audio_path, slug, model=args.model)
    print(f"  Transcript length: {len(transcript)} chars")

    if args.transcript_only:
        if args.output:
            Path(args.output).write_text(transcript, encoding="utf-8")
            print(f"Transcript saved to {args.output}")
        else:
            print("\n" + transcript)
        return

    # --- Summarize ---
    from podcast_takeaways.summarizer import summarize

    print("Summarizing...")
    takeaways = summarize(transcript, episode_title)

    # --- Output ---
    if args.output:
        Path(args.output).write_text(takeaways, encoding="utf-8")
        print(f"\nTakeaways saved to {args.output}")
    else:
        print("\n" + takeaways)

    if args.keep_transcript:
        tx_path = Path(args.output or "takeaways.md").with_suffix(".transcript.txt")
        tx_path.write_text(transcript, encoding="utf-8")
        print(f"Transcript saved to {tx_path}")


if __name__ == "__main__":
    main()
