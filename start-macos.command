#!/bin/zsh
cd "${0:A:h}"
PYTHONPYCACHEPREFIX="${TMPDIR:-/tmp}/cord-flow-pycache" python3 run.py --source auto --open
