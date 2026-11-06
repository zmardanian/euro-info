"""The main reading window."""
from __future__ import annotations

import json
import time
from pathlib import Path

from PySide6.QtCore import QDate, QLocale, QPoint, QSize, Qt, QThreadPool, QTimer, Slot
from PySide6.QtGui import QAction, QActionGroup, QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QButtonGroup, QComboBox, QDialog, QFileDialog, QFrame, QGridLayout,
                               QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox,
                               QPushButton, QScrollArea, QSystemTrayIcon, QVBoxLayout, QWidget)

from .. import __version__, logs, paths, settings
from ..core import ai, feeds, intel, sources, translation, updates
from ..core.articles import (article_key, load_saved_stories, load_seen, load_snapshot, normalized_headline,
                             save_seen, save_snapshot, store_saved_stories)
from ..core.i18n import LANGUAGES, city_name
from ..core.quality import technology_topics
from ..core.retrieval import SearchIndex
from ..core.reasoning import build_analysis_articles
from ..core.workspace import export_articles, matches_query, query_tokens, validate_library_backup
from . import theme
from .cards import FeaturedStory, NewsCard, StoryCard
from .common import COUNTRY_NAMES, explain, icon, localized_date, plain_label, short_date, open_url, run_dialog, state, tool_button, tr, workspace
from .dialogs import (CoverageDialog, DiagnosticsDialog, NewsQualityDialog, NotesDialog, PullModelDialog,
                      SettingsDialog, SourceDialog, about)
from .jobs import FunctionJob, ImageJob, TranslationJob, refresh_everything, select_translation_batch
from .widgets import AIStatusButton, Banner

log = logs.get("window")

FILTERS = ("ALL", "POLITICS", "ECONOMY", "TECHNOLOGY", "SECURITY")
FILTER_LABELS = {"ALL": "All topics", "POLITICS": "Politics", "ECONOMY": "Economy", "TECHNOLOGY": "Technology",
                 "SECURITY": "Security"}
REGIONS = (("ALL", "All regions"), ("EUROPE", "Europe"), ("US", "United States"), ("GLOBAL", "Global"))
SORTS = (("important", "Most important"), ("newest", "Newest first"), ("oldest", "Oldest first"),
         ("focus", "Location focus"), ("source", "Publisher"))
TECH_TOPICS = (("ALL", "All technology"), ("Linux", "Linux"), ("AI", "AI"), ("Biotech", "Biotech"),
               ("Breakthroughs", "Breakthroughs"))
VIEWS = (("briefing", "Briefing", "layers", "Ctrl+1"), ("latest", "Latest news", "newspaper", "Ctrl+2"),
         ("saved", "Saved for later", "bookmark", "Ctrl+3"), ("research", "Research library", "library", "Ctrl+4"),
         ("history", "Recently opened", "history", "Ctrl+5"))
