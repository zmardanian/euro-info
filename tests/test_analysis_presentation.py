import support  # noqa: F401  (must come first: isolates user folders)

import unittest

from euroinfo.ui.summary import analysis_html


class AnalysisPresentationTests(unittest.TestCase):
    def test_sections_bullets_and_multiline_paragraphs(self):
        rendered = analysis_html('## (1) Facts\n- Evidence [1]\n- **Important** point [2]\n\n(3) Judgment\nA considered\nassessment.', 2)
        self.assertIn('<h2>(1) Facts</h2>', rendered)
        self.assertIn('<ul><li>', rendered)
        self.assertEqual(rendered.count('<li>'), 2)
        self.assertIn('<strong>Important</strong>', rendered)
        self.assertIn('<p>A considered assessment.</p>', rendered)

    def test_source_html_and_invalid_citations_cannot_become_links(self):
        rendered = analysis_html('<img src="https://example.com/tracker"> [1] [99]', 1)
        self.assertIn('&lt;img', rendered)
        self.assertNotIn('<img', rendered)
        self.assertIn('href="euroinfo://source/1"', rendered)
        self.assertNotIn('source/99', rendered)

    def test_legacy_bold_numbered_sections_and_unfinished_stream(self):
        rendered = analysis_html('**(4) Developments**\n- An unfinished **point', 0)
        self.assertIn('<h2>(4) Developments</h2>', rendered)
        self.assertEqual(rendered.count('<ul>'), rendered.count('</ul>'))
        self.assertIn('An unfinished **point', rendered)

class DialogLifetimeTests(unittest.TestCase):
    def test_closed_modals_are_released_from_parent(self):
        from PySide6.QtCore import QCoreApplication, QEvent, QTimer
        from PySide6.QtWidgets import QApplication, QDialog, QWidget
        from euroinfo.ui.common import run_dialog
        QApplication.instance() or QApplication([])
        parent = QWidget()
        for _ in range(5):
            dialog = QDialog(parent)
            QTimer.singleShot(0, dialog.accept)
            run_dialog(dialog)
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            self.assertEqual(parent.findChildren(QDialog), [])
        parent.deleteLater()
