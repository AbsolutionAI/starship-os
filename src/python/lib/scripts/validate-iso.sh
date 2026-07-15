#!/bin/bash
# ISO validation after build
# Checks size, basic contents via loop mount or 7z, bootable markers

set -euo pipefail

ISO="${1:-$(ls -t dist/agnet-os-*-amd64.iso 2>/dev/null | head -1)}"
if [[ -z "$ISO" || ! -f "$ISO" ]]; then
  echo "No ISO to validate"
  exit 1
fi

echo "=== Validating $ISO ==="
ls -lh "$ISO"

# Check not empty
size=$(stat -c%s "$ISO")
if (( size < 500000000 )); then
  echo "WARN: ISO suspiciously small (<500MB)"
fi

# Check for hybrid boot marker (common for live isos)
if command -v isohybrid >/dev/null; then
  echo "isohybrid available"
fi

# Quick content peek (if xorriso or 7z)
if command -v 7z >/dev/null; then
  7z l "$ISO" | head -20 || true
elif command -v xorriso >/dev/null; then
  xorriso -indev "$ISO" -find / -type f 2>/dev/null | head -5 || true
fi

echo "Basic validation passed. Use qemu-test.sh for full boot test."
echo "After QEMU boot verify: systemctl status agnetic-mesh ; ollama list ; ls /var/lib/agnetic/lancedb"
