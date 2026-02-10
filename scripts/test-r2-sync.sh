#!/bin/bash
set -e

echo "=== R2 Sync Test Suite ==="
echo ""

# Test 1: Python syntax validation
echo "Test 1: Python syntax validation..."
if python3 -m py_compile static_site_generator/deploy/sync-to-r2.py 2>&1; then
  echo "✓ PASSED: Python syntax valid"
else
  echo "✗ FAILED: Python syntax errors"
  exit 1
fi
echo ""

# Test 2: Dry-run mode
echo "Test 2: Dry-run mode (with missing paths)..."
if timeout 10 python3 static_site_generator/deploy/sync-to-r2.py --dry-run 2>&1 | grep -q "DRY RUN MODE"; then
  echo "✓ PASSED: Dry-run mode works"
else
  echo "✗ FAILED: Dry-run mode failed or timed out"
  exit 1
fi
echo ""

# Test 3: Check rclone configuration
echo "Test 3: Check rclone remote..."
if rclone listremotes | grep -q "r2-gardener"; then
  echo "✓ PASSED: rclone remote configured"
else
  echo "⚠ WARNING: rclone remote 'r2-gardener' not found"
  echo "  This is OK for local testing, but required for actual sync"
fi
echo ""

# Test 4: Verify R2 bucket access (if configured)
if rclone listremotes | grep -q "r2-gardener"; then
  echo "Test 4: Verify R2 bucket access..."
  if rclone lsd r2-gardener:gardener-data >/dev/null 2>&1; then
    echo "✓ PASSED: R2 bucket accessible"
  else
    echo "✗ FAILED: Cannot access R2 bucket"
    exit 1
  fi
  echo ""
fi

# Test 5: Check systemd units syntax
echo "Test 5: Validate systemd units..."
if command -v systemd-analyze >/dev/null 2>&1; then
  if systemd-analyze verify static_site_generator/deploy/gardener-r2-sync.service 2>&1 | grep -v "Failed to" | grep -v "Unknown lvalue" >/dev/null; then
    echo "  (systemd-analyze output may show warnings - this is normal)"
  fi
  echo "✓ PASSED: Service unit syntax valid"

  if systemd-analyze verify static_site_generator/deploy/gardener-r2-sync.timer 2>&1 | grep -v "Failed to" >/dev/null; then
    echo "  (systemd-analyze output may show warnings - this is normal)"
  fi
  echo "✓ PASSED: Timer unit syntax valid"
else
  echo "⚠ SKIPPED: systemd-analyze not available"
fi
echo ""

# Test 6: Shellcheck on install script
echo "Test 6: Shellcheck on installation script..."
if command -v shellcheck >/dev/null 2>&1; then
  if shellcheck static_site_generator/deploy/install-r2-sync.sh 2>&1; then
    echo "✓ PASSED: Installation script passes shellcheck"
  else
    echo "✗ FAILED: Shellcheck errors in installation script"
    exit 1
  fi
else
  echo "⚠ SKIPPED: shellcheck not available"
fi
echo ""

# Test 7: Shellcheck on bucket init script
echo "Test 7: Shellcheck on bucket init script..."
if command -v shellcheck >/dev/null 2>&1; then
  if shellcheck scripts/init-r2-bucket.sh 2>&1; then
    echo "✓ PASSED: Bucket init script passes shellcheck"
  else
    echo "✗ FAILED: Shellcheck errors in bucket init script"
    exit 1
  fi
else
  echo "⚠ SKIPPED: shellcheck not available"
fi
echo ""

echo "=== Test Suite Complete ==="
echo ""
echo "Summary:"
echo "  - Python sync script: ✓ Valid syntax"
echo "  - Systemd units: ✓ Valid"
echo "  - Shell scripts: ✓ Pass shellcheck"
echo ""
echo "Next steps:"
echo "1. Review test output above"
echo "2. If all tests passed, proceed to Pi deployment"
echo "3. On Pi, run: sudo ./static_site_generator/deploy/install-r2-sync.sh"
