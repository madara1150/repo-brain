"""`main.py --sync`: press "Update" without the window."""
import sys

from .config import index_path, load_config, save_config
from .store import Store
from .sync import Syncer


def sync_cli() -> int:
    cfg = load_config()
    store = Store(index_path())
    syncer = Syncer(cfg, store, progress=lambda msg, frac=None: msg and print(msg, file=sys.stderr))
    results = syncer.run()
    if syncer.team_changed:
        save_config(cfg)
        print("repository list updated from the team list", file=sys.stderr)
    failed = False
    for r in results:
        line = f"{r.repo}: {r.mode} {r.old_sha[:8]}->{r.new_sha[:8]} ({r.changed} files)"
        if r.error:
            line += f" ERROR {r.error}"
            failed = True
        print(line)
    return 1 if failed else 0
