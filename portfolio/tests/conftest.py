import os
import sys
import tempfile
from pathlib import Path

os.environ["SITE_DATA"] = tempfile.mkdtemp(prefix="mgsite-")
os.environ["SITE_ADMIN_PASSWORD"] = "correct horse battery"
os.environ.pop("SMTP_HOST", None)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
