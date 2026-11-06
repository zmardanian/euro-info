"""Design tokens and the generated Qt stylesheet for the three reading themes."""
from __future__ import annotations

THEMES = ("standard", "paper", "night")

PALETTES = {
    "standard": dict(
        bg="#F4F2EE", surface="#FFFFFF", surface_alt="#F8F6F2", border="#E4DFD5", border_strong="#CFC6B4",
        ink="#16202A", ink_soft="#2F3C48", muted="#5E6873", faint="#848C94",
        accent="#1F5C8B", accent_soft="#E5EEF6", gold="#9D7A35", gold_soft="#F2EBDC",
        primary="#1C3A52", primary_ink="#FFFFFF", primary_hover="#132C40",
        sidebar="#0F1D2B", sidebar_ink="#C9D4DE", sidebar_muted="#8398AB", sidebar_hover="#172A3C",
        sidebar_active="#21405C", sidebar_border="#182A3B", star="#C98216",
        success="#2E7D4F", warning="#B26F12", danger="#B4443A", selection="#CFE1F0", scroll="#C9D0D7",
    ),
    "paper": dict(
        bg="#EEE6D5", surface="#F8F2E5", surface_alt="#F2EAD9", border="#DCCFB3", border_strong="#C8B690",
        ink="#2D2920", ink_soft="#423B2F", muted="#675F50", faint="#887F6C",
        accent="#2F5E7E", accent_soft="#E5DDC9", gold="#946F2E", gold_soft="#E8DCC1",
        primary="#4A3B22", primary_ink="#FBF6EA", primary_hover="#3A2E1A",
        sidebar="#2A2318", sidebar_ink="#E9DFCB", sidebar_muted="#B3A68C", sidebar_hover="#382F21",
        sidebar_active="#4B3E29", sidebar_border="#372E20", star="#B97A1A",
        success="#3E7A45", warning="#A86A12", danger="#A6473A", selection="#E3D2AA", scroll="#CDBF9F",
    ),
    "night": dict(
        bg="#111518", surface="#191E22", surface_alt="#20262B", border="#283036", border_strong="#3A444C",
        ink="#ECE8DF", ink_soft="#D3CEC3", muted="#A5A8A1", faint="#868B87",
        accent="#8EC3E6", accent_soft="#1C2C38", gold="#D5B66E", gold_soft="#2B2719",
        primary="#2F5873", primary_ink="#F4F1EA", primary_hover="#3A6B8C",
        sidebar="#0B0F12", sidebar_ink="#CED4D7", sidebar_muted="#8B969C", sidebar_hover="#151B20",
        sidebar_active="#1F2D38", sidebar_border="#182027", star="#E3A73F",
        success="#6FBF8A", warning="#E0A84A", danger="#E07A6E", selection="#2E4A5E", scroll="#3A444C",
    ),
}


def palette(mode: str) -> dict[str, str]:
    return PALETTES.get(mode, PALETTES["standard"])


def sizes(compact: bool, large: bool) -> dict[str, int]:
    bump = 3 if large else 0
    return dict(
        base=13 if compact else 14,
        small=12 if compact else 12,
        story=(17 if compact else 19) + bump,
        featured=(23 if compact else 30) + bump,
        excerpt=(13 if compact else 14) + (1 if large else 0),
        masthead=26 if compact else 30,
        section=18 if compact else 20,
        pad=6 if compact else 9,
    )


