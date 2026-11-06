import support  # noqa: F401  (must come first: isolates user folders)

import tempfile
import time
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QEvent, QThreadPool
from PySide6.QtWidgets import QWidget

from euroinfo import settings
from euroinfo.core import feeds
from euroinfo.core.articles import article_key
from euroinfo.core.workspace import ReaderWorkspace
from euroinfo.ui import common, theme
from euroinfo.ui.cards import FeaturedStory, NewsCard
from euroinfo.ui.dialogs import NewsQualityDialog, NotesDialog, SettingsDialog, SourceDialog
from euroinfo.ui.main_window import MainWindow
from euroinfo.ui.summary import SummaryDialog


def flush():
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


class UITestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = support.application()

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.workspace = ReaderWorkspace(Path(self.folder.name) / "library.sqlite3")
        self.settings = settings.use_file(Path(self.folder.name) / "settings.conf")
        self.stack = ExitStack()
        self.stack.enter_context(patch.object(common.state, "workspace", self.workspace))
        self.stack.enter_context(patch.object(common.state, "language", "en"))
        self.stack.enter_context(patch.object(common.state, "mode", "standard"))
        self.started = self.stack.enter_context(patch.object(QThreadPool, "start"))
        self.stack.enter_context(patch("euroinfo.ui.main_window.QTimer.singleShot"))
        self.parent = QWidget()
        self.parent.workspace = self.workspace
        self.parent.utility_pool = QThreadPool(self.parent)
        self.article = {"title": "Policy announcement", "source": "Example News",
                        "link": "https://example.org/story", "summary": "A new budget was announced."}
        self.dialogs = []
        self.windows = []

    def tearDown(self):
        for dialog in self.dialogs:
            dialog.done(0)
            dialog.deleteLater()
        for window in self.windows:
            window.close()
            window.deleteLater()
        self.parent.deleteLater()
        flush()
        self.stack.close()
        settings.use_file(None)
        self.folder.cleanup()

    def window(self, news=None, width=1480):
        window = MainWindow()
        self.windows.append(window)
        window.resize(width, 900)
        if news is not None:
            window.selected_sources = {item["source"] for item in news}
            window.news = news
        window.show()
        window.set_view("latest")
        self.application.processEvents()
        return window

    def stories(self, count, source="BBC World"):
        return [dict(self.article, title=f"Policy article {index}", source=source,
                     link=f"https://example.org/{index}") for index in range(count)]


