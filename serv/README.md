# Bountybot × SERV — `serv/` module (SERV Hackathon Edition 02, Track 02 · KITE)

Built during SERV Hackathon Edition 02 on top of the existing Bountybot
repo (no pipeline behaviour changed; `pipeline.py` is untouched). Track
02 · KITE asks for *"agents with a verifiable identity and spending
limits you control"*, powered by SERV Reasoning. This module is exactly
that, wrapped around Bountybot's existing policy gate.

## What was built

| File | What it does |
|---|---|
| `config.json` | Non-secret config: SERV base URL, model (`gpt-6-luna` — cheapest in the SERV catalog, per official Day One guidance), token prices for cost estimation, budget caps (defaults far below the $5 free participant credit), spending allowlists, identity fields. |
| `serv_reasoning_client.py` | SERV Reasoning triage client. Same router pattern as `near/ai_cloud_client.py`: OpenAI-compatible `POST /v1/chat/completions` at `inference-api.openserv.ai/v1`, mandatory system prompt fixing the triage policy, API key from env only (`OPENSERV_API_KEY`, or `SERV_API_KEY` as named in the official docs). The model only **annotates**; deterministic gates own every verdict. No key / any error → deterministic local classifier, labelled `mode=local-fallback`. Every call is priced and authorised by the spending policy **before** it is made. |
| `spending_policy.py` | The spending fence. Wraps `near/gated_signer.Gate` and adds: per-action cap, daily cap, warn threshold (≥80% of daily → held for a human), category + recipient allowlists. Verdicts combine with the sign gate, most restrictive wins. Every decision and every committed execution is appended to one audit log, `serv_decision_log.jsonl` — auditable steps, replayable by anyone. |
| `agent_identity.py` | Verifiable identity card. Canonical manifest (agent, owner, public repo, payout address, current hunting scope + frozen commit) → `sha256` → signature requested **only** through the policy + gate (the gate signs `evidence_hash` payloads only, via a function-call key scoped to one method). Emits `identity_card.json`. Anyone can verify offline: recompute the hash, find the decision-log fingerprint, confirm verdict `allow`. |
| `run_demo.py` | The demo. Four scenes in one run: (1) pipeline triage via the SERV client behind the policy, (2) identity card issue + live verification, (3) the prompt-injection replay — an untrusted note ordering a 10 NEAR transfer is **refused and logged**, (4) a spending spree that hits the daily cap and gets **blocked**, while a smaller in-policy action still passes. Logs land in `serv/demo_output/`. |
| `pipeline_serv.py` | Pipeline variant (scope → scan → skeptic → SERV annotation). The NEAR-default `pipeline.py` is unchanged. |
| `tests/test_serv.py` | 12 offline tests: per-action and daily cap blocks, warn threshold + human release, allowlist refusals, injection refusal, identity issue/verify + tamper detection, fallback labelling, and "policy block prevents any HTTP call" (urlopen is rigged to fail the test if attempted). |

## Run it

```bash
# offline demo (no key needed — fallback is labelled, never faked)
python3 serv/run_demo.py

# tests
python3 -m unittest discover -s serv/tests -v

# identity card
python3 serv/agent_identity.py --issue
python3 serv/agent_identity.py --verify serv/identity_card.json

# pipeline with SERV annotation
python3 serv/pipeline_serv.py
```

With a real key, the same call sites upgrade to live SERV Reasoning —
no code changes:

```bash
export OPENSERV_API_KEY=...   # from console.openserv.ai; env only
python3 serv/run_demo.py      # triage scenes now report mode=serv
```

## Honesty boundaries

- The signer backend in this repo is the **simulated testnet stand-in**,
  labelled SIMULATED in every output; no real funds move, and the card
  proves the issuance *process* (through the gate), not an on-chain
  signature, until the testnet backend is provisioned.
- Costs are **estimates** from published per-token prices, used for
  budgeting by the policy — not billing records.
- Fallback is a feature, not a fudge: any output produced without a key
  says `mode=local-fallback` in the artefact itself.
- The identity-card fields map onto **Kite Agent Passport** concepts
  (agent identity bound to an owner, spending rules attached to the
  identity, verifiable record). Registering a Passport via the `kpass`
  CLI (passkey-approved sessions) is an owner step — see the submission
  checklist maintained with the hackathon package; no Passport
  registration is claimed here.
