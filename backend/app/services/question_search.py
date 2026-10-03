"""Phrase-first union and bounded source-local ranking; never answer grading."""
from functools import lru_cache
import re,html,os,json,time,math,bisect
from app.core.observability import profiled,record_phase
from app.core.budget import DEADLINE, BudgetExceeded
from contextvars import ContextVar
SEARCH_STATE=ContextVar("question_search_state",default=None)
from app.services import library_db as db
from app.services.query_language import language_plan,morphological_forms
from app.services.question_intent import plan,concept_regex
from app.core.arabic_utils import normalize_search_text,safe_tokens,safe_term_variants
from app.core.budget import expired
from app.core.evidence_blocks import body_text,INCLUDE_TOC
from app.core.attribution import attribution_at
@lru_cache(maxsize=8192)
def pattern(term):
 inner='|'.join(db._build_highlight_regex(t,whole_word=False,normalization_level='broad').pattern for t in morphological_forms(term))
 return re.compile(r'(?<![ء-ي])(?:[وفبل])?(?:'+inner+r')(?:ات|ون|ين|ها|هم|ه|ي)?(?![ء-ي])')
@lru_cache(maxsize=4096)
def comparison_forms(term):
 """Distinct source tokens, including attached conjunctions, for comparisons."""
 bases=safe_term_variants(term)
 return tuple(dict.fromkeys((*bases,*(prefix+form for form in bases for prefix in ('و','ف','ب')),
                             *('ل'+form[1:] for form in bases if form.startswith('ال')))))
@lru_cache(maxsize=4096)
def comparison_pattern(term):
 return re.compile('|'.join('(?:'+db._build_exact_variant_regex(form).pattern+')' for form in comparison_forms(term)))
@lru_cache(maxsize=4)
def _topics(path,mtime,size):return [json.loads(r[0]) for r in db._connection().execute('SELECT terms FROM discovery_topics')]
def topic_proposals(anchors):
 path=db.get_settings().library_db_path;st=os.stat(path);forms={f for t in anchors for f in morphological_forms(t)};proposals=[]
 for terms in _topics(os.path.abspath(path),st.st_mtime_ns,st.st_size):
  if any(t in forms for t in terms):proposals.extend(t for t in terms if t not in forms)
 return list(dict.fromkeys(proposals))[:12]
@profiled("question_parsing")
def anchor_plan(query,keep_terms=()):
 result=language_plan(query,keep_terms);conn=db._connection();total=int(conn.execute("SELECT value FROM discovery_meta WHERE key='pages'").fetchone()[0]);common=[];anchors=[]
 # A comparison needs both named subjects, not the generic word "difference".
 terms=result['comparison_subjects'] or result['terms']
 for t in terms:
  # Corpus frequency estimates must refer to the query word. Loose morphology
  # turns بالهم into the ubiquitous pronoun هم and discards a crucial anchor.
  forms=tuple(normalize_search_text(f,level='broad') for f in safe_term_variants(t))
  row=conn.execute('SELECT MAX(documents) FROM term_document_frequency WHERE term IN ('+','.join('?'*len(forms))+')',forms).fetchone()
  if (row[0] or 0)>total*.15 and t not in keep_terms:common.append(t)
  else:anchors.append(t)
 # Preserve the rarest subject when a generic question has no recognized
 # relation. A page about a generic companion word is not evidence about it.
 frequencies={t:conn.execute('SELECT MAX(documents) FROM term_document_frequency WHERE term IN ('+','.join('?'*len(safe_term_variants(t)))+')',tuple(normalize_search_text(f,level='broad') for f in safe_term_variants(t))).fetchone()[0] or 0 for t in anchors}
 subject_anchors=anchors
 # In an action/object phrase the object is the protected subject: a page
 # mentioning "استعمال" alone is not evidence about استعمال الهاتف.
 if len(anchors)>1 and normalize_search_text(anchors[0],level='broad') in {'استعمال','استخدام','شرب','تناول','قراءه','قراءة','زياره','زيارة'}:
  subject_anchors=anchors[1:]
 result.update(anchors=anchors,common_nonanchors=common,protected_anchor=min(subject_anchors,key=lambda t:frequencies[t]) if subject_anchors else None,frequency_basis='precomputed_corpus_document_frequency');return result
def dialogue_at(text,start):
 from app.services.discovery_index import QUESTION,ANSWER
 text_start=max(0,text.rfind('\n\n',0,start))
 local=text[text_start:start+1]
 if not QUESTION.search(local) and not ANSWER.search(local):return {}
 marks=[(m.start(),'question') for m in QUESTION.finditer(text)]+[(m.start(),'answer') for m in ANSWER.finditer(text)];prior=[m for m in marks if m[0]<=start]
 if not prior:return {}
 role=max(prior)[1];return {'dialogue_role':role,'speaker':'السائل' if role=='question' else None,'speaker_basis':'explicit_question_marker' if role=='question' else 'answer_marker_author_not_inferred'}
def supporting_span(query,text,keep_terms=(),ap=None):
 ap=ap or anchor_plan(query,keep_terms)
 terms=ap['anchors'];comparison=ap['comparison_subjects'];p=plan(query);events=[]
 for t in terms:
  # The comparison subjects are distinct words: broad morphology can collapse
  # توكل and تواكل or accidentally score الفرق against فرج.
  matcher=comparison_pattern(t) if comparison else pattern(t)
  events.extend((m.start(),m.end(),'term:'+t,m.group()) for m in matcher.finditer(text))
 if not comparison:
  for group in p['groups']:events.extend((m.start(),m.end(),'concept:'+group,m.group()) for m in concept_regex(group).finditer(text))
 if not events:return None
 events.sort();starts=[event[0] for event in events];best=None
 for i,(start,end,tag,form) in enumerate(events):
  if expired():break
  boundary=text.find('\n\n',start,start+180);stop=boundary if boundary>=0 else start+180;local=[e for e in events[i:bisect.bisect_left(starts,stop,i)] if e[1]<=stop]
  if not local:continue
  matched={e[2][5:] for e in local if e[2].startswith('term:')};groups={e[2][8:] for e in local if e[2].startswith('concept:')};relation=bool(p['required']) and set(p['required'])<=groups;provision_remedy=False
  if comparison:
   relation=set(comparison)<=matched
   width=max(e[1] for e in local)-min(e[0] for e in local)
   value=(.70+.25*(1-min(width,180)/180)) if relation else .22
   candidate=(value,start,max(e[1] for e in local),sorted(matched),relation)
   if best is None or value>best[0]:best=candidate
   continue
  # Co-occurrence of generic words alone does not establish the requested
  # relation (e.g. a passing mention of a phone and prayer is not a ruling).
  if p['required']==['provision']:
   window=text[max(0,start-15):start+180];provision_remedy=any(db._build_highlight_regex(t,whole_word=False).search(window) for t in ('تيسير الرزق','جلب الرزق','سعة الرزق','شكا الفقر','عنه الفقر'));relation='provision' in groups and (bool(groups.intersection({'relief','distress'})) or provision_remedy)
  for t in terms:
   if any(concept_regex(g).search(t) for g in groups):matched.add(t)
  if relation and p['required']:
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
@profiled("excerpt_selection")
def make_row(page,query,start,end,score,matched,relation):
 text=page['text'];row={k:v for k,v in page.items() if k not in ('text','has_next','has_prev','content_types','evidence_blocks')};snippet=db._evidence_excerpt(text,start,end,180,[])
 query_plan=language_plan(query)
 row.update(score=round(max(0,min(.99,score)),6),match_type='reformulated',score_kind='local_span_discovery',match_id=f"{page['book_id']}-p{page['seq']}-c{start}",snippet=snippet,evidence_span={'start':start,'end':end,'excerpt':snippet},original_queries=[query],reformulation_method='phrase_and_passage_union_v1',reformulation_warning='Candidate discovery only; inspect the Arabic passage before using it as an answer.',answer_verified=False,question_relevance='relation_candidate' if relation else 'topic_only',intent_term_coverage=round(len(matched)/max(1,len(query_plan['comparison_subjects'] or query_plan['terms'])),4),evidence_type=db.evidence_type(text,start,start+1),evidence_type_method='structural_heuristic',evidence_type_confidence='unverified',evidence_type_scope='start_anchor');row.update(dialogue_at(text,start))
 row['_matched_anchors']=matched
 if query_plan['comparison_subjects'] and not relation:row['comparison_side']=matched
 return row
