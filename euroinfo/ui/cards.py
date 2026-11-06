"""Story cards. Each card updates its own state (saved, read, translated, image)
in place, so a click never rebuilds the whole page."""
from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QMenu, QPushButton, QSizePolicy, QVBoxLayout

from ..core.articles import reading_excerpt
from ..core.feeds import classify_article
from ..core.sources import SOURCE_BY_NAME
from ..core.quality import evidence_label, freshness, publisher_family, update_label
from .common import age, explain, icon, state, tool_button, tr


def _label(text: str, name: str, *, wrap: bool = False) -> QLabel:
    label = QLabel(text)
    label.setObjectName(name)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(wrap)
    label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    return label


def rounded(image, size: QSize, radius: float = 8.0) -> QPixmap:
    """Crop to fill the slot and round the corners, at the screen's pixel ratio."""
    application = QApplication.instance()
    ratio = max(1.0, application.devicePixelRatio() if application else 1.0)
    pixels = QSize(round(size.width() * ratio), round(size.height() * ratio))
    source = QPixmap.fromImage(image).scaled(pixels, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                             Qt.TransformationMode.SmoothTransformation)
    result = QPixmap(pixels)
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, pixels.width(), pixels.height()), radius * ratio, radius * ratio)
    painter.setClipPath(path)
    painter.drawPixmap((pixels.width() - source.width()) // 2, (pixels.height() - source.height()) // 2, source)
    painter.end()
    result.setDevicePixelRatio(ratio)
    return result


def story_tooltip(article: dict) -> str:
    parts = [tr(evidence_label(article)), tr(freshness(article)[0])]
    if update_label(article):
        parts.append(tr(update_label(article)))
    return " · ".join(parts)


def coverage_text(group: list[dict]) -> str:
    families = len({publisher_family(item) for item in group})
    return f"{len(group)} {tr('reports')} · {families} {tr('families')}"


class _Card(QFrame):
    """Behaviour shared by the lead story and the regular cards."""

    def __init__(self, article: dict, host, *, saved: bool, read: bool, coverage, show_image: bool):
        super().__init__()
        self.article, self.host = article, host
        self.coverage = coverage if coverage and len(coverage) > 1 else None
        self.saved, self.read = saved, read
        self.thumb: QLabel | None = None
        self.show_image = show_image
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setToolTip(story_tooltip(article))
        self.setAccessibleName(article.get("localized_title") or article.get("title", ""))

    # -- shared pieces
    def _thumb(self, size: QSize) -> QLabel:
        self.thumb = QLabel()
        self.thumb.setObjectName("thumb")
        self.thumb.setFixedSize(size)
        self.thumb.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.thumb.setPixmap(icon("image", "border_strong", 26).pixmap(26, 26))
        self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return self.thumb

    def _coverage_chip(self) -> QPushButton | None:
        if not self.coverage:
            return None
        chip = QPushButton(coverage_text(self.coverage))
        chip.setObjectName("coverageChip")
        chip.setIcon(icon("layers", "accent", 14))
        chip.setToolTip(tr("Open the coverage timeline and source articles"))
        chip.setCursor(Qt.CursorShape.PointingHandCursor)
        chip.clicked.connect(lambda: self.host.show_coverage(self.coverage))
        return chip

    def _more_menu(self, button) -> QMenu:
        menu = QMenu(button)
        menu.addAction(icon("pencil"), tr("Notes and tags"), lambda: self.host.edit_notes(self.article))
        menu.addAction(icon("check"), tr("Mark as unread") if self.read else tr("Mark as read"),
                       lambda: self.host.mark_read(self.article, not self.read))
        if state.language != "en":
            menu.addAction(icon("translate"), tr("Translate full story"),
                           lambda: self.host.open_translated(self.article))
        menu.addAction(icon("external"), tr("Open in browser"), lambda: self.host.open_external(self.article))
        menu.addAction(icon("link"), tr("Copy article link"),
                       lambda: QApplication.clipboard().setText(self.article.get("link", "")))
        menu.aboutToShow.connect(lambda: self._refresh_menu(menu))
        return menu

    def _refresh_menu(self, menu: QMenu):
        actions = menu.actions()
        if len(actions) > 1:
            actions[1].setText(tr("Mark as unread") if self.read else tr("Mark as read"))

    # -- in-place updates
    def set_image(self, image) -> None:
        if self.thumb is not None and image is not None and not image.isNull():
            self.thumb.setPixmap(rounded(image, self.thumb.size()))

    def set_saved(self, saved: bool) -> None:
        self.saved = saved
        self._sync_saved()

    def set_read(self, read: bool) -> None:
        self.read = read
        self._sync_read()

    def _sync_saved(self):
        pass

    def _sync_read(self):
        pass

    def set_localized(self, title: str, summary: str) -> None:
        pass

    # -- input
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.host.open_article(self.article)
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.host.open_article(self.article)
            event.accept()
        elif event.key() == Qt.Key.Key_S:
            self.host.toggle_saved_story(self.article)
            event.accept()
        else:
            super().keyPressEvent(event)


def _country(article: dict) -> str:
    return SOURCE_BY_NAME.get(article.get("source", ""), {}).get("country", "")


class NewsCard(_Card):
    def __init__(self, article: dict, host, *, compact=False, saved=False, read=False, coverage=None,
                 show_image=False, new=False):
        super().__init__(article, host, saved=saved, read=read, coverage=coverage, show_image=show_image)
        self.setObjectName("newsCard")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 11, 12, 9) if compact else row.setContentsMargins(16, 14, 14, 11)
        row.setSpacing(14)
        if show_image:
            row.addWidget(self._thumb(QSize(108, 70) if compact else QSize(136, 88)), 0, Qt.AlignmentFlag.AlignTop)
        body = QVBoxLayout()
        body.setSpacing(5 if compact else 7)

        meta = QHBoxLayout()
        meta.setSpacing(8)
        meta.addWidget(_label(article.get("source", "Unknown"), "storySource"))
        meta.addWidget(_label(tr(classify_article(article).title()), "categoryTag"))
        when = " · ".join(part for part in (_country(article), age(article.get("timestamp", 0), article.get("time", ""))) if part)
        if update_label(article):
            when += " · " + tr(update_label(article))
        meta.addWidget(_label(when, "storyMeta"))
        if new:
            meta.addWidget(_label(tr("New"), "newTag"))
        meta.addStretch()
        self.read_tag = _label("✓ " + tr("Read"), "readTag")
        meta.addWidget(self.read_tag)
        body.addLayout(meta)

        self.title = _label(article.get("localized_title") or article.get("title", "Untitled"), "storyTitle", wrap=True)
        body.addWidget(self.title)
        self.excerpt = None
        if not compact:
            text = reading_excerpt(article.get("localized_summary") or article.get("summary", ""), 170)
            if text:
                self.excerpt = _label(text, "storyExcerpt", wrap=True)
                body.addWidget(self.excerpt)
        body.addStretch(1)

        footer = QHBoxLayout()
        footer.setSpacing(2)
        chip = self._coverage_chip()
        if chip:
            footer.addWidget(chip)
        footer.addStretch()
        self.save_button = tool_button("star", "", self, object_name="cardAction", tone="star", size=17)
        self.save_button.clicked.connect(lambda: host.toggle_saved_story(article))
        ai_button = tool_button("sparkle", tr("Analyze this story with related coverage"), self,
                                object_name="cardAction", tone="gold", size=17)
        ai_button.clicked.connect(lambda: host.summarize_article(article))
        more = tool_button("more", tr("More actions"), self, object_name="cardAction", size=17)
        more.setPopupMode(more.ToolButtonPopupMode.InstantPopup)
        more.setMenu(self._more_menu(more))
        for button in (self.save_button, ai_button, more):
            footer.addWidget(button)
        body.addLayout(footer)
        row.addLayout(body, 1)
        self._sync_saved()
        self._sync_read()

    def _sync_saved(self):
        self.save_button.setIcon(icon("star-filled" if self.saved else "star", "star", 17))
        tip = tr("Remove from saved stories") if self.saved else tr("Save for later")
        self.save_button.setToolTip(tip + " · S")
        self.save_button.setAccessibleName(tip)

    def _sync_read(self):
        self.read_tag.setVisible(self.read)
        self.title.setProperty("read", self.read)
        self.title.style().unpolish(self.title)
        self.title.style().polish(self.title)

    def set_localized(self, title: str, summary: str) -> None:
        if title:
            self.title.setText(title)
            self.setAccessibleName(title)
        if summary and self.excerpt is not None:
            self.excerpt.setText(reading_excerpt(summary, 170))


