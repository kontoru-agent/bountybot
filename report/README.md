# Layer 5 — report/

**Responsibility:** Render PoC-passed survivors into an Immunefi-format draft
and *stop there*. Submission happens only on the user's explicit order, per
report — Bountybot never submits autonomously.

**Input:** `survivors.jsonl` with `poc_result: pass`.
**Output:** `drafts/<id>.md`, sections: Title · Severity (using the program's
in-scope impact wording) · Description · Proof of Concept (test + run log) ·
Recommended fix · **Evidence Trail appendix** (scope.json commit, scan
evidence, skeptic notes, PoC command/output, NEAR evidence signature when
available — see `../DESIGN.md` §4).

Status: template specified; no draft exists yet, and none may be submitted
without a human order.
