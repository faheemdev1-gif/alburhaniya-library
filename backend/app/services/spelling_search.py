"""Hamza-only discovery with original source evidence and separate literal counts."""
from itertools import product
from pathlib import Path
from app.core.arabic_utils import normalize_alef, normalize_search_text


def variants(query, db):
    tokens = normalize_search_text(query).split()
    if not tokens or len(tokens) > 8:
        return [query]
    path = Path(db.get_settings().library_db_path).resolve()
    stamp = path.stat()
    vocabulary = db._spelling_subset(str(path), stamp.st_mtime_ns, stamp.st_size,
                                     tuple(sorted({normalize_search_text(token, level="broad") for token in tokens})))
    groups = []
    for token in tokens:
        broad = normalize_search_text(token, level='broad')
        forms = {token}
        forms.update(form for form in vocabulary.get(broad, ())
                     if normalize_alef(form) == normalize_alef(token))
        groups.append(sorted(forms))
    size = 1
    for group in groups:
        size *= len(group)
    # Bound query expansion rather than silently returning an incomplete census.
    if size > 128:
        return [query]
    return [' '.join(parts) for parts in product(*groups)]


def search(raw_queries, *, db, **kwargs):
    expanded = [variants(query, db) for query in raw_queries]
    if all(len(forms) == 1 for forms in expanded):
        return None
    offset = kwargs.pop('offset', 0)
    limit = kwargs.pop('limit', 8)
    diversify = kwargs.pop('diversify_books', True)
    max_per_book = kwargs.pop('max_per_book', 2)
    operator = kwargs.pop('operator', 'OR')
    groups = []
    for original, forms in zip(raw_queries, expanded):
        rows = db.search(queries=forms, operator='OR', search_mode='exact_phrase',
                         limit=10000, offset=0, diversify_books=False, **kwargs)
        grouped = {}
        for row in rows:
            start, end = row['evidence_span']['start'], row['evidence_span']['end']
            text = db.get_page(row['book_id'], row['seq'])['text'][start:end]
            row.update(match_type='spelling_discovery', original_queries=raw_queries,
                       normalization_level='hamza_discovery',
                       reformulation_warning='Hamza spelling discovery; literal counts retain the original spelling.',
                       matched_terms={original: {'corpus_form': text, 'relation': 'hamza_variant' if normalize_search_text(text) != normalize_search_text(original) else 'exact'}},
                       answer_verified=False)
            grouped[(row['book_id'], row['seq'])] = row
        groups.append(grouped)
    keys = set(groups[0])
    for group in groups[1:]:
        keys = keys & set(group) if operator == 'AND' else keys | set(group)
    rows = [next(group[key] for group in groups if key in group) for key in keys]
    ranking = kwargs.get('ranking', 'primary_first')
    if ranking in {'book_order', 'chronological'}:
        rows.sort(key=lambda row: (row['book_id'], row['seq']))
    elif ranking == 'primary_first':
        rows.sort(key=db.primary_first_sort_key)
    else:
        rows.sort(key=lambda row: (-row['score'], row['book_id'], row['seq']))
    if diversify and len(kwargs.get('book_ids') or []) != 1:
        counts, selected = {}, []
        for row in rows:
            book = row['book_id']
            if counts.get(book, 0) < max_per_book:
                counts[book] = counts.get(book, 0) + 1
                selected.append(row)
        rows = selected
    rows = rows[offset:offset + limit]
    for rank, row in enumerate(rows, offset + 1):
        row['rank'] = rank
    return rows
