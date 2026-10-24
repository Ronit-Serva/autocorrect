#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
mkdir -p build
"${CXX:-c++}" -std=c++17 -O2 -Wall -Wextra -Wpedantic tests/unit.cpp -o build/unit-tests
build/unit-tests
python3 -m unittest discover -s tests -p 'test_*.py' -v
