"""Language-level discovery rules, not assertions of quotation equivalence."""
from functools import lru_cache
import re
from app.core.arabic_utils import safe_tokens,normalize_search_text
FUNCTION_WORDS=set('ما ماذا هل كيف لماذا متى أين اين من في على إلى الى عن مع و أو أم ثم هذا هذه ذلك تلك هو هي هم هن نحن أنا انا أنت انت الذي التي الذين إن أن كان كانت يكون وهل وما وهو وهي به بها لهم له لها عليه عليها عليهم لكي حتى عند بين كل أي اي ولا إلا لا لم لن بس لو لما عشان إزاي ازاي إيه ايه ليه عايز عاوز أعمل اعمل بماذا'.split())
KEYS={normalize_search_text(t,level='broad') for t in FUNCTION_WORDS}
FRAMES=sorted(['إيه رأي مولانا في','ما المراد بـ','ما المراد ب','ما المراد','ما ثواب','ما فضل','ما فائدة','ما أثر','ما هي','ما هو','ما حكم','ما معنى','ما الفرق بين','كيف يفرق الشيخ بين','كيف يفرق بين','كيف يجمع السالك بين','كيف يجمع بين','كيف يميز السالك بين','كيف يميز بين','كيف أميز بين','كيف يختلف','ما التوازن بين','لماذا تعد','لماذا يعتبر','إيه أعمل','ما','كيف','هل','لماذا','متى','ماذا','بماذا','إيه','ايه','عايز','عاوز','ليه','إزاي','ازاي'],key=len,reverse=True)
_PAIR = re.compile(r'(?:الفرق|التوازن|يفرق|يجمع|يميز|أميز)\s+(?:(?:الشيخ|السالك)\s+)?بين\s+([ء-ي]+)\s+و\s*([ء-ي]+)')
_VERSUS = re.compile(r'([ء-ي]+)\s+(?:عن|من)\s+([ء-ي]+)')
_MEANING_VERSUS = re.compile(r'معنى\s+([ء-ي]+)\s+وكيف\s+يختلف\s+عن\s+([ء-ي]+)')
# These are discovery-only families. Source text and literal counts are never
# rewritten to a synonym or a different spelling.
# Source-attested vocabulary for candidate discovery only. Literal search and
# occurrence counts continue to use the caller's original surface form.
DISCOVERY_VARIANTS = {
 'تدخين': ('سجاير','الدخان','الشيشة'),
 'سجاير': ('تدخين','الدخان','الشيشة'),
 'شيشة': ('تدخين','سجاير','الدخان'),
 'السجائر': ('سجاير','سيجارة','تدخين'),
 'سجائر': ('سجاير','سيجارة','تدخين'),
 'سيجارة': ('سجاير','السجائر','تدخين'),
 'مجالسة': ('صحبة','الصحبة','مصاحبة','ملازمة'),
 'صحبة': ('مجالسة','مصاحبة','ملازمة'),
 'مصاحبة': ('مجالسة','صحبة','ملازمة'),
 'ثواب': ('فضل','أفضل','أجر'),
 'فضل': ('ثواب','أفضل','أجر'),
 'أجر': ('ثواب','فضل'),
 'رؤية': ('رؤيا','يرى','رأى'),
 'رؤيا': ('رؤية','يرى','رأى'),
 'يرى': ('رؤية','رؤيا','رأى'),
}
DISCOVERY_VARIANTS = {
 normalize_search_text(key,level='broad'): tuple(normalize_search_text(value,level='broad') for value in values)
 for key,values in DISCOVERY_VARIANTS.items()
}
_ROLE = r'(?:الشيخ|مولانا|المريد|السالك|العبد|الإنسان|الناس)'
_TRAILING_CONTEXT = re.compile(r'\s+(?:عند\s+الصوفية|في\s+طريق\s+(?:السلوك|القوم)|في\s+رحمته|من\s+الله)$')


def comparison_subjects(query):
 """Extract the two requested concepts, without question-frame vocabulary."""
 q=normalize_search_text(query,level='safe')
 # Explicit contrast between doing a deed for God and for people's praise is
 # the sincerity/showing-off pair in the source vocabulary. This is a topic
 # expansion for discovery, not a claim that either source passage answers it.
 if re.search(r'عمل[هي]?\s+لله',q) and re.search(r'(?:مدح|ثناء)\s+الناس',q):
  return ['الإخلاص','الرياء']
 meaning=_MEANING_VERSUS.search(q)
 if meaning:parts=list(meaning.groups())
 else:
  # Combining two practices is a practical-relation question; keep its
  # intent concepts so an attested paraphrase of either practice can match.
  between=None if re.search(r'\b(?:نجمع|يجمع)\s+(?:السالك\s+)?بين\b',q) else re.search(r'\bبين\s+(.+)$',q)
  if between:
   payload=between.group(1)
   pair=re.search(r'\s+و(?=[ء-ي])',payload)
   parts=[payload[:pair.start()],payload[pair.start()+1:]] if pair else []
  else:
   arrival=re.search(r'(?:يصل|يبلغ)\s+(?:'+_ROLE+r'\s+)?إلى\s+(.+?)\s+بعد\s+(.+)$',q)
   direct=(re.search(r'(?:أميز|نميز|يميز)\s+(.+?)\s+من\s+(.+)$',q)
           or re.search(r'يختلف\s+(.+?)\s+عن\s+(.+)$',q)
           or re.search(r'يغل[ّ]?ب\s+(?:'+_ROLE+r'\s+)?(.+?)\s+أم\s+(.+)$',q))
   parts=list(reversed(arrival.groups())) if arrival else list(direct.groups()) if direct else []
 if len(parts)!=2:return []
 cleaned=[]
 for part in parts:
  part=re.sub(r'^و(?=[ء-ي])','',part.strip())
  part=_TRAILING_CONTEXT.sub('',part).strip()
  part=re.sub(r'\s+(?:الحقيقي|الحقيقية)$','',part).strip()
  cleaned.append(part)
 if all(part.startswith('مقام ') for part in cleaned):cleaned=[part[5:] for part in cleaned]
 if any(not part or len(safe_tokens(part))>3 for part in cleaned):return []
 if normalize_search_text(cleaned[0],level='broad')==normalize_search_text(cleaned[1],level='broad'):return []
 return cleaned

