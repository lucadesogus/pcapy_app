#!/usr/bin/env python3
"""Refreshes web_docs/plugin/ from the main repository's wireshark/ folder.

The website repository is self-contained, so it keeps its own copy of the Wireshark plugin sources (the
download on the install page is built from this copy). Run this from a checkout of the main repository
whenever the plugin changes, then commit the result:

    python3 web_docs/tools/sync_plugin.py
"""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_site as bs  # noqa: E402


def main():
    source = bs.SITE.parent / "wireshark"
    if not (source / "install.sh").is_file():
        sys.exit(f"No Wireshark plugin sources at {source}. Run this inside the main repository checkout.")
    changed = 0
    for rel, _mode in bs.PLUGIN_FILES:
        src, dst = source / rel, bs.PLUGIN_SRC / rel
        if not src.is_file():
            sys.exit(f"missing in the main repository: wireshark/{rel}")
        if not dst.is_file() or bs.normalise(rel, dst.read_bytes()) != bs.normalise(rel, src.read_bytes()):
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
            print("updated", f"plugin/{rel}")
            changed += 1
    print("plugin copy is up to date" if not changed else f"{changed} file(s) updated: commit them")


if __name__ == "__main__":
    main()
