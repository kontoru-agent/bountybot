#!/usr/bin/env python3
"""
Bountybot — serv/serv_reasoning_client.py  (SERV Reasoning triage client)

The same router pattern as near/ai_cloud_client.py, pointed at SERV
Reasoning instead: OpenAI-compatible API at
https://inference-api.openserv.ai/v1, `/chat/completions` endpoint.

    OPENSERV_BASE_URL  (default https://inference-api.openserv.ai/v1)
    OPENSERV_MODEL     (default from serv/config.json: gpt-6-luna,
                        the cheapest model in the SERV catalog)
    OPENSERV_API_KEY   (env ONLY — never a file, never printed, never
                        logged; SERV_API_KEY is also accepted, matching
                        the name used in the official SERV docs)

SERV requires a system prompt on every request; ours fixes the triage
policy in code: the model only *annotates* (category + rationale). It can
never promote or kill a candidate — the deterministic skeptic gates own
every verdict. An LLM agreeing with itself is not evidence.

Spending gate: when a SpendingPolicy is attached, every call is priced
(estimated from config token prices) and authorised BEFORE it is made.
A `block` verdict means no HTTP request leaves the machine; a `warn`
verdict holds the call for a human. Both degrade to the local
classifier, labelled as such.

Fallback: with no key (or on any request error), triage degrades to the
same deterministic LOCAL keyword classifier as the NEAR client and says
so in its output (`mode: local-fallback`). The pipeline therefore runs
end-to-end offline, and the day a key is provided the same call sites
upgrade to SERV Reasoning with zero code changes.

CLI:  python3 serv/serv_reasoning_client.py [survivors.jsonl]
      (annotates the file in place with a `serv_triage` object per record)
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CONFIG = json.loads((HERE / "config.json").read_text(encoding="utf-8"))


def _load_near_client():
    """Reuse the NEAR client's deterministic local classifier verbatim —
    one classifier, two reasoning backends, identical fallback labels."""
    spec = importlib.util.spec_from_file_location(
        "ai_cloud_client", ROOT / "near" / "ai_cloud_client.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ai_cloud_client"] = mod
    spec.loader.exec_module(mod)
    return mod


_nc = _load_near_client()
local_classify = _nc.local_classify


def _load_spending_policy():
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    spec = importlib.util.spec_from_file_location(
        "spending_policy", HERE / "spending_policy.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["spending_policy"] = mod
    spec.loader.exec_module(mod)
    return mod


_sp = _load_spending_policy()
PricedAction = _sp.PricedAction
SpendingPolicy = _sp.SpendingPolicy

SYSTEM_PROMPT = (
    "You are the triage classifier inside Bountybot, an evidence-gated bug "
    "bounty agent. Classify the candidate finding into exactly one category "
    "from: liquidation-accounting, tranche-accounting, queue-liveness, "
    "oracle-staleness, access-control, rounding-accounting, other. Reply "
    "with ONLY a JSON object: {\"category\": \"...\", \"rationale\": \"one "
    "sentence\"}. You are annotating, not judging: never claim the candidate "
    "is or is not a real bug."
)

RECIPIENT_HOST = "inference-api.openserv.ai"
EST_OUTPUT_TOKENS = 140  # a category + one sentence, bounded by the prompt


def estimate_cost_credits(text: str) -> tuple[float, int, int]:
    """Estimate the price of one triage call from config token prices.
    Returns (credits, est_input_tokens, est_output_tokens)."""
    est_in = (len(SYSTEM_PROMPT) + len(text[:6000])) // 4
    price = CONFIG["pricing_usd_per_mtok"]
    cost = (est_in * price["input"] + EST_OUTPUT_TOKENS * price["output"]) \
        / 1_000_000
    return round(cost, 6), est_in, EST_OUTPUT_TOKENS


class ServReasoningTriage:
    def __init__(self, policy: SpendingPolicy | None = None) -> None:
        self.base_url = os.environ.get(
            "OPENSERV_BASE_URL", CONFIG["base_url"]).rstrip("/")
        self.model = os.environ.get("OPENSERV_MODEL", CONFIG["model"])
        # Primary name per this build's spec; SERV_API_KEY per official docs.
        self.api_key = (os.environ.get("OPENSERV_API_KEY", "")
                        or os.environ.get("SERV_API_KEY", ""))
        self.policy = policy

    @property
    def mode(self) -> str:
        return "serv" if self.api_key else "local-fallback"

    def _local(self, text: str, note: str, model=None,
               policy_verdict: str | None = None) -> dict:
        cat, why = local_classify(text)
        out = {"mode": "local-fallback", "model": model, "category": cat,
               "rationale": why, "note": note}
        if policy_verdict is not None:
            out["policy_verdict"] = policy_verdict
        return out

    def triage(self, candidate: dict) -> dict:
        text = (f"{candidate.get('title', '')}\n"
                f"{candidate.get('description', '')}")
        est_cost, est_in, est_out = estimate_cost_credits(text)

        action = None
        if self.policy is not None:
            action = PricedAction(
                action_id=f"triage-{candidate.get('id', 'unknown')}",
                label=f"triage {candidate.get('id', '?')} via SERV "
                      f"Reasoning",
                category="serv-reasoning",
                recipient=RECIPIENT_HOST,
                est_cost_credits=est_cost)
            verdict, reason = self.policy.evaluate_action(action)
            if verdict != "allow":
                return self._local(
                    text,
                    note=(f"spending policy {verdict.upper()}: {reason}; "
                          "no SERV API call was made — local classifier "
                          "used"),
                    policy_verdict=verdict)

        if not self.api_key:
            return self._local(
                text,
                note=("no OPENSERV_API_KEY/SERV_API_KEY in env — "
                      "deterministic local classifier used; no model was "
                      "called"),
                policy_verdict="allow" if action is not None else None)

        try:
            body = json.dumps({
                "model": self.model,
                "reasoning_effort": CONFIG["reasoning_effort"],
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": text[:6000]},
                ],
            }).encode()
            req = urllib.request.Request(
                f"{self.base_url}/chat/completions", data=body, headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read())
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            if action is not None:
                self.policy.commit(
                    action, note="SERV Reasoning call completed")
            return {"mode": "serv", "model": self.model,
                    "category": parsed["category"],
                    "rationale": parsed["rationale"],
                    "est_cost_credits": est_cost,
                    "est_tokens": {"input": est_in, "output": est_out},
                    "note": "SERV Reasoning (OpenAI-compatible API); "
                            "annotation only"}
        except Exception as exc:  # network, auth, shape — degrade, never crash
            if action is not None:
                self.policy.commit(
                    action, note=f"SERV call attempted, failed "
                                 f"({type(exc).__name__}); spend committed "
                                 "conservatively")
            return self._local(
                text,
                note=(f"SERV call failed ({type(exc).__name__}); local "
                      "classifier used instead"),
                model=self.model,
                policy_verdict="allow" if action is not None else None)


def annotate(path: Path, policy: SpendingPolicy | None = None) -> int:
    client = ServReasoningTriage(policy=policy)
    records = [json.loads(l)
               for l in path.read_text(encoding="utf-8").splitlines()
               if l.strip()]
    for r in records:
        r["serv_triage"] = client.triage(r)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n"
                            for r in records), encoding="utf-8")
    print(f"[serv-ai] mode={client.mode} model={client.model} "
          f"annotated={len(records)} record(s) in {path.name}")
    for r in records:
        t = r["serv_triage"]
        print(f"[serv-ai]   {r['id']:<4} category={t['category']:<24} "
              f"mode={t['mode']}")
    return 0


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else (
        HERE.parent / "demo_output" / "survivors.jsonl")
    raise SystemExit(annotate(target))