def deduplicate(rows):
 kept=[];sets=[]
 for row in rows:
  words=safe_tokens(normalize_search_text(re.sub('<[^>]+>','',html.unescape(row['snippet'])),level='broad'));grams=set(zip(words,words[1:],words[2:]));duplicate=None
  if len(words)>=15:
   for i,other in enumerate(sets):
    if grams and (len(grams&other)/len(grams|other)>=.62 or len(grams&other)/max(1,min(len(grams),len(other)))>=.75):duplicate=i;break
  if duplicate is not None:kept[duplicate].setdefault('also_in',[]).append({k:row.get(k) for k in ('book_id','seq','match_id','citation_label','source_tier','provenance_status','source_role','reported_view','attribution_warning')})
  else:kept.append(row);sets.append(grams)
 return kept


def _fts(forms):
    return '(' + ' OR '.join('"'+normalize_search_text(f,level='broad').replace('"','""')+'"' for f in dict.fromkeys(forms) if len(f)>2) + ')'


@profiled('candidate_union')
def passage_candidates(query, ap, scope):
    """Bounded BM25 union of source windows; never rescan the whole corpus."""
    from app.services.question_intent import CONCEPTS
    filters, params = db._search_filters(**scope)
    # Livelihood and distress vocabulary expand to particularly broad unions.
    # Bound their scoring work more tightly; other subjects need the wider
    # pool for attribution-sensitive passages such as b07 p256.
    broad_intent = plan(query)['required'] in (['provision'], ['distress', 'relief'])
    per_expression = 20 if broad_intent else 60
    candidate_limit = 40 if broad_intent else 120
    sql = '''SELECT d.*,p.book_id,p.seq,bm25(discovery_fts,1,3) AS relevance
             FROM discovery_fts JOIN discovery_passages d ON d.id=discovery_fts.rowid
             JOIN pages p ON p.id=d.page_id JOIN books b ON b.book_id=p.book_id
             WHERE discovery_fts MATCH ?''' + filters + f' ORDER BY relevance LIMIT {per_expression}'
    groups = [] if ap['comparison_subjects'] else plan(query)['required']
    expressions=[]
    if groups:
        expressions.append(' AND '.join(_fts(CONCEPTS[g]) for g in groups))
        if len(groups)==1:
            expressions.insert(0, _fts(CONCEPTS[groups[0]])+' AND '+_fts(CONCEPTS['relief']+CONCEPTS['distress']))
    # A conjunction of content anchors is selective; OR is a bounded fallback.
    anchors=ap['anchors'][:8]
    if anchors:
        forms=comparison_forms if ap['comparison_subjects'] else morphological_forms
        expressions.append(' AND '.join(_fts(forms(t)) for t in anchors))
        # Preserve each subject independently before the broad OR pool;
        # this also allows an explicitly weak one-sided comparison result.
        expressions.extend(_fts(forms(t)) for t in anchors[:3])
        if not ap['comparison_subjects']:
            expressions.append(_fts([f for t in anchors for f in forms(t)]))
    output={}
    for expression in expressions:
        if expired() or len(output)>=candidate_limit:break
        for row in db._connection().execute(sql,[expression,*params]).fetchall():
            output.setdefault(row['id'],dict(row))
    return list(output.values())[:candidate_limit]


@profiled('relation_check')
def classify_row(row, query, ap, text, start, end, relation=False):
    """Labels describe observable evidence, never automated answer truth."""
    window=text[max(0,start-120):min(len(text),max(end,start+200)+160)]
    subject=db._build_exact_variant_regex(ap['subject_phrase'],normalization_level='broad')
    phrase=bool(subject.search(window))
    directive=bool(re.search(r'عليك|ينبغي|يجب|حافظ|لا تغضب|نعم|أربع خصال|أربعة|معنى|عبارة عن|هو |هي ',window))
    row['question_relevance']='relation_candidate' if relation or (phrase and directive) or row.get('matched_source_question') else 'phrase_candidate' if phrase else 'topic_only'
    # A discussion *about* the literature on etiquette is not itself advice
    # about how to behave. Require an actionable conduct term in the local span.
    if plan(query)['required']==['etiquette','guide'] and not re.search(
        r'التزام|يلتزم|خدمة|يحفظ|حفظ|ملازمة|يستأذن|الاستئذان|يجب\s+على\s+المريد|يراعي|تأدب\s+له',window
    ):
        row['question_relevance']='topic_only'
        row['score']=round(max(0,row['score']-.22),6)
    if re.search(r'نظم حضرات|النهوض بالتصوف|إرساء دعائم',window):row['question_relevance']='topic_only'
    row['answer_verified']=False
    row['subject_phrase_match']=phrase
    row.update(db.citation_metadata(row['book_id'],row['seq'],row.get('printed_page')))
    row.update(attribution_at(text,start,end))
    if 'الأورام' in window and re.search(r'قراءة|لقراءة',window):
        row['text_errata']=[{'surface':'الأورام','proposed_reading':'الأوراد','status':'unverified_editorial_proposal','source_text_preserved':True}]
    return row


