#!/usr/bin/env python3
"""Builds the Pcapy website into _site/ (standard library only).

  python3 tools/build_site.py                     # build into _site/ (run from the website repository)
  python3 -m http.server -d _site 8000            # preview at http://localhost:8000

What it does:
  * fills {{TOKENS}} and {{#if TOKEN}}..{{else}}..{{/if}} from web_docs/site.config.json
    (invalid values stop the build: store links must really be App Store / Google Play links)
  * includes partials ({{> header}}) and marks the current page in the navigation
  * copies assets and builds downloads/pcapy-wireshark-plugin.zip (+ .sha256) from plugin/
    (a copy of the plugin kept in this repository; refresh it with tools/sync_plugin.py)
"""
import argparse
import datetime
import hashlib
import html
import json
import os
import re
import shutil
import sys
import zipfile
from pathlib import Path

# This folder is a repository of its own, so nothing here may depend on files outside it.
SITE = Path(__file__).resolve().parents[1]
WEB = SITE
PLUGIN_SRC = SITE / "plugin"
PAGES = ["index", "install", "privacy", "404"]
PLUGIN_NAME = "pcapy-wireshark-plugin"

# (path inside plugin/, unix mode). Line endings are normalised by extension.
PLUGIN_FILES = [
    ("install.sh", 0o755), ("install-linux.sh", 0o755), ("install-macos.sh", 0o755), ("install-common.sh", 0o644),
    ("install.ps1", 0o644), ("install.bat", 0o644),
    ("extcap/pcapy_extcap.py", 0o755), ("extcap/pcapy_extcap.bat", 0o644),
    ("lua/pcapy.lua", 0o644), ("profile/preferences", 0o644),
]
CRLF_EXT = {".bat", ".ps1"}

PLUGIN_README = """Pcapy Wireshark plugin
======================

Installs the "Pcapy: phone" capture interface, the dissector that adds pcapy.app / pcapy.uid
fields, and a "Pcapy" Wireshark profile with an App column.

macOS / Linux:  sh install.sh
Windows:        double-click install.bat   (needs Python 3)

Then quit Wireshark completely and open it again.
Remove it again with:  sh install.sh --uninstall   (Windows: install.bat -Uninstall)

Full guide: the Install page of the Pcapy website.
"""


class ConfigError(SystemExit):
    pass


def load_config(path):
    cfg = {"appStoreUrl": "", "playStoreUrl": "", "developerName": "", "contactEmail": "", "privacyUpdated": ""}
    cfg.update(json.loads(Path(path).read_text(encoding="utf-8")))
    checks = [
        ("appStoreUrl", lambda v: v == "" or v.startswith("https://apps.apple.com/"), "must be empty or start with https://apps.apple.com/"),
        ("playStoreUrl", lambda v: v == "" or v.startswith("https://play.google.com/"), "must be empty or start with https://play.google.com/"),
        ("contactEmail", lambda v: v == "" or re.fullmatch(r"[^@\s<>\"']+@[^@\s<>\"']+\.[^@\s<>\"']+", v) is not None, "is not a valid email address"),
        ("developerName", lambda v: len(v) <= 100 and not re.search(r"[<>]", v), "must be at most 100 characters without < or >"),
        ("privacyUpdated", lambda v: re.fullmatch(r"\d{4}-\d{2}-\d{2}", v) is not None, "must look like 2026-11-08"),
    ]
    for key, ok, msg in checks:
        if not isinstance(cfg[key], str) or not ok(cfg[key]):
            raise ConfigError(f"site.config.json: {key} {msg} (got {cfg[key]!r})")
    return cfg


def context(cfg, today):
    return {
        "APP_STORE_URL": cfg["appStoreUrl"], "PLAY_STORE_URL": cfg["playStoreUrl"],
        "DEVELOPER_NAME": cfg["developerName"], "CONTACT_EMAIL": cfg["contactEmail"],
        "PRIVACY_UPDATED": cfg["privacyUpdated"], "YEAR": str(today.year),
    }


