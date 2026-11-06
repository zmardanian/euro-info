"""The local AI analysis window: streaming brief, cited sources and evidence notes."""
from __future__ import annotations

import html
import re
import time
from pathlib import Path

from PySide6.QtCore import QThreadPool, QTimer, QUrl, Qt, Slot
from PySide6.QtGui import QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QDialog, QFileDialog, QHBoxLayout, QLabel, QMessageBox,
                               QPlainTextEdit, QProgressBar, QPushButton, QScrollArea, QTextBrowser, QVBoxLayout,
                               QWidget)

from .. import logs, settings
from ..core.i18n import ai_output_language_instruction
from ..core.quality import declared_origins, evidence_label, provenance_report, publisher_family
from ..core.reasoning import (analysis_instructions, ask_instructions, briefing_instructions, build_ask_evidence,
                              build_briefing_evidence, build_investigation_map)
from ..core.workspace import analysis_key, analysis_options, build_evidence_text, evidence_budget
from . import theme
from .common import color, run_dialog, state, tr, workspace
from .jobs import LocalSummaryJob

log = logs.get("summary")
SOURCE_LIMIT = {"efficient": 6, "balanced": 8, "deep": 12}


def analysis_html(text: str, source_count: int = 0) -> str:
    """Render the model's limited Markdown without accepting raw HTML."""
    def inline(value):
        value = html.escape(value)
        value = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", value)
        return re.sub(r"\[(\d+)\]", lambda m: (f'<a href="euroinfo://source/{m[1]}">[{m[1]}]</a>'
                                              if 1 <= int(m[1]) <= source_count else m[0]), value)

    blocks, paragraph, listing = [], [], False

    def flush():
        if paragraph:
            blocks.append("<p>" + inline(" ".join(paragraph)) + "</p>")
            paragraph.clear()

    for line in text.splitlines():
        stripped = line.strip()
        heading = re.match(r"^(?:#{1,6}\s+|(?=(?:\*\*)?\(?[1-4]\)\s))(.*)$", stripped)
        bullet = re.match(r"^(?:[-*•]\s+|\d+[.)]\s+)(.+)$", stripped)
        if (not stripped or heading or not bullet) and listing:
            blocks.append("</ul>")
            listing = False
        if heading:
            flush()
            blocks.append("<h2>" + inline(heading[1].strip("* ")) + "</h2>")
        elif bullet:
            flush()
            if not listing:
                blocks.append("<ul>")
                listing = True
            blocks.append("<li>" + inline(bullet[1]) + "</li>")
        elif stripped:
            paragraph.append(stripped)
        else:
            flush()
    if listing:
        blocks.append("</ul>")
    flush()
    return "".join(blocks)


