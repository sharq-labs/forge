import pathlib
import sys

ROUND = pathlib.Path(__file__).resolve().parent.parent
REPO = ROUND.parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))
