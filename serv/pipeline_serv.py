#!/usr/bin/env python3
"""
Bountybot — serv/pipeline_serv.py  (pipeline variant with SERV Reasoning)

Identical stages to pipeline.py (scope -> scan -> skeptic), but the
annotation step runs through SERV Reasoning (serv_reasoning_client)
instead of NEAR AI Cloud. pipeline.py itself is untouched — the NEAR
submission's default behaviour does not change.

Usage:  python3 serv/pipeline_serv.py
Outputs land in serv/demo_output/ (kept apart from the NEAR demo_output/).
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "demo_output"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    print("=== Bountybot pipeline (SERV Reasoning variant) — "
          "Plether demo target ===\n")
    scope_mod = _load("load_scope", ROOT / "scope" / "load_scope.py")
    scope_mod.load_scope(OUT)
    print()
    scan_mod = _load("generate_candidates",
                     ROOT / "scan" / "generate_candidates.py")
    scan_mod.generate(OUT)
    print(f"[scan] candidates -> {OUT / 'candidates.jsonl'}")
    print()
    rank_mod = _load("rank_candidates",
                     ROOT / "skeptic" / "rank_candidates.py")
    survivors, killed = rank_mod.rank(OUT)
    print(f"[skeptic] survivors={len(survivors)} killed={len(killed)} -> "
          f"survivors.jsonl + triage_report.md")
    print()
    client_mod = _load("serv_reasoning_client",
                       HERE / "serv_reasoning_client.py")
    client_mod.annotate(OUT / "survivors.jsonl")
    print("\n=== done — artefacts in serv/demo_output/ (survivors are "
          "hypotheses; PoC gate is Layer 4) ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
