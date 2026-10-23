"""Phrase-first union and bounded source-local ranking; never answer grading."""
from functools import lru_cache
import re,html,os,json,time,math,bisect
from app.core.observability import profiled,record_phase
from app.core.budget import DEADLINE, BudgetExceeded
from contextvars import ContextVar
@lru_cache(maxsize=1)
def ranker_config():
 from pathlib import Path
 return json.loads(Path(__file__).with_name('ranker_weights.json').read_text())

SEARCH_STATE=ContextVar("question_search_state",default=None)
from app.services import library_db as db
from app.services.query_language import language_plan,morphological_forms,phrase_pages,synonym_variants
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
 bases=tuple(dict.fromkeys((*safe_term_variants(term),*synonym_variants(term))))
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
 protected_phrase=(len(safe_tokens(result['subject_phrase']))>=2
                   and phrase_pages(result['subject_phrase'])>=2)
 for t in terms:
  # Corpus frequency estimates must refer to the query word. Loose morphology
  # turns بالهم into the ubiquitous pronoun هم and discards a crucial anchor.
  forms=tuple(normalize_search_text(f,level='broad') for f in safe_term_variants(t))
  row=conn.execute('SELECT MAX(documents) FROM term_document_frequency WHERE term IN ('+','.join('?'*len(forms))+')',forms).fetchone()
  # A named entity can be common in a religious corpus and still be essential
  # to the requested subject (e.g. a dream of the Prophet).
  named_subject=normalize_search_text(t,level='broad') in {'النبي','الرسول','محمد'}
  if (row[0] or 0)>total*.15 and t not in keep_terms and not named_subject and not protected_phrase:common.append(t)
  else:anchors.append(t)
 # A generic role noun (المريد، للمريد، السالك...) names the asker, and
 # "ربه/ربك" names God generically. When the question has another content
 # word, requiring these as well discards passages about the subject (Q-1).
 from app.services.query_language import morphological_forms as _forms
 role_bases={'مريد','سالك','عبد','انسان','ناس','مؤمن','مسلم','رب','سلوك','طريق'}
 def _generic(t):
  word=normalize_search_text(t,level='broad')
  bases=set(_forms(t))|{word[:-len(x)] for x in ('ه','ها','هم','ك','كم','ي','نا') if word.endswith(x)}
  return bool(bases&role_bases)
 if not result['comparison_subjects']:
  roles=[t for t in anchors if _generic(t)]
  if roles and len(anchors)>len(roles) and not protected_phrase and (result.get('question_frame') or {}).get('intent')!='signs':
   anchors=[t for t in anchors if t not in roles];common.extend(roles)
 # Preserve the rarest subject when a generic question has no recognized
 # relation. A page about a generic companion word is not evidence about it.
 frequencies={t:conn.execute('SELECT MAX(documents) FROM term_document_frequency WHERE term IN ('+','.join('?'*len(safe_term_variants(t)))+')',tuple(normalize_search_text(f,level='broad') for f in safe_term_variants(t))).fetchone()[0] or 0 for t in anchors}
 subject_anchors=anchors
 # In an action/object phrase the object is the protected subject: a page
 # mentioning "استعمال" alone is not evidence about استعمال الهاتف.
 if len(anchors)>1 and normalize_search_text(anchors[0],level='broad') in {'استعمال','استخدام','شرب','تناول','قراءه','قراءة','زياره','زيارة'}:
  subject_anchors=anchors[1:]
 # The protected subject is a noun. A rare verb (يعالج، يستعد) names the
 # relation asked about; requiring it would discard the passages that
 # discuss the subject itself (الكبر، الموت) in other words.
 # Generic role nouns (المريد، السالك...) are the asker, not the subject,
 # and a possessed noun (منامه) is a noun even without the article.
 from app.services.query_language import canonical_subject
 nouns=[t for t in subject_anchors if (protected_phrase or not _generic(t)) and not any(f=='شيخ' for f in _forms(t)) and (
        normalize_search_text(t,level='broad').startswith(('ال','وال','بال','فال','لل')) or canonical_subject(t)!=t)]
 if nouns:subject_anchors=nouns
 from app.services.concept_links import query_groups
 result['protected_concepts']=query_groups(query) or list(terms)
 result['original_query']=query
 result.update(anchors=anchors,common_nonanchors=common,protected_anchor=min(subject_anchors,key=lambda t:frequencies[t]) if subject_anchors else None,frequency_basis='precomputed_corpus_document_frequency',attested_subject_phrase=protected_phrase);return result
@lru_cache(maxsize=4096)
def relation_verb(term):
 """An imperfect verb (يضر، يخاف، يتعامل) that names the asked relation.

 Its noun reading with the article is unattested; nouns such as تربية or
 الصلاة are never treated as optional.
 """
 from app.services.query_language import corpus_documents
 word=normalize_search_text(term,level='broad')
 return (len(word)>=3 and word[0] in 'يتن' and not word.startswith('ال')
         and corpus_documents('ال'+word)<2)


