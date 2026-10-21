"""One canonical source/evidence contract before compact or alias projection."""
from app.core.coordinates import source_span,coordinate_contract
from app.core.attribution import speaker_span,attribution_at

def canonical_hit(row,page):
    text=page['text'];span=row.get('evidence_span')
    if span:
        start,end=int(span['start']),int(span['end'])
        row['evidence_span']=source_span(text,start,end)
        row['text_version']=coordinate_contract(text)['text_version']
        # Speaker interpretation belongs to this precise source span. Excerpt
        # context and page authorship are separate scopes.
        row.update(speaker_span(text,start,end))
        legacy=attribution_at(text,start,end)
        if legacy.get('reported_view'):row.update(legacy)
        segments=row.get('speaker_segments') or []
        role=row.get('dialogue_role','unknown');speaker=row.get('speaker')
        if role=='mixed' and segments:
            anchor=next((s for s in segments if s['start']<=start<s['end']),segments[0])
            anchor_role=anchor['role']
        else:anchor_role=role
        if role in ('question','answer','mixed') and row.get('source_role')!='reported_view':
            row['source_role']=role
        basis='explicit_marker' if speaker not in (None,'mixed') else 'structural' if role!='unknown' else 'none'
        row['speaker_evidence']={'anchor_role':anchor_role,'passage_role':role,
                                  'basis':basis,'review_status':'unreviewed'}
        if speaker not in (None,'mixed'):row['speaker_evidence']['name']=speaker
        if segments:row['speaker_evidence']['segments']=segments
        if not speaker and row.get('speaker_basis')=='explicit_marker':row['speaker_basis']='structural'
    if row.get('pagination_status')=='repeated_printed_label_unresolved':
        # Unreliable labels remain only in the source/review files. The public
        # citation and machine identity already use the sequence.
        row['printed_page']=None
    row.setdefault('answer_verified',False)
    if row.get('question_relevance'):
        row['support']={'estimate':'candidate' if row['question_relevance']!='topic_only' else 'topical',
                        'method':'source_local_rules_v1','calibrated':False,'review_status':'unreviewed'}
    from app.services.evidence_contract import CanonicalHit
    CanonicalHit.model_validate(row,context={'page_text':text})
    return row
