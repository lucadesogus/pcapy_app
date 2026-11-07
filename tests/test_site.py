"""Tests for the Pcapy website build (web_docs/).

Beyond HTML hygiene they guard the privacy policy against drifting from the app: every Android permission
in the manifest must be explained on the policy page, and the app may not gain a third-party dependency
without the policy being revisited.
"""
import hashlib
import html.parser
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools"))
import build_site as bs  # noqa: E402

# This folder is a repository of its own. Some checks compare it with the app it documents; they run when it
# sits inside the main repository checkout and skip themselves when it is standalone.
MAIN = bs.SITE.parent
HAVE_APP = (MAIN / "app/pubspec.yaml").is_file() and (MAIN / "app/android/app/src/main/AndroidManifest.xml").is_file()
HAVE_PLUGIN_SOURCE = (MAIN / "wireshark/install.sh").is_file()
needs_app = unittest.skipUnless(HAVE_APP, "app sources not available (website repository is standalone)")
needs_plugin_source = unittest.skipUnless(HAVE_PLUGIN_SOURCE, "main repository not available (website repository is standalone)")
CSS = (bs.WEB / "assets" / "style.css").read_text()


def write_config(tmp, **over):
    cfg = {"appStoreUrl": "", "playStoreUrl": "", "developerName": "", "contactEmail": "", "privacyUpdated": "2026-11-08"}
    cfg.update(over)
    p = Path(tmp) / "config.json"
    p.write_text(json.dumps(cfg))
    return p


class Page(html.parser.HTMLParser):
    """Collects what the checks need from one HTML page."""

    def __init__(self, text):
        super().__init__()
        self.lang = None; self.title = ""; self._in_title = False
        self.meta = {}; self.headings = []; self.ids = []; self.links = []; self.resources = []
        self.imgs = []; self.styles_attr = 0; self.inline_scripts = 0; self._script_src = False; self.csp = ""
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "html": self.lang = a.get("lang")
        if tag == "title": self._in_title = True
        if tag == "meta":
            if a.get("name"): self.meta[a["name"]] = a.get("content", "")
            if (a.get("http-equiv") or "").lower() == "content-security-policy": self.csp = a.get("content", "")
        if re.fullmatch(r"h[1-6]", tag): self.headings.append(int(tag[1]))
        if "id" in a: self.ids.append(a["id"])
        if "style" in a: self.styles_attr += 1
        if tag == "a" and "href" in a: self.links.append(a["href"])
        if tag in ("link",) and "href" in a: self.resources.append(a["href"])
        if tag in ("script", "img") and "src" in a: self.resources.append(a["src"])
        if tag == "script": self._script_src = "src" in a; self.inline_scripts += 0 if "src" in a else 1
        if tag == "img": self.imgs.append(a)

    def handle_endtag(self, tag):
        if tag == "title": self._in_title = False

    def handle_data(self, data):
        if self._in_title: self.title += data


