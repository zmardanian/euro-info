import support  # noqa: F401  (must come first: isolates user folders)

import unittest

from PySide6.QtCore import QBuffer, QIODevice, QSize
from PySide6.QtGui import QImage

from euroinfo.ui.jobs import decode_article_thumbnail, select_translation_batch


class ImageThumbnailTests(unittest.TestCase):
    def test_decoded_image_is_scaled_to_card_resolution(self):
        source = QImage(1600, 900, QImage.Format.Format_RGB32)
        source.fill(0xFF345678)
        buffer = QBuffer()
        self.assertTrue(buffer.open(QIODevice.OpenModeFlag.WriteOnly))
        self.assertTrue(source.save(buffer, "PNG"))
        thumbnail = decode_article_thumbnail(bytes(buffer.data()), QSize(320, 180))
        self.assertIsNotNone(thumbnail)
        self.assertEqual((thumbnail.width(), thumbnail.height()), (320, 180))

    def test_invalid_or_empty_image_data_is_ignored(self):
        self.assertIsNone(decode_article_thumbnail(None))
        self.assertIsNone(decode_article_thumbnail(b"not an image"))

    def test_failed_headline_translation_is_not_requeued_forever(self):
        articles = [{"link": "https://example.org/a", "title": "Headline A", "timestamp": 2}]
        attempted = set()
        self.assertEqual(select_translation_batch(articles, "ro", attempted, 40), articles)
        self.assertEqual(select_translation_batch(articles, "ro", attempted, 40), [])

    def test_newer_visible_articles_can_be_translated_without_retrying_old_ones(self):
        older = {"link": "https://example.org/a", "title": "Older", "timestamp": 1}
        newer = {"link": "https://example.org/b", "title": "Newer", "timestamp": 2}
        attempted = set()
        self.assertEqual(select_translation_batch([older, newer], "de", attempted, 1), [newer])
        self.assertEqual(select_translation_batch([older, newer], "de", attempted, 2), [older])


if __name__ == "__main__":
    unittest.main()
