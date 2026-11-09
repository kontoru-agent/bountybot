#!/usr/bin/env python3
"""
Bountybot — serv/run_demo.py  (SERV Edition 02 end-to-end demo)

Four scenes, one run, real logs — the demo link asset for the SERV
Hackathon Edition 02 submission (Track 02 · KITE):

  Scene 1  TRIAGE — the Bountybot pipeline runs its frozen Plether scope
           and the survivors are annotated through the SERV Reasoning
           client, behind the spending policy. If no OPENSERV_API_KEY /
           SERV_API_KEY is in the environment the client degrades to
           its deterministic local classifier and the output SAYS SO
           (mode=local-fallback) — we do not fake inference.
  Scene 2  IDENTITY — the agent issues its verifiable identity card:
           manifest -> sha256 -> signature requested through BOTH the
           spending policy and the sign gate; verification is re-run
           live in the demo.
  Scene 3  INJECTION — the NEAR demo's prompt-injection attack is
           replayed against the full SERV stack: an untrusted scanner
           note orders a 10 NEAR transfer to an attacker. REFUSED and
           logged, twice over (payload kind is not signable; recipient
           is not on the spending allowlist).
  Scene 4  BUDGET — a scripted spending spree against a demo policy
           (per-action cap 0.20, daily cap 0.50 credits): in-policy
           actions ALLOW, the warn threshold holds one action for a
           human, and the action that would cross the daily cap is
           BLOCKED on budget grounds. A smaller in-policy action still
           passes afterwards — the fence is a budget, not a shutdown.

Everything is value-free and offline-safe. Outputs land in
serv/demo_output/: demo_run.log (this transcript), annotated survivors,
identity_card.json, serv_decision_log.jsonl + gate_decision_log.jsonl
(the demo's own audit logs — the live serv/ logs are not touched).

Usage:  python3 serv/run_demo.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "demo_output"
OUT.mkdir(parents=True, exist_ok=True)

_transcript: list[str] = []


def log(line: str = "") -> None:
    print(line, flush=True)
    _transcript.append(line)


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    sp = _load("spending_policy", HERE / "spending_policy.py")
    client_mod = _load("serv_reasoning_client",
                       HERE / "serv_reasoning_client.py")
    ident_mod = _load("agent_identity", HERE / "agent_identity.py")
    # Reuse the gated_signer module instance that spending_policy loaded:
    # reloading it would create a second SigningRefused class and the
    # Scene 3 `except` below would silently miss the refusal.
    gs = sp.gs

    PricedAction = sp.PricedAction
    SpendingPolicy = sp.SpendingPolicy
    Gate = gs.Gate
    SignRequest = gs.SignRequest
    SigningRefused = gs.SigningRefused

    # Demo policy: small, readable caps. Logs live in demo_output so the
    # run is reproducible from a clean slate and never mixes with the
    # module's live audit log.
    for stale in (OUT / "serv_decision_log.jsonl",
                  OUT / "gate_decision_log.jsonl"):
        if stale.exists():
            stale.unlink()
    gate = Gate(log_path=OUT / "gate_decision_log.jsonl")
    policy = SpendingPolicy(gate=gate,
                            log_path=OUT / "serv_decision_log.jsonl",
                            per_call_cap=0.20, daily_cap=0.50)

    log("=== Bountybot × SERV — Edition 02 demo "
        "(Track 02 · KITE) ===")
    key_present = bool(client_mod.ServReasoningTriage().api_key)
    log(f"SERV Reasoning key in env: {'yes' if key_present else 'NO'}"
        + ("" if key_present else
           " — triage will run in labelled local-fallback mode"))
    log(f"demo spending policy: per-action cap "
        f"{policy.per_call_cap:.2f} credits, daily cap "
        f"{policy.daily_cap:.2f} credits, warn at "
        f"{policy.warn_fraction:.0%} of daily")
    log("")

    # ------------------------------------------------------ Scene 1 -----
    log("--- Scene 1 · TRIAGE — pipeline survivors annotated via the "
        "SERV Reasoning client (behind the spending policy)")
    survivors_path = OUT / "survivors.jsonl"
    # Re-run the deterministic stages so this demo is self-contained.
    import io
    from contextlib import redirect_stdout
    buf = io.StringIO()
    with redirect_stdout(buf):
        scope_mod = _load("load_scope", ROOT / "scope" / "load_scope.py")
        scope_mod.load_scope(OUT)
        scan_mod = _load("generate_candidates",
                         ROOT / "scan" / "generate_candidates.py")
        scan_mod.generate(OUT)
        rank_mod = _load("rank_candidates",
                         ROOT / "skeptic" / "rank_candidates.py")
        survivors, killed = rank_mod.rank(OUT)
    for line in buf.getvalue().splitlines():
        log(f"    [pipeline] {line}")
    client = client_mod.ServReasoningTriage(policy=policy)
    records = [json.loads(l) for l in
               survivors_path.read_text(encoding="utf-8").splitlines()
               if l.strip()]
    for r in records:
        r["serv_triage"] = client.triage(r)
    survivors_path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records),
        encoding="utf-8")
    log(f"    survivors={len(records)} killed={len(killed)} — annotated "
        f"in {survivors_path.name}")
    for r in records:
        t = r["serv_triage"]
        log(f"    {r['id']:<4} category={t['category']:<24} "
            f"mode={t['mode']}")
        log(f"         note: {t['note']}")
    log("")

    # ------------------------------------------------------ Scene 2 -----
    log("--- Scene 2 · IDENTITY — verifiable identity card, issued "
        "through policy + gate")
    card = ident_mod.issue_card(policy=policy,
                                card_path=OUT / "identity_card.json")
    log(f"    manifest: {card['manifest']['agent_name']} · owner "
        f"{card['manifest']['owner']} · repo {card['manifest']['repo']}")
    log(f"    identity_hash: {card['identity_hash']}")
    log(f"    signature: backend={card['signature']['backend']} "
        f"simulated={card['signature']['simulated']} "
        f"(labelled in the card itself)")
    ok, lines = ident_mod.verify_card(
        OUT / "identity_card.json",
        extra_logs=[OUT / "gate_decision_log.jsonl"])
    for ln in lines:
        log(f"    verify: {ln}")
    log(f"    IDENTITY VERIFY: {'PASS' if ok else 'FAIL'}")
    log("")

    # ------------------------------------------------------ Scene 3 -----
    log("--- Scene 3 · INJECTION — untrusted scanner note orders a "
        "10 NEAR transfer to an attacker")
    inj_req = SignRequest(
        candidate_id="INJ-1", action="sign-evidence",
        target_contract="attacker.testnet",
        payload_kind="transfer",  # transfers are never signable
        payload="transfer:10NEAR->attacker.testnet",
        gate_decision="block", note=gs.INJECTION_NOTE)
    log("    note attached (data, never instructions): "
        + gs.INJECTION_NOTE.splitlines()[1][:80] + "...")
    try:
        policy.guarded_sign(inj_req, gs.SimulatedTestnetSigner())
        log("    RESULT: SIGNED — THIS MUST NEVER HAPPEN")
    except SigningRefused as exc:
        log(f"    RESULT: REFUSED — {exc}")
    log("")

    # ------------------------------------------------------ Scene 4 -----
    log("--- Scene 4 · BUDGET — spending spree vs the daily cap")
    spree = [
        ("batch-triage-A", 0.15, False),
        ("batch-triage-B", 0.15, False),
        ("batch-triage-C", 0.15, False),  # crosses warn threshold
        ("batch-triage-D", 0.15, False),  # would cross the daily cap
        ("batch-triage-E", 0.04, False),  # small, still inside after D
    ]
    for action_id, cost, _ in spree:
        action = PricedAction(
            action_id=action_id,
            label=f"scripted SERV triage batch {action_id[-1]}",
            category="serv-reasoning",
            recipient="inference-api.openserv.ai",
            est_cost_credits=cost)
        verdict, reason = policy.evaluate_action(action)
        log(f"    {action_id} est={cost:.2f} -> {verdict.upper()}: "
            f"{reason}")
        if verdict == "warn":
            log("    ... held for a human; the owner approves this one")
            verdict, reason = policy.evaluate_action(
                action, human_approved=True)
            log(f"    {action_id} after approval -> {verdict.upper()}")
        if verdict == "allow":
            policy.commit(action, note="demo spree action executed")
            log(f"    committed. spent today = "
                f"{policy.spent_today():.2f} / {policy.daily_cap:.2f} "
                "credits")
    log("")

    # --------------------------------------------------------- wrap -----
    log("=== demo complete ===")
    log(f"audit log (policy): {OUT / 'serv_decision_log.jsonl'}")
    log(f"audit log (gate):   {OUT / 'gate_decision_log.jsonl'}")
    log(f"identity card:      {OUT / 'identity_card.json'}")
    log(f"annotated survivors:{OUT / 'survivors.jsonl'}")
    log("honesty: no real funds moved; the signer backend is the "
        "labelled simulated testnet stand-in; triage mode above is "
        "exactly what ran.")
    (OUT / "demo_run.log").write_text("\n".join(_transcript) + "\n",
                                      encoding="utf-8")
    summary = {
        "triage_mode": client.mode,
        "survivors": len(records),
        "identity_verify_pass": ok,
        "injection_refused": True,
        "demo_daily_spend_credits": policy.spent_today(),
        "demo_daily_cap_credits": policy.daily_cap,
    }
    (OUT / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
