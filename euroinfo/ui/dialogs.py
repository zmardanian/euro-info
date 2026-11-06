"""Settings, diagnostics, sources, notes, coverage and model-download dialogs."""
from __future__ import annotations

import html
import time
from pathlib import Path

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                               QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QScrollArea, QTextBrowser,
                               QVBoxLayout, QWidget)

from .. import __version__, logs, paths, settings
from ..core import ai, feeds
from ..core.articles import article_key, reading_excerpt
from ..core.quality import (coverage_audit, declared_origins, evidence_label, freshness, provenance_report,
                            publisher_family, update_label)
from .common import open_url, tr
from .jobs import FunctionJob

log = logs.get("dialogs")


def _pool(widget) -> QThreadPool:
    owner = widget
    while owner is not None and not hasattr(owner, "utility_pool"):
        owner = owner.parentWidget() if hasattr(owner, "parentWidget") else None
    return getattr(owner, "utility_pool", None) or QThreadPool.globalInstance()


def _muted(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("muted")
    label.setWordWrap(True)
    return label


def _buttons(dialog, ok_text: str, accept, reject=None) -> QDialogButtonBox:
    box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    box.button(QDialogButtonBox.StandardButton.Ok).setText(ok_text)
    box.button(QDialogButtonBox.StandardButton.Ok).setObjectName("primary")
    box.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Cancel"))
    box.accepted.connect(accept)
    box.rejected.connect(reject or dialog.reject)
    return box


class NotesDialog(QDialog):
    def __init__(self, article, workspace, parent=None):
        super().__init__(parent)
        self.article, self.workspace = article, workspace
        self.setWindowTitle(tr("Notes and tags"))
        self.resize(640, 480)
        root = QVBoxLayout(self)
        title = QLabel(article.get("localized_title") or article.get("title", ""))
        title.setTextFormat(Qt.TextFormat.PlainText)
        title.setWordWrap(True)
        title.setObjectName("articleHeading")
        root.addWidget(title)
        current = workspace.metadata().get(article_key(article), {})
        self.notes = QPlainTextEdit()
        self.notes.setPlaceholderText(tr("Your research notes stay on this computer."))
        self.notes.setPlainText(current.get("notes", ""))
        root.addWidget(self.notes, 1)
        self.tags = QLineEdit(", ".join(current.get("tags", [])))
        self.tags.setPlaceholderText(tr("Tags, separated by commas"))
        root.addWidget(self.tags)
        self.read = QCheckBox(tr("Mark as read"))
        self.read.setChecked(bool(current.get("read_at")))
        root.addWidget(self.read)
        self._original = (self.notes.toPlainText(), self.tags.text(), self.read.isChecked())
        root.addWidget(_buttons(self, tr("Save"), self.save))

    def save(self):
        try:
            self.workspace.save_story(article_key(self.article), self.article, notes=self.notes.toPlainText(),
                                      tags=self.tags.text().split(","), read=self.read.isChecked())
            self.accept()
        except Exception as exc:  # show storage errors instead of losing the note silently
            log.warning("Could not save notes: %s", exc)
            QMessageBox.warning(self, tr("Notes and tags"), str(exc))

    def reject(self):
        if (self.notes.toPlainText(), self.tags.text(), self.read.isChecked()) != self._original:
            choice = QMessageBox.question(self, tr("Notes and tags"), tr("Discard unsaved notes?"),
                                          QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                                          QMessageBox.StandardButton.Cancel)
            if choice != QMessageBox.StandardButton.Discard:
                return
        super().reject()


TRANSLATION_CHOICES = (
    ("off", "Keep original language"),
    ("local", "Translate with local AI (private)"),
    ("google", "Translate with Google (sends headlines online)"),
)


class SettingsDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle(tr("Settings"))
        self.resize(620, 560)
        root = QVBoxLayout(self)
        root.setSpacing(10)
        heading = QLabel(tr("Settings"))
        heading.setObjectName("dialogTitle")
        root.addWidget(heading)
        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.model = QComboBox()
        self.model.addItem(tr("Automatic model"), "auto")
        selected = settings.text("ai_model")
        if selected != "auto":
            self.model.addItem(selected, selected)
            self.model.setCurrentIndex(1)
        form.addRow(tr("Local AI model"), self.model)
        self.profile = QComboBox()
        for label, code in (("Efficient", "efficient"), ("Balanced", "balanced"), ("Deeper analysis", "deep")):
            self.profile.addItem(tr(label), code)
        self.profile.setCurrentIndex(max(0, self.profile.findData(settings.text("ai_profile"))))
        form.addRow(tr("Analysis profile"), self.profile)
        self.retention = QComboBox()
        for label, code in (("Release after analysis", "0"), ("2 minutes", "2m"), ("10 minutes", "10m"),
                            ("30 minutes", "30m")):
            self.retention.addItem(tr(label), code)
        self.retention.setCurrentIndex(max(0, self.retention.findData(settings.text("ai_keep_alive"))))
        form.addRow(tr("Keep model in memory"), self.retention)
        self.stop_on_exit = QCheckBox(tr("Stop local AI when Euro Info closes, if Euro Info started it"))
        self.stop_on_exit.setChecked(settings.flag("ai_stop_on_exit"))
        form.addRow("", self.stop_on_exit)

        self.translation = QComboBox()
        for code, label in TRANSLATION_CHOICES:
            self.translation.addItem(tr(label), code)
        self.translation.setCurrentIndex(max(0, self.translation.findData(settings.text("translation_provider") or "off")))
        self.translation.setToolTip(tr("Applies when the interface language is not English."))
        form.addRow(tr("Headline translation"), self.translation)

        self.refresh = QComboBox()
        for minutes in (0, 5, 15, 30, 60):
            self.refresh.addItem(tr("Off") if not minutes else f"{minutes} {tr('minutes')}", minutes)
        self.refresh.setCurrentIndex(max(0, self.refresh.findData(settings.number("refresh_minutes"))))
        form.addRow(tr("Automatic refresh"), self.refresh)
        self.personalise = QCheckBox(tr("Rank stories using what I read and save (stays on this computer)"))
        self.personalise.setChecked(settings.flag("personalise"))
        form.addRow(tr("For you"), self.personalise)
        self.notify_watches = QCheckBox(tr("Notify me about new stories for my saved searches"))
        self.notify_watches.setChecked(settings.flag("notify_watches"))
        form.addRow(tr("Alerts"), self.notify_watches)
        self.updates = QCheckBox(tr("Check GitHub for new versions once a day"))
        self.updates.setChecked(settings.flag("check_updates"))
        form.addRow(tr("Updates"), self.updates)
        root.addLayout(form)

        clear = QPushButton(tr("Clear saved analyses"))
        clear.clicked.connect(self.clear_cache)
        root.addWidget(clear, 0, Qt.AlignmentFlag.AlignLeft)
        self.message = _muted(tr("Checking local AI…"))
        root.addWidget(self.message)
        root.addStretch()
        root.addWidget(_buttons(self, tr("Apply"), self.save))
        self.job = FunctionJob(ai.status, selected)
        self.job.signals.finished.connect(self.models_loaded)
        self.job.signals.failed.connect(self.message.setText)
        _pool(parent).start(self.job)

    def models_loaded(self, status):
        for name in status.models:
            if self.model.findData(name) < 0:
                self.model.addItem(name, name)
        if status.state == "ready":
            self.message.setText(tr("Local AI available") + f" · {tr('Automatic model')}: "
                                 f"{ai.choose_model(status.models) or '—'}")
        else:
            self.message.setText(tr(status.detail) if status.detail else tr("Local AI unavailable"))

    def clear_cache(self):
        try:
            workspace = getattr(self.parent(), "workspace", None)
            if workspace is None:
                from .common import workspace as shared
                workspace = shared()
            workspace.clear_analyses()
            self.message.setText(tr("Saved analyses cleared"))
        except Exception as exc:  # report, do not crash the dialog
            self.message.setText(str(exc))

    def save(self):
        for key, widget in (("ai_model", self.model), ("ai_profile", self.profile),
                            ("ai_keep_alive", self.retention), ("refresh_minutes", self.refresh),
                            ("translation_provider", self.translation)):
            settings.put(key, widget.currentData())
        settings.put("ai_stop_on_exit", self.stop_on_exit.isChecked())
        settings.put("check_updates", self.updates.isChecked())
        settings.put("personalise", self.personalise.isChecked())
        settings.put("notify_watches", self.notify_watches.isChecked())
        self.accept()


def diagnostics_report() -> dict:
    status = ai.status(settings.text("ai_model"))
    return {"ai": status, "feeds": feeds.feed_health_snapshot()}


class DiagnosticsDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle(tr("Diagnostics"))
        self.resize(860, 660)
        root = QVBoxLayout(self)
        self.output = QTextBrowser()
        self.output.setPlainText(tr("Checking local AI…"))
        root.addWidget(self.output, 1)
        row = QHBoxLayout()
        self.refresh_button = QPushButton(tr("Refresh"))
        self.refresh_button.clicked.connect(self.refresh)
        row.addWidget(self.refresh_button)
        copy = QPushButton(tr("Copy report"))
        copy.clicked.connect(lambda: QApplication.clipboard().setText(self.output.toPlainText()))
        row.addWidget(copy)
        folder = QPushButton(tr("Open log folder"))
        folder.clicked.connect(lambda: open_url(paths.ensure(paths.cache_dir()).as_uri()))
        row.addWidget(folder)
        row.addStretch()
        close = QPushButton(tr("Close"))
        close.clicked.connect(self.accept)
        row.addWidget(close)
        root.addLayout(row)
        self.refresh()

    def refresh(self):
        self.refresh_button.setEnabled(False)
        self.job = FunctionJob(diagnostics_report)
        self.job.signals.finished.connect(self.loaded)
        self.job.signals.failed.connect(self.output.setPlainText)
        _pool(self.parent()).start(self.job)

    def loaded(self, report):
        self.refresh_button.setEnabled(True)
        status = report["ai"]
        lines = [f"Euro Info {__version__}", "",
                 f"{tr('Settings')}: {paths.settings_file()}",
                 f"{tr('Research data')}: {paths.data_dir()}",
                 f"{tr('Log file')}: {paths.log_file()}", "",
                 f"{tr('Local AI')}: {status.state} {('· ' + status.detail) if status.detail else ''}",
                 f"{tr('Local AI model')}: {status.model or '—'}",
                 f"{tr('Installed models')}: {', '.join(status.models) or tr('None')}"]
        for item in status.running:
            lines.append(f"  {item.get('name', '')}: {item.get('size_vram', 0) / 1024 ** 3:.1f} GiB GPU")
        lines += ["", tr("News sources")]
        for source in feeds.NEWS_SOURCES:
            health = report["feeds"].get(source["name"])
            if health:
                checked = time.strftime("%H:%M:%S", time.localtime(health["checked"]))
                lines.append(f"{source['name']} · {health['articles']} {tr('stories')} · {health['seconds']:.1f}s · "
                             f"{checked} · {health['error'] or tr('Ready')}")
            else:
                lines.append(f"{source['name']} · {tr('Not checked in this session')}")
        lines += ["", tr("Saved analyses are reused for up to 48 hours only when evidence, language and AI "
                         "settings match.")]
        self.output.setPlainText("\n".join(lines))


class SourceDialog(QDialog):
    def __init__(self, sources, selected, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("News sources"))
        self.resize(720, 700)
        root = QVBoxLayout(self)
        heading = QLabel(tr("News sources"))
        heading.setObjectName("dialogTitle")
        root.addWidget(heading)
        root.addWidget(_muted(tr("Choose sources to display:")))
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Search sources…"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.filter_sources)
        root.addWidget(self.search)
        quick = QHBoxLayout()
        for label, region in (("Select all", "ALL"), ("Romania", "ROMANIA"), ("Europe", "EUROPE"),
                              ("World", "WORLD"), ("Technology", "TECHNOLOGY"), ("Clear", "NONE")):
            button = QPushButton(tr(label))
            button.clicked.connect(lambda _=False, value=region: self.set_group(value))
            quick.addWidget(button)
        root.addLayout(quick)
        self.list = QListWidget()
        self.source_items = []
        for source in sources:
            item = QListWidgetItem(
                f"{source['name']}   ·   {tr(source['region'].title())}   ·   {source['language']}\n"
                f"{tr(source.get('specialty', 'General affairs'))} · {tr(source.get('kind', 'Newsroom'))} · "
                f"{tr(source.get('access', 'Access not verified'))}")
            item.setData(Qt.ItemDataRole.UserRole, source["name"])
            item.setData(Qt.ItemDataRole.UserRole + 1, source["region"])
            item.setData(Qt.ItemDataRole.UserRole + 2, source.get("topic", ""))
            item.setToolTip(source["url"] + "\n" + tr("Publisher family") + ": " +
                            source.get("publisher_family", source["name"]))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if source["name"] in selected else Qt.CheckState.Unchecked)
            self.list.addItem(item)
            self.source_items.append(item)
        root.addWidget(self.list, 1)
        self.selection_count = _muted("")
        root.addWidget(self.selection_count)
        self.list.itemChanged.connect(self.update_selection_count)
        self.update_selection_count()
        root.addWidget(_buttons(self, tr("Apply"), self.accept))

    def update_selection_count(self):
        self.selection_count.setText(f"{len(self.selected())} / {self.list.count()} · {tr('Sources')}")

    def filter_sources(self, query):
        query = query.strip().casefold()
        for item in self.source_items:
            item.setHidden(query not in item.text().casefold())

    def set_group(self, region):
        for item in self.source_items:
            if region == "ALL" or (region != "NONE" and region in (item.data(Qt.ItemDataRole.UserRole + 1),
                                                                    item.data(Qt.ItemDataRole.UserRole + 2))):
                item.setCheckState(Qt.CheckState.Checked)
            elif region == "NONE":
                item.setCheckState(Qt.CheckState.Unchecked)

    def selected(self):
        return [self.list.item(index).data(Qt.ItemDataRole.UserRole) for index in range(self.list.count())
                if self.list.item(index).checkState() == Qt.CheckState.Checked]


