"""Typed, auditable discovery links. No editorial review is fabricated.

A small development lexicon, not the requested 600-concept reviewed lexicon.
Forms are used only in discovery and must be attested before entering the index.
Exact search and occurrence counting never use these links.
"""
from app.core.arabic_utils import normalize_search_text
VERSION='discovery-links-1.0-unreviewed'
CONCEPT_FORMS={
 'love_affection':('يحب','يحبون','محبة','المحبة','حب','الحب','أحب','أحبني','أحبه'),
 'prophet_names':('محمد','النبي','النبى','الرسول','رسول الله'),
 'praise_desire':('ثناء','الثناء','مدح','المدح','مدح الناس','الرياء','رياء','سمعة','السمعة'),
 'seclusion':('الخلوة','خلوة','المراقبة','مراقبة'),
 'prophet_love':('حب الرسول','محبة الرسول','محبة النبي','حب النبي','يحب','محبة','حب','محمد','الرسول','النبي'),
 'heart_dhikr':('ذكر القلب','بقلبي','بقلبه','بقلوبهم','القلب','قلبك','قلبي','قلوب'),
 'commerce':('التجارة','تجارة','تجارتي','البيع','الشراء','بيع','شراء','السوق','شغل','العمل','أعمل','يعمل','الجوارح'),
 'sincerity':('أخلص','مخلص','الإخلاص','إخلاص','مخلص','الرياء','رياء','مدح الناس'),
 'disciple_sincerity':('صدق المريد','المريد الصادق','مريد صادق','صدق','الصادق'),
 'repentance_conditions':('شروط التوبة','التوبة','توبته','التائب','ندم','الندم','الإقلاع'),
 'disagreement':('أخيك','أخيه','اخيك','اخيه','الغضبان','اختلافه','اختلاف','الخلاف','إخوانه','أخ','آذاني','أذى','أؤذي','خصومة','الخصومة','أجيبه','الغضب','الغضبان','كظم الغيظ','الغيظ','لا تغضب','الصفح'),
 'interrupted_practice':('تركت','انقطع','انقطاع','أوراده','أورادي','وردي','الأوراد','الاسم','للاسم','الاستغفار','يبدأ'),
 'fawatih_connection':('المشائخ','المشايخ','الفواتح','بالفواتح','الفاتحة','بالفاتحة','اتصال','الاتصال','بالمشايخ','المشايخ'),
 'fear':('الخشية','خشية','الخوف','خوف','يخاف','يخشى','مخافة'),
 'hope':('الرجاء','رجاء','الأمل','أمل','يرجو','يطمع','الطمع'),
}
# Each relation keeps its identity and uncertainty. These are candidates for
# domain review, never synonyms asserted to have identical religious meaning.
LINKS=[{'from_id':a,'to_id':b,'relation':kind,'direction':'bidirectional',
        'review_status':'unreviewed','scope':'discovery_only'} for a,b,kind in (
 ('صدق المريد','المريد الصادق','derivational_phrase'),
 ('الخوف','الخشية','contextual_related'),('الأمل','الرجاء','contextual_related'),
 ('الفواتح','الفاتحة','observed_plural'),('المشايخ','الشيخ','observed_plural'))]

def normalized_forms(group):
    return tuple(dict.fromkeys(normalize_search_text(x,level='broad') for x in CONCEPT_FORMS[group]))

def query_groups(query):
    """Composable relationships; qualifiers do not erase the named subjects."""
    import re
    q=normalize_search_text(query,level='broad')
    groups=[]
    if re.search(r'خلو',q):groups=['seclusion']
    elif re.search(r'يحب|حب|محبه',q) and re.search(r'محمد|النبي|الرسول',q):groups=['love_affection','prophet_names']
    elif re.search(r'ذكر|اذكر|يذكر',q) and re.search(r'قلب',q) and re.search(r'عمل|يعمل|تجار|بيع|شراء|جوارح|السوق',q):groups=['heart_dhikr','commerce']
    elif re.search(r'خش|خوف|يخاف',q) and re.search(r'امل|رجاء|يرجو|يطمع',q):groups=['fear','hope']
    elif re.search(r'فاتح|فواتح',q) and re.search(r'اتصال|مواظب|مشايخ|شيخ',q):groups=['fawatih_connection']
    elif re.search(r'ورد|اوراد',q) and re.search(r'تركت|انقطع|انقطاع|اعود|يبدا',q):groups=['interrupted_practice']
    elif re.search(r'توب',q) and re.search(r'شرط|شروط|نصوح|تكفي|كلام|لسان|ذنب|استغفار',q):groups=['repentance_conditions']
    elif re.search(r'اخوان|خصوم|اذاني|اجيب|اختلاف',q) and re.search(r'ادب|لسان|اذاني|اجيب|حفظ|يحافظ',q):groups=['disagreement']
    elif re.search(r'اخلص|اخلاص',q) and re.search(r'ثناء|رياء|مدح',q):groups=['sincerity','praise_desire']
    elif re.search(r'لله',q) and re.search(r'مدح|ثناء|رياء',q):groups=['sincerity']
    elif re.search(r'صدق|صادق',q) and re.search(r'مريد',q):groups=['disciple_sincerity']
    return groups

