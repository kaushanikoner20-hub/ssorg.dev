"""Stage 4: keyword search and the evidence retrieval behind Ask ssorg.

Everything here works on the local SQLite library. Searching never runs OCR
or the AI again: it only reads text that was saved when the screenshot was
imported. Nothing here talks to the network.

Two things live in this file:
1. Keyword search for the Search page: search_screenshots, filter_screenshots,
   get_recent_screenshots, make_snippet, highlight_segments.
2. Evidence retrieval for Ask ssorg: extract_keywords, retrieve_evidence.
   It picks a few relevant screenshots and trims their text. Asking the AI is
   done in ask.py, using only what is picked here.

The SQL itself is in database.search_screenshot_rows (parameterized).
"""

import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone

from app import config, database

# Human-friendly names for the searchable fields (used to say where a match was found).
FIELD_LABELS = {
    "original_filename": "filename",
    "ocr_text": "extracted text",
    "short_summary": "summary",
    "category": "category",
    "named_entities": "named entities",
    "useful_search_terms": "search terms",
    "important_dates": "dates in the text",
}

SORT_OPTIONS = ("relevance", "newest", "oldest", "category")


# =====================================================================
# Keyword search
# =====================================================================
@dataclass
class SearchHit:
    """One matching screenshot, with a short snippet showing where it matched."""

    record: dict
    snippet: str = ""
    snippet_field: str = ""
    matched_fields: list[str] = field(default_factory=list)
    score: int = 0


@dataclass
class SearchResponse:
    """One page of search results."""

    hits: list[SearchHit]
    total: int  # all matches, not just this page
    terms: list[str]
    limit: int
    offset: int
    terms_were_cut: bool = False  # the query had more words than we use


def parse_query(query: str | None) -> tuple[list[str], bool]:
    """Split a search query into terms. "Quoted words" stay together as one phrase.

    Returns (terms, were_some_terms_dropped). Empty or blank queries give [].
    """
    text = (query or "").strip()[: config.SEARCH_MAX_QUERY_CHARS]
    terms: list[str] = []
    for phrase, word in re.findall(r'"([^"]+)"|(\S+)', text):
        term = " ".join((phrase or word).split()).strip('"')
        if term and term.lower() not in [existing.lower() for existing in terms]:
            terms.append(term)
    cut = len(terms) > config.SEARCH_MAX_TERMS
    return terms[: config.SEARCH_MAX_TERMS], cut


def local_date_bounds(
    start: date | None = None, end: date | None = None
) -> tuple[str | None, str | None]:
    """Turn two local calendar dates into UTC timestamps for the database.

    The end date is included: the upper bound is the start of the next day.
    """
    def to_utc_text(day: date) -> str:
        local_midnight = datetime.combine(day, time.min).astimezone()  # computer's time zone
        return local_midnight.astimezone(timezone.utc).isoformat(timespec="seconds")

    created_from = to_utc_text(start) if start else None
    created_to = to_utc_text(end + timedelta(days=1)) if end else None
    return created_from, created_to


def _field_texts(record: dict) -> dict[str, str]:
    """The searchable text of a record, one string per field."""
    return {
        "original_filename": record.get("original_filename") or "",
        "ocr_text": record.get("ocr_text") or "",
        "short_summary": record.get("short_summary") or "",
        "category": record.get("category") or "",
        "named_entities": ", ".join(record.get("named_entities") or []),
        "useful_search_terms": ", ".join(record.get("useful_search_terms") or []),
        "important_dates": ", ".join(record.get("important_dates") or []),
    }


def matched_fields(record: dict, terms: list[str]) -> list[str]:
    """Names of the fields that contain at least one of the terms."""
    lowered = [term.lower() for term in terms]
    found = []
    for name, text in _field_texts(record).items():
        if any(term in text.lower() for term in lowered):
            found.append(FIELD_LABELS[name])
    return found


