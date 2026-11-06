"""Find the stories that answer a question: BM25 ranking over loaded news and the library.

Fast, local and language-tolerant (accents and case are ignored). Used by Ask the news.
"""
from __future__ import annotations

import math
import time
from collections import Counter

from .articles import article_key
from .feeds import _STORY_STOP_WORDS
from .intel import _words

K1, B = 1.4, 0.75
_EXTRA_STOP = frozenset("what which when where does did do is are was were how why who whom will would should "
                        "can could about tell me latest news today happening there their any".split())


def tokens(text: str) -> list[str]:
    return [word for word in _words(text) if len(word) > 1 and word not in _STORY_STOP_WORDS
            and word not in _EXTRA_STOP]


class SearchIndex:
    def __init__(self, articles: list[dict]):
        unique: dict[str, dict] = {}
        for article in articles:
            unique.setdefault(article_key(article), article)
        self.articles = list(unique.values())
        self.terms: list[Counter] = []
        self.lengths: list[int] = []
        document_frequency: Counter = Counter()
        for article in self.articles:
            # The headline counts twice: it states what the report is about.
            words = tokens(article.get("title", "")) * 2 + tokens(article.get("summary", ""))
            counts = Counter(words)
            self.terms.append(counts)
            self.lengths.append(len(words))
            document_frequency.update(counts.keys())
        total = max(1, len(self.articles))
        self.average = sum(self.lengths) / total if self.lengths else 1.0
        self.idf = {term: math.log(1 + (total - count + 0.5) / (count + 0.5))
                    for term, count in document_frequency.items()}

    def search(self, query: str, limit: int = 10, now: float | None = None,
               diverse: bool = True) -> list[tuple[float, dict]]:
        query_terms = tokens(query)
        if not query_terms:
            return []
        now = time.time() if now is None else now
        scored = []
        for index, counts in enumerate(self.terms):
            score = 0.0
            length = self.lengths[index] or 1
            for term in query_terms:
                frequency = counts.get(term)
                if frequency:
                    score += self.idf[term] * frequency * (K1 + 1) / (
                        frequency + K1 * (1 - B + B * length / self.average))
            if score > 0:
                article = self.articles[index]
                try:
                    hours = max(0.0, (now - float(article.get("timestamp") or 0)) / 3600)
                except (TypeError, ValueError):
                    hours = 72.0
                # Newer reports win close calls.
                scored.append((score * (1 + 0.25 * 0.5 ** (hours / 24)), article))
        scored.sort(key=lambda pair: -pair[0])
        if not diverse:
            return scored[:limit]
        result, per_source = [], Counter()
        for score, article in scored:
            source = article.get("source", "")
            if per_source[source] >= 2:
                continue
            per_source[source] += 1
            result.append((score, article))
            if len(result) >= limit:
                break
        return result
