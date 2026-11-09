# Bountybot × SERV — SERV Hackathon Edition 02 (Track 02 · KITE)

*WRITE-UP FINAL — siap tempel ke formulir submisi
(https://openserv.typeform.com/submissions02). Fakta event: `SPEC.md`.
Status build: SELESAI 2026-11-09 (modul `serv/` + 12 tes offline lulus +
demo 4 adegan jalan). Satu-satunya yang belum: run demo dengan key asli
(langah pemilik — lihat `SUBMIT_CHECKLIST.md`).*

---

## Write-up (teks untuk formulir submisi — sesuaikan field formulir)

**Project:** Bountybot — an evidence-gated AI bounty-hunting agent,
extended for SERV Edition 02 with a **verifiable agent identity** and
**owner-controlled spending limits**, powered by **SERV Reasoning**.

**What it does.** Bug-bounty programs are being flooded with
AI-generated "slop" reports — plausible, unreproducible findings that
pay nothing and burn triage teams. Bountybot inverts the objective:
a candidate bug must survive five deterministic evidence gates
(frozen official scope → known-issues filter → skeptic kill-gates →
runnable-PoC requirement → human submission order) before it may
become a report. On its live target — the Plether audit competition
on Immunefi ($80k USDC, scope frozen at commit `a82d4fe`, 131 files)
— the pipeline killed 5 of 8 candidates and ranked 3 survivors as
hypotheses, claiming nothing it could not prove.

**What we built during this hackathon (the meaningful feature).**
Bountybot already refused to *sign* anything outside a policy gate.
For the KITE track we gave the agent the two things an agent needs
before it may act economically on someone's behalf — a new `serv/`
module in the same public repo:

1. **A verifiable identity** (`serv/agent_identity.py`). The agent
   issues an *identity card*: a canonical manifest (agent name,
   owner, public repo, payout address, the scope it is currently
   hunting), hashed with SHA-256 and signed — but the signature
   itself must pass the same policy gate, which only ever signs
   `evidence_hash` payloads through a function-call key scoped to a
   single method. Anyone can verify the card offline against the
   hash and the public decision log.
2. **Spending limits the owner controls** (`serv/spending_policy.py`).
   Every action the agent takes — each SERV Reasoning call, each
   signing request — is priced and checked against an owner-set
   policy *before* it runs: per-action cap, daily cap, category and
   recipient allowlists. Over budget → **block**. Near the limit →
   **warn** (a human decides). Inside policy → **allow**. Every
   verdict is appended to one audit log: real data, real decisions,
   auditable steps. Defaults sit far below the $5 free participant
   credit.

**How SERV Reasoning powers it.** The pipeline's triage step — the
judgment call of classifying candidate findings — runs through
**SERV Reasoning** (`serv/serv_reasoning_client.py`: OpenAI-compatible
API at `inference-api.openserv.ai/v1`, key from environment only,
system-prompt-defined triage policy, the catalog's smallest model at
low reasoning effort to stay inside the free participant credits).
By design the model only *annotates*; it can never promote or kill a
candidate. The deterministic gates own every verdict — so the agent's
reasoning is inspectable while its authority stays bounded by code.
If no key is present the client degrades to a deterministic local
classifier and labels itself `mode=local-fallback` — we do not fake
inference.

**The demo** (`python3 serv/run_demo.py`, logs in
`serv/demo_output/`). One run shows all of it: (1) the pipeline
triages a real competition scope via the SERV Reasoning client,
behind the spending policy; (2) the agent issues and verifies its
identity card; (3) a prompt-injection hidden in scanner output
orders the agent to sign a 10 NEAR transfer to an attacker —
**refused and logged**, because transfers are not a signable payload
kind and the recipient is not on the spending allowlist; (4) a
scripted spending spree hits the daily cap and the next action is
**blocked on budget grounds**, while a smaller in-policy action
still passes — an agent that can shop, book and pay *safely*,
because it provably cannot exceed the limits its owner set.
12 offline tests cover the caps, the warn threshold, the allowlist
refusals, the injection refusal, and card tamper detection.

**Why this matters (user readiness & revenue potential).** Every
autonomous agent that will ever hold a key or a budget needs exactly
this shape: identity you can verify, spending you can bound, and an
audit trail you can replay. Bountybot is the working instance —
today for bounty hunting, where the same wrapper is a sellable
triage service for programs drowning in slop reports.

**Honesty box.** The signing backend in this repo is testnet-shaped
and simulated (labelled as such in every output); no real funds move.
Costs shown are estimates from published token prices, used for
budgeting. Survivors of the pipeline are hypotheses, not bug
claims — nothing is submitted anywhere without a runnable proof of
concept and a human order. That restraint is the product.

**Reproduce (under 5 minutes, offline):**

```bash
python3 serv/run_demo.py                          # 4-scene demo
python3 -m unittest discover -s serv/tests -v     # 12 tests
python3 serv/agent_identity.py --verify serv/demo_output/identity_card.json \
        serv/demo_output/gate_decision_log.jsonl  # card verification
```

---

## Catatan status untuk tim (bukan bagian write-up)

- Modul selesai & teruji **tanpa** key (fallback berlabel jujur di
  semua artefak demo saat ini: `mode=local-fallback`).
- Agar syarat "SERV Reasoning must be part of your build" tampil
  maksimal di artefak demo, jalankan ulang `serv/run_demo.py` SEKALI
  dengan `OPENSERV_API_KEY` asli sebelum submit (konsumsi estimasi
  per run penuh: pecahan sen — 3 panggilan triase model terkecil).
- Langkah pemilik persis: `SUBMIT_CHECKLIST.md`.

---

## Hasil live SERV Reasoning (2026-11-09) — bukti anotasi asli

Pada 2026-11-09 (±19:00 WIB) tiga kandidat nyata Bountybot — **K-1**
dan **K-2** (Plether) serta **ND-1** (Granite, Stacks mainnet) —
dianotasi oleh lapisan **SERV Reasoning (GPT-6-Luna)** di endpoint
resmi OpenServ, masing-masing dua panel (Raw + SERV Reasoning).
Hasil lengkap, verbatim, dengan usage per panggilan:
`serv/demo_output/serv_live_annotations.json` dan
`serv/demo_output/serv_live_annotations.md`. Total biaya 6 panggilan:
**$0,0013** dari saldo kredit konsol $1,00. Keenam anotasi konsisten
dengan doktrin pipeline: SERV hanya *menganotasi* (ringkasan, bukti
pendukung, bukti yang akan membunuh kandidat, skor kejelasan) —
keputusan tetap milik gerbang deterministik dan PoC yang bisa
dijalankan.

**Disclosure transport (persis, jangan diparafrase):** panggilan ini
berjalan sebagai *SERV Reasoning (GPT-6-Luna) via OpenServ console
Playground — same /v1/chat/completions endpoint,
session-authenticated*. Bukan lewat Bearer API key (kolom "Last used"
key konsol tetap **Never**), bukan ditembakkan pipeline lokal, dan
temperature tidak disetel (reasoning effort Medium di Playground;
konfigurasi klien lokal memakai `low`). Nilai tambahnya tetap sah:
anotasi benar-benar dihasilkan lapisan SERV Reasoning di endpoint
resmi mereka, dan `serv/serv_reasoning_client.py` di repo ini memang
menargetkan endpoint yang sama (`/v1/chat/completions`, model
`gpt-6-luna`) untuk pemakaian programatik. Artefak demo offline di
`serv/demo_output/` tetap berlabel `mode=local-fallback` apa adanya —
file anotasi live ini adalah bukti terpisah, tidak me-relabel artefak
mana pun.