def render(text, ctx, partials, page):
    def partial(m):
        if m.group(1) not in partials:
            raise ConfigError(f"unknown partial {{{{> {m.group(1)}}}}} in {page}")
        return partials[m.group(1)]

    text = re.sub(r"\{\{>\s*(\w+)\s*\}\}", partial, text)

    def cond(m):
        key, body = m.group(1), m.group(2)
        if key not in ctx:
            raise ConfigError(f"unknown token {key} in {page}")
        yes, _, no = body.partition("{{else}}")
        return yes if ctx[key] else no

    text = re.sub(r"\{\{#if (\w+)\}\}(.*?)\{\{/if\}\}", cond, text, flags=re.S)

    def token(m):
        if m.group(1) not in ctx:
            raise ConfigError(f"unknown token {{{{{m.group(1)}}}}} in {page}")
        return html.escape(ctx[m.group(1)], quote=True)

    text = re.sub(r"\{\{(\w+)\}\}", token, text)
    if "{{" in text:
        raise ConfigError(f"unrendered template syntax left in {page}")
    # navigation: mark the current page, drop the helper attribute everywhere else
    text = text.replace(f'data-nav="{page}"', 'aria-current="page"')
    return re.sub(r' data-nav="\w+"', "", text)


def normalise(path, data):
    if Path(path).suffix in CRLF_EXT:
        return data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    return data.replace(b"\r\n", b"\n")


def build_plugin_zip(out_file):
    out_file.parent.mkdir(parents=True, exist_ok=True)
    stamp = (2026, 1, 1, 0, 0, 0)  # fixed, so the same sources always give the same zip
    with zipfile.ZipFile(out_file, "w", zipfile.ZIP_DEFLATED) as z:
        def add(name, data, mode):
            info = zipfile.ZipInfo(f"{PLUGIN_NAME}/{name}", stamp)
            info.external_attr = (0o100000 | mode) << 16  # keep the executable bits
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, data)

        add("README.txt", PLUGIN_README.encode(), 0o644)
        for rel, mode in PLUGIN_FILES:
            src = PLUGIN_SRC / rel
            if not src.is_file():
                raise ConfigError(f"plugin file missing: plugin/{rel} (restore it, or refresh with tools/sync_plugin.py)")
            add(rel, normalise(rel, src.read_bytes()), mode)
    digest = hashlib.sha256(out_file.read_bytes()).hexdigest()
    out_file.with_name(out_file.name + ".sha256").write_text(f"{digest}  {out_file.name}\n")
    return digest


def build(out=None, config=None, today=None):
    out = Path(out or SITE / "_site")
    cfg = load_config(config or WEB / "site.config.json")
    ctx = context(cfg, today or datetime.date.today())
    partials = {p.stem: p.read_text(encoding="utf-8").strip() for p in (WEB / "partials").glob("*.html")}
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    for page in PAGES:
        text = (WEB / f"{page}.html").read_text(encoding="utf-8")
        (out / f"{page}.html").write_text(render(text, ctx, partials, page), encoding="utf-8")
    shutil.copytree(WEB / "assets", out / "assets")
    build_plugin_zip(out / "downloads" / f"{PLUGIN_NAME}.zip")
    return out, cfg


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", help="output folder (default: _site)")
    ap.add_argument("--config", help="config file (default: site.config.json)")
    args = ap.parse_args()
    out, cfg = build(args.out, args.config)
    print(f"Built {out} ({sum(1 for _ in out.rglob('*') if _.is_file())} files)")
    missing = [(k, why) for k, why in [
        ("appStoreUrl", "the App Store button shows 'Coming soon'"),
        ("playStoreUrl", "the Google Play button shows 'Coming soon'"),
        ("contactEmail", "the privacy policy points to the store page for contact details"),
        ("developerName", "the footer shows 'Pcapy' instead of a name"),
    ] if not cfg[k]]
    for key, why in missing:
        msg = f"site.config.json: {key} is empty: {why}"
        print(("::warning::" if os.environ.get("GITHUB_ACTIONS") else "note: ") + msg)


if __name__ == "__main__":
    sys.exit(main())