class SiteBuild(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.out, _ = bs.build(Path(cls.tmp) / "site", write_config(cls.tmp))
        cls.pages = {p: Page((cls.out / f"{p}.html").read_text()) for p in bs.PAGES}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    # ---- markup hygiene ----
    def test_every_page_has_language_title_and_viewport(self):
        for name, p in self.pages.items():
            self.assertEqual(p.lang, "en", name)
            self.assertTrue(p.title.strip(), name)
            self.assertLessEqual(len(p.title), 70, name)
            self.assertIn("width=device-width", p.meta.get("viewport", ""), name)
            if name != "404":
                self.assertGreaterEqual(len(p.meta.get("description", "")), 50, name)

    def test_one_h1_and_headings_never_skip_a_level(self):
        for name, p in self.pages.items():
            self.assertEqual(p.headings.count(1), 1, f"{name}: exactly one h1")
            for prev, cur in zip(p.headings, p.headings[1:]):
                self.assertLessEqual(cur, prev + 1, f"{name}: h{prev} followed by h{cur}")

    def test_ids_are_unique(self):
        for name, p in self.pages.items():
            self.assertEqual(len(p.ids), len(set(p.ids)), name)

    def test_every_image_has_an_alt_attribute(self):
        for name, p in self.pages.items():
            for img in p.imgs:
                self.assertIn("alt", img, f"{name}: {img}")

    def test_internal_links_and_anchors_resolve(self):
        for name, p in self.pages.items():
            for href in p.links:
                if re.match(r"(https?:|mailto:)", href):
                    continue
                target, _, frag = href.partition("#")
                path = self.out / target if target else self.out / f"{name}.html"
                self.assertTrue(path.is_file(), f"{name}: broken link {href}")
                if frag and path.suffix == ".html":
                    self.assertIn(frag, Page(path.read_text()).ids, f"{name}: missing anchor {href}")

    def test_external_links_use_https_and_noopener(self):
        for name, p in self.pages.items():
            for href in p.links:
                if href.startswith("http"):
                    self.assertTrue(href.startswith("https://"), f"{name}: {href}")
        text = (self.out / "install.html").read_text()
        for m in re.finditer(r'<a [^>]*href="https://[^"]+"[^>]*>', text):
            self.assertIn("noopener", m.group(0), m.group(0))

    # ---- privacy hygiene: the site must practise what the policy says ----
    def test_no_external_resources_and_no_inline_code(self):
        for name, p in self.pages.items():
            for r in p.resources:
                self.assertFalse(re.match(r"(https?:)?//", r), f"{name} loads {r}")
            self.assertEqual(p.styles_attr, 0, f"{name}: inline style attribute (blocked by the CSP)")
            self.assertEqual(p.inline_scripts, 0, f"{name}: inline script (blocked by the CSP)")

    def test_content_security_policy_is_strict(self):
        for name, p in self.pages.items():
            self.assertIn("default-src 'none'", p.csp, name)
            self.assertNotIn("unsafe", p.csp, name)
            self.assertNotRegex(p.csp, r"https?:", name)

    def test_assets_do_not_pull_remote_content(self):
        for f in ["style.css", "site.js"]:
            text = (bs.WEB / "assets" / f).read_text()
            self.assertNotRegex(text, r"url\(\s*['\"]?https?:|@import|fetch\(|XMLHttpRequest|https?://", f)

    def test_pages_do_not_document_adb_or_usb_connections(self):
        for name in bs.PAGES:
            text = re.sub(r"<[^>]+>", " ", (self.out / f"{name}.html").read_text()).lower()
            self.assertNotRegex(text, r"\badb\b|\busb\b", f"{name}: adb/USB connection info was removed on purpose")

    # ---- the policy must match the app ----
    @needs_app
    def test_every_android_permission_is_explained_in_the_policy(self):
        manifest = (MAIN / "app/android/app/src/main/AndroidManifest.xml").read_text()
        perms = re.findall(r'uses-permission android:name="android\.permission\.(\w+)"', manifest)
        explained = {  # permission -> text the policy must contain
            "ACCESS_NETWORK_STATE": "Network state", "FOREGROUND_SERVICE": "foreground",
            "FOREGROUND_SERVICE_SPECIAL_USE": "foreground", "POST_NOTIFICATIONS": "Notifications",
            "QUERY_ALL_PACKAGES": "installed apps",
        }
        policy = (self.out / "privacy.html").read_text()
        for perm in perms:
            self.assertIn(perm, explained, f"{perm} is new: explain it in web_docs/privacy.html, then list it here")
            self.assertIn(explained[perm], policy, perm)

    @needs_app
    def test_app_has_no_third_party_dependencies_the_policy_does_not_mention(self):
        pub = (MAIN / "app/pubspec.yaml").read_text()
        deps = re.search(r"^dependencies:\n(.*?)^dev_dependencies:", pub, re.S | re.M).group(1)
        names = set(re.findall(r"^  ([a-z_0-9]+):", deps, re.M))
        self.assertEqual(names, {"flutter", "cupertino_icons"},
                         "a new dependency changes what the privacy policy can promise: review privacy.html")
        self.assertIn("no third-party SDKs", (self.out / "privacy.html").read_text())

    def test_policy_states_the_facts_users_most_need(self):
        policy = re.sub(r"\s+", " ", (self.out / "privacy.html").read_text())
        for must in ["not encrypted", "1.1.1.1", "8.8.8.8", "Saved captures", "no accounts, no ads, no analytics"]:
            self.assertIn(must, policy, must)

    # ---- install page matches the product ----
    def test_install_page_commands_exist_in_the_download(self):
        names = zipfile.ZipFile(self.out / "downloads/pcapy-wireshark-plugin.zip").namelist()
        install = (self.out / "install.html").read_text()
        for needed in ["install.sh", "install.bat", "install.ps1"]:
            self.assertIn(needed, install)
            self.assertIn(f"{bs.PLUGIN_NAME}/{needed}", names)
        self.assertIn("downloads/pcapy-wireshark-plugin.zip", install)

    # ---- visual accessibility: WCAG contrast of every text/background pair ----
    @staticmethod
    def luminance(hex_color):
        c = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]

    def ratio(self, a, b):
        la, lb = sorted([self.luminance(a), self.luminance(b)], reverse=True)
        return (la + 0.05) / (lb + 0.05)

    def palettes(self):
        dark = dict(re.findall(r"--([a-z-]+):\s*(#[0-9A-Fa-f]{6})", CSS.split("@media (prefers-color-scheme: light)")[0]))
        light = dict(dark)
        light.update(dict(re.findall(r"--([a-z-]+):\s*(#[0-9A-Fa-f]{6})", CSS.split("@media (prefers-color-scheme: light)")[1].split("}")[0])))
        return {"dark": dark, "light": light}

    def test_text_contrast_meets_wcag_aa(self):
        pairs = [("text", "bg"), ("text", "surface"), ("text", "surface-hi"), ("text-dim", "bg"), ("text-dim", "surface"),
                 ("text-dim", "surface-hi"), ("accent-text", "bg"), ("accent-text", "surface"), ("accent-text", "surface-hi"),
                 ("on-live", "live")]
        for mode, pal in self.palettes().items():
            for fg, bg in pairs:
                r = self.ratio(pal[fg], pal[bg])
                self.assertGreaterEqual(r, 4.5, f"{mode}: {fg} on {bg} is {r:.2f}:1")

    def test_tables_can_shrink_to_phone_width(self):
        rule = re.search(r"(?m)^table\s*\{([^}]*)\}", CSS).group(1)
        self.assertNotRegex(rule, r"min-width:\s*[1-9]", "a minimum table width forces sideways scrolling on phones")
        self.assertRegex(CSS, r"th, td \{[^}]*overflow-wrap:\s*anywhere")

    def test_every_css_variable_in_use_is_defined(self):
        defined = set(self.palettes()["dark"]) | {"mono", "sans"}
        used = set(re.findall(r"var\(--([a-z-]+)\)", CSS))
        self.assertFalse(used - defined, f"undefined variables: {used - defined}")


