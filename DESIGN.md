# Bountybot v1 — Design

## 1. Architecture

```
official program page (Immunefi)
        │  scope.json (frozen: program, commit, in-scope paths, exclusions)
        ▼
┌─────────────┐   candidates.jsonl   ┌─────────────┐   survivors.jsonl
│ 2. scan/    │ ───────────────────► │ 3. skeptic/ │ ──────────────────┐
│ Slither +   │                      │ disprove,   │                   ▼
│ patterns    │                      │ dup-check   │            ┌─────────────┐
└─────────────┘                      └─────────────┘            │ 4. poc/     │
        ▲                                  ▲                    │ Foundry PoC │
        │ known_issues.txt                 │ known-issues gate  │ run log     │
┌─────────────┐                            │ (scope tool)       └──────┬──────┘
│ 1. scope/   │ ───────────────────────────┘                          │ passed only
└─────────────┘                                                       ▼
                                                               ┌─────────────┐
                                                               │ 5. report/  │
                                                               │ draft only  │
                                                               └─────────────┘
                                                  submission = human order, per report
```

Principles: deterministic tools before LLMs; every layer can kill a finding;
no layer can promote a finding past a later gate; all artefacts are files on
disk (auditable, resumable, diff-able).

## 2. Modules

| Module | Responsibility | Key tools |
|---|---|---|
| `scope/` | Fetch official scope, freeze commit, load known issues / prior audits / accepted-risk; provide the duplicate gate | `check_known_issues.py` (done), git |
| `scan/` | Generate candidates: Slither detectors + a short manual-pattern checklist (access control, oracle/staleness, rounding/accounting, reentrancy, liquidation math) | Slither, Foundry build |
| `skeptic/` | For each candidate: state the strongest "this is not a bug" argument; check reachability, trusted-role assumptions, known-issue overlap; verdict `kill` / `survive` with reasons | `check_known_issues.py` output + manual/LLM review notes |
| `poc/` | One Foundry test per survivor at the frozen commit; must fail-safe (show impact) to pass; record exact command + output | Foundry (`forge test`), local Anvil fork |
| `report/` | Render survivors into Immunefi format with the full evidence trail attached; hold in `drafts/` until a human orders submission | template in `report/README.md` |

## 3. Data contracts between layers

All JSON/JSONL, UTF-8, paths relative to the frozen target checkout.

`scope.json`
```json
{"program": "plether-audit-competition", "platform": "immunefi",
 "repo": "<official repo url>", "commit": "a82d4fe",
 "in_scope": ["packages/perps/src"], "exclusions": ["view-only contracts x6"],
 "known_issues_source": "<official url>", "frozen_at": "<ISO-8601>"}
```

`candidates.jsonl` — one candidate per line:
```json
{"id": "C-001", "title": "...", "contract": "Foo.sol", "function": "bar()",
 "pattern": "access-control|oracle|rounding|reentrancy|accounting|other",
 "tool_evidence": "slither detector / manual note", "description": "..."}
```

`survivors.jsonl` — candidate fields plus:
```json
{"skeptic_verdict": "survive", "skeptic_notes": "...",
 "known_issue_max_score": 0.12, "poc_path": "poc/C-001.t.sol",
 "poc_command": "forge test --match-test test_C001", "poc_result": "pass"}
```

`report draft` — Markdown, Immunefi sections (Title, Severity + impact in
scope wording, Description, PoC, Recommended fix) + an Evidence Trail appendix
(scope commit, skeptic notes, PoC run log). See `report/README.md`.

## 4. NEAR integration — concrete plan (Chain Signatures)

> **Implementation status (2026-11-09):** the NEAR layer is now code, in
> `near/` — an AI Cloud triage client (env-key, config-swappable model,
> labelled local fallback) and a gated-signing policy wrapper whose
> allow/warn/block gate, decision log, and prompt-injection demo run today
> against a simulated testnet backend. The plan below remains the design
> record for the real Chain Signatures backend (testnet provisioning is
> the only step left, and it needs env keys that are never committed).

Goal for the hackathon story (AI Security & Defense): give Bountybot a
**verifiable, leash-able agent identity** without giving it funds or keys.

1. **Identity:** a NEAR testnet account `bountybot.<owner>.testnet` is the
   agent's public identity; its account ID is embedded in every report draft's
   Evidence Trail.
2. **Signing evidence, not transactions:** via NEAR Chain Signatures (MPC
   contract on testnet), the agent derives an EVM address and signs the
   *hash of its PoC run log + scope.json*. The signature + derived address go
   into the draft — a judge/triager can verify the evidence trail was produced
   by that agent identity and has not been altered. No mainnet, no value.
3. **Leash:** the derived EVM address holds nothing and is allow-listed
   nowhere; if a future version ever submits via API, the human order is a
   signed message from the owner's NEAR account, checked before submission —
   "spending limit" pattern applied to *submissions* (max N drafts/day,
   human signature required per release).
4. **Fallback if MPC testnet is flaky at demo time:** sign the same hash with
   the NEAR account's own key (ed25519) and record that instead; the evidence
   format does not change, only the `signature_scheme` field.

Explicitly out of scope for v1: NEAR Intents, mainnet anything, holding or
moving funds, automated submission.

## 5. Still needed for an end-to-end demo before 14 Nov (priority order)

1. **Public GitHub repo + demo post on X (video/screenshots)** — hard NEAR
   submission requirements: repo public by 14 Nov 23:59 UTC and both links
   submitted. Needs the user's go-ahead to publish (scaffold is local-only until then).
2. **Freeze the real Plether target:** clone the official repo at `a82d4fe`,
   write the real `scope.json`, and load the verbatim known-issues list.
3. **Scan run that produces real candidates:** Slither + Foundry build on
   `packages/perps/src`, output committed as a sample `candidates.jsonl`.
4. **One survivor carried all the way:** skeptic notes + a runnable Foundry
   PoC (pass or an honest "all candidates killed" run — a clean zero is also
   a valid demo of the gates working).
5. **NEAR testnet identity + one evidence signature** per §4 (Chain
   Signatures, with the ed25519 fallback if needed).
6. **Report draft rendered from a real survivor** (or the worked example) in
   Immunefi format with the Evidence Trail appendix.
7. **Demo script / 2-minute walkthrough** that runs: scope gate → scan →
   skeptic kill of the known-issue duplicate → PoC → draft, live.
8. **README final pass:** screenshots/GIF of the run in §7 and the exact
   submission form fields filled in a checklist file.
