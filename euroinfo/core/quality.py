"""Local, explainable news metadata. Signals describe evidence, never certify truth."""
from __future__ import annotations

import hashlib
import math
import re
import time
import unicodedata
from collections import Counter
from functools import lru_cache
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

TECH_TERMS = {
    'Linux': ('linux', 'ubuntu', 'fedora', 'debian', 'arch linux', 'opensuse', 'red hat', 'gnome', 'kde', 'wayland', 'systemd', 'flatpak', 'flathub', 'proton', 'btrfs', 'mesa', 'open source', 'open-source', 'kernel'),
    'AI': ('artificial intelligence', 'inteligenta artificiala', 'intelligence artificielle', 'kunstliche intelligenz', 'intelligenza artificiale', 'inteligencia artificial', 'sztuczna inteligencja', 'machine learning', 'deep learning', 'chatgpt', 'openai', 'anthropic', 'llm', 'neural network', 'generative ai', ' ai ', ' ia '),
    'Biotech': ('biotech', 'biotechnology', 'biotehnolog', 'gene therapy', 'genetic', 'genomic', 'crispr', 'clinical trial', 'molecular', 'bioengineering', 'stem cell', 'mRNA', 'protein design', 'neuroscience'),
    'Breakthroughs': ('breakthrough', 'descoperire', 'quantum', 'fusion', 'semiconductor', 'battery', 'batteries', 'photonic', 'nanotech', 'new material', 'researchers', 'scientists', 'scientific', 'science', 'discovery', 'robot'),
    'Technology': ('technology', 'tehnolog', 'technologie', 'tecnologia', 'tecnologie', 'technologia', 'software', 'hardware', 'cybersecurity', 'cyberattack', 'ransomware', 'chip', 'computing', 'smartphone', 'satellite', 'spacex', 'data center'),
}
FRAME_TERMS = {
    'Political': ('election', 'parliament', 'government', 'minister', 'president', 'vote', 'policy', 'aleger', 'guvern', 'politic', 'wahl', 'regierung'),
    'Economic': ('econom', 'market', 'inflation', 'bank', 'trade', 'tariff', 'investment', 'budget', 'tax', 'finance', 'business', 'piata', 'wirtschaft'),
    'Geopolitical': ('sanction', 'diploma', 'treaty', 'alliance', 'border', 'ukraine', 'russia', 'china', 'iran', 'ucraina', 'rus', 'geopolit'),
    'Military': ('military', 'army', 'missile', 'defence', 'defense', 'nato', 'war', 'troops', 'weapon', 'militar', 'razboi', 'nuclear'),
}
WIRE_NAMES = ('Reuters', 'AFP', 'Associated Press', 'AP', 'Agerpres', 'DPA', 'PA Media', 'Bloomberg')
WIRE_PATTERN = re.compile(r'\b(?:' + '|'.join(re.escape(name) for name in WIRE_NAMES) + r')\b', re.I)
UPDATE_PATTERN = re.compile(r'\b(?:updated?|correction|corrected|retraction|retracted|actualizat|rectificare|corectie|retractare|aktualisiert|korrigiert|corrige|mise a jour)\b', re.I)


def plain(value):
    return _normal_text(str(value or '')[:20000])


