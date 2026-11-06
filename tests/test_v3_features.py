"""Tests for the Euro Info 3.0 improvements: one per item where it can be checked offline."""
import support  # noqa: F401  (must come first: isolates user folders)

import ast
import json
import logging
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PySide6.QtCore import QSettings

import euroinfo
from euroinfo import paths, settings
from euroinfo.core import feeds, translation, updates, widget
from euroinfo.core.articles import article_key
from euroinfo.core.workspace import export_articles

PROJECT = support.PROJECT


class MarkdownExportTests(unittest.TestCase):
    """Item 2 and 15: Markdown export works and is covered."""

    def setUp(self):
        self.article = {"title": "EU *budget* vote", "source": "Example", "time": "Mon", "link": "https://example.org/a",
                        "summary": "Ministers <b>agreed</b> a plan."}
        self.metadata = {article_key(self.article): {"notes": "Check # the vote", "tags": ["budget"]}}

    def test_markdown_export_includes_story_tags_and_notes(self):
        text = export_articles([self.article], self.metadata, article_key, "markdown")
        self.assertTrue(text.startswith("# Euro Info research export"))
        self.assertIn("## EU budget vote", text)
        self.assertIn("https://example.org/a", text)
        self.assertIn("Tags: budget", text)
        self.assertIn("Notes:\nCheck  the vote", text)
        self.assertNotIn("<b>", text)

    def test_markdown_export_of_an_empty_view_is_just_the_heading(self):
        self.assertEqual(export_articles([], {}, article_key, "markdown").strip(), "# Euro Info research export")

    def test_csv_export_still_neutralises_formulas(self):
        dangerous = dict(self.article, title="=HYPERLINK(1)")
        self.assertIn("'=HYPERLINK(1)", export_articles([dangerous], {}, article_key, "csv"))


class PhrasebookTests(unittest.TestCase):
    """Item 6: no phrase is defined twice, so no translation silently overwrites another."""

    def test_no_duplicate_keys_in_the_phrasebook_or_term_tables(self):
        for relative in ("euroinfo/core/i18n.py", "euroinfo/core/feeds.py"):
            tree = ast.parse((PROJECT / relative).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Dict):
                    keys = [key.value for key in node.keys if isinstance(key, ast.Constant)]
                    duplicates = {key for key in keys if keys.count(key) > 1}
                    self.assertFalse(duplicates, f"{relative}:{node.lineno} repeats {duplicates}")

    def test_every_interface_string_is_translated(self):
        from euroinfo.core import i18n
        used = set()
        for path in (PROJECT / "euroinfo/ui").glob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "tr" and node.args:
                    if isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                        used.add(node.args[0].value)
        missing = sorted(text for text in used if text not in i18n.UI)
        self.assertEqual(missing, [])
        for text in used:
            for language in ("fr", "de", "it", "ro", "pl", "es"):
                self.assertIn(language, i18n.UI[text], text)


class RequirementsTests(unittest.TestCase):
    """Item 5: a fresh source setup gets the GUI library."""

    def test_runtime_requirements_include_pyside6(self):
        runtime = (PROJECT / "requirements.txt").read_text()
        build = (PROJECT / "requirements-build.txt").read_text()
        self.assertRegex(runtime, r"(?m)^PySide6")
        self.assertIn("-r requirements.txt", build)
        self.assertRegex(build, r"(?m)^PySide6==")


class TranslationPrivacyTests(unittest.TestCase):
    """Item 8: nothing is sent to Google unless the reader chose Google."""

    def test_local_batches_keep_order_and_fall_back_per_item(self):
        reply = json.dumps({"items": [{"id": 2, "title": "Doi", "summary": ""},
                                      {"id": 1, "title": "Unu", "summary": "Rezumat"}]})
        with patch.object(translation.ai, "chat", return_value=reply) as chat:
            result = translation.local_translate_batch([("One", "Summary"), ("Two", ""), ("Three", "x")], "ro", "m")
        self.assertEqual(result, [("Unu", "Rezumat"), ("Doi", ""), ("Three", "x")])
        self.assertEqual(chat.call_args.args[0], "m")
        self.assertIn("Romanian", chat.call_args.args[1][0]["content"])

    def test_local_translation_never_calls_google(self):
        from euroinfo.ui.jobs import TranslationJob
        job = TranslationJob([{"title": "Hello", "link": "https://example.org/h"}], "fr", "local")
        with patch.object(translation.requests, "get") as google, \
                patch("euroinfo.ui.jobs.ai.ensure_running", return_value=["qwen3.5:9b"]), \
                patch.object(translation.ai, "chat", return_value=json.dumps(
                    {"items": [{"id": 1, "title": "Bonjour", "summary": ""}]})):
            job.run()
        google.assert_not_called()

    def test_no_provider_is_chosen_by_default(self):
        self.assertEqual(translation.PROVIDERS, ("off", "local", "google"))
        self.assertEqual(settings.DEFAULTS["translation_provider"], "")


