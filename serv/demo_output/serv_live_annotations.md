# SERV Reasoning — Live Annotations (2026-11-09)

*Companion to `serv_live_annotations.json` (same content, human-readable).
Generated for the SERV Hackathon Edition 02 submission (Track 02 · KITE).*

**Transport (exact, do not paraphrase):** SERV Reasoning (GPT-6-Luna) via
OpenServ console Playground — same `/v1/chat/completions` endpoint,
session-authenticated.

**Executed:** 2026-11-09, approx. 19:00 WIB · **Model:** `gpt-6-luna` ·
**Endpoint:** `https://inference-api.openserv.ai/v1/chat/completions` ·
**Calls:** 6 (Raw panel + SERV Reasoning panel × 3 candidates) ·
**Total cost:** **$0.0013** of the $1.00 console credit grant.

## Transport disclosure (honesty box)

- These calls ran from the OpenServ **console Playground** under the
  signed-in console session. They were **not** made with a Bearer API
  key — the console API key's "Last used" field still reads **Never** —
  and no local program (`pipeline.py`, `pipeline_serv.py`,
  `serv_reasoning_client.py`) fired them.
- Temperature was **not set** (Playground default); reasoning effort was
  **Medium** (the local client's `serv/config.json` uses `low` for
  programmatic runs).
- The annotations below were genuinely produced by the SERV Reasoning
  layer on OpenServ's official endpoint, and
  `serv/serv_reasoning_client.py` in this repo targets that same
  endpoint for programmatic use.
- The Playground panels return an annotation schema (*summary /
  supporting evidence / killing evidence / clarity*), not the
  category+rationale schema the local client parses. Both panels'
  outputs are recorded verbatim.
- The offline demo artifacts in this folder (`demo_run.log`,
  `summary.json`, `triage_report.md`) remain labelled
  `mode=local-fallback`. This file is separate live evidence; neither
  relabels the other.
- Annotations annotate only: the deterministic gates own every verdict.
  Each candidate stands or falls on its own runnable PoC.

**System prompt** (verbatim from `serv/serv_reasoning_client.py`):

