#!/bin/sh
# Install Sol Advisor's shipped custom-agent templates without changing Codex config.

set -eu

usage() {
  cat <<'EOF'
Usage: install-agents.sh [--target-dir PATH] [--check] [--check-role ROLE ...]

Install Sol Advisor's four current custom-agent templates into the target directory.
Normal mode also migrates only exact byte-matching historical templates where the
role remains the same. It never overwrites a modified, nonregular, or symlinked
destination.

Without --target-dir, the target is "$CODEX_HOME/agents" when CODEX_HOME is already
set, otherwise "$HOME/.codex/agents".

Options:
  --target-dir PATH  Explicit destination directory (absolute or relative).
  --check            Verify that Luna, Terra, DeepSeek, and Sol match exactly; do not create,
                     replace, or remove anything.
  --check-role ROLE  Verify only ROLE (luna, terra, deepseek, or sol); repeatable and implies
                     --check. Unknown or missing roles fail without mutation.
  --help             Show this help text.
EOF
}

fail() {
  printf '%s\n' "ERROR: $*" >&2
  exit 1
}

report_preflight_error() {
  printf '%s\n' "ERROR: $*" >&2
  preflight_failed=1
}

role_selected() {
  role=$1
  if [ -z "$check_roles" ]; then
    return 0
  fi
  case ",$check_roles," in
    *,"$role",*) return 0 ;;
    *) return 1 ;;
  esac
}

path_exists() {
  [ -e "$1" ] || [ -L "$1" ]
}

sha256_file() {
  shasum -a 256 "$1" 2>/dev/null | awk 'NF >= 1 && length($1) == 64 { print $1; exit }'
}

classify_current_or_legacy() {
  destination=$1
  template=$2
  legacy_digest=$3
  legacy_digest_alt=${4-}
  legacy_digest_alt2=${5-}

  if ! path_exists "$destination"; then
    printf '%s\n' missing
  elif [ -L "$destination" ] || [ ! -f "$destination" ]; then
    printf '%s\n' unsafe
  elif cmp -s "$template" "$destination"; then
    printf '%s\n' current
  else
    digest=$(sha256_file "$destination")
    if [ -n "$digest" ] && {
      [ "$digest" = "$legacy_digest" ] || [ "$digest" = "$legacy_digest_alt" ] || [ "$digest" = "$legacy_digest_alt2" ]
    }; then
      printf '%s\n' legacy
    elif [ -z "$digest" ]; then
      printf '%s\n' unreadable
    else
      printf '%s\n' conflict
    fi
  fi
}

same_state() {
  label=$1
  expected=$2
  actual=$3
  [ "$expected" = "$actual" ] || fail "$label changed after preflight; no further destination files were changed."
}

install_missing() {
  template=$1
  destination=$2
  staged=''

  if path_exists "$destination"; then
    fail "destination changed after preflight and will not be overwritten: $destination"
  fi

  staged=$(mktemp "$target_dir/.sol-advisor-agent.XXXXXX") || fail "could not stage template for installation: $destination"
  if ! cp "$template" "$staged"; then
    rm -f "$staged"
    fail "could not stage template for installation: $destination"
  fi

  if ! ln "$staged" "$destination"; then
    rm -f "$staged"
    fail "destination changed after preflight and will not be overwritten: $destination"
  fi

  rm -f "$staged" || fail "could not remove staged template after installation: $staged"
  printf '%s\n' "INSTALLED: $destination"
}

replace_legacy_role() {
  label=$1
  template=$2
  destination=$3
  legacy_digest=$4
  legacy_digest_alt=${5-}
  legacy_digest_alt2=${6-}
  staged=''

  [ "$(classify_current_or_legacy "$destination" "$template" "$legacy_digest" "$legacy_digest_alt" "$legacy_digest_alt2")" = legacy ] ||
    fail "legacy $label destination changed after preflight and will not be replaced: $destination"

  staged=$(mktemp "$target_dir/.sol-advisor-agent.XXXXXX") || fail "could not stage migrated $label template: $destination"
  if ! cp "$template" "$staged"; then
    rm -f "$staged"
    fail "could not stage migrated $label template: $destination"
  fi

  [ "$(classify_current_or_legacy "$destination" "$template" "$legacy_digest" "$legacy_digest_alt" "$legacy_digest_alt2")" = legacy ] || {
    rm -f "$staged"
    fail "legacy $label destination changed after preflight and will not be replaced: $destination"
  }

  if ! mv -f "$staged" "$destination"; then
    rm -f "$staged"
    fail "could not replace exact legacy $label template: $destination"
  fi

  printf '%s\n' "MIGRATED: $destination"
}

