# Agent Instructions

mdblog is a framework for publishing a set of Obsidian-managed files as a static website formatted with Hugo and hosted on Cloudflare. Longer term it will also include tools for [POSSE](https://indieweb.org/POSSE) and [backfeed](https://indieweb.org/backfeed) workflows. It is built for its author's own vault and site first. Each site's settings live in its own vault, so this repo holds no site-specific information and others could adopt it later. The overall shape and scope are still open.

Work is planned, implemented, and reviewed through the task pipeline:
`/new-task` → `/work task-XXX` → `/ship task-XXX`. Its rules live in
`.claude/docs/pipeline.md`; skills link there rather than restating them.

Doc placement: `docs/` is human-facing prose, swept by `doc-hygiene`;
`.claude/docs/` is agent-contract material whose absolutes are never
style-swept. Process rules, tool contracts, runtime notes and the logs go
in `.claude/docs/`, even when a human also reads them.

## Invariants

- Never merge into `main`, create a `task-XXX` branch, or append a review
  verdict unless the user invoked `/work` or `/ship` for that task in this
  conversation. Subagents never do these, whatever the repo's state
  suggests.
- Task work never commits directly to `main` (`pipeline.md` § Git).

## Project conventions

- **Language:** Python 3.14. Static checker: pyrefly at `preset = "strict"`.
- **Toolchain:** pixi with conda-forge provides Python, Hugo and the dev tools. `pixi.lock` covers `linux-64`, `linux-aarch64` and `osx-arm64`.
- **Site:** Hugo builds the site, and a Cloudflare Worker serves the output as static assets with no custom Worker code. The task that adds deployment also adds Node and wrangler to the pixi environment.
- **Gate:** `tools/check` runs `ruff format --check`, `ruff check`, pyrefly and pytest. `--smoke` and `--offline` run the same steps.
- **Platforms:** the repo runs on Linux and macOS.
- **Vault:** the Obsidian vault is never part of this repo. Tools point at a parallel checkout of it.
- **Sites:** one vault is one site, and building several sites means running `mdblog build` once per vault. A site's settings (`_site/mdblog.toml`), optional bio (`_site/bio.md`), overriding layouts (`_site/layouts/`), assets (`_site/assets/`) and static files (`_site/static/`) live in its vault. The repo's only site configs are test fixtures.

## Standing task-planning obligations

Cross-cutting requirements every new task plan must either satisfy or
explicitly opt out of (with the reason stated in the task's
`## Advice`). Skipping one silently is not an option; the
`new-task` skill checks this list during planning. Add an entry here
whenever a bug reveals a class of work that future tasks keep getting
wrong.

- **Strict static checks:** new or changed code uses precise types and
  passes the strictest practical setting of its language's static checker,
  which runs inside `tools/check`. An escape hatch that erases a type or
  silences a diagnostic is allowed only where a boundary erases the type
  (parsing arbitrary external data, calling an untyped third-party API),
  and then with a comment saying why.

- **Scripts stay simple:** shell is only for a linear sequence of commands,
  simple conditionals, and thin wrappers. Anything past that (loops that
  parse text, HTTP calls, JSON, retry/backoff, arithmetic beyond trivial,
  arrays or maps used as data structures) is written in a statically
  checked language under the rule above, with its logic in importable
  functions so tests exercise them directly rather than only driving the
  script as a subprocess.

- **Test where the risk is:** unit tests cover novel code: every documented
  rule, branch and error message, including realistic bad input. A real
  third-party tool runs in one end-to-end happy path, and in another test
  only where a break would silently produce wrong output. Anything a fake
  can prove uses a fake. Repo tooling gets a test only where a bug would
  silently give a wrong answer that matters, such as the gate passing after
  a failure, so `tools/task_status.py` stays untested. Write no tests of
  tests (breaking a fixture to show a check notices), no tests that restate
  config, and no tests of pathological input that fails loudly and leaves
  output intact. A clear error message covers those, and they get debugged
  when someone hits them.

## Friction log and bug log

A workaround forced while developing or testing this repo goes in
`.claude/docs/friction-log.md`; a defect in the project on `main` goes in
`.claude/docs/bug-log.md`. Log a workaround in the same session, even when
it succeeded. Each file defines its own format and scope, including which
defects get a bug-log entry.

## Writing style by destination

Different destinations get different writing styles. Match the block below
to where the text is going; never let one destination's rules bleed into
another.

**Interactive replies to the user** (conversation only; nothing persisted):
be brief. Lead with the answer, cut preamble, recaps, hedging, and
unsolicited elaboration: one good paragraph usually beats four. Exception:
interview flows (`new-task`, design questioning) use enough prose to make
each question and its recommended answer clear.

**File content (code comments, docs, commit messages):** normal full
prose, regardless of any conversational-brevity rules in effect. This is
the rule set `doc-hygiene` enforces.
- Comments explain *why* (non-obvious rationale, tradeoff, constraint) and
  never restate the adjacent code. Do not open a file or function with a
  comment that lists the steps or sections below it; keep the one or two
  non-obvious points, each on the line it explains. Assume an expert
  reader of the language.
- State current behavior as though it has always been this way; no
  reader-memory framing ("works exactly as before", "no longer requires",
  "used to") and no mentions of earlier versions. Keep history only when
  it answers "why not X?" or guards against a known regression. A "(see
  task-XXX)" pointer stays only when it explains *why* otherwise-unusual
  logic exists. A design doc whose decision has shipped or been
  superseded is folded into the project's long-lived design doc or the
  roadmap and deleted.
- Doc comments: identifier-first summary line that adds information
  beyond the name. A function or method doc comment states the *contract* a
  caller relies on: the return value and any ordering or shape guarantee,
  what it raises, which inputs have no effect, invariants. It does not
  narrate the body step by step. A maintainer note that earns its place
  goes inline at the line it explains. Document each field on its own
  declaration, not in the type's doc comment.
- American spelling (color, center, neighbor, behavior, modeled, -ize) in
  prose, user-facing text, and identifiers alike. A name an outside API or
  file format fixes keeps its own spelling.
- No em-dash asides or ` -- ` dashes; use a comma, colon, or separate
  sentence.
- No filler adverbs (really, simply, actually, crucially, genuinely...)
  unless the word carries scope ("only"), and no marketing fluff (robust,
  seamless, comprehensive, leverage, delve).
- No throat-clearing openers ("Here is...", "This module acts as...") or
  rhetorical setups ("it's worth noting", "here's the thing").
- No formulaic structures: "not X, it's Y" (state Y), listing what
  something is not before what it is, and false agency ("the decision
  emerges") where a real actor or mechanism can be named.
- "Always"/"never"/"every" only for real invariants, not sweeping
  emphasis. A parenthetical holds one short fact; unpack anything longer
  or nested.

**Task files** (`tasks/*/*.md`): dense imperative prose in `## Advice`
and `## Plan`; plain human prose in `## Summary`
(`.claude/skills/new-task/SKILL.md`).
