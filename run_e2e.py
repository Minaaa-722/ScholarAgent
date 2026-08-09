#!/usr/bin/env python3
"""
End-to-End Pipeline Runner — ScholarAgent
------------------------------------------
Drives the full survey-generation pipeline:
  课题输入 → 文献检索 → 综述初稿撰写 → 5维度校验纠错 → 多轮迭代 → 输出CVPR格式综述论文

Usage:
    python run_e2e.py                          # 使用默认课题
    python run_e2e.py --topic "Your Topic"     # 自定义课题
    python run_e2e.py --topic "X" --keywords "a,b,c" --goal "goal"
    python run_e2e.py --dry-run                # 仅校验配置，不调用LLM
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime

# Ensure the project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Fix Unicode display on Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from dotenv import load_dotenv

load_dotenv()

from agent.core.llm import OpenAILLM
from agent.core.harness import Harness, HarnessConfig

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("e2e")


# ---------------------------------------------------------------------------
# Progress callback
# ---------------------------------------------------------------------------
def on_progress(stage: str, message: str, detail: dict | None):
    """Display pipeline progress in the console."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    icon = {
        "planning": "📋",
        "retrieval": "🔍",
        "analysis": "📊",
        "writing": "✍️",
        "validation": "✅",
        "feedback": "🔄",
        "complete": "🎉",
        "error": "❌",
    }.get(stage, "•")
    print(f"  {icon} [{timestamp}] [{stage.upper():>10}] {message}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="ScholarAgent E2E Pipeline Runner")
    parser.add_argument(
        "--topic",
        default="Efficient Vision Transformers for Edge Deployment",
        help="Research topic for the survey paper",
    )
    parser.add_argument(
        "--keywords",
        default="vision transformer, efficient, edge deployment, model compression, lightweight, mobile-friendly",
        help="Comma-separated keywords",
    )
    parser.add_argument(
        "--goal",
        default="Write a comprehensive CVPR-format survey covering efficient vision transformer architectures, "
                "model compression techniques, hardware-aware design, and deployment on edge devices",
        help="Goal description for the survey",
    )
    parser.add_argument(
        "--max-papers",
        type=int,
        default=50,
        help="Maximum number of papers to retrieve",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=2,
        help="Maximum writing-validation retry rounds",
    )
    parser.add_argument(
        "--quality-threshold",
        type=float,
        default=0.7,
        help="Quality pass threshold (0.0–1.0)",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("LLM_MODEL", "deepseek-v4-flash"),
        help="LLM model name (default: deepseek-v4-flash)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate configuration and exit without calling LLM",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Directory to write output files",
    )
    args = parser.parse_args()

    print("=" * 72)
    print("  ScholarAgent — End-to-End Pipeline Runner")
    print("=" * 72)
    print(f"\n  Topic:        {args.topic}")
    print(f"  Keywords:     {args.keywords}")
    print(f"  Max papers:   {args.max_papers}")
    print(f"  Max retries:  {args.max_retries}")
    print(f"  Quality thr:  {args.quality_threshold}")
    print(f"  LLM model:    {args.model}")
    print()

    # ---- Validate API key ----
    api_key = os.getenv("LLM_API_KEY", "")
    if not api_key:
        print("  ❌ LLM_API_KEY not set. Create a .env file with:\n")
        print("     LLM_API_KEY=sk-...")
        print("     LLM_MODEL=gpt-4o\n")
        sys.exit(1)

    if args.dry_run:
        print("  ✅ Dry-run mode: API key present, configuration valid.")
        print("  ✅ OpenAILLM can be instantiated.")
        try:
            llm = OpenAILLM(api_key=api_key, model=args.model)
            print(f"  ✅ Model: {llm.model}")
        except Exception as e:
            print(f"  ❌ LLM init failed: {e}")
            sys.exit(1)
        print("\n  Dry-run complete. Use --dry-run to skip LLM calls.")
        return

    # ---- Initialize ----
    print("  Initializing LLM and Harness…")
    llm = OpenAILLM(api_key=api_key, model=args.model)
    config = HarnessConfig(
        max_papers=args.max_papers,
        max_retries=args.max_retries,
        quality_threshold=args.quality_threshold,
    )
    harness = Harness(config=config, llm=llm)

    # ---- Run pipeline ----
    print("\n" + "─" * 72)
    print("  🚀  Starting Pipeline")
    print("─" * 72)
    print()

    start_time = time.time()

    try:
        result = harness.run(
            topic=args.topic,
            keywords=args.keywords,
            goal=args.goal,
            on_progress=on_progress,
        )
    except KeyboardInterrupt:
        print("\n\n  ⚠️  Interrupted by user.")
        # Save partial execution log
        _save_execution_log(harness.execution_log, args.output_dir)
        sys.exit(130)
    except Exception as e:
        print(f"\n\n  ❌ Unhandled pipeline exception: {e}")
        logger.exception("Pipeline exception")
        _save_execution_log(harness.execution_log, args.output_dir)
        sys.exit(1)

    elapsed = time.time() - start_time

    # ---- Output results ----
    print("\n" + "─" * 72)
    print("  📊  Pipeline Complete")
    print("─" * 72)
    print(f"\n  Status:          {result.get('status', 'unknown')}")
    print(f"  Rounds:          {result.get('rounds', 0)}")
    print(f"  Retry count:     {result.get('retry_count', 0)}")
    print(f"  Has warnings:    {result.get('has_warnings', False)}")
    print(f"  Elapsed time:    {elapsed:.1f}s")
    print(f"  Execution steps: {len(harness.execution_log)}")

    if result.get("status") == "error":
        print(f"\n  Error: {result.get('error', 'Unknown error')}")
        _save_execution_log(harness.execution_log, args.output_dir)
        _save_paper(result.get("paper", ""), args.output_dir, args.topic)
        sys.exit(1)

    # Save paper
    paper_path = _save_paper(result.get("paper", ""), args.output_dir, args.topic)
    print(f"\n  📄 Survey paper saved to: {paper_path}")

    # Save execution log
    log_path = _save_execution_log(harness.execution_log, args.output_dir)
    print(f"  📋 Execution log saved to: {log_path}")

    # Print summary table
    _print_execution_summary(harness.execution_log)

    print("\n" + "=" * 72)
    print("  ✅  Pipeline finished successfully!" if result.get("status") == "complete"
          else "  ⚠️  Pipeline finished with warnings")
    print("=" * 72)


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------
def _save_paper(paper: str, output_dir: str, topic: str) -> str:
    """Write the survey paper to a file."""
    os.makedirs(output_dir, exist_ok=True)
    safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in topic)[:60]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{safe_name}_{timestamp}.md"
    path = os.path.join(output_dir, filename)

    with open(path, "w", encoding="utf-8") as f:
        f.write(paper)

    return path


