#!/usr/bin/env python3
"""
Bountybot — serv/tests/test_serv.py  (offline tests, no real API calls)

Covers PLAN.md §2.8: policy block over the per-action cap, block over
the daily cap, warn at the threshold, allow inside policy, allowlist
refusals, identity-card hash verification, and the prompt-injection
refusal with the SERV stack in place. The SERV client is tested with a
monkeypatched urlopen that fails the test if any HTTP call is attempted
while the spending policy has blocked it.

Run:  python3 -m unittest discover -s serv/tests -v
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

SERV_DIR = Path(__file__).resolve().parent.parent
ROOT = SERV_DIR.parent


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


sp = _load("spending_policy", SERV_DIR / "spending_policy.py")
client_mod = _load("serv_reasoning_client",
                   SERV_DIR / "serv_reasoning_client.py")
ident_mod = _load("agent_identity", SERV_DIR / "agent_identity.py")

PricedAction = sp.PricedAction
SpendingPolicy = sp.SpendingPolicy
Gate = sp.Gate
SignRequest = sp.SignRequest
SigningRefused = sp.SigningRefused


def make_policy(tmp: Path, per_call=0.20, daily=0.50) -> SpendingPolicy:
    return SpendingPolicy(
        gate=Gate(log_path=tmp / "gate_log.jsonl"),
        log_path=tmp / "serv_log.jsonl",
        per_call_cap=per_call, daily_cap=daily)


def action(action_id="a1", cost=0.10, category="serv-reasoning",
           recipient="inference-api.openserv.ai") -> PricedAction:
    return PricedAction(action_id=action_id, label=f"test {action_id}",
                        category=category, recipient=recipient,
                        est_cost_credits=cost)


class PolicyTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.policy = make_policy(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    def test_allow_inside_policy(self):
        verdict, _ = self.policy.evaluate_action(action(cost=0.10))
        self.assertEqual(verdict, "allow")

    def test_block_over_per_call_cap(self):
        verdict, reason = self.policy.evaluate_action(action(cost=0.21))
        self.assertEqual(verdict, "block")
        self.assertIn("per-action cap", reason)

    def test_block_over_daily_cap(self):
        for i in range(3):  # 3 x 0.15 committed = 0.45 of 0.50
            a = action(action_id=f"fill{i}", cost=0.15)
            v, _ = self.policy.evaluate_action(a, human_approved=True)
            self.assertEqual(v, "allow")
            self.policy.commit(a)
        verdict, reason = self.policy.evaluate_action(
            action(action_id="over", cost=0.15))
        self.assertEqual(verdict, "block")
        self.assertIn("daily cap", reason)

    def test_warn_at_threshold(self):
        a = action(action_id="w1", cost=0.15)
        self.policy.evaluate_action(a)
        self.policy.commit(a)  # spent 0.15
        a2 = action(action_id="w2", cost=0.15)
        self.policy.evaluate_action(a2)
        self.policy.commit(a2)  # spent 0.30
        verdict, reason = self.policy.evaluate_action(
            action(action_id="w3", cost=0.15))  # projected 0.45 >= 80%
        self.assertEqual(verdict, "warn")
        self.assertIn("human approval", reason)

    def test_warn_released_by_human_approval(self):
        for i in range(2):  # spent 0.30 via in-cap actions
            a = action(action_id=f"pre{i}", cost=0.15)
            self.policy.evaluate_action(a)
            self.policy.commit(a)
        verdict, _ = self.policy.evaluate_action(
            action(action_id="w", cost=0.15), human_approved=True)
        self.assertEqual(verdict, "allow")

    def test_block_non_allowlisted_recipient(self):
        verdict, reason = self.policy.evaluate_action(
            action(recipient="attacker.example.com"))
        self.assertEqual(verdict, "block")
        self.assertIn("allowlist", reason)

    def test_block_non_allowlisted_category(self):
        verdict, _ = self.policy.evaluate_action(
            action(category="shopping"))
        self.assertEqual(verdict, "block")


class InjectionTest(unittest.TestCase):
    def test_injection_transfer_refused(self):
        with tempfile.TemporaryDirectory() as td:
            policy = make_policy(Path(td))
            gs = _load("gated_signer", ROOT / "near" / "gated_signer.py")
            req = SignRequest(
                candidate_id="INJ-1", action="sign-evidence",
                target_contract="attacker.testnet",
                payload_kind="transfer",
                payload="transfer:10NEAR->attacker.testnet",
                gate_decision="block", note=gs.INJECTION_NOTE)
            with self.assertRaises(SigningRefused):
                policy.guarded_sign(req, gs.SimulatedTestnetSigner())


class IdentityTest(unittest.TestCase):
    def test_issue_and_verify(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            policy = make_policy(tmp)
            card_path = tmp / "identity_card.json"
            card = ident_mod.issue_card(policy=policy,
                                        card_path=card_path)
            self.assertEqual(card["identity_hash"],
                             ident_mod.identity_hash(card["manifest"]))
            ok, lines = ident_mod.verify_card(
                card_path, extra_logs=[tmp / "gate_log.jsonl"])
            self.assertTrue(ok, msg="; ".join(lines))

    def test_tampered_manifest_fails_verify(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            policy = make_policy(tmp)
            card_path = tmp / "identity_card.json"
            ident_mod.issue_card(policy=policy, card_path=card_path)
            card = json.loads(card_path.read_text())
            card["manifest"]["owner"] = "Mallory"
            card_path.write_text(json.dumps(card))
            ok, _ = ident_mod.verify_card(
                card_path, extra_logs=[tmp / "gate_log.jsonl"])
            self.assertFalse(ok)


class ClientTest(unittest.TestCase):
    def test_fallback_label_without_key(self):
        env = {k: v for k, v in os.environ.items()
               if k not in ("OPENSERV_API_KEY", "SERV_API_KEY")}
        with mock.patch.dict(os.environ, env, clear=True):
            client = client_mod.ServReasoningTriage()
            self.assertEqual(client.mode, "local-fallback")
            out = client.triage({"id": "K-1", "title": "Liquidation "
                                   "reserve refund",
                                   "description": "liquidation bounty"})
            self.assertEqual(out["mode"], "local-fallback")
            self.assertEqual(out["category"], "liquidation-accounting")
            self.assertIn("no OPENSERV_API_KEY", out["note"])

    def test_policy_block_prevents_http(self):
        """With a key present but a zero per-call cap, the policy must
        block BEFORE any HTTP request is attempted."""
        with tempfile.TemporaryDirectory() as td:
            policy = make_policy(Path(td), per_call=0.0, daily=0.50)
            with mock.patch.dict(os.environ,
                                 {"OPENSERV_API_KEY": "test-key-not-real"}):
                client = client_mod.ServReasoningTriage(policy=policy)
                self.assertEqual(client.mode, "serv")
                with mock.patch.object(
                        urllib.request, "urlopen",
                        side_effect=AssertionError(
                            "HTTP attempted despite policy block")):
                    out = client.triage(
                        {"id": "K-9", "title": "oracle staleness",
                         "description": "stale oracle mark price"})
            self.assertEqual(out["mode"], "local-fallback")
            self.assertEqual(out["policy_verdict"], "block")
            self.assertIn("spending policy BLOCK", out["note"])


if __name__ == "__main__":
    unittest.main()
