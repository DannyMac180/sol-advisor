#!/bin/sh
# Structural verifier for the Prime Agent capability package.
#
# Prime Agent is lenient by design: a broken manifest entry, a frontmatter name that
# disagrees with its directory, or a hatch wheel-packages list that disagrees with the
# source directory does not raise. The skill just degrades to markdown, or vanishes
# from discovery, behind a load warning nobody reads. This script is what makes those
# failures loud. It checks structure only — it never installs, never starts a session,
# and never touches the operator's Prime Agent home or kernel venv.
#
# The full pass adds three things the structural checks cannot see: the Python suite,
# an install cycle against a disposable home, and a parity assertion that no code path
# tries to read or write a thinking level through the host. None spends model quota.
# The inherited Codex plugin has its own verifier and remains a separate lane: coupling
# this new verifier to an unchanged baseline failure would force unrelated plugin edits
# into a package-only contribution.
#
# Usage: sh scripts/verify-prime-agent-package.sh [package-root] [--structural-only]
# Exit:  0 when every check passes; 1 otherwise, naming each offending file.

set -u

STRUCTURAL_ONLY=no
ROOT=""
for argument in "$@"; do
	case "$argument" in
	--structural-only) STRUCTURAL_ONLY=yes ;;
	*) ROOT="$argument" ;;
	esac
done
ROOT=${ROOT:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)}
MANIFEST="$ROOT/package.json"

failures=0
checks=0

fail() {
	failures=$((failures + 1))
	printf 'FAIL %s: %s\n' "$1" "$2" >&2
}

pass() {
	checks=$((checks + 1))
	printf 'ok   %s\n' "$1"
}

skip() {
	printf 'skip %s: %s\n' "$1" "$2"
}

require_command() {
	if ! command -v "$1" >/dev/null 2>&1; then
		printf 'FAIL %s: required command not found; install it and re-run\n' "$1" >&2
		exit 1
	fi
}

require_command jq

# --- manifest -----------------------------------------------------------------

if [ ! -f "$MANIFEST" ]; then
	fail "$MANIFEST" "root package.json is missing; Prime Agent cannot install this as a package"
	printf '\n%d check(s) passed, %d failed\n' "$checks" "$failures" >&2
	exit 1
fi

if ! jq empty "$MANIFEST" >/dev/null 2>&1; then
	fail "$MANIFEST" "not valid JSON: $(jq empty "$MANIFEST" 2>&1 | head -1)"
	printf '\n%d check(s) passed, %d failed\n' "$checks" "$failures" >&2
	exit 1
fi
pass "$MANIFEST parses as JSON"

if [ "$(jq -r '(.keywords // []) | index("pi-package") | if . == null then "no" else "yes" end' "$MANIFEST")" = "yes" ]; then
	pass "$MANIFEST declares the pi-package keyword"
else
	fail "$MANIFEST" 'keywords must contain "pi-package" for package discoverability'
fi

skill_roots=$(jq -r '.pi.skills // [] | .[]' "$MANIFEST")
if [ -z "$skill_roots" ]; then
	fail "$MANIFEST" 'pi.skills must list at least one skills directory (for example ["./skills"])'
else
	pass "$MANIFEST declares pi.skills"
fi

if [ "$(jq -r '(.dependencies // {}) | length' "$MANIFEST")" != "0" ]; then
	fail "$MANIFEST" "declares npm dependencies; this package must install with no dependency graph"
else
	pass "$MANIFEST declares no npm dependencies"
fi

# --- declared repository matches the checkout ---------------------------------
#
# Documentation in this repository never hardcodes an owner/repo slug: every command
# derives it from `origin`, so the docs stay correct here, upstream, and in any fork.
# `package.json` is the single declared exception, and this is what stops it going
# stale. A fork that has not updated it is told once, loudly, rather than shipping
# someone else's URL quietly.
#
# Deliberately compares against `origin` and not `gh repo view`: for a fork, `gh`
# resolves to the *parent* repository, so it would report upstream's slug and this
# check would pass while the manifest was wrong.

declared_repo=$(jq -r '.repository.url // .repository // ""' "$MANIFEST" \
	| sed -E 's#^git\+##; s#^(git@|ssh://git@|https://)github\.com[:/]##; s#\.git$##')
