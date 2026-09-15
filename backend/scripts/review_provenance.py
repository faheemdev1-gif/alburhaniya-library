#!/usr/bin/env python3
"""Create a reproducible review inventory, not an authorship certification."""
import argparse
from datetime import date
import hashlib
import json
from pathlib import Path
import re
import sqlite3

ROOT=Path(__file__).resolve().parent.parent


def inventory(db_path):
    conn=sqlite3.connect(f'file:{Path(db_path).resolve()}?mode=ro',uri=True)
    conn.row_factory=sqlite3.Row
    records=[]
    try:
        for book in conn.execute('SELECT * FROM books ORDER BY book_id').fetchall():
            unresolved=any(x in book['provenance_status'] for x in
                ('not_identified','needs_review','provisional','unverified'))
            digest=hashlib.sha256()
            candidates=[]
            pages=conn.execute('SELECT seq,citation_label,text FROM pages WHERE book_id=? ORDER BY seq',(book['book_id'],)).fetchall()
            for page in pages:
                digest.update(page['text'].encode('utf-8'))
                if page['seq'] > 3 and page['seq'] < len(pages)-2:
                    continue
                for match in re.finditer(r'تأليف|إعداد|جمعه|جمعها|تحقيق|المؤلف|المحقق',page['text']):
                    start=max(0,match.start()-80);end=min(len(page['text']),match.end()+160)
                    candidates.append({'seq':page['seq'],'citation_label':page['citation_label'],
                        'start':start,'end':end,'excerpt':page['text'][start:end],
                        'status':'unreviewed_attribution_clue_not_proof'})
                    if len(candidates)>=6:break
                if len(candidates)>=6:break
            # Hash every page, even when the bounded clue list is already full.
            digest=hashlib.sha256(''.join(p['text'] for p in pages).encode('utf-8'))
            records.append({'book_id':book['book_id'],'title':book['title'],
                'source_author':book['source_author'],'compiler':book['compiler'],
                'existing_provenance_status':book['provenance_status'],
                'attribution_confidence':book['attribution_confidence'],
                'review_date':date.today().isoformat(),
                'review_status':'documentary_review_required' if unresolved else 'existing_attribution_preserved_not_recertified',
                'review_method':'automated_front_and_back_matter_triage',
                'corpus_text_sha256':digest.hexdigest(),'candidate_evidence':candidates,
                'required_next_evidence':'Signed title page, colophon, official catalogue, or documented transmission/compilation attribution.' if unresolved else None})
    finally:conn.close()
    return {'review_basis':'Supplied parsed corpus and existing catalogue only; no independent documentary authentication.',
            'author_metadata_changed':False,'records':records,
            'documentary_review_required':sum(r['review_status']=='documentary_review_required' for r in records)}


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--db',default=str(ROOT/'library.db'))
    parser.add_argument('--output',default=str(ROOT/'data/provenance_review.json'))
    args=parser.parse_args()
    result=inventory(args.db)
    Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'books':len(result['records']),'documentary_review_required':result['documentary_review_required'],'author_metadata_changed':False}))