@profiled('question_pipeline')
def search_questions(**kwargs):
    queries=kwargs.get('queries') or [kwargs.get('query')]
    keep=tuple(kwargs.get('keep_terms') or ())
    scope={k:kwargs.get(k) for k in ('book_ids','source_code','page_from','page_to','qasida_number','min_tier')}
    state={'completion':'full','stages_completed':[],'stages_skipped':[],
           'candidate_counts':{},'path':'full','phrase_search_counts':{}}
    SEARCH_STATE.set(state)
    records={};pages={};query_ids=[];plans={}
    overall=DEADLINE.get() or time.monotonic()+10
    for query in queries:
        ap=anchor_plan(query,keep);plans[query]=ap;matched_ids=set()
        # Reserve time for serialisation after each independently bounded stage.
        stage_end=min(overall-.08,time.monotonic()+1.5)
        token=DEADLINE.set(stage_end)
        try:
            literal=db.search(query=ap['subject_phrase'],search_mode='exact_phrase',limit=80,
                              diversify_books=False,ranking=kwargs.get('ranking','primary_first'),context_chars=kwargs.get('context_chars',180),**scope)
        except (BudgetExceeded, __import__('sqlite3').OperationalError):
            if not expired():raise
            literal=[];state['completion']='partial';state['stages_skipped'].append('phrase_candidates')
        finally:DEADLINE.reset(token)
        state['phrase_search_counts'][query]=len(literal)
        for row in literal:
            key=(row['book_id'],row['seq']);matched_ids.add(key)
            page=pages.setdefault(key,db.get_page(*key));span=row['evidence_span']
            row['score']=round(.70+.28*row['score'],6)
            classify_row(row,query,ap,page['text'],span['start'],span['end'])
            records[key]=row
        state['candidate_counts']['phrase_candidates']=len(records)
        state['stages_completed'].append('phrase_candidates')
        if len(ap['terms'])<=3 and len(literal)>=3:
            state['path']='fast';query_ids.append(matched_ids);continue
        # Do not discard phrase matches, even if the later passage stage stops.
        token=DEADLINE.set(min(overall-.08,time.monotonic()+4.5))
        try:
            candidates=passage_candidates(query,ap,scope)
            state['candidate_counts']['passage_union']=len(candidates)
            state['stages_completed'].append('candidate_union')
            scored=time.perf_counter()
            for candidate in candidates:
                if expired():
                    state['completion']='partial';state['stages_skipped'].append('remaining_window_scoring');break
                key=(candidate['book_id'],candidate['seq'])
                if key not in pages:pages[key]=db.get_page(*key)
                page=pages[key];left=candidate['start_char'];right=min(candidate['end_char'],left+1200)
                window=db._indexable_text(page['text'])[left:right]
                # Filter fixed-expression homographs, never rewrite the source.
                if re.search(r'العجب كل العجب|كتب على نفسه البقاء وعلى الدنيا الفناء',window):continue
                support=supporting_span(query,window,keep,ap)
                if not support:continue
                value,start,end,matched,relation=support
                if not relation and not ap['comparison_subjects'] and len(matched)<min(2,len(ap['anchors'])):continue
                start+=left;end+=left
                score=.10+.70*value
                q=candidate['question']
                qa_match=bool(q) and sum(bool((comparison_pattern(t) if ap['comparison_subjects'] else pattern(t)).search(q)) for t in ap['anchors'])>=min(2,len(ap['anchors']))
                if qa_match:score+=.18
                if relation and plan(query)['required']==['litanies','work','provision'] and re.search(r'سؤال\s*[:：]|الجواب\s*[:：]|السائل\s*[:：]',window):score+=.16
                # A biography describes someone's life, rather than addressing
                # the user's practical question, even when all concepts occur.
                if re.search(r'نظم حضرات|النهوض بالتصوف|إرساء دعائم|إرساؤه لدعائم',window):score-=.18
                if plan(query)['required']==['distress','relief']:
                    literal_distress=bool(concept_regex('distress').search(window))
                    if literal_distress:score+=.15
                    # Practical advice can use a different distress synonym
                    # from the user's wording; keep that local relation.
                    normalized_window=normalize_search_text(window,level='broad')
                    if literal_distress and re.search(r'لا تياس|اجعلها شعارك|توكل عليه|اترك له|تذكرها|اصبر|استغفر',normalized_window):score+=.14
                    if re.search(r'فقتله|سيف الزبير|رثته|بغض آل',window):score-=.2
                # Keep phrases in top results when the question has a clear subject.
                if db._build_exact_variant_regex(ap['subject_phrase'],normalization_level='broad').search(window):score+=.20
                score+=.025/(1+abs(float(candidate['relevance'])))
                row=make_row(page,query,start,end,min(.985,score),matched,relation)
                if qa_match:row['matched_source_question']=q
                classify_row(row,query,ap,page['text'],start,end,relation)
                matched_ids.add(key)
                if key not in records or row['score']>records[key]['score']:records[key]=row
            record_phase('window_scoring',scored)
            if state['completion']=='full':state['stages_completed'].append('window_scoring')
        except (BudgetExceeded,__import__('sqlite3').OperationalError):
            if not expired():raise
            state['completion']='partial';state['stages_skipped'].append('passage_union_or_scoring')
        finally:DEADLINE.reset(token)
        query_ids.append(matched_ids)
    rows=list(records.values())
    for row in rows:
        query=row['original_queries'][0] if row.get('original_queries') else queries[0]
        ap=plans[query]
        if not plan(query)['required'] and not ap['comparison_subjects'] and len(ap['anchors'])>=2:
            row['_missing_protected_subject']=ap['protected_anchor'] not in row.get('_matched_anchors',()) and not row.get('subject_phrase_match')
    rows=[row for row in rows if not row.get('_missing_protected_subject')]
    # Coverage is evidence based and scoped: retain explicit mentions only.
    if any(set(plan(q)['required'])=={'children','upbringing'} for q in queries):
        child_phrase=db._build_highlight_regex('تربية',whole_word=True).pattern+r'\s+(?:'+ '|'.join(db._build_highlight_regex(w,whole_word=False).pattern for w in ('الأطفال','الأولاد','الأبناء'))+')'
        rows=[r for r in rows if re.search(child_phrase,html.unescape(re.sub('<[^>]+>','',r['snippet'])))]
        for row in rows:row['question_relevance']='topic_only'
        state['coverage_gap']={'topic':'raising children','basis':'Only passing mentions established in supplied corpus audit'}

    if kwargs.get('operator')=='AND' and query_ids:rows=[r for r in rows if (r['book_id'],r['seq']) in set.intersection(*query_ids)]
    # Phrase protection is only applicable when a complete subject was found.
    protected=sum(r.get('subject_phrase_match',False) for r in rows)>=3
    if kwargs.get('ranking') in ('book_order','chronological'):rows.sort(key=lambda r:(r['book_id'],r['seq']))
    else:
        for row in rows:db._set_rank_score(row)
        rows.sort(key=lambda r:(-(bool(r.get('subject_phrase_match')) if protected else 0),-(r['rank_score'] if kwargs.get('ranking')=='primary_first' else r['score']),r['source_tier'],r['book_id'],r['seq']))
    t=time.perf_counter();rows=deduplicate([r for r in rows if r['score']>=float(kwargs.get('min_score') or 0)]);record_phase('deduplication',t)
    if not kwargs.get('include_topic_only',True) and not state.get('coverage_gap'):
        supported=[r for r in rows if r['question_relevance']!='topic_only' or r.get('also_in')]
        # A weak source mention is safer than an unexplained empty result when
        # the subject is present; never promote it to an answer candidate.
        if supported:rows=supported
    if kwargs.get('diversify_books',True) and len(kwargs.get('book_ids') or [])!=1:
        counts={};selected=[]
        for r in rows:
            b=r['book_id']
            if counts.get(b,0)<kwargs.get('max_per_book',2):selected.append(r);counts[b]=counts.get(b,0)+1
        rows=selected
    state['stages_completed']=list(dict.fromkeys(state['stages_completed']+['relation_check','deduplication']))
    state['evidence_strength']='weak' if state.get('coverage_gap') else 'candidate' if any(r['question_relevance']!='topic_only' for r in rows) else 'weak'
    state['path']='partial' if state['completion']=='partial' else state['path']
    offset=kwargs.get('offset',0);rows=rows[offset:offset+kwargs.get('limit',8)]
    for i,r in enumerate(rows,offset+1):
        r['rank']=i
        r.pop('_matched_anchors',None);r.pop('_missing_protected_subject',None)
    return rows
