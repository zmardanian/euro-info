"""The news intelligence engine: topics, regions, entities, noise, importance,
developing stories, trending subjects and a private interest profile.

Everything is local, explainable and fast: patterns and counts, no remote service.
Per-article results are cached by content, so a refresh only analyses new stories.
"""
from __future__ import annotations

import math
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache

from .articles import article_key
from .quality import plain, publisher_family
from .sources import COUNTRY_TERMS, SOURCE_BY_NAME

TOPICS = ("POLITICS", "ECONOMY", "TECHNOLOGY", "SECURITY")
REGION_ALL = "ALL"


_WORD = re.compile(r"\w+")


def _words(text: str) -> list[str]:
    """Case- and accent-insensitive words."""
    return _WORD.findall(plain(text))


def _patterns(*terms: str) -> tuple[str, ...]:
    """Terms for the lexicon; a trailing * matches any word ending ("econom*")."""
    return terms


class Lexicon:
    """Finds many terms with one pass over the words: exact words, word stems and phrases."""

    def __init__(self):
        self.exact: dict[str, list] = {}
        self.stems: dict[str, list] = {}
        self.phrases: dict[tuple, list] = {}
        self.stem_lengths: list[int] = []
        self.longest_prefix = 0

    def add(self, label, terms) -> None:
        for term in terms:
            stem = term.endswith("*")
            words = tuple(_words(term.rstrip("*")))
            if not words:
                continue
            if len(words) == 1:
                (self.stems if stem else self.exact).setdefault(words[0], []).append(label)
            else:
                self.phrases.setdefault(words[:-1], []).append((words[-1], stem, label))
        self.stem_lengths = sorted({len(stem) for stem in self.stems})
        self.longest_prefix = max((len(prefix) for prefix in self.phrases), default=0)

    def count(self, words: list[str]) -> Counter:
        hits: Counter = Counter()
        size = len(words)
        for index, word in enumerate(words):
            for label in self.exact.get(word, ()):
                hits[label] += 1
            for length in self.stem_lengths:
                if length > len(word):
                    break
                for label in self.stems.get(word[:length], ()):
                    hits[label] += 1
            for width in range(1, self.longest_prefix + 1):
                end = index + width
                if end >= size:
                    break
                for last, stem, label in self.phrases.get(tuple(words[index:end]), ()):
                    following = words[end]
                    if following == last or (stem and following.startswith(last)):
                        hits[label] += 1
        return hits