def dialogue_at(text,start):
 from app.services.discovery_index import QUESTION,ANSWER
 text_start=max(0,text.rfind('\n\n',0,start))
 local=text[text_start:start+1]
 if not QUESTION.search(local) and not ANSWER.search(local):return {}
 marks=[(m.start(),'question') for m in QUESTION.finditer(text)]+[(m.start(),'answer') for m in ANSWER.finditer(text)];prior=[m for m in marks if m[0]<=start]
 if not prior:return {}
 position,role=max(prior)
 # Many transcripts give the reply straight after the question mark, with no
 # الجواب marker ("سؤال: ...؟ لا لا لا ..."), or introduce it with a phrase
 # such as "فقال رضي الله عنه". Evidence after the question's own question
 # mark belongs to the reply, never to the questioner (MD-2).
 if role=='question' and re.search(r'[؟?]',text[position:start]):
  return {'dialogue_role':'answer','speaker':None,'speaker_basis':'implicit_answer_after_question_mark'}
 return {'dialogue_role':role,'speaker':'السائل' if role=='question' else None,'speaker_basis':'explicit_question_marker' if role=='question' else 'answer_marker_author_not_inferred'}
# The honorific "عليه أفضل الصلاة والسلام" is a blessing formula, not a
# statement about virtue (فضل) or prayer. It is blanked, offsets preserved,
# for scoring only; displayed text is never changed.
_HONORIFIC=re.compile(r'(?:أفضل|افضل|أزكى|ازكى|أتم|اتم)\s+(?:ال)?(?:صلاة|صلاه|صلوات)\s*(?:و\s*(?:أتم|اتم|أزكى)\s+)?(?:و\s*)?(?:ال)?(?:سلام|تسليم|تحية)?')
_PROCEDURAL_QUESTION=re.compile(r'^(?:كيف|ما\s+الذي\s+يجب|ماذا\s+(?:يفعل|أفعل)|بماذا|إزاي|ازاي|إيه\s+أعمل)\b')
_PROCEDURAL_EVIDENCE=re.compile(
 r'(?<![ء-ي])(?:شروط|خطوات|مراحل)(?![ء-ي])[^.!؟\n]{0,65}'
 r'(?<![ء-ي])(?:ثلاث|أربع|خمسة|أولاً|أولا|ثانياً|ثانيا)(?![ء-ي])'
)
def mask_honorifics(text):
 return _HONORIFIC.sub(lambda m:' '*len(m.group()),text)


def sense_conflict(query, text, start, end):
    """Reject an attested wrong reading of a polysemous noun locally.

    An explicit vowel sequence is stronger evidence than a stripped index
    token. Unvocalised nominal uses need local topic context; a bare verb
    describing physical growth cannot stand in for the noun الكِبْر.
    """
    normalized_query=normalize_search_text(query,level='broad')
    if not re.search(r'(?<![ء-ي])(?:ال|بال|من\s+ال)كبر(?![ء-ي])',normalized_query):
        return False
    local=text[max(0,start-90):min(len(text),end+130)]
    matched=text[start:end]
    if re.search(r'كُبَر|كِبَر|كَبُر|كْبَر',matched):
        return True
    if not re.search(r'(?<![ء-ي])(?:ال|وال|بال|لل)\s*[ًٌٍَُِّْ]*ك[ًٌٍَُِّْ]*ب[ًٌٍَُِّْ]*ر',matched) and not re.search(r'(?<![ء-ي])(?:ال|وال|بال|لل)كبر',normalize_search_text(matched,level='broad')):
        return True
    pride=re.search(r'تواضع|ع[ُ]?جب|رياء|غرور|تكبر|متكبر|نفاق|نفساني|الأخلاق|القلب|القلوب|التواضع',local)
    physical=re.search(r'جسم|حجم|سن[ّه]?|حمل|زاد|يكبر|كبر\s+(?:جسم|الحمل|الولد)',local)
    return bool(physical and not pride)


def procedural_support(query, window, start, end, matched, ap, relation):
 """Favor an actionable span over a passing mention in a how-to question.

 The enumerated cue must occur beside the matched evidence, and the protected
 subject must also be present. A passing mention of "conditions" alone does
 not count. This is a ranking signal, never an answer label.
 """
 if not relation or not _PROCEDURAL_QUESTION.match(query.strip()):return 0.0
 if not ap.get('protected_anchor') or ap['protected_anchor'] not in matched:return 0.0
 local=window[max(0,start-80):min(len(window),end+100)]
 return .16 if _PROCEDURAL_EVIDENCE.search(local) else 0.0


def explicit_observance(text, start, end):
    """Evidence of a practice for the named night in the same local passage.

    This is a candidate cue, not verification of a full religious answer.
    Incidental prayer and merit elsewhere on a page cannot satisfy it.
    """
    left=max(0,text.rfind('\n\n',0,start)+2,start-160)
    boundary=text.find('\n\n',end)
    right=min(len(text),end+220,boundary if boundary>=0 else len(text))
    local=text[left:right]
    night=re.search(r'ليلة\s+القدر',local)
    action=re.search(r'قيام|قام\s+ليلة|صلاة|الصلاة|دعاء|الذكر|قراءة\s+القرآن|عبادة',local)
    guidance=re.search(r'أحيوا|إحياء|يستحب|ينبغي|عليكم|من\s+قام\s+ليلة\s+القدر',local)
    return bool(night and action and guidance and abs(night.start()-action.start())<150)


def supporting_span(query,text,keep_terms=(),ap=None,features=None):
 ap=ap or anchor_plan(query,keep_terms)
 text=mask_honorifics(text)
 terms=ap['anchors'];comparison=ap['comparison_subjects'];p=plan(query);events=[];weights=ranker_config()['weights']
 for t in terms:
  # The comparison subjects are distinct words: broad morphology can collapse
  # توكل and تواكل or accidentally score الفرق against فرج.
  matcher=comparison_pattern(t) if comparison else pattern(t)
  if features and 'lexical_spans' in features and len(safe_tokens(t))==1:
   for surface,spans in features['lexical_spans'].items():
    if matcher.fullmatch(surface):
     events.extend((a,b,'term:'+t,surface) for a,b in spans if b<=len(text))
  else:
   events.extend((m.start(),m.end(),'term:'+t,m.group()) for m in matcher.finditer(text))
 if not comparison:
  for group in p['groups']:
   if features and 'concept_spans' in features:
    events.extend((a,b,'concept:'+group,surface) for a,b,surface in features['concept_spans'].get(group,[]) if b<=len(text))
   else:events.extend((m.start(),m.end(),'concept:'+group,m.group()) for m in concept_regex(group).finditer(text))
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
   value=(weights['comparison_base']+weights['comparison_compactness']*(1-min(width,180)/180)) if relation else weights['comparison_unpaired']
   candidate=(value,start,max(e[1] for e in local),sorted(matched),relation)
   if best is None or value>best[0]:best=candidate
   continue
  # Co-occurrence of generic words alone does not establish the requested
  # relation (e.g. a passing mention of a phone and prayer is not a ruling).
  if p['required']==['provision']:
   window=text[max(0,start-15):start+180];provision_remedy=any(db._build_highlight_regex(t,whole_word=False).search(window) for t in ('تيسير الرزق','جلب الرزق','سعة الرزق','شكا الفقر','عنه الفقر'));relation='provision' in groups and (bool(groups.intersection({'relief','distress'})) or provision_remedy)
  for t in terms:
   if any(concept_regex(g).search(t) for g in groups):matched.add(t)
  if ap.get('focus_word') and set(terms)<=matched:
   # All subject words and the reward/focus expression are in one local span.
   # This is a candidate relation, never an answer verification.
   relation=True
  # A yes/no reply cue. نعم counts only as a reply ("…؟ نعم،"), not as the
  # verb of praise in "نعم الشافعة".
  if query.startswith('هل ') and set(terms)<=matched and re.search(
      r'\b(?:يجوز|جائز|جايز|وارد|لا بأس)\b|(?:^|[:؟?\n])\s*نعم\b',text[max(0,start-35):min(len(text),stop+100)]):
   relation=True
  if relation and p['required']:
   required_events=[e for e in local if e[2] in {'concept:'+g for g in p['required']}];width=max(e[1] for e in required_events)-min(e[0] for e in required_events)
  else:width=180
  coverage=len(matched)/max(1,len(terms));required=len(groups.intersection(p['required']))/max(1,len(p['required']));value=weights['slot_coverage']*coverage+weights['required_concept_coverage']*required+weights['co_location']*relation+(weights['compactness']*(1-width/180) if relation else 0)
  if provision_remedy and relation:value+=.32
  if 'quran' in p['required']:
   window=text[max(0,start-50):stop+50];reading=bool(re.search(r'تلاوة|قراءة|يقرأ|تقرأ|بتقرأ|قراء|ورد',window))
   if not reading:value-=.28;relation=False
   elif re.search(r'كل يوم|ورد يومي|كتر منه|المداومة|يداوم|يواظب',window):value+=.20
  window=text[start:min(len(text),start+250)]
  if 'prayer' in p['required'] and re.search(r'الصلاة\s+(?:والسلام|على\s+النبي)',window) and 'timing' not in groups:value-=.25
  if re.search(r'قال الراوي|حكى|يحكى|حكاية',text[max(0,start-60):start]):value-=.06
  if re.search(r'ينبغي|عليك|يجب|المحافظة|الاجتهاد|احفظ|حفظ|لا تغضب',window):value+=weights['answer_shape']
  candidate=(value,start,max(e[1] for e in local),sorted(matched),relation)
  if best is None or value>best[0]:best=candidate
 return best
@profiled("excerpt_selection")
def make_row(page,query,start,end,score,matched,relation,context_chars=180,query_plan=None):
 text=page['text'];row={k:v for k,v in page.items() if k not in ('text','has_next','has_prev','content_types','evidence_blocks')};snippet=db._evidence_excerpt(text,start,end,context_chars,[])
 query_plan=query_plan if query_plan is not None else language_plan(query)
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

def _clitic_forms(forms):
    # Match the same conservative attached prefixes accepted by local source
    # validation. FTS stores والاخلاص as one token, not الاخلاص.
    return tuple(dict.fromkeys(x for form in forms for x in (form,'و'+form,'ف'+form,'ب'+form,'ل'+form)))


