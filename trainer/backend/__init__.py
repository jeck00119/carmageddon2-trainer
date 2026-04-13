"""Backend package — Frida agent management, game detection, config I/O."""
import os
import sys

# Make the parent carma2_tools/ importable so backend modules can
# import hash_function and powerup_names without sys.path hacks.
_TOOLS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)
