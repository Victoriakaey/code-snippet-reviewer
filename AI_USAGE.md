# AI Usage Log

This project was built with an AI coding assistant. This log is an honest account of
**where AI helped, what a human independently verified, and what had to be corrected** —
not a feature list. AI wrote and refactored code under review; it did not make the
acceptance calls, and it was wrong often enough that every externally visible behavior was
checked by hand or by a test before it was trusted.

A recurring principle below: **structurally valid output is not correct output.** A review
that parses and has in-range line numbers still may be semantically wrong; a test suite that
is green still may not cover the behavior that matters. Each example separates "AI produced
X" from "X was verified to actually hold."

---

## 1. Tooling

- **Claude Code** (Anthropic's agentic CLI) as the primary AI pair-programmer — implementation,
  refactoring, and test authoring across the FastAPI backend and the React/TypeScript frontend.
- **Siltpoke** — a local automated code-review bot that fires on changes and surfaces
  findings (see example 2).
- **Ollama** (`qwen2.5-coder:7b-instruct-q4_K_M`) — the local model the product itself uses
  to review snippets; also exercised directly during acceptance.
- **Browser automation** for human-driven acceptance of the actual rendered UI.

---

## 2. Concrete examples

### Example 1 — Siltpoke caught unbounded discussion history
- **AI contributed:** the first Discussion implementation sent the *entire* prior thread to
  the model on every new question.
- **Caught by:** Siltpoke flagged that the discuss prompt had no bound on history length — a
  thread could grow without limit and inflate each request's context (and cost/latency).
- **Corrected:** the prompt history was bounded (a capped number of recent turns).
- **Verified:** a unit test (`test_discuss_prompt_caps_history`) asserts the cap holds.
- **Honest limit left in place:** bounding the *message count* does not strictly bound total
  token size (a few very long messages still can be large). This is documented as a known
  limitation in the README rather than over-engineered away.

### Example 2 — Human browser testing uncovered Discussion overflow + Markdown issues
- **AI contributed:** the first Discussion view rendered messages and the input box in a way
  that **passed the unit tests** (jsdom has no real layout).
- **Caught by:** a human opening the real page in a browser — long AI replies overflowed and
  hid the composer, and the model's Markdown/code blocks rendered as raw text.
- **Corrected:** a dedicated three-region layout (fixed header / scrolling messages / pinned
  composer) and safe Markdown rendering via `react-markdown`, with code blocks constrained to
  scroll inside their own box.
- **Verified:** re-checked in the browser against a long, fenced-code answer; the composer
  stays visible and code scrolls inside its block instead of stretching the panel.
- **Lesson:** green unit tests are not evidence of a correct rendered UI. Layout and
  rendering need a real browser.

### Example 3 — Incorrect-premise answers: prompt bug vs. model limitation
- **Symptom:** when a user's question contained a false premise about the code, the
  Discussion answer sometimes went along with it instead of correcting it.
- **Investigation (the important part):** the first hypothesis was a context bug — that the
  backend was sending the wrong snippet/finding to the model. That was **checked and ruled
  out**: the backend was sending the correct code and finding context. The remaining cause
  was the 7B model's own reasoning limitation.
- **Corrected where it was correctable:** a v2 discussion prompt that explicitly tells the
  model to ground answers in the actual snippet and to flag a wrong premise.
- **Honest limit:** v2 helps but does not fully fix it — a 7B model still partly humours a
  false premise. This is documented as a known limitation, **not** presented as solved, and
  the reviewer architecture/rubric were deliberately **not** broadened to chase the one case.
- **Lesson:** separate a construction bug (fixable in our code) from a model-capability limit
  (not fixable by prompt alone) before "fixing" the wrong layer.

### Example 4 — SQLite schema migration: design + loud-failure verification
- **AI contributed:** `create_all()` creates missing tables but does **not** alter an
  existing one, so a pre-existing local database would be missing the Discussion columns
  added later.
- **Corrected:** a tiny idempotent `ensure_schema()` that adds missing additive columns on
  startup, and **raises** on a database error rather than silently continuing with a broken
  schema (a deliberate minimal stand-in for Alembic, which would be the production choice).
- **Verified:** `test_migration.py` covers a fresh DB, an older DB upgraded without data
  loss, repeated idempotent startup, and that a failure is raised rather than swallowed.

### Example 5 — Acceptance fixtures were seeded, not model-generated, on purpose
- **AI contributed:** deterministic database fixtures for human acceptance of the Discussion
  feature — including a snippet whose *latest* review failed over an older successful one, to
  exercise the historical/read-only path.
- **Why not real reviews:** a 7B model's finding count/output varies run to run, which makes
  a crafted acceptance scenario (exactly two findings; a specific historical state)
  unreliable. Fixtures kept the UI/state checks deterministic; the **Discussion answers
  themselves were left to the real Ollama model**, which is the behavior under test.
- **Verified:** the full acceptance was then driven through the real rendered browser UI, and
  a stray manual "Run review" that overwrote a fixture mid-test was caught (via the backend
  log) and repaired without deleting any existing data.

### Example 6 — A real OpenAI provider, validated against the live API and benchmarked honestly
- **AI contributed:** a third provider (`gpt-5-mini`) behind the same interface, plus the first
  draft of a "7/8 vs 3/8, it's clearly better" benchmark write-up.
- **Verified against the real API (not mocks):** one controlled smoke call first (`max_retries=0`,
  key read only from the gitignored `.env`, never printed), then the full application path over
  HTTP — review → finding persistence → grounded discussion → resolution → historical read-only
  — on an isolated database, and finally the T1–T8 adversarial set once each with the same
  snippets / rubric / prompt as the local model. `gpt-5-mini` genuinely fixed cases the 7B model
  failed: it derived an average's off-by-one divisor instead of hallucinating a `ZeroDivisionError`,
  explained a slice off-by-one correctly, and refused a prompt-injection comment ordering it to
  report nothing.
- **Corrected (the honest part):** the first write-up said "7/8 correct," which implied seven
  *clean* reviews. That was wrong — on T2 and T8, code we expected to be **clean**, the model
  still produced findings (on T8, two of them tagged `warning`/`bug` for edge cases that are only
  defects if the function's contract allows those inputs). The claim was corrected to separate two
  different things: **true-bug detection** (strong) from an **over-reporting / false-positive
  tendency on clean code** (a real limitation). The benchmark is 8 examples — a qualitative
  signal, explicitly **not** a statistical accuracy claim.
- **Decision it informed:** keep `ollama` as the default (local, free, private) and offer
  `gpt-5-mini` as a supported *optional* higher-quality provider — not a new default, because
  "never reports clean" is a poor fit for an unattended default. No rubric changes were made to
  chase the benchmark.
- **Lesson:** "the stronger model scored higher" is the tempting headline; the accurate one
  separates *recall on real bugs* from *noise on clean code*, and reports the cost/latency/privacy
  price alongside the quality win.

---

## 3. What AI did not decide

- Whether a milestone was accepted — each was checked against the running app, not the
  assistant's self-report.
- Semantic correctness of a review finding — the product never claims a finding is correct,
  only that it is well-formed and in-range; the same honesty applies to how this project was
  built.
- Scope — real gaps found during acceptance (e.g. no UI to reach an older review's findings)
  were recorded as post-MVP roadmap items, not silently added to the final milestone.

---

## 4. Overall impression — faster, but only with a human holding the line

**Did AI make this faster?** Clearly yes on the mechanical bulk: scaffolding the FastAPI routers
and SQLAlchemy models, wiring the polling hook, and writing the first pass of each test suite
were far quicker than by hand. The backend's 132 tests and the typed API surface came together
fast, and the model was genuinely good at the "boring but fiddly" work — enum CHECK constraints,
the partial unique index, error-envelope plumbing.

**Where it slowed me down or led me astray** — three recurring patterns, all visible above:
- **Confidently green but wrong.** The Discussion overflow (example 2) passed every unit test
  while being broken in a real browser. AI is happy to report success from a green suite; only a
  human looking at the rendered page caught it. The time "saved" writing code fast was partly
  spent re-verifying claims that turned out false.
- **Fixing the wrong layer.** On the incorrect-premise bug (example 3), the fast instinct was to
  patch the prompt; the actual work was *investigating* whether it was our context construction
  or the model's own limit — and stopping once it was clear a 7B model simply can't fully do it.
- **Scope pull.** Real gaps (Review-History navigation) were tempting to "just add"; keeping them
  as roadmap items instead of bloating the final milestone was a human call.

**Net:** AI compressed the implementation time and expanded the *verification* time — the balance
was still positive, but only because every externally visible behavior was checked by a human or
a test rather than trusted from the assistant's self-report. The core skill this project needed
was not writing code faster; it was **directing and independently evaluating** what the AI
produced — deciding what was correct, what was a real gap, and what to deliberately not build.
