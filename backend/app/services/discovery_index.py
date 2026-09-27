"""Source-offset paragraph/Q&A index and corpus-derived topic proposals."""
import hashlib,json,re
from collections import Counter
from app.core.arabic_utils import normalize_search_text,safe_tokens
from app.services.query_language import KEYS
QUESTION=re.compile(r'(?:^|\n|(?<= ))\s*(?:سؤال|السؤال|السائل|س)\s*[:：]')
ANSWER=re.compile(r'(?:الجواب|الإجابة|الاجابة|مولانا الشيخ|سيدي فخر الدين|ج)\s*[:：]')
def build_discovery_indexes(conn):
 for t in ('discovery_fts','discovery_passages','term_document_frequency','discovery_topics','discovery_meta'):conn.execute('DROP TABLE IF EXISTS '+t)
 conn.execute('CREATE TABLE discovery_passages(id INTEGER PRIMARY KEY,page_id INTEGER,start_char INTEGER,end_char INTEGER,question TEXT,kind TEXT)')
 conn.execute('CREATE VIRTUAL TABLE discovery_fts USING fts5(body,question)')
 conn.execute('CREATE TABLE term_document_frequency(term TEXT PRIMARY KEY,documents INTEGER)')
 conn.execute('CREATE TABLE discovery_topics(label TEXT,terms TEXT,page_id INTEGER,start_char INTEGER,method TEXT,review_status TEXT)')
 conn.execute('CREATE TABLE discovery_meta(key TEXT PRIMARY KEY,value TEXT)')
 df=Counter();pairs=Counter();examples={};count=0;qa=0;digest=hashlib.sha256()
 rows=conn.execute('SELECT id,text,block_type FROM pages ORDER BY id').fetchall()
 from app.core.evidence_blocks import blocks
 for page_id,text,kind in rows:
  digest.update(f'{page_id}\0{text}'.encode());df.update(set(safe_tokens(normalize_search_text(text,level='broad'))))
  for block in blocks(text,kind):
   body=text[block['start']:block['end']]
   if block['type']=='toc':
    for line in body.splitlines():
     tokens=[t for t in safe_tokens(normalize_search_text(line,level='broad')) if t not in KEYS and len(t)>2]
     if len(tokens)>=2:conn.execute('INSERT INTO discovery_topics VALUES(?,?,?,?,?,?)',(line[:180],json.dumps(tokens[:12],ensure_ascii=False),page_id,block['start'],'source_contents','unreviewed'))
    continue
   tokens=[t for t in safe_tokens(normalize_search_text(body,level='broad')) if t not in KEYS and len(t)>2]
   for a,b in zip(tokens,tokens[1:]):
    if a!=b:pairs[(a,b)]+=1;examples.setdefault((a,b),(page_id,block['start']))
   windows=[(s,min(s+900,block['end']),'','paragraph') for s in range(block['start'],block['end'],650)]
   questions=list(QUESTION.finditer(body))
   for i,m in enumerate(questions):
    stop=questions[i+1].start() if i+1<len(questions) else len(body);ans=ANSWER.search(body,m.end(),stop)
    if ans:windows.append((block['start']+ans.end(),block['start']+stop,body[m.end():ans.start()].strip()[:600],'answer'));qa+=1
   for start,end,q,k in windows:
    if end<=start:continue
    count+=1;conn.execute('INSERT INTO discovery_passages VALUES(?,?,?,?,?,?)',(count,page_id,start,end,q,k))
    conn.execute('INSERT INTO discovery_fts(rowid,body,question) VALUES(?,?,?)',(count,normalize_search_text(text[start:end],level='broad'),normalize_search_text(q,level='broad')))
 conn.executemany('INSERT INTO term_document_frequency VALUES(?,?)',df.items())
 for (a,b),n in pairs.most_common():
  if n<3:break
  if max(df[a],df[b])>len(rows)*.15:continue
  page_id,start=examples[(a,b)];conn.execute('INSERT INTO discovery_topics VALUES(?,?,?,?,?,?)',(a+' '+b,json.dumps([a,b],ensure_ascii=False),page_id,start,'adjacent_cooccurrence','unreviewed'))
  if conn.execute('SELECT COUNT(*) FROM discovery_topics').fetchone()[0]>=500:break
 meta={'corpus_digest':digest.hexdigest(),'pages':len(rows),'answer_windows':qa,'passages':count,'topic_groups':conn.execute('SELECT COUNT(*) FROM discovery_topics').fetchone()[0]}
 conn.executemany('INSERT INTO discovery_meta VALUES(?,?)',[(k,str(v)) for k,v in meta.items()]);return meta
