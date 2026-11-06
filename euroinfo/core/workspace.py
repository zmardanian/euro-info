"""Local research library, bounded AI cache and dependency-free search/export."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
import shlex
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from urllib.parse import urlsplit

from .. import paths
from .articles import storable
from .quality import publisher_family, declared_origins, evidence_label, freshness, update_label
from .reasoning import build_investigation_map

# Context sizes suit an 8 GB GPU with a 9B model (Qwen3.5 fits 32K with a q8 KV cache).
AI_PROFILES = {
    'efficient': {'num_ctx': 4096, 'num_predict': 1000},
    'balanced': {'num_ctx': 6144, 'num_predict': 1400},
    'deep': {'num_ctx': 12288, 'num_predict': 2000},
}


def evidence_budget(options) -> int:
    """Characters of evidence that fit the context next to instructions and the answer."""
    return max(1800, int((int(options.get('num_ctx', 6144)) - int(options.get('num_predict', 1400)) - 1100) * 2.8))


def analysis_options(model='auto', profile='balanced', keep_alive='10m'):
    profile = profile if profile in AI_PROFILES else 'balanced'
    return dict(AI_PROFILES[profile], model=str(model or 'auto')[:120],
                profile=profile, keep_alive=keep_alive if keep_alive in ('0', '2m', '10m', '30m') else '10m')


def analysis_key(prompt, language, options):
    payload = json.dumps(['v4', prompt, language, options], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()


class ReaderWorkspace:
    """Transactions use their own short-lived connections, also safe in workers."""
    def __init__(self, path=None):
        self.path = Path(path or paths.data_dir()/'research.sqlite3')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as connection, connection:
            connection.execute('PRAGMA journal_mode=WAL')
            connection.executescript('''
                CREATE TABLE IF NOT EXISTS stories (
                    key TEXT PRIMARY KEY, article TEXT NOT NULL, notes TEXT NOT NULL DEFAULT '',
                    tags TEXT NOT NULL DEFAULT '[]', read_at REAL NOT NULL DEFAULT 0, updated REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS watches (name TEXT PRIMARY KEY, query TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS analyses (
                    key TEXT PRIMARY KEY, summary TEXT NOT NULL, created REAL NOT NULL);
            ''')

    def connect(self):
        return sqlite3.connect(str(self.path), timeout=3)

    def metadata(self):
        with closing(self.connect()) as connection:
            return {key: {'notes': notes, 'tags': json.loads(tags), 'read_at': read_at}
                    for key, notes, tags, read_at in connection.execute('SELECT key,notes,tags,read_at FROM stories')}

    def save_story(self, key, article, notes=None, tags=None, read=None):
        with closing(self.connect()) as connection, connection:
            connection.execute('INSERT INTO stories(key,article,updated) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET article=excluded.article,updated=excluded.updated',
                               (key, json.dumps(storable(article), ensure_ascii=False), time.time()))
            if notes is not None:
                connection.execute('UPDATE stories SET notes=? WHERE key=?', (str(notes)[:30000], key))
            if tags is not None:
                cleaned = sorted({str(tag).strip().casefold()[:60] for tag in tags if str(tag).strip()})[:30]
                connection.execute('UPDATE stories SET tags=? WHERE key=?', (json.dumps(cleaned), key))
            if read is not None:
                connection.execute('UPDATE stories SET read_at=? WHERE key=?', (time.time() if read else 0, key))
            # Keep research notes; bound incidental reading history.
            connection.execute("DELETE FROM stories WHERE notes='' AND tags='[]' AND key NOT IN (SELECT key FROM stories ORDER BY updated DESC LIMIT 5000)")

    def research_articles(self):
        with closing(self.connect()) as connection:
            return [json.loads(row[0]) for row in connection.execute("SELECT article FROM stories WHERE notes<>'' OR tags<>'[]' ORDER BY updated DESC")]

    def history_articles(self):
        with closing(self.connect()) as connection:
            return [json.loads(row[0]) for row in connection.execute('SELECT article FROM stories WHERE read_at>0 ORDER BY read_at DESC LIMIT 500')]

    def watches(self):
        with closing(self.connect()) as connection:
            return dict(connection.execute('SELECT name,query FROM watches ORDER BY name COLLATE NOCASE'))

    def save_watch(self, name, query):
        name, query = name.strip()[:80], query.strip()[:500]
        if not name or not query:
            raise ValueError('A name and search query are required.')
        with closing(self.connect()) as connection, connection:
            if name not in self.watches() and connection.execute('SELECT COUNT(*) FROM watches').fetchone()[0] >= 50:
                raise ValueError('The watchlist limit is 50.')
            connection.execute('INSERT OR REPLACE INTO watches VALUES(?,?)', (name, query))

    def remove_watch(self, name):
        with closing(self.connect()) as connection, connection:
            connection.execute('DELETE FROM watches WHERE name=?', (name,))

    def get_analysis(self, key, max_age=48*3600):
        with closing(self.connect()) as connection:
            row = connection.execute('SELECT summary,created FROM analyses WHERE key=?', (key,)).fetchone()
        return row if row and time.time()-row[1] < max_age else None

    def put_analysis(self, key, summary):
        if not summary.strip():
            return
        with closing(self.connect()) as connection, connection:
            connection.execute('INSERT OR REPLACE INTO analyses VALUES(?,?,?)', (key, summary[:60000], time.time()))
            connection.execute('DELETE FROM analyses WHERE key NOT IN (SELECT key FROM analyses ORDER BY created DESC LIMIT 100) OR created<?', (time.time()-48*3600,))

    def clear_analyses(self):
        with closing(self.connect()) as connection, connection:
            connection.execute('DELETE FROM analyses')


def query_tokens(query):
    try:
        return shlex.split(query.casefold())
    except ValueError:
        return query.casefold().split()


def matches_query(article, tokens, metadata=None, saved=False):
    metadata = metadata or {}
    searchable = ' '.join(str(article.get(field) or '') for field in (
        'title','localized_title','summary','localized_summary','source','link'))
    searchable = (searchable+' '+metadata.get('notes', '')+' '+' '.join(metadata.get('tags', []))).casefold()
    for token in tokens:
        negative = token.startswith('-') and len(token) > 1
        term = token[1:] if negative else token
        field, separator, value = term.partition(':')
        if separator and field == 'source':
            matched = value in str(article.get('source','')).casefold()
        elif separator and field == 'tag':
            matched = value in metadata.get('tags', [])
        elif separator and field == 'is' and value in ('read','unread','saved','noted'):
            matched = {'read': bool(metadata.get('read_at')), 'unread': not metadata.get('read_at'),
                       'saved': saved, 'noted': bool(metadata.get('notes'))}[value]
        else:
            matched = term in searchable
        if matched == negative:
            return False
    return True


def export_articles(articles, metadata, key_function, format='markdown'):
    if format == 'csv':
        target = io.StringIO(newline='')
        writer = csv.writer(target)
        writer.writerow(['Title','Publisher','Published','URL','Tags','Notes'])
        for article in articles:
            state = metadata.get(key_function(article), {})
            # Prevent spreadsheet formula execution in fields from publishers or notes.
            fields = [article.get('title',''), article.get('source',''), article.get('time',''),
                      article.get('link',''), ', '.join(state.get('tags', [])), state.get('notes','')]
            writer.writerow(["'"+str(value) if str(value).lstrip().startswith(('=','+','-','@')) else value for value in fields])
        return target.getvalue()
    def plain(value):
        return re.sub(r'[\\`*_{}\[\]<>#]', '', str(value)).replace('\r','')
    parts = ['# Euro Info research export\n']
    for article in articles:
        state = metadata.get(key_function(article), {})
        parts.extend([f"## {plain(article.get('title',''))}",
                      f"{plain(article.get('source',''))} · {plain(article.get('time',''))}",
                      str(article.get('link','')), plain(article.get('summary',''))])
        if state.get('tags'):
            parts.append('Tags: '+', '.join(map(plain, state['tags'])))
        if state.get('notes'):
            parts.append('Notes:\n'+plain(state['notes']))
        parts.append('')
    return '\n\n'.join(parts)


def validate_library_backup(path):
    """Validate the complete import before any existing user data is changed."""
    path = Path(path)
    if path.stat().st_size > 5*1024*1024:
        raise ValueError('Library backup exceeds 5 MB.')
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict) or payload.get('schema') != 2:
        raise ValueError('Unsupported library backup format.')
    stories, saved, metadata, watches = (payload.get(key) for key in ('stories','saved_keys','metadata','watches'))
    if not isinstance(stories, list) or len(stories) > 3000 or not isinstance(saved, list) or not isinstance(metadata, dict) or not isinstance(watches, dict) or len(watches) > 50:
        raise ValueError('Invalid library backup structure.')
    for article in stories:
        if not isinstance(article, dict) or not isinstance(article.get('title'), str) or not article['title'].strip():
            raise ValueError('An imported story is missing its title.')
        link = article.get('link')
        if not isinstance(link, str) or len(link)>4096 or any(ord(character)<32 for character in link):
            raise ValueError('An imported story has an invalid publisher URL.')
        parsed = urlsplit(link)
        if parsed.scheme not in ('http','https') or not parsed.hostname:
            raise ValueError('An imported story has an invalid publisher URL.')
        if len(article['title']) > 2000:
            raise ValueError('An imported headline is too long.')
        if article.get('image_url') is not None and not isinstance(article['image_url'], str):
            raise ValueError('Invalid image URL.')
        for field in ('summary','source','time','localized_title','localized_summary','author','source_topic','specialty','publisher_family','country','access','kind','evidence_kind'):
            if field in article and not isinstance(article[field], str):
                raise ValueError('Invalid story text field.')
        if 'updated_timestamp' in article and (not isinstance(article['updated_timestamp'], (int,float)) or not math.isfinite(article['updated_timestamp'])):
            raise ValueError('Invalid updated timestamp.')
        if 'timestamp' in article and (not isinstance(article['timestamp'], (int,float)) or not math.isfinite(article['timestamp'])):
            raise ValueError('Invalid story timestamp.')
    if any(not isinstance(key,str) for key in saved):
        raise ValueError('Invalid saved story keys.')
    for key, state in metadata.items():
        if not isinstance(key,str) or not isinstance(state,dict) or not isinstance(state.get('notes',''),str) or len(state.get('notes',''))>30000:
            raise ValueError('Invalid research notes.')
        tags = state.get('tags',[])
        if not isinstance(tags,list) or len(tags)>30 or any(not isinstance(tag,str) or len(tag)>60 for tag in tags):
            raise ValueError('Invalid research tags.')
        if not isinstance(state.get('read_at',0),(int,float)) or not math.isfinite(state.get('read_at',0)):
            raise ValueError('Invalid read history.')
    for name, query in watches.items():
        if not isinstance(name,str) or not name.strip() or len(name)>80 or not isinstance(query,str) or not query.strip() or len(query)>500:
            raise ValueError('Invalid saved search.')
    return payload


def build_evidence_text(articles, options):
    """Build bounded evidence with room reserved for the investigative map."""
    profile = options.get('profile', 'balanced')
    profile = profile if profile in ('efficient', 'balanced', 'deep') else 'balanced'
    items = list(articles[:{'efficient': 6, 'balanced': 8, 'deep': 12}[profile]])
    budget = max(1800, int((int(options.get('num_ctx', 4096)) -
                            int(options.get('num_predict', 1400)) - 1300) * 2.8))
    map_limit = {'efficient': 360, 'balanced': 850, 'deep': 1100}[profile]
    investigation = build_investigation_map(items, max_chars=map_limit)
    headers = [
        f"[{index}] {str(item.get('source') or 'Unknown source')[:40]} — "
        f"{str(item.get('title') or '')[:140]} ({str(item.get('time') or '')[:30]})\n"
        f"Family: {publisher_family(item)[:40]}; evidence: {evidence_label(item)}; "
        f"origin mentions: {(', '.join(declared_origins(item)) or 'Unknown')[:60]}; "
        f"{freshness(item)[0]}; {update_label(item)}; kind: {str(item.get('kind', 'Unknown'))[:30]}"
        + (f"\nAnalysis role: {item['_analysis_role']}" if item.get('_analysis_role') else '')
        for index, item in enumerate(items, 1)
    ]
    # Headers and the map are valuable context; allocate only the remaining space
    # to excerpts. Divide the remainder fairly across available sources.
    fixed = sum(len(header) + 24 for header in headers) + (len(investigation) + 2 if investigation else 0)
    remaining = max(0, budget - fixed)
    parts = []
    sources_left = max(1, len(items))
    for item, header in zip(items, headers, strict=True):
        body = str(item.get('reader_text') or item.get('summary') or '')
        allocation = remaining // sources_left
        if item.get('reader_text'):
            limit = min(6000 if profile == 'deep' else 2600, allocation)
            label = 'Publisher page extract'
        else:
            limit = min(1200, allocation)
            label = 'RSS excerpt'
        clipped = body[:max(0, limit)]
        remaining = max(0, remaining - len(clipped))
        sources_left -= 1
        parts.append(f'{header}\n{label}: {clipped}')
    evidence = '\n\n'.join(parts)
    result = evidence + ('\n\n' + investigation if investigation else '')
    return result[:budget]