class FeaturedStory(_Card):
    """The large lead card that opens the page."""

    def __init__(self, article: dict, host, *, compact=False, saved=False, read=False, coverage=None,
                 show_image=False, reasons: str = ""):
        super().__init__(article, host, saved=saved, read=read, coverage=coverage, show_image=show_image)
        self.setObjectName("featuredStory")
        self.reasons = reasons
        if reasons:
            self.setToolTip(reasons)
        row = QHBoxLayout(self)
        row.setContentsMargins(16, 14, 20, 14) if compact else row.setContentsMargins(20, 18, 24, 18)
        row.setSpacing(18 if compact else 24)
        if show_image:
            row.addWidget(self._thumb(QSize(200, 124) if compact else QSize(320, 196)), 0, Qt.AlignmentFlag.AlignTop)
        copy = QVBoxLayout()
        copy.setSpacing(6 if compact else 9)

        top = QHBoxLayout()
        top.setSpacing(8)
        top.addWidget(_label(tr("Lead story · European briefing").upper(), "kicker"))
        top.addWidget(_label(tr(classify_article(article).title()), "categoryTag"))
        top.addStretch()
        why = QPushButton(tr("Why featured"))
        why.setObjectName("linkButton")
        why.setCursor(Qt.CursorShape.PointingHandCursor)
        why.setToolTip(reasons)
        why.clicked.connect(lambda: host.explain_featured(self.reasons))
        top.addWidget(why)
        copy.addLayout(top)

        meta = QHBoxLayout()
        meta.setSpacing(8)
        meta.addWidget(_label(article.get("source", ""), "storySource"))
        meta.addWidget(_label(age(article.get("timestamp", 0), article.get("time", "")), "storyMeta"))
        self.read_tag = _label("✓ " + tr("Read"), "readTag")
        meta.addWidget(self.read_tag)
        meta.addStretch()
        copy.addLayout(meta)

        self.title = _label(article.get("localized_title") or article.get("title", "Top story"), "featuredTitle", wrap=True)
        copy.addWidget(self.title)
        self.summary = None
        if not compact:
            text = reading_excerpt(article.get("localized_summary") or article.get("summary")
                                   or article.get("description"), 240)
            if text:
                self.summary = _label(text, "featuredSummary", wrap=True)
                copy.addWidget(self.summary)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        read_button = QPushButton(tr("Read full story"))
        read_button.setObjectName("primary")
        read_button.setIcon(icon("newspaper", "primary_ink", 16))
        read_button.clicked.connect(lambda: host.open_article(article))
        actions.addWidget(read_button)
        brief = QPushButton(tr("AI brief"))
        brief.setIcon(icon("sparkle", "gold", 16))
        brief.setToolTip(tr("Analyze this story with related coverage"))
        brief.clicked.connect(lambda: host.summarize_article(article))
        actions.addWidget(brief)
        self.save_button = QPushButton()
        self.save_button.clicked.connect(lambda: host.toggle_saved_story(article))
        actions.addWidget(self.save_button)
        chip = self._coverage_chip()
        if chip:
            actions.addWidget(chip)
        actions.addStretch()
        more = tool_button("more", tr("More actions"), self, object_name="cardAction", size=18)
        more.setPopupMode(more.ToolButtonPopupMode.InstantPopup)
        more.setMenu(self._more_menu(more))
        actions.addWidget(more)
        copy.addLayout(actions)
        row.addLayout(copy, 1)
        self._sync_saved()
        self._sync_read()

    def _sync_saved(self):
        self.save_button.setText(tr("Saved") if self.saved else tr("Save for later"))
        self.save_button.setIcon(icon("star-filled" if self.saved else "star", "star", 16))
        self.save_button.setToolTip(tr("Remove from saved stories") if self.saved else tr("Save for later"))

    def _sync_read(self):
        self.read_tag.setVisible(self.read)

    def set_localized(self, title: str, summary: str) -> None:
        if title:
            self.title.setText(title)
        if summary and self.summary is not None:
            self.summary.setText(reading_excerpt(summary, 240))


