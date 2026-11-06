import support  # noqa: F401  (must come first: isolates user folders)

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from euroinfo.core import articles


class SavedStoriesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "saved-stories.json"
        self.patch = patch.object(articles, "saved_stories_file", return_value=self.path)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def test_saved_articles_round_trip(self):
        article = {"title": "European policy update", "link": "https://example.org/story/1",
                   "source": "Example News", "timestamp": 1700000000}
        key = articles.article_key(article)
        articles.store_saved_stories({key: article})
        self.assertEqual(articles.load_saved_stories(), {key: article})
        self.assertEqual([path.name for path in Path(self.temp.name).iterdir()], ["saved-stories.json"])

    def test_translations_and_page_text_are_not_saved(self):
        article = {"title": "Headline", "link": "https://example.org/a", "localized_title": "Titlu",
                   "localized_summary": "Rezumat", "reader_text": "Full page", "_analysis_role": "context"}
        articles.store_saved_stories({articles.article_key(article): article})
        stored = next(iter(articles.load_saved_stories().values()))
        self.assertEqual(stored, {"title": "Headline", "link": "https://example.org/a"})

    def test_invalid_saved_file_is_recovered_as_empty(self):
        self.path.write_text("not json", encoding="utf-8")
        self.assertEqual(articles.load_saved_stories(), {})

    def test_articles_without_titles_are_ignored(self):
        self.path.write_text('[{"link":"https://example.org"}]', encoding="utf-8")
        self.assertEqual(articles.load_saved_stories(), {})

    def test_article_key_is_stable_across_versions(self):
        # The research library is keyed by this value; changing it would orphan notes.
        self.assertEqual(articles.article_key({"link": "https://example.org/story"}), "89b07b87bba2e0ccf469a0de")


if __name__ == "__main__":
    unittest.main()
