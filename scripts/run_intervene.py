#!/usr/bin/env python3
"""Run only the intervention phase using saved H-Neurons."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.run_full import main

if __name__ == "__main__":
    sys.argv.extend(["--phase", "intervene"])
    main()
