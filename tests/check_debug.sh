#!/usr/bin/env bash

if grep -Rn "^ *debug(" em2/; then
    echo "ERROR: debug commands found in em2/"
    exit 1
fi

if grep -Rn "^ *debug(" tests/; then
    echo "ERROR: debug commands found in tests/"
    exit 1
fi
