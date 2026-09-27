#!/usr/bin/env python3
"""Record only documentary identifications visible in the supplied source."""
import json,sys,hashlib,sqlite3
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT))
from app.services import library_db as db
# Each anchor was inspected in the source, not inferred from a similar title.
CASES=[('b05',1,'الدكتور خالد العروسي','خالد العروسي','authored_work',None),
       ('b16',72,'نبذة عن المؤلف فضيلة الأستاذ فوزى محمد أبوزيد','فوزى محمد أبوزيد','authored_work',None),
       ('b17',1,'جمعه وحقَّقه وعلَّق عَلَيْه','إبراهيم الدسوقي محمد بدور','murid_commentary','إبراهيم الدسوقي محمد بدور'),
       ('b37',1,'أما أنا فلو لقيت عمنا عبد الحميد با بكر','عبد الحميد بابكر','compiled_durus','عبد الحميد بابكر')]
sources=json.loads((ROOT/'data/sources.json').read_text());records=[]
for book,seq,anchor,name,mode,compiler in CASES:
 page=db.get_page(book,seq);start=page['text'].index(anchor);end=min(len(page['text']),start+260)
 before=dict(sources['books'][book]);updates={'author':name,'compiler':compiler,'authorship_mode':mode,'attribution_confidence':'medium','provenance_status':'identified_in_supplied_front_matter' if book!='b16' else 'identified_in_supplied_author_biography'}
 # b37 preserves the teacher as speaker; the endorsee is the compiler only.
 if book=='b37':updates['author']=before['author']
 sources['books'][book].update(updates)
 records.append({'book_id':book,'seq':seq,'start':start,'end':end,'source_excerpt':page['text'][start:end],'source_text_sha256':hashlib.sha256(page['text'].encode()).hexdigest(),'before':before,'after':sources['books'][book],'basis':'Visible attribution in supplied text; scan authenticity not independently established','reviewer':'Codex source-text review','review_date':'2026-09-26'})
(ROOT/'data/sources.json').write_text(json.dumps(sources,ensure_ascii=False,indent=2)+'\n')
(ROOT/'data/provenance_decisions_2100.json').write_text(json.dumps({'records':records,'no_tier_upgrades':True},ensure_ascii=False,indent=2)+'\n')
# Refresh metadata without changing indexed source bytes.
with sqlite3.connect(ROOT/'library.db') as c:
 for record in records:
  s=record['after'];c.execute('UPDATE books SET source_author=?,compiler=?,authorship_mode=?,attribution_confidence=?,provenance_status=? WHERE book_id=?',(s['author'],s['compiler'],s['authorship_mode'],s['attribution_confidence'],s['provenance_status'],record['book_id']))
print('Four source-supported metadata records reviewed; other authorship questions remain open.')
