"""
Build SHARE_PACK.md — handoff + all source files for pasting into another agent.

Excludes secrets, parquet, caches, and generated outputs.

Usage:
  python scripts/export_share_pack.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "SHARE_PACK.md"

SKIP_DIR_NAMES = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".ipynb_checkpoints",
    "parquet",
}

SKIP_FILES = {
    ".env",
    "SHARE_PACK.md",
}

# Include research metrics/summaries; skip bulky trade/equity CSVs
INCLUDE_SUFFIXES = {".py", ".txt", ".md", ".gitignore", ".csv"}
INCLUDE_CSV_NAMES = {
    "v1_ablation_summary.csv",
    "v1_tighten_summary.csv",
    "v1_regime_summary.csv",
    "regime_spec_summary.csv",
    "regime_15m_summary.csv",
}


def should_skip(path: Path) -> bool:
    rel = path.as_posix() if not path.is_absolute() else path.name
    name = path.name
    if name in SKIP_FILES:
        return True
    if path.suffix == ".parquet":
        return True
    for part in path.parts:
        if part in SKIP_DIR_NAMES:
            return True
    if path.suffix == ".csv":
        # Keep summary tables only (not every trade blotter)
        if name not in INCLUDE_CSV_NAMES and "summary" not in name:
            return True
    return False


def main() -> None:
    chunks: list[str] = []
    handoff = ROOT / "HANDOFF.md"
    if handoff.exists():
        chunks.append(handoff.read_text(encoding="utf-8"))
        chunks.append("\n\n---\n\n# Source dump\n\n")

    files = sorted(
        p
        for p in ROOT.rglob("*")
        if p.is_file()
        and not should_skip(p.relative_to(ROOT))
        and (p.suffix in INCLUDE_SUFFIXES or p.name == ".gitignore")
    )

    for path in files:
        rel = path.relative_to(ROOT).as_posix()
        if rel == "HANDOFF.md":
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        lang = "python" if path.suffix == ".py" else "text"
        chunks.append(f"## `{rel}`\n\n```{lang}\n{text}\n```\n\n")

    OUT.write_text("".join(chunks), encoding="utf-8")
    size_kb = OUT.stat().st_size / 1024
    print(f"Wrote {OUT} ({size_kb:.1f} KB, {len(files)} files)")
    print("Includes: all .py source, HANDOFF, metrics .txt, summary CSVs")
    print("Excluded: .env, parquet market data, per-trade equity CSVs")


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    main()