class Config(unittest.TestCase):
    def build(self, **over):
        tmp = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, tmp, True)
        out, _ = bs.build(Path(tmp) / "site", write_config(tmp, **over))
        return out

    def test_empty_config_shows_coming_soon_and_a_store_page_contact(self):
        out = self.build()
        for page in ("index", "install"):
            text = (out / f"{page}.html").read_text()
            self.assertIn("Coming soon", text)
            self.assertNotIn("apps.apple.com", text)
        policy = (out / "privacy.html").read_text()
        self.assertNotIn("mailto:", policy)
        self.assertIn("App Store or Google Play page", policy)

    def test_filled_config_creates_links_and_a_mailto(self):
        out = self.build(appStoreUrl="https://apps.apple.com/app/id1", playStoreUrl="https://play.google.com/store/apps/details?id=x",
                         contactEmail="hello@example.com", developerName="Ada & Co")
        index = (out / "index.html").read_text()
        self.assertIn('href="https://apps.apple.com/app/id1"', index)
        self.assertIn("play.google.com/store/apps/details?id=x", index.replace("&amp;", "&"))
        self.assertNotIn("Coming soon", index)
        self.assertIn('href="mailto:hello@example.com"', (out / "privacy.html").read_text())
        self.assertIn("Ada &amp; Co", index, "values must be HTML-escaped")

    def test_no_template_syntax_survives(self):
        out = self.build(contactEmail="a@b.co")
        for page in bs.PAGES:
            self.assertNotIn("{{", (out / f"{page}.html").read_text(), page)
            self.assertNotIn("data-nav", (out / f"{page}.html").read_text(), page)

    def test_current_page_is_marked_in_the_navigation(self):
        out = self.build()
        for page, label in [("index", "Home"), ("install", "Install"), ("privacy", "Privacy")]:
            text = (out / f"{page}.html").read_text()
            self.assertEqual(text.count('aria-current="page"'), 1, page)
            self.assertRegex(text, rf'aria-current="page">{label}</a>')

    def test_unsafe_config_values_are_rejected(self):
        bad = [("appStoreUrl", "javascript:alert(1)"), ("appStoreUrl", "http://apps.apple.com/x"), ("appStoreUrl", "https://evil.example/x"),
               ("playStoreUrl", "https://apps.apple.com/x"), ("contactEmail", "not an email"), ("contactEmail", 'a"@b.co'),
               ("developerName", "<script>"), ("privacyUpdated", "yesterday")]
        for key, value in bad:
            tmp = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, tmp, True)
            with self.assertRaises(SystemExit, msg=f"{key}={value!r} must be rejected"):
                bs.build(Path(tmp) / "site", write_config(tmp, **{key: value}))

    def test_unknown_token_or_partial_fails_the_build(self):
        ctx = bs.context(bs.load_config(bs.WEB / "site.config.json"), __import__("datetime").date(2026, 1, 1))
        with self.assertRaises(SystemExit): bs.render("{{NOPE}}", ctx, {}, "x")
        with self.assertRaises(SystemExit): bs.render("{{> missing}}", ctx, {}, "x")
        with self.assertRaises(SystemExit): bs.render("{{#if NOPE}}a{{/if}}", ctx, {}, "x")


