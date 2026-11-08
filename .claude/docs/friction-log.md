---
next_id: friction-003
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

- `friction-001` - **Seeing the rendered site during task-012's restyle**:
  the environment has no headless browser (no Chromium, Firefox or
  Playwright), so the agent could not render a page, take a screenshot or
  measure layout. It checked markup with real-Hugo tests and left the whole
  visual check (sidebar placement at 375px and desktop width, light and
  dark palettes, no sideways scroll) to the author's manual QA, the first
  time anyone saw the pages. Simpler if: a headless browser in the pixi
  environment (for example Playwright with Chromium), so the agent can
  screenshot fixture pages at each width and color scheme before manual
  QA, and tests can assert layout facts such as no horizontal overflow at
  375px and the sidebar's position.
- `friction-002` - **Checking task-012's palettes against WCAG AA**: no
  contrast tool exists, so the agent wrote a throwaway script that
  hardcodes both palettes, computes `color-mix()` tints by hand and
  regex-parses the Chroma rules out of `main.css`. Its results depend on
  the hardcoded values staying in step with the stylesheet. Simpler if: a
  contrast check in `tools/check` that reads the color pairs from
  `main.css` itself, so the stylesheet header's AA claim is enforced
  instead of rechecked by hand.
