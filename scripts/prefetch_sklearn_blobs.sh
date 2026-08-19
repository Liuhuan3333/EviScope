#!/usr/bin/env bash
# Pre-fetch all blobs needed for L2 evidence from the partial clone.
# Run once; after this, build_l2_evidence.py will be fast.
set -euo pipefail
export NO_PROXY=github.com ALL_PROXY= HTTP_PROXY= HTTPS_PROXY=

REPO=/data/disk1/Lhuan/EviScope/data/private/pr-candidates/sklearn-34412
cd "$REPO"

HEADS=(
  3e27c19185e55ecf19e705b4e14b6b8005d8ae61
  b4174c03dd7d3e597badb7f041d40679a3559aed
  8341c2029b9fd763bd908798a0886241fa2b4e22
  63b0c146dd78afd43db7066d3b539691b5d06259
)

MERGE_BASES=(
  2ead92d34fcb858e39610a81bcab1832cd1c0c1a
  bf2dfd4f4d1949cf78405af7891ec9b340b83d15
)

FILES=(
  sklearn/utils/optimize.py
  sklearn/utils/extmath.py
  sklearn/utils/tests/test_optimize.py
  sklearn/linear_model/_logistic.py
  sklearn/linear_model/_linear_loss.py
  sklearn/linear_model/tests/test_logistic.py
  sklearn/_loss/tests/test_loss.py
  doc/modules/array_api.rst
  doc/whats_new/upcoming_changes/array-api/34412.enhancement.rst
)

echo "Prefetching blobs for ${#HEADS[@]} heads x ${#FILES[@]} files..."
COUNT=0
FAIL=0
for commit in "${HEADS[@]}" "${MERGE_BASES[@]}"; do
  for f in "${FILES[@]}"; do
    if git cat-file -e "$commit:$f" 2>/dev/null; then
      git show "$commit:$f" > /dev/null 2>&1 && COUNT=$((COUNT+1)) || FAIL=$((FAIL+1))
    fi
  done
  # Also cache ls-tree output
  git ls-tree -r --name-only "$commit" > /dev/null 2>&1 && echo "ls-tree $commit OK" || echo "ls-tree $commit FAIL"
done
echo "Prefetched $COUNT blobs ($FAIL failures)"
