#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
subprocess.run([sys.executable, str(BASE_DIR / "app_integrator.py"), "--settings"] + sys.argv[1:])
