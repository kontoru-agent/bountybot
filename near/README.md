# NEAR integration — near/

Two pieces, matching the official **AI Security & Defense** track prompt
point-for-point: (1) a service that classifies what an agent is about to act
on and returns **allow / warn / block + reason**; (2) a wrapper around the
agent's signing ability that **refuses to sign on block, asks the human on
warn**, with the agent holding a **scoped function-call key** instead of the
keys to everything; (3) a **prompt-injection attack demo** the wrapper stops.

## 1. `ai_cloud_client.py` — private triage on NEAR AI Cloud

Pre-disclosure target code is secret. Pasting it into a public inference
endpoint would leak the very bugs being hunted, so candidate triage runs on
**NEAR AI Cloud**: OpenAI-compatible inference inside TEEs — private and
verifiable.

Router pattern (model/endpoint are config, not code):

| Setting | Source | Default |
|---|---|---|
| `NEARAI_BASE_URL` | env → `config.json` | `https://cloud-api.near.ai/v1` |
| `NEARAI_MODEL` | env → `config.json` | `zai-org/GLM-5.1-FP8` |
| `NEARAI_API_KEY` | **env only** | — (never a file, never logged) |

With no key set, the client degrades to a deterministic local keyword
classifier and labels its output `local-fallback`. The pipeline runs
end-to-end offline today; adding a key upgrades the same call sites to TEE
inference with no code change. Either way the model only **annotates**
(category + rationale) — verdicts belong to the deterministic gates in
`../skeptic/`, because an LLM agreeing with itself is not evidence.

## 2. `gated_signer.py` — policy wrapper over Chain Signatures (testnet)

The agent's "hand" is NEAR **Chain Signatures**: an EVM address derived from
its NEAR account (`deriveAddressAndPublicKey(accountId, "bountybot-arbitrum-1")`),
signatures produced by the MPC contract — testnet `v1.signer-prod.testnet`,
mainnet `v1.signer`. The agent would call it with a **function-call access
key scoped to the single method `sign` on that single contract**, with a
limited gas allowance (see `config.json → chain_signatures.function_call_key`):
such a key cannot transfer NEAR, cannot add or remove keys, and locks itself
out when the allowance is spent — the leash is structural, not a promise.

In front of that hand sits the policy gate (`Gate.evaluate`), which is fully
implemented here and backend-independent:

- **block** → signing is refused, always (killed candidates, non-signable
  payload kinds; the only signable kind is `evidence_hash` — this wrapper
  will never sign a value transfer).
- **warn** → held until an explicit human approval is on record.
- **allow** → possible only after a passing PoC *and* the human order.
- Free-form text attached to a request (scanner output, LLM notes — the
  natural home of a prompt injection) is treated as **data** and is never
  read by the gate. Verdicts come from structured fields only.
- Every evaluation is appended to `decision_log.jsonl` — timestamp, request
  fingerprint, verdict, reason.

Backends: `SimulatedTestnetSigner` (deterministic, clearly-labelled
stand-in used by the offline demo) and `ChainSignaturesTestnetSigner`
(documented step-for-step, raises until provisioned with
`NEAR_TESTNET_ACCOUNT_ID` + `NEAR_FUNCTION_CALL_KEY` env placeholders and a
chainsig.js / near-api-js bridge — real keys are never committed).

Run it: `python3 near/gated_signer.py --demo` — three scenarios: a
prompt-injection attack (blocked), a warn hold, and an allowed evidence
signature. Real output: `../demo_output/near_demo.log`.