@lru_cache(maxsize=8192)
def _normal_text(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', value.casefold()) if not unicodedata.combining(c))


def article_text(article):
    return ' ' + plain(' '.join(str(article.get(key) or '') for key in ('title', 'summary', 'description'))) + ' '


_TECH_PATTERNS = {
    name: [re.compile(r"(?<!\w)" + re.escape(plain(word).strip()) + (r"\w*" if word in ('tehnolog', 'technologie', 'biotehnolog', 'genetic', 'genomic') else r"(?!\w)"))
           for word in words if word.strip().casefold() not in ('ai', 'ia', 'mesa', 'proton', 'kernel')]
    for name, words in TECH_TERMS.items()
}


def technology_topics(article):
    """Technology topics for an article. Cached by content, so repeated renders are free."""
    return list(_technology_topics(
        str(article.get('title') or ''), str(article.get('summary') or ''), str(article.get('description') or ''),
        str(article.get('source_topic') or ''), str(article.get('specialty') or '')))


@lru_cache(maxsize=8192)
def _technology_topics(title, summary, description, source_topic, specialty):
    raw = ' '.join(value for value in (title, summary, description) if value)
    text = ' ' + plain(raw) + ' '
    topics = [name for name, patterns in _TECH_PATTERNS.items() if any(pattern.search(text) for pattern in patterns)]
    if re.search(r"\b(?:AI|IA)\b", raw) and 'AI' not in topics:
        topics.append('AI')
    if source_topic == 'TECHNOLOGY':
        if specialty in ('Linux', 'AI', 'Biotech') and specialty not in topics:
            topics.append(specialty)
        if not topics:
            topics = [specialty if specialty in TECH_TERMS else 'Technology']
    return tuple(topics)


def frames(article):
    return list(_frames(article_text(article)))


@lru_cache(maxsize=8192)
def _frames(text):
    return tuple(name for name, words in FRAME_TERMS.items() if any(word in text for word in words))


def publisher_family(article):
    if article.get('publisher_family'):
        return str(article['publisher_family'])[:100]
    source = str(article.get('source') or 'Unknown publisher')
    for prefix in ('BBC', 'The Guardian', 'France 24', 'Deutsche Welle', 'Nature'):
        if source.startswith(prefix):
            return prefix
    return source


def declared_origins(article):
    """An agency mention is attribution, not proof the entire report is syndicated."""
    text = ' '.join(str(article.get(key) or '') for key in ('author', 'summary', 'description'))
    names = {match.group().casefold() for match in WIRE_PATTERN.finditer(text)}
    return [name for name in WIRE_NAMES if name.casefold() in names]


def evidence_label(article):
    return 'Publisher page extract' if article.get('reader_text') else ('RSS excerpt' if article.get('summary') else 'Headline only')


def freshness(article, now=None):
    now = time.time() if now is None else now
    try:
        stamp = float(article.get('updated_timestamp') or article.get('timestamp') or 0)
    except (TypeError, ValueError):
        stamp = 0
    if not math.isfinite(stamp) or stamp <= 0:
        return 'Unknown date', None
    if stamp > now + 3600:
        return 'Future date', None
    hours = max(0, (now - stamp)/3600)
    return ('Older report' if hours > 72 else 'Recent report'), hours


def update_label(article):
    if _mentions_update(article_text(article)):
        return 'Update/correction mentioned'
    try:
        if float(article.get('updated_timestamp') or 0) > float(article.get('timestamp') or 0) + 60:
            return 'Feed updated'
    except (TypeError, ValueError):
        pass
    return ''


@lru_cache(maxsize=8192)
def _mentions_update(text):
    return bool(UPDATE_PATTERN.search(text))


def canonical_link(link):
    """Remove tracking keys without changing case-sensitive article paths or IDs."""
    try:
        parsed = urlsplit(str(link or ''))
        query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True)
                 if not key.lower().startswith('utm_') and key.lower() not in ('fbclid', 'gclid', 'mc_cid', 'mc_eid')]
        return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip('/'), urlencode(query), ''))
    except ValueError:
        return str(link or '')


def excerpt_fingerprint(article):
    words = re.findall(r'\w+', plain(article.get('summary', '')))
    if len(words) < 24:
        return ''
    return hashlib.sha256(' '.join(words[:70]).encode()).hexdigest()[:16]


def provenance_report(articles):
    """Find observable dependencies. An unflagged report is still unverified."""
    families = {publisher_family(item) for item in articles}
    origins = Counter(origin for item in articles for origin in declared_origins(item))
    excerpts = Counter(value for item in articles if (value := excerpt_fingerprint(item)))
    repeated_origins = {origin: count for origin, count in origins.items() if count > 1}
    repeated_excerpts = sum(count-1 for count in excerpts.values() if count > 1)
    return {'reports': len(articles), 'families': len(families),
            'shared_attributions': repeated_origins, 'repeated_excerpts': repeated_excerpts,
            'independence': 'Not verified'}


def annotate_article(article, source=None, author='', updated_timestamp=0):
    source = source or {}
    result = dict(article)
    for field in ('topic', 'specialty', 'publisher_family', 'country', 'access', 'kind'):
        if source.get(field):
            result['source_topic' if field == 'topic' else field] = source[field]
    result['author'] = str(author or article.get('author') or '')[:200]
    result['updated_timestamp'] = float(updated_timestamp or article.get('updated_timestamp') or 0)
    result['evidence_kind'] = evidence_label(result)
    result['attributed_origins'] = declared_origins(result)
    return result