def subject_phrase(query):
 query=query.strip(' ؟?')
 subjects=comparison_subjects(query)
 if subjects:return ' و'.join(subjects)
 query=re.sub(r'^(?:كيف\s+)?يتخلص\s+(?:'+_ROLE+r'\s+)?من\s+','',query)
 query=re.sub(r'^هل\s+يرى\s+(?:'+_ROLE+r'\s+)?','رؤية ',query)
 query=re.sub(r'^ما\s+(?:رأي|موقف)\s+(?:'+_ROLE+r')\s+في\s+','',query)
 for frame in FRAMES:
  if query.startswith(frame+' '):
   query=query[len(frame):].strip();break
 # Keep the noun phrase; a trailing request is a separate clause.
 query=re.split(r'\s+(?:وكيف|وهل|ولماذا|في طريق القوم)\b',query,maxsplit=1)[0]
 query=re.sub(r'\s+(?:عند الشيخ|مهمة للمريد|على قلب المريد)$','',query)
 if query.startswith('مجالسة '):query=re.sub(r'\s+في\s+تزكية\b.*$','',query)
 query=re.sub(r'\s+في\s+عبادته$','',query)
 query=re.sub(r'\s+صلى\s+الله\s+عليه\s+وسلم\b','',query)
 query=re.sub(r'^ب(?=الأعيان|المعنى|المقصود)', '', query)
 return query
def language_plan(query,keep_terms=()):
 keep={normalize_search_text(t,level='broad') for t in keep_terms}
 tokens=list(dict.fromkeys(safe_tokens(subject_phrase(query))+[t for t in safe_tokens(query) if normalize_search_text(t,level='broad') in keep]))
 terms=[t for t in tokens if normalize_search_text(t,level='broad') not in KEYS or normalize_search_text(t,level='broad') in keep]
 focus=re.match(r'^ما\s+(ثواب|فضل|أجر)\b',query)
 focus_word=focus.group(1) if focus else None
 if focus_word and focus_word not in terms:terms.append(focus_word)
 negation=any(t in safe_tokens(query) for t in ('لا','لم','لن','ولا')) or any(t.endswith('ش') and len(t)>4 for t in tokens)
 # Initial ما is an interrogative in these frames. Only a later ما can negate.
 negation=negation or bool(re.search(r'\S+\s+ما\s+',query))
 subjects=comparison_subjects(query)
 subject=subject_phrase(query)
 if subjects:terms=subjects
 return {'subject_phrase':subject,'terms':terms,'focus_word':focus_word,'dropped_function_words':[t for t in safe_tokens(query) if normalize_search_text(t,level='broad') in KEYS and normalize_search_text(t,level='broad') not in keep],'negation_present':negation,'comparison_subjects':subjects}
@lru_cache(maxsize=4096)
def morphological_forms(term):
 word=normalize_search_text(term,level='broad');bases={word}
 if word.startswith('ما') and word.endswith('ش') and len(word)>6:bases.add(word[2:-1])
 elif word.endswith('ش') and len(word)>4:bases.add(word[:-1])
 for value in tuple(bases):
  for prefix in ('وال','بال','فال','لل','ال','و','ف','ب','ل'):
   if value.startswith(prefix) and len(value)-len(prefix)>=3:bases.add(value[len(prefix):])
 for value in tuple(bases):
  for suffix in ('هما','هم','ها','نا','كم','ه','ي'):
   if value.endswith(suffix) and len(value)-len(suffix)>=3:bases.add(value[:-len(suffix)])
 for value in tuple(bases):
  if value[:1] in ('ا','ت','ي','ن') and len(value)>=4:bases.add(value[1:])
 forms=set(bases)
 for value in tuple(bases):forms.update(DISCOVERY_VARIANTS.get(value,()))
 for value in bases:forms.update((value,'ال'+value,'ي'+value,'ت'+value))
 return tuple(sorted(forms,key=lambda x:(-len(x),x)))