class PluginDownload(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.out, _ = bs.build(Path(cls.tmp) / "site", write_config(cls.tmp))
        cls.zip = cls.out / "downloads" / "pcapy-wireshark-plugin.zip"

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_contents_and_single_top_folder(self):
        names = zipfile.ZipFile(self.zip).namelist()
        self.assertEqual({n.split("/")[0] for n in names}, {bs.PLUGIN_NAME})
        for rel, _ in bs.PLUGIN_FILES + [("README.txt", 0)]:
            self.assertIn(f"{bs.PLUGIN_NAME}/{rel}", names)
        self.assertFalse([n for n in names if "tests" in n or "__pycache__" in n or n.endswith(".pyc")])

    def test_unix_scripts_stay_executable(self):
        # An independent list on purpose: deriving it from the build script would let a mistake there pass.
        must_be_executable = ["install.sh", "install-linux.sh", "install-macos.sh", "extcap/pcapy_extcap.py"]
        z = zipfile.ZipFile(self.zip)
        for rel in must_be_executable:
            mode = (z.getinfo(f"{bs.PLUGIN_NAME}/{rel}").external_attr >> 16) & 0o777
            self.assertEqual(mode, 0o755, f"{rel} lost its executable bit")

    def test_line_endings_per_platform(self):
        z = zipfile.ZipFile(self.zip)
        for rel, _ in bs.PLUGIN_FILES:
            data = z.read(f"{bs.PLUGIN_NAME}/{rel}")
            if rel.endswith((".bat", ".ps1")):
                self.assertNotIn(b"\n", data.replace(b"\r\n", b""), f"{rel} needs CRLF")
            else:
                self.assertNotIn(b"\r", data, f"{rel} needs LF")

    def test_checksum_file_matches(self):
        line = (self.zip.with_name(self.zip.name + ".sha256")).read_text().split()
        self.assertEqual(line[0], hashlib.sha256(self.zip.read_bytes()).hexdigest())
        self.assertEqual(line[1], self.zip.name)

    def test_build_is_reproducible(self):
        a = bs.build_plugin_zip(Path(self.tmp) / "a" / "p.zip")
        b = bs.build_plugin_zip(Path(self.tmp) / "b" / "p.zip")
        self.assertEqual(a, b)

    def test_the_downloaded_installer_really_installs_and_uninstalls(self):
        work = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, work, True)
        subprocess.run(["unzip", "-q", str(self.zip), "-d", str(work)], check=True)
        home = work / "home"; home.mkdir()
        dirs = {k: work / k for k in ("extcap", "plugins", "profile")}
        env = {"HOME": str(home), "PATH": "/usr/bin:/bin"}
        base = ["sh", str(work / bs.PLUGIN_NAME / "install.sh"), "--extcap-dir", str(dirs["extcap"]),
                "--plugins-dir", str(dirs["plugins"]), "--profile-dir", str(dirs["profile"])]
        r = subprocess.run(base, capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        ext = dirs["extcap"] / "pcapy_extcap.py"
        self.assertTrue(ext.is_file() and os.access(ext, os.X_OK))
        self.assertTrue((dirs["plugins"] / "pcapy.lua").is_file())
        self.assertIn("pcapy.app", (dirs["profile"] / "preferences").read_text())
        # the installed extcap program answers Wireshark's discovery call
        out = subprocess.run([str(ext), "--extcap-interfaces"], capture_output=True, text=True, env=env).stdout
        self.assertIn("interface {value=pcapy}", out)
        r = subprocess.run(base + ["--uninstall"], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(ext.exists() or (dirs["plugins"] / "pcapy.lua").exists())


class BundledPlugin(unittest.TestCase):
    def test_every_plugin_file_is_present_in_the_repository(self):
        for rel, _ in bs.PLUGIN_FILES:
            self.assertTrue((bs.PLUGIN_SRC / rel).is_file(), f"plugin/{rel} is missing: run tools/sync_plugin.py")

    @needs_plugin_source
    def test_bundled_copy_matches_the_main_repository(self):
        stale = [rel for rel, _ in bs.PLUGIN_FILES
                 if bs.normalise(rel, (bs.PLUGIN_SRC / rel).read_bytes()) != bs.normalise(rel, (MAIN / "wireshark" / rel).read_bytes())]
        self.assertEqual(stale, [], "the download would ship an outdated plugin: run tools/sync_plugin.py and commit")


class Workflow(unittest.TestCase):
    def setUp(self):
        self.text = (bs.SITE / ".github/workflows/pages.yml").read_text()

    def test_deploys_the_built_site_with_minimal_permissions(self):
        for needle in ["actions/checkout@v4", "actions/configure-pages@v5", "actions/upload-pages-artifact@v3",
                       "actions/deploy-pages@v4", "path: _site", "tools/build_site.py", "pages: write", "id-token: write", "contents: read"]:
            self.assertIn(needle, self.text, needle)
        self.assertNotIn("contents: write", self.text)
        self.assertLess(self.text.index("tools/build_site.py"), self.text.index("upload-pages-artifact"))

    def test_runs_the_site_tests_before_deploying(self):
        self.assertIn("tests/test_site.py", self.text)
        self.assertLess(self.text.index("test_site.py"), self.text.index("upload-pages-artifact"))

    def test_deploys_on_every_push_to_main_and_can_be_started_by_hand(self):
        self.assertRegex(self.text, r"branches:\s*\[main\]")
        self.assertIn("workflow_dispatch", self.text)
        self.assertNotIn("paths:", self.text, "this repository only contains the site: any change should deploy")
        self.assertNotIn("web_docs/", self.text, "the workflow runs at the root of the website repository")


if __name__ == "__main__":
    unittest.main()