def rank_articles(articles, country='', country_terms=(), technology=False, now=None, coverage=None):
    """Bounded local scoring plus publisher variety; preserve every article."""
    now = time.time() if now is None else now
    scored = []
    diversity_cache = {}
    for index, article in enumerate(articles):
        text = article_text(article)
        score = 0.0
        if country_terms and any(plain(word) in text for word in country_terms):
            score += 10
        if article.get('country') == country:
            score += 3
        _, hours = freshness(article, now)
        if hours is not None:
            score += 12 * math.exp(-hours/36)
        score += min(6, 2*len(frames(article)))
        if len(str(article.get('summary') or '')) >= 120:
            score += 2
        if update_label(article):
            score += 3
        if technology and 'Linux' in technology_topics(article):
            score += 16
        group = (coverage or {}).get(id(article), [])
        if group:
            group_key = id(group)
            if group_key not in diversity_cache:
                observed = provenance_report(group)
                dependence = max(max(observed['shared_attributions'].values(), default=1)-1, observed['repeated_excerpts'])
                diversity_cache[group_key] = max(1, observed['families']-dependence)
            score += 2*min(2, diversity_cache[group_key]-1)
        else:
            group_key = plain(article.get("title"))
        scored.append((score, index, article, publisher_family(article), group_key))
    scored.sort(key=lambda row: (-row[0], row[1]))
    # Re-rank only the leading 40: avoid quadratic work across the whole archive.
    pool = scored[:80]
    ordered = []
    seen_families = Counter()
    seen_titles = Counter()
    while pool and len(ordered) < 40:
        choice = max(range(len(pool)), key=lambda pos: (pool[pos][0] - 5*seen_families[pool[pos][3]] - 8*seen_titles[pool[pos][4]], -pool[pos][1]))
        _, _, article, family, title = pool.pop(choice)
        ordered.append(article)
        seen_families[family] += 1
        seen_titles[title] += 1
    ordered.extend(row[2] for row in sorted(pool+scored[80:], key=lambda row: (-row[0], row[1])))
    return ordered


def ranking_reasons(article, country_terms=(), technology=False, coverage=None):
    reasons = ['Freshness' if freshness(article)[1] is not None else freshness(article)[0], 'Publisher variety']
    if country_terms and any(plain(word) in article_text(article) for word in country_terms):
        reasons.append('Location relevance')
    if technology and 'Linux' in technology_topics(article):
        reasons.append('Linux priority')
    if frames(article):
        reasons.append('Public impact signals')
    if len(str(article.get('summary') or '')) >= 120:
        reasons.append('Excerpt available')
    if coverage and provenance_report(coverage)['families'] > 1:
        reasons.append('Multiple publisher families')
    if update_label(article):
        reasons.append('Update signal')
    return reasons


def coverage_audit(articles, catalogue, health=None, enabled=None, country_terms=None):
    health = health or {}
    enabled = set(source['name'] for source in catalogue) if enabled is None else set(enabled)
    counts = Counter(item.get('source') for item in articles)
    topic_counts = Counter(topic for item in articles for topic in technology_topics(item))
    frame_counts = Counter(frame for item in articles for frame in frames(item))
    regions = Counter(item.get('source_region', 'Unknown') for item in articles)
    languages = Counter(item.get('source_language', 'Unknown') for item in articles)
    countries = Counter(item.get('country', 'Unknown') for item in articles)
    country_mentions = {country:sum(any(plain(term) in article_text(item) for term in terms) for item in articles) for country,terms in (country_terms or {}).items()}
    sources = []
    for source in catalogue:
        state = health.get(source['name'], {})
        sources.append(dict(source, enabled=source['name'] in enabled, loaded=counts[source['name']],
                            feed_error=state.get('error', ''), cached=state.get('cached', False),
                            checked=state.get('checked', 0)))
    return {'articles': len(articles), 'regions': dict(regions), 'languages': dict(languages),
            'publisher_countries': dict(countries), 'country_mentions': country_mentions, 'frames': dict(frame_counts), 'topics': dict(topic_counts),
            'missing_frames': [name for name in FRAME_TERMS if not frame_counts[name]],
            'missing_topics': [name for name in TECH_TERMS if not topic_counts[name]],
            'sources': sources, 'older': sum(freshness(item)[0] == 'Older report' for item in articles),
            'undated': sum(freshness(item)[1] is None for item in articles)}
