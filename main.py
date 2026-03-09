"""CLI entry point for the Enterprise Deep Research workflow.

Usage:
    python main.py --query "What is our policy on remote work?"
    python main.py --query "Summarize the 2025 cloud migration plan" --plan-review
    python main.py --query "..." --output report.md --no-stream
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# Load .env before importing any module that reads os.getenv
load_dotenv()

from deep_research.config import load_config  # noqa: E402 (after load_dotenv)
from deep_research.tools import build_search_tools  # noqa: E402
from deep_research.workflow import build_workflow, run_deep_research  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Enterprise Deep Research — powered by Microsoft Agent Framework",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--query",
        "-q",
        required=True,
        help="The research question to investigate.",
    )
    parser.add_argument(
        "--output",
        "-o",
        default=None,
        help="Path to save the final Markdown report (default: auto-named in output dir).",
    )
    parser.add_argument(
        "--plan-review",
        action="store_true",
        default=False,
        help="Enable interactive human review of the research plan before execution.",
    )
    parser.add_argument(
        "--no-stream",
        action="store_true",
        default=False,
        help="Suppress intermediate agent output (only show final report).",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        default=False,
        help="Enable debug-level logging.",
    )
    return parser.parse_args()


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )
    # Suppress noisy library loggers unless in verbose mode
    if not verbose:
        for noisy in ("azure", "httpx", "httpcore", "openai"):
            logging.getLogger(noisy).setLevel(logging.ERROR)


def _save_report(report: str, query: str, output_path: str | None, output_dir: str) -> Path:
    """Save *report* to disk and return the file path."""
    if output_path:
        path = Path(output_path)
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_query = "".join(c if c.isalnum() or c in "-_ " else "_" for c in query[:40])
        safe_query = safe_query.strip().replace(" ", "_")
        filename = f"research_{safe_query}_{timestamp}.md"
        path = Path(output_dir) / filename

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")
    return path


async def main() -> int:
    args = _parse_args()
    _setup_logging(args.verbose)

    # ── Load configuration ────────────────────────────────────────────────────
    try:
        cfg = load_config()
    except EnvironmentError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    # CLI flag overrides config-file plan_review setting
    if args.plan_review:
        cfg.workflow.enable_plan_review = True

    # ── Build tools and workflow ──────────────────────────────────────────────
    print("Initializing enterprise deep research workflow…")
    search_tools = build_search_tools(cfg.knowledge_base)
    workflow = build_workflow(cfg, search_tools)

    # ── Run research ──────────────────────────────────────────────────────────
    try:
        report = await run_deep_research(
            workflow,
            args.query,
            verbose=not args.no_stream,
        )
    except KeyboardInterrupt:
        print("\nResearch interrupted by user.", file=sys.stderr)
        return 130
    except Exception as exc:  # noqa: BLE001
        print(f"\nResearch failed: {exc}", file=sys.stderr)
        if args.verbose:
            raise
        return 1

    # ── Save report ───────────────────────────────────────────────────────────
    saved_path = _save_report(report, args.query, args.output, cfg.workflow.output_dir)
    print(f"\nReport saved to: {saved_path}")

    # Also print the report to stdout
    print("\n" + "=" * 70)
    print("FINAL REPORT")
    print("=" * 70)
    print(report)

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