# Topic vocabulary in English, German, French, Italian, Spanish, Romanian, Polish and Dutch.
# Each entry is (pattern, weight); the headline counts double.
TOPIC_VOCABULARY = {
    "POLITICS": [
        (_patterns("election*", "vote*", "voter*", "ballot*", "referendum*", "parliament*", "government*", "minister*",
                   "prime minister", "president*", "chancellor*", "coalition*", "opposition", "lawmaker*", "senat*",
                   "congress*", "white house", "supreme court", "legislat*", "policy", "policies", "campaign*",
                   "democrat*", "republican*", "party", "parties", "cabinet", "impeach*", "veto*", "summit*",
                   "diplomat*", "treaty", "sanction*", "commission*", "eu leaders", "member states", "brussels",
                   "wahl*", "regierung*", "bundestag", "kanzler*", "partei*", "élection*", "gouvernement*",
                   "assemblée", "elezion*", "governo", "elecciones", "gobierno", "alegeri*", "guvern*",
                   "parlament*", "premier*", "wybory", "rząd*", "sejm", "verkiezing*", "kabinet*"), 1.0),
    ],
    "ECONOMY": [
        (_patterns("econom*", "inflation*", "interest rate*", "central bank*", "ecb", "federal reserve", "the fed",
                   "gdp", "recession*", "growth", "market*", "stock*", "shares", "bond*", "yield*", "currency",
                   "euro", "dollar", "tariff*", "trade", "export*", "import*", "budget*", "deficit*", "debt*",
                   "tax*", "invest*", "bank*", "earnings", "profit*", "revenue*", "merger*", "acquisition*",
                   "ipo", "oil price*", "energy price*", "gas price*", "jobs report", "unemployment",
                   "wirtschaft*", "konjunktur*", "zins*", "économi*", "croissance", "economia", "inflazione",
                   "economía", "inflación", "economi*", "inflați*", "dobând*", "gospodark*", "inflacj*",
                   "economie", "rente"), 1.0),
    ],
    "TECHNOLOGY": [
        (_patterns("technolog*", "artificial intelligence", "ai model*", "chatbot*", "openai", "anthropic",
                   "nvidia", "semiconductor*", "chip*", "software", "hardware", "cyber*", "hacker*", "ransomware",
                   "data cent*", "cloud", "linux", "open source", "open-source", "smartphone*", "robot*",
                   "quantum", "startup*", "start-up*", "big tech", "algorithm*", "digital", "internet",
                   "privacy", "gdpr", "ai act", "digital markets act", "digital services act", "spacex",
                   "satellite*", "electric vehicle*", "battery", "batteries", "biotech*", "gene therapy",
                   "kernel", "technologie*", "künstliche intelligenz", "intelligence artificielle",
                   "intelligenza artificiale", "inteligencia artificial", "inteligență artificială",
                   "inteligenta artificiala", "sztuczna inteligencja", "tehnologi*", "technologia"), 1.0),
        (_patterns("ai"), 0.8),
    ],
    "SECURITY": [
        (_patterns("military", "army", "armed forces", "troop*", "soldier*", "war", "wars", "warfare", "invasion",
                   "missile*", "drone*", "air defen*", "defence", "defense", "nato", "weapon*", "ammunition",
                   "ceasefire", "cease-fire", "front line", "frontline", "airstrike*", "strike on", "attack*", "bomb*",
                   "explosive*", "hostage*", "cyberattack*",
                   "nuclear", "espionage", "spy", "spies", "sabotage", "hybrid", "border guard*",
                   "terror*", "security council", "krieg*", "bundeswehr", "armee", "guerre", "guerra",
                   "război*", "razboi*", "militar*", "wojsk*", "wojn*", "oorlog", "defensie"), 1.0),
    ],
}

# Signals of stories outside the reader's focus. They lower importance; nothing is hidden
# unless Focus mode is on, and strong news signals outweigh them.
NOISE_VOCABULARY = [
    (_patterns("football", "soccer", "premier league", "champions league", "la liga", "bundesliga", "serie a",
               "nba", "nfl", "mlb", "nhl", "tennis", "golf", "formula 1", "f1", "grand prix", "olympic*",
               "world cup", "match", "goal*", "coach", "striker", "quarterback", "playoff*", "transfer window",
               "fotbal", "piłk*", "fußball"), "sport"),
    (_patterns("celebrit*", "actor", "actress", "singer", "rapper", "pop star", "oscar*", "grammy*", "emmy*",
               "box office", "red carpet", "royal baby", "reality show", "influencer*", "taylor swift",
               "kardashian*", "netflix series", "tv series", "album", "concert*", "festival"), "entertainment"),
    (_patterns("recipe*", "horoscope*", "diet", "workout", "fashion", "beauty", "travel tips", "holiday deals",
               "best deals", "black friday", "cyber monday", "gift guide", "hands-on"), "lifestyle"),
    (_patterns("shooting", "stabbing", "murder*", "homicide", "car crash", "fire department", "police said",
               "arrested", "sheriff", "missing child", "accident"), "local crime"),
]

