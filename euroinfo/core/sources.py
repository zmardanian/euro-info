"""The news source catalogue: all of Europe, US politics and economy, global technology.

Every feed was checked live for current entries (catalogue version 4).
region    EUROPE, US or GLOBAL: where the coverage is centred
country   publisher base, used only as a ranking hint, never to hide stories
language  feed language; English feeds and feeds in the reader's language are on by default
topic     the source's main subject (POLITICS, ECONOMY, TECHNOLOGY) or "" for general news
"""
from __future__ import annotations

CATALOGUE_VERSION = 4


def _source(name, url, region, country, language="en", topic="", kind="Newsroom", family=None,
            access="Access not verified", specialty=None):
    return {"name": name, "url": url, "region": region, "country": country, "language": language,
            "topic": topic, "kind": kind, "publisher_family": family or name, "access": access,
            "specialty": specialty or {"POLITICS": "Politics", "ECONOMY": "Economic",
                                       "TECHNOLOGY": "Technology"}.get(topic, "General affairs")}


PAYWALL = "May require subscription"
OFFICIAL = "Official source"
RESEARCH = "Research and commentary"
PROJECT = "Project publication"

NEWS_SOURCES = [
    # European Union affairs and pan-European desks
    _source("POLITICO Europe", "https://www.politico.eu/feed/", "EUROPE", "EU", topic="POLITICS", family="POLITICO"),
    _source("EUobserver", "https://euobserver.com/feed/", "EUROPE", "EU", topic="POLITICS"),
    _source("Euractiv", "https://www.euractiv.com/feed/", "EUROPE", "EU", topic="POLITICS"),
    _source("European Commission", "https://ec.europa.eu/commission/presscorner/api/rss?language=en", "EUROPE", "EU",
            topic="POLITICS", kind=OFFICIAL),
    _source("Euronews", "https://www.euronews.com/rss?level=theme&name=news", "EUROPE", "EU", family="Euronews"),
    _source("Euronews Business", "https://www.euronews.com/rss?level=vertical&name=business", "EUROPE", "EU",
            topic="ECONOMY", family="Euronews"),
    _source("Euronews Next", "https://www.euronews.com/rss?level=vertical&name=next", "EUROPE", "EU",
            topic="TECHNOLOGY", family="Euronews"),
    _source("European Central Bank", "https://www.ecb.europa.eu/rss/press.html", "EUROPE", "EU", topic="ECONOMY",
            kind=OFFICIAL),
    _source("VoxEU (CEPR)", "https://cepr.org/rss/vox-content", "EUROPE", "EU", topic="ECONOMY", kind=RESEARCH),
    _source("BBC Europe", "https://feeds.bbci.co.uk/news/world/europe/rss.xml", "EUROPE", "GB", family="BBC"),
    _source("Deutsche Welle Europe", "https://rss.dw.com/rdf/rss-en-eu", "EUROPE", "DE", family="Deutsche Welle"),
    _source("Deutsche Welle Business", "https://rss.dw.com/rdf/rss-en-bus", "EUROPE", "DE", topic="ECONOMY",
            family="Deutsche Welle"),
    _source("The Guardian Europe", "https://www.theguardian.com/world/europe-news/rss", "EUROPE", "GB",
            family="The Guardian"),
    _source("France 24 Europe", "https://www.france24.com/en/europe/rss", "EUROPE", "FR", family="France 24"),
    _source("Le Monde Europe (English)", "https://www.lemonde.fr/en/europe/rss_full.xml", "EUROPE", "FR",
            family="Le Monde", access=PAYWALL),
    _source("RFI", "https://www.rfi.fr/en/rss", "EUROPE", "FR"),
    _source("Financial Times", "https://www.ft.com/europe?format=rss", "EUROPE", "GB", topic="ECONOMY", access=PAYWALL),
    _source("The Economist Europe", "https://www.economist.com/europe/rss.xml", "EUROPE", "GB",
            family="The Economist", access=PAYWALL),
    # National desks across Europe
    _source("Der Spiegel International", "https://www.spiegel.de/international/index.rss", "EUROPE", "DE",
            family="Der Spiegel"),
    _source("The Local Germany", "https://www.thelocal.de/feeds/rss.php", "EUROPE", "DE", family="The Local"),
    _source("Tagesschau", "https://www.tagesschau.de/xml/rss2/", "EUROPE", "DE", language="de", family="ARD"),
    _source("Le Monde", "https://www.lemonde.fr/rss/une.xml", "EUROPE", "FR", language="fr", family="Le Monde",
            access=PAYWALL),
    _source("The Local France", "https://www.thelocal.fr/feeds/rss.php", "EUROPE", "FR", family="The Local"),
    _source("ANSA English", "https://www.ansa.it/english/news/english_nr_rss.xml", "EUROPE", "IT"),
    _source("El País English", "https://feeds.elpais.com/mrss-s/pages/ep/site/english.elpais.com/portada",
            "EUROPE", "ES", family="El País"),
    _source("Portugal News", "https://www.theportugalnews.com/rss", "EUROPE", "PT"),
    _source("NOS", "https://feeds.nos.nl/nosnieuwsalgemeen", "EUROPE", "NL", language="nl"),
    _source("The Irish Times", "https://www.irishtimes.com/arc/outboundfeeds/feed-world/?outputType=xml",
            "EUROPE", "IE", access=PAYWALL),
    _source("RTÉ News", "https://www.rte.ie/feeds/rss/?index=/news/", "EUROPE", "IE"),
    _source("The Local Sweden", "https://www.thelocal.se/feeds/rss.php", "EUROPE", "SE", family="The Local"),
    _source("Yle News", "https://yle.fi/rss/t/18-34837/en", "EUROPE", "FI"),
    _source("ERR News", "https://news.err.ee/rss", "EUROPE", "EE"),
    _source("LRT English", "https://www.lrt.lt/en/news-in-english?rss", "EUROPE", "LT"),
    _source("Notes from Poland", "https://notesfrompoland.com/feed/", "EUROPE", "PL"),
    _source("Rzeczpospolita", "https://www.rp.pl/rss_main", "EUROPE", "PL", language="pl"),
    _source("Radio Prague International", "https://english.radio.cz/rcz-rss/en", "EUROPE", "CZ"),
    _source("Hungary Today", "https://hungarytoday.hu/feed/", "EUROPE", "HU"),
    _source("Greek Reporter", "https://greekreporter.com/feed/", "EUROPE", "GR"),
    _source("Balkan Insight", "https://balkaninsight.com/feed/", "EUROPE", "RS", family="BIRN"),
    _source("Kyiv Independent", "https://kyivindependent.com/news-archive/rss/", "EUROPE", "UA"),
    _source("Ukrainska Pravda", "https://www.pravda.com.ua/eng/rss/", "EUROPE", "UA"),
    _source("Meduza", "https://meduza.io/rss/en/all", "EUROPE", "LV"),
    _source("Romania Insider", "https://www.romania-insider.com/feed", "EUROPE", "RO"),
    _source("Digi24", "https://www.digi24.ro/rss", "EUROPE", "RO", language="ro"),
    _source("HotNews", "https://hotnews.ro/feed", "EUROPE", "RO", language="ro"),
    _source("G4Media", "https://www.g4media.ro/feed", "EUROPE", "RO", language="ro"),
    _source("Spotmedia", "https://spotmedia.ro/feed", "EUROPE", "RO", language="ro"),
    _source("Economedia", "https://economedia.ro/feed", "EUROPE", "RO", language="ro", topic="ECONOMY"),
    # United States: politics and economy that matter beyond the US
    _source("POLITICO US", "https://rss.politico.com/politics-news.xml", "US", "US", topic="POLITICS", family="POLITICO"),
    _source("NPR Politics", "https://feeds.npr.org/1014/rss.xml", "US", "US", topic="POLITICS", family="NPR"),
    _source("The Hill", "https://thehill.com/homenews/feed/", "US", "US", topic="POLITICS"),
    _source("The New York Times Politics", "https://rss.nytimes.com/services/xml/rss/nyt/Politics.xml", "US", "US",
            topic="POLITICS", family="The New York Times", access=PAYWALL),
    _source("The Guardian US Politics", "https://www.theguardian.com/us-news/us-politics/rss", "US", "GB",
            topic="POLITICS", family="The Guardian"),
    _source("PBS NewsHour Politics", "https://www.pbs.org/newshour/feeds/rss/politics", "US", "US", topic="POLITICS"),
    _source("CBS News Politics", "https://www.cbsnews.com/latest/rss/politics", "US", "US", topic="POLITICS"),
    _source("Axios", "https://api.axios.com/feed/", "US", "US"),
    _source("Bloomberg Politics", "https://feeds.bloomberg.com/politics/news.rss", "US", "US", topic="POLITICS",
            family="Bloomberg", access=PAYWALL),
    _source("Federal Reserve", "https://www.federalreserve.gov/feeds/press_all.xml", "US", "US", topic="ECONOMY",
            kind=OFFICIAL),
    _source("CNBC Economy", "https://www.cnbc.com/id/20910258/device/rss/rss.html", "US", "US", topic="ECONOMY",
            family="CNBC"),
    _source("MarketWatch", "https://feeds.content.dowjones.io/public/rss/mw_topstories", "US", "US", topic="ECONOMY"),
    _source("The New York Times Business", "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml", "US", "US",
            topic="ECONOMY", family="The New York Times", access=PAYWALL),
    # Global economy and markets
    _source("Bloomberg Markets", "https://feeds.bloomberg.com/markets/news.rss", "GLOBAL", "US", topic="ECONOMY",
            family="Bloomberg", access=PAYWALL),
    _source("CNBC World", "https://www.cnbc.com/id/100727362/device/rss/rss.html", "GLOBAL", "US", topic="ECONOMY",
            family="CNBC"),
    _source("The Economist Finance", "https://www.economist.com/finance-and-economics/rss.xml", "GLOBAL", "GB",
            topic="ECONOMY", family="The Economist", access=PAYWALL),
    _source("BBC Business", "https://feeds.bbci.co.uk/news/business/rss.xml", "GLOBAL", "GB", topic="ECONOMY",
            family="BBC"),
    _source("The Guardian Business", "https://www.theguardian.com/business/rss", "GLOBAL", "GB", topic="ECONOMY",
            family="The Guardian"),
    # Technology
    _source("Ars Technica", "https://arstechnica.com/feed/", "GLOBAL", "US", topic="TECHNOLOGY", access=PAYWALL),
    _source("The Verge", "https://www.theverge.com/rss/index.xml", "GLOBAL", "US", topic="TECHNOLOGY"),
    _source("Wired", "https://www.wired.com/feed/rss", "GLOBAL", "US", topic="TECHNOLOGY", access=PAYWALL),
    _source("TechCrunch", "https://techcrunch.com/feed/", "GLOBAL", "US", topic="TECHNOLOGY"),
    _source("MIT Technology Review", "https://www.technologyreview.com/feed/", "GLOBAL", "US", topic="TECHNOLOGY",
            access=PAYWALL),
    _source("Bloomberg Technology", "https://feeds.bloomberg.com/technology/news.rss", "GLOBAL", "US",
            topic="TECHNOLOGY", family="Bloomberg", access=PAYWALL),
    _source("BBC Technology", "https://feeds.bbci.co.uk/news/technology/rss.xml", "GLOBAL", "GB", topic="TECHNOLOGY",
            family="BBC"),
    _source("The Register", "https://www.theregister.com/headlines.atom", "GLOBAL", "GB", topic="TECHNOLOGY"),
    _source("Sifted", "https://sifted.eu/feed", "EUROPE", "GB", topic="TECHNOLOGY"),
    _source("Tech.eu", "https://tech.eu/feed/", "EUROPE", "EU", topic="TECHNOLOGY"),
    _source("Heise", "https://www.heise.de/rss/heise-atom.xml", "EUROPE", "DE", language="de", topic="TECHNOLOGY"),
    _source("Phoronix", "https://www.phoronix.com/rss.php", "GLOBAL", "US", topic="TECHNOLOGY", specialty="Linux"),
    _source("LWN", "https://lwn.net/headlines/rss", "GLOBAL", "US", topic="TECHNOLOGY", specialty="Linux",
            access=PAYWALL),
    _source("OMG! Ubuntu!", "https://www.omgubuntu.co.uk/feed", "GLOBAL", "GB", topic="TECHNOLOGY", specialty="Linux"),
    _source("Fedora Magazine", "https://fedoramagazine.org/feed/", "GLOBAL", "US", topic="TECHNOLOGY",
            specialty="Linux", kind=PROJECT, family="Fedora Project"),
    _source("Kernel Releases", "https://www.kernel.org/feeds/kdist.xml", "GLOBAL", "US", topic="TECHNOLOGY",
            specialty="Linux", kind=PROJECT, family="Linux Kernel Project"),
    _source("Nature AI", "https://www.nature.com/subjects/machine-learning.rss", "GLOBAL", "GB", topic="TECHNOLOGY",
            specialty="AI", kind=RESEARCH, family="Nature", access=PAYWALL),
    _source("Science News", "https://www.sciencenews.org/feed", "GLOBAL", "US", topic="TECHNOLOGY",
            specialty="Breakthroughs"),
    # Global desks
    _source("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml", "GLOBAL", "GB", family="BBC"),
    _source("The Guardian World", "https://www.theguardian.com/world/rss", "GLOBAL", "GB", family="The Guardian"),
    _source("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml", "GLOBAL", "QA"),
    _source("Deutsche Welle World", "https://rss.dw.com/rdf/rss-en-world", "GLOBAL", "DE", family="Deutsche Welle"),
    _source("France 24 World", "https://www.france24.com/en/rss", "GLOBAL", "FR", family="France 24"),
    _source("NPR World", "https://feeds.npr.org/1004/rss.xml", "GLOBAL", "US", family="NPR"),
    _source("The New York Times World", "https://rss.nytimes.com/services/xml/rss/nyt/World.xml", "GLOBAL", "US",
            family="The New York Times", access=PAYWALL),
    _source("Sky News World", "https://feeds.skynews.com/feeds/rss/world.xml", "GLOBAL", "GB"),
]

