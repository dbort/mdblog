---
next_id: friction-005
---

# Friction log

Moments where developing or testing this repo forced a workaround: a
missing tool, data in the wrong shape, a doc that had to be
reverse-engineered. Log it in the same session, even when the workaround
succeeded. Defects in the project itself go in `bug-log.md` instead.

An entry qualifies only if its fix is something this repo could build or
write. An upstream tool's permanent behavior belongs in a comment at the
call site, a doc under `.claude/docs/`, or a Claude memory.

Format, oldest first:

- `friction-NNN` - **<what was needed>**: what happened; the workaround
  used. Simpler if: <the missing tool/data/doc>.

The id is `next_id` from the front matter; increment it in the same
commit. It only moves forward, even when entries are deleted. An entry
written during task work commits on the task's branch. A commit that
fixes the entry, or removes the code it concerns, deletes it and records
the papercut and its fix in its message.

## Entries

- `friction-001` - **Seeing the rendered site during task-012's restyle**: with no headless browser, the agent could not screenshot or measure layout, so it checked markup with real-Hugo tests and left the visual check (sidebar placement at 375px and desktop, both palettes, no sideways scroll) to manual QA. Simpler if: a headless browser in the pixi environment, such as Playwright with Chromium, so agents can screenshot fixture pages and tests can assert layout facts like no horizontal overflow at 375px.
- `friction-002` - **Checking task-012's palettes against WCAG AA**: with no contrast tool, the agent wrote a throwaway script that hardcoded both palettes, computed `color-mix()` tints by hand and regex-parsed the Chroma rules from `main.css`. Simpler if: a contrast check in `tools/check` that reads the color pairs from `main.css`, so the stylesheet's AA claim is enforced.
- `friction-003` - **Proving task-016's wrangler runs need no network**: `unshare -rn` is not permitted in the agent's sandbox, so the agent pointed `HTTPS_PROXY` and `HTTP_PROXY` at a closed local port and watched for connection errors, which catches only requests that honor the proxy variables. `tests/test_stage.py` keeps that check as `NO_NETWORK`. Simpler if: a `tools/` wrapper that runs a command with networking cut off on Linux and macOS, such as one built on `bwrap --unshare-net` and `sandbox-exec`, for tests that must prove a tool stays offline.

- `friction-004` - **Telling a flaky gate failure from a real one**: shipping task-019, `tools/check` on the merged tree failed once in `test_stage_serve_passes_verify` with "wrangler dev never served the home page", then passed twice alone and once in a full rerun on the same tree. The message does not say whether wrangler exited or the startup timeout ran out, and the test drops wrangler's output, so the cause stayed unknown and the workaround was a rerun. Simpler if: the test reports wrangler's exit status and the end of its output when it fails, so a timeout can be told from a crash.