script_dir=$(CDPATH= cd "$(dirname "$0")" && pwd) || exit 1
template_dir=$script_dir/../agents

if [ -n "${CODEX_HOME-}" ]; then
  target_dir=$CODEX_HOME/agents
else
  [ -n "${HOME-}" ] || fail "HOME is unset and CODEX_HOME was not supplied; pass --target-dir explicitly."
  target_dir=$HOME/.codex/agents
fi

check_only=0
check_roles=''

while [ "$#" -gt 0 ]; do
  case "$1" in
    --target-dir)
      [ "$#" -ge 2 ] || fail "--target-dir requires a path."
      [ -n "$2" ] || fail "--target-dir requires a non-empty path."
      case "$2" in
        --*) fail "--target-dir path must be explicit; prefix an option-like relative name with ./ or use an absolute path." ;;
      esac
      target_dir=$2
      shift 2
      ;;
    --check)
      check_only=1
      shift
      ;;
    --check-role)
      [ "$#" -ge 2 ] || fail "--check-role requires a role: luna, terra, deepseek, or sol."
      case "$2" in
        luna|terra|deepseek|sol) ;;
        *) fail "unknown --check-role '$2'; expected luna, terra, deepseek, or sol." ;;
      esac
      check_only=1
      check_roles=$check_roles$2,
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      fail "unknown argument: $1 (run with --help for usage)."
      ;;
  esac
done

case "$target_dir" in
  /*) ;;
  *) target_dir=$(pwd -P)/$target_dir ;;
esac

case "$target_dir" in
  /|//) fail "refusing to use the filesystem root as an agent target directory." ;;
esac

terra_file=sol-advisor-terra-implementer.toml
luna_file=sol-advisor-luna-implementer.toml
deepseek_file=sol-advisor-deepseek-implementer.toml
sol_file=sol-advisor-sol-reviewer.toml
terra_template=$template_dir/$terra_file
luna_template=$template_dir/$luna_file
deepseek_template=$template_dir/$deepseek_file
sol_template=$template_dir/$sol_file
terra_destination=$target_dir/$terra_file
luna_destination=$target_dir/$luna_file
deepseek_destination=$target_dir/$deepseek_file
sol_destination=$target_dir/$sol_file

# Immutable historical byte digests, calculated from the shipped v0.2.0 role files:
# git show bbc3dc1:plugins/sol-advisor/agents/sol-advisor-luna-implementer.toml | shasum -a 256
# git show bbc3dc1:plugins/sol-advisor/agents/sol-advisor-terra-implementer.toml | shasum -a 256
legacy_luna_sha256=fba1b42849d93737e83b094a2ab0b1611f87ac37db7438c8bbdf581f0813f8eb
legacy_terra_sha256=4425a8c1f21ce8c6af93f96adc253bbc33ea301f1389b3fa8ce350be08584eca
# Immutable v0.4.0 Terra digest, calculated from the shipped base profile.
legacy_terra_v040_sha256=06c318e5e93f37452635906394e6ea69fb6a65ba9e6ad7172d37b444e0dc871d
# Immutable v0.5.0 role digests, calculated from the shipped base profiles.
legacy_luna_v050_sha256=5cfaf77f14757074ca5d3cfecd0b8204c91dc14eff8d6119985c64416ddf4853
legacy_terra_v050_sha256=dc329fe87f6f6610c13157ec16432f91c79cf5a541ee3e7448f6afb165dd18ce

for template in "$luna_template" "$terra_template" "$deepseek_template" "$sol_template"; do
  [ -f "$template" ] && [ ! -L "$template" ] ||
    fail "shipped template is missing or not a regular file: $template"
done

preflight_failed=0
if path_exists "$target_dir"; then
  if [ -L "$target_dir" ] || [ ! -d "$target_dir" ]; then
    report_preflight_error "target directory is not a real directory: $target_dir"
  fi
fi

luna_state=$(classify_current_or_legacy "$luna_destination" "$luna_template" "$legacy_luna_sha256" "$legacy_luna_v050_sha256")
terra_state=$(classify_current_or_legacy "$terra_destination" "$terra_template" "$legacy_terra_sha256" "$legacy_terra_v040_sha256" "$legacy_terra_v050_sha256")
deepseek_state=$(classify_current_or_legacy "$deepseek_destination" "$deepseek_template" '' '')
sol_state=$(classify_current_or_legacy "$sol_destination" "$sol_template" '' '')

if [ "$check_only" -eq 1 ]; then
  if role_selected luna; then
    [ "$luna_state" = current ] ||
      report_preflight_error "Luna template is $luna_state, not the current exact file: $luna_destination"
  fi
  if role_selected terra; then
    [ "$terra_state" = current ] ||
      report_preflight_error "Terra template is $terra_state, not the current exact file: $terra_destination"
  fi
  if role_selected deepseek; then
    [ "$deepseek_state" = current ] ||
      report_preflight_error "DeepSeek template is $deepseek_state, not the current exact file: $deepseek_destination"
  fi
  if role_selected sol; then
    [ "$sol_state" = current ] ||
      report_preflight_error "Sol template is $sol_state, not the current exact file: $sol_destination"
  fi
else
  case "$luna_state" in
    current|legacy|missing) ;;
    *) report_preflight_error "Luna destination is $luna_state and will not be replaced: $luna_destination" ;;
  esac
  case "$terra_state" in
    current|legacy|missing) ;;
    *) report_preflight_error "Terra destination is $terra_state and will not be replaced: $terra_destination" ;;
  esac
  case "$deepseek_state" in
    current|missing) ;;
    *) report_preflight_error "DeepSeek destination is $deepseek_state and will not be replaced: $deepseek_destination" ;;
  esac
  case "$sol_state" in
    current|missing) ;;
    *) report_preflight_error "Sol destination is $sol_state and will not be replaced: $sol_destination" ;;
  esac
fi

[ "$preflight_failed" -eq 0 ] || exit 1

if [ "$check_only" -eq 1 ]; then
  if [ -n "$check_roles" ]; then
    printf '%s\n' "CHECK PASSED: selected role templates exactly match $template_dir."
  else
    printf '%s\n' "CHECK PASSED: Luna, Terra, DeepSeek, and Sol exactly match $template_dir."
  fi
  exit 0
fi

if [ ! -d "$target_dir" ]; then
  mkdir -p "$target_dir" || fail "could not create target directory: $target_dir"
fi
[ -d "$target_dir" ] && [ ! -L "$target_dir" ] ||
  fail "target directory changed after preflight: $target_dir"

same_state Luna "$luna_state" "$(classify_current_or_legacy "$luna_destination" "$luna_template" "$legacy_luna_sha256" "$legacy_luna_v050_sha256")"
same_state Terra "$terra_state" "$(classify_current_or_legacy "$terra_destination" "$terra_template" "$legacy_terra_sha256" "$legacy_terra_v040_sha256" "$legacy_terra_v050_sha256")"
same_state DeepSeek "$deepseek_state" "$(classify_current_or_legacy "$deepseek_destination" "$deepseek_template" '' '')"
same_state Sol "$sol_state" "$(classify_current_or_legacy "$sol_destination" "$sol_template" '' '')"

case "$luna_state" in
  missing) install_missing "$luna_template" "$luna_destination" ;;
  legacy) replace_legacy_role Luna "$luna_template" "$luna_destination" "$legacy_luna_sha256" "$legacy_luna_v050_sha256" ;;
  current) printf '%s\n' "ALREADY CURRENT: $luna_destination" ;;
esac

case "$terra_state" in
  missing) install_missing "$terra_template" "$terra_destination" ;;
  legacy) replace_legacy_role Terra "$terra_template" "$terra_destination" "$legacy_terra_sha256" "$legacy_terra_v040_sha256" "$legacy_terra_v050_sha256" ;;
  current) printf '%s\n' "ALREADY CURRENT: $terra_destination" ;;
esac

case "$deepseek_state" in
  missing) install_missing "$deepseek_template" "$deepseek_destination" ;;
  current) printf '%s\n' "ALREADY CURRENT: $deepseek_destination" ;;
esac

case "$sol_state" in
  missing) install_missing "$sol_template" "$sol_destination" ;;
  current) printf '%s\n' "ALREADY CURRENT: $sol_destination" ;;
esac

[ "$(classify_current_or_legacy "$luna_destination" "$luna_template" "$legacy_luna_sha256" "$legacy_luna_v050_sha256")" = current ] ||
  fail "post-install exactness check failed: $luna_destination"
[ "$(classify_current_or_legacy "$terra_destination" "$terra_template" "$legacy_terra_sha256" "$legacy_terra_v040_sha256" "$legacy_terra_v050_sha256")" = current ] ||
  fail "post-install exactness check failed: $terra_destination"
[ "$(classify_current_or_legacy "$deepseek_destination" "$deepseek_template" '' '')" = current ] ||
  fail "post-install exactness check failed: $deepseek_destination"
[ "$(classify_current_or_legacy "$sol_destination" "$sol_template" '' '')" = current ] ||
  fail "post-install exactness check failed: $sol_destination"

printf '%s\n' "INSTALL PASSED: Luna, Terra, DeepSeek, and Sol exactly match $template_dir."
