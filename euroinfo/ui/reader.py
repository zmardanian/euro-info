"""The in-app article reader. Qt WebEngine is imported only when a story is opened,
which keeps the main window's startup fast."""
from __future__ import annotations

from urllib.parse import quote

from PySide6.QtCore import QUrl
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QMessageBox, QProgressBar, QPushButton, QVBoxLayout
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
from PySide6.QtWebEngineWidgets import QWebEngineView
from shiboken6 import isValid

from .. import logs, paths, settings
from ..core.articles import article_key
from ..core.reasoning import build_analysis_articles
from .common import open_url, run_dialog, state, tool_button, tr, workspace

log = logs.get("reader")
_profile: QWebEngineProfile | None = None


def profile() -> QWebEngineProfile:
    """A persistent browser profile, so publisher cookie choices are remembered."""
    global _profile
    if _profile is None:
        _profile = QWebEngineProfile("euro-info")
        storage = paths.ensure(paths.data_dir() / "web")
        _profile.setPersistentStoragePath(str(storage))
        _profile.setCachePath(str(paths.ensure(paths.cache_dir() / "web")))
        _profile.setHttpCacheMaximumSize(64 * 1024 * 1024)
    return _profile


class ArticlePage(QWebEnginePage):
    """Keep navigation inside the reader and reject unsafe URL schemes."""

    def acceptNavigationRequest(self, url, navigation_type, is_main_frame):
        return url.scheme().lower() in {"http", "https"}

    def createWindow(self, window_type):
        # Publishers open many links with target="_blank": reuse this page.
        return self


def translated_url(link: str, language: str) -> str:
    return f"https://translate.google.com/translate?sl=auto&tl={language}&u={quote(link, safe='')}"


class ArticleReader(QDialog):
    def __init__(self, article: dict, parent=None, *, news: list[dict] | None = None):
        super().__init__(parent)
        self.article = article
        self.news = news
        try:
            workspace().save_story(article_key(article), article, read=True)
        except Exception as exc:  # reading must work even if the library is read-only
            log.warning("Could not record reading history: %s", exc)
        self.setWindowTitle(article.get("localized_title") or article.get("title", tr("Article reader")))
        self.resize(1080, 860)
        self.setMinimumSize(640, 480)
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(6)

        heading = QLabel(article.get("localized_title") or article.get("title", "Article"))
        heading.setObjectName("articleHeading")
        heading.setWordWrap(True)
        root.addWidget(heading)
        meta = QLabel(f"{article.get('source', '')}  ·  {article.get('time', '')}")
        meta.setObjectName("articleMeta")
        root.addWidget(meta)

        self.content = QWebEngineView()
        self.content.setPage(ArticlePage(profile(), self.content))
        self.content.setZoomFactor(1.1)
        root.addWidget(self.content, 1)
        self.loading = QProgressBar()
        self.loading.setRange(0, 100)
        self.loading.setTextVisible(False)
        self.loading.setFixedHeight(3)
        root.addWidget(self.loading)

        bar = QHBoxLayout()
        bar.setSpacing(6)
        back = tool_button("back", tr("Back"))
        forward = tool_button("forward", tr("Forward"))
        back.clicked.connect(self.content.back)
        forward.clicked.connect(self.content.forward)
        reload_page = tool_button("refresh", tr("Reload"))
        reload_page.clicked.connect(self.content.reload)
        for button in (back, forward, reload_page):
            bar.addWidget(button)
        for label, step in (("A−", -0.1), ("A+", 0.1)):
            zoom = QPushButton(label)
            zoom.setToolTip(tr("Smaller text") if step < 0 else tr("Larger text"))
            zoom.clicked.connect(lambda _=False, delta=step: self.zoom(delta))
            bar.addWidget(zoom)
        bar.addStretch()
        self.analyze_button = QPushButton(tr("AI brief"))
        self.analyze_button.setObjectName("primary")
        self.analyze_button.setToolTip(tr("Analyze the loaded publisher article"))
        self.analyze_button.setEnabled(False)
        self.analyze_button.clicked.connect(self.analyze_loaded_article)
        bar.addWidget(self.analyze_button)
        notes = QPushButton(tr("Notes and tags"))
        notes.clicked.connect(self.edit_notes)
        bar.addWidget(notes)
        external = tool_button("external", tr("Open in browser"))
        external.clicked.connect(lambda: open_url(self.content.url().toString() or article.get("link", "")))
        bar.addWidget(external)
        close = QPushButton(tr("Close"))
        close.clicked.connect(self.accept)
        bar.addWidget(close)
        root.addLayout(bar)

        self.content.loadStarted.connect(self.loading.show)
        self.content.loadProgress.connect(self.loading.setValue)
        self.content.loadFinished.connect(self._loaded)
        self._history = (back, forward)
        back.setEnabled(False)
        forward.setEnabled(False)
        QShortcut(QKeySequence("Ctrl++"), self).activated.connect(lambda: self.zoom(0.1))
        QShortcut(QKeySequence("Ctrl+-"), self).activated.connect(lambda: self.zoom(-0.1))
        QShortcut(QKeySequence("Alt+Left"), self).activated.connect(self.content.back)

        target = QUrl(article.get("link", ""))
        if target.scheme().lower() in {"http", "https"} and target.host():
            self.content.setUrl(target)
        else:
            self.content.setHtml(f"<h2>{tr('Article unavailable')}</h2>"
                                 f"<p>{tr('This story does not have a valid web address.')}</p>")

    def zoom(self, step: float):
        self.content.setZoomFactor(max(0.6, min(2.5, self.content.zoomFactor() + step)))

    def _loaded(self, ok: bool):
        self.loading.hide()
        self.analyze_button.setEnabled(ok)
        history = self.content.history()
        self._history[0].setEnabled(history.canGoBack())
        self._history[1].setEnabled(history.canGoForward())

    def edit_notes(self):
        from .dialogs import NotesDialog
        run_dialog(NotesDialog(self.article, workspace(), self))

    def analyze_loaded_article(self):
        self.analyze_button.setEnabled(False)
        script = ("(() => {const node = document.querySelector('article') || document.querySelector('[role=main]')"
                  " || document.querySelector('main') || document.body;"
                  " return node ? node.innerText.slice(0, 20000) : '';})()")
        self.content.page().runJavaScript(script, self.publisher_text_ready)

    def publisher_text_ready(self, text):
        if not isValid(self):
            return
        self.analyze_button.setEnabled(True)
        if not isinstance(text, str) or len(text.strip()) < 120:
            QMessageBox.information(self, tr("AI brief"), tr(
                "Not enough readable article text was available. Use the feed analysis or try after the page "
                "finishes loading."))
            return
        focus = dict(self.article, reader_text=text.strip()[:12000])
        current = self.content.url().toString()
        if current != self.article.get("link"):
            focus.update(link=current, title=self.content.title() or self.article.get("title", ""),
                         localized_title="", time="")
            if QUrl(current).host() != QUrl(self.article.get("link", "")).host():
                focus["source"] = QUrl(current).host()
        news = self.news if self.news is not None else []
        evidence = build_analysis_articles(focus, news, settings.text("ai_profile"))
        from .summary import SummaryDialog
        run_dialog(SummaryDialog(evidence, self, focus_article=focus, news=news))


def open_reader(article: dict, parent=None, news=None, *, translated: bool = False) -> None:
    if translated and state.language != "en" and article.get("link"):
        article = dict(article, link=translated_url(article["link"], state.language))
    run_dialog(ArticleReader(article, parent, news=news))
