#!/bin/sh
# Run on the target OS. This produces a native executable and its offline index.
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
mkdir -p build data
"${CXX:-c++}" -std=c++17 -O3 -DNDEBUG -Wall -Wextra -Wpedantic src/autocorrect.cpp -o build/autocorrect.new
build/autocorrect.new --build-index-enhanced data/words.tsv build/index.new
mv build/index.new data/index.bin
mv build/autocorrect.new autocorrect
echo "Built ./autocorrect" >&2
