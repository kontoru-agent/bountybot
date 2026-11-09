# Layer 4 — poc/

**Responsibility:** Proof or discard. One Foundry test per survivor, at the
frozen commit, in the repo's own test suite or on a local Anvil fork
(e.g. Arbitrum Sepolia for Plether). The test must demonstrate the claimed
impact; the exact command and full output are recorded.

**Input:** `survivors.jsonl`.
**Output:** `poc/<id>.t.sol` per survivor + run log; `poc_result: pass|fail`
written back into `survivors.jsonl`.

Rule: `fail` or "cannot write it" = finding discarded. No exceptions for
how convincing the prose sounds. Local/fork only — never live contracts.
Status: specified, awaiting a real survivor (DESIGN.md §5 item 4).