# Signs that a US story matters beyond the US.
_GLOBAL_SIGNALS = _patterns(
    "white house", "president trump", "trump administration", "administration", "congress", "senate",
    "supreme court", "federal reserve", "the fed", "tariff*", "trade", "sanction*", "nato", "europe*", "eu",
    "china", "russia", "ukraine", "iran", "israel", "gaza", "g7", "g20", "imf", "world bank", "dollar",
    "treasury", "inflation", "interest rate*", "markets", "wall street", "pentagon", "state department",
    "foreign policy", "nvidia", "openai", "apple", "microsoft", "google", "meta", "amazon", "tesla", "musk",
    "election", "midterm*")
_US_TERMS = _patterns("united states", "u.s.", "american*", "washington", "white house", "congress", "senate",
                      "pentagon", "trump", "federal reserve", "wall street")
_EUROPE_TERMS = _patterns("europe*", "eu", "european union", "brussels", "eurozone", "nato", "schengen",
                          *[term for terms in COUNTRY_TERMS.values() for term in terms])

# Named subjects worth tracking: (display name, kind, weight, patterns).
_ENTITY_TABLE = [
    ("European Commission", "institution", 1.0, ("european commission", "commission president")),
    ("European Parliament", "institution", 0.9, ("european parliament", "meps")),
    ("European Council", "institution", 0.9, ("european council", "eu summit", "eu leaders")),
    ("European Central Bank", "institution", 1.0, ("european central bank", "ecb")),
    ("NATO", "institution", 1.0, ("nato",)),
    ("Federal Reserve", "institution", 1.0, ("federal reserve", "the fed")),
    ("White House", "institution", 0.9, ("white house",)),
    ("US Congress", "institution", 0.8, ("congress", "senate", "house of representatives")),
    ("US Supreme Court", "institution", 0.8, ("supreme court",)),
    ("United Nations", "institution", 0.8, ("united nations", "un security council", "un general assembly")),
    ("IMF", "institution", 0.8, ("imf", "international monetary fund")),
    ("G7", "institution", 0.8, ("g7",)),
    ("G20", "institution", 0.8, ("g20",)),
    ("OPEC", "institution", 0.7, ("opec",)),
    ("Ursula von der Leyen", "person", 1.0, ("von der leyen",)),
    ("António Costa", "person", 0.8, ("antonio costa",)),
    ("Roberta Metsola", "person", 0.7, ("metsola",)),
    ("Christine Lagarde", "person", 0.9, ("lagarde",)),
    ("Kaja Kallas", "person", 0.8, ("kallas",)),
    ("Mark Rutte", "person", 0.8, ("rutte",)),
    ("Emmanuel Macron", "person", 0.9, ("macron",)),
    ("Friedrich Merz", "person", 0.9, ("merz",)),
    ("Keir Starmer", "person", 0.9, ("starmer",)),
    ("Giorgia Meloni", "person", 0.8, ("meloni",)),
    ("Pedro Sánchez", "person", 0.8, ("pedro sanchez",)),
    ("Donald Tusk", "person", 0.8, ("tusk",)),
    ("Viktor Orbán", "person", 0.8, ("orban",)),
    ("Robert Fico", "person", 0.7, ("fico",)),
    ("Nicușor Dan", "person", 0.7, ("nicusor dan",)),
    ("Volodymyr Zelensky", "person", 1.0, ("zelensky", "zelenskyy", "zelenskiy")),
    ("Vladimir Putin", "person", 1.0, ("putin",)),
    ("Donald Trump", "person", 1.0, ("trump",)),
    ("JD Vance", "person", 0.7, ("vance",)),
    ("Marco Rubio", "person", 0.7, ("rubio",)),
    ("Xi Jinping", "person", 0.9, ("xi jinping",)),
    ("Recep Tayyip Erdoğan", "person", 0.7, ("erdogan",)),
    ("Benjamin Netanyahu", "person", 0.8, ("netanyahu",)),
    ("Elon Musk", "person", 0.7, ("musk",)),
    ("Ukraine war", "subject", 1.0, ("war in ukraine", "ukraine war", "russia's war", "russian invasion")),
    ("Tariffs", "subject", 0.9, ("tariff*",)),
    ("Sanctions", "subject", 0.8, ("sanction*",)),
    ("Inflation", "subject", 0.8, ("inflation",)),
    ("Interest rates", "subject", 0.8, ("interest rate*", "rate cut*", "rate hike*")),
    ("Energy prices", "subject", 0.7, ("energy price*", "gas price*", "oil price*")),
    ("Migration", "subject", 0.7, ("migration", "migrant*", "asylum")),
    ("AI regulation", "subject", 0.8, ("ai act", "ai regulation", "regulating ai")),
    ("Digital Markets Act", "subject", 0.7, ("digital markets act", "dma")),
    ("Defence spending", "subject", 0.8, ("defence spending", "defense spending", "military spending",
                                          "rearm*")),
    ("Climate policy", "subject", 0.6, ("climate target*", "emissions", "green deal", "net zero")),
    ("OpenAI", "company", 0.7, ("openai", "chatgpt")),
    ("Nvidia", "company", 0.7, ("nvidia",)),
    ("Apple", "company", 0.6, ("apple",)),
    ("Microsoft", "company", 0.6, ("microsoft",)),
    ("Google", "company", 0.6, ("google", "alphabet")),
    ("Meta", "company", 0.6, ("meta platforms", "facebook", "instagram")),
    ("Amazon", "company", 0.6, ("amazon",)),
    ("Tesla", "company", 0.6, ("tesla",)),
    ("Anthropic", "company", 0.6, ("anthropic",)),
    ("TSMC", "company", 0.6, ("tsmc",)),
    ("ASML", "company", 0.6, ("asml",)),
    ("China", "country", 0.8, ("china", "chinese", "beijing")),
    ("Russia", "country", 0.8, ("russia", "russian", "kremlin", "moscow")),
    ("Ukraine", "country", 0.8, ("ukraine", "ukrainian", "kyiv")),
    ("United States", "country", 0.7, ("united states", "u.s.", "washington")),
    ("Iran", "country", 0.7, ("iran", "iranian", "tehran")),
    ("Israel", "country", 0.7, ("israel", "israeli")),
    ("Gaza", "country", 0.7, ("gaza",)),
    ("Turkey", "country", 0.6, ("turkey", "türkiye", "turkiye", "ankara")),
    ("India", "country", 0.6, ("india", "indian", "new delhi")),
    ("Japan", "country", 0.6, ("japan", "japanese", "tokyo")),
]
_COUNTRY_ENTITY = {"DE": "Germany", "FR": "France", "IT": "Italy", "ES": "Spain", "PL": "Poland", "RO": "Romania",
                   "HU": "Hungary", "NL": "Netherlands", "GB": "United Kingdom", "MD": "Moldova", "RS": "Serbia",
                   "GR": "Greece", "SE": "Sweden", "FI": "Finland", "DK": "Denmark", "CZ": "Czechia",
                   "SK": "Slovakia", "AT": "Austria", "BE": "Belgium", "IE": "Ireland", "PT": "Portugal",
                   "BG": "Bulgaria", "HR": "Croatia", "EE": "Estonia", "LV": "Latvia", "LT": "Lithuania"}
