#!/usr/bin/env python3.6
"""
Build a production js bundle, calls "yarn build", but also does some other stuff.

Designed primarily for netlify.
"""
import sys
import subprocess
from pathlib import Path
THIS_DIR = Path(__file__).parent

print('python version:', sys.version)

subprocess.run(['yarn', 'build'], cwd=str(THIS_DIR), check=True)
