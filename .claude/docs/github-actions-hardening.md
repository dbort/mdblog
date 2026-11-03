# GitHub Actions hardening

These rules apply to every workflow in `.github/workflows/`, once the
project has one. They limit the blast radius of a compromised action, a
malicious pull request, or a leaked token. A change that relaxes one
changes this file too and says why in its commit message.

A project with workflows lints them inside `tools/check`. `actionlint`
catches workflow errors, and `zizmor` with its `unpinned-uses` policy set
to `hash-pin` enforces the pinning rule below.

## Pin every action to a commit SHA

Every `uses:` names a full 40-hex commit SHA followed by the release it
corresponds to:

```yaml
uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
```

Tags and branches are mutable; a SHA is not. Resolve the SHA from the
release tag yourself, never from a value pasted from documentation.

A confirmed linter false positive is silenced inline with a one-line
reason. A genuine finding is fixed, never suppressed.

## Start with no permissions

Each workflow sets `permissions: {}` at the top level, and each job grants
only the scopes it uses.

## Never `pull_request_target`

Workflows trigger on `push` and `pull_request` only. `pull_request_target`
runs with a read-write token and secrets while checking out untrusted code.

## Never interpolate event context into shell

No `run:` body contains `${{ github.event.* }}` or any other
attacker-controllable expression, because it is substituted before the
shell parses the line. Pass it through `env:` and quote the variable:

```yaml
- env:
    TITLE: ${{ github.event.pull_request.title }}
  run: echo "$TITLE"
```

## Pinned runner, harden-runner first

`runs-on` names a dated image (`ubuntu-24.04`), never `ubuntu-latest`, so
an OS upgrade is never an unplanned side effect of an unrelated push.
`step-security/harden-runner` with `egress-policy: audit` is the first step
of every job, building the baseline for a later move to `block`.

A workflow cancels a branch's in-flight run on a new push (`concurrency`
keyed on workflow and ref).

## Dependency updates

`.github/dependabot.yml` proposes weekly SHA bumps for `github-actions`.