class TranslationChoiceUITests(unittest.TestCase):
    def test_banner_offers_a_choice_and_off_sends_nothing(self):
        import test_research_ui
        case = test_research_ui.UITestCase("run")
        case.setUpClass()
        case.setUp()
        try:
            settings.put("interface_language", "ro")
            window = case.window(case.stories(3))
            self.assertFalse(window.translation_banner.isHidden())
            case.started.reset_mock()
            window.choose_translation("off")
            window.request_headline_translations()
            self.assertTrue(window.translation_banner.isHidden())
            self.assertFalse(any(call.args and call.args[0].__class__.__name__ == "TranslationJob"
                                 for call in case.started.call_args_list))
            window.choose_translation("google")
            self.assertTrue(any(call.args and call.args[0].__class__.__name__ == "TranslationJob"
                                for call in case.started.call_args_list))
        finally:
            case.tearDown()


class LoggingTests(unittest.TestCase):
    """Item 9: failures are written to ~/.cache/euro-info/euro-info.log."""

    def test_feed_failures_are_logged(self):
        from euroinfo import logs
        logs.setup()
        source = {"name": "Broken Outlet", "url": "https://example.invalid/feed", "region": "EUROPE", "language": "en"}
        session = Mock()
        session.get.side_effect = feeds.requests.RequestException("offline")
        with patch.object(feeds, "session", return_value=session):
            feeds._fetch_feed(source)
        for handler in logging.getLogger("euroinfo").handlers:
            handler.flush()
        self.assertIn("Feed Broken Outlet failed: offline", paths.log_file().read_text(encoding="utf-8"))

    def test_no_bare_silent_exception_handlers_remain(self):
        offenders = []
        for path in (PROJECT / "euroinfo").rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.ExceptHandler) and len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                    broad = node.type is None or getattr(node.type, "id", "") in ("Exception", "BaseException")
                    if broad:
                        offenders.append(f"{path.name}:{node.lineno}")
        self.assertEqual(offenders, [])


class PackagingTests(unittest.TestCase):
    """Items 7, 10, 11 and 16: release files, bundle and version."""

    def setUp(self):
        self.script = (PROJECT / "build-linux.sh").read_text(encoding="utf-8")

    def test_version_has_one_source(self):
        self.assertRegex(euroinfo.__version__, r"^\d+\.\d+\.\d+$")
        self.assertNotRegex(self.script, r'(?m)^VERSION="\d')
        self.assertIn("euroinfo/__init__.py", self.script)
        for path in (PROJECT / "euroinfo").rglob("*.py"):
            if path.name != "__init__.py" or path.parent.name != "euroinfo":
                self.assertNotIn(f'"{euroinfo.__version__}"', path.read_text(encoding="utf-8"), path)

    def test_checksums_use_plain_file_names(self):
        self.assertIn("sha256sum", self.script)
        self.assertRegex(self.script, r'cd "\$DIST"')
        self.assertNotIn("release/", re.sub(r"(?m)^#.*$", "", self.script))

    def test_bundle_leaves_font_libraries_to_the_system(self):
        self.assertRegex(self.script, r"libfontconfig")
        self.assertRegex(self.script, r"libfreetype")

    def test_release_is_an_unpacked_app_folder_with_installer(self):
        self.assertIn("tar.zst", self.script)
        self.assertTrue((PROJECT / "packaging/install.sh").is_file())

    def test_command_line_reports_the_version(self):
        result = subprocess.run([sys.executable, "-m", "euroinfo", "--version"], cwd=PROJECT,
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.stdout.strip(), f"Euro Info {euroinfo.__version__}")


class WidgetTests(unittest.TestCase):
    """Item 12: the Plasma widget runs the installed app, not a developer setup."""

    def test_widget_json_is_valid_and_uses_the_feeds(self):
        news = [{"title": "Linux 7.2 released", "link": "https://example.org/l", "source": "Phoronix",
                 "source_region": "WORLD", "time": "Mon", "image_url": ""}]
        with patch.object(feeds, "get_news", return_value=news), \
                patch.object(feeds, "get_weather", return_value={"Paris": {"temperature": 10.0}}):
            payload = widget.payload()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["articles"][0]["category"], "TECHNOLOGY")
        self.assertIn("1 stories", payload["status"])

    def test_bridge_prefers_the_installed_command(self):
        bridge = (PROJECT / "plasma-widget/package/contents/code/bridge.sh").read_text(encoding="utf-8")
        self.assertIn("--widget-json", bridge)
        self.assertIn("euro-info", bridge)
        self.assertNotIn("/var/home/", bridge)
        qml = (PROJECT / "plasma-widget/package/contents/ui/main.qml").read_text(encoding="utf-8")
        self.assertNotIn("/var/home/", qml)


