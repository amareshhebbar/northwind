import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["LLM_FORCE"] = "mock:test"
os.environ["SUPPORT_FORCE_STORE"] = "json"
os.environ.setdefault("QDRANT_URL", "local")
