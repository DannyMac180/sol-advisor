# scripts/

Verifiers and operator procedures for the Prime Agent capability package.

The inherited Codex plugin keeps its own verifier at
`plugins/sol-advisor/scripts/verify.sh` and is deliberately not extended or coupled
from here. Package contributions instead require an empty base diff for `plugins/` and
`.agents/`; baseline plugin failures stay in their own issue and PR.

## Contents

| File | Purpose |
|---|---|
| `verify-prime-agent-package.sh` | Validates the package: manifest, skill frontmatter, the Python-backed detection contract, the full Python suite, an isolated install cycle, and the no-effort-write assertion. |
| `live-smoke-delegation.sh` | Prepares a throwaway environment for one real, operator-approved delegation. Prints the procedure; never spawns. |

## Quick reference

```sh
# Validate the package. No model quota, no host mutation.
sh scripts/verify-prime-agent-package.sh

# Skip the install cycle and the test run (useful without uv or prime-agent).
sh scripts/verify-prime-agent-package.sh --structural-only

# Prepare the one gate that costs money. Requires an explicit flag and a selector.
sh scripts/live-smoke-delegation.sh --i-understand-this-spends-quota provider/model
```

The verifier exits zero when every check passes and non-zero otherwise, naming each
offending file. A check that cannot run — `uv` or `prime-agent` missing — reports `skip`
with the reason rather than passing quietly.

## Why the live smoke gate exists

Every other gate runs against fixtures and a recording double, which means the package
could satisfy all of them having never delegated once. In a package whose deliverable is
a dataset of real delegations, that is a false-completion trap. So exactly one gate
spends quota, deliberately, and it is manual and operator-approved.

It has already earned its keep: its first runs found four defects that every
fixture-based gate had passed over, including a child's transcript not being where the
code looked and build artifacts being misread as ownership violations.
