import pathlib
import sys

ROUND = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROUND / "audit"))
sys.path.insert(0, str(ROUND.parent.parent / "src"))
