#!/usr/bin/env python3
"""
Bountybot — serv/spending_policy.py  (owner-controlled spending limits)

The KITE half of the SERV Edition 02 build: an agent that can act
economically on its owner's behalf needs a *budget fence* in code, not in
prompts. This module wraps the existing policy gate
(`near/gated_signer.Gate`) with a spending policy:

  * every priced action (a SERV Reasoning call, a signing request, ...)
    is checked BEFORE it runs:
        - category and recipient must be on the owner allowlist,
        - estimated cost must fit the per-action cap,
        - today's committed spend + estimate must fit the daily cap,
        - crossing `warn_threshold_fraction` of the daily cap yields
          `warn` — the action is held for a human, not executed;
  * verdicts combine with the underlying sign gate for signing actions
    (most restrictive wins: block > warn > allow);
  * EVERY decision and every committed execution is appended to one
    unified audit log (serv/serv_decision_log.jsonl) — the "auditable
    steps" the hackathon asks for.

Costs are estimates in SERV credits (≈USD). The policy never moves money
itself; it only refuses, holds, or permits. Free-form text is data here
too: the policy reads structured fields only, so an injected note cannot
talk an action past the caps (the injection demo lives in run_demo.py).

Stdlib only, like the rest of Bountybot.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CONFIG = json.loads((HERE / "config.json").read_text(encoding="utf-8"))
DEFAULT_LOG_PATH = HERE / "serv_decision_log.jsonl"


def _load_gate_module():
    """Load near/gated_signer.py the same way pipeline.py loads modules."""
    spec = importlib.util.spec_from_file_location(
        "gated_signer", ROOT / "near" / "gated_signer.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["gated_signer"] = mod
    spec.loader.exec_module(mod)
    return mod


gs = _load_gate_module()
Gate = gs.Gate
SignRequest = gs.SignRequest
SigningRefused = gs.SigningRefused

_SEVERITY = {"allow": 0, "warn": 1, "block": 2}


@dataclass
class PricedAction:
    """A structured, priced action the agent wants to take."""
    action_id: str
    label: str               # human label, e.g. "triage K-1 via SERV"
    category: str            # must be in config allowlist_categories
    recipient: str           # host / contract the spend flows to
    est_cost_credits: float  # estimated cost in SERV credits (≈USD)


@dataclass
class SpendingPolicy:
    gate: Gate = field(default_factory=Gate)
    log_path: Path = field(default=DEFAULT_LOG_PATH)
    per_call_cap: float = field(
        default_factory=lambda: CONFIG["budget"]["per_call_cap_credits"])
    daily_cap: float = field(
        default_factory=lambda: CONFIG["budget"]["daily_cap_credits"])
    warn_fraction: float = field(
        default_factory=lambda: CONFIG["budget"]["warn_threshold_fraction"])
    allowlist_categories: tuple = field(
        default_factory=lambda: tuple(CONFIG["spending"]
                                      ["allowlist_categories"]))
    allowlist_recipients: tuple = field(
        default_factory=lambda: tuple(CONFIG["spending"]
                                      ["allowlist_recipients"]))

    # ------------------------------------------------------------ ledger --
    def _append(self, entry: dict) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def spent_today(self) -> float:
        """Sum of COMMITTED executions logged for today (UTC)."""
        if not self.log_path.exists():
            return 0.0
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        total = 0.0
        for line in self.log_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            e = json.loads(line)
            if e.get("kind") == "execution" and e["ts"].startswith(today):
                total += float(e.get("est_cost_credits", 0.0))
        return round(total, 6)

    # ----------------------------------------------------------- verdict --
    def _budget_verdict(self, action: PricedAction) -> tuple[str, str]:
        if action.category not in self.allowlist_categories:
            return "block", (f"category '{action.category}' is not on the "
                             "owner spending allowlist")
        if action.recipient not in self.allowlist_recipients:
            return "block", (f"recipient '{action.recipient}' is not on "
                             "the owner spending allowlist")
        if action.est_cost_credits > self.per_call_cap:
            return "block", (f"estimated cost {action.est_cost_credits:.4f} "
                             f"credits exceeds the per-action cap "
                             f"{self.per_call_cap:.4f}")
        spent = self.spent_today()
        projected = spent + action.est_cost_credits
        if projected > self.daily_cap:
            return "block", (f"daily cap reached: spent "
                             f"{spent:.4f} + est {action.est_cost_credits:.4f}"
                             f" > daily cap {self.daily_cap:.4f} credits")
        if projected >= self.warn_fraction * self.daily_cap:
            return "warn", (f"approaching daily cap: projected "
                            f"{projected:.4f} of {self.daily_cap:.4f} "
                            f"credits (>= {self.warn_fraction:.0%}) — "
                            "human approval required")
        return "allow", (f"within policy: est {action.est_cost_credits:.4f}"
                         f" credits, projected daily {projected:.4f} of "
                         f"{self.daily_cap:.4f}")

    def evaluate_action(self, action: PricedAction,
                        sign_request: SignRequest | None = None,
                        human_approved: bool = False) -> tuple[str, str]:
        """Combined verdict for a priced action (and, for signing actions,
        the wrapped sign gate). Logs a `decision` entry either way."""
        verdict, reason = self._budget_verdict(action)
        if sign_request is not None:
            g_verdict, g_reason = self.gate.evaluate(sign_request)
            if _SEVERITY[g_verdict] > _SEVERITY[verdict]:
                verdict = g_verdict
                reason = f"{reason} | sign gate: {g_reason}"
            else:
                reason = f"{reason} | sign gate: {g_reason}"
        if verdict == "warn" and human_approved:
            verdict = "allow"
            reason += " | warn released by explicit human approval"
        self._append({
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "kind": "decision",
            "action_id": action.action_id,
            "action": action.label,
            "category": action.category,
            "recipient": action.recipient,
            "est_cost_credits": action.est_cost_credits,
            "spent_today_before": self.spent_today(),
            "per_call_cap_credits": self.per_call_cap,
            "daily_cap_credits": self.daily_cap,
            "verdict": verdict,
            "reason": reason,
        })
        return verdict, reason

    def commit(self, action: PricedAction, note: str = "") -> None:
        """Record that an allowed action actually ran (counts as spend)."""
        self._append({
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "kind": "execution",
            "action_id": action.action_id,
            "action": action.label,
            "category": action.category,
            "recipient": action.recipient,
            "est_cost_credits": action.est_cost_credits,
            "spent_today_after": round(
                self.spent_today() + action.est_cost_credits, 6),
            "note": note,
        })

    # ------------------------------------------------------------ signing --
    def guarded_sign(self, sign_request: SignRequest, backend,
                     est_cost_credits: float = 0.0,
                     human_approved: bool = False) -> dict:
        """Sign only if BOTH the budget policy and the sign gate allow it.
        Raises SigningRefused on block / warn-hold, exactly like the gate."""
        action = PricedAction(
            action_id=f"sign-{sign_request.candidate_id}",
            label=f"sign: {sign_request.action} for "
                  f"{sign_request.candidate_id}",
            category="signing",
            recipient=sign_request.target_contract,
            est_cost_credits=est_cost_credits)
        verdict, reason = self.evaluate_action(
            action, sign_request=sign_request,
            human_approved=human_approved)
        if verdict == "block":
            raise SigningRefused(f"BLOCK: {reason}")
        if verdict == "warn":
            raise SigningRefused(f"WARN-HOLD: {reason}")
        out = self.gate.sign(sign_request, backend)  # gate re-checks + logs
        self.commit(action, note="signature produced by gated signer")
        return out
