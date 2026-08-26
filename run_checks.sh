#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")"

TEST_DATA="$(mktemp -d "${TMPDIR:-/tmp}/joblooper-tests.XXXXXX")"
trap 'rm -rf -- "$TEST_DATA"' EXIT
cp -R "$PWD/examples/starter/." "$TEST_DATA/"
export JOBLOOPER_DATA_DIR="$TEST_DATA"
failed=0

check() {
  printf '\n== %s ==\n' "$1"
  shift
  "$@" || failed=1
}

check "truth integrity" python -B jl.py check
check "adversarial gates" python -B tests/test_gates.py
check "output invariants" python -B tests/test_pipeline.py
check "semantic matching" python -B tests/test_match.py
check "approval and releases" python -B tests/test_release.py
check "ground-truth context" python -B tests/test_context.py
check "ground-truth review" python -B tests/test_truth_review.py
check "pre-generation questions" python -B tests/test_preflight.py
check "protected inventory" python -B tests/test_inventory_retention.py
check "outcome learning" python -B tests/test_learning.py
check "case lifecycle" python -B tests/test_case_lifecycle.py
check "PDF extraction" python -B tests/test_pdftext.py
check "portability and onboarding" python -B tests/test_portability.py
check "single-writer safety" python -B tests/test_locking.py
check "standalone skill installation" python -B tests/test_installability.py
check "personal/public repository boundary" python -B tests/test_repo_policy.py
check "repository policy" python -B tools/check_repo.py

if [ "$failed" -eq 0 ]; then
  printf '\nALL CHECKS PASS\n'
else
  printf '\nCHECKS FAILED\n'
fi
exit "$failed"