class NewsQualityDialog(QDialog):
    """Coverage and source audit from the loaded evidence, without model calls."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle(tr("Coverage & sources"))
        self.resize(1000, 720)
        root = QVBoxLayout(self)
        self.scope = QComboBox()
        self.scope.addItem(tr("All enabled sources"), "enabled")
        self.scope.addItem(tr("Current view"), "view")
        self.scope.currentIndexChanged.connect(self.refresh)
        root.addWidget(self.scope, 0, Qt.AlignmentFlag.AlignLeft)
        self.output = QTextBrowser()
        self.output.setOpenExternalLinks(False)
        root.addWidget(self.output, 1)
        row = QHBoxLayout()
        for label, slot in (("Refresh report", self.refresh), ("Copy report", self.copy), ("Export report", self.export)):
            button = QPushButton(tr(label))
            button.clicked.connect(slot)
            row.addWidget(button)
        row.addStretch()
        close = QPushButton(tr("Close"))
        close.clicked.connect(self.accept)
        row.addWidget(close)
        root.addLayout(row)
        self.refresh()

    def copy(self):
        QApplication.clipboard().setText(self.output.toPlainText())

    def refresh(self):
        parent = self.parent()
        articles = (parent.filtered_news() if self.scope.currentData() == "view"
                    else [item for item in parent.news if item.get("source") in parent.selected_sources])
        self.report = coverage_audit(articles, feeds.NEWS_SOURCES, feeds.feed_health_snapshot(),
                                     parent.selected_sources, feeds.COUNTRY_TERMS)

        def esc(value):
            return html.escape(str(value))

        def mapping(values):
            return " · ".join(f"{esc(tr(key.title() if key in ('ROMANIA', 'EUROPE', 'WORLD') else key))}: {value}"
                              for key, value in sorted(values.items())) or esc(tr("None"))

        parts = [f"<h2>{esc(tr('Coverage & sources'))}</h2>", f"<p>{len(articles)} {esc(tr('stories'))}</p>",
                 f"<p>{esc(tr('This is a snapshot of loaded feeds, not a complete map of world events. Missing coverage is not evidence that nothing happened.'))}</p>"]
        for label, field in (("Source regions", "regions"), ("Languages", "languages"),
                             ("Publisher countries", "publisher_countries"), ("Country mentions", "country_mentions"),
                             ("Assessment frames", "frames"), ("Technology topics", "topics")):
            parts.append(f"<h3>{esc(tr(label))}</h3><p>{mapping(self.report[field])}</p>")
        gaps = self.report["missing_frames"] + self.report["missing_topics"]
        parts.append(f"<p><b>{esc(tr('No matching reports in this snapshot'))}:</b> "
                     f"{', '.join(esc(tr(value)) for value in gaps) or esc(tr('None'))}</p>")
        parts.append(f"<p>{esc(tr('Older report'))}: {self.report['older']} · "
                     f"{esc(tr('Unknown date'))}: {self.report['undated']}</p>")
        parts.append(f"<p>{esc(tr('Frames and topics are keyword signals. Publisher countries describe source bases, not where every event happened.'))}</p>")
        parts.append(f"<h3>{esc(tr('Source audit'))}</h3><p>{esc(tr('No automatic reliability scores. Publisher variety and agency attribution do not prove independent reporting. Access can vary by article.'))}</p>")
        headers = ("Sources", "Specialty", "Publisher family", "Country", "Evidence context", "Access", "Feed status")
        parts.append('<table cellspacing="7"><tr>' +
                     "".join(f'<th align="left">{esc(tr(label))}</th>' for label in headers) + "</tr>")
        for source in self.report["sources"]:
            status = tr("Disabled") if not source["enabled"] else (
                source["feed_error"] or (tr("Ready") if source["checked"] else tr("Not checked in this session")))
            if source["cached"]:
                status = tr("Cached fallback") + " · " + status
            status += f" · {source['loaded']} {tr('stories')}"
            values = (source["name"], tr(source.get("specialty", "General affairs")), source["publisher_family"],
                      source["country"], tr(source["kind"]), tr(source["access"]), status)
            parts.append("<tr>" + "".join(f'<td valign="top">{esc(value)}</td>' for value in values) + "</tr>")
        parts.append("</table>")
        self.output.setHtml("".join(parts))

    def export(self):
        path, _ = QFileDialog.getSaveFileName(self, tr("Export report"), "euro-info-source-audit.md", "Markdown (*.md)")
        if path:
            try:
                Path(path).write_text(self.output.toPlainText(), encoding="utf-8")
            except OSError as exc:
                QMessageBox.warning(self, tr("Export report"), str(exc))


class CoverageDialog(QDialog):
    """The source reports behind a clustered developing story."""

    def __init__(self, articles, parent=None, on_open=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Coverage timeline"))
        self.resize(720, 560)
        root = QVBoxLayout(self)
        families = len({publisher_family(item) for item in articles})
        heading = QLabel(f"{len(articles)} {tr('reports')} · {families} {tr('Publisher families')}")
        heading.setObjectName("dialogTitle")
        root.addWidget(heading)
        root.addWidget(_muted(tr("Reports are ordered newest first. Select one to open the publisher article.")))
        report = provenance_report(articles)
        note = tr("Reporting independence is not verified.")
        if report["shared_attributions"]:
            note += " · " + tr("Shared agency attribution") + ": " + ", ".join(report["shared_attributions"])
        if report["repeated_excerpts"]:
            note += " · " + tr("Repeated excerpts") + f": {report['repeated_excerpts']}"
        root.addWidget(_muted(note))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        rows = QVBoxLayout(content)
        rows.setContentsMargins(2, 2, 2, 2)
        for article in sorted(articles, key=lambda item: item.get("timestamp", 0), reverse=True):
            button = QPushButton(f"{article.get('source', 'Unknown source')}  ·  {article.get('time', '')}\n"
                                 f"{article.get('title', 'Untitled')}")
            button.setStyleSheet("text-align:left; padding:10px 12px;")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _=False, item=article: on_open(item) if on_open else None)
            rows.addWidget(button)
            context = [tr(evidence_label(article)), tr("Publisher family") + ": " + publisher_family(article),
                       tr(freshness(article)[0])]
            if declared_origins(article):
                context.append(tr("Agency mentioned") + ": " + ", ".join(declared_origins(article)))
            if update_label(article):
                context.append(tr(update_label(article)))
            detail = _muted(" · ".join(context) + "\n" + reading_excerpt(article.get("summary", ""), 400))
            detail.setTextFormat(Qt.TextFormat.PlainText)
            rows.addWidget(detail)
        rows.addStretch()
        scroll.setWidget(content)
        root.addWidget(scroll, 1)
        close = QPushButton(tr("Close"))
        close.clicked.connect(self.accept)
        root.addWidget(close, 0, Qt.AlignmentFlag.AlignRight)


class PullModelDialog(QDialog):
    """Download the recommended local model with visible progress."""

    def __init__(self, model: str, parent=None):
        super().__init__(parent)
        self.model = model
        self.cancelled = False
        self.setWindowTitle(tr("Install local AI model"))
        self.resize(520, 220)
        root = QVBoxLayout(self)
        heading = QLabel(tr("Install local AI model"))
        heading.setObjectName("dialogTitle")
        root.addWidget(heading)
        root.addWidget(_muted(tr("Downloading {model} through Ollama. It stays on this computer.").format(model=model)))
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setFixedHeight(8)
        root.addWidget(self.bar)
        self.status = _muted(tr("Starting…"))
        root.addWidget(self.status)
        row = QHBoxLayout()
        row.addStretch()
        self.button = QPushButton(tr("Cancel"))
        self.button.clicked.connect(self.cancel)
        row.addWidget(self.button)
        root.addLayout(row)
        self.job = FunctionJob(ai.pull_model, model, self._progress, lambda: self.cancelled)
        self.job.signals.progress.connect(self.show_progress)
        self.job.signals.finished.connect(self.finished)
        self.job.signals.failed.connect(self.failed)
        _pool(parent).start(self.job)

    def _progress(self, text, fraction):
        self.job.signals.progress.emit((text, fraction))

    def show_progress(self, update):
        text, fraction = update
        if fraction < 0:
            self.bar.setRange(0, 0)
        else:
            self.bar.setRange(0, 1000)
            self.bar.setValue(int(fraction * 1000))
        self.status.setText(text + (f" · {fraction * 100:.0f}%" if fraction >= 0 else ""))

    def finished(self, _result):
        self.bar.setRange(0, 1000)
        self.bar.setValue(1000)
        self.status.setText(tr("Model installed"))
        self.button.setText(tr("Close"))
        self.button.clicked.disconnect()
        self.button.clicked.connect(self.accept)

    def failed(self, message):
        self.status.setText(tr("Download failed") + ": " + message)
        self.button.setText(tr("Close"))
        self.button.clicked.disconnect()
        self.button.clicked.connect(self.reject)

    def cancel(self):
        self.cancelled = True
        self.reject()


def about(parent) -> None:
    from .. import REPOSITORY_URL
    QMessageBox.about(parent, tr("About Euro Info"), (
        f"<h2>Euro Info {__version__}</h2>"
        f"<p>{tr('European news, weather and research on your desktop.')}</p>"
        f"<p>{tr('Local AI analysis runs on this computer through Ollama.')}</p>"
        f'<p><a href="{REPOSITORY_URL}">{REPOSITORY_URL}</a></p>'))