ENTITIES = [(name, kind, weight, words) for name, kind, weight, words in _ENTITY_TABLE]
ENTITIES += [(name, "country", 0.6, COUNTRY_TERMS[code]) for code, name in _COUNTRY_ENTITY.items()]
ENTITY_KIND = {name: kind for name, kind, _weight, _terms in ENTITIES}
COUNTRY_OF_ENTITY = {name: code for code, name in _COUNTRY_ENTITY.items()} | {
    "United States": "US", "Ukraine": "UA", "Russia": "RU", "China": "CN", "Turkey": "TR"}
ENTITY_WEIGHT = {name: weight for name, _kind, weight, _terms in ENTITIES}

# Every vocabulary in one lexicon; labels say what was found.
LEXICON = Lexicon()
for _topic, _rules in TOPIC_VOCABULARY.items():
    for _terms, _weight in _rules:
        LEXICON.add(("topic", _topic, _weight), _terms)
for _terms, _label in NOISE_VOCABULARY:
    LEXICON.add(("noise", _label, 1.0), _terms)
for _name, _kind, _weight, _terms in ENTITIES:
    LEXICON.add(("entity", _name, _weight), _terms)
for _code, _terms in COUNTRY_TERMS.items():
    LEXICON.add(("country", _code, 0.0), _terms)
LEXICON.add(("signal", "global", 0.0), _GLOBAL_SIGNALS)
LEXICON.add(("signal", "us", 0.0), _US_TERMS)
LEXICON.add(("signal", "europe", 0.0), _EUROPE_TERMS)


@dataclass(frozen=True)
class Features:
    """Everything the engine knows about one story, independent of the time of day."""
    topic: str                      # strongest topic, or "GENERAL"
    topic_scores: tuple             # (topic, score) pairs, strongest first
    regions: frozenset              # EUROPE / US / GLOBAL
    countries: tuple                # European country codes mentioned
    entities: tuple                 # named subjects mentioned, strongest first
    entity_weight: float            # 0..1
    noise: str                      # "", "sport", "entertainment", "lifestyle", "local crime"
    global_signal: bool             # a US story with consequences beyond the US
    official: bool                  # an institution's own statement


@lru_cache(maxsize=16384)
def _analyse(title: str, summary: str, source: str, source_region: str, source_topic: str) -> Features:
    headline = _words(title)
    everything = LEXICON.count(headline + _words(summary[:900]))
    in_headline = LEXICON.count(headline)  # headline words count twice

    scores: dict[str, float] = {}
    noise_hits: Counter = Counter()
    found: list[tuple[str, float]] = []
    countries, signals = [], set()
    for label, hits in everything.items():
        kind, value, weight = label
        if kind == "topic":
            scores[value] = scores.get(value, 0.0) + weight * (hits + in_headline.get(label, 0))
        elif kind == "noise":
            noise_hits[value] += hits + in_headline.get(label, 0)
        elif kind == "entity":
            found.append((value, weight))
        elif kind == "country":
            countries.append(value)
        else:
            signals.add(value)
    if source_topic in TOPICS:
        scores[source_topic] = scores.get(source_topic, 0.0) + 1.0  # a tie-breaker, never decisive
    ranked = tuple(sorted(scores.items(), key=lambda pair: (-pair[1], pair[0])))
    topic = ranked[0][0] if ranked and ranked[0][1] >= 1.0 else "GENERAL"
    strongest = ranked[0][1] if ranked else 0.0
    noise = next((label for _terms, label in NOISE_VOCABULARY
                  if noise_hits[label] >= 2 and noise_hits[label] > strongest), "")
    found.sort(key=lambda pair: (-pair[1], pair[0]))
    entity_weight = min(1.0, sum(weight for _name, weight in found[:4]) / 2.4)
    regions = {source_region or "GLOBAL"}
    if countries or "europe" in signals:
        regions.add("EUROPE")
    if "us" in signals:
        regions.add("US")
    official = SOURCE_BY_NAME.get(source, {}).get("kind") == "Official source"
    return Features(topic, ranked, frozenset(regions), tuple(sorted(countries)), tuple(name for name, _ in found),
                    entity_weight, noise, "global" in signals, official)


def features(article: dict) -> Features:
    source = str(article.get("source", ""))
    catalogue = SOURCE_BY_NAME.get(source, {})
    return _analyse(str(article.get("title", "")), str(article.get("summary", "")), source,
                    str(article.get("source_region") or catalogue.get("region") or "GLOBAL"),
                    str(article.get("source_topic") or catalogue.get("topic") or ""))


def topic_of(article: dict) -> str:
    return features(article).topic


