"""Conservative, compositional Arabic discovery. No answer verification.

Aliases are language-level vocabulary, not query-to-page mappings. New topics
retain content anchors instead of selecting arbitrary sentence-final words.
"""
from functools import lru_cache
from app.core.observability import profiled
from app.core.arabic_utils import ARABIC_STOPWORDS, safe_tokens, normalize_search_text

POLICY = 'local-question-facets-v2'
from app.services.query_language import FUNCTION_WORDS,language_plan,FRAMES,morphological_forms

# Each concept has explicit forms; ambiguous bare صدر / مال / عيش / يوم
# are deliberately absent. Clitic forms are generated conservatively below.
CONCEPTS = {
 'provision': 'الرزق رزق رزقه الأرزاق للرزق المعيشة معيشة الدخل الفقر فقر الغنى قلة المال كسب العيش لقمة العيش',
 'work': 'السعي سعي العمل عمل للعمل الكسب للكسب كسب لكسب شغل الشغل بتعمل اشتغل طلب الرزق يترك العمل ترك العمل',
 'litanies': 'الأوراد أوراد الورد بالذكر الذكر يقرأ الأوراد قراءة الأوراد',
 'prayer': 'الصلاة صلاة الصلوات صلاتي صلاته الفرائض الفريضة فريضة',
 'timing': 'وقتها أوقاتها اوقاتها مواعيدها أوقاتها ميقات مواقيت الأوقات يؤخر تأخير تأخيرها لوقتها لمواقيتها',
 'anger': 'الغضب غضب غضبت غضبه غاضب الغيظ غيظ كظم الغيظ أتعصب تعصب',
 'speech': 'اللسان لسان لساني لسانه كلام الكلام بكلامي الجارح الجارحة أؤذي السب الشتم الغيبة حفظ اللسان ضبط اللسان',
 'quran': 'القرآن قرآن القران قران المصحف',
 'continuity': 'أداوم المداومة للمداومة يداوم داوم دائما دائم الاستمرار أستمر يستمر أنتظم أواظب المحافظة للمحافظة أحافظ يحافظ منتظم يومي يوميا يومية كل يوم ورد يومي أنقطع انقطع',
 'distress': 'الحزن حزن حزنا حزين الهم مهموم الهموم الكرب كرب كربه ضيق الصدر ضيق صدرك ضاق صدرك تضيق ضيق بضيق ضاقت فقد الأمل اليأس',
 'relief': 'الطمأنينة طمأنينة يطمئن اطمأن الاطمئنان الفرج فرج تفريج الصبر صبر اصبر صبرا الاستغفار استغفر التوكل توكل الرجاء الأمل مخرجا',
}
# Language-level variants. No book/page IDs or benchmark answer mappings.
CONCEPTS.update({
 'repentance':'التوبة توبة يتوب توبته تتوب تاب التائب التواب أرجع التوبة',
 'sin':'الذنب الذنوب ذنوبه ذنب المعاصي المعصية معصية الخطايا الندم الإقلاع',
 'pride':'الكبر كبر تكبر التكبر الغرور متكبر',
 'vanity':'العجب عجب الإعجاب بالنفس حظوظ نفس',
 'etiquette':'آداب أدب الأدب احترام حرمة طاعة',
 'guide':'شيخه الشيخ شيخ المشايخ أستاذه',
 'intercession':'التوسل توسل يتوسل استغاث استغاثة الشفاعة',
 'saints':'الأولياء أولياء قبور ولي صالحين',
 'parents':'والديه والدي والديه الوالدين أباه أبيه أبوه والديهما',
 'death':'موتهما موتهم موته الميت قبره بعده الدعاء',
 'mawlid':'المولد مولد المولد النبوي الاحتفال',
 'children':'الأطفال الأولاد الأبناء ولادي أولادي',
 'upbringing':'تربية أربي التربية تقويمهم',
 # Bayʿa/ʿahd vocabulary (البيعة، الرباط، الرابطة) is the covenant, a different
 # concept; matching it made covenant passages pose as companionship.
 'companionship':'صحبة الصحبة مصاحبة يصاحب الرفقة ملازمة مجالسة الجلوس يجالس',
})
# Parse multiword expressions separately; avoid accidental homographs.
PHRASES={
 'provision':['قلة المال','كسب العيش','لقمة العيش','تيسير الرزق','جلب الرزق','طلب الرزق','سعة الرزق'],
 'work':['طلب الرزق','يترك العمل','ترك العمل'],
 'litanies':['يقرأ الأوراد','قراءة الأوراد'],
 'anger':['كظم الغيظ'], 'speech':['حفظ اللسان','ضبط اللسان'],
 'continuity':['كل يوم','ورد يومي'],
 'vanity':['حظوظ نفس','الإعجاب بالنفس'], 'mawlid':['المولد النبوي'],
 'distress':['ضيق الصدر','ضيق صدرك','ضاق صدرك','فقد الأمل']}
