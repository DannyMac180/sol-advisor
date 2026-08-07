# tests/

258 tests. None of them spends model quota.

## Layout

| File | Covers |
|---|---|
| `conftest.py` | The recording host double, a fake clock, recording recorder and snapshotter |
| `test_contract.py` | Refusal and degradation vocabulary |
| `test_home.py`, `test_detection_contract.py`, `test_run.py` | Package skeleton and the skill detection contract |
| `test_config.py` | Operator declarations and every refusal |
| `test_host.py`, `test_spawn_adapter.py` | The host seam and the spawn guards |
| `test_preflight.py`, `test_routing.py` | Availability, effort floor, retention, selection |
| `test_spec.py` | Child prompt and the trust boundary |
| `test_lifecycle.py` | Dispatch, collection, correction, closing |
| `test_evidence.py` | Delta, tamper gate, redaction, integrity, adversarial signals |
| `test_review.py` | The review child |
| `test_packet.py` | Assembly, forgery resistance, failure-aware bounding |
| `test_episodes.py`, `test_ledger.py` | The corpus, the ledger, the reader |

## How to trust this suite

Green is not enough. Anything load-bearing here has been **mutation-checked**: the
behaviour is deleted on purpose and the suite must fail. That practice has caught real
defects — including a truncation test that passed with the failure-aware branch removed,
which meant it was proving nothing until it was rewritten to discriminate.

```sh
uv run --with pytest python -m pytest -q
```