def _save_execution_log(execution_log: list[dict], output_dir: str) -> str:
    """Write the execution log to a JSON file."""
    if not execution_log:
        return ""
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(output_dir, f"execution_log_{timestamp}.json")

    with open(path, "w", encoding="utf-8") as f:
        json.dump(execution_log, f, ensure_ascii=False, indent=2)

    return path


def _print_execution_summary(execution_log: list[dict]):
    """Print a compact execution summary."""
    print("\n  ┌─────────────────────────────────────────────────────────────────┐")
    print("  │                     Execution Summary                            │")
    print("  ├──────────────┬──────────┬────────────────────────────────────────┤")
    print("  │ Stage        │ Status   │ Detail                                 │")
    print("  ├──────────────┼──────────┼────────────────────────────────────────┤")

    for entry in execution_log:
        stage = entry.get("stage", "").ljust(12)
        if stage.strip() == "ERROR":
            status = "❌"
            detail = entry.get("error", "")[:50]
        elif stage.strip() == "VALIDATION":
            score = entry.get("score", 0)
            passed = entry.get("passed", False)
            status = "✅" if passed else "🔄"
            detail = f"score={score:.2f}, failures={entry.get('failures', [])}"
        elif stage.strip() == "RETRIEVAL":
            status = "✅"
            detail = f"papers={entry.get('paper_count', 0)}"
        elif stage.strip() == "COMPLETE":
            status = "✅"
            detail = "Pipeline finished"
        else:
            status = "✅"
            detail = "ok"

        print(f"  │ {stage} │ {status}     │ {detail[:50]:<48} │")

    print("  └──────────────┴──────────┴────────────────────────────────────────┘")


if __name__ == "__main__":
    main()