@profiled('candidate_union')
def passage_candidates(query, ap, scope):
    """Fair route-family fusion; every route runs before the final cap.

    Multiple aliases in one family receive one vote. Exact routes and narrow
    conjunctions cannot be starved by an earlier broad concept route.
    """
    from app.services.question_intent import CONCEPTS
    from app.services.concept_links import query_groups, normalized_forms
    filters, params = db._search_filters(**scope)
    sql = """SELECT d.*,p.book_id,p.seq,bm25(discovery_fts,1,3) AS relevance
             FROM discovery_fts JOIN discovery_passages d ON d.id=discovery_fts.rowid
             JOIN pages p ON p.id=d.page_id JOIN books b ON b.book_id=p.book_id
             WHERE discovery_fts MATCH ?""" + filters + ' ORDER BY relevance,d.id LIMIT 61'
    routes={}
    def add(family,expression):
        if expression and expression!='()':routes.setdefault(family,[]).append(expression)
    anchors=ap['anchors'][:8]
    forms=comparison_forms if ap['comparison_subjects'] else morphological_forms
    add('original_phrase',_fts([ap['subject_phrase']]))
    if anchors:
        add('content_conjunction',' AND '.join(_fts(forms(t)) for t in anchors))
        add('content_terms',_fts([f for t in anchors for f in forms(t)]))
        for term in dict.fromkeys([ap.get('protected_anchor'),*anchors[:3]]):
            if term:add('subject_terms',_fts(forms(term)))
    groups=[] if ap['comparison_subjects'] else plan(query)['required']
    if groups:
        add('intent_concepts',' AND '.join(_fts(CONCEPTS[g]) for g in groups))
        if len(groups)==1:add('intent_concepts',_fts(CONCEPTS[groups[0]])+' AND '+_fts(CONCEPTS['relief']+CONCEPTS['distress']))
    linked=query_groups(query)
    if linked:
        add('typed_concepts',' AND '.join(_fts(_clitic_forms(normalized_forms(g))) for g in linked))
        if len(linked)>1:
            # Related concept groups can share aliases (e.g. riya appears in
            # both sincerity and praise-desire discovery). Reserve a route
            # whose subjects have distinct lexical evidence, rather than
            # allowing one shared word to fill every slot.
            group_forms={g:set(normalized_forms(g)) for g in linked}
            exclusive={g:forms-set().union(*(v for h,v in group_forms.items() if h!=g))
                       for g,forms in group_forms.items()}
            if all(exclusive.values()) and any(exclusive[g]!=group_forms[g] for g in linked):
                add('distinct_subjects',' AND '.join(_fts(_clitic_forms(sorted(exclusive[g]))) for g in linked))
        # Preserve the requested relation in a separate bounded family so a
        # common subject cannot fill every slot before reward/condition cues.
        intent=(ap.get('question_frame') or {}).get('intent')
        from app.services.evidence_units import CUE_FORMS
        if intent in CUE_FORMS:
            add('subject_relation',' AND '.join([*(_fts(_clitic_forms(normalized_forms(g))) for g in linked),_fts(CUE_FORMS[intent])]))
            surface_cues=[f for f in CUE_FORMS[intent] if pattern(f).search(query)]
            if surface_cues:
                add('predicate_surface',' AND '.join([*(_fts(_clitic_forms(normalized_forms(g))) for g in linked),_fts(surface_cues)]))
    if len(anchors)>=2 and not ap['comparison_subjects']:
        for left in (*synonym_variants(anchors[0]),anchors[0])[:4]:
            for right in (*synonym_variants(anchors[1]),anchors[1])[:4]:
                if phrase_pages(left+' '+right):add('attested_phrase',_fts([left+' '+right,'و'+left+' '+right]))
    output={};family_ranks={};counts={};caps={}
    # No early stop at 120: finish every bounded route, then fuse once.
    for family,expressions in routes.items():
        family_rows={};capped=False
        for expression in dict.fromkeys(expressions):
            if expired():break
            found=db._connection().execute(sql,[expression,*params]).fetchall()
            capped=capped or len(found)>60
            for rank,row in enumerate(found[:60],1):
                d=dict(row);d['_family_rank']=rank;old=family_rows.get(d['id'])
                if old is None or rank<old['_family_rank']:family_rows[d['id']]=d
        ordered=sorted(family_rows.values(),key=lambda x:(x['_family_rank'],x['id']))[:60]
        counts[family]=len(ordered);caps[family]=capped or len(family_rows)>60
        for rank,d in enumerate(ordered,1):
            output.setdefault(d['id'],d);family_ranks.setdefault(d['id'],{})[family]=rank
    for uid,d in output.items():
        d['route_ranks']=family_ranks[uid]
        d['fusion_score']=sum(1/(60+rank) for rank in family_ranks[uid].values())
    ordered=sorted(output.values(),key=lambda d:(-d['fusion_score'],d['relevance'],d['id']))
    # Reserve a small floor per family before filling by RRF. Otherwise an
    # exclusive relation route can lose all its candidates to multi-route
    # generic mentions despite being run successfully.
    priorities=('original_phrase','predicate_surface','distinct_subjects','content_conjunction',
                'subject_relation','intent_concepts','typed_concepts','attested_phrase',
                'subject_terms','content_terms')
    families=list(dict.fromkeys((*priorities,*routes)))
    family_lists={family:sorted((d for d in output.values() if family in d['route_ranks']),
                               key=lambda d:(d['route_ranks'][family],d['id']))[:8]
                  for family in families}
    reserved=[];seen=set()
    # Interleave the route floors instead of sorting all reserved units by
    # their broad-route votes. Specific predicate routes now get an early
    # validated checkpoint even when a later stage reaches its budget.
    for position in range(8):
        for family in families:
            choices=family_lists[family]
            if position<len(choices) and choices[position]['id'] not in seen:
                d=choices[position];seen.add(d['id']);reserved.append(d)
    ordered=reserved+[d for d in ordered if d['id'] not in seen]
    # Precomputed source-unit features; no per-request corpus scan.
    ids=[d['id'] for d in ordered[:160]]
    if ids:
        placeholders=','.join('?' for _ in ids)
        for row in db._connection().execute('SELECT id,unit_id,features FROM evidence_units WHERE id IN ('+placeholders+')',ids):
            output[row['id']]['unit_id']=row['unit_id'];output[row['id']]['features']=json.loads(row['features'])
    state=SEARCH_STATE.get()
    if state is not None:
        state.setdefault('candidate_manifest',[]).append({'query':query,'units':[{'id':d['id'],'book_id':d['book_id'],'seq':d['seq'],'start':d['start_char'],'end':d['end_char'],'routes':d['route_ranks']} for d in ordered[:160]]})
        state.setdefault('route_funnels',[]).append({'query':query,'routes':counts,'route_cap_reached':caps,'union_units':len(output),'final_cap':160,'cap_reached':len(output)>160,'selected_units':len(ids)})
    return ordered[:160]


