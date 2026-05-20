import os
import sys

# Put src/ on sys.path so tests import modules the same way the runtime does
# (main.py runs as `python src/main.py`, which puts src/ on the path and
# imports `display.X`, `input.X`, etc. with no `src.` prefix). Importing the
# same module under two names (src.input.category_store AND input.category_store)
# would create duplicate NodeKind enums that fail `is` comparisons.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
