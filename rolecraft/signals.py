"""Conservative, inspectable English evidence rules, not a culture classifier.

Only explicitly selected preferences are assessed. Negation/hedging is bounded
and deliberately abstains in ambiguous clauses. Source spans remain exact.
"""
from __future__ import annotations

import re
from .text import LABELS, tokens

POLICY = 'selected-preferences-lexical-v1'
SUPPORT = {
    'async': r'asynchronous|async[- ](?:first|friendly)|written communication|fewer meetings|deep work|maker schedule|(?:protected )?focus time|documentation[- ]first',
    'balance': r'work[- ]life balance|sustainable pace|no on[- ]call|no weekends|four[- ]day (?:work)?week|protected (?:evenings|weekends)|calm (?:team|workplace)|clear boundaries',
    'ownership': r'ownership|autonomy|own (?:a|the|your) (?:product|service|roadmap)|end[- ]to[- ]end|decision[- ]making authority',
    'mentorship': r'mentorship|mentoring|dedicated mentor|paired with a mentor|weekly coaching|pair programming',
    'mission': r'mission[- ]driven|social impact|nonprofit|climate|clean energy|sustainability|education|accessibility|healthcare',
    'learning': r'learning budget|learning time|professional development|conference budget|research time|experimentation|room to grow|career development',
}
CONFLICT = {
    'async': r'meeting[- ]heavy|synchronous[- ]first|constant meetings|mandatory daily meetings',
    'balance': r'on[- ]call (?:rotation|rota|duty)|mandatory overtime|regular weekend work|weekend work (?:is )?required|24/7 availability',
    'ownership': r'limited autonomy|all decisions (?:are )?made by management',
    'mentorship': r'no (?:formal )?mentor(?:ship|ing)|mentorship (?:is )?unavailable',
    'mission': r'no social impact|no sustainability commitment',
    'learning': r'no (?:dedicated )?learning (?:budget|time)|no professional development',
}
RULES = {key: (re.compile(r'(?<!\w)(?:' + SUPPORT[key] + r')(?!\w)', re.I),
               re.compile(r'(?<!\w)(?:' + CONFLICT[key] + r')(?!\w)', re.I)) for key in LABELS}
# Contrast boundaries prevent "not async, but ..." spilling into the next claim.
CLAUSE = re.compile(r'[^.!?;\n]+')
CONTRAST = re.compile(r'\b(?:but|however|whereas|although|yet)\b', re.I)
NEGATION = re.compile(r"\b(?:no|not|never|without|lack(?:s|ing)?(?: of)?|isn['’]t|aren['’]t|don['’]t|doesn['’]t|cannot|can['’]t)\b", re.I)
HEDGE = re.compile(r'\b(?:may|might|could|hope to|plan to|aim to|aspire to|considering|potential|possible)\b', re.I)
AFTER_NEGATION = re.compile(r"\s*(?:is|are|will be)?\s*(?:not\b|unavailable\b|absent\b|isn['’]t\b|aren['’]t\b)", re.I)
AFTER_HEDGE = re.compile(r'\s*(?:is|are)?\s*(?:optional|planned|not guaranteed)\b', re.I)


def _clauses(text: str):
    for sentence in CLAUSE.finditer(text):
        start = sentence.start()
        for boundary in CONTRAST.finditer(sentence.group()):
            end = sentence.start() + boundary.start()
            if start < end:
                yield start, end
            start = sentence.start() + boundary.end()
        if start < sentence.end():
            yield start, sentence.end()


def _context(clause: str, match: re.Match) -> tuple[bool, bool]:
    before = ' '.join(clause[:match.start()].split()[-8:])
    # "Not only X" is additive, not a denial. Other double negations abstain.
    before = re.sub(r'\bnot only\b', '', before, flags=re.I)
    after = clause[match.end():match.end() + 65]
    negative = bool(NEGATION.search(before) or AFTER_NEGATION.match(after))
    uncertain = bool(HEDGE.search(before) or AFTER_HEDGE.match(after) or
                     re.search(r"\b(?:cannot|can['’]t|do not|don['’]t) guarantee\b", before, re.I))
    return negative, uncertain


def _span(text: str, start: int, end: int, hit: int) -> dict:
    # Center long clauses near the evidence instead of always quoting the prefix.
    start = max(start, min(hit - 180, end - 500))
    end = min(end, start + 500)
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return {'quote': text[start:end], 'start': start, 'end': end}


def assess_preferences(description: str, preferences: list[str]) -> list[dict]:
    """Five states; supporting text is a source claim, not a verified benefit."""
    clauses = list(_clauses(description))
    assessments = []
    for key in dict.fromkeys(preferences):
        support, conflict = RULES[key]
        found: dict[str, dict] = {}
        for start, end in clauses:
            clause = description[start:end]
            for kind, rule in (('support', support), ('conflict', conflict)):
                for match in rule.finditer(clause):
                    negative, uncertain = _context(clause, match)
                    # A negated conflict does not establish a positive benefit.
                    polarity = ('uncertain' if uncertain else 'conflict' if negative else 'support') if kind == 'support' else ('uncertain' if negative or uncertain else 'conflict')
                    if kind == 'support' and not match.group().lower().startswith('no '):
                        for denial in conflict.finditer(clause):
                            if denial.start() < match.end() and denial.end() > match.start():
                                denied, hedged = _context(clause, denial)
                                polarity = 'uncertain' if denied or hedged else 'conflict'
                                break
                    if polarity not in found:
                        found[polarity] = {'theme': key, 'label': LABELS[key], 'polarity': polarity,
                                           **_span(description, start, end, start + match.start())}
        if 'support' in found and 'conflict' in found:
            status = 'mixed'
        elif 'conflict' in found:
            status = 'conflicting'
        elif 'support' in found:
            status = 'supporting'
        elif found:
            status = 'uncertain'
        else:
            status = 'not_found'
        assessments.append({'theme': key, 'label': LABELS[key], 'status': status,
                            'excerpts': [found[p] for p in ('conflict', 'uncertain', 'support') if p in found]})
    return assessments


def excerpts(description: str, query: str, assessments: list[dict]) -> list[dict]:
    found = [e for assessment in assessments for e in assessment['excerpts']]
    if found:
        # Contradicting text must not be hidden by a positive excerpt cap.
        return sorted(found, key=lambda e: {'conflict': 0, 'uncertain': 1, 'support': 2}[e['polarity']])[:3]
    query_terms = set(tokens(query))
    spans = list(CLAUSE.finditer(description))
    if not spans:
        return []
    best = max(spans, key=lambda m: len(query_terms & set(tokens(m.group()))))
    hits = [m.start() for m in re.finditer(r'\w+', best.group()) if m.group().lower() in query_terms]
    return [{'theme': 'description', 'label': 'From the description', 'polarity': 'neutral',
             **_span(description, best.start(), best.end(), best.start() + (hits[0] if hits else 0))}]
