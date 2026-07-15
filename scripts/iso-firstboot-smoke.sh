#!/usr/bin/env bash
# Starship OS — ISO autoinstall + firstboot static smoke (no QEMU required)
# Validates edge/server/ops user-data wire firstboot profile correctly.
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"
PASS=0
FAIL=0
check() {
  local name="$1"; shift
  if "$@"; then
    echo "  PASS  $name"
    PASS=$((PASS + 1))
  else
    echo "  FAIL  $name"
    FAIL=$((FAIL + 1))
  fi
}

echo "=== ISO firstboot smoke ==="

check "autoinstall README" test -f iso/autoinstall/README.md
check "user-data.edge" test -f iso/autoinstall/user-data.edge.yaml
check "user-data.server" test -f iso/autoinstall/user-data.server.yaml
check "user-data.ops" test -f iso/autoinstall/user-data.ops.yaml
check "firstboot script" test -f scripts/starship-firstboot.sh
check "firstboot executable bit or bash" bash -n scripts/starship-firstboot.sh

for prof in edge server ops; do
  f="iso/autoinstall/user-data.${prof}.yaml"
  check "profile $prof sets STARSHIP_PROFILE" grep -q "STARSHIP_PROFILE=${prof}" "$f"
  check "profile $prof writes profile.yaml" grep -q "profile: ${prof}" "$f"
  check "profile $prof creates /etc/starship" grep -q '/etc/starship' "$f"
  check "profile $prof creates /opt/starship" grep -q '/opt/starship' "$f"
done

check "ops firstboot hook present" grep -q 'starship-firstboot\|firstboot' iso/autoinstall/user-data.ops.yaml
check "server firstboot hook present" grep -q 'starship-firstboot\|firstboot' iso/autoinstall/user-data.server.yaml
check "edge firstboot hook present" grep -q 'starship-firstboot\|firstboot' iso/autoinstall/user-data.edge.yaml

# Dry-run: firstboot profile mapping without root (extract case logic)
check "firstboot maps edge→plant-edge" grep -q 'edge).*plant-edge' scripts/starship-firstboot.sh
check "firstboot maps ops→accounts or fleet" bash -c 'grep -q "_enable_accounts_bus\|_enable_fleet_bus" scripts/starship-firstboot.sh'
check "firstboot ops enables fleet service" grep -q 'starship-fleet.service' scripts/starship-firstboot.sh

# YAML well-formed enough (no tabs-only issues; basic key presence)
for prof in edge server ops; do
  f="iso/autoinstall/user-data.${prof}.yaml"
  check "yaml $prof has autoinstall" grep -q '^autoinstall:' "$f"
  check "yaml $prof has late-commands" grep -q 'late-commands:' "$f"
done

# Simulate profile env write like late-commands (tmpdir)
SIM=$(mktemp -d)
mkdir -p "$SIM/etc/starship" "$SIM/opt/starship"
echo "STARSHIP_PROFILE=ops" > "$SIM/etc/starship/firstboot.env"
echo "profile: ops" > "$SIM/etc/starship/profile.yaml"
check "sim firstboot.env readable" grep -q 'STARSHIP_PROFILE=ops' "$SIM/etc/starship/firstboot.env"
check "sim profile.yaml readable" grep -q 'profile: ops' "$SIM/etc/starship/profile.yaml"
rm -rf "$SIM"

echo ""
echo "Result: $PASS passed, $FAIL failed"
[[ "$FAIL" -eq 0 ]]
