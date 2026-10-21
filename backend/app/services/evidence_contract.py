"""Shared typed source model for every search path and projection.

This validates coordinates and metadata consistency. It does not grade whether a
passage answers the user's religious question.
"""
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,ValidationInfo,model_validator

class SourceSpan(BaseModel):
    start:int=Field(ge=0)
    end:int=Field(gt=0)
    source_quote:str|None=None
    @model_validator(mode='after')
    def ordered(self):
        if self.end<=self.start:raise ValueError('Source span must be non-empty and half-open')
        return self

class SpeakerEvidence(BaseModel):
    anchor_role:Literal['unknown','question','answer','mixed']
    passage_role:Literal['unknown','question','answer','mixed']
    basis:Literal['none','structural','explicit_marker']
    name:str|None=None
    review_status:Literal['unreviewed']='unreviewed'
    segments:list[dict]=Field(default_factory=list)
    @model_validator(mode='after')
    def named_basis(self):
        if self.name and self.basis!='explicit_marker':raise ValueError('A speaker name needs an explicit source marker')
        return self

class SupportEstimate(BaseModel):
    estimate:Literal['candidate','topical']
    method:str
    calibrated:Literal[False]=False
    review_status:Literal['unreviewed']='unreviewed'

class CanonicalHit(BaseModel):
    model_config=ConfigDict(extra='allow')
    book_id:str
    seq:int=Field(ge=1)
    match_id:str=Field(pattern=r'^b\d+-p\d+-c\d+$')
    score:float=Field(ge=0,le=1)
    printed_page:str|None=None
    evidence_span:SourceSpan
    speaker_evidence:SpeakerEvidence
    support:SupportEstimate|None=None
    answer_verified:Literal[False]=False
    @model_validator(mode='after')
    def source_and_metadata(self,info:ValidationInfo):
        text=(info.context or {}).get('page_text')
        span=self.evidence_span
        if text is not None:
            if span.end>len(text):raise ValueError('Evidence outside canonical page text')
            if span.source_quote!=text[span.start:span.end]:raise ValueError('Evidence quote does not resolve to source')
        if getattr(self,'pagination_status',None)=='repeated_printed_label_unresolved' and self.printed_page is not None:
            raise ValueError('Unreliable printed page label must be absent')
        return self
