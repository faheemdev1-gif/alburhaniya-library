"""Phrase-first union and bounded source-local ranking; never answer grading."""
from functools import lru_cache
import re,html,os,json
from app.services import library_db as db
from app.services.query_language import language_plan,morphological_forms
from app.services.question_intent import plan,concept_regex
from app.core.arabic_utils import normalize_search_text,safe_tokens
from app.core.budget import expired
from app.core.evidence_blocks import body_text,INCLUDE_TOC
@lru_cache(maxsize=8192)
def pattern(term):
 inner='|'.join(db._build_highlight_regex(t,whole_word=False,normalization_level='broad').pattern for t in morphological_forms(term))
 return re.compile(r'(?<![ء-ي])(?:[وفبل])?(?:'+inner+r')(?:ات|ون|ين|ها|هم|ه|ي)?(?![ء-ي])')
@lru_cache(maxsize=4)
def _topics(path,mtime,size):return [json.loads(r[0]) for r in db._connection().execute('SELECT terms FROM discovery_topics')]
def topic_proposals(anchors):
 path=db.get_settings().library_db_path;st=os.stat(path);forms={f for t in anchors for f in morphological_forms(t)};proposals=[]
 for terms in _topics(os.path.abspath(path),st.st_mtime_ns,st.st_size):
  if any(t in forms for t in terms):proposals.extend(t for t in terms if t not in forms)
 return list(dict.fromkeys(proposals))[:12]
def anchor_plan(query,keep_terms=()):
 result=language_plan(query,keep_terms);conn=db._connection();total=int(conn.execute("SELECT value FROM discovery_meta WHERE key='pages'").fetchone()[0]);common=[];anchors=[]
 for t in result['terms']:
  forms=morphological_forms(t);row=conn.execute('SELECT MAX(documents) FROM term_document_frequency WHERE term IN ('+','.join('?'*len(forms))+')',forms).fetchone()
  if (row[0] or 0)>total*.15 and t not in keep_terms:common.append(t)
  else:anchors.append(t)
 result.update(anchors=anchors,common_nonanchors=common,frequency_basis='precomputed_corpus_document_frequency');return result
def dialogue_at(text,start):
 from app.services.discovery_index import QUESTION,ANSWER
 marks=[(m.start(),'question') for m in QUESTION.finditer(text)]+[(m.start(),'answer') for m in ANSWER.finditer(text)];prior=[m for m in marks if m[0]<=start]
 if not prior:return {}
 role=max(prior)[1];return {'dialogue_role':role,'speaker':'السائل' if role=='question' else None,'speaker_basis':'explicit_question_marker' if role=='question' else 'answer_marker_author_not_inferred'}