for key,phrases in PHRASES.items():
 for phrase in phrases:CONCEPTS[key]=CONCEPTS[key].replace(phrase,'')
CONCEPTS={k:tuple(dict.fromkeys(v.split()+PHRASES.get(k,[]))) for k,v in CONCEPTS.items()}


@lru_cache(maxsize=64)
def concept_regex(name):
 import re
 return re.compile('|'.join('(?:'+pat.pattern+')' for _,pat in concept_patterns(name)))


def content_terms(query):
 return language_plan(query)['terms']

@lru_cache(maxsize=2048)
def concept_patterns(name):
 from app.services.library_db import _build_highlight_regex
 forms=[]
 for form in CONCEPTS[name]:
  forms.append(form)
  forms.extend(prefix+form for prefix in ('و','ف','ب'))
  forms.append('ل'+form[1:] if form.startswith('ال') else 'ل'+form)
 return tuple((form,_build_highlight_regex(form)) for form in dict.fromkeys(forms))

@lru_cache(maxsize=2048)
@profiled("question_parsing")
def plan(query):
 found={k: [m.group() for m in concept_regex(k).finditer(query)] for k in CONCEPTS}
 found={k:v for k,v in found.items() if v}
 for term in content_terms(query):
  for group in CONCEPTS:
   if group not in found and any(concept_regex(group).fullmatch(f) for f in morphological_forms(term)):found[group]=[term]
 # Different questions use the same compositional facets. Supporting facets
 # may be proposed for discovery, but are disclosed rather than inferred facts.
 # Comparison subjects are extracted by the language parser. A role word such
 # as "الشيخ" must not reroute a comparison to disciple etiquette.
 if language_plan(query)['comparison_subjects']:groups=[];required=[]
 elif 'الصلاة على' in query or 'الصلاه علي' in query:groups=[];required=[]
 elif 'litanies' in found and ('work' in found or 'provision' in found):groups=['litanies','work','provision'];required=['litanies','work','provision']
 elif 'prayer' in found and ('timing' in found or 'continuity' in found):groups=['prayer','timing','continuity'];required=['prayer','timing'] if 'timing' in found else ['prayer','continuity']
 elif 'companionship' in found:groups=['companionship','guide'];required=groups[:]
 elif 'anger' in found:groups=['anger','speech'];required=['anger','speech']
 elif 'quran' in found:groups=['quran','continuity'];required=groups[:]
 elif 'provision' in found:groups=['provision','distress','relief'];required=['provision']
 # Relief words (الرجاء، الاستغفار، التوكل، الصبر) are also stations and
 # practices in their own right. Only an explicit distress word makes a
 # question about relief from distress; otherwise the forgiveness hadiths
 # become a fixed result group for any question that mentions hope.
 elif 'distress' in found:groups=['distress','relief'];required=groups[:]
 else:
  pairs=[('repentance','sin'),('pride','vanity'),('etiquette','guide'),('intercession','saints'),('parents','death'),('children','upbringing')]
  chosen=next((list(pair) for pair in pairs if all(g in found for g in pair)),None)
  if chosen:groups=chosen;required=chosen
  elif 'mawlid' in found:groups=['mawlid'];required=['mawlid']
  else:groups=[];required=[]
 return {'groups':groups,'required':required,'recognized':found,'terms':content_terms(query),
         'relation_verification':'anchor_cooccurrence_only'}


def livelihood_intent(query):
 return 'provision' in plan(query)['recognized']


def is_question(query):
 from app.services.query_language import question_frame
 return len(safe_tokens(query))>=2 and (bool(question_frame(query)) or bool(__import__('re').search(r'^إذا\b.+(?:فكيف|فهل)',query)) or len(safe_tokens(query)) > 3 and bool(plan(query)['groups']) or any(query.startswith(frame+' ') for frame in FRAMES))


def discovery_phrases(queries,limit=6):
 phrases=[]
 for q in queries:
  terms=content_terms(q)
  phrases.extend(' '.join(terms[i:i+2]) for i in range(len(terms)-1) if ' '.join(terms[i:i+2]) in q)
  p=plan(q)
  for group in p['groups']:
   for form in CONCEPTS[group]:
    if form not in phrases:phrases.append(form)
  if not p['groups']:
   phrases.extend(p['terms'])
 return phrases[:max(1,int(limit))]