def _window(text: str, position: int, width: int) -> str:
    """Cut about `width` characters around `position`, with ... where text was cut."""
    start = max(0, position - width // 3)
    end = min(len(text), start + width)
    start = max(0, end - width)
    return ("..." if start > 0 else "") + text[start:end].strip() + ("..." if end < len(text) else "")


def make_snippet(record: dict, terms: list[str], width: int = 160) -> tuple[str, str]:
    """A short piece of text around the first match. Returns (snippet, field label).

    Looks in the extracted text first, then the other fields. Returns ("", "")
    when there is nothing to show (for example with an empty query).
    """
    if not terms:
        return "", ""
    texts = _field_texts(record)
    for name in ("ocr_text", "short_summary", "original_filename", "named_entities",
                 "useful_search_terms", "important_dates", "category"):
        text = " ".join(texts[name].split())
        positions = [text.lower().find(term.lower()) for term in terms]
        positions = [position for position in positions if position >= 0]
        if positions:
            return _window(text, min(positions), width), FIELD_LABELS[name]
    return "", ""


def highlight_segments(text: str, terms: list[str]) -> list[tuple[str, bool]]:
    """Split text into (piece, is_match) parts so the interface can emphasize matches."""
    terms = [term for term in terms if term]
    if not text or not terms:
        return [(text, False)] if text else []
    pattern = re.compile("|".join(re.escape(term) for term in sorted(terms, key=len, reverse=True)), re.IGNORECASE)
    segments, last_end = [], 0
    for match in pattern.finditer(text):
        if match.start() > last_end:
            segments.append((text[last_end:match.start()], False))
        segments.append((match.group(0), True))
        last_end = match.end()
    if last_end < len(text):
        segments.append((text[last_end:], False))
    return segments


def search_screenshots(
    query: str | None = "",
    category: str | None = None,
    date_range: tuple[date | None, date | None] | None = None,
    sort: str = "relevance",
    limit: int | None = None,
    offset: int = 0,
    db_path=None,
) -> SearchResponse:
    """Search the library. An empty query lists screenshots (so filters and sorting still work).

    Every word must appear somewhere in the screenshot's searchable fields:
    filename, extracted text, summary, category, named entities, search terms
    and the dates the AI found. Raises database.DatabaseError if the library cannot be read.
    """
    terms, cut = parse_query(query)
    created_from, created_to = local_date_bounds(*(date_range or (None, None)))
    page_size = limit or config.SEARCH_PAGE_SIZE
    sort = sort if sort in SORT_OPTIONS else "relevance"

    records, total = database.search_screenshot_rows(
        terms=terms, match_all=True, category=category or None,
        created_from=created_from, created_to=created_to,
        sort=sort, limit=page_size, offset=offset, db_path=db_path,
    )
    hits = []
    for record in records:
        snippet, snippet_field = make_snippet(record, terms)
        hits.append(SearchHit(
            record=record, snippet=snippet, snippet_field=snippet_field,
            matched_fields=matched_fields(record, terms) if terms else [],
            score=int(record.get("relevance_score") or 0),
        ))
    return SearchResponse(hits=hits, total=total, terms=terms, limit=page_size, offset=offset, terms_were_cut=cut)


def filter_screenshots(
    category: str | None = None,
    date_range: tuple[date | None, date | None] | None = None,
    sort: str = "newest",
    limit: int | None = None,
    offset: int = 0,
    db_path=None,
) -> SearchResponse:
    """List screenshots by category and/or import date, without any search words."""
    return search_screenshots("", category=category, date_range=date_range, sort=sort,
                              limit=limit, offset=offset, db_path=db_path)


def get_recent_screenshots(limit: int = 10, db_path=None) -> list[dict]:
    """The most recently imported screenshots (reuses the existing database function)."""
    return database.get_all_screenshots(limit=limit, db_path=db_path)


# =====================================================================
# Evidence retrieval for Ask ssorg
# =====================================================================
# Words that carry no search value in a question. They are ignored so that a
# question like "Which screenshot mentions my assignment deadline?" searches
# for "assignment" and "deadline". Words like "screenshot" are listed because
# every record would match them.
STOPWORDS = frozenset("""
a about above after again all also am an and any are as at be because been before being below between both
but by can could did do does doing down during each few find for from further get give had has have having he
her here hers him his how i if in into is it its just like me more most my myself no nor not now of off on once
only or other our ours out over own same she should show shows shown so some such than that the their them then
there these they this those through to too under until up us very was we were what when where which while who
whom why will with would you your yours
screenshot screenshots screen image images picture pictures photo photos saved save mention mentions mentioned
mentioning contain contains containing contained tell look looking see seen know remember did ssorg
""".split())


@dataclass
class EvidenceItem:
    """One screenshot chosen as evidence. Only these fields are ever sent to the AI."""

    id: int
    original_filename: str
    category: str
    imported: str   # date only, for example 2026-10-21 (UTC)
    summary: str
    excerpt: str    # a trimmed piece of the OCR text around the matches
    matched_terms: list[str] = field(default_factory=list)
    score: int = 0


@dataclass
class EvidenceResult:
    """The outcome of looking for evidence for one question."""

    keywords: list[str]
    items: list[EvidenceItem]


def extract_keywords(question: str | None) -> list[str]:
    """Pick the useful words of a question, locally and deterministically.

    Lowercases, drops common words, keeps order, removes repeats, keeps at most
    SEARCH_MAX_TERMS words. Numbers are kept (a price or a date can be the clue).
    """
    keywords: list[str] = []
    for word in re.findall(r"[\w][\w.\-]*", (question or "").lower()):
        word = word.strip(".-")
        if len(word) < 2 and not word.isdigit():
            continue
        if word in STOPWORDS or word in keywords:
            continue
        keywords.append(word)
    return keywords[: config.SEARCH_MAX_TERMS]


def expand_variants(word: str) -> list[str]:
    """A word plus a simple singular form, so 'headphones' also finds 'headphone'."""
    variants = [word]
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        variants.append(word[:-1])
    return variants


def _find_positions(text: str, words: list[str]) -> list[int]:
    lowered = text.lower()
    positions = [lowered.find(word) for word in words]
    return sorted(position for position in positions if position >= 0)


def extract_excerpt(text: str, words: list[str], max_chars: int) -> str:
    """A trimmed piece of OCR text around the matches, at most `max_chars` long.

    With several matches far apart, short windows around each (up to 3) are joined with ' ... '.
    """
    text = " ".join((text or "").split())
    if max_chars <= 0 or not text:
        return ""
    if len(text) <= max_chars:
        return text
    positions = _find_positions(text, words)
    if not positions:
        return text[:max_chars].rstrip() + "..."
    # Keep the first match of up to 3 matches, spread out.
    chosen = positions[:1]
    for position in positions[1:]:
        if len(chosen) < 3 and position - chosen[-1] > max_chars // 3:
            chosen.append(position)
    half = max(20, max_chars // (2 * len(chosen)))
    windows: list[list[int]] = []
    for position in chosen:
        start, end = max(0, position - half), min(len(text), position + half)
        if windows and start <= windows[-1][1]:
            windows[-1][1] = max(windows[-1][1], end)
        else:
            windows.append([start, end])
    pieces = [("..." if s > 0 else "") + text[s:e].strip() + ("..." if e < len(text) else "") for s, e in windows]
    return " ".join(pieces)[:max_chars]


def _item_overhead(item: EvidenceItem) -> int:
    """Roughly how many characters an item's non-excerpt fields take in the prompt."""
    return 60 + len(item.original_filename) + len(item.category) + len(item.imported) + len(item.summary)


def retrieve_evidence(question: str, db_path=None) -> EvidenceResult:
    """Find the screenshots most relevant to a question.

    Steps (all local, no AI): keywords -> SQLite OR-search -> rank by how many
    keywords matched, then by the field-weighted score, then newest -> keep the best
    ASK_MAX_EVIDENCE -> trim their OCR text so the total stays under ASK_CONTEXT_CHARS.
    Returns no items when nothing matches, and then no AI call should be made.
    """
    keywords = extract_keywords(question)
    if not keywords:
        return EvidenceResult(keywords=[], items=[])

    flat_terms = []
    for word in keywords:
        flat_terms.extend(expand_variants(word))
    records, _ = database.search_screenshot_rows(
        terms=flat_terms, match_all=False, sort="relevance",
        limit=config.ASK_CANDIDATE_LIMIT, db_path=db_path,
    )

    ranked = []
    for record in records:
        texts = " ".join(_field_texts(record).values()).lower()
        matched = [word for word in keywords if any(variant in texts for variant in expand_variants(word))]
        if matched:
            ranked.append((len(matched), int(record.get("relevance_score") or 0), record["created_at"], record, matched))
    ranked.sort(key=lambda entry: (entry[0], entry[1], entry[2]), reverse=True)
    best = ranked[: config.ASK_MAX_EVIDENCE]

    # Build items with a fair share of the total text budget for each excerpt.
    drafts = []
    for _, score, _, record, matched in best:
        drafts.append(EvidenceItem(
            id=record["id"],
            original_filename=(record["original_filename"] or "")[:120],
            category=record["category"] or "",
            imported=(record["created_at"] or "")[:10],
            summary=" ".join((record["short_summary"] or "").split())[:300],
            excerpt="",
            matched_terms=matched,
            score=score,
        ))
    if not drafts:
        return EvidenceResult(keywords=keywords, items=[])
    overhead = sum(_item_overhead(item) for item in drafts)
    per_item = min(config.ASK_EXCERPT_CHARS, max(150, (config.ASK_CONTEXT_CHARS - overhead) // len(drafts)))
    for item, (_, _, _, record, matched) in zip(drafts, best):
        variants = [variant for word in matched for variant in expand_variants(word)]
        item.excerpt = extract_excerpt(record["ocr_text"], variants, per_item)

    # Final guard: if the total is still too large, drop the least relevant items.
    while len(drafts) > 1 and sum(_item_overhead(i) + len(i.excerpt) for i in drafts) > config.ASK_CONTEXT_CHARS:
        drafts.pop()
    return EvidenceResult(keywords=keywords, items=drafts)