def supporting_span(query,text,keep_terms=()):
 terms=anchor_plan(query,keep_terms)['anchors'];p=plan(query);events=[]
 for t in terms:events.extend((m.start(),m.end(),'term:'+t,m.group()) for m in pattern(t).finditer(text))
 for group in p['groups']:events.extend((m.start(),m.end(),'concept:'+group,m.group()) for m in concept_regex(group).finditer(text))
 if not events:return None
 events.sort();best=None
 for start,end,tag,form in events:
  if expired():break
  boundary=text.find('\n\n',start,start+180);stop=boundary if boundary>=0 else start+180;local=[e for e in events if e[0]>=start and e[1]<=stop]
  if not local:continue
  matched={e[2][5:] for e in local if e[2].startswith('term:')};groups={e[2][8:] for e in local if e[2].startswith('concept:')};relation=bool(p['required']) and set(p['required'])<=groups;provision_remedy=False
  if p['required']==['provision']:
   window=text[max(0,start-15):start+180];provision_remedy=any(db._build_highlight_regex(t,whole_word=False).search(window) for t in ('تيسير الرزق','جلب الرزق','سعة الرزق','شكا الفقر','عنه الفقر'));relation='provision' in groups and (bool(groups.intersection({'relief','distress'})) or provision_remedy)
  for t in terms:
   if any(concept_regex(g).search(t) for g in groups):matched.add(t)
  if relation:
   required_events=[e for e in local if e[2] in {'concept:'+g for g in p['required']}];width=max(e[1] for e in required_events)-min(e[0] for e in required_events)
  else:width=180
  coverage=len(matched)/max(1,len(terms));required=len(groups.intersection(p['required']))/max(1,len(p['required']));value=.48*coverage+.24*required+.18*relation+(.18*(1-width/180) if relation else 0)
  if provision_remedy and relation:value+=.32
  if 'quran' in p['required']:
   window=text[max(0,start-50):stop+50];reading=bool(re.search(r'تلاوة|قراءة|يقرأ|تقرأ|بتقرأ|قراء|ورد',window))
   if not reading:value-=.28;relation=False
   elif re.search(r'كل يوم|ورد يومي|كتر منه|المداومة|يداوم|يواظب',window):value+=.20
  window=text[start:min(len(text),start+250)]
  if 'prayer' in p['required'] and re.search(r'الصلاة\s+(?:والسلام|على\s+النبي)',window) and 'timing' not in groups:value-=.25
  if re.search(r'قال الراوي|حكى|يحكى|حكاية',text[max(0,start-60):start]):value-=.06
  if re.search(r'ينبغي|عليك|يجب|المحافظة|الاجتهاد|احفظ|حفظ|لا تغضب',window):value+=.06
  candidate=(value,start,max(e[1] for e in local),sorted(matched),relation)
  if best is None or value>best[0]:best=candidate
 return best
def make_row(page,query,start,end,score,matched,relation):
 text=page['text'];row={k:v for k,v in page.items() if k not in ('text','has_next','has_prev','content_types','evidence_blocks')};snippet=db._evidence_excerpt(text,start,end,180,[])
 row.update(score=round(max(0,min(.99,score)),6),match_type='reformulated',score_kind='local_span_discovery',match_id=f"{page['book_id']}-p{page['seq']}-c{start}",snippet=snippet,evidence_span={'start':start,'end':end,'excerpt':snippet},original_queries=[query],reformulation_method='phrase_and_passage_union_v1',reformulation_warning='Candidate discovery only; inspect the Arabic passage before using it as an answer.',answer_verified=False,question_relevance='relation_candidate' if relation else 'topic_only',intent_term_coverage=round(len(matched)/max(1,len(language_plan(query)['terms'])),4),evidence_type=db.evidence_type(text,start,start+1),evidence_type_method='structural_heuristic',evidence_type_confidence='unverified',evidence_type_scope='start_anchor');row.update(dialogue_at(text,start));return row
def deduplicate(rows):
 kept=[];sets=[]
 for row in rows:
  words=safe_tokens(normalize_search_text(re.sub('<[^>]+>','',html.unescape(row['snippet'])),level='broad'));grams=set(zip(words,words[1:],words[2:]));duplicate=None
  if len(words)>=15:
   for i,other in enumerate(sets):
    if grams and len(grams&other)/len(grams|other)>=.82:duplicate=i;break
  if duplicate is not None:kept[duplicate].setdefault('alternate_locations',[]).append({k:row.get(k) for k in ('book_id','seq','match_id','citation_label','source_tier','provenance_status')})
  else:kept.append(row);sets.append(grams)
 return kept
