"""Language-level discovery rules, not assertions of quotation equivalence."""
from functools import lru_cache
import re
from app.core.arabic_utils import safe_tokens,normalize_search_text
FUNCTION_WORDS=set('ما ماذا هل كيف لماذا متى أين اين من في على إلى الى عن مع و أو أم ثم هذا هذه ذلك تلك هو هي هم هن نحن أنا انا أنت انت الذي التي الذين إن أن كان كانت يكون وهل وما وهو وهي به بها لهم له لها عليه عليها عليهم لكي حتى عند بين كل أي اي ولا إلا لا لم لن بس لو لما عشان إزاي ازاي إيه ايه ليه عايز عاوز أعمل اعمل بماذا'.split())
KEYS={normalize_search_text(t,level='broad') for t in FUNCTION_WORDS}
FRAMES=sorted(['إيه رأي مولانا في','ما المراد بـ','ما المراد ب','ما المراد','ما فضل','ما فائدة','ما أثر','ما هي','ما هو','ما حكم','ما معنى','ما الفرق بين','كيف يفرق الشيخ بين','كيف يفرق بين','كيف يجمع السالك بين','كيف يجمع بين','ما التوازن بين','لماذا تعد','لماذا يعتبر','إيه أعمل','ما','كيف','هل','لماذا','بماذا','إيه','ايه','عايز','عاوز','ليه','إزاي','ازاي'],key=len,reverse=True)
_PAIR = re.compile(r'(?:الفرق|التوازن|يفرق|يجمع)\s+(?:(?:الشيخ|السالك)\s+)?بين\s+([ء-ي]+)\s+و\s*([ء-ي]+)')
_VERSUS = re.compile(r'([ء-ي]+)\s+(?:عن|من)\s+([ء-ي]+)')
_MEANING_VERSUS = re.compile(r'معنى\s+([ء-ي]+)\s+وكيف\s+يختلف\s+عن\s+([ء-ي]+)')
# Source-attested vocabulary for candidate discovery only. Literal search and
# occurrence counts continue to use the caller's original surface form.
DISCOVERY_VARIANTS = {
 'تدخين': ('سجاير','الدخان','الشيشة'),
 'سجاير': ('تدخين','الدخان','الشيشة'),
 'شيشة': ('تدخين','سجاير','الدخان'),
}
def subject_phrase(query):
 query=query.strip(' ؟?')
 for frame in FRAMES:
  if query.startswith(frame+' '):
   query=query[len(frame):].strip();break
 # Keep the noun phrase; a trailing request is a separate clause.
 import re
 query=re.split(r'\s+(?:وكيف|وهل|ولماذا|في طريق القوم)\b',query,maxsplit=1)[0]
 query=re.sub(r'\s+(?:عند الشيخ|مهمة للمريد|على قلب المريد)$','',query)
 query=re.sub(r'^ب(?=الأعيان|المعنى|المقصود)', '', query)
 return query
def language_plan(query,keep_terms=()):
 keep={normalize_search_text(t,level='broad') for t in keep_terms}
 tokens=list(dict.fromkeys(safe_tokens(subject_phrase(query))+[t for t in safe_tokens(query) if normalize_search_text(t,level='broad') in keep]))
 terms=[t for t in tokens if normalize_search_text(t,level='broad') not in KEYS or normalize_search_text(t,level='broad') in keep]
 negation=any(t in safe_tokens(query) for t in ('لا','لم','لن','ولا')) or any(t.endswith('ش') and len(t)>4 for t in tokens)
 # Initial ما is an interrogative in these frames. Only a later ما can negate.
 negation=negation or bool(re.search(r'\S+\s+ما\s+',query))
 comparison=_PAIR.search(query) or _MEANING_VERSUS.search(query)
 if not comparison and re.search(r'يختلف\s+عن|مقارنة|مقابل',query):
  comparison=_VERSUS.search(query)
  if comparison and comparison.group(1)=='يختلف':comparison=None
 subjects=list(comparison.groups()) if comparison else []
 if len(subjects)==2 and normalize_search_text(subjects[0],level='broad')==normalize_search_text(subjects[1],level='broad'):subjects=[]
 subject=subject_phrase(query)
 if subjects and subjects[1] not in subject:subject=' و'.join(subjects)
 return {'subject_phrase':subject,'terms':terms,'dropped_function_words':[t for t in safe_tokens(query) if normalize_search_text(t,level='broad') in KEYS and normalize_search_text(t,level='broad') not in keep],'negation_present':negation,'comparison_subjects':subjects}
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
