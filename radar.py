"""Run the Tryout Radar command line from anywhere: python <plugin folder>/radar.py <command> ...

Your settings and data live in ~/.tryout-radar (or $TRYOUT_RADAR_HOME); `python radar.py init` creates them.
$TRYOUT_RADAR_CONFIG or --config still point at another config.toml."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
home = Path(os.environ.get("TRYOUT_RADAR_HOME") or Path.home() / ".tryout-radar").expanduser()
os.environ.setdefault("TRYOUT_RADAR_HOME", str(home))
os.environ.setdefault("TRYOUT_RADAR_CONFIG", str(home / "config.toml"))

from tryout_radar.cli import main  # noqa: E402

main()
