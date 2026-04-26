import sys
from pathlib import Path

root = Path(__file__).parent
sys.path.insert(0, str(root / "server"))
sys.path.insert(0, str(root / "ingestion"))