def region_matches(article: dict, region: str) -> bool:
    return region in (REGION_ALL, "", None) or region in features(article).regions


def us_story_without_global_relevance(article: dict) -> bool:
    found = features(article)
    return found.regions == frozenset({"US"}) and not found.global_signal


# ------------------------------------------------------------------ interest profile

@dataclass
class Profile:
    """What the reader opens, saves and annotates, kept on this computer."""
    entities: Counter = field(default_factory=Counter)
    topics: Counter = field(default_factory=Counter)
    sources: Counter = field(default_factory=Counter)
    stories: int = 0

    def affinity(self, article: dict) -> tuple[float, str]:
        """0..1 interest match and the strongest reason."""
        if self.stories < 5:
            return 0.0, ""
        found = features(article)
        best_entity = max(found.entities, key=lambda name: self.entities[name], default="")
        entity_share = self.entities[best_entity] / self.stories if best_entity else 0.0
        topic_share = self.topics[found.topic] / self.stories
        source_share = self.sources[article.get("source", "")] / self.stories
        score = min(1.0, 0.55 * min(1.0, entity_share * 3) + 0.30 * topic_share + 0.15 * min(1.0, source_share * 4))
        return score, best_entity if entity_share >= 0.15 else ""


def build_profile(read: list[dict], saved: list[dict], researched: list[dict]) -> Profile:
    profile = Profile()
    for weight, articles in ((1, read), (3, saved), (3, researched)):
        for article in articles:
            found = features(article)
            profile.stories += weight
            profile.topics[found.topic] += weight
            profile.sources[article.get("source", "")] += weight
            for name in found.entities[:4]:
                profile.entities[name] += weight
    return profile


# ------------------------------------------------------------------ scoring and stories

HALF_LIFE_HOURS = 20.0
TOPIC_WEIGHT = {"POLITICS": 1.0, "ECONOMY": 1.0, "SECURITY": 1.0, "TECHNOLOGY": 0.9, "GENERAL": 0.45}


@dataclass
class Story:
    """A developing story: every loaded report about the same event."""
    articles: list
    lead: dict
    importance: float
    families: int
    countries: tuple
    topic: str
    regions: frozenset
    entities: tuple
    updated: float
    reasons: list

    @property
    def key(self) -> str:
        return article_key(self.lead)