def _muted(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("muted")
    label.setWordWrap(True)
    label.setTextFormat(Qt.TextFormat.PlainText)
    return label


class SummaryDialog(QDialog):
    """Local AI writing: one story's analysis, today's briefing (stories=...) or an answer (question=...)."""

    def __init__(self, article, parent=None, focus_article=None, news=None, stories=None, question=""):
        super().__init__(parent)
        self.mode = "briefing" if stories else ("ask" if question else "analysis")
        self.question = question
        self.workspace = getattr(parent, "workspace", None) or workspace()
        self.news = news
        self.ai_options = analysis_options(settings.text("ai_model"), settings.text("ai_profile"),
                                           settings.text("ai_keep_alive"))
        self.focus_article = focus_article if isinstance(focus_article, dict) else None
        self.setWindowTitle(tr("AI article analysis") if self.focus_article else tr("Local AI summary"))
        self.resize(960, 820)
        self.setMinimumSize(620, 480)
        self.reading_size = max(14, min(26, settings.number("ai_reading_size")))
        self._stream_text = ""
        self._rendered_text = None
        self._started = time.monotonic()
        self._running = True
        self._cache_hit = False
        self.model_name = ""
        self.summary_job = None
        self.render_timer = QTimer(self, interval=250)
        self.render_timer.timeout.connect(self.render_analysis)
        self.elapsed_timer = QTimer(self, interval=1000)
        self.elapsed_timer.timeout.connect(self.update_elapsed)
        self.elapsed_timer.start()

        articles = article if isinstance(article, list) else [article]
        if stories:
            articles = [story.lead for story in stories]
        self.articles = articles if self.mode != "analysis" else articles[:SOURCE_LIMIT[self.ai_options["profile"]]]
        is_brief = self.mode == "analysis" and self.focus_article is None and len(self.articles) > 1
        lead = self.focus_article or (self.articles[0] if self.articles else {})

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 14)
        root.setSpacing(8)
        heading = {"briefing": tr("Today's briefing"), "ask": question}.get(self.mode)
        title = QLabel(heading or (tr("Daily reader brief") if is_brief else (lead.get("localized_title") or lead.get("title", ""))))
        title.setObjectName("dialogTitle")
        title.setTextFormat(Qt.TextFormat.PlainText)
        title.setWordWrap(True)
        root.addWidget(title)
        uses_page = any(item.get("reader_text") for item in self.articles)
        root.addWidget(_muted(tr("Analysis uses text extracted from the opened publisher page and related RSS "
                                 "excerpts. Extraction may be incomplete.") if uses_page else
                              tr("Analysis uses supplied RSS headlines and excerpts, not the complete publisher "
                                 "articles.")))
        report = provenance_report(self.articles[:12])
        dependency = tr("Reporting independence is not verified.") + " " + tr("Publisher families") + \
            f": {report['families']}"
        if report["shared_attributions"]:
            dependency += " · " + tr("Shared agency attribution") + ": " + ", ".join(report["shared_attributions"])
        if report["repeated_excerpts"]:
            dependency += " · " + tr("Repeated excerpts") + f": {report['repeated_excerpts']}"
        root.addWidget(_muted(dependency))
        if self.focus_article:
            publishers = {str(item.get("source", "")).strip() for item in self.articles[1:]
                          if item.get("source") and item.get("source") != self.focus_article.get("source")}
            root.addWidget(_muted(
                tr("Compared with {reports} related reports from {publishers} other publishers in the currently "
                   "loaded feeds.").format(reports=len(self.articles) - 1, publishers=len(publishers))
                if len(self.articles) > 1 else
                tr("No closely related reports were found in the currently loaded feeds.")))

        self.output = QTextBrowser()
        self.output.setObjectName("analysisOutput")
        self.output.setOpenLinks(False)
        self.output.setOpenExternalLinks(False)
        self.output.anchorClicked.connect(self.open_evidence)
        self.output.setAccessibleName(tr("AI article analysis"))
        self.output.setPlainText(tr("Starting local AI…"))
        root.addWidget(self.output, 1)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(3)
        root.addWidget(self.progress)
        self.status_label = _muted(tr("Starting local AI…"))
        root.addWidget(self.status_label)

        sources = QHBoxLayout()
        toggle = QPushButton(f"{tr('Sources')} ({len(self.articles)})")
        toggle.setCheckable(True)
        sources.addWidget(toggle)
        self.investigation_map = build_investigation_map(self.articles, limit=min(12, len(self.articles)),
                                                         max_chars=1600)
        self.investigation_button = QPushButton(tr("Investigative connections"))
        self.investigation_button.setToolTip(tr("Headline connections are leads to review, not proof of cause."))
        self.investigation_button.setEnabled(len(self.articles) > 1)
        self.investigation_button.clicked.connect(self.show_investigation_map)
        sources.addWidget(self.investigation_button)
        sources.addStretch()
        root.addLayout(sources)
        self.source_panel = self._source_panel()
        self.source_panel.hide()
        toggle.toggled.connect(self.source_panel.setVisible)
        root.addWidget(self.source_panel)

        actions = QHBoxLayout()
        for label, delta in (("A−", -1), ("A+", 1)):
            button = QPushButton(label)
            button.setToolTip(tr("Smaller text") if delta < 0 else tr("Larger text"))
            button.clicked.connect(lambda _=False, step=delta: self.change_reading_size(step))
            actions.addWidget(button)
        self.copy_button = QPushButton(tr("Copy analysis"))
        self.copy_button.clicked.connect(self.copy_analysis)
        self.export_button = QPushButton(tr("Export analysis"))
        self.export_button.clicked.connect(self.export_analysis)
        self.retry_button = QPushButton(tr("Retry"))
        self.retry_button.clicked.connect(lambda: self.start_summary(force=True))
        for button in (self.copy_button, self.export_button, self.retry_button):
            button.setEnabled(False)
            actions.addWidget(button)
        actions.addStretch()
        close = QPushButton(tr("Close"))
        close.clicked.connect(self.reject)
        actions.addWidget(close)
        root.addLayout(actions)
        self.update_document_style()
        QShortcut(QKeySequence("Ctrl++"), self).activated.connect(lambda: self.change_reading_size(1))
        QShortcut(QKeySequence("Ctrl+-"), self).activated.connect(lambda: self.change_reading_size(-1))

        self.language_instruction = ai_output_language_instruction(state.language)
        budget = evidence_budget(self.ai_options)
        if self.mode == "briefing":
            self.prompt = f"{briefing_instructions()}\n\n{build_briefing_evidence(stories, budget)}"
        elif self.mode == "ask":
            self.prompt = f"{ask_instructions(question)}\n\n{build_ask_evidence(self.articles, budget)}"
        else:
            instruction = analysis_instructions(focus_article=self.focus_article, is_brief=is_brief,
                                                profile=self.ai_options["profile"])
            self.prompt = f"{instruction}\n\n{build_evidence_text(self.articles, self.ai_options)}"
        self.cache_key = analysis_key(self.prompt, self.language_instruction, self.ai_options)
        owner = parent
        while owner is not None and not hasattr(owner, "summary_pool"):
            owner = owner.parentWidget()
        self.summary_pool = getattr(owner, "summary_pool", None) or QThreadPool.globalInstance()
        self.start_summary()

    def _source_panel(self) -> QScrollArea:
        panel = QScrollArea()
        panel.setWidgetResizable(True)
        panel.setMaximumHeight(190)
        content = QWidget()
        layout = QVBoxLayout(content)
        for index, item in enumerate(self.articles[:20], 1):
            row = QLabel(f'<a style="color:{color("accent")};text-decoration:none" href="euroinfo://source/{index}">'
                         f'[{index}] {html.escape(item.get("source", ""))}</a> · {html.escape(item.get("title", ""))}')
            row.setWordWrap(True)
            row.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
            row.linkActivated.connect(lambda link: self.open_evidence(QUrl(link)))
            layout.addWidget(row)
            detail = tr(evidence_label(item)) + " · " + tr("Publisher family") + ": " + publisher_family(item)
            if item.get("_analysis_role"):
                detail = tr("Wider context — separate report; not corroboration") + " · " + detail
            if declared_origins(item):
                detail += " · " + tr("Agency mentioned") + ": " + ", ".join(declared_origins(item))
            layout.addWidget(_muted(detail))
        panel.setWidget(content)
        return panel

    def show_investigation_map(self):
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("Investigative connections"))
        dialog.resize(760, 540)
        layout = QVBoxLayout(dialog)
        layout.addWidget(_muted(tr("Connections are evidence leads, not proof of cause. Timeline entries show "
                                   "publication time, not necessarily event time.")))
        output = QPlainTextEdit()
        output.setReadOnly(True)
        output.setPlainText(self.investigation_map)
        layout.addWidget(output, 1)
        close = QPushButton(tr("Close"))
        close.clicked.connect(dialog.accept)
        layout.addWidget(close, 0, Qt.AlignmentFlag.AlignRight)
        run_dialog(dialog)

    def update_document_style(self):
        self.output.document().setDefaultStyleSheet(theme.analysis_css(state.mode, self.reading_size))
        self.output.setFont(QFont("Sans Serif", self.reading_size * 3 // 4))

    def change_reading_size(self, step):
        self.reading_size = max(14, min(26, self.reading_size + step))
        settings.put("ai_reading_size", self.reading_size)
        self.update_document_style()
        self._rendered_text = None
        self.render_analysis()

    def _model_suffix(self) -> str:
        return f" · {self.model_name}" if self.model_name else ""

    def update_elapsed(self):
        if self._running:
            phase = tr("Writing analysis…") if self._stream_text else tr("Starting local AI…")
            self.status_label.setText(f"{phase} · {int(time.monotonic() - self._started)} s{self._model_suffix()}")

    def start_summary(self, force=False):
        self._running, self._started = True, time.monotonic()
        self._stream_text, self._rendered_text, self._cache_hit = "", None, False
        self.output.setPlainText(tr("Starting local AI…"))
        self.progress.show()
        for button in (self.copy_button, self.export_button, self.retry_button):
            button.setEnabled(False)
        if not force:
            try:
                cached = self.workspace.get_analysis(self.cache_key)
            except Exception as exc:  # a damaged cache must not block a fresh analysis
                log.warning("Analysis cache unavailable: %s", exc)
                cached = None
            if cached:
                self._cache_hit = True
                self.summary_finished(cached[0], "")
                self.status_label.setText(tr("Saved analysis") + " · " +
                                          time.strftime("%Y-%m-%d %H:%M", time.localtime(cached[1])))
                return
        self.elapsed_timer.start()
        self.render_timer.stop()
        self.update_elapsed()
        self.summary_job = LocalSummaryJob(self.prompt, self.language_instruction,
                                           require_sections=bool(self.focus_article), options=self.ai_options)
        self.summary_job.signals.model.connect(self.model_chosen)
        self.summary_job.signals.chunk.connect(self.summary_chunk)
        self.summary_job.signals.finished.connect(self.summary_finished)
        self.summary_pool.start(self.summary_job)

    @Slot(str)
    def model_chosen(self, name):
        self.model_name = name
        self.update_elapsed()

    def render_analysis(self):
        if not self._stream_text or self._stream_text == self._rendered_text:
            return
        scroll = self.output.verticalScrollBar()
        previous = scroll.value()
        at_bottom = previous >= scroll.maximum() - 24
        self.output.setHtml(analysis_html(self._stream_text, len(self.articles)))
        self._rendered_text = self._stream_text
        scroll.setValue(scroll.maximum() if at_bottom and self._running else previous)

    @Slot(str, str)
    def summary_finished(self, summary, error):
        self.render_timer.stop()
        self.elapsed_timer.stop()
        self.progress.hide()
        if summary:
            if not self._cache_hit:
                try:
                    self.workspace.put_analysis(self.cache_key, summary)
                except Exception as exc:  # keep the result on screen even if caching fails
                    log.warning("Could not store analysis: %s", exc)
            self._stream_text = summary
            self.render_analysis()
            self.output.verticalScrollBar().setValue(0)
            self.copy_button.setEnabled(True)
            self.export_button.setEnabled(True)
            self.status_label.setText(f"{tr('Analysis complete')} · {time.monotonic() - self._started:.1f} s"
                                      f"{self._model_suffix()}")
        else:
            self.output.setPlainText(f"{tr('Local AI did not return a summary.')}\n\n{error or ''}")
            self.status_label.setText(tr("Analysis failed") + self._model_suffix())
        self._running = False
        self.retry_button.setEnabled(True)

    @Slot(str)
    def summary_chunk(self, chunk):
        self._stream_text += chunk
        if self._running and not self.render_timer.isActive():
            self.render_timer.start()

    def analysis_export_text(self):
        sources = "\n".join(f"[{index}] {item.get('source', '')} — {item.get('title', '')}\n{item.get('link', '')}"
                            for index, item in enumerate(self.articles[:20], 1))
        footer = f"\n\n{tr('Local AI model')}: {self.model_name}" if self.model_name else ""
        return self.output.toPlainText() + "\n\n" + tr("Sources") + "\n" + sources + footer

    def export_analysis(self):
        path, _ = QFileDialog.getSaveFileName(self, tr("Export analysis"), "euro-info-analysis.txt", "Text (*.txt)")
        if path:
            try:
                Path(path).write_text(self.analysis_export_text(), encoding="utf-8")
            except OSError as exc:
                QMessageBox.warning(self, tr("Export analysis"), str(exc))

    def copy_analysis(self):
        QApplication.clipboard().setText(self.analysis_export_text())
        self.status_label.setText(tr("Analysis copied"))

    def done(self, result):
        if self._running and self.summary_job is not None:
            self.summary_job.cancel()
        self._running = False
        self.render_timer.stop()
        self.elapsed_timer.stop()
        super().done(result)

    @Slot(QUrl)
    def open_evidence(self, url):
        if url.scheme() != "euroinfo" or url.host() != "source":
            return
        try:
            index = int(url.path().strip("/"))
        except (TypeError, ValueError):
            return
        if 1 <= index <= len(self.articles):
            from .reader import open_reader
            open_reader(self.articles[index - 1], self, news=self.news)