> You are the triage classifier inside Bountybot, an evidence-gated bug
> bounty agent. Classify the candidate finding into exactly one category
> from: liquidation-accounting, tranche-accounting, queue-liveness,
> oracle-staleness, access-control, rounding-accounting, other. Reply
> with ONLY a JSON object: {"category": "...", "rationale": "one
> sentence"}. You are annotating, not judging: never claim the candidate
> is or is not a real bug.

---

## K-1 — Plether (MarginClearinghouse.sol:1279)

**User message sent:** "Liquidation-reserve remainder is refunded to a
defaulting trader when a SHORT price loss is written off" — on
liquidation the charge shrinks to minBounty while the price loss is
written off against LPs, yet the settlement plan always unlocks the
reserve remainder (reserve − minBounty) back to the liquidated account
as withdrawable settlement, with no condition that write-off == 0.

### Raw panel — $0.0001 (169 in / 195 out / 58 reasoning)

- **Summary:** Candidate K-1 alleges that, after a short trader's loss
  is written off to LPs, the remaining liquidation reserve (75 − 25 =
  50) is refunded to the defaulting trader; the PoC reports a 55,000
  LP-absorbed loss and a 50 withdrawal.
- **Supporting evidence:**
  - The stated reserve and minimum-bounty amounts leave 50.
  - The reported PoC says LPs absorbed the 55,000 loss while the
    defaulter withdrew 50.
  - The candidate identifies MarginClearinghouse.sol:1279 as the
    relevant location.
- **Killing evidence:**
  - Code or execution evidence showing the reserve remainder is not
    credited or paid to the defaulting trader.
  - Evidence that the 50 withdrawal came from another balance or was
    unavailable to a defaulting trader after the write-off.
  - A reproduced PoC showing the reported loss allocation or
    withdrawal does not occur.
- **Clarity:** 3

### SERV Reasoning panel — $0.0003 (402 in / 149 out / 186 reasoning)

- **Summary:** The finding alleges that after LPs absorb a short
  trader's loss, the remaining liquidation reserve is returned to the
  defaulting trader.
- **Supporting evidence:**
  - The candidate cites MarginClearinghouse.sol:1279.
  - The PoC reports a 55,000 loss absorbed by LPs and a 50-unit
    withdrawal from a reserve of 75 with a 25-unit minimum bounty.
  - The candidate reports the deterministic gate as SURVIVOR.
- **Potentially disconfirming evidence:**
  - Code or accounting showing the 50-unit remainder is not refunded
    to the defaulting trader.
  - Evidence that the PoC's loss allocation, reserve balance, or
    withdrawal attribution is incorrect.
- **Clarity:** 4

---

## K-2 — Plether (HousePool waterfall)

**User message sent:** "Second recapitalisation after a high-water-mark
reset is misrouted to unassignedAssets instead of restoring senior
principal" — after a wipeout, a first small recap resets the HWM via
the bootstrap branch; the else branch's gap (HWM − seniorPrincipal) is
then 0, so a second recap is routed entirely to unassignedAssets and
stops restoring senior principal (and unassignedAssets > 0 blocks all
tranche deposits until the owner assigns it manually).

### Raw panel — $0.0001 (159 in / 119 out / 80 reasoning)

- **Summary:** Candidate K-2 alleges that, after a wipeout resets the
  high-water mark from 50000 to a 10000 recap, a second 10000 recap is
  left in unassignedAssets instead of increasing seniorPrincipal.
- **Supporting evidence:**
  - PoC reportedly passes.
  - Deterministic gate reports SURVIVOR.
- **Killing evidence:**
  - Execution traces showing the second recap correctly increases
    seniorPrincipal.
  - Accounting or state-transition evidence showing the 10000
    unassignedAssets balance is intentional and not misrouted.
- **Clarity:** 4

### SERV Reasoning panel — $0.0002 (392 in / 121 out / 143 reasoning)

- **Summary:** The finding alleges that after a wipeout and two 10,000
  recaps, the second recap is misrouted: seniorPrincipal remains
  10,000 while unassignedAssets also becomes 10,000.
- **Supporting evidence:**
  - The reported post-recap state matches the alleged accounting
    mismatch.
  - The provided proof of concept passes.
- **Killing evidence:**
  - A reproduction showing the second recap is correctly allocated
    under the intended waterfall rules.
  - Evidence that the reported state is expected or results from an
    invalid test setup or assertion.
- **Clarity:** 4

---

## ND-1 — Granite, Stacks mainnet (borrower-v1, aeUSDC market)

**User message sent:** "Granite: borrow mints 0 debt shares
(permissionless drain)" — a repay/liquidation principal-delta asymmetry
can drive a market to open-interest > 0 while total-debt-shares == 0,
so every borrow mints exactly 0 debt shares; a PoC on pre-fix code
identical in shape to the live borrower-v1 extracted 19,999,946,719
market units with 0 debt shares, repay errors in that state, and the
drain is repeatable. *(Input assembled in the same client format from
`nday/ND1_VERDICT.md`; ND-1 is not part of the frozen Plether
survivors file.)*

### Raw panel — $0.0002 (169 in / 143 out / 141 reasoning)

- **Summary:** Claim: repay/liquidation principal-delta asymmetry can
  leave positive market open interest with zero total debt shares,
  enabling further borrowing without minted debt shares and causing
  repay failures.
- **Supporting evidence:**
  - Reported PoC extracted about 20 billion market units with zero
    debt shares; subsequent repay errors.
  - Reported deterministic-gate result: SURVIVOR.
- **Killing evidence:**
  - A reproduction on the live Granite Stacks borrower-v1
    configuration showing the state cannot be reached, or that
    borrowing cannot proceed when total debt shares are zero.
  - Code or tests demonstrating that repay/liquidation accounting
    preserves the debt-share invariant and prevents zero-share
    borrowing.
- **Clarity:** 4

### SERV Reasoning panel — $0.0003 (402 in / 171 out / 136 reasoning)

- **Summary:** Candidate ND-1 describes a repay/liquidation
  principal-delta asymmetry that may leave open interest positive
  after debt shares reach zero, allowing subsequent borrows to mint
  zero debt shares.
- **Supporting evidence:**
  - The reported PoC extracted about 20 billion market units with
    zero debt shares.
  - The reported market state had open interest greater than zero and
    total debt shares equal to zero.
  - Repay reportedly errors in that state.
  - The deterministic gate is reported as SURVIVOR.
- **Evidence that would kill:**
  - A trace showing the reported state cannot be reached through the
    repay or liquidation paths.
  - Evidence that a zero-share borrow is rejected or still records
    debt shares or an equivalent enforceable obligation.
  - A reproducible test showing the reported extraction or resulting
    state is invalid.
- **Clarity:** 4

---

## Totals

| Panel | Calls | Input tok | Output tok | Reasoning tok | Cost |
|---|---|---|---|---|---|
| Raw | 3 | 497 | 457 | 279 | $0.0004 |
| SERV Reasoning | 3 | 1,196 | 441 | 465 | $0.0009 |
| **Total** | **6** | **1,693** | **898** | **744** | **$0.0013** |

Charged against the $1.00 console credit grant. No further API calls
are needed for the submission.