def stylesheet(mode: str = "standard", compact: bool = False, large: bool = False) -> str:
    p, s = palette(mode), sizes(compact, large)
    return f"""
* {{ outline: none; }}
QWidget {{ font-size:{s['base']}px; color:{p['ink_soft']}; }}
QMainWindow, QWidget#central, QWidget#content, QWidget#newsContainer, QDialog {{ background:{p['bg']}; }}
QLabel {{ background:transparent; border:none; color:{p['ink_soft']}; }}
QToolTip {{ background:{p['sidebar']}; color:{p['sidebar_ink']}; border:1px solid {p['sidebar_border']};
           padding:6px 8px; border-radius:6px; }}

/* Sidebar */
QFrame#sidebar {{ background:{p['sidebar']}; border-right:1px solid {p['sidebar_border']}; }}
QFrame#sidebar QLabel {{ color:{p['sidebar_ink']}; }}
QLabel#brand {{ color:#FFFFFF; font-size:19px; font-weight:800; letter-spacing:2px; }}
QLabel#brandSubtitle {{ color:{p['sidebar_muted']}; font-size:11px; font-weight:600; letter-spacing:1px; }}
QLabel#sideSection {{ color:{p['sidebar_muted']}; font-size:11px; font-weight:800; letter-spacing:1.4px;
                      padding:14px 10px 4px 10px; }}
QLabel#sideHint {{ color:{p['sidebar_muted']}; font-size:12px; padding:0 10px; }}
QLabel#sideVersion {{ color:{p['sidebar_muted']}; font-size:11px; padding:0 10px; }}
QPushButton#sideNav, QToolButton#sideNav {{ text-align:left; color:{p['sidebar_ink']}; background:transparent;
    border:0; border-radius:8px; padding:{s['pad'] - 1}px 10px; font-size:{s['base']}px; font-weight:600; }}
QPushButton#sideNav:hover {{ background:{p['sidebar_hover']}; color:#FFFFFF; }}
QPushButton#sideNav:checked {{ background:{p['sidebar_active']}; color:#FFFFFF; }}
QPushButton#sideNav:focus {{ background:{p['sidebar_hover']}; }}
QLabel#navBadge {{ color:{p['sidebar_ink']}; background:{p['sidebar_hover']}; border-radius:8px; padding:1px 7px;
                   font-size:11px; font-weight:700; }}
QComboBox#sideCombo {{ background:{p['sidebar_hover']}; border:1px solid {p['sidebar_border']};
                       color:{p['sidebar_ink']}; border-radius:8px; padding:6px 9px; }}
QComboBox#sideCombo:hover {{ border-color:{p['sidebar_muted']}; }}
QPushButton#aiStatus {{ text-align:left; background:{p['sidebar_hover']}; color:{p['sidebar_ink']};
    border:1px solid {p['sidebar_border']}; border-radius:10px; padding:8px 10px; font-size:12px; font-weight:600; }}
QPushButton#aiStatus:hover {{ border-color:{p['sidebar_muted']}; }}

/* Masthead and header */
QLabel#mastheadTitle {{ color:{p['ink']}; font-family:'Newsreader'; font-size:{s['masthead']}px; font-weight:700; }}
QLabel#subtitle {{ color:{p['muted']}; font-size:13px; }}
QLabel#section {{ color:{p['ink']}; font-family:'Newsreader'; font-size:{s['section']}px; font-weight:700; }}
QLabel#muted, QLabel#storyCount {{ color:{p['muted']}; font-size:12px; }}
QLineEdit#search {{ background:{p['surface']}; border:1px solid {p['border']}; border-radius:10px;
                    padding:8px 12px 8px 6px; font-size:{s['base']}px; color:{p['ink']}; min-width:300px; }}
QLineEdit#search:focus {{ border-color:{p['accent']}; }}

/* Info strip */
QFrame#infoStrip {{ background:{p['surface']}; border:1px solid {p['border']}; border-radius:10px; }}
QLabel#stripSection {{ color:{p['gold']}; font-size:10px; font-weight:900; letter-spacing:1.2px; }}
QLabel#stripMetric, QLabel#stripRate {{ color:{p['ink_soft']}; font-size:12px; font-weight:700; }}
QLabel#stripDate {{ color:{p['faint']}; font-size:11px; }}
QFrame#stripDivider {{ background:{p['border']}; max-width:1px; min-width:1px; border:none; }}

/* Banners */
QFrame#banner {{ background:{p['accent_soft']}; border:1px solid {p['border']}; border-radius:10px; }}
QFrame#banner QLabel {{ color:{p['ink_soft']}; }}

/* Filter chips */
QPushButton#chip {{ background:transparent; border:1px solid {p['border']}; border-radius:15px;
                    padding:4px 13px; color:{p['muted']}; font-weight:600; min-height:20px; }}
QPushButton#chip:hover {{ border-color:{p['border_strong']}; color:{p['ink']}; }}
QPushButton#chip:checked {{ background:{p['ink']}; border-color:{p['ink']}; color:{p['bg']}; }}

/* Cards */
QFrame#newsCard, QFrame#featuredStory {{ background:{p['surface']}; border:1px solid {p['border']}; border-radius:12px; }}
QFrame#newsCard:hover {{ border-color:{p['border_strong']}; }}
QFrame#newsCard:focus, QFrame#featuredStory:focus {{ border:2px solid {p['accent']}; }}
QFrame#featuredStory {{ border-color:{p['border_strong']}; }}
QLabel#thumb {{ background:{p['surface_alt']}; border-radius:8px; }}
QLabel#kicker {{ color:{p['gold']}; font-size:11px; font-weight:900; letter-spacing:1.3px; }}
QLabel#storySource {{ color:{p['accent']}; font-size:12px; font-weight:700; }}
QLabel#storyMeta {{ color:{p['faint']}; font-size:12px; }}
QLabel#categoryTag {{ color:{p['gold']}; background:{p['gold_soft']}; border-radius:5px; padding:1px 7px;
                      font-size:11px; font-weight:700; }}
QLabel#readTag {{ color:{p['success']}; font-size:11px; font-weight:700; }}
QLabel#newTag {{ color:{p['primary_ink']}; background:{p['accent']}; border-radius:5px; padding:1px 6px;
                 font-size:10px; font-weight:800; }}
QLabel#regionTag {{ color:{p['accent']}; background:{p['accent_soft']}; border-radius:5px; padding:1px 7px;
                    font-size:11px; font-weight:700; }}
QLabel#rankTag {{ color:{p['faint']}; font-size:12px; font-weight:800; font-family:'Newsreader'; }}
QLabel#importanceTag {{ color:{p['ink']}; background:{p['surface_alt']}; border:1px solid {p['border']};
                        border-radius:9px; padding:1px 8px; font-size:11px; font-weight:800; }}
QLabel#trendLabel {{ color:{p['gold']}; font-size:10px; font-weight:900; letter-spacing:1.2px; }}
QPushButton#trendChip {{ background:transparent; border:0; color:{p['accent']}; padding:2px 6px;
                         font-weight:700; min-height:16px; }}
QPushButton#trendChip:hover {{ text-decoration:underline; }}
QPushButton#trendChip:checked {{ background:{p['accent_soft']}; border-radius:6px; }}
QLabel#briefingTitle {{ color:{p['ink']}; font-family:'Newsreader'; font-size:{s['section'] + 2}px; font-weight:700; }}
QLabel#storyTitle {{ color:{p['ink']}; font-family:'Newsreader'; font-size:{s['story']}px; font-weight:600; }}
QLabel#storyTitle[read="true"] {{ color:{p['muted']}; }}
QLabel#featuredTitle {{ color:{p['ink']}; font-family:'Newsreader'; font-size:{s['featured']}px; font-weight:700; }}
QLabel#storyExcerpt {{ color:{p['muted']}; font-size:{s['excerpt']}px; }}
QLabel#featuredSummary {{ color:{p['muted']}; font-size:{s['excerpt'] + 1}px; }}
QToolButton#cardAction {{ background:transparent; border:1px solid transparent; border-radius:7px; padding:3px; }}
QToolButton#cardAction:hover {{ background:{p['surface_alt']}; border-color:{p['border']}; }}
QToolButton#cardAction:checked {{ background:transparent; }}
QToolButton#cardAction::menu-indicator {{ image:none; width:0; }}
QPushButton#coverageChip {{ background:{p['accent_soft']}; color:{p['accent']}; border:0; border-radius:6px;
                            padding:3px 9px; font-size:11px; font-weight:700; min-height:16px; }}
QPushButton#coverageChip:hover {{ background:{p['selection']}; }}
QPushButton#linkButton {{ background:transparent; border:0; color:{p['accent']}; padding:2px 4px; font-weight:600; }}
QPushButton#linkButton:hover {{ text-decoration:underline; }}
QLabel#emptyState {{ color:{p['muted']}; background:{p['surface']}; border:1px dashed {p['border_strong']};
                     border-radius:12px; padding:44px; font-size:14px; }}

/* Generic controls */
QPushButton, QToolButton {{ background:{p['surface']}; border:1px solid {p['border']}; border-radius:8px;
    color:{p['ink_soft']}; padding:6px 12px; font-weight:600; min-height:18px; }}
QPushButton:hover, QToolButton:hover {{ border-color:{p['border_strong']}; background:{p['surface_alt']}; }}
QPushButton:checked, QToolButton:checked {{ background:{p['gold_soft']}; border-color:{p['gold']}; color:{p['ink']}; }}
QPushButton:disabled, QToolButton:disabled {{ color:{p['faint']}; background:{p['surface_alt']}; }}
QPushButton:focus, QToolButton:focus, QComboBox:focus {{ border:1px solid {p['accent']}; }}
QPushButton#primary {{ background:{p['primary']}; color:{p['primary_ink']}; border:0; padding:7px 15px; }}
QPushButton#primary:hover {{ background:{p['primary_hover']}; }}
QToolButton#iconButton {{ padding:6px; border-radius:9px; }}
QToolButton::menu-indicator {{ image:none; width:0; }}
QComboBox {{ background:{p['surface']}; border:1px solid {p['border']}; border-radius:8px; padding:5px 10px;
             color:{p['ink_soft']}; min-height:18px; }}
QComboBox:hover {{ border-color:{p['border_strong']}; }}
QComboBox::drop-down {{ border:0; width:20px; }}
QComboBox QAbstractItemView {{ background:{p['surface']}; color:{p['ink_soft']}; border:1px solid {p['border']};
                               selection-background-color:{p['selection']}; selection-color:{p['ink']}; }}
QLineEdit, QPlainTextEdit {{ background:{p['surface']}; border:1px solid {p['border']}; border-radius:8px;
    padding:7px 10px; color:{p['ink']}; selection-background-color:{p['selection']}; selection-color:{p['ink']}; }}
QLineEdit:focus, QPlainTextEdit:focus {{ border-color:{p['accent']}; }}
QTextBrowser {{ background:{p['surface']}; border:1px solid {p['border']}; border-radius:10px; color:{p['ink_soft']};
                padding:10px; selection-background-color:{p['selection']}; }}
QTextBrowser#analysisOutput {{ padding:22px; }}
QListWidget {{ background:{p['surface']}; border:1px solid {p['border']}; border-radius:10px; color:{p['ink_soft']};
               padding:4px; }}
QListWidget::item {{ padding:8px; border-radius:6px; }}
QListWidget::item:selected {{ background:{p['selection']}; color:{p['ink']}; }}
QCheckBox {{ color:{p['ink_soft']}; spacing:8px; }}
QProgressBar {{ background:{p['border']}; border:none; border-radius:2px; }}
QProgressBar::chunk {{ background:{p['gold']}; border-radius:2px; }}
QMenuBar {{ background:{p['bg']}; color:{p['ink_soft']}; }}
QMenuBar::item:selected {{ background:{p['surface_alt']}; }}
QMenu {{ background:{p['surface']}; color:{p['ink_soft']}; border:1px solid {p['border']}; padding:5px;
         border-radius:8px; }}
QMenu::item {{ padding:6px 22px 6px 12px; border-radius:5px; }}
QMenu::item:selected {{ background:{p['selection']}; color:{p['ink']}; }}
QMenu::separator {{ height:1px; background:{p['border']}; margin:4px 6px; }}
QStatusBar {{ background:{p['bg']}; color:{p['muted']}; border-top:1px solid {p['border']}; }}
QStatusBar QLabel {{ color:{p['muted']}; font-size:12px; padding:0 6px; }}
QScrollArea {{ background:transparent; border:none; }}
QScrollBar:vertical {{ background:transparent; width:11px; margin:2px; }}
QScrollBar::handle:vertical {{ background:{p['scroll']}; border-radius:4px; min-height:36px; }}
QScrollBar::handle:vertical:hover {{ background:{p['border_strong']}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background:transparent; }}
QLabel#dialogTitle {{ color:{p['ink']}; font-family:'Newsreader'; font-size:26px; font-weight:700; }}
QLabel#articleHeading {{ color:{p['ink']}; font-family:'Newsreader'; font-size:24px; font-weight:700; padding:4px 2px; }}
QLabel#articleMeta {{ color:{p['muted']}; padding:0 2px 6px; }}
"""


def analysis_css(mode: str, reading_size: int) -> str:
    p = palette(mode)
    return (f"body {{color:{p['ink_soft']};font-size:{reading_size}px;}} "
            f"p,li {{font-size:{reading_size}px;line-height:150%;margin-bottom:12px;}} "
            f"h2 {{font-family:Newsreader;color:{p['ink']};font-size:{reading_size + 7}px;"
            f"margin-top:22px;margin-bottom:10px;}} "
            f"a {{color:{p['accent']};font-weight:bold;text-decoration:none;}} ul {{margin-left:18px;}}")
