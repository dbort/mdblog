---
publish: true
slug: syntax
date: 2026-01-03
---
## Linking Out

See [[first-note|the first note]], [[link-target#Details]], [[projects/link-target#^detail-block]] and [[#Linking Out]].

![[diagram.svg|120x80]]

%% UNPUBLISHED-COMMENT [[missing note]] %%

> [!tip]- Folded tip
> FIXTURE-CALLOUT-BODY

Some ==FIXTURE-HIGHLIGHT== text. ^syntax-block

```
[[first-note]] %% kept %% ^kept
```

## Style sampler

> [!note]
> FIXTURE-NOTE-CALLOUT with `inline code` and a [[first-note|link]].

> [!warning]+ Open warning
> FIXTURE-OPEN-CALLOUT body.

> A plain quote.

```python
def greet(name: str) -> str:
    # Builds a greeting long enough that this line has to scroll inside its own box at phone width.
    return f"Hello, {name}!"
```

| Name | Kind | Default | Required | Description of what this setting does on the site |
|---|---|---|---|---|
| `base_url` | string | none | yes | The address every page lives under, including any path |
| `title` | string | none | yes | The site's name in the header and feeds |

A long address that must wrap at phone width: https://example.com/a/deliberately/long/path/without/any/spaces/that/would/widen/the/page.

- A list item
- Another list item