BRIEFING_PAGE = 16
THEMES = (("standard", "Standard display"), ("paper", "Warm paper"), ("night", "Soft night"))
PAGE_SIZE = 40
TWO_COLUMNS_AT = 1320
SEARCH_SYNTAX = 'Search syntax: "exact phrase", -exclude, source:name, tag:name, is:unread, is:saved, is:noted'


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        language = settings.text("interface_language")
        state.language = language if language in LANGUAGES else "en"
        mode = settings.text("display_mode")
        state.mode = mode if mode in theme.THEMES else "standard"
        self.compact = settings.flag("compact_layout")
        self.large_reading_text = settings.flag("large_reading_text")
        self.article_images_enabled = settings.flag("article_images_enabled")

        self.workspace = workspace()
        self.research_metadata = self.workspace.metadata()
        snapshot = load_snapshot()
        self.weather = snapshot.get("weather", {})
        self.exchange_rates = snapshot.get("exchange_rates", {})
        self.news: list[dict] = snapshot.get("news", [])
        self.saved_stories = load_saved_stories()
        self.view = "briefing"
        self.current_filter = "ALL"
        region = settings.text("coverage_region")
        self.current_region = region if region in dict(REGIONS) else "ALL"
        self.focus_mode = settings.flag("focus_mode")
        self.entity_filter = ""
        self.visible_story_limit = PAGE_SIZE
        self.selected_sources = self._load_source_selection()
        self.seen_keys = load_seen()
        self.watch_alerts: dict[str, int] = {}
        self.tray: QSystemTrayIcon | None = None
        self._last_warm_up = 0.0
        self.index = intel.NewsIndex(self.news)
        self.trends: list[tuple[str, int]] = self.index.trending()

        # Worker pools are separate so images never delay a refresh or an analysis.
        self.image_pool = QThreadPool(self)
        self.image_pool.setMaxThreadCount(3)
        self.refresh_pool = QThreadPool(self)
        self.refresh_pool.setMaxThreadCount(1)
        self.translation_pool = QThreadPool(self)
        self.translation_pool.setMaxThreadCount(1)
        self.summary_pool = QThreadPool(self)
        self.summary_pool.setMaxThreadCount(1)
        self.utility_pool = QThreadPool(self)
        self.utility_pool.setMaxThreadCount(2)
        self.refresh_job = None
        self.translation_job = None
        self.translation_attempted: set = set()
        self.image_active: set[str] = set()
        self.cards: dict[str, NewsCard | FeaturedStory | StoryCard] = {}
        self._card_cache: dict[str, NewsCard] = {}
        self._story_cards: dict[tuple, StoryCard] = {}
        self._last_columns = 0
        self.ai_status: ai.Status | None = None

        self.setWindowTitle("Euro Info")
        self.resize(1480, 940)
        self.setMinimumSize(1000, 680)
        self._build()
        self.apply_theme()
        self.retranslate()

        self.relayout_timer = QTimer(self, singleShot=True, interval=120)
        self.relayout_timer.timeout.connect(self.relayout)
        self.image_scan_timer = QTimer(self, singleShot=True, interval=90)
        self.image_scan_timer.timeout.connect(self.prioritize_visible_images)
        self.scroll.verticalScrollBar().valueChanged.connect(lambda _value: self.image_scan_timer.start())
        self.auto_refresh = QTimer(self)
        self.auto_refresh.timeout.connect(self.refresh_data)
        self.apply_refresh_interval()

        if self.news or self.weather or self.exchange_rates:
            self.render_weather()
            self.render_news()
            self.set_status(tr("Showing saved headlines while refreshing…"))
        self.maybe_offer_translation()
        self.request_headline_translations()
        QTimer.singleShot(0, self.refresh_data)
        QTimer.singleShot(1500, self.check_ai)
        QTimer.singleShot(6000, self.maybe_check_updates)

    # ================================================================ building

    def _build(self):
        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        shell = QHBoxLayout(central)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)
        shell.addWidget(self._build_sidebar())
        content = QWidget()
        content.setObjectName("content")
        shell.addWidget(content, 1)
        root = QVBoxLayout(content)
        self.content_layout = root
        root.setSpacing(10)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(0)
        self.page_title = QLabel()
        self.page_title.setObjectName("mastheadTitle")
        titles.addWidget(self.page_title)
        self.subtitle = QLabel()
        self.subtitle.setObjectName("subtitle")
        titles.addWidget(self.subtitle)
        header.addLayout(titles)
        header.addStretch()
        self.refresh_button = tool_button("refresh", "", self)
        self.refresh_button.clicked.connect(self.refresh_data)
        self.view_button = tool_button("type", "", self)
        self.view_button.setPopupMode(self.view_button.ToolButtonPopupMode.InstantPopup)
        self.settings_button = tool_button("sliders", "", self)
        self.settings_button.clicked.connect(self.open_settings)
        for button in (self.refresh_button, self.view_button, self.settings_button):
            header.addWidget(button)
        root.addLayout(header)

        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        self.search = QLineEdit()
        self.search.setObjectName("search")
        self.search.setClearButtonEnabled(True)
        self.search_action = self.search.addAction(icon("search"), QLineEdit.ActionPosition.LeadingPosition)
        self.search_debounce = QTimer(self, singleShot=True, interval=180)
        self.search_debounce.timeout.connect(self.search_committed)
        self.search.textChanged.connect(lambda _text: self.search_debounce.start())
        self.search.textChanged.connect(self.maybe_warm_up)
        search_row.addWidget(self.search, 1)
        self.ask_button = QPushButton()
        self.ask_button.setObjectName("primary")
        self.ask_button.clicked.connect(self.ask_ai)
        search_row.addWidget(self.ask_button)
        self.watch_combo = QComboBox()
        self.watch_combo.setMinimumWidth(170)
        self.watch_combo.activated.connect(self.select_watch)
        search_row.addWidget(self.watch_combo)
        self.save_watch_button = QPushButton("+")
        self.save_watch_button.clicked.connect(self.save_watch)
        self.remove_watch_button = QPushButton("−")
        self.remove_watch_button.clicked.connect(self.remove_watch)
        for button in (self.save_watch_button, self.remove_watch_button):
            button.setFixedWidth(34)
            search_row.addWidget(button)
        root.addLayout(search_row)

        self.translation_banner = Banner()
        self.translation_banner.closed.connect(lambda: settings.put("translation_provider",
                                                                    settings.text("translation_provider") or "off"))
        self.update_banner = Banner()
        root.addWidget(self.translation_banner)
        root.addWidget(self.update_banner)
        root.addWidget(self._build_info_strip())

        self.trend_row = QHBoxLayout()
        self.trend_row.setSpacing(2)
        self.trend_label = QLabel()
        self.trend_label.setObjectName("trendLabel")
        self.trend_row.addWidget(self.trend_label)
        self.trend_chips = QHBoxLayout()
        self.trend_chips.setSpacing(2)
        self.trend_row.addLayout(self.trend_chips)
        self.trend_row.addStretch()
        root.addLayout(self.trend_row)

        regions = QHBoxLayout()
        regions.setSpacing(6)
        self.region_group = QButtonGroup(self)
        self.region_buttons = {}
        for code, _label in REGIONS:
            chip = QPushButton()
            chip.setObjectName("chip")
            chip.setCheckable(True)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.clicked.connect(lambda _=False, value=code: self.set_region(value))
            self.region_group.addButton(chip)
            self.region_buttons[code] = chip
            regions.addWidget(chip)
        self.region_buttons[self.current_region].setChecked(True)
        regions.addStretch()
        self.focus_button = QPushButton()
        self.focus_button.setObjectName("chip")
        self.focus_button.setCheckable(True)
        self.focus_button.setChecked(self.focus_mode)
        self.focus_button.clicked.connect(self.toggle_focus_mode)
        regions.addWidget(self.focus_button)
        root.addLayout(regions)

        filters = QHBoxLayout()
        filters.setSpacing(6)
        self.filter_group = QButtonGroup(self)
        self.filter_buttons = {}
        for name in FILTERS:
            chip = QPushButton()
            chip.setObjectName("chip")
            chip.setCheckable(True)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.clicked.connect(lambda _=False, value=name: self.set_filter(value))
            self.filter_group.addButton(chip)
            self.filter_buttons[name] = chip
            filters.addWidget(chip)
        self.filter_buttons["ALL"].setChecked(True)
        divider = QFrame()
        divider.setObjectName("stripDivider")
        divider.setFixedHeight(20)
        filters.addSpacing(4)
        filters.addWidget(divider)
        filters.addSpacing(4)
        self.unread_button = QPushButton()
        self.unread_button.setObjectName("chip")
        self.unread_button.setCheckable(True)
        self.unread_button.clicked.connect(lambda: self.render_news())
        filters.addWidget(self.unread_button)
        filters.addStretch()
        self.tech_topic_combo = QComboBox()
        for code, _label in TECH_TOPICS:
            self.tech_topic_combo.addItem("", code)
        self.tech_topic_combo.currentIndexChanged.connect(lambda: self.render_news())
        self.tech_topic_combo.hide()
        filters.addWidget(self.tech_topic_combo)
        self.sort_combo = QComboBox()
        for code, _label in SORTS:
            self.sort_combo.addItem("", code)
        self.sort_combo.currentIndexChanged.connect(lambda: self.render_news())
        filters.addWidget(self.sort_combo)
        root.addLayout(filters)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.news_container = QWidget()
        self.news_container.setObjectName("newsContainer")
        self.news_layout = QGridLayout(self.news_container)
        self.news_layout.setContentsMargins(0, 2, 6, 12)
        self.news_layout.setHorizontalSpacing(12)
        self.news_layout.setVerticalSpacing(12)
        self.news_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.news_container)
        # J and K move between stories while the news area has focus.
        for key, step in (("J", 1), ("K", -1)):
            shortcut = QShortcut(QKeySequence(key), self.scroll, context=Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(lambda delta=step: self.move_focus(delta))
        root.addWidget(self.scroll, 1)
        self.more_button = QPushButton()
        self.more_button.clicked.connect(self.load_more_stories)
        self.more_button.hide()
        root.addWidget(self.more_button, 0, Qt.AlignmentFlag.AlignHCenter)

        self.status = QLabel()
        self.story_count = QLabel()
        self.statusBar().addWidget(self.status, 1)
        self.statusBar().addPermanentWidget(self.story_count)
        self.statusBar().setSizeGripEnabled(False)
        self._build_menus()
        self._build_shortcuts()

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        self.sidebar = sidebar
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(14, 22, 14, 14)
        side.setSpacing(2)
        brand = QLabel("EURO INFO")
        brand.setObjectName("brand")
        side.addWidget(brand)
        self.brand_subtitle = QLabel()
        self.brand_subtitle.setObjectName("brandSubtitle")
        side.addWidget(self.brand_subtitle)
        side.addSpacing(10)

        self.desk_section = self._side_section(side)
        self.view_group = QButtonGroup(self)
        self.nav_buttons = {}
        for code, _label, icon_name, _shortcut in VIEWS:
            button = self._side_button(side, icon_name, lambda _=False, view=code: self.set_view(view))
            button.setCheckable(True)
            self.view_group.addButton(button)
            self.nav_buttons[code] = button
        self.nav_buttons[self.view].setChecked(True)

        self.tools_section = self._side_section(side)
        self.daily_brief_button = self._side_button(side, "sparkle", self.write_briefing)
        self.quality_button = self._side_button(side, "layers", self.show_news_quality)
        self.copy_headlines_button = self._side_button(side, "copy", self.copy_headlines)
        self.reset_filters_button = self._side_button(side, "reset", self.reset_reader_filters)

        self.focus_section = self._side_section(side)
        self.location_combo = QComboBox()
        self.location_combo.setObjectName("sideCombo")
        self.location_combo.addItem("", "AUTO")
        for code in COUNTRY_NAMES:
            self.location_combo.addItem("", code)
        self.location_combo.setCurrentIndex(max(0, self.location_combo.findData(settings.text("news_focus_country"))))
        self.location_combo.currentIndexChanged.connect(self.change_location_focus)
        side.addWidget(self.location_combo)
        self.location_hint = QLabel()
        self.location_hint.setObjectName("sideHint")
        self.location_hint.setWordWrap(True)
        side.addSpacing(4)
        side.addWidget(self.location_hint)

        self.sources_section = self._side_section(side)
        self.side_sources = self._side_button(side, "rss", self.choose_sources)
        self.images_button = self._side_button(side, "image", self.toggle_article_images)
        self.images_button.setCheckable(True)
        self.images_button.setChecked(self.article_images_enabled)
        side.addStretch()
        self.ai_button = AIStatusButton()
        self.ai_button.clicked.connect(self.show_ai_menu)
        side.addWidget(self.ai_button)
        side.addSpacing(6)
        version = QLabel(f"Euro Info {__version__}")
        version.setObjectName("sideVersion")
        side.addWidget(version)
        sidebar.setFixedWidth(236)
        return sidebar

    @staticmethod
    def _side_section(layout) -> QLabel:
        label = QLabel()
        label.setObjectName("sideSection")
        layout.addWidget(label)
        return label

    def _side_button(self, layout, icon_name: str, slot) -> QPushButton:
        button = QPushButton()
        button.setObjectName("sideNav")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setProperty("iconName", icon_name)
        button.setIconSize(QSize(17, 17))
        button.clicked.connect(slot)
        layout.addWidget(button)
        return button

    def _build_info_strip(self) -> QFrame:
        self.info_strip = QFrame()
        self.info_strip.setObjectName("infoStrip")
        strip = QHBoxLayout(self.info_strip)
        strip.setContentsMargins(14, 7, 14, 7)
        strip.setSpacing(12)
        self.weather_label = QLabel()
        self.weather_label.setObjectName("stripSection")
        strip.addWidget(self.weather_label)
        self.weather_metrics = QHBoxLayout()
        self.weather_metrics.setSpacing(14)
        strip.addLayout(self.weather_metrics)
        divider = QFrame()
        divider.setObjectName("stripDivider")
        divider.setFixedHeight(16)
        strip.addWidget(divider)
        self.rates_label = QLabel("ECB · EUR")
        self.rates_label.setObjectName("stripSection")
        strip.addWidget(self.rates_label)
        self.rate_metrics = QHBoxLayout()
        self.rate_metrics.setSpacing(14)
        strip.addLayout(self.rate_metrics)
        strip.addStretch()
        self.rates_date = QLabel("—")
        self.rates_date.setObjectName("stripDate")
        strip.addWidget(self.rates_date)
        return self.info_strip

    def _build_menus(self):
        bar = self.menuBar()
        bar.setNativeMenuBar(False)
        self.file_menu = bar.addMenu("")
        self.export_action = self.file_menu.addAction("", self.export_view)
        self.export_action.setShortcut(QKeySequence("Ctrl+Shift+E"))
        self.backup_action = self.file_menu.addAction("", self.backup_library)
        self.import_action = self.file_menu.addAction("", self.import_library)
        self.file_menu.addSeparator()
        self.quit_action = self.file_menu.addAction("", QApplication.quit)
        self.quit_action.setShortcut(QKeySequence.StandardKey.Quit)

        self.view_menu = bar.addMenu("")
        self.theme_menu = self.view_menu.addMenu("")
        self.theme_group = QActionGroup(self)
        self.theme_actions = {}
        for code, _label in THEMES:
            action = QAction(self, checkable=True)
            action.setChecked(code == state.mode)
            action.triggered.connect(lambda _=False, value=code: self.change_display_mode(value))
            self.theme_group.addAction(action)
            self.theme_menu.addAction(action)
            self.theme_actions[code] = action
        self.language_menu = self.view_menu.addMenu("")
        self.language_group = QActionGroup(self)
        for code, label in LANGUAGES.items():
            action = QAction(label, self, checkable=True)
            action.setChecked(code == state.language)
            action.triggered.connect(lambda _=False, value=code: self.change_language(value))
            self.language_group.addAction(action)
            self.language_menu.addAction(action)
        self.view_menu.addSeparator()
        self.large_text_action = self.view_menu.addAction("")
        self.large_text_action.setCheckable(True)
        self.large_text_action.setChecked(self.large_reading_text)
        self.large_text_action.triggered.connect(self.toggle_large_reading_text)
        self.compact_action = self.view_menu.addAction("")
        self.compact_action.setCheckable(True)
        self.compact_action.setChecked(self.compact)
        self.compact_action.triggered.connect(self.toggle_compact)
        self.images_action = self.view_menu.addAction("")
        self.images_action.setCheckable(True)
        self.images_action.setChecked(self.article_images_enabled)
        self.images_action.triggered.connect(lambda checked: self.toggle_article_images(checked))
        self.view_menu.addSeparator()
        self.refresh_action = self.view_menu.addAction("", self.refresh_data)
        self.refresh_action.setShortcut(QKeySequence("F5"))
        self.view_button.setMenu(self.view_menu)

        self.tools_menu = bar.addMenu("")
        self.settings_action = self.tools_menu.addAction("", self.open_settings)
        self.settings_action.setShortcut(QKeySequence("Ctrl+,"))
        self.brief_action = self.tools_menu.addAction("", self.write_briefing)
        self.ask_action = self.tools_menu.addAction("", self.ask_ai)
        self.ask_action.setShortcut(QKeySequence("Ctrl+Return"))
        self.coverage_action = self.tools_menu.addAction("", self.show_news_quality)
        self.sources_action = self.tools_menu.addAction("", self.choose_sources)
        self.diagnostics_action = self.tools_menu.addAction("", lambda: run_dialog(DiagnosticsDialog(self)))

        self.help_menu = bar.addMenu("")
        self.shortcuts_action = self.help_menu.addAction("", self.show_shortcuts)
        self.update_action = self.help_menu.addAction("", lambda: self.check_updates(manual=True))
        self.log_action = self.help_menu.addAction("", lambda: open_url(paths.ensure(paths.cache_dir()).as_uri()))
        self.help_menu.addSeparator()
        self.about_action = self.help_menu.addAction("", lambda: about(self))

    def _build_shortcuts(self):
        for sequence in ("Ctrl+K", "Ctrl+L", "/"):
            QShortcut(QKeySequence(sequence), self).activated.connect(self.focus_search)
        for code, _label, _icon, sequence in VIEWS:
            QShortcut(QKeySequence(sequence), self).activated.connect(lambda view=code: self.set_view(view))
        QShortcut(QKeySequence("Escape"), self.search).activated.connect(self.search.clear)

    def focus_search(self):
        self.search.setFocus()
        self.search.selectAll()

    # ================================================================ language and theme

    def retranslate(self):
        self.setWindowTitle(f"Euro Info — {tr('Europe, in focus.')}")
        self.page_title.setText(tr("Europe, in focus."))
        self.subtitle.setText(localized_date() + "  ·  " + tr("European news and weather"))
        self.brand_subtitle.setText(tr("European Daily Briefing").upper())
        self.desk_section.setText(tr("Your desk").upper())
        self.tools_section.setText(tr("Reader tools").upper())
        self.focus_section.setText(tr("Location focus").upper())
        self.sources_section.setText(tr("Your sources").upper())
        for code, label, _icon, sequence in VIEWS:
            self.nav_buttons[code].setText("  " + tr(label))
            self.nav_buttons[code].setToolTip(f"{tr(label)} · {sequence}")
        self.update_saved_count()
        self.daily_brief_button.setText("  " + tr("Write AI briefing"))
        self.daily_brief_button.setToolTip(tr("Uses the local AI model; CPU/GPU use can rise while it generates."))
        self.quality_button.setText("  " + plain_label(tr("Coverage & sources")))
        self.copy_headlines_button.setText("  " + tr("Copy headlines"))
        self.reset_filters_button.setText("  " + tr("Reset filters"))
        self.side_sources.setText("  " + tr("Manage sources"))
        self.images_button.setText("  " + tr("Article images"))
        self.images_button.setToolTip(tr("Article images are optional and use additional system resources."))
        detected = self.detected_country()
        self.location_combo.blockSignals(True)
        for index in range(self.location_combo.count()):
            code = self.location_combo.itemData(index)
            text = (f"{tr(COUNTRY_NAMES.get(detected, 'Europe'))} · {tr('Auto')}" if code == "AUTO"
                    else tr(COUNTRY_NAMES.get(code, code)))
            self.location_combo.setItemText(index, text)
        self.location_combo.blockSignals(False)
        self.location_combo.setToolTip(tr("Location changes article order only. No precise location is collected or shared."))
        self.location_hint.setText(tr("Local stories first · all headlines stay available"))

        self.refresh_button.setToolTip(tr("Refresh") + " · F5")
        self.view_button.setToolTip(tr("Display options"))
        self.settings_button.setToolTip(tr("Settings") + " · Ctrl+,")
        self.search.setPlaceholderText(tr("Search stories, or type a question and press Ask AI"))
        self.ask_button.setText(tr("Ask AI"))
        self.ask_button.setToolTip(tr("Answer a question from the loaded stories with the local AI") + " · Ctrl+Enter")
        self.trend_label.setText(tr("Trending").upper())
        for code, label in REGIONS:
            self.region_buttons[code].setText(tr(label))
        self.focus_button.setText(tr("Focus"))
        self.focus_button.setToolTip(tr("Hide sport, celebrity, lifestyle and local US stories"))
        self.search.setToolTip(tr(SEARCH_SYNTAX) + " · Ctrl+K")
        self.search.setAccessibleName(tr("Search stories..."))
        self.save_watch_button.setToolTip(tr("Save current search"))
        self.remove_watch_button.setToolTip(tr("Remove saved search"))
        self.reload_watches()
        self.weather_label.setText(tr("Weather").upper())
        self.rates_label.setToolTip(tr("Daily ECB reference rates, not live trading quotes"))
        for name, chip in self.filter_buttons.items():
            chip.setText(tr(FILTER_LABELS[name]))
        self.unread_button.setText(tr("Unread only"))
        for index, (_code, label) in enumerate(TECH_TOPICS):
            self.tech_topic_combo.setItemText(index, tr(label))
        self.tech_topic_combo.setToolTip(tr("Linux news is prioritised; choose a topic to filter technology coverage."))
        for index, (_code, label) in enumerate(SORTS):
            self.sort_combo.setItemText(index, tr(label))

        self.file_menu.setTitle(tr("File"))
        self.export_action.setText(tr("Export current view"))
        self.backup_action.setText(tr("Backup reading list"))
        self.import_action.setText(tr("Import reading list"))
        self.quit_action.setText(tr("Quit"))
        self.view_menu.setTitle(tr("View"))
        self.theme_menu.setTitle(tr("Theme"))
        for code, label in THEMES:
            self.theme_actions[code].setText(tr(label))
        self.language_menu.setTitle(tr("Language"))
        self.large_text_action.setText(tr("Larger story headlines for reading"))
        self.compact_action.setText(tr("Compact"))
        self.images_action.setText(tr("Show article images"))
        self.refresh_action.setText(tr("Refresh"))
        self.tools_menu.setTitle(tr("Tools"))
        self.settings_action.setText(tr("Settings"))
        self.brief_action.setText(tr("Write AI briefing"))
        self.ask_action.setText(tr("Ask AI"))
        self.coverage_action.setText(plain_label(tr("Coverage & sources")))
        self.sources_action.setText(tr("Manage sources"))
        self.diagnostics_action.setText(tr("Diagnostics"))
        self.help_menu.setTitle(tr("Help"))
        self.shortcuts_action.setText(tr("Keyboard shortcuts"))
        self.update_action.setText(tr("Check for updates"))
        self.log_action.setText(tr("Open log folder"))
        self.about_action.setText(tr("About Euro Info"))
        self.more_button.setText(tr("Load more stories"))
        self.render_trending()
        if self.ai_status is not None:
            self.show_ai_status(self.ai_status)

    def apply_theme(self):
        application = QApplication.instance()
        if application:
            application.setStyleSheet(theme.stylesheet(state.mode, self.compact, self.large_reading_text))
        margins = (18, 12, 18, 6) if self.compact else (26, 18, 26, 8)
        self.content_layout.setContentsMargins(*margins)
        self.content_layout.setSpacing(8 if self.compact else 11)
        for button in self.sidebar.findChildren(QPushButton):
            name = button.property("iconName")
            if name:
                button.setIcon(icon(name, "sidebar_ink", 17))
        for button in (self.refresh_button, self.view_button, self.settings_button):
            button.setIcon(icon(button.property("iconName"), "ink_soft", 18))
        self.search_action.setIcon(icon("search", "faint", 16))
        self.ask_button.setIcon(icon("sparkle", "primary_ink", 16))
        self._card_cache.clear()
        self._story_cards.clear()
        if self.ai_status is not None:
            self.show_ai_status(self.ai_status)

    def change_display_mode(self, mode: str):
        if mode == state.mode or mode not in theme.THEMES:
            return
        state.mode = mode
        settings.put("display_mode", mode)
        self.apply_theme()
        self.render_news()

    def toggle_large_reading_text(self, enabled):
        self.large_reading_text = bool(enabled)
        settings.put("large_reading_text", self.large_reading_text)
        self.apply_theme()
        self.render_news()

    def toggle_compact(self, checked):
        self.compact = bool(checked)
        settings.put("compact_layout", self.compact)
        self.apply_theme()
        self.render_news()

    def toggle_article_images(self, enabled=None):
        self.article_images_enabled = self.images_button.isChecked() if enabled is None else bool(enabled)
        self.images_button.setChecked(self.article_images_enabled)
        self.images_action.setChecked(self.article_images_enabled)
        settings.put("article_images_enabled", self.article_images_enabled)
        self.images_button.setText("  " + tr("Article images"))
        self._card_cache.clear()
        self._story_cards.clear()
        self.render_news()

    def change_language(self, language: str):
        if language == state.language or language not in LANGUAGES:
            return
        state.language = language
        settings.put("interface_language", language)
        self.translation_attempted.clear()
        for article in self.news + list(self.saved_stories.values()):
            article.pop("localized_title", None)
            article.pop("localized_summary", None)
        self._card_cache.clear()
        self._story_cards.clear()
        self.retranslate()
        self.render_weather()
        self.render_news()
        self.maybe_offer_translation()
        self.request_headline_translations()

    # ================================================================ status

    def set_status(self, text: str):
        self.status.setText(text)

    def update_saved_count(self):
        count = len(self.saved_stories)
        button = self.nav_buttons["saved"]
        button.setText(f"  {tr('Saved for later')}" + (f"   {count}" if count else ""))

    # ================================================================ refresh

    def apply_refresh_interval(self):
        minutes = settings.number("refresh_minutes")
        self.auto_refresh.stop()
        if minutes > 0:
            self.auto_refresh.start(max(5, minutes) * 60_000)

    def refresh_data(self):
        if self.refresh_job is not None:
            return
        self.refresh_button.setEnabled(False)
        self.set_status(tr("Updating weather, rates and news…"))
        chosen = [source for source in feeds.NEWS_SOURCES if source["name"] in self.selected_sources]
        self.refresh_job = FunctionJob(refresh_everything, chosen, list(self.saved_stories.values()),
                                       settings.flag("personalise"))
        self.refresh_job.signals.finished.connect(self.data_loaded)
        self.refresh_job.signals.failed.connect(self.data_error)
        self.refresh_pool.start(self.refresh_job)

    @Slot(object)
    def data_loaded(self, result):
        weather, news, rates, index, trends = result
        self.refresh_job = None
        self.refresh_button.setEnabled(True)
        old_keys = {article_key(item) for item in self.news}
        previous_weather, self.weather = self.weather, weather or {}
        for city, old in previous_weather.items():
            if self.weather.get(city, {}).get("error") and not old.get("error"):
                self.weather[city] = old
        if (rates or {}).get("rates") or not self.exchange_rates.get("rates"):
            self.exchange_rates = rates or {}
        fresh = list(news or [])
        health = feeds.feed_health_snapshot()
        failed = sum(bool(item["error"]) for item in health.values())
        stale = (not fresh and bool(self.news)) or (bool(health) and failed == len(health))
        if fresh:
            # Keep translations already shown for stories that are still in the feed.
            localized = {article_key(item): (item.get("localized_title"), item.get("localized_summary"))
                         for item in self.news if item.get("localized_title")}
            for item in fresh:
                title, summary = localized.get(article_key(item), (None, None))
                if title:
                    item["localized_title"], item["localized_summary"] = title, summary or ""
            self.news = fresh
            self.index, self.trends = index, trends
            self._card_cache.clear()
            self._story_cards.clear()
            save_snapshot(self.news, self.weather, self.exchange_rates)
            self.check_watch_alerts([item for item in fresh if article_key(item) not in old_keys] if old_keys else [])
        new_count = len({article_key(item) for item in self.news} - old_keys) if old_keys else 0
        since_visit = sum(1 for item in self.news if self.is_new(item))
        self.render_trending()
        self.render_weather()
        self.render_news()
        self.request_headline_translations()
        if stale:
            self.set_status(tr("Showing saved headlines; feed refresh failed"))
            return
        message = f"{tr('Updated')} {time.strftime('%H:%M')} · {len(self.news)} {tr('stories')}"
        if new_count:
            message += f" · {new_count} {tr('new')}"
        elif since_visit:
            message += f" · {since_visit} {tr('new since your last visit')}"
        if failed:
            message += f" · {tr('Unavailable sources')}: {failed}"
        self.set_status(message)

    @Slot(str)
    def data_error(self, message):
        self.refresh_job = None
        self.refresh_button.setEnabled(True)
        self.set_status(f"{tr('Update failed')}: {message}")

    # ================================================================ weather strip

    def render_weather(self):
        for layout in (self.weather_metrics, self.rate_metrics):
            while layout.count():
                widget = layout.takeAt(0).widget()
                if widget:
                    widget.deleteLater()
        narrow = self.width() < TWO_COLUMNS_AT
        capital = {"RO": "Bucharest", "DE": "Berlin", "FR": "Paris", "IT": "Rome", "ES": "Madrid", "PL": "Warsaw",
                   "BE": "Brussels", "EU": "Brussels", "US": "Washington"}.get(self.focus_country())
        cities = sorted(self.weather.items(), key=lambda pair: pair[0] != capital)
        for city, data in cities[:3 if narrow else (8 if self.width() >= 1640 else 6)]:
            temperature = data.get("temperature")
            value = f"{temperature:.0f}°" if isinstance(temperature, (int, float)) else "—"
            metric = QLabel(f"{city_name(city, state.language)} {value}")
            metric.setObjectName("stripMetric")
            if "error" in data:
                metric.setToolTip(data["error"])
            else:
                metric.setToolTip(f"{tr(data.get('description', ''))} · {tr('Feels')} {data.get('feels_like', 0):.1f}°C"
                                  f" · {tr('Humidity')} {data.get('humidity', 0):.0f}% · {tr('Wind')} "
                                  f"{data.get('wind', 0):.1f} km/h")
            self.weather_metrics.addWidget(metric)
        rates = self.exchange_rates.get("rates", {})
        for currency in feeds.EXCHANGE_RATE_CURRENCIES[:3 if narrow else 5]:
            if currency in rates:
                metric = QLabel(f"{currency} {rates[currency]:.3f}")
                metric.setObjectName("stripRate")
                metric.setToolTip(f"1 EUR = {rates[currency]:.5f} {currency} · "
                                  f"{tr('Daily ECB reference rate; not a live trading quote')}")
                self.rate_metrics.addWidget(metric)
        rate_date = self.exchange_rates.get("date", "")
        parsed = QDate.fromString(rate_date, Qt.DateFormat.ISODate)
        self.rates_date.setText(short_date(parsed) if parsed.isValid() else "—")
        self.rates_date.setToolTip(f"{tr('ECB reference-rate date')}: {rate_date}" if rate_date
                                   else self.exchange_rates.get("error", tr("Rates unavailable")))

    # ================================================================ views and filters

    def set_view(self, view: str):
        self.view = view
        self.nav_buttons[view].setChecked(True)
        if view in ("saved", "history"):
            self.current_filter = "ALL"
            self.filter_buttons["ALL"].setChecked(True)
        self.sort_combo.setEnabled(view != "briefing")
        if view == "history":
            self.unread_button.setChecked(False)
        self.research_metadata = self.workspace.metadata()
        self.visible_story_limit = PAGE_SIZE
        self.render_news()
        self.request_headline_translations()

    # Short entry points used by menus and tests.
    def show_all_stories(self):
        self.set_view("latest")

    def show_saved_stories(self):
        self.set_view("saved")

    def show_research(self, checked=True):
        self.set_view("research" if checked else "latest")

    def show_history(self):
        self.set_view("history")

    def set_filter(self, name: str):
        self.current_filter = name
        self.filter_buttons[name].setChecked(True)
        self.visible_story_limit = PAGE_SIZE
        self.render_news()
        self.request_headline_translations()

    def set_region(self, region: str):
        self.current_region = region if region in dict(REGIONS) else "ALL"
        self.region_buttons[self.current_region].setChecked(True)
        settings.put("coverage_region", self.current_region)
        self.visible_story_limit = PAGE_SIZE
        self.render_news()
        self.request_headline_translations()

    def toggle_focus_mode(self, enabled=None):
        self.focus_mode = self.focus_button.isChecked() if enabled is None else bool(enabled)
        self.focus_button.setChecked(self.focus_mode)
        settings.put("focus_mode", self.focus_mode)
        self.render_news()

    def set_entity_filter(self, name: str):
        self.entity_filter = "" if name == self.entity_filter else name
        self.visible_story_limit = PAGE_SIZE
        self.render_trending()
        self.render_news()
        self.request_headline_translations()

    def search_committed(self):
        self.visible_story_limit = PAGE_SIZE
        self.render_news()
        self.request_headline_translations()

    def change_location_focus(self, index):
        settings.put("news_focus_country", self.location_combo.itemData(index) or "AUTO")
        self.render_weather()
        self.render_news()

    def reset_reader_filters(self):
        self.entity_filter = ""
        self.region_buttons["ALL"].setChecked(True)
        for widget in (self.sort_combo, self.tech_topic_combo):
            widget.blockSignals(True)
            widget.setCurrentIndex(0)
            widget.blockSignals(False)
        self.unread_button.setChecked(False)
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        self.search_debounce.stop()
        self.current_region = "ALL"
        settings.put("coverage_region", "ALL")
        self.current_filter = "ALL"
        self.filter_buttons["ALL"].setChecked(True)
        self.render_trending()
        self.set_view(self.view if self.view in ("briefing", "latest") else "briefing")

    def load_more_stories(self):
        self.visible_story_limit += PAGE_SIZE
        self.render_news()
        self.request_headline_translations()

    @staticmethod
    def detected_country() -> str:
        parts = QLocale.system().name().replace("-", "_").split("_")
        code = parts[-1].upper() if len(parts) > 1 else ""
        return code if code in feeds.COUNTRY_TERMS else "EU"

    def focus_country(self) -> str:
        focus = self.location_combo.currentData()
        return self.detected_country() if focus in (None, "AUTO") else focus

    def candidates(self) -> list[dict]:
        if self.view == "history":
            return self.workspace.history_articles()
        if self.view == "research":
            return self.workspace.research_articles()
        if self.view == "saved":
            return list(self.saved_stories.values())
        return self.news

    def matching(self) -> list[dict]:
        """Stories in the current view that pass every filter, in feed order."""
        technology = self.current_filter == "TECHNOLOGY"
        self.tech_topic_combo.setVisible(technology and self.view != "briefing")
        tokens = query_tokens(self.search.text().strip())
        topic = self.tech_topic_combo.currentData()
        unread_only = self.unread_button.isChecked()
        browsing = self.view in ("briefing", "latest")
        result = []
        for article in self.candidates():
            if browsing and article.get("source") not in self.selected_sources:
                continue
            found = intel.features(article)
            if self.current_region != "ALL" and self.current_region not in found.regions:
                continue
            if self.current_filter != "ALL" and found.topic != self.current_filter:
                continue
            if technology and topic != "ALL" and topic not in technology_topics(article):
                continue
            if self.entity_filter and self.entity_filter not in found.entities:
                continue
            if browsing and self.focus_mode and (found.noise or (found.regions == frozenset({"US"})
                                                                 and not found.global_signal)):
                continue
            key = article_key(article)
            metadata = self.research_metadata.get(key, {})
            if unread_only and metadata.get("read_at"):
                continue
            if tokens and not matches_query(article, tokens, metadata, key in self.saved_stories):
                continue
            result.append(article)
        return result

    def filtered_news(self) -> list[dict]:
        result = self.matching()
        if self.view == "history":
            return result
        order = self.sort_combo.currentData()
        if order == "important":
            ranked = self.index.rank(result)
            if self.view == "latest" and not self.search.text().strip():
                # One card per developing story; its other reports open from the card.
                seen_groups, collapsed = set(), []
                for article in ranked:
                    group = self.index.group_of.get(id(article))
                    marker = id(group) if group and len(group) > 1 else id(article)
                    if marker not in seen_groups:
                        seen_groups.add(marker)
                        collapsed.append(article)
                return collapsed
            return ranked
        if order == "newest":
            return sorted(result, key=lambda item: item.get("timestamp") or 0, reverse=True)
        if order == "oldest":
            return sorted(result, key=lambda item: item.get("timestamp") or 0)
        if order == "source":
            return sorted(result, key=lambda item: str(item.get("source", "")).casefold())
        return feeds.prioritize_articles(self.index.rank(result), self.focus_country())

    def coverage_index(self, articles=None, by_identity=False):
        """Developing-story groups, by article key (or object identity)."""
        groups = {}
        for group in self.index.groups:
            if len(group) > 1:
                for item in group:
                    groups[id(item) if by_identity else article_key(item)] = group
        return groups

    def is_new(self, article: dict) -> bool:
        return bool(self.seen_keys) and article_key(article) not in self.seen_keys

    # ================================================================ rendering

    def columns(self) -> int:
        return 2 if self.width() >= (TWO_COLUMNS_AT + (120 if self.large_reading_text else 0)) else 1

    def render_news(self):
        self.news_container.setUpdatesEnabled(False)
        try:
            self._render_news()
        finally:
            self.news_container.setUpdatesEnabled(True)
        self.image_scan_timer.start()

    def _clear_grid(self):
        while self.news_layout.count():
            widget = self.news_layout.takeAt(0).widget()
            if widget is None:
                continue
            if isinstance(widget, NewsCard) and self._card_cache.get(article_key(widget.article)) is widget:
                widget.hide()  # kept for reuse by the next render
            elif isinstance(widget, StoryCard) and self._story_cards.get((widget.story.key,
                                                                          widget.objectName() == "featuredStory")) is widget:
                widget.hide()
            else:
                widget.hide()
                widget.deleteLater()

    def _render_news(self):
        self.cards = {}
        self._clear_grid()
        if self.view == "briefing":
            self._render_briefing()
            return
        articles = self.filtered_news()
        coverage = self.coverage_index(articles)
        shown = articles[:self.visible_story_limit]
        remaining = len(articles) - len(shown)
        self.more_button.setVisible(remaining > 0)
        self.more_button.setText(f"{tr('Load more stories')}  ·  {min(PAGE_SIZE, remaining)}")
        self.story_count.setText(f"{len(shown)} / {len(articles)} {tr('stories')}")
        columns = self.columns()
        self._last_columns = columns
        self.news_layout.setColumnStretch(0, 1)
        self.news_layout.setColumnStretch(1, 1 if columns == 2 else 0)
        if not articles:
            label = QLabel(tr("No stories match this view. Try another topic, clear the search, or refresh."))
            label.setObjectName("emptyState")
            label.setWordWrap(True)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.news_layout.addWidget(label, 0, 0, 1, columns)
            return

        lead, rest = shown[0], shown[1:]
        lead_key = article_key(lead)
        if self.sort_combo.currentData() in ("important", "focus"):
            reasons = explain(self.index.why(lead)) or [tr("Freshness")]
        else:
            reasons = [self.sort_combo.currentText()]
        hint = (tr("Why featured") + ":\n• " + "\n• ".join(reasons) + "\n" +
                tr("Ranking signals are not a reliability score."))
        featured = FeaturedStory(lead, self, compact=self.compact, saved=lead_key in self.saved_stories,
                                 read=bool(self.research_metadata.get(lead_key, {}).get("read_at")),
                                 coverage=coverage.get(lead_key), show_image=self.article_images_enabled,
                                 reasons=hint)
        self.news_layout.addWidget(featured, 0, 0, 1, columns)
        self.cards[lead_key] = featured
        # Same-headline copies of the lead from its coverage group are not repeated below it.
        group_keys = {article_key(item) for item in coverage.get(lead_key, [lead])}
        headline = normalized_headline(lead)
        rest = [item for item in rest
                if not (article_key(item) in group_keys and normalized_headline(item) == headline)]
        for index, article in enumerate(rest):
            card = self._card_for(article, coverage.get(article_key(article)))
            self.news_layout.addWidget(card, index // columns + 1, index % columns)
            card.show()
        self.queue_image(lead, featured)

    def _card_for(self, article: dict, group) -> NewsCard:
        key = article_key(article)
        saved = key in self.saved_stories
        read = bool(self.research_metadata.get(key, {}).get("read_at"))
        card = self._card_cache.get(key)
        group_size = len(group) if group else 0
        if card is None or card.article is not article or len(card.coverage or ()) != group_size:
            if card is not None:
                card.deleteLater()
            card = NewsCard(article, self, compact=self.compact, saved=saved, read=read, coverage=group,
                            show_image=self.article_images_enabled, new=self.is_new(article))
            self._card_cache[key] = card
        else:
            if card.saved != saved:
                card.set_saved(saved)
            if card.read != read:
                card.set_read(read)
        self.cards[key] = card
        return card

    def _render_briefing(self):
        everything = self.index.stories(self.matching(), state.language, 200)
        stories = everything[:max(BRIEFING_PAGE, self.visible_story_limit * BRIEFING_PAGE // PAGE_SIZE)]
        remaining = len(everything) - len(stories)
        self.more_button.setVisible(remaining > 0)
        self.more_button.setText(f"{tr('Load more stories')}  ·  {min(BRIEFING_PAGE, remaining)}")
        reports = sum(len(story.articles) for story in everything)
        self.story_count.setText(f"{len(stories)} / {len(everything)} {tr('developing stories')} · "
                                 f"{reports} {tr('reports')}")
        columns = self.columns()
        self._last_columns = columns
        self.news_layout.setColumnStretch(0, 1)
        self.news_layout.setColumnStretch(1, 1 if columns == 2 else 0)
        header = QWidget()
        row = QHBoxLayout(header)
        row.setContentsMargins(2, 0, 2, 0)
        title = QLabel(tr("Today's briefing"))
        title.setObjectName("briefingTitle")
        row.addWidget(title)
        hint = QLabel(tr("Developing stories ranked by how widely they are covered, their subject and freshness."))
        hint.setObjectName("muted")
        row.addWidget(hint, 1)
        write = QPushButton(tr("Write AI briefing"))
        write.setIcon(icon("sparkle", "gold", 16))
        write.clicked.connect(self.write_briefing)
        write.setEnabled(bool(stories))
        row.addWidget(write)
        self.news_layout.addWidget(header, 0, 0, 1, columns)
        if not stories:
            label = QLabel(tr("No stories match this view. Try another topic, clear the search, or refresh."))
            label.setObjectName("emptyState")
            label.setWordWrap(True)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.news_layout.addWidget(label, 1, 0, 1, columns)
            return
        for rank, story in enumerate(stories, 1):
            key = story.key
            card = self._story_card_for(story, rank)
            if rank == 1:
                self.news_layout.addWidget(card, 1, 0, 1, columns)
            else:
                position = rank - 2
                self.news_layout.addWidget(card, position // columns + 2, position % columns)
            self.cards[key] = card

    def _story_card_for(self, story, rank: int) -> StoryCard:
        """Reuse a built story card when its story has not changed."""
        key = story.key
        large = rank == 1
        saved = key in self.saved_stories
        read = bool(self.research_metadata.get(key, {}).get("read_at"))
        cache_key = (key, large)
        card = self._story_cards.get(cache_key)
        if card is None or card.story is not story:
            if card is not None:
                card.deleteLater()
            card = StoryCard(story, self, rank=rank, compact=self.compact, saved=saved, read=read,
                             new=self.is_new(story.lead), show_image=self.article_images_enabled, large=large)
            self._story_cards[cache_key] = card
        else:
            card.set_rank(rank)
            if card.saved != saved:
                card.set_saved(saved)
            if card.read != read:
                card.set_read(read)
        card.show()
        return card

    def move_focus(self, step: int):
        """J/K: focus the next or previous story and keep it in view."""
        cards = [card for card in self.cards.values() if card.isVisible()]
        cards.sort(key=lambda card: (card.geometry().top(), card.geometry().left()))
        if not cards:
            return
        current = next((index for index, card in enumerate(cards) if card.hasFocus()), -1)
        target = cards[max(0, min(len(cards) - 1, current + step))] if current >= 0 else cards[0]
        target.setFocus()
        self.scroll.ensureWidgetVisible(target, 0, 40)

    def render_trending(self):
        while self.trend_chips.count():
            widget = self.trend_chips.takeAt(0).widget()
            if widget:
                widget.deleteLater()
        names = [name for name, _count in self.trends]
        if self.entity_filter and self.entity_filter not in names:
            names.insert(0, self.entity_filter)
        for name, count in [(name, dict(self.trends).get(name, 0)) for name in names[:8]]:
            chip = QPushButton(("× " if name == self.entity_filter else "") + tr(name))
            chip.setObjectName("trendChip")
            chip.setCheckable(True)
            chip.setChecked(name == self.entity_filter)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            if count:
                chip.setToolTip(f"{count} {tr('reports in the last 6 hours')}")
            chip.clicked.connect(lambda _=False, value=name: self.set_entity_filter(value))
            self.trend_chips.addWidget(chip)
        visible = bool(names)
        self.trend_label.setVisible(visible)

    def relayout(self):
        if self.columns() != self._last_columns:
            self.render_news()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        old, new = event.oldSize().width(), event.size().width()
        if (old < TWO_COLUMNS_AT) != (new < TWO_COLUMNS_AT) and hasattr(self, "weather_metrics"):
            self.render_weather()
        if hasattr(self, "relayout_timer"):
            self.relayout_timer.start()

    def sync_card_states(self):
        """Refresh saved/read marks on visible cards without rebuilding them."""
        for key, card in self.cards.items():
            card.set_saved(key in self.saved_stories)
            card.set_read(bool(self.research_metadata.get(key, {}).get("read_at")))

    # ================================================================ images

    def queue_image(self, article, card):
        if not self.article_images_enabled or card.thumb is None or getattr(card, "has_image", False):
            return
        key = article_key(article)
        if key in self.image_active:
            return
        self.image_active.add(key)
        job = ImageJob(article)
        job.signals.finished.connect(self.image_loaded)
        self.image_pool.start(job)

    @Slot(object)
    def image_loaded(self, result):
        key, image = result
        self.image_active.discard(key)
        card = self.cards.get(key) or self._card_cache.get(key)
        if card is not None and image is not None:
            card.set_image(image)
            card.has_image = True

    def prioritize_visible_images(self):
        if not self.article_images_enabled:
            return
        viewport = self.scroll.viewport()
        top = self.news_container.mapFrom(viewport, QPoint(0, 0)).y() - viewport.height()
        bottom = top + viewport.height() * 3
        for card in self.cards.values():
            if card.isVisible() and card.geometry().bottom() >= top and card.geometry().top() <= bottom:
                self.queue_image(card.article, card)

    # ================================================================ story actions (called by cards)

    def open_article(self, article):
        from .reader import open_reader
        open_reader(article, self, news=self.news)
        self.after_reading()

    def open_translated(self, article):
        from .reader import open_reader
        open_reader(article, self, news=self.news, translated=True)
        self.after_reading()

    def open_external(self, article):
        if article.get("link"):
            open_url(article["link"])

    def after_reading(self):
        self.research_metadata = self.workspace.metadata()
        if self.view == "history" or self.unread_button.isChecked():
            self.render_news()
        else:
            self.sync_card_states()

    def show_coverage(self, articles):
        run_dialog(CoverageDialog(articles, self, on_open=self.open_article))

    def explain_featured(self, reasons: str):
        QMessageBox.information(self, tr("Why featured"), reasons)

    def summarize_article(self, article):
        from .summary import SummaryDialog
        evidence = build_analysis_articles(article, self.news, settings.text("ai_profile"))
        run_dialog(SummaryDialog(evidence, self, focus_article=article, news=self.news))
        self.after_reading()
        self.check_ai()

    def edit_notes(self, article):
        run_dialog(NotesDialog(article, self.workspace, self))
        self.research_metadata = self.workspace.metadata()
        if self.view == "research":
            self.render_news()
        else:
            self.sync_card_states()

    def mark_read(self, article, read):
        key = article_key(article)
        try:
            self.workspace.save_story(key, article, read=read)
        except Exception as exc:  # show storage errors to the reader
            QMessageBox.warning(self, tr("Mark as read"), str(exc))
            return
        self.research_metadata = self.workspace.metadata()
        if self.unread_button.isChecked() or self.view == "history":
            self.render_news()
        elif key in self.cards:
            self.cards[key].set_read(read)

    def toggle_saved_story(self, article):
        key = article_key(article)
        if key in self.saved_stories:
            self.saved_stories.pop(key, None)
            message = tr("Removed from your reading list")
        else:
            self.saved_stories[key] = dict(article)
            message = tr("Saved to your reading list")
        try:
            store_saved_stories(self.saved_stories)
        except OSError as exc:
            QMessageBox.warning(self, tr("Could not save story"), str(exc))
            return
        self.update_saved_count()
        self.set_status(message)
        if self.view == "saved":
            self.render_news()
        elif key in self.cards:
            self.cards[key].set_saved(key in self.saved_stories)

    # ================================================================ tools

    def write_briefing(self):
        stories = self.index.stories(self.matching(), state.language, 14)
        if not stories:
            QMessageBox.information(self, tr("Write AI briefing"), tr("No stories are available in this view."))
            return
        from .summary import SummaryDialog
        run_dialog(SummaryDialog([], self, news=self.news, stories=stories))
        self.check_ai()

    def ask_ai(self):
        question = self.search.text().strip()
        if not question:
            self.search.setFocus()
            self.set_status(tr("Type a question in the search box, then press Ask AI."))
            return
        pool = self.news + list(self.saved_stories.values()) + self.workspace.research_articles()
        found = [article for _score, article in SearchIndex(pool).search(question, limit=10)]
        if not found:
            QMessageBox.information(self, tr("Ask AI"), tr("No loaded stories match this question. Try other words "
                                                           "or refresh."))
            return
        from .summary import SummaryDialog
        run_dialog(SummaryDialog(found, self, news=self.news, question=question))
        self.after_reading()
        self.check_ai()

    def maybe_warm_up(self, text: str):
        """Load the model while the reader is still typing a question."""
        status = self.ai_status
        if (not text.strip().endswith("?") or status is None or status.state != "ready"
                or time.monotonic() - self._last_warm_up < 300):
            return
        self._last_warm_up = time.monotonic()
        self.utility_pool.start(FunctionJob(ai.warm_up, status.model, settings.text("ai_keep_alive")))

    def check_watch_alerts(self, fresh: list[dict]):
        """Count new stories for each saved search and tell the reader once per refresh."""
        if not fresh:
            return
        hits = {}
        for name, query in self.workspace.watches().items():
            tokens = query_tokens(query)
            count = sum(1 for article in fresh if matches_query(article, tokens,
                                                                self.research_metadata.get(article_key(article), {}),
                                                                article_key(article) in self.saved_stories))
            if count:
                hits[name] = count
                self.watch_alerts[name] = self.watch_alerts.get(name, 0) + count
        if not hits:
            return
        self.reload_watches()
        if settings.flag("notify_watches"):
            text = " · ".join(f"{name}: {count}" for name, count in hits.items())
            self.notify(tr("New stories for your saved searches"), text)

    def notify(self, title: str, text: str):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.set_status(f"{title}: {text}")
            return
        if self.tray is None:
            self.tray = QSystemTrayIcon(self.windowIcon() or QApplication.windowIcon(), self)
            self.tray.setToolTip("Euro Info")
            self.tray.activated.connect(lambda _reason: (self.showNormal(), self.raise_(), self.activateWindow()))
            self.tray.show()
        self.tray.showMessage(title, text, QSystemTrayIcon.MessageIcon.Information, 8000)

    def _load_source_selection(self) -> set[str]:
        """Selected sources, upgraded once when the catalogue changes."""
        names = set(sources.SOURCE_BY_NAME)
        stored = settings.get().value("selected_sources", None)
        if isinstance(stored, str):
            stored = [stored]
        version = settings.number("catalogue_version")
        if not stored:
            selected = sources.default_selection(state.language)
        elif version < sources.CATALOGUE_VERSION:
            selected = sources.default_selection(state.language) | (set(stored) & names)
            region = settings.text("coverage_region")
            if region not in dict(REGIONS):
                settings.put("coverage_region", "ALL")
                self.current_region = "ALL"
        else:
            selected = set(stored) & names or sources.default_selection(state.language)
        settings.put("selected_sources", sorted(selected))
        settings.put("catalogue_version", sources.CATALOGUE_VERSION)
        return selected

    def create_daily_brief(self):
        articles = []
        for group in feeds.cluster_stories(self.filtered_news()):
            articles.extend(group[:2])  # a little outlet diversity, bounded prompt size
            if len(articles) >= 12:
                articles = articles[:12]
                break
        if not articles:
            QMessageBox.information(self, tr("Daily reader brief"), tr("No stories are available in this view."))
            return
        from .summary import SummaryDialog
        run_dialog(SummaryDialog(articles, self, news=self.news))
        self.check_ai()

    def copy_headlines(self):
        text = "\n".join(f"• {item.get('localized_title') or item.get('title', '')} — {item.get('source', '')}\n"
                         f"  {item.get('link', '')}" for item in self.filtered_news())
        if not text:
            QMessageBox.information(self, tr("Copy headlines"), tr("No stories are available in this view."))
            return
        QApplication.clipboard().setText(text)
        self.set_status(tr("Copied headlines to clipboard"))

    def show_news_quality(self):
        run_dialog(NewsQualityDialog(self))

    def choose_sources(self):
        dialog = SourceDialog(feeds.NEWS_SOURCES, self.selected_sources, self)
        try:
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            selected = set(dialog.selected())
            if not selected:
                QMessageBox.information(self, tr("Sources"), tr("Select at least one source."))
                return
            added = selected - self.selected_sources
            self.selected_sources = selected
            settings.put("selected_sources", sorted(selected))
            self.render_news()
            self.request_headline_translations()
            if added:
                self.refresh_data()
        finally:
            dialog.deleteLater()

    def open_settings(self):
        before = settings.text("translation_provider")
        dialog = SettingsDialog(self)
        try:
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.apply_refresh_interval()
                if settings.text("translation_provider") != before:
                    self.translation_attempted.clear()
                    self.translation_banner.hide()
                    self.request_headline_translations()
                self.check_ai()
        finally:
            dialog.deleteLater()

    def show_shortcuts(self):
        rows = [("F5", tr("Refresh")), ("Ctrl+K, /", tr("Search stories...")), ("Ctrl+1 … Ctrl+5", tr("Your desk")), ("J / K", tr("Next or previous story")),
                ("Ctrl+Enter", tr("Ask AI")),
                ("Ctrl+,", tr("Settings")), ("Ctrl+Shift+E", tr("Export current view")),
                ("Enter", tr("Read")), ("S", tr("Save for later")), ("Ctrl+ / Ctrl−", tr("Larger text")),
                ("Esc", tr("Clear search")), ("Ctrl+Q", tr("Quit"))]
        table = "".join(f"<tr><td><b>{keys}</b></td><td>&nbsp;&nbsp;{label}</td></tr>" for keys, label in rows)
        QMessageBox.information(self, tr("Keyboard shortcuts"), f"<table>{table}</table>")

    # ================================================================ saved searches

    def reload_watches(self):
        self.watch_combo.blockSignals(True)
        self.watch_combo.clear()
        self.watch_combo.addItem(tr("Saved searches"), "")
        for name, query in self.workspace.watches().items():
            count = self.watch_alerts.get(name, 0) if hasattr(self, "watch_alerts") else 0
            self.watch_combo.addItem(f"{name}  ({count} {tr('new')})" if count else name, query)
        self.watch_combo.blockSignals(False)

    def select_watch(self, index):
        query = self.watch_combo.itemData(index)
        if query:
            name = self.watch_combo.itemText(index).split("  (")[0]
            self.watch_alerts.pop(name, None)
            self.search.setText(query)
            self.view = "latest"
            self.nav_buttons["latest"].setChecked(True)
            self.reload_watches()

    def save_watch(self):
        if not self.search.text().strip():
            self.search.setFocus()
            return
        name, accepted = QInputDialog.getText(self, tr("Save current search"), tr("Name"))
        if accepted:
            try:
                self.workspace.save_watch(name, self.search.text())
                self.reload_watches()
            except Exception as exc:  # invalid names and storage errors
                QMessageBox.warning(self, tr("Saved searches"), str(exc))

    def remove_watch(self):
        if self.watch_combo.currentIndex() > 0:
            self.workspace.remove_watch(self.watch_combo.currentText().split("  (")[0])
            self.reload_watches()

    # ================================================================ files

    def export_view(self):
        articles = self.filtered_news()
        if not articles:
            QMessageBox.information(self, tr("Export current view"), tr("No stories are available in this view."))
            return
        path, chosen = QFileDialog.getSaveFileName(self, tr("Export current view"), "euro-info-research.md",
                                                   "Markdown (*.md);;CSV (*.csv)")
        if path:
            try:
                Path(path).write_text(export_articles(articles, self.research_metadata, article_key,
                                                      "csv" if "CSV" in chosen else "markdown"), encoding="utf-8")
                self.set_status(tr("Export complete"))
            except OSError as exc:
                QMessageBox.warning(self, tr("Export current view"), str(exc))

    def backup_library(self):
        path, _ = QFileDialog.getSaveFileName(self, tr("Backup reading list"), "euro-info-library.json", "JSON (*.json)")
        if not path:
            return
        try:
            library = {article_key(item): item for item in self.workspace.research_articles()}
            library.update(self.saved_stories)
            payload = {"schema": 2, "stories": list(library.values()), "saved_keys": list(self.saved_stories),
                       "metadata": self.research_metadata, "watches": self.workspace.watches()}
            Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            self.set_status(tr("Export complete"))
        except Exception as exc:  # disk and database errors
            QMessageBox.warning(self, tr("Backup reading list"), str(exc))

    def import_library(self):
        path, _ = QFileDialog.getOpenFileName(self, tr("Import reading list"), "", "JSON (*.json)")
        if not path:
            return
        try:
            imported = validate_library_backup(Path(path))
            for item in imported["stories"]:
                key = article_key(item)
                if key in imported["saved_keys"]:
                    self.saved_stories[key] = item
                incoming = imported["metadata"].get(key)
                if incoming:
                    existing = self.research_metadata.get(key, {})
                    self.workspace.save_story(
                        key, item, notes=existing.get("notes") or incoming.get("notes", ""),
                        tags=set(existing.get("tags", [])) | set(incoming.get("tags", [])),
                        read=bool(existing.get("read_at") or incoming.get("read_at")))
            for name, query in imported["watches"].items():
                self.workspace.save_watch(name, query)
            store_saved_stories(self.saved_stories)
            self.research_metadata = self.workspace.metadata()
            self.reload_watches()
            self.update_saved_count()
            self.render_news()
        except Exception as exc:  # validation, disk and database errors
            QMessageBox.warning(self, tr("Import reading list"), str(exc))

    # ================================================================ translation

    def translation_provider(self) -> str:
        provider = settings.text("translation_provider")
        return provider if provider in translation.PROVIDERS else "off"

    def maybe_offer_translation(self):
        if state.language == "en" or settings.text("translation_provider"):
            self.translation_banner.hide()
            return
        self.translation_banner.show_message(
            tr("Headlines stay in their original language. Translate them into your language?"),
            [(tr("Local AI (private)"), lambda: self.choose_translation("local"), True),
             (tr("Google (sends headlines online)"), lambda: self.choose_translation("google"), False),
             (tr("Keep original"), lambda: self.choose_translation("off"), False)])

    def choose_translation(self, provider: str):
        settings.put("translation_provider", provider)
        self.translation_banner.hide()
        self.translation_attempted.clear()
        self.request_headline_translations()

    def request_headline_translations(self):
        provider = self.translation_provider()
        if state.language == "en" or provider == "off" or not self.news or self.translation_job is not None:
            return
        visible = self.filtered_news()[:self.visible_story_limit]
        batch = select_translation_batch(visible, state.language, self.translation_attempted,
                                         min(PAGE_SIZE, len(visible)))
        if not batch:
            return
        job = TranslationJob(batch, state.language, provider, settings.text("ai_model"), settings.text("ai_keep_alive"))
        job.signals.progress.connect(self.apply_translations)
        job.signals.finished.connect(self.translations_finished)
        self.translation_job = job
        self.set_status(tr("Translating headlines…") + (f" · {tr('Local AI')}" if provider == "local" else ""))
        self.translation_pool.start(job)

    @Slot(object)
    def apply_translations(self, translations: dict):
        if not translations:
            return
        for article in self.news + list(self.saved_stories.values()):
            localized = translations.get(article_key(article))
            if localized:
                article["localized_title"], article["localized_summary"] = localized
        for key, (title, summary) in translations.items():
            card = self.cards.get(key) or self._card_cache.get(key)
            if card is not None:
                card.set_localized(title, summary)

    @Slot(object)
    def translations_finished(self, result: dict):
        self.translation_job = None
        if result["target"] != state.language:
            self.request_headline_translations()
            return
        self.apply_translations(result["results"])
        if result["error"]:
            self.set_status(tr("Translation stopped") + ": " + result["error"])
            return
        self.set_status(f"{len(result['results'])} {tr('headlines translated')}")
        self.request_headline_translations()

    # ================================================================ local AI status

    def check_ai(self):
        job = FunctionJob(ai.status, settings.text("ai_model"))
        job.signals.finished.connect(self.show_ai_status)
        job.signals.failed.connect(lambda message: self.ai_button.show_state("error", tr("Local AI unavailable"), message))
        self.utility_pool.start(job)

    @Slot(object)
    def show_ai_status(self, status: ai.Status):
        self.ai_status = status
        texts = {
            "ready": (f"{tr('Local AI')} · {status.model}", tr("Ready for analysis and private translation.")),
            "stopped": (tr("Local AI is off"), tr("Click to start Ollama.")),
            "no-model": (tr("No AI model installed"), tr("Click to install {model} ({size}).").format(
                model=ai.RECOMMENDED_MODEL, size=ai.RECOMMENDED_MODEL_SIZE)),
            "missing": (tr("Ollama not installed"), tr("Click to open the Ollama download page.")),
            "error": (tr("Local AI unavailable"), status.detail),
        }
        text, tip = texts.get(status.state, (tr("Checking local AI…"), ""))
        if status.state == "no-model" and status.models:
            tip = tr(status.detail) + "\n" + tip
        self.ai_button.show_state(status.state, text, tip)

    def show_ai_menu(self):
        menu = QMenu(self)
        status = self.ai_status
        if status and status.state == "stopped":
            menu.addAction(icon("sparkle"), tr("Start local AI"), self.start_ai)
        elif status and status.state == "no-model":
            menu.addAction(icon("download"), tr("Install {model}").format(model=ai.RECOMMENDED_MODEL), self.install_model)
        elif status and status.state == "missing":
            menu.addAction(icon("external"), tr("Download Ollama"), lambda: open_url(ai.DOWNLOAD_PAGE))
        if status and status.state == "ready" and ai.started_by_app():
            menu.addAction(icon("close"), tr("Stop local AI"), self.stop_ai)
        menu.addAction(icon("refresh"), tr("Check again"), self.check_ai)
        menu.addSeparator()
        menu.addAction(icon("sliders"), tr("Settings"), self.open_settings)
        menu.addAction(icon("layers"), tr("Diagnostics"), lambda: run_dialog(DiagnosticsDialog(self)))
        menu.exec(self.ai_button.mapToGlobal(QPoint(0, -menu.sizeHint().height() - 4)))

    def start_ai(self):
        self.ai_button.show_state("checking", tr("Starting local AI…"))
        job = FunctionJob(ai.start_service)
        job.signals.finished.connect(lambda _how: self.check_ai())
        job.signals.failed.connect(lambda message: (self.ai_button.show_state("error", tr("Local AI unavailable"),
                                                                               message), self.set_status(message)))
        self.utility_pool.start(job)

    def stop_ai(self):
        ai.stop_if_started()
        self.check_ai()

    def install_model(self):
        answer = QMessageBox.question(self, tr("Install local AI model"), tr(
            "Download {model} ({size}) through Ollama? It runs entirely on this computer.").format(
            model=ai.RECOMMENDED_MODEL, size=ai.RECOMMENDED_MODEL_SIZE))
        if answer == QMessageBox.StandardButton.Yes:
            run_dialog(PullModelDialog(ai.RECOMMENDED_MODEL, self))
            self.check_ai()

    # ================================================================ updates

    def maybe_check_updates(self):
        if not settings.flag("check_updates"):
            return
        try:
            last = float(settings.get().value("last_update_check", 0) or 0)
        except (TypeError, ValueError):
            last = 0
        if time.time() - last >= updates.CHECK_INTERVAL_SECONDS:
            self.check_updates(manual=False)

    def check_updates(self, manual: bool = False):
        if not manual:
            settings.put("last_update_check", time.time())
        job = FunctionJob(updates.check)
        job.signals.finished.connect(lambda release: self.update_checked(release, manual))
        job.signals.failed.connect(lambda message: manual and QMessageBox.information(
            self, tr("Check for updates"), tr("Could not reach GitHub") + f": {message}"))
        self.utility_pool.start(job)

    def update_checked(self, release, manual: bool):
        settings.put("last_update_check", time.time())
        if release is None:
            if manual:
                QMessageBox.information(self, tr("Check for updates"),
                                        tr("Euro Info {version} is up to date.").format(version=__version__))
            return
        if not manual and settings.text("skipped_update_version") == release.version:
            return
        self.update_banner.show_message(
            tr("Euro Info {version} is available. You have {current}.").format(version=release.version,
                                                                               current=__version__),
            [(tr("View release"), lambda: open_url(release.url), True),
             (tr("Skip this version"), lambda: (settings.put("skipped_update_version", release.version),
                                                self.update_banner.hide()), False)])

    # ================================================================ closing

    def closeEvent(self, event):
        if self.translation_job is not None:
            self.translation_job.cancelled = True
        translation.save_cache()
        save_seen({article_key(item) for item in self.news} | (self.seen_keys if len(self.seen_keys) < 4000 else set()))
        if self.tray is not None:
            self.tray.hide()
        if settings.flag("ai_stop_on_exit") and ai.started_by_app():
            ai.stop_if_started()
        settings.get().sync()
        event.accept()

