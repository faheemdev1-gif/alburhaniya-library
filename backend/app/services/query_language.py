"""Language-level discovery rules, not assertions of quotation equivalence."""
from functools import lru_cache
from app.core.arabic_utils import safe_tokens,normalize_search_text
FUNCTION_WORDS=set('ما ماذا هل كيف لماذا متى أين اين من في على إلى الى عن مع و أو أم ثم هذا هذه ذلك تلك هو هي هم هن نحن أنا انا أنت انت الذي التي الذين إن أن كان كانت يكون وهل وما وهو وهي به بها لهم له لها عليه عليها عليهم لكي حتى عند بين كل أي اي ولا إلا لا لم لن بس لو لما عشان إزاي ازاي إيه ايه ليه عايز عاوز أعمل اعمل بماذا'.split())
KEYS={normalize_search_text(t,level='broad') for t in FUNCTION_WORDS}
FRAMES=sorted(['إيه رأي مولانا في','ما المراد بـ','ما المراد ب','ما المراد','ما فضل','ما هي','ما هو','ما حكم','ما معنى','إيه أعمل','ما','كيف','هل','لماذا','بماذا','إيه','ايه','عايز','عاوز','ليه','إزاي','ازاي'],key=len,reverse=True)
def subject_phrase(query):
 query=query.strip(' ؟?')
 for frame in FRAMES:
  if query.startswith(frame+' '):
   query=query[len(frame):].strip();break
 # Keep the noun phrase; a trailing request is a separate clause.
 import re
 query=re.split(r'\s+(?:وكيف|وهل|ولماذا|في طريق القوم)\b',query,maxsplit=1)[0]
 query=re.sub(r'^ب(?=الأعيان|المعنى|المقصود)', '', query)
 return query
def language_plan(query,keep_terms=()):
 keep={normalize_search_text(t,level='broad') for t in keep_terms}
 tokens=list(dict.fromkeys(safe_tokens(subject_phrase(query))+[t for t in safe_tokens(query) if normalize_search_text(t,level='broad') in keep]))
 terms=[t for t in tokens if normalize_search_text(t,level='broad') not in KEYS or normalize_search_text(t,level='broad') in keep]
 return {'subject_phrase':subject_phrase(query),'terms':terms,'dropped_function_words':[t for t in safe_tokens(query) if normalize_search_text(t,level='broad') in KEYS and normalize_search_text(t,level='broad') not in keep],'negation_present':any(t in safe_tokens(query) for t in ('لا','لم','لن','ما','ولا')) or any(t.endswith('ش') and len(t)>4 for t in tokens)}
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
 for value in bases:forms.update((value,'ال'+value,'ي'+value,'ت'+value))
 return tuple(sorted(forms,key=lambda x:(-len(x),x)))