class SettingsTests(unittest.TestCase):
    """Item 17: one settings file, migrated once from the 2.x location."""

    def test_legacy_settings_are_copied_once(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.dict("os.environ", {"XDG_CONFIG_HOME": directory}):
            legacy = Path(directory) / "EuroInfo" / "EuroInfo.conf"
            legacy.parent.mkdir()
            old = QSettings(str(legacy), QSettings.Format.IniFormat)
            old.setValue("interface_language", "ro")
            old.setValue("selected_sources", ["Digi24", "LWN"])
            old.sync()
            settings.use_file(None)
            try:
                store = settings.get()
                self.assertEqual(Path(store.fileName()), Path(directory) / "euro-info" / "settings.conf")
                self.assertEqual(settings.text("interface_language"), "ro")
                self.assertEqual(store.value("selected_sources"), ["Digi24", "LWN"])
                settings.put("interface_language", "de")
                settings.use_file(None)
                self.assertEqual(settings.text("interface_language"), "de")  # not copied again
            finally:
                settings.use_file(None)


class UpdateTests(unittest.TestCase):
    """Item 19: the update check compares versions correctly."""

    def test_version_comparison(self):
        self.assertTrue(updates.is_newer("3.0.1", "3.0.0"))
        self.assertTrue(updates.is_newer("v3.10.0", "3.9.9"))
        self.assertFalse(updates.is_newer("3.0.0", "3.0.0"))
        self.assertFalse(updates.is_newer("2.3.0", "3.0.0"))

    def test_latest_release_is_read_from_github(self):
        response = Mock()
        response.json.return_value = {"tag_name": "v9.0.0", "html_url": "https://github.com/x/releases/v9",
                                      "name": "Euro Info 9", "body": "Notes", "draft": False, "prerelease": False}
        with patch.object(updates.requests, "get", return_value=response) as get:
            release = updates.check()
        self.assertEqual(release.version, "9.0.0")
        self.assertIn(euroinfo.REPOSITORY, get.call_args.args[0])

    def test_up_to_date_returns_nothing(self):
        response = Mock()
        response.json.return_value = {"tag_name": f"v{euroinfo.__version__}", "html_url": ""}
        with patch.object(updates.requests, "get", return_value=response):
            self.assertIsNone(updates.check())


class StartupTests(unittest.TestCase):
    """The embedded browser loads only when a story is opened."""

    def test_main_window_does_not_load_qt_webengine(self):
        code = ("import support, sys\n"
                "from unittest.mock import patch\n"
                "app = support.application()\n"
                "from euroinfo.ui import main_window\n"
                "with patch('euroinfo.ui.main_window.QTimer.singleShot'):\n"
                "    window = main_window.MainWindow()\n"
                "print('PySide6.QtWebEngineWidgets' in sys.modules)\n")
        result = subprocess.run([sys.executable, "-c", code], cwd=PROJECT / "tests", capture_output=True,
                                text=True, timeout=120)
        self.assertEqual(result.stdout.strip().splitlines()[-1], "False", result.stderr[-2000:])


class ClassificationTests(unittest.TestCase):
    def test_source_names_do_not_decide_the_topic(self):
        story = {"title": "Comedian found guilty", "source": "France 24 Europe", "source_region": "EUROPE"}
        self.assertEqual(feeds.classify_article(story), "GENERAL")
        self.assertEqual(feeds.classify_article(dict(story, title="ECB keeps interest rates")), "ECONOMY")
        self.assertEqual(feeds.classify_article(dict(story, title="US Senate passes Ukraine aid bill")), "POLITICS")

    def test_weather_is_one_request(self):
        rows = [{"current": {"temperature_2m": index, "weather_code": 0}} for index in range(len(feeds.CITIES))]
        session = Mock()
        session.get.return_value.json.return_value = rows
        with patch.object(feeds, "session", return_value=session):
            weather = feeds.get_weather()
        session.get.assert_called_once()
        self.assertEqual(list(weather), list(feeds.CITIES))
        self.assertEqual(weather["Paris"]["temperature"], float(list(feeds.CITIES).index("Paris")))


if __name__ == "__main__":
    unittest.main()