class NewsIndex:
    """Scores, stories and trends for one snapshot of the news. Built off the interface thread."""

    def __init__(self, articles: list[dict], profile: Profile | None = None, now: float | None = None,
                 groups: list[list[dict]] | None = None):
        from .feeds import cluster_stories
        self.now = time.time() if now is None else now
        self.articles = articles
        self.profile = profile or Profile()
        self.groups = groups if groups is not None else cluster_stories(articles)
        self.group_of: dict[int, list[dict]] = {id(item): group for group in self.groups for item in group}
        self.scores: dict[int, float] = {}
        self.reasons: dict[int, list] = {}
        self._story_cache: dict[tuple, Story] = {}
        for article in articles:
            score, reasons = self._score(article)
            self.scores[id(article)] = score
            self.reasons[id(article)] = reasons

    def _breadth(self, group: list[dict]) -> tuple[int, int]:
        families = {publisher_family(item) for item in group}
        countries = {SOURCE_BY_NAME.get(item.get("source", ""), {}).get("country", "") for item in group}
        return len(families), len(countries - {""})

    def _score(self, article: dict) -> tuple[float, list[tuple]]:
        """Importance 0..100 and the reasons, as (template, values) pairs for translation."""
        found = features(article)
        group = self.group_of.get(id(article), [article])
        families, countries = self._breadth(group)
        breadth = min(1.0, math.log2(1 + families) / math.log2(9)) * 0.75 + min(1.0, countries / 4) * 0.25
        try:
            stamp = float(article.get("timestamp") or 0)
        except (TypeError, ValueError):
            stamp = 0.0
        hours = max(0.0, (self.now - stamp) / 3600) if stamp else 48.0
        freshness = 0.5 ** (hours / HALF_LIFE_HOURS)
        topic = TOPIC_WEIGHT.get(found.topic, 0.45)
        value = 0.30 * breadth + 0.22 * topic + 0.18 * found.entity_weight + 0.30 * freshness
        reasons = []
        if families > 1:
            reasons.append(("Covered by {n} publisher families", {"n": families}))
        if countries > 1:
            reasons.append(("Publishers in {n} countries", {"n": countries}))
        if found.entities:
            reasons.append(("Key subjects: {names}", {"names": found.entities[:3]}))
        if freshness > 0.7:
            reasons.append(("Freshness", {}))
        if found.official:
            value += 0.06
            reasons.append(("Official source", {}))
        if found.noise:
            value *= 0.35
            reasons.append(("Lower priority: {kind}", {"kind": found.noise}))
        if found.regions == frozenset({"US"}) and not found.global_signal:
            value *= 0.5
            reasons.append(("Lower priority: US story without wider relevance", {}))
        affinity, interest = self.profile.affinity(article)
        if affinity:
            value += 0.08 * affinity
            if interest:
                reasons.append(("Matches your reading: {name}", {"name": interest}))
        return round(100 * min(1.0, value), 1), reasons

    def score(self, article: dict) -> float:
        return self.scores.get(id(article)) or self._score(article)[0]

    def why(self, article: dict) -> list[tuple]:
        return self.reasons.get(id(article)) or self._score(article)[1]

    def is_low_priority(self, article: dict) -> bool:
        found = features(article)
        return bool(found.noise) or (found.regions == frozenset({"US"}) and not found.global_signal)

    def rank(self, articles: list[dict], limit_diverse: int = 60) -> list[dict]:
        """Highest importance first, with publisher variety near the top."""
        ordered = sorted(articles, key=lambda item: -self.score(item))
        head, tail, seen = [], [], Counter()
        pool = ordered[:limit_diverse * 2]
        while pool and len(head) < limit_diverse:
            choice = max(range(len(pool)), key=lambda index: (self.score(pool[index]) -
                                                             7 * seen[publisher_family(pool[index])], -index))
            item = pool.pop(choice)
            head.append(item)
            seen[publisher_family(item)] += 1
        tail = pool + ordered[limit_diverse * 2:]
        return head + tail

    def stories(self, articles: list[dict] | None = None, language: str = "en", limit: int = 40) -> list[Story]:
        """Developing stories, most important first. Story summaries are cached per index."""
        wanted = None if articles is None else {id(item) for item in articles}
        result = []
        for group in self.groups:
            members = group if wanted is None else [item for item in group if id(item) in wanted]
            if not members:
                continue
            key = (id(group), language, len(members) if len(members) == len(group) else tuple(map(id, members)))
            story = self._story_cache.get(key)
            if story is None:
                story = self._story(members, language)
                self._story_cache[key] = story
            result.append(story)
        result.sort(key=lambda story: (-story.importance, -story.updated))
        return result[:limit]

    def _story(self, members: list[dict], language: str) -> Story:
        families, countries = self._breadth(members)
        best = max(self.score(item) for item in members)
        importance = round(min(100.0, best + 4 * math.log2(families) if families > 1 else best), 1)
        lead = max(members, key=lambda item: (
            self.score(item) + (6 if item.get("source_language") == language else 0)
            + (3 if item.get("source_language") == "en" else 0) + (2 if item.get("summary") else 0)))
        # The story's topic is the majority view of its reports, not one desk's beat.
        topics = Counter(features(item).topic for item in members if features(item).topic != "GENERAL")
        topic = topics.most_common(1)[0][0] if topics else features(lead).topic
        entity_counts = Counter(name for item in members for name in features(item).entities[:4])
        country_codes = tuple(sorted({SOURCE_BY_NAME.get(item.get("source", ""), {}).get("country", "")
                                      for item in members} - {""}))
        updated = max(float(item.get("timestamp") or 0) for item in members)
        return Story(sorted(members, key=lambda item: -float(item.get("timestamp") or 0)), lead, importance,
                     families, country_codes, topic,
                     frozenset().union(*(features(item).regions for item in members)),
                     tuple(name for name, _count in entity_counts.most_common(4)), updated, self.why(lead))

    def trending(self, limit: int = 8, recent_hours: float = 6.0, window_hours: float = 48.0,
                 history: dict[str, list] | None = None) -> list[tuple[str, int]]:
        """Subjects mentioned much more in the last hours than usual, by several publishers.

        history holds earlier counts per subject (see TrendHistory); without it the
        older part of the current snapshot is the baseline.
        """
        recent, earlier, families = Counter(), Counter(), {}
        recent_total = earlier_total = 0
        for article in self.articles:
            try:
                age = (self.now - float(article.get("timestamp") or 0)) / 3600
            except (TypeError, ValueError):
                continue
            if age < 0 or age > window_hours:
                continue
            home = SOURCE_BY_NAME.get(article.get("source", ""), {}).get("country")
            # A publisher mentioning its own country is not a sign of a trend.
            names = [name for name in features(article).entities[:5] if COUNTRY_OF_ENTITY.get(name) != home]
            if age <= recent_hours:
                recent_total += 1
                recent.update(names)
                for name in names:
                    families.setdefault(name, set()).add(publisher_family(article))
            else:
                earlier_total += 1
                earlier.update(names)
        scored = []
        for name, count in recent.items():
            if count < 3 or len(families.get(name, ())) < 2:
                continue
            # Compare shares of coverage, not raw counts: a busy news day is not a trend.
            share = count / max(1, recent_total)
            past = [value for stamp, value in (history or {}).get(name, []) if self.now - stamp > recent_hours * 3600]
            if len(past) >= 3:
                past.sort()
                baseline = past[len(past) // 2]
            else:
                baseline = (earlier[name] + 0.5) / max(1, earlier_total) if earlier_total >= 20 else 0.02
            growth = (share + 0.01) / (baseline + 0.01)
            needed = 2.5 if ENTITY_KIND.get(name) == "country" else 1.5
            if growth >= needed:
                scored.append((count * math.log2(1 + growth) * ENTITY_WEIGHT.get(name, 0.6), name, count))
        scored.sort(reverse=True)
        return [(name, count) for _score, name, count in scored[:limit]]


class TrendHistory:
    """Mention counts per subject from earlier refreshes (7 days), for a fair trending baseline."""

    KEEP_SECONDS = 7 * 24 * 3600

    def __init__(self, path):
        self.path = path
        self.data: dict[str, list] = {}

    def load(self) -> "TrendHistory":
        import json
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.data = data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            self.data = {}
        return self

    def record(self, articles: list[dict], now: float | None = None, recent_hours: float = 6.0) -> None:
        now = time.time() if now is None else now
        counts, total = Counter(), 0
        for article in articles:
            try:
                if (now - float(article.get("timestamp") or 0)) / 3600 <= recent_hours:
                    counts.update(features(article).entities[:5])
                    total += 1
            except (TypeError, ValueError):
                continue
        cutoff = now - self.KEEP_SECONDS
        for name in set(self.data) | set(counts):
            points = [point for point in self.data.get(name, []) if point[0] >= cutoff]
            # One point per hour is enough for a baseline.
            if not points or now - points[-1][0] >= 3600:
                points.append([now, round(counts.get(name, 0) / max(1, total), 4)])
            self.data[name] = points[-200:]
        self.data = {name: points for name, points in self.data.items() if any(value for _stamp, value in points)}

    def save(self) -> None:
        import json
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps(self.data), encoding="utf-8")
            temporary.replace(self.path)
        except OSError:
            pass