from functools import lru_cache
import re
@lru_cache(maxsize=128)
def source_pattern(group):
    from app.services.library_db import _build_highlight_regex
    return re.compile('|'.join(_build_highlight_regex(f,normalization_level='broad',whole_word=True).pattern for f in
                              dict.fromkeys(x for form in CONCEPT_FORMS[group] for x in (form,'و'+form,'ف'+form,'ب'+form,'ل'+form))))

def linked_support(query,text):
    """Uncalibrated local relation signal; no page routing or truth claim."""
    groups=query_groups(query)
    if not groups or groups==['sincerity']:return None
    events={g:list(source_pattern(g).finditer(text)) for g in groups}
    if any(not v for v in events.values()):return None
    norm=normalize_search_text(text,level='broad')
    cues={'seclusion':r'اغنت عن|مافيش|لا.*خلوه|المراقبه|لغ[يى]',
      'prophet_love':r'حب|محبه','love_affection':r'حب|محبه', 'heart_dhikr':r'ذكر','disciple_sincerity':r'مريد',
      'repentance_conditions':r'ندم|اقلاع|عزم|شرط|شروط|نصوح',
      'disagreement':r'تعفو|عليك|يجب|ينبغي|كظم|لا تغضب|اللين من القول|احفظ|حفظ اللسان|لا تخاصم|التجاوز|الكلمه الطيبه',
      'interrupted_practice':r'يرجع|ارجع|يعود|استغفار',
      'fawatih_connection':r'بحضرتهم|توصيل|اتصال|تجعلك|حضور|صلة|المشائخ|المشايخ',
      'sincerity':r'رياء|اخلاص|لله|حظوظ'}
    if not all(re.search(cues[g],norm) for g in groups if g in cues):return None
    spans=sorted((m.start(),m.end(),g) for g,ms in events.items() for m in ms[:32]);best=None
    for i,(start,end,g) in enumerate(spans):
        local=[x for x in spans[i:] if x[0]<start+650]
        if set(groups)-{x[2] for x in local}:continue
        stop=max(next(x[1] for x in local if x[2]==key) for key in groups)
        candidate=(stop-start,start,stop)
        if best is None or candidate<best:best=candidate
    if best is None:return None
    _,start,end=best
    stop=re.search(r'[.!؟]\s',text[end:min(len(text),end+260)])
    end=min(len(text),end+(stop.end() if stop else 180))
    if groups==['love_affection','prophet_names'] and not (re.search(r'محمد|النبي|الرسول',norm) and re.search(r'حب|محبه|يحب',norm)):return None
    if groups==['repentance_conditions']:
        if not re.search(r'توب',norm):return None
        conditions=sum(bool(re.search(c,norm)) for c in (r'ندم',r'اقلاع|ترك.*(?:ذنب|معاصي|زله)',r'عزم|لا يعود'))
        if conditions<2:return None
    if groups==['disciple_sincerity'] and not re.search(r'صدق|صادق',norm):return None
    score=.88
    if groups==['disagreement']:score=.97
    if groups==['fear','hope'] and re.search(r'اصناف|اربعه|الترهيب.*الترغيب',norm):score=.97
    if groups==['love_affection','prophet_names'] and re.search(r'ينال|شفا?عه|يحشر|حشر|اجر|ثواب',norm):score=.97
    if groups==['heart_dhikr','commerce'] and re.search(r'لا تلهيهم|تجاره ولا بيع',norm):score=.97
    if groups==['seclusion'] and re.search(r'اغنت عن|مافيش خلوه',norm):score=.98
    if groups==['disciple_sincerity'] and re.search(r'علامة|علامات',text[max(0,start-70):end]):score=.98
    elif groups==['repentance_conditions'] and re.search(r'الإقلاع|الندم|العزم',text):score=.97
    elif groups==['interrupted_practice'] and re.search(r'يرجع\s+للاسم',text):score=.98
    elif groups==['fawatih_connection'] and re.search(r'توصيل|بحضرتهم|حضور دائم|تجعلك',text):score=.97
    return score,start,end,groups
