# Agent Instructions

mdblog publishes an Obsidian vault as a static Hugo site hosted on Cloudflare, and will later add [POSSE](https://indieweb.org/POSSE) and [backfeed](https://indieweb.org/backfeed) tools. It is built for its author's own site first. Each site's settings live in its own vault, so this repo holds nothing site-specific.

Work is planned, implemented, and reviewed through the task pipeline:
`/new-task` → `/work task-XXX` → `/ship task-XXX`. Its rules live in
`.claude/docs/pipeline.md`; skills link there rather than restating them.

Doc placement: `docs/` is human-facing prose, swept by `doc-hygiene`.
`.claude/docs/` holds agent contracts (process rules, tool contracts,
runtime notes, the logs), even when a human also reads them, and its
absolutes are never style-swept. Planned work lives only in
`docs/roadmap.md` and task files (`pipeline.md` § Roadmap). Every fact
has one home, and other files point to it (§ Writing style by
destination).

## Invariants

- Never merge into `main`, create a `task-XXX` branch, or append a review
  verdict unless the user invoked `/work` or `/ship` for that task in this
  conversation. Subagents never do these, whatever the repo's state
  suggests.
- Task work never commits directly to `main` (`pipeline.md` § Git).

## Project conventions

- **Language:** Python, checked by pyrefly at its strict preset. `pixi.toml` pins the version.
- **Toolchain:** pixi with conda-forge provides Python, Hugo, Node and the dev tools for the platforms `pixi.toml` lists. Wrangler comes from npm, pinned by `package-lock.json`, which `tools/check` installs and checks against `package.json`.
- **Site:** Hugo builds the site, and a Cloudflare Worker serves the output as static assets with no custom Worker code.
- **Vault format and Hugo:** `docs/vault-format.md` is the vault author's contract, with no Hugo terms or theme behavior, so it could describe another generator. `.claude/docs/hugo-site.md` maps it onto Hugo and the theme, pointing into the code.
- **Gate:** `tools/check`, whose contract is in `.claude/docs/pipeline.md` § Checks and whose steps are in `tools/check_runner.py`.
- **Platforms:** the repo runs on Linux and macOS.
- **Vault:** the Obsidian vault is never part of this repo. Tools point at a parallel checkout of it.
- **Manual QA:** each manual-QA Must Have is a check in `tools/manual_qa.py`. Ask the author to run `tools/manual-qa [NAME...]`, which writes a log they hand back, rather than giving them ad hoc steps or setup.
- **Sites:** one vault is one site, built by one `mdblog build`. The repo's only site configs are test fixtures.

## Standing task-planning obligations

Every new task plan satisfies each entry or opts out with its reason in
`## Decisions`; the `new-task` skill checks this list. A task file names
an entry only to opt out of it or where the entry changes what that task
must do, never to say it applies. Add an entry whenever a bug reveals a
class of work that tasks keep getting wrong.

- **Strict static checks:** new or changed code uses precise types and
  passes the strictest practical setting of its language's static checker,
  which runs inside `tools/check`.
  An escape hatch that erases a type or silences a diagnostic is allowed
  only at a boundary that erases the type (arbitrary external data, an
  untyped third-party API), with a comment saying why.

- **Scripts stay simple:** shell is only for linear commands, simple
  conditionals and thin wrappers. Anything more (text-parsing loops, HTTP,
  JSON, retries, real arithmetic, arrays or maps as data) is written in a
  statically checked language, with its logic in importable functions that
  tests call directly.

- **Docs point to code:** a task updates only the doc that owns each
  changed fact and copies nothing code defines into a doc (§ Writing
  style by destination). A Must Have or Checklist step that calls for a
  doc edit names the facts it adds.

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

Log a workaround forced while developing or testing this repo in
`.claude/docs/friction-log.md` in the same session, even when it
succeeded, and a defect on `main` in `.claude/docs/bug-log.md`. Each file
defines its own format and scope.

## Writing style by destination

Match the block below to where the text is going; never let one
destination's rules bleed into another.

**Interactive replies to the user** (conversation only; nothing persisted):
be brief. Lead with the answer, cut preamble, recaps, hedging, and
unsolicited elaboration: one good paragraph usually beats four. Exception:
interview flows (`new-task`, design questioning) use enough prose to make
each question and its recommended answer clear.

**File content (code comments, docs, commit messages):** normal full
prose, regardless of any conversational-brevity rules in effect. This is
the rule set `doc-hygiene` enforces.
- One home per fact. A tunable value (limit, default, list of names)
  lives only in code, and every doc names its constant, file or test, so
  changing the value changes no doc. An agent doc also points to code for
  rules and mechanics instead of restating them. A user doc states the
  rules its reader must follow, such as a property's valid values, and
  still points to code for tunable values. Between docs, link to the
  owner.
- Frugal docs. A user doc says what to do, the rules and what fails, and
  leaves out edge cases an error or warning message reports when they
  happen. An agent doc records only what no single source file shows
  (cross-file design, decisions and their reasons). Prefer a pointer to a
  paragraph.
- Comments explain *why* (non-obvious rationale, tradeoff, constraint) and
  never restate the adjacent code. Do not open a file or function with a
  comment that lists the steps or sections below it; keep the one or two
  non-obvious points, each on the line it explains. Assume an expert
  reader of the language.
- State current behavior as though it has always been this way: no
  reader-memory framing ("no longer requires", "used to") and no earlier
  versions. Keep history only when it answers "why not X?" or guards
  against a known regression, and a "(see task-XXX)" pointer only when it
  explains otherwise-unusual logic. Fold a shipped or superseded design
  doc into the long-lived design doc or the roadmap and delete it.
- Doc comments: an identifier-first summary line that adds to the name.
  A function's doc comment states the *contract* a caller relies on
  (return value, ordering or shape guarantees, what it raises, inputs with
  no effect, invariants) and never narrates the body. A maintainer note
  goes inline at the line it explains. Document each field on its own
  declaration.
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

**Task files** (`tasks/*/*.md`): dense imperative prose in `## Decisions`,
`## Notes` and `## Checklist`; plain human prose in `## Summary`
(`.claude/skills/new-task/SKILL.md`).
