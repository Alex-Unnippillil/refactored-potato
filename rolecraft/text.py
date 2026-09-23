from __future__ import annotations

import hashlib
import html
import math
import re
from html.parser import HTMLParser

# This compact ontology is intentionally labelled as a DEMO concept index, not a
# pretrained language model. The production provider uses actual neural embeddings.
CONCEPTS = {
    'async': ('async', 'asynchronous', 'written communication', 'fewer meetings', 'deep work', 'maker schedule', 'focus time', 'documentation first'),
    'balance': ('work life', 'work-life', 'balance', 'calm', 'sustainable pace', 'no on-call', 'quiet', 'boundaries', 'no weekends', 'four-day'),
    'ownership': ('ownership', 'autonomy', 'own a product', 'end-to-end', 'small team', 'independent', 'decision making'),
    'mentorship': ('mentorship', 'mentor', 'coaching', 'pair programming', 'junior', 'early career', 'entry level'),
    'mission': ('mission', 'climate', 'sustainability', 'education', 'accessibility', 'healthcare', 'social impact', 'nonprofit'),
    'learning': ('learning', 'growth', 'professional development', 'conference budget', 'research', 'experimentation'),
    'backend': ('backend', 'back-end', 'python', 'api', 'distributed systems', 'go', 'postgres', 'sql'),
    'frontend': ('frontend', 'front-end', 'react', 'typescript', 'design systems', 'web interfaces', 'javascript'),
    'ai': ('ai', 'machine learning', 'llm', 'rag', 'artificial intelligence', 'embeddings', 'neural', 'intelligent'),
    'data': ('data', 'analytics', 'warehouse', 'dbt', 'etl', 'pipeline', 'business intelligence'),
    'design': ('design', 'ux', 'user experience', 'user research', 'figma', 'product designer'),
    'infrastructure': ('infrastructure', 'devops', 'aws', 'cloud', 'kubernetes', 'platform', 'reliability', 'security'),
}
LABELS = {'async': 'Async-friendly', 'balance': 'Sustainable pace', 'ownership': 'Real ownership', 'mentorship': 'Mentorship', 'mission': 'Mission-driven', 'learning': 'Room to grow'}
STOP = set('a an and are as at be by for from i in is it me my of on or that the this to want with work looking role job team company more like would where you your'.split())


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.skip += 1
        if tag in ('p', 'br', 'li', 'h1', 'h2', 'h3', 'div') and not self.skip:
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in ('script', 'style') and self.skip:
            self.skip -= 1
        if tag in ('p', 'li', 'div') and not self.skip:
            self.parts.append('\n')

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def plain_text(value: str) -> str:
    parser = PlainText()
    parser.feed(html.unescape(value))
    return re.sub(r'\n{3,}', '\n\n', '\n'.join(' '.join(line.split()) for line in ''.join(parser.parts).splitlines())).strip()


def tokens(text: str) -> list[str]:
    return [t for t in re.findall(r'[a-z0-9]+', text.lower()) if len(t) > 1 and t not in STOP][:2000]


def has_phrase(text: str, phrase: str) -> bool:
    return bool(re.search(r'(?<!\w)' + re.escape(phrase) + r'(?!\w)', text, re.I))


def themes(text: str) -> set[str]:
    return {key for key, phrases in CONCEPTS.items() if any(has_phrase(text, p) for p in phrases)}


def chunk_text(text: str, size: int = 1100, overlap: int = 160) -> list[str]:
    """Bounded character chunks with word-boundary overlap and exact source spans.

    1,100 characters is deliberately conservative for multilingual tokenization.
    Unlike word counts, a character bound also protects against very long words.
    """
    if size < 100 or overlap < 0 or overlap >= size // 2:
        raise ValueError('Use size >= 100 and overlap < half the chunk size.')
    chunks, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            boundary = text.rfind(' ', start + size // 2, end)
            if boundary > start:
                end = boundary
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == len(text):
            break
        following = max(start + 1, end - overlap)
        boundary = text.find(' ', following, end)
        start = boundary + 1 if boundary >= following else following
    return chunks


def concept_vector(text: str) -> list[float]:
    vector = [0.0] * 256
    present = themes(text)
    for index, key in enumerate(CONCEPTS):
        if key in present:
            vector[index] = 3.0
    for token in set(tokens(text)):
        digest = hashlib.blake2b(token.encode(), digest_size=4).digest()
        vector[32 + int.from_bytes(digest, 'big') % 224] += 0.35
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


def cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        raise ValueError('Embedding dimensions do not match.')
    return sum(x * y for x, y in zip(a, b))


def evidence(description: str, query: str, preferences: list[str]) -> list[dict]:
    wanted = set(preferences) | (themes(query) & set(LABELS))
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+|\n+', description) if s.strip()]
    found = []
    for key in LABELS:
        if key not in wanted:
            continue
        for sentence in sentences:
            if any(has_phrase(sentence, p) for p in CONCEPTS[key]):
                found.append({'theme': key, 'label': LABELS[key], 'quote': sentence[:500]})
                break
    if not found:
        query_terms = set(tokens(query))
        ranked = sorted(sentences, key=lambda s: len(query_terms & set(tokens(s))), reverse=True)
        if ranked:
            found.append({'theme': 'description', 'label': 'From the description', 'quote': ranked[0][:500]})
    return found[:3]
