#!/bin/bash
#
# run_all_checks.sh - Run all functional test checks for WhisprBar
#
# This script runs automated checks to verify the system is ready for WhisprBar.
# Tests include: dependencies, configuration, audio devices, and API key.
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   WhisprBar V6 - Automated Functional Test Suite          ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}✗ Python 3 not found${NC}"
    echo "  Please install Python 3.10 or higher"
    exit 1
fi

PYTHON_CMD="python3"

# Optionally use virtual environment if it exists
if [ -d "$REPO_ROOT/.venv" ]; then
    echo -e "${GREEN}→ Using virtual environment: $REPO_ROOT/.venv${NC}"
    source "$REPO_ROOT/.venv/bin/activate"
    PYTHON_CMD="$REPO_ROOT/.venv/bin/python3"
    echo ""
fi

# Track results
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0
FAILED_REQUIRED_TESTS=0

run_check() {
    local name="$1"
    local script="$2"
    local required="$3"  # "required" or "optional"

    TOTAL_TESTS=$((TOTAL_TESTS + 1))

    echo -e "${BLUE}▶ Running: $name${NC}"
    echo -e "${BLUE}  Script: $script${NC}"
    echo ""

    if "$PYTHON_CMD" "$SCRIPT_DIR/$script"; then
        PASSED_TESTS=$((PASSED_TESTS + 1))
        echo -e "${GREEN}✓ $name: PASSED${NC}"
    else
        FAILED_TESTS=$((FAILED_TESTS + 1))
        if [ "$required" = "required" ]; then
            FAILED_REQUIRED_TESTS=$((FAILED_REQUIRED_TESTS + 1))
            echo -e "${RED}✗ $name: FAILED (Required)${NC}"
        else
            echo -e "${YELLOW}⚠ $name: FAILED (Optional)${NC}"
        fi
    fi

    echo ""
    echo "────────────────────────────────────────────────────────────"
    echo ""
}

# Run all checks
echo "Running automated checks..."
echo ""
echo "════════════════════════════════════════════════════════════"
echo ""

# Check 1: Dependencies
run_check "Dependency Check" "check_dependencies.py" "required"

# Check 2: Configuration
run_check "Configuration Check" "check_config.py" "optional"

# Check 3: Session diagnostics (X11/Wayland code paths)
run_check "Session Diagnose Check" "check_session_diagnostics.py" "optional"

# Check 4: Audio Devices
run_check "Audio Device Check" "check_audio.py" "required"

# Check 5: API Key
run_check "API Key Check" "check_api_key.py" "optional"

# Summary
echo ""
echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                      Test Summary                          ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "Total Tests:  ${TOTAL_TESTS}"
echo -e "Passed:       ${GREEN}${PASSED_TESTS}${NC}"
echo -e "Failed:       ${RED}${FAILED_TESTS}${NC}"
echo -e "Required Failed: ${RED}${FAILED_REQUIRED_TESTS}${NC}"
echo ""

if [ $FAILED_REQUIRED_TESTS -eq 0 ]; then
    echo -e "${GREEN}✓ All automated checks passed!${NC}"
    if [ $FAILED_TESTS -gt 0 ]; then
        echo -e "${YELLOW}⚠ Some optional checks failed. Review warnings above.${NC}"
    fi
    echo ""
    echo "Your system is ready to run WhisprBar V6."
    echo ""
    echo "Next steps:"
    echo "  1. Start WhisprBar: python3 whisprbar.py"
    echo "  2. Run manual tests: See FUNCTIONAL_TESTING_GUIDE.md"
    echo "  3. Create visual content: See VISUAL_CONTENT_GUIDE.md"
    echo ""
    exit 0
else
    echo -e "${RED}✗ Some checks failed${NC}"
    echo ""
    echo "Please fix the failed checks before running WhisprBar."
    echo ""
    echo "For help:"
    echo "  - Review the test output above"
    echo "  - Check FUNCTIONAL_TESTING_GUIDE.md"
    echo "  - Run individual checks for detailed output:"
    echo "      python3 tests/functional/check_dependencies.py"
    echo "      python3 tests/functional/check_config.py"
    echo "      python3 tests/functional/check_session_diagnostics.py"
    echo "      python3 tests/functional/check_audio.py"
    echo "      python3 tests/functional/check_api_key.py"
    echo ""
    exit 1
fi
