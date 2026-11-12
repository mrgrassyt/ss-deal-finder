"""Start the background monitoring service without a console window (used by autostart)."""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from ssdeal.service import main  # noqa: E402

if __name__ == "__main__":
    main(sys.argv[1:])
