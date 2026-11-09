#!/usr/bin/env python3
"""
Bountybot — serv/agent_identity.py  (verifiable agent identity card)

The KITE track asks for agents with a *verifiable identity*. Bountybot's
answer: an identity card that anyone can check, issued through the same
policy machinery that bounds everything else the agent does.

  1. Build a canonical manifest (JSON, sorted keys): agent name, owner,
     public repo, payout address, and the scope the agent is currently
     hunting (target + frozen commit).
  2. identity_hash = sha256(canonical manifest bytes).
  3. Ask the gated signer to sign that hash — the ONLY payload kind the
     wrapper will ever sign is `evidence_hash`, and the request must
     additionally pass the spending policy (recipient allowlist, caps)
     via SpendingPolicy.guarded_sign. No full-access key is involved;
     the production backend is a function-call key scoped to the single
     `sign` method of the testnet MPC contract (see near/README.md).
  4. Emit serv/identity_card.json: manifest + hash + signature record +
     the decision-log fingerprint of the approval.

Verification (anyone, offline): recompute sha256 over the manifest in
the card and compare with identity_hash; then find the fingerprint in
the decision logs and confirm the entry's verdict is `allow`. Both
steps are implemented in verify_card() below.

Honesty boundary: the offline demo uses the simulated testnet signer,
labelled SIMULATED in the card itself. The card proves the *process* —
that this identity was issued only through the policy gate — not an
on-chain signature, until the testnet backend is provisioned.

CLI:  python3 serv/agent_identity.py --issue   (write identity_card.json)
      python3 serv/agent_identity.py --verify [card] [extra-log ...]
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CONFIG = json.loads((HERE / "config.json").read_text(encoding="utf-8"))
CARD_PATH = HERE / "identity_card.json"
SIGNER_CONTRACT = "v1.signer-prod.testnet"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_sp = _load("spending_policy", HERE / "spending_policy.py")
_gs = _load("gated_signer", ROOT / "near" / "gated_signer.py")
SpendingPolicy = _sp.SpendingPolicy
PricedAction = _sp.PricedAction
Gate = _gs.Gate
SignRequest = _gs.SignRequest
SimulatedTestnetSigner = _gs.SimulatedTestnetSigner


def build_manifest() -> dict:
    ident = CONFIG["identity"]
    return {
        "agent_name": ident["agent_name"],
        "owner": ident["owner"],
        "repo": ident["repo"],
        "payout_near_address": ident["payout_near_address"],
        "scope_target": ident["scope_target"],
        "scope_commit": ident["scope_commit"],
        "serv_module": "bountybot/serv@1.0.0 (SERV Hackathon Edition 02)",
        "issued_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }


def canonical_bytes(manifest: dict) -> bytes:
    return json.dumps(manifest, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode()


def identity_hash(manifest: dict) -> str:
    return hashlib.sha256(canonical_bytes(manifest)).hexdigest()


def issue_card(policy: SpendingPolicy | None = None,
               card_path: Path = CARD_PATH) -> dict:
    """Issue the identity card through policy + gate. Raises
    SigningRefused if either layer refuses."""
    policy = policy or SpendingPolicy()
    manifest = build_manifest()
    digest = identity_hash(manifest)
    req = SignRequest(
        candidate_id="AGENT-IDENTITY",
        action="sign-identity-card",
        target_contract=SIGNER_CONTRACT,
        payload_kind="evidence_hash",   # the only kind the gate ever signs
        payload=digest,
        gate_decision="allow",
        human_approved=True,
        note="identity issuance requested by serv/agent_identity.py")
    sig = policy.guarded_sign(req, SimulatedTestnetSigner())
    card = {
        "manifest": manifest,
        "identity_hash": digest,
        "signature": sig,
        "decision_log_ref": {
            "fingerprint": req.fingerprint(),
            "gate": "near/gated_signer.Gate via serv/spending_policy",
            "note": "find this fingerprint in the decision logs; its "
                    "verdict must be 'allow'",
        },
        "how_to_verify": "python3 serv/agent_identity.py --verify "
                         "serv/identity_card.json",
    }
    card_path.parent.mkdir(parents=True, exist_ok=True)
    card_path.write_text(json.dumps(card, indent=2, ensure_ascii=False)
                         + "\n", encoding="utf-8")
    return card


def verify_card(card_path: Path = CARD_PATH,
                extra_logs: list[Path] | None = None) -> tuple[bool, list[str]]:
    """Offline verification: (ok, human-readable check lines)."""
    lines: list[str] = []
    card = json.loads(card_path.read_text(encoding="utf-8"))
    recomputed = identity_hash(card["manifest"])
    hash_ok = recomputed == card["identity_hash"]
    lines.append(f"manifest hash recomputed: {recomputed[:16]}... "
                 f"({'MATCH' if hash_ok else 'MISMATCH'} vs card "
                 f"{card['identity_hash'][:16]}...)")

    fp = card["decision_log_ref"]["fingerprint"]
    log_paths = [HERE / "serv_decision_log.jsonl",
                 ROOT / "near" / "decision_log.jsonl"] + (extra_logs or [])
    found = None
    for lp in log_paths:
        if not lp.exists():
            continue
        for line in lp.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            e = json.loads(line)
            if e.get("fingerprint") == fp:
                found = (lp, e)
    if found:
        lp, e = found
        verdict_ok = e.get("verdict") == "allow"
        mark = "OK" if verdict_ok else "NOT ALLOW"
        lines.append(f"decision log entry found in {lp.name}: verdict="
                     f"{e.get('verdict')} ({mark}) — "
                     f"{e.get('reason', '')[:90]}")
    else:
        verdict_ok = False
        lines.append("decision log entry NOT found for fingerprint "
                     f"{fp} (searched {[str(p) for p in log_paths]})")
    sim = card["signature"].get("simulated")
    lines.append(f"signature backend: {card['signature'].get('backend')} "
                 f"(simulated={sim}) — process proof, not an on-chain "
                 "signature, until the testnet backend is provisioned")
    return (hash_ok and verdict_ok), lines


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--issue", action="store_true",
                    help="issue a fresh identity card")
    ap.add_argument("--verify", nargs="*", metavar="PATH",
                    help="verify a card: first path = card file, rest = "
                         "extra decision logs to search")
    args = ap.parse_args()
    if args.issue:
        card = issue_card()
        print(f"identity card issued -> {CARD_PATH}")
        print(f"identity_hash: {card['identity_hash']}")
        print(f"signature backend: {card['signature']['backend']} "
              f"(simulated={card['signature']['simulated']})")
    elif args.verify is not None:
        card_file = Path(args.verify[0]) if args.verify else CARD_PATH
        extras = [Path(p) for p in args.verify[1:]]
        ok, lines = verify_card(card_file, extras)
        for ln in lines:
            print(f"  {ln}")
        print(f"VERIFY: {'PASS' if ok else 'FAIL'}")
        raise SystemExit(0 if ok else 1)
    else:
        print("usage: agent_identity.py --issue | --verify [card] [logs...]")