def search_questions(**kwargs):
 queries=kwargs.get('queries') or [kwargs.get('query')];records={};keep=kwargs.pop('keep_terms',()) or ();scope={k:kwargs.get(k) for k in ('book_ids','source_code','page_from','page_to','qasida_number','min_tier')};pages={};support_cache={};literal_ids=set();query_ids=[]
 for query in queries:
  matched_ids=set();ap=anchor_plan(query,keep);literal=db.search(query=ap['subject_phrase'],search_mode='exact_phrase',limit=80,diversify_books=False,ranking='relevance',context_chars=kwargs.get('context_chars',180),**scope)
  for row in literal:
   key=(row['book_id'],row['seq']);literal_ids.add(key);matched_ids.add(key);row['score']=round(.91+.08*row['score'],6);row['answer_verified']=False;row['question_relevance']='phrase_candidate';records[key]=row
  if len(ap['terms'])<=3 and len(literal)>=kwargs.get('limit',8):query_ids.append(matched_ids);continue
  forms=list(dict.fromkeys(f for t in ap['anchors'] for f in morphological_forms(t)))
  from app.services.question_intent import CONCEPTS
  forms.extend(f for group in plan(query)['groups'] for f in CONCEPTS[group]);forms.extend(topic_proposals(ap['anchors']));expression=' OR '.join('"'+normalize_search_text(f,level='broad').replace('"','""')+'"*' for f in forms[:160] if len(f)>2)
  if not expression:query_ids.append(matched_ids);continue
  filters,params=db._search_filters(**scope);candidates=db._connection().execute('SELECT d.*,p.book_id,p.seq,bm25(discovery_fts,1,3) AS relevance FROM discovery_fts JOIN discovery_passages d ON d.id=discovery_fts.rowid JOIN pages p ON p.id=d.page_id JOIN books b ON b.book_id=p.book_id WHERE discovery_fts MATCH ?'+filters+' ORDER BY relevance LIMIT 100',[expression,*params]).fetchall()
  if plan(query)['groups'] and not expired():
   extras=db.reformulated_search(**{**kwargs,'queries':[query],'offset':0,'limit':35,'diversify_books':False,'include_topic_only':False});candidates=list(candidates)+[{'book_id':r['book_id'],'seq':r['seq'],'question':'','kind':'paragraph','start_char':0,'end_char':0} for r in extras]
  for candidate in candidates:
   if expired():break
   key=(candidate['book_id'],candidate['seq'])
   if key in literal_ids:continue
   if key not in pages:pages[key]=db.get_page(*key)
   page=pages[key];cache_key=(query,key)
   if cache_key not in support_cache:support_cache[cache_key]=supporting_span(query,db._indexable_text(page['text']) if INCLUDE_TOC.get() else body_text(db._indexable_text(page['text']),page['block_type']),keep)
   support=support_cache[cache_key]
   if not support:continue
   value,start,end,matched,relation=support
   if not relation and len(matched)<min(2,len(ap['anchors'])):continue
   score=.14+.74*value;q=candidate['question']
   if q and sum(bool(pattern(t).search(q)) for t in ap['anchors'])>=min(2,len(ap['anchors'])):
    start=candidate['start_char'];end=min(candidate['end_char'],start+180);score+=.08;matched=[t for t in ap['anchors'] if pattern(t).search(page['text'][start:end])];relation=False
   row=make_row(page,query,start,end,score,matched,relation)
   if q:row['matched_source_question']=q
   matched_ids.add(key)
   if key not in records or row['score']>records[key]['score']:records[key]=row
  query_ids.append(matched_ids)
 rows=list(records.values())
 if kwargs.get('operator')=='AND' and query_ids:rows=[r for r in rows if (r['book_id'],r['seq']) in set.intersection(*query_ids)]
 if kwargs.get('ranking') in ('book_order','chronological'):rows.sort(key=lambda r:(r['book_id'],r['seq']))
 elif kwargs.get('ranking')=='primary_first':rows.sort(key=db.primary_first_sort_key)
 else:rows.sort(key=lambda r:(-r['score'],r['source_tier'],r['book_id'],r['seq']))
 rows=deduplicate([r for r in rows if r['score']>=float(kwargs.get('min_score') or 0)])
 if kwargs.get('diversify_books',True) and len(kwargs.get('book_ids') or [])!=1:
  counts={};selected=[]
  for r in rows:
   b=r['book_id']
   if counts.get(b,0)<kwargs.get('max_per_book',2):selected.append(r);counts[b]=counts.get(b,0)+1
  rows=selected
 offset=kwargs.get('offset',0);rows=rows[offset:offset+kwargs.get('limit',8)]
 for i,r in enumerate(rows,offset+1):r['rank']=i
 return rows