def phrase_matches(phrase, text, builder):
 return any(builder(form).search(text) for form in [phrase,'ل'+phrase,'ب'+phrase,'و'+phrase,'ف'+phrase])

def local_concept_matches(group, text):
 matches=[]
 for m in concept_regex(group).finditer(text):
  before=normalize_search_text(text[max(0,m.start()-14):m.start()],level='broad').split()
  # "Abu al-Faraj" and "Abu Karib" are names, not relief/distress.
  if group in ('distress','relief') and before and before[-1] in ('ابو','ابي','ابا'):continue
  matches.append(m.group())
 return matches

def assess_window(query,text,start,end,pattern_builder):
 p=plan(query);left=max(0,start-420);right=min(len(text),end+420)
 # A blank-line boundary is a source paragraph boundary. Do not borrow an
 # unrelated relation from the next Q&A merely because it is nearby.
 before=text.rfind('\n\n',left,start)
 after=text.find('\n\n',end,right)
 if before>=0:left=before+2
 if after>=0:right=after
 window=text[left:right]
 matched=[t for t in p['terms'] if pattern_builder(t).search(window)]
 anchors={g:local_concept_matches(g,window) for g in p['groups']}
 preserved=[g for g in p['required'] if anchors[g]]
 dropped=[g for g in p['required'] if not anchors[g]]
 if p['groups']:
  if not anchors[p['required'][0]]:return None
  if 'provision'==p['required'][0] and len(p['required'])==1:
   relational=bool(anchors.get('relief') or anchors.get('distress') or any(phrase_matches(t,window,pattern_builder) for t in ['تيسير الرزق','جلب الرزق','شكا الفقر','عنه الفقر','طلب الرزق']))
  else:relational=not dropped
  if p['required']==['anger','speech']:
   control=[t for t in ['كظم','الكاظمين','يكظم','لا تغضب','ضبط','احفظ','حفظ','يمسك','أمسك','حليم','الحلم','الصفح','عفوا'] if pattern_builder(t).search(window)]
   relational=relational and bool(control)
  if p['required']==['litanies','work','provision']:
   earning=[t for t in ['الرزق','للرزق','رزقه','الكسب','كسب العيش','دكان','اشتغل','شغل'] if pattern_builder(t).search(window)]
   relational=relational and bool(earning)
  score=.2+.48*(len(preserved)/len(p['required'])) + .12*relational
  if relational:
   score += .08*sum(bool(anchors[g]) for g in p['groups'])/len(p['groups'])
  topic=anchors[p['required'][0]]
  relations=[a for g,forms in anchors.items() if g!=p['required'][0] for a in forms]
  if p['required']==['provision']:
   relations += [t for t in ['تيسير الرزق','جلب الرزق','طلب الرزق','سعة الرزق','شكا الفقر','عنه الفقر'] if phrase_matches(t,window,pattern_builder)]
 else:
  if len(matched)<2:return None
  # Unknown relations are never promoted based on token count.
  relational=False;score=.2+.4*len(matched)/max(1,len(p['terms']));topic=matched;relations=[]
 if p['required']==['provision'] and relational:
   if any(phrase_matches(t,window,pattern_builder) for t in ['تيسير الرزق','جلب الرزق','سعة الرزق']):score += .22
   elif any(phrase_matches(t,window,pattern_builder) for t in ['شكا الفقر','عنه الفقر']):score += .16
   elif phrase_matches('طلب الرزق',window,pattern_builder):score += .10
 if p['required']==['quran','continuity'] and any(pattern_builder(t).search(window) for t in ['كل يوم','ورد يومي','يواظب','يداوم']):score += .07
 coverage=len(matched)/max(1,len(p['terms']))
 return {'intent_score':round(min(.99,(score+.08*coverage)/1.15),6),'intent_term_coverage':round(coverage,4),
  'question_relevance':'relation_candidate' if relational else 'topic_only','intent_method':POLICY,
  'answer_verified':False,'reformulation_status':'ok' if relational else 'degraded',
  'intent_evidence':{'query_terms':matched,'topic_terms':sorted(set(topic)),
   'relation_terms':sorted(set(relations)),'preserved_concepts':preserved,'dropped_concepts':dropped,
   'proposed_concepts':[g for g in p['groups'] if g not in p['recognized']],
   'relation_check':'local_anchor_cooccurrence_unverified','start':left,'end':right}}
