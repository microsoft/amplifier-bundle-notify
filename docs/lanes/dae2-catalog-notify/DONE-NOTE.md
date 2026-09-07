# dae2 — delegate-catalog SOURCES sweep, amplifier-bundle-notify

**Work item:** `model_performance-2drn` (per-repo child of `model_performance-dae2`,
filed because the container item was held by a sibling lane — the recovery pattern
established by `model_performance-k75p`).

**Landing stage:** DRAFT PR. Nothing merged. The merge is the manager's next stage.

**Spend:** $0.00 of $0.00 authority. Text edits, local test runs, byte counts, and the
validate-agents recipe's own deterministic (non-LLM) phases. No API measurement, no
provider call, no `amplifier` invocation on the host.

---

## 1. Census — this repo ships exactly ONE agent

| file | is an agent? | why |
|---|---|---|
| `agents/notify-expert.md` | yes | declares a top-level `meta:` key (the loader's own contract) |
| `behaviors/desktop-notifications.yaml` | no | `bundle.description`, not an agent description — never enters the delegate catalog |
| `behaviors/push-notifications.yaml` | no | same |

`validate-agents` v1.8.0 discovery agrees, on both sides of the change:
**`agents discovered: 1`**, `location_counts {'agents/': 1}`, `candidates_scanned 1`,
`non_agent_count 0`.

**Baseline correction.** The census figure carried into this lane was **~1,852 chars**.
Measured against **CURRENT `origin/main` @ `01ea1f1`**, the parsed `meta.description`
scalar is **1,825 chars**. The lane's own number is used throughout; the inherited one
had drifted, exactly as a sibling lane warned.

---

## 2. Before / after

| agent | before | after | delta | % |
|---|---:|---:|---:|---:|
| `notify-expert` | 1,825 | **594** | −1,231 | −67.5% |
| **REPO TOTAL** | **1,825** | **594** | **−1,231** | **−67.5%** |

Counts are of the **parsed YAML scalar** — what the delegate catalog actually receives,
not the raw indented block.

Compliance, after:

| gate | result |
|---|---|
| trigger-first (opens `USE WHEN`) | yes |
| ≤ ~600 chars | yes — 594 |
| explicit `USE WHEN` | yes |
| explicit `DO NOT USE WHEN` | yes |
| `<example>` blocks | 0 (stock: 2) |
| `<commentary>` blocks | 0 (stock: 2) |

---

## 3. FIDELITY TABLE — `notify-expert`

Every fact in the stock description, and where it lives now. **Nothing was lost; nothing
needed restoring.**

| # | fact present in STOCK | present in LEAN? | where |
|---|---|---|---|
| 1 | authoritative/owner of Amplifier's notification system | yes | "Owns the notify bundle end to end" |
| 2 | scope = desktop/terminal alerts, mobile push, and the events that drive them | yes | "terminal bell vs desktop vs mobile push"; "picking which events to hook" |
| 3 | covers configuration, troubleshooting **and** extension, end to end | yes | "config, troubleshooting, extension" |
| 4 | trigger: notifications aren't firing or are misfiring | yes | "alerts not firing or misfiring" |
| 5 | trigger: choosing between terminal bell / desktop / mobile push | yes | verbatim in the USE WHEN list |
| 6 | trigger: adding a webhook or Slack/Teams handler | yes | verbatim |
| 7 | trigger: deciding which Amplifier events to hook | yes | "picking which events to hook" |
| 8 | trigger: platform-specific issues (WSL, macOS, Linux, SSH) | yes | "platform-specific breakage on WSL, macOS, Linux or SSH" |
| 9 | authoritative-on: `hooks-notify` | yes | named |
| 10 | authoritative-on: `hooks-notify-push` | yes | named |
| 11 | authoritative-on: ntfy.sh | yes | named |
| 12 | authoritative-on: terminal bell | yes | "terminal bell vs desktop vs mobile push" |
| 13 | authoritative-on: `notify:turn-complete` | yes | named |
| 14 | authoritative-on: `suppress_if_focused` | yes | named |
| 15 | authoritative-on: `AMPLIFIER_NOTIFY` | yes | named |
| 16 | authoritative-on: `AMPLIFIER_NTFY_TOPIC` | yes | named |
| 17 | authoritative-on: WSL notifications | yes | "platform-specific breakage on WSL…" |
| 18 | authoritative-on: `goal_final` | yes | named |
| 19 | authoritative-on: `orchestrator:complete` | yes | named |
| 20 | authoritative-on: desktop notifications | yes | named |
| 21 | authoritative-on: mobile push notifications | yes | named |
| 22 | authoritative-on: notification troubleshooting | yes | "troubleshooting" |

**Facts present in STOCK and ABSENT from LEAN: none.** Nothing restored; byte delta from
restoration **0**.

### The two `<example>` blocks

Both were delegation illustrations, not new facts. Their substantive content was already
covered twice over — once by a USE WHEN trigger above, and once in the **agent body**,
which is unchanged:

| example | its factual content | already covered by |
|---|---|---|
| WSL desktop notifications stopped working → "WSL's PowerShell toast path" | WSL toast mechanism | trigger #8 above, **and** body line: *"Platform-specific notification mechanisms (macOS `osascript`, Linux `notify-send`, Windows/WSL PowerShell toast)"* |
| phone alert over SSH → ntfy.sh + `AMPLIFIER_NTFY_TOPIC` | mobile push config | triggers #5/#16 above, **and** body line: *"The `hooks-notify-push` module for mobile push via ntfy.sh (`AMPLIFIER_NTFY_TOPIC`)"* |

Because the body already carried both, **no text had to move into the body** — which is
what let the body stay byte-identical (§4). The examples were pure pay-per-turn
duplication of pay-per-use content.

### The one thing added

`DO NOT USE WHEN the subject is the Amplifier CLI itself, or a non-notification module or
hook.` Stock had **no** exclusion clause at all; the standard requires one. It is a
scoping addition, not a change to any stock claim, and both exclusions are real: CLI
questions belong to `app-cli:cli-expert`, and non-notification module authoring belongs
to the `creating-amplifier-modules` skill.

---

## 4. Body byte-identity

Only the frontmatter `description` changed. Everything after the closing `---`:

```
stock body : 2356 chars  md5 ab7abb228780435b87ab347e5687014b
lean  body : 2356 chars  md5 ab7abb228780435b87ab347e5687014b
IDENTICAL  : True
```

Other frontmatter keys unchanged: `meta.name: notify-expert`, `model_role: general`.

Whole file: `4363 chars / md5 5a6bba0dab8f5700cdb2db555d2d1f61` →
`3060 chars / md5 e1de65b6673a79479dcf02e4341967a3`.

---

## 5. validate-agents

Recipe: `foundation:recipes/validate-agents.yaml` **v1.8.0**. Run at **$0** — its phases
0–3 (`environment-check`, `agent-discovery`, `structural-validation`,
`quality-classification`) are pure bash/python heredocs with no LLM step. The runner
(`run_validate_phases.py`, this directory) executes those steps **verbatim out of the
recipe YAML**, so it cannot diverge from the recipe. The LLM phases (4–6) were not run;
they cost money and this lane has $0. Phase 6's own **Verdict Selection** mapping is
quoted and applied to the deterministic `quality_level`.

```
===== BEFORE (stock, origin/main 01ea1f1) =====
agents discovered: 1        location_counts: {'agents/': 1}
structural summary: {'total': 1, 'passed': 0, 'errors': 3, 'warnings': 1}
quality_level: critical
  notify-expert  chars=1825  examples=2  commentary=2
                 errors=['DESCRIPTION_EXCESSIVE','COMMENTARY_TAG_PRESENT','EXAMPLE_BLOCK_PRESENT']
                 warnings=['NO_TOOLS_SECTION']

===== AFTER (branch lane/dae2-catalog-notify) =====
agents discovered: 1        location_counts: {'agents/': 1}
structural summary: {'total': 1, 'passed': 1, 'errors': 0, 'warnings': 1}
quality_level: needs_work
  notify-expert  chars= 594  examples=0  commentary=0
                 errors=[]  warnings=['NO_TOOLS_SECTION']
```

Verdict mapping, quoted from the recipe: `good → PASS · polish → PASS WITH SUGGESTIONS ·
needs_work → PASS WITH WARNINGS · critical → FAIL`.

- **BEFORE: `critical` → ❌ FAIL** (3 structural errors)
- **AFTER: `needs_work` → ⚠️ PASS WITH WARNINGS** (0 structural errors)

**Honest reading: this is not "PASS held", it is FAIL → PASS WITH WARNINGS.** Stock was
never PASS — it carried three structural ERRORs, all of which this change clears.

The single remaining warning, `NO_TOOLS_SECTION`, is **byte-identical to stock**. It is
out of scope here: adding a `tools:` key changes what the agent can actually do at
runtime, which a description-only sweep must not do. Left as found, named as such.

---

## 6. Tests and CI

All three CI jobs run locally on the branch:

| CI job | command | result |
|---|---|---|
| Lint | `uvx ruff@0.16.6 check --isolated --select E4,E7,E9,F .` | **All checks passed!** |
| Tests — hooks-notify | `uv run --no-sync pytest tests/ -q` | **11 passed** |
| Tests — hooks-notify-push | `uv run --no-sync pytest tests/ -q` | **4 passed** |
| Bundle structure (YAML) | the workflow's inline PyYAML check | **3 YAML documents parsed. Bundle structure OK.** |

The repo **does** have CI: `.github/workflows/ci.yml`, added on `main` @ `01ea1f1` after
this lane's branch point. The branch was fast-forwarded onto `01ea1f1` before any edit,
so the PR runs against it. Live CI state is on the PR.

---

## 7. Deliverable roll-up

| deliverable | state |
|---|---|
| targeted agent description trigger-first, ≤~600, USE WHEN / DO NOT USE WHEN, zero example/commentary | **DONE** |
| fidelity table per agent | **DONE** — 22 facts, 0 lost, 0 restored |
| bodies byte-identical, md5 both sides | **DONE** |
| before/after char counts + repo total vs CURRENT origin/main | **DONE** — 1,825 → 594 |
| validate-agents on the branch, verdict + agent count quoted | **DONE** — 1 agent; FAIL → PASS WITH WARNINGS (deterministic phases, $0) |
| CI green where the repo has CI | **DONE** — repo has CI; all 4 job-equivalents green locally, live state on the PR |
| anything already compliant left unedited and named | **N/A** — the repo's one agent was non-compliant on 3 counts |

## 8. Files this lane touched

- `agents/notify-expert.md` — frontmatter `description` only
- `docs/lanes/dae2-catalog-notify/**` — this note, the runner, and evidence

Nothing else in the repo, and no other repo.