SOURCE_BY_NAME = {source["name"]: source for source in NEWS_SOURCES}
SOURCE_COUNTRIES = {source["name"]: source["country"] for source in NEWS_SOURCES}
REGIONS = ("EUROPE", "US", "GLOBAL")


def default_selection(language: str = "en") -> set[str]:
    """Sources switched on for a new reader: English feeds plus feeds in the reader's language."""
    return {source["name"] for source in NEWS_SOURCES if source["language"] in ("en", language)}


COUNTRY_TERMS = {
    "AL": ("albania", "albanian", "tirana"),
    "AT": ("austria", "austrian", "vienna", "wien"),
    "BA": ("bosnia", "sarajevo"),
    "BE": ("belgium", "belgian", "brussels", "antwerp"),
    "BG": ("bulgaria", "bulgarian", "sofia"),
    "CH": ("switzerland", "swiss", "bern", "zurich", "zürich", "geneva"),
    "CY": ("cyprus", "cypriot", "nicosia", "limassol"),
    "CZ": ("czechia", "czech republic", "czech", "prague"),
    "DE": ("germany", "german", "deutschland", "berlin", "munich", "münchen", "hamburg", "frankfurt", "bavaria", "bayern"),
    "DK": ("denmark", "danish", "copenhagen", "greenland"),
    "EE": ("estonia", "estonian", "tallinn"),
    "ES": ("spain", "spanish", "madrid", "barcelona", "valencia", "sevilla", "catalonia"),
    "FI": ("finland", "finnish", "helsinki"),
    "FR": ("france", "french", "paris", "marseille", "lyon", "toulouse", "bordeaux", "élysée", "elysee"),
    "GB": ("united kingdom", "britain", "british", "england", "scotland", "wales", "london", "manchester", "downing street"),
    "GR": ("greece", "greek", "athens", "thessaloniki"),
    "HR": ("croatia", "croatian", "zagreb"),
    "HU": ("hungary", "hungarian", "budapest", "orbán", "orban"),
    "IE": ("ireland", "irish", "dublin", "cork"),
    "IS": ("iceland", "icelandic", "reykjavik"),
    "IT": ("italy", "italian", "rome", "roma", "milan", "milano", "naples", "napoli", "meloni"),
    "LT": ("lithuania", "lithuanian", "vilnius"),
    "LU": ("luxembourg", "luxembourgish"),
    "LV": ("latvia", "latvian", "riga"),
    "MD": ("moldova", "moldovan", "chișinău", "chisinau", "transnistria"),
    "ME": ("montenegro", "podgorica"),
    "MK": ("north macedonia", "skopje"),
    "MT": ("malta", "maltese", "valletta"),
    "NL": ("netherlands", "dutch", "amsterdam", "rotterdam", "the hague"),
    "NO": ("norway", "norwegian", "oslo"),
    "PL": ("poland", "polish", "warsaw", "warszawa", "kraków", "krakow", "gdańsk", "wrocław", "tusk"),
    "PT": ("portugal", "portuguese", "lisbon", "porto"),
    "RO": ("romania", "romanian", "românia", "bucharest", "bucurești", "cluj", "timișoara", "iași"),
    "RS": ("serbia", "serbian", "belgrade", "kosovo"),
    "SE": ("sweden", "swedish", "stockholm", "gothenburg"),
    "SI": ("slovenia", "slovenian", "ljubljana"),
    "SK": ("slovakia", "slovak", "bratislava", "fico"),
    "UA": ("ukraine", "ukrainian", "kyiv", "kiev", "zelensky", "zelenskyy", "kharkiv", "odesa"),
}

CITIES = {
    "Brussels": (50.8503, 4.3517),
    "Berlin": (52.5200, 13.4050),
    "Paris": (48.8566, 2.3522),
    "Rome": (41.9028, 12.4964),
    "Madrid": (40.4168, -3.7038),
    "Warsaw": (52.2297, 21.0122),
    "Bucharest": (44.4268, 26.1025),
    "Washington": (38.9072, -77.0369),
}
