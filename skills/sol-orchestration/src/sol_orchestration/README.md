# sol_orchestration

Kernel-side callables for cost-routed delegation. Fourteen modules; each opens with a
docstring explaining the failure it prevents.

## Reading order

Start at `contract.py` — the refusal and degradation vocabulary everything else uses.
Then follow a delegation end to end:

`preflight.py` → `routing.py` → `spec.py` → `lifecycle.py` → `evidence.py` →
`review.py` → `packet.py` → `ledger.py` → `episodes.py`

`host.py` sits under all of it: every host request goes through one seam with a single
injection point, which is what lets the whole package be tested without spending quota.
`home.py` resolves the Prime Agent home and the kernel venv — separately, because the
runtime never derives one from the other.

## The property that makes the tests possible

Every module imports outside a kernel. The bundled runtime is imported lazily inside
calls, never at module level, because it ships with Prime Agent rather than on PyPI and
the skill contract forbids declaring it as a dependency.

```sh
python -c "import sol_orchestration.evidence"   # works with no kernel, no runtime
```