class StoryCard(_Card):
    """A developing story on the Briefing page: every report about one event, led by the best one."""

    def __init__(self, story, host, *, rank=1, compact=False, saved=False, read=False, new=False,
                 show_image=False, large=False):
        super().__init__(story.lead, host, saved=saved, read=read, coverage=story.articles, show_image=show_image)
        self.story = story
        self.setObjectName("featuredStory" if large else "newsCard")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        lead = story.lead
        row = QHBoxLayout(self)
        margins = (20, 16, 20, 14) if large else ((14, 11, 12, 9) if compact else (16, 14, 14, 11))
        row.setContentsMargins(*margins)
        row.setSpacing(18 if large else 14)
        if show_image:
            size = (QSize(260, 160) if not compact else QSize(180, 112)) if large else (QSize(108, 70) if compact else QSize(136, 88))
            row.addWidget(self._thumb(size), 0, Qt.AlignmentFlag.AlignTop)
        body = QVBoxLayout()
        body.setSpacing(6 if compact else 8)

        meta = QHBoxLayout()
        meta.setSpacing(8)
        self.rank_label = _label(f"{rank:02d}", "rankTag")
        meta.addWidget(self.rank_label)
        meta.addWidget(_label(tr(story.topic.title()), "categoryTag"))
        for region in sorted(story.regions & {"EUROPE", "US"}):
            meta.addWidget(_label({"EUROPE": tr("Europe"), "US": tr("United States")}[region], "regionTag"))
        coverage = f"{story.families} {tr('sources') if story.families != 1 else tr('source')}"
        if len(story.countries) > 1:
            coverage += f" · {len(story.countries)} {tr('countries')}"
        meta.addWidget(_label(coverage + " · " + age(story.updated), "storyMeta"))
        if new:
            meta.addWidget(_label(tr("New"), "newTag"))
        meta.addStretch()
        self.read_tag = _label("✓ " + tr("Read"), "readTag")
        meta.addWidget(self.read_tag)
        importance = _label(f"{story.importance:.0f}", "importanceTag")
        importance.setToolTip(tr("Importance") + "\n" + "\n".join(explain(story.reasons)))
        importance.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        meta.addWidget(importance)
        body.addLayout(meta)

        self.title = _label(lead.get("localized_title") or lead.get("title", ""), "featuredTitle" if large else "storyTitle",
                            wrap=True)
        body.addWidget(self.title)
        self.excerpt = None
        text = reading_excerpt(lead.get("localized_summary") or lead.get("summary", ""), 260 if large else 170)
        if text and not (compact and not large):
            self.excerpt = _label(text, "featuredSummary" if large else "storyExcerpt", wrap=True)
            body.addWidget(self.excerpt)
        names = []
        for item in story.articles:
            name = item.get("source", "")
            if name and name not in names:
                names.append(name)
        sources = ", ".join(names[:4]) + (f"  +{len(names) - 4}" if len(names) > 4 else "")
        if story.entities:
            sources += "   ·   " + ", ".join(tr(name) for name in story.entities[:3])
        body.addWidget(_label(sources, "storyMeta", wrap=True))
        if not large:
            body.addStretch(1)  # equal-height cards in a row keep their actions aligned

        footer = QHBoxLayout()
        footer.setSpacing(4)
        if large:
            read_button = QPushButton(tr("Read full story"))
            read_button.setObjectName("primary")
            read_button.setIcon(icon("newspaper", "primary_ink", 16))
            read_button.clicked.connect(lambda: host.open_article(lead))
            footer.addWidget(read_button)
        if len(story.articles) > 1:
            chip = QPushButton(f"{tr('All reports')} · {len(story.articles)}")
            chip.setObjectName("coverageChip")
            chip.setIcon(icon("layers", "accent", 14))
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.clicked.connect(lambda: host.show_coverage(story.articles))
            footer.addWidget(chip)
        footer.addStretch()
        self.save_button = tool_button("star", "", self, object_name="cardAction", tone="star", size=17)
        self.save_button.clicked.connect(lambda: host.toggle_saved_story(lead))
        ai_button = tool_button("sparkle", tr("Analyze this story with related coverage"), self,
                                object_name="cardAction", tone="gold", size=17)
        ai_button.clicked.connect(lambda: host.summarize_article(lead))
        more = tool_button("more", tr("More actions"), self, object_name="cardAction", size=17)
        more.setPopupMode(more.ToolButtonPopupMode.InstantPopup)
        more.setMenu(self._more_menu(more))
        for button in (self.save_button, ai_button, more):
            footer.addWidget(button)
        body.addLayout(footer)
        row.addLayout(body, 1)
        self._sync_saved()
        self._sync_read()

    _sync_saved = NewsCard._sync_saved
    set_localized = NewsCard.set_localized

    def set_rank(self, rank: int) -> None:
        self.rank_label.setText(f"{rank:02d}")

    def _sync_read(self):
        self.read_tag.setVisible(self.read)
