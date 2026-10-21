"""Build-time evidence features and stable canonical source units.

The index is discovery-only. Page text, literal postings, census and existing
match IDs are unchanged. Stable unit IDs supplement legacy page-offset IDs.
"""
import hashlib,json,re
from functools import lru_cache
from app.core.arabic_utils import normalize_search_text
from app.services.concept_links import CONCEPT_FORMS, normalized_forms, VERSION
INDEX_VERSION='evidence-units-1.0'
CUES={
 'definition':r'معنى|عباره عن|المراد|يعني',
 'importance':r'اهم|ضروري|لا بد|لازم|اغنت عن|مافيش|بدلا من',
 'merit':r'ثواب|اجر|ينال|يحبه|محبه|كان له|حشر|يحشر',
 'ruling':r'حرام|حلال|يجوز|لا يجوز|ممنوع|غلط|لا باس',
 'stance':r'حرام|لا يجوز|ينهي|يرفض|غلط|مافيش|بدعه',
 'comparison':r'فرق|بخلاف|بينما|اما|غير',
 'preference':r'افضل من|اعلي من|اولي|يرجح|يغلب|يقدم|يفضل',
 'remedy':r'علاج|دواء|عليك|فعليه|لازم|كظم|لا تغضب|تعفو|الصفح|التسامح|اللين|اللين من القول',
 'method':r'بان|عن طريق|يداوم|يعمل|يرجع|يقرا|عليك|حافظ',
 'coexistence':r'لا تلهيهم|وهو|مع|بينما|في نفس الوقت|التجاره والبيع',
 'signs':r'علامه|علامات|من علامات|دليل|يعرف',
 'condition':r'شرط|شروط|بشرط|لا بد|الا اذا|يكفي|الاقلاع|الندم|العزم|يرجع للاسم',
 'cause':r'لان|عشان|علشان|بسبب|لكي',
 'timing':r'اذا|لما|حين|بعد ان|متي',
 'identity':r'وظيفته|دوره|يقوم|القطب|الغوث',
 'relation':r'يوصل|توصيل|تجعلك|بحضرتهم|حضور دائم|علاقه|صله|اتصال',
 'stages':r'الاول|الثاني|المرتبه|سبعه|ثلاثه|درجات|اربعه',
}
@lru_cache(maxsize=128)
def _norm_pattern(group):
    return re.compile(r'(?<![ء-ي])(?:و|ف|ب|ل)?(?:'+ '|'.join(re.escape(x) for x in normalized_forms(group))+r')(?![ء-ي])')

def features(text):
    norm=normalize_search_text(text,level='broad')
    return {'concepts':[g for g in CONCEPT_FORMS if _norm_pattern(g).search(norm)],
            'cues':[g for g,p in CUES.items() if re.search(p,norm)],
            'corrective':bool(re.search(r'اغنت عن|مافيش|بدلا من|الغي|لغ[يى]',norm)),
            'chars':len(text)}

def build_evidence_units(conn):
    conn.execute('DROP TABLE IF EXISTS evidence_units')
    conn.execute('CREATE TABLE evidence_units(id INTEGER PRIMARY KEY,unit_id TEXT UNIQUE,page_id INTEGER,start_char INTEGER,end_char INTEGER,kind TEXT,question TEXT,features TEXT,text_sha256 TEXT)')
    conn.execute('CREATE INDEX idx_evidence_unit_page ON evidence_units(page_id,start_char)')
    conn.execute('DROP TABLE IF EXISTS evidence_concepts')
    conn.execute('CREATE TABLE evidence_concepts(concept TEXT,unit_id INTEGER,PRIMARY KEY(concept,unit_id))')
    pages=dict(conn.execute('SELECT id,text FROM pages'))
    rows=conn.execute('SELECT id,page_id,start_char,end_char,question,kind FROM discovery_passages').fetchall()
    for uid,pid,start,end,q,kind in rows:
        text=pages[pid];quote=text[start:end]
        if not 0<=start<end<=len(text):raise ValueError('Evidence unit outside source page')
        f=features(quote)
        # Structural links use source coordinates. No answer author is inferred.
        headings=list(re.finditer(r'(?:^|\n\n)\s*\(\d+\)\s+[^\n]{1,100}:[-]?',text))
        prior=[h for h in headings if h.start()<=start]
        if prior:
            h=prior[-1];following=next((x for x in headings if x.start()>h.start()),None)
            f['heading_span']={'start':h.start(),'end':h.end()}
            f['section_span']={'start':h.start(),'end':following.start() if following else len(text)}
        sha=hashlib.sha256(quote.encode()).hexdigest()
        stable=f'u{pid}-{start}-{end}-{sha[:12]}'
        conn.execute('INSERT INTO evidence_units VALUES(?,?,?,?,?,?,?,?,?)',(uid,stable,pid,start,end,kind,q,json.dumps(f,ensure_ascii=False),sha))
        conn.executemany('INSERT INTO evidence_concepts VALUES(?,?)',[(g,uid) for g in f['concepts']])
    conn.executemany('INSERT OR REPLACE INTO discovery_meta VALUES(?,?)',[('index_version',INDEX_VERSION),('lexicon_version',VERSION)])
    return {'units':len(rows),'index_version':INDEX_VERSION,'lexicon_version':VERSION}
