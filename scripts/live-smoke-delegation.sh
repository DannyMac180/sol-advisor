#!/bin/sh
# Prepare the one gate in this package that spends model quota.
#
# Every other gate runs against fixtures and a recording double, which means the whole
# Definition of Done is otherwise reachable by a package that has never delegated once.
# In an epic whose deliverable is a dataset, that is a false-completion trap. So exactly
# one gate spends quota, deliberately, and it is required.
#
# It is also the only moment a model-controlled process gets execution on this host.
# What this script does to bound that:
#
#   * The working directory is a throwaway git repository created fresh in a temp dir.
#     The child edits that, not any real project.
#   * The Prime Agent home and the kernel venv are both redirected to temp directories.
#     The episode lands there, and the operator's real ~/.prime/agent is never written.
#   * Only auth.json is copied into the disposable home, because a spawn has to
#     authenticate against real credentials or it cannot resolve a model at all.
#
# What it does NOT bound, stated plainly: the child runs with the operator's own OS
# permissions. The throwaway repository is a convention about where it should write,
# not a sandbox that stops it writing elsewhere. The kernel is documented as a durable
# control environment, not a security boundary, and this package never claims otherwise.
#
# This script prepares and prints; it does not spawn. Driving a live delegation needs a
# real kernel, so the last step is a session the operator starts and a cell they paste.
#
# Usage: sh scripts/live-smoke-delegation.sh --i-understand-this-spends-quota <selector>
# Exit:  0 when the throwaway environment is ready; 1 otherwise.

set -eu

CONFIRM=no
SELECTOR=""
for argument in "$@"; do
	case "$argument" in
	--i-understand-this-spends-quota) CONFIRM=yes ;;
	-*) printf 'unknown option: %s\n' "$argument" >&2; exit 1 ;;
	*) SELECTOR="$argument" ;;
	esac
done

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

if [ "$CONFIRM" != yes ] || [ -z "$SELECTOR" ]; then
	cat >&2 <<'USAGE'
This gate spends model quota and gives a model-controlled process execution on this
host. It is deliberate and required, but it is not automatic.

  sh scripts/live-smoke-delegation.sh --i-understand-this-spends-quota <provider/model>

Pass the cheapest model you have declared. Run `prime-agent model list` to see what is
authenticated. Nothing is spawned by this script.
USAGE
	exit 1
fi

case "$SELECTOR" in
*/*) ;;
*) printf 'selector must be a full provider/model, got: %s\n' "$SELECTOR" >&2; exit 1 ;;
esac

command -v prime-agent >/dev/null 2>&1 || { printf 'prime-agent is not installed\n' >&2; exit 1; }
command -v git >/dev/null 2>&1 || { printf 'git is not installed\n' >&2; exit 1; }

REAL_HOME=${PRIME_AGENT_CODING_AGENT_DIR:-$HOME/.prime/agent}
[ -f "$REAL_HOME/auth.json" ] || { printf 'no auth.json at %s; a spawn cannot authenticate\n' "$REAL_HOME" >&2; exit 1; }

SMOKE_HOME=$(mktemp -d)
SMOKE_VENV=$(mktemp -d)/kernel-venv
SMOKE_REPO=$(mktemp -d)/throwaway-repo

# --- the throwaway repository --------------------------------------------------

mkdir -p "$SMOKE_REPO/src" "$SMOKE_REPO/tests"
cd "$SMOKE_REPO"
git init -q -b main
git config user.email smoke@example.invalid
git config user.name "Live Smoke"

cat > src/adder.py <<'PY'
def add(left, right):
    """Return the sum of two numbers."""
    return left + right
PY

cat > tests/test_adder.py <<'PY'
from src.adder import add


def test_add():
    assert add(2, 3) == 5


def test_add_negative():
    assert add(-1, -1) == -2
PY

git add -A
git commit -q -m "throwaway baseline"

# --- the disposable Prime Agent home -------------------------------------------

cp "$REAL_HOME/auth.json" "$SMOKE_HOME/auth.json"
mkdir -p "$SMOKE_HOME/sol-orchestration"
cat > "$SMOKE_HOME/sol-orchestration/config.json" <<CONFIG
{
  "allowlist": ["$SELECTOR"],
  "review_model": "$SELECTOR",
  "verification_commands": {
    "unit": ["python", "-m", "pytest", "-q"]
  },
  "routing_prior": {
    "default": "$SELECTOR",
    "rules": []
  }
}
CONFIG

PRIME_AGENT_CODING_AGENT_DIR="$SMOKE_HOME" PRIME_AGENT_KERNEL_VENV="$SMOKE_VENV" \
	prime-agent package install "$ROOT" >/dev/null

cat <<READY

Throwaway environment ready. Nothing has spawned and no quota has been spent yet.

  repository    $SMOKE_REPO
  agent home    $SMOKE_HOME
  kernel venv   $SMOKE_VENV
  selector      $SELECTOR
  real home     $REAL_HOME  (untouched; only auth.json was read)

Start the session:

  cd $SMOKE_REPO
  PRIME_AGENT_CODING_AGENT_DIR=$SMOKE_HOME \\
  PRIME_AGENT_KERNEL_VENV=$SMOKE_VENV \\
  prime-agent --thinking high

Then paste this into one kernel cell:

  from pathlib import Path
  from sol_orchestration import config, evidence, ledger, lifecycle, packet, reader, routing, spec

  declared = config.load()
  repo = Path("$SMOKE_REPO")
  book = ledger.Ledger()

  class Snap:
      def capture(self): return evidence.snapshot(repo, declared)

  engine = lifecycle.Lifecycle(declared=declared, recorder=book, snapshotter=Snap())
  work = spec.Spec(
      objective="Add a subtract(left, right) function to src/adder.py returning left - right, "
                "and a test for it in tests/test_adder.py.",
      domain="python", difficulty="easy",
      ownership=("src/adder.py", "tests/test_adder.py"),
      verification_command="unit",
  )
  decision = routing.select(domain=work.domain, difficulty=work.difficulty,
                            prior=declared.prior, surviving=declared.allowlist)
  delegation = await engine.dispatch(work, selector=decision.selector,
                                     surviving=declared.allowlist)
  print("dispatched:", delegation.delegation_id, "on", delegation.selector)

Wait for the child, then in a later cell:

  collected = await engine.collect(delegation, bound_seconds=600)
  result = evidence.collect(repo=repo, snapshot=delegation.snapshot,
                            ownership=work.ownership,
                            verification_argv=declared.verification_commands["unit"],
                            declared=declared)
  book.record_round(delegation.delegation_id, ...)      # one RoundOutcome from result
  await engine.close(delegation, "ship")                # or the verdict the packet earns
  print(reader.summarise())

What proves the gate passed:

  * exactly one closed record in $SMOKE_HOME/sol-orchestration/episodes.jsonl
  * that record has a non-null selector and a real verification status
  * reader.validate(record).valid is True
  * nothing under $REAL_HOME changed

Clean up when done:

  rm -rf $SMOKE_HOME $(dirname "$SMOKE_VENV") $(dirname "$SMOKE_REPO")

READY