origin_url=$(git -C "$ROOT" remote get-url origin 2>/dev/null || true)
origin_repo=$(printf '%s' "$origin_url" \
	| sed -E 's#^(git@|ssh://git@|https://)github\.com[:/]##; s#\.git$##')

if [ -z "$declared_repo" ]; then
	fail "$MANIFEST" "declares no .repository.url; add one so tooling and docs have a source of truth"
elif [ -z "$origin_repo" ]; then
	skip "$MANIFEST repository check" "no git origin remote in $ROOT (tarball or detached checkout)"
elif [ "$declared_repo" = "$origin_repo" ]; then
	pass "$MANIFEST .repository.url matches the origin remote ($origin_repo)"
else
	fail "$MANIFEST" "declares repository '$declared_repo' but origin is '$origin_repo'. If you forked this repository, update .repository.url and .homepage in package.json to your own slug — that is the only place a slug is written down; every documented command derives it from origin instead"
fi

# --- skill directories --------------------------------------------------------

skill_dirs=""
for entry in $skill_roots; do
	resolved="$ROOT/${entry#./}"
	if [ ! -d "$resolved" ]; then
		fail "$MANIFEST" "pi.skills entry '$entry' does not resolve to a directory ($resolved)"
		continue
	fi
	pass "pi.skills entry '$entry' resolves to $resolved"

	# Prime Agent discovers direct root .md files in a skills root as individual
	# skills. A README.md or AGENTS.md left there is loaded as a malformed skill and
	# warns on every session start. Documentation for a skills root belongs one level
	# up; documentation inside a skill directory is never scanned and is fine.
	loose=$(find "$resolved" -maxdepth 1 -type f -name '*.md' | sort | tr '\n' ' ')
	if [ -n "$loose" ]; then
		fail "$(printf '%s' "$loose" | sed 's/ $//')" "loose markdown in the skills root '$entry' is discovered as a skill and will warn on every session start; move it up a level"
	else
		pass "skills root '$entry' has no loose markdown discovered as a skill"
	fi
	found=$(find "$resolved" -name SKILL.md -type f | sort)
	if [ -z "$found" ]; then
		fail "$resolved" "contains no SKILL.md; nothing would be discovered from this entry"
		continue
	fi
	skill_dirs="$skill_dirs$(printf '%s\n' "$found" | sed 's:/SKILL.md$::')
"
done

frontmatter_value() {
	# $1 = SKILL.md path, $2 = key. Prints the raw scalar value, quotes stripped.
	awk -v key="$2" '
		NR == 1 { if ($0 != "---") exit 1; next }
		/^---[[:space:]]*$/ { exit }
		{
			split($0, parts, ":")
			k = parts[1]
			gsub(/^[[:space:]]+|[[:space:]]+$/, "", k)
			if (k == key) {
				value = substr($0, index($0, ":") + 1)
				gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
				gsub(/^"|"$/, "", value)
				gsub(/^'\''|'\''$/, "", value)
				print value
				exit
			}
		}
	' "$1"
}