@profiled('relation_check')
def classify_row(row, query, ap, text, start, end, relation=False):
    """Labels describe observable evidence, never automated answer truth."""
    text=mask_honorifics(text)
    window=text[max(0,start-120):min(len(text),max(end,start+200)+160)]
    subject=db._build_exact_variant_regex(ap['subject_phrase'],normalization_level='broad')
    phrase=bool(subject.search(window))
    # Guidance or definition cues only. Bare "هو"/"هي" occur in nearly every
    # passage and "نعم" is also the verb of praise; as cues they marked
    # incidental mentions (a duʿāʾ "ولا رياء") as likely answers (LB-1).
    directive=bool(re.search(r'عليك|ينبغي|يجب|حافظ|لا تغضب|أربع خصال|أربعة|معنى|عبارة عن|يعني|علامة|إنما\s+الاستعداد|\b(?:هو|هي)\s+أن\b|المراد\s+ب|(?:^|[:؟?\n])\s*نعم\b',window))
    row['question_relevance']='relation_candidate' if relation or (phrase and directive) or row.get('matched_source_question') else 'phrase_candidate' if phrase else 'topic_only'
    frame=ap.get('question_frame') or {}
    if frame.get('intent')=='signs' and phrase:
        # A singular or plural sign cue attached to the subject is stronger
        # than the subject appearing incidentally elsewhere on a page.
        if (re.search(r'(?:علامة|علامات|من\s+علامات|دليل)\s+'+subject.pattern,window)
                or re.search(r'(?:وضع|جعل)[^.!؟\n]{0,65}(?:شروط|الشرط)|شروط(?:ا|اً)?[^.!؟\n]{0,80}إذا',window)):
            row['score']=round(min(.985,row['score']+.20),6)
            row['question_relevance']='relation_candidate'
    if (frame.get('presupposition') or re.search(r'بديل|بديلا',query)) and (phrase or any(pattern(t).search(window) for t in ap['anchors'])) and re.search(r'مافيش|لا\s+توجد|أغنت\s+عن|لغى|ألغى|بدل(?:ا)?\s+من',window):
        row['corrects_premise']=True
        row['question_relevance']='relation_candidate'
    # Co-occurrence inside a story or prayer formula does not answer a
    # practice question. These guards describe the local evidence only.
    local=text[max(0,start-85):min(len(text),end+125)]
    if (re.search(r'\b(?:إنما|علامة|معنى)\s+الاستعداد\s+للموت',local)
            and re.search(r'(?:للموت|الموت)',query) and re.search(r'يستعد|استعداد',query)):
        row['question_relevance']='relation_candidate'
    if ('companionship' in plan(query)['required'] and
            re.search(r'بينه\s+وبين(?:ه|\s+الشيخ)\s+صحبة|كان\s+بينه\s+وبين',local)):
        row['question_relevance']='topic_only'
    if ('anger' in plan(query)['required'] and 'علاج' in query and not re.search(
            r'علاج|دواء|كظم|تجنب|اترك|ترك\s+الخصومة|اصمت|الاستعاذة|إذا\s+غضبت|لا\s+تغضب',local)):
        row['question_relevance']='topic_only'
    if re.search(r'لم\s+أخرج\s+(?:أشرا|بطرا)[^.!؟]{0,55}رياء',local):
        row['question_relevance']='topic_only'
    if re.search(r'في\s+وسواس\s+وفي\s+ملطية|في\s+دمشق\s+وفي\s+وسواس',local):
        row['question_relevance']='topic_only'
    if ap.get('focus_word') and _HONORIFIC.search(row.get('snippet','')) and not re.search(
            r'أفضل\s+من|ثواب|أجر|عشرا|مائة\s+حاجة',row['snippet']):
        row['question_relevance']='topic_only'
    facets=ap.get('requested_facets',())
    if 'observance' in facets:
        row['observance_support']=explicit_observance(text,start,end)
        if not row['observance_support'] and 'merit' not in facets:
            row['question_relevance']='topic_only'
    if 'preference' in facets:
        # Two sides in a heading or a balanced description do not answer
        # which side, if either, the author says to prefer.
        subjects=ap['comparison_subjects']
        direction=False
        if len(subjects)==2:
            first,second=(comparison_pattern(t).pattern for t in subjects)
            direction=bool(re.search('(?:'+first+r')[^.!؟\n]{0,80}(?:أفضل\s+من|أعلى\s+من|أولى\s+من)[^.!؟\n]{0,50}(?:'+second+')',window))
        if not direction:row['question_relevance']='topic_only'
    focus=ap.get('focus_word')
    row['focus_match_strength']=0
    subject_words=len(safe_tokens(ap['subject_phrase']))
    # Subjects of three or more words (الصلاة على النبي) keep the original
    # rule and 300-character proximity; two-word subjects are unchanged
    # (no focus ranking). A single-word subject (فضل الاستغفار) is now
    # eligible too, with its focus word within 120 characters, because a
    # single common word gives far more chance co-occurrences.
    reach=300 if subject_words>=3 else 120
    if focus and subject_words!=2 and all(pattern(t).search(window) for t in ap['anchors'] if t!=focus):
        focus_forms=set(safe_term_variants(focus))
        literal_focus=re.compile('|'.join(db._build_highlight_regex(form,whole_word=True,normalization_level='broad').pattern
                                          for form in focus_forms))
        # The passage index may start at the subject while the direct reward
        # wording lies in the following sentence on the same source page.
        direct=any(subject.search(text[max(0,m.start()-reach):min(len(text),m.end()+reach)])
                   for m in literal_focus.finditer(text))
        comparison_reward=focus=='فضل' and any(re.search(r'أفضل\s+من',text[m.end():m.end()+100])
                                                 for m in subject.finditer(text))
        if direct or comparison_reward:
            row['focus_match_strength']=2
            if comparison_reward:row['score']=round(min(.985,row['score']+.08),6)
        elif pattern(focus).search(window):
            row['focus_match_strength']=1
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
    synonym_hits=[]
    for term in ap['comparison_subjects'] or ap['terms']:
        if not synonym_variants(term):continue
        direct=db._build_highlight_regex(term,whole_word=True,normalization_level='broad')
        if direct.search(text[start:end]):continue
        for form in synonym_variants(term):
            if db._build_highlight_regex(form,whole_word=True,normalization_level='broad').search(text[start:end]):
                synonym_hits.append({'query_term':term,'matched_form':form,'scope':'discovery_only'})
                break
    if synonym_hits:row['synonym_variant']=synonym_hits
    row.update(db.citation_metadata(row['book_id'],row['seq'],row.get('printed_page')))
    row.update(attribution_at(text,start,end))
    from app.core.attribution import speaker_span
    speaker_evidence=speaker_span(text,start,end)
    if not (row.get('dialogue_role')=='answer' and speaker_evidence.get('dialogue_role')=='question'):
        row.update(speaker_evidence)
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
    from app.core.search_trace import checkpoint, checkpoint_row, stage
    records={};pages={};indexed_pages={};query_ids=[];plans={}
    overall=min(DEADLINE.get() or time.monotonic()+5,time.monotonic()+5)
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
            page=pages.get(key)
            if page is None:page=pages.setdefault(key,db.get_page(*key))
            span=row['evidence_span']
            if sense_conflict(query,page['text'],span['start'],span['end']):continue
            row['score']=round(.70+.28*row['score'],6)
            row['score']=round(min(.985,row['score']+procedural_support(
                query,page['text'],span['start'],span['end'],
                [ap['protected_anchor']],ap,True)),6)
            classify_row(row,query,ap,page['text'],span['start'],span['end'])
            from app.services.hit_contract import canonical_hit
            canonical_hit(row,page)
            records[key]=row
        checkpoint(list(records.values()),'phrase_candidates')
        state['candidate_counts']['phrase_candidates']=len(records)
        state['stages_completed'].append('phrase_candidates')
        # A literal phrase answers a definition or a named multi-word subject.
        # A single word under a "how/why/when" frame (كيف يتخلص من الرياء)
        # asks about a remedy or a relation, so its passages must be scored.
        definitional=bool(re.match(r'^(?:ما|وما)\s+(?:معنى|هو|هي|المراد|المقصود|الفرق|حقيقة|مراتب|درجات)\b',query.strip()))
        named_phrase=len(safe_tokens(ap['subject_phrase']))>=2
        if not ap.get('focus_word') and len(ap['terms'])<=3 and len(literal)>=3 and (named_phrase or definitional):
            state['path']='phrase_and_union'
        # Do not discard phrase matches, even if the later passage stage stops.
        token=DEADLINE.set(min(overall-.08,time.monotonic()+4.5))
        try:
            stage('candidate_union')
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
                if key not in indexed_pages:indexed_pages[key]=db._indexable_text(page['text'])
                window=indexed_pages[key][left:right]
                # Filter fixed-expression homographs, never rewrite the source.
                if re.search(r'العجب كل العجب|كتب على نفسه البقاء وعلى الدنيا الفناء',window):continue
                from app.services.concept_links import linked_support
                linked=linked_support(query,window) if not ap.get('focus_word') else None
                if linked and ap['comparison_subjects'] and linked[3]==['sincerity','praise_desire']:linked=None
                support=supporting_span(query,window,keep,ap,candidate.get('features')) if not linked else None
                if linked:
                    value,start,end,linked_groups=linked
                    matched=[t for t in ap['anchors'] if pattern(t).search(window)]
                    relation=True
                elif support:
                    value,start,end,matched,relation=support
                else:
                    state.setdefault('rejections',{}).setdefault('no_local_subject',0)
                    state['rejections']['no_local_subject']+=1
                    continue
                # Two question words should co-occur, but a passage that names
                # the protected subject itself is kept as topic-only evidence:
                # extra verbs (يضر، يخاف) must not discard the only statement.
                if (not relation and not ap['comparison_subjects'] and len(matched)<min(2,len(ap['anchors']))
                        and not (ap.get('protected_anchor') in matched
                                 and all(relation_verb(t) for t in ap['anchors'] if t not in matched))):continue
                start+=left;end+=left
                if sense_conflict(query,page['text'],start,end):continue
                score=value if linked else .10+.70*value
                if linked:
                    # A broad related-topic alias must not outrank the
                    # requested subject solely through corpus authority.
                    score+=ranker_config()['weights']['linked_subject_coverage']*len(matched)/max(1,len(ap['anchors']))
                score+=procedural_support(query,window,start-left,end-left,matched,ap,relation)
                q=candidate['question']
                qa_match=bool(q) and all((comparison_pattern(t) if ap['comparison_subjects'] else pattern(t)).search(q) for t in ap['anchors'])
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
                if not linked and db._build_exact_variant_regex(ap['subject_phrase'],normalization_level='broad').search(window):score+=.20
                score+=.025/(1+abs(float(candidate['relevance'])))
                procedure=bool(_PROCEDURAL_QUESTION.match(query) and _PROCEDURAL_EVIDENCE.search(window) and (linked or relation))
                if procedure:
                    cue=_PROCEDURAL_EVIDENCE.search(window)
                    start=left+cue.start();end=min(right,left+cue.end()+220)
                row=make_row(page,query,start,end,min(.985,score),matched,relation,kwargs.get('context_chars',180),query_plan=ap)
                if procedure:row['procedure_list_support']=True
                row['candidate_routes']=candidate.get('route_ranks',{})
                row['fusion_score']=round(candidate.get('fusion_score',0),6)
                if candidate.get('unit_id'):row['evidence_unit_id']=candidate['unit_id']
                if linked:
                    row['concept_coverage']=linked_groups
                    row['subject_match']='typed_discovery'
                    from app.services.evidence_units import CUE_FORMS
                    intent=(ap.get('question_frame') or {}).get('intent')
                    cues=[f for f in CUE_FORMS.get(intent,()) if pattern(f).search(query)]
                    local=page['text'][max(left,start-80):min(right,end+120)]
                    if intent=='merit' and cues and any(pattern(cue).search(local) for cue in cues):
                        row['requested_relation_match']=True
                if qa_match:row['matched_source_question']=q
                classify_row(row,query,ap,page['text'],start,end,relation)
                matched_ids.add(key)
                if key not in records or row['score']>records[key]['score']:
                    from app.services.hit_contract import canonical_hit
                    canonical_hit(row,page)
                    records[key]=row
                    checkpoint_row(row,'validated_ranked_candidates')
            record_phase('indexed_feature_ranking_and_span_validation',scored)
            if state['completion']=='full':state['stages_completed'].append('indexed_feature_ranking_and_span_validation')
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
            row['_missing_protected_subject']=ap['protected_anchor'] not in row.get('_matched_anchors',()) and not row.get('subject_phrase_match') and not row.get('concept_coverage')
    before=len(rows)
    rows=[row for row in rows if not row.get('_missing_protected_subject')]
    state.setdefault('page_funnel',[]).append({'stage':'protected_subject_filter','in_pages':before,'out_pages':len(rows)})
    if any('observance' in ap.get('requested_facets',()) for ap in plans.values()):
        if not any(row.get('observance_support') for row in rows):
            state['unresolved_facets']=['observance']
    if any('preference' in ap.get('requested_facets',()) for ap in plans.values()):
        if not any(row['question_relevance']=='relation_candidate' for row in rows):
            state['unresolved_facets']=list(dict.fromkeys(state.get('unresolved_facets',[])+['preference']))
    # Coverage is evidence based and scoped: retain explicit mentions only.
    if any((set(plan(q)['required'])=={'children','upbringing'} or
            (re.search(r'تربي|اربي|ربي',normalize_search_text(q,level='broad')) and
             re.search(r'ابنا|اطفال|اولاد',normalize_search_text(q,level='broad')))) for q in queries):
        # The full how-to wording need not occur in an incidental source
        # mention. Discover attested topic phrases within the caller's scope,
        # while keeping them explicitly weak rather than inventing guidance.
        child_phrase=db._build_highlight_regex('تربية',whole_word=True).pattern+r'\s+(?:'+ '|'.join(db._build_highlight_regex(w,whole_word=False).pattern for w in ('الأطفال','الأولاد','الأبناء'))+')'
        rows=[r for r in rows if re.search(child_phrase,html.unescape(re.sub('<[^>]+>','',r['snippet'])))]
        if not rows:
            for phrase in ('تربية الأبناء','تربية الأطفال','تربية الأولاد'):
                for row in db.search(query=phrase,search_mode='exact_phrase',limit=8,
                                     diversify_books=False,ranking=kwargs.get('ranking','primary_first'),
                                     context_chars=kwargs.get('context_chars',180),**scope):
                    key=(row['book_id'],row['seq'])
                    if any((existing['book_id'],existing['seq'])==key for existing in rows):continue
                    records[key]=row
                    rows.append(row)
        for row in rows:row['question_relevance']='topic_only'
        state['coverage_gap']={'topic':'raising children','basis':'Only passing mentions established in supplied corpus audit'}

    if not rows and len(queries)==1:
        ap=plans[queries[0]];frame=ap.get('question_frame') or {}
        # A recognized question may lack a supported relation even though its
        # subject occurs. Keep such mentions visibly weak and scope-correct.
        if frame and frame['intent'] in {'importance','stance','signs','preference','coexistence','permission'} and not ap['comparison_subjects'] and not state.get('coverage_gap'):
            for term in dict.fromkeys((ap['subject_phrase'],ap.get('protected_anchor'))):
                if not term:continue
                found=db.search(query=term,search_mode='exact_phrase',limit=8,
                                diversify_books=False,ranking=kwargs.get('ranking','primary_first'),
                                context_chars=kwargs.get('context_chars',180),**scope)
                if found:rows=found;break
            for row in rows:
                row['question_relevance']='topic_only';row['answer_verified']=False
            if rows:
                state['fallback_level']='subject_only'
                state['candidate_counts']['subject_fallback']=len(rows)

    if kwargs.get('operator')=='AND' and query_ids:rows=[r for r in rows if (r['book_id'],r['seq']) in set.intersection(*query_ids)]
    # Phrase protection is only applicable when a complete subject was found.
    protected=sum(r.get('subject_phrase_match',False) for r in rows)>=3
    if kwargs.get('ranking') in ('book_order','chronological'):rows.sort(key=lambda r:(r['book_id'],r['seq']))
    else:
        for row in rows:db._set_rank_score(row)
        rows.sort(key=lambda r:(-bool(r.get('procedure_list_support')),-bool(r.get('corrects_premise')),-bool(r.get('requested_relation_match')),-r.get('focus_match_strength',0),
                                -(r.get('question_relevance')=='relation_candidate' if r.get('focus_match_strength') else 0),
                                -(bool(r.get('subject_phrase_match')) if protected else 0),
                                -(r['rank_score'] if kwargs.get('ranking')=='primary_first' else r['score']),
                                r['source_tier'],r['book_id'],r['seq']))
    before=len(rows);rows=[r for r in rows if r['score']>=float(kwargs.get('min_score') or 0)]
    state['page_funnel'].append({'stage':'score_filter','in_pages':before,'out_pages':len(rows)})
    before=len(rows);t=time.perf_counter();rows=deduplicate(rows);record_phase('deduplication',t)
    state['page_funnel'].append({'stage':'deduplication','in_pages':before,'out_pages':len(rows)})
    if not kwargs.get('include_topic_only',True) and not state.get('coverage_gap'):
        # A parallel copy in another edition (also_in) is not evidence that the
        # passage answers the question; it must not displace the other hits.
        supported=[r for r in rows if r['question_relevance']!='topic_only']
        # A weak source mention is safer than an unexplained empty result when
        # the subject is present; never promote it to an answer candidate.
        if supported:rows=supported
    before=len(rows)
    if kwargs.get('diversify_books',True) and len(kwargs.get('book_ids') or [])!=1:
        counts={};selected=[]
        for r in rows:
            b=r['book_id']
            if counts.get(b,0)<kwargs.get('max_per_book',2):selected.append(r);counts[b]=counts.get(b,0)+1
        rows=selected
    state['page_funnel'].append({'stage':'diversification','in_pages':before,'out_pages':len(rows)})
    state['stages_completed']=list(dict.fromkeys(state['stages_completed']+['relation_check','deduplication']))
    state['evidence_strength']='weak' if state.get('coverage_gap') else 'partial' if state.get('unresolved_facets') and any(r['question_relevance']!='topic_only' for r in rows) else 'weak' if state.get('unresolved_facets') else 'candidate' if any(r['question_relevance']!='topic_only' for r in rows) else 'weak'
    state['path']='partial' if state['completion']=='partial' else state['path']
    before=len(rows);offset=kwargs.get('offset',0);rows=rows[offset:offset+kwargs.get('limit',8)]
    state['page_funnel'].append({'stage':'pagination','in_pages':before,'out_pages':len(rows)})
    for i,r in enumerate(rows,offset+1):
        r['rank']=i
        r.pop('_matched_anchors',None);r.pop('_missing_protected_subject',None)
    return rows