class ResearchUITests(UITestCase):
    def test_identical_analysis_reopens_without_starting_a_model(self):
        first = SummaryDialog([self.article], self.parent, focus_article=self.article)
        self.dialogs.append(first)
        self.assertEqual(self.started.call_count, 1)
        first.summary_finished("## (1) Facts\n- A budget [1].\n## (2) Assessment\nRelevant context.\n"
                               "## (3) Judgment\nA qualified judgment.\n## (4) Watch\n- The vote [1].", "")
        second = SummaryDialog([self.article], self.parent, focus_article=self.article)
        self.dialogs.append(second)
        self.assertTrue(second._cache_hit)
        self.assertFalse(second._running)
        self.assertEqual(self.started.call_count, 1)
        second.start_summary(force=True)
        self.assertEqual(self.started.call_count, 2)

    def test_changed_source_material_cannot_reuse_an_old_analysis(self):
        first = SummaryDialog([self.article], self.parent, focus_article=self.article)
        self.dialogs.append(first)
        first.summary_finished("Cached answer.", "")
        changed = dict(self.article, summary="The announced budget was revised.")
        second = SummaryDialog([changed], self.parent, focus_article=changed)
        self.dialogs.append(second)
        self.assertFalse(second._cache_hit)
        self.assertEqual(self.started.call_count, 2)

    def test_notes_are_saved(self):
        dialog = NotesDialog(self.article, self.workspace, self.parent)
        self.dialogs.append(dialog)
        dialog.notes.setPlainText("Compare the next vote.")
        dialog.tags.setText("Policy, Budget")
        dialog.read.setChecked(True)
        dialog.save()
        state = self.workspace.metadata()[article_key(self.article)]
        self.assertEqual(state["notes"], "Compare the next vote.")
        self.assertEqual(state["tags"], ["budget", "policy"])
        self.assertGreater(state["read_at"], 0)

    def test_resource_settings_roundtrip(self):
        dialog = SettingsDialog(self.parent)
        self.dialogs.append(dialog)
        dialog.profile.setCurrentIndex(dialog.profile.findData("deep"))
        dialog.retention.setCurrentIndex(dialog.retention.findData("0"))
        dialog.refresh.setCurrentIndex(dialog.refresh.findData(0))
        dialog.translation.setCurrentIndex(dialog.translation.findData("local"))
        dialog.updates.setChecked(False)
        dialog.save()
        self.assertEqual(self.settings.value("ai_profile"), "deep")
        self.assertEqual(self.settings.value("ai_keep_alive"), "0")
        self.assertEqual(self.settings.value("refresh_minutes", type=int), 0)
        self.assertEqual(self.settings.value("translation_provider"), "local")
        self.assertFalse(self.settings.value("check_updates", type=bool))

    def test_reading_preferences_do_not_shrink_the_masthead(self):
        window = self.window()
        for mode in theme.THEMES:
            window.change_display_mode(mode)
            for enlarged in (False, True):
                window.toggle_large_reading_text(enlarged)
                self.application.processEvents()
                expected = theme.sizes(window.compact, enlarged)["masthead"]
                self.assertEqual(window.page_title.font().pixelSize(), expected)

    def test_compact_layout_persists_and_lead_story_leads_the_grid(self):
        window = self.window(self.stories(8, "Example News"))
        self.assertTrue(window.compact)
        for _ in range(3):
            window.render_news()
            self.application.processEvents()
            flush()
            lead = window.news_layout.itemAtPosition(0, 0).widget()
            self.assertIsInstance(lead, FeaturedStory)
            self.assertIs(lead.parentWidget(), window.news_container)
        window.toggle_compact(False)
        self.assertFalse(self.settings.value("compact_layout", type=bool))
        window.toggle_compact(True)
        self.assertTrue(self.settings.value("compact_layout", type=bool))

    def test_technology_filters_linux_priority_and_primary_source_context(self):
        now = time.time()
        news = [dict(self.article, title="Linux kernel release", source="Phoronix", timestamp=now),
                dict(self.article, title="Gene therapy clinical trial", source="Science News", timestamp=now),
                dict(self.article, title="AI model benchmark", source="Ars Technica", timestamp=now)]
        window = self.window(news)
        window.set_filter("TECHNOLOGY")
        self.assertEqual(window.filtered_news()[0]["source"], "Phoronix")
        window.tech_topic_combo.setCurrentIndex(window.tech_topic_combo.findData("Biotech"))
        self.assertEqual([item["source"] for item in window.filtered_news()], ["Science News"])
        dialog = NewsQualityDialog(window)
        self.dialogs.append(dialog)
        self.assertEqual(len(dialog.report["sources"]), len(feeds.NEWS_SOURCES))
        self.assertTrue(dialog.report["topics"]["Linux"])
        self.assertIn(common.tr("Project publication"), dialog.output.toPlainText())

    def test_new_technology_feeds_are_added_once_and_source_choices_survive(self):
        window = self.window()
        self.assertIn("LWN", window.selected_sources)
        window.selected_sources.remove("LWN")
        self.settings.setValue("selected_sources", sorted(window.selected_sources))
        reopened = self.window()
        self.assertNotIn("LWN", reopened.selected_sources)

    def test_source_selection_can_select_technology_without_changing_geography(self):
        dialog = SourceDialog(feeds.NEWS_SOURCES, [], self.parent)
        self.dialogs.append(dialog)
        dialog.set_group("TECHNOLOGY")
        technology = [source["name"] for source in feeds.NEWS_SOURCES if source["topic"] == "TECHNOLOGY"]
        self.assertEqual(sorted(dialog.selected()), sorted(technology))
        self.assertIn("Heise", dialog.selected())
        self.assertNotIn("BBC World", dialog.selected())

    def test_analysis_prompt_exposes_evidence_limits_and_scientific_stage(self):
        dialog = SummaryDialog([dict(self.article, kind="Project publication",
                                     summary="According to Reuters, this result is preliminary.")],
                               self.parent, focus_article=self.article)
        self.dialogs.append(dialog)
        self.assertIn("origin mentions: Reuters", dialog.prompt)
        self.assertIn("publisher families", dialog.prompt)
        self.assertIn("preprints", dialog.prompt)
        self.assertIn("coverage gap", dialog.prompt)

    def test_replaced_news_widgets_are_hidden(self):
        window = self.window(self.stories(5))
        obsolete = window.news_layout.itemAtPosition(1, 0).widget()
        window.news = [dict(item, link=item["link"] + "-new") for item in window.news]
        window.render_news()
        self.assertTrue(obsolete.isHidden())


class FastPathTests(UITestCase):
    """Common actions update cards in place instead of rebuilding the page."""

    def test_starring_a_story_updates_only_its_card(self):
        window = self.window(self.stories(6))
        target = window.filtered_news()[2]
        key = article_key(target)
        card = window.cards[key]
        others = {k: c for k, c in window.cards.items() if k != key}
        window.toggle_saved_story(target)
        self.assertIs(window.cards[key], card)
        self.assertTrue(card.saved)
        self.assertEqual({k: c for k, c in window.cards.items() if k != key}, others)
        self.assertIn(key, window.saved_stories)

    def test_switching_filters_reuses_built_cards(self):
        window = self.window(self.stories(6))
        before = {key: card for key, card in window.cards.items() if isinstance(card, NewsCard)}
        window.set_filter("ECONOMY")
        window.set_filter("ALL")
        for key, card in before.items():
            self.assertIs(window.cards[key], card)

    def test_translations_update_cards_in_place(self):
        window = self.window(self.stories(4))
        key, card = next((k, c) for k, c in window.cards.items() if isinstance(c, NewsCard))
        window.apply_translations({key: ("Titlu tradus", "Rezumat tradus")})
        self.assertIs(window.cards[key], card)
        self.assertEqual(card.title.property("plainText"), "Titlu tradus")

    def test_marking_read_updates_the_card(self):
        window = self.window(self.stories(4))
        key, card = next((k, c) for k, c in window.cards.items() if isinstance(c, NewsCard))
        window.mark_read(card.article, True)
        self.assertTrue(card.read)
        self.assertFalse(card.read_tag.isHidden())

    def test_saved_view_drops_a_story_when_it_is_unsaved(self):
        news = self.stories(3)
        window = self.window(news)
        window.toggle_saved_story(news[0])
        window.set_view("saved")
        self.assertEqual(len(window.filtered_news()), 1)
        window.toggle_saved_story(news[0])
        self.assertEqual(window.filtered_news(), [])


if __name__ == "__main__":
    unittest.main()