for skill_dir in $skill_dirs; do
	[ -n "$skill_dir" ] || continue
	skill_md="$skill_dir/SKILL.md"
	dir_name=$(basename "$skill_dir")

	if ! head -1 "$skill_md" | grep -q '^---[[:space:]]*$'; then
		fail "$skill_md" "must open with a YAML frontmatter block delimited by ---"
		continue
	fi

	name=$(frontmatter_value "$skill_md" name)
	description=$(frontmatter_value "$skill_md" description)

	if [ -z "$name" ]; then
		fail "$skill_md" "frontmatter has no name"
		continue
	fi

	if [ "$name" != "$dir_name" ]; then
		fail "$skill_md" "frontmatter name '$name' disagrees with its directory '$dir_name'; Prime Agent warns and the detection contract breaks"
	else
		pass "$skill_md name matches its directory ($name)"
	fi

	if printf '%s' "$name" | grep -Eq '^[a-z0-9]+(-[a-z0-9]+)*$'; then
		pass "$skill_md name '$name' satisfies the Agent Skills name rules"
	else
		fail "$skill_md" "name '$name' must be lowercase a-z, 0-9 and single internal hyphens only"
	fi

	if [ "${#name}" -gt 64 ]; then
		fail "$skill_md" "name is ${#name} characters; the specification allows at most 64"
	fi

	if [ -z "$description" ]; then
		fail "$skill_md" "frontmatter has no description; Prime Agent refuses to load a skill without one"
	elif [ "${#description}" -gt 1024 ]; then
		fail "$skill_md" "description is ${#description} characters; the specification allows at most 1024"
	else
		pass "$skill_md has a description within the 1024-character limit"
	fi

	# --- Python-backed detection contract -------------------------------------

	pyproject="$skill_dir/pyproject.toml"
	if [ ! -f "$pyproject" ]; then
		pass "$skill_md is a markdown-only skill (no pyproject.toml, nothing further to check)"
		continue
	fi

	import_name=$(printf '%s' "$name" | tr '-' '_')
	if ! printf '%s' "$import_name" | grep -Eq '^[a-z_][a-z0-9_]*$'; then
		fail "$pyproject" "import name '$import_name' derived from '$name' is not a valid Python identifier"
		continue
	fi

	init_py="$skill_dir/src/$import_name/__init__.py"
	if [ -f "$init_py" ]; then
		pass "$init_py exists (src layout matches the import name)"
	else
		fail "$pyproject" "expected src/$import_name/__init__.py for skill '$name'; without it the skill silently degrades to markdown"
	fi

	if grep -Eq "packages[[:space:]]*=[[:space:]]*\[[[:space:]]*[\"']src/$import_name[\"']" "$pyproject"; then
		pass "$pyproject wheel packages match src/$import_name"
	else
		declared=$(grep -E '^[[:space:]]*packages[[:space:]]*=' "$pyproject" | head -1 | sed 's/^[[:space:]]*//')
		fail "$pyproject" "[tool.hatch.build.targets.wheel] packages must be [\"src/$import_name\"]; found ${declared:-nothing}"
	fi

	# Only meaningful when the module is where the contract says it is; a missing
	# module has already been reported above and would report twice otherwise.
	if [ -f "$init_py" ]; then
		if grep -Eq '^[[:space:]]*(async[[:space:]]+)?def[[:space:]]+run[[:space:]]*\(' "$init_py"; then
			pass "$init_py defines run(), so the kernel exposes the module as a callable"
		else
			fail "$init_py" "defines no run(); the module would be imported but not callable in the kernel"
		fi
	fi

	if sed -n '/^dependencies[[:space:]]*=/,/\]/p' "$pyproject" | grep -q 'prime-agent-runtime'; then
		fail "$pyproject" "declares prime-agent-runtime as a dependency; it is bundled with Prime Agent, not published, and declaring it breaks every install outside the kernel venv"
	else
		pass "$pyproject does not declare the bundled runtime as a dependency"
	fi

	offenders=$(find "$skill_dir/src" -name '*.py' -type f 2>/dev/null | sort | while read -r module; do
		if grep -Eq '^(import|from)[[:space:]]+rlm([[:space:]]|\.|$)' "$module"; then
			printf '%s ' "$module"
		fi
	done)
	if [ -n "$offenders" ]; then
		fail "$(printf '%s' "$offenders" | sed 's/ $//')" "imports the bundled runtime at module level; import it lazily inside the call so the module still imports outside a kernel"
	else
		pass "$skill_dir/src has no module-level import of the bundled runtime"
	fi
done

# --- no thinking or effort host request, anywhere ------------------------------
#
# Nothing in the kernel can set a thinking level: the host bridge exposes no handler
# for it, so a call would fail at best and silently no-op at worst. The whole design
# rests on one operator-set dial per session, and this is what stops a future edit
# quietly introducing a best-effort call that appears to work.
#
# This looks for host *call sites*, not for the words. Reading a transcript's
# thinking_level_change entries is exactly how effort is observed and must stay legal.

for skill_dir in $skill_dirs; do
	[ -n "$skill_dir" ] || continue
	[ -d "$skill_dir/src" ] || continue

	effort_calls=$(grep -rnE '(host_request|\.request|rlm\.[a-z_]+)\([^)]*(thinking|effort)' "$skill_dir/src" 2>/dev/null || true)
	handler_names=$(grep -rnE '"[a-z_]+\.[a-z_]*(thinking|effort)[a-z_]*"' "$skill_dir/src" 2>/dev/null || true)
	offending=$(printf '%s\n%s' "$effort_calls" "$handler_names" | grep -v '^$' || true)

	if [ -n "$offending" ]; then
		fail "$skill_dir/src" "issues a thinking or effort host request; no such handler exists, so this would fail or silently no-op. Only the operator can change the level, through /effort:
$offending"
	else
		pass "$skill_dir/src issues no thinking or effort host request"
	fi
done

# --- Codex plugin boundary ------------------------------------------------------
#
# This verifier deliberately makes no request of the inherited Codex lane. Package PRs
# prove non-interference with an empty base diff for ``plugins/`` and ``.agents/``;
# the plugin's own verifier remains a separate command and any baseline failure stays
# in a separate issue/PR rather than being hidden inside Prime Agent package work.

# --- the Python suite ----------------------------------------------------------

if [ "$STRUCTURAL_ONLY" = yes ]; then
	skip "python suite" "--structural-only"
elif ! command -v uv >/dev/null 2>&1; then
	skip "python suite" "uv is not installed; install it to run this check"
else
	for skill_dir in $skill_dirs; do
		[ -n "$skill_dir" ] || continue
		[ -d "$skill_dir/tests" ] || continue
		if suite_output=$(cd "$skill_dir" && uv run --with pytest python -m pytest -q 2>&1); then
			pass "$skill_dir/tests: $(printf '%s' "$suite_output" | tail -1)"
		else
			fail "$skill_dir/tests" "the Python suite failed:
$(printf '%s' "$suite_output" | tail -25)"
		fi
	done
fi

# --- isolated install cycle ----------------------------------------------------
#
# Both variables are redirected. The home variable alone does not isolate the kernel
# venv: Prime Agent resolves that from its own variable and otherwise from a path
# hardcoded off the real user home, so a half-redirected cycle editable-installs into,
# and rebuilds, the operator's real venv. The real home is compared by path and size
# rather than by a hash including mtimes, which unrelated activity moves on a live host.

real_home=${PRIME_AGENT_CODING_AGENT_DIR:-$HOME/.prime/agent}

if [ "$STRUCTURAL_ONLY" = yes ]; then
	skip "install cycle" "--structural-only"
elif ! command -v prime-agent >/dev/null 2>&1; then
	skip "install cycle" "prime-agent is not installed; install it to run this check"
else
	before=$(mktemp)
	after=$(mktemp)
	find "$real_home" -printf '%p|%s\n' 2>/dev/null | sort > "$before"

	disposable_home=$(mktemp -d)
	disposable_venv=$(mktemp -d)/kernel-venv
	install_log=$(mktemp)

	if PRIME_AGENT_CODING_AGENT_DIR="$disposable_home" PRIME_AGENT_KERNEL_VENV="$disposable_venv" \
		prime-agent package install "$ROOT" >"$install_log" 2>&1; then
		listed=$(PRIME_AGENT_CODING_AGENT_DIR="$disposable_home" PRIME_AGENT_KERNEL_VENV="$disposable_venv" \
			prime-agent package list 2>&1 || true)
		if printf '%s' "$listed" | grep -qF "$ROOT"; then
			pass "install cycle: the package appears in a disposable home"
		else
			fail "install cycle" "the package installed but does not appear in package list"
		fi

		PRIME_AGENT_CODING_AGENT_DIR="$disposable_home" PRIME_AGENT_KERNEL_VENV="$disposable_venv" \
			prime-agent package remove "$ROOT" >>"$install_log" 2>&1 || true
		listed_after=$(PRIME_AGENT_CODING_AGENT_DIR="$disposable_home" PRIME_AGENT_KERNEL_VENV="$disposable_venv" \
			prime-agent package list 2>&1 || true)
		if printf '%s' "$listed_after" | grep -qF "$ROOT"; then
			fail "install cycle" "the package is still listed after removal"
		else
			pass "install cycle: the package disappears after removal"
		fi
	else
		fail "install cycle" "prime-agent package install failed:
$(tail -10 "$install_log")"
	fi

	find "$real_home" -printf '%p|%s\n' 2>/dev/null | sort > "$after"
	if diff -q "$before" "$after" >/dev/null 2>&1; then
		pass "the operator's real Prime Agent home at $real_home is unchanged (compared by path and size)"
	else
		fail "$real_home" "changed during the install cycle; the redirect did not hold:
$(diff "$before" "$after" | head -10)"
	fi

	rm -rf "$disposable_home" "$(dirname "$disposable_venv")" "$before" "$after" "$install_log"
fi

printf '\n%d check(s) passed, %d failed\n' "$checks" "$failures"
[ "$failures" -eq 0 ] || exit 1
