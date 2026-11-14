"""Proposed note/release contract v0.1, separate from supplied wire schemas."""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,model_validator,field_validator

NodeType=Literal['FACT','RULE','STEP','PROCEDURE','ACTION','CONCEPT','SOURCE']
Relation=Literal['defines','requires','validated_by','uses_rule','uses_source','invokes','steps','follows','produces','supersedes']
ID_PATTERN=r'^(FACT|RULE|STEP|PROC|ACTION|CONCEPT|SOURCE)-[A-Za-z0-9][A-Za-z0-9_-]{0,95}$'


class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,frozen=True)


class Alias(Strict):
    text:str=Field(min_length=1,max_length=160)
    locale:str=Field(pattern=r'^[a-z]{2}(?:-[A-Z]{2})?$')
    scope:str=Field(pattern=r'^[a-z0-9:_-]{1,80}$')


class Link(Strict):
    relation:Relation
    target:str=Field(min_length=1,max_length=110)
    position:int|None=Field(default=None,ge=1,le=256)

    @field_validator('target')
    @classmethod
    def target_id(cls,value):
        import re
        if value.startswith('[[') and value.endswith(']]'):value=value[2:-2]
        if not re.fullmatch(ID_PATTERN,value):raise ValueError('Invalid target ID')
        return value

    @model_validator(mode='after')
    def ordered(self):
        if (self.relation=='steps')!=(self.position is not None):raise ValueError('Only ordered steps have a required position')
        return self


class Node(Strict):
    id:str=Field(pattern=ID_PATTERN)
    type:NodeType
    version:str=Field(pattern=r'^[0-9]+(?:\.[0-9]+){0,2}$',max_length=32)
    status:Literal['draft','in_review','approved','deprecated']
    classification:Literal['public','internal','restricted']
    source_ref:str=Field(min_length=1,max_length=240)
    approved_by:str|None=Field(max_length=80)
    approved_at:str|None=Field(max_length=40)
    aliases:list[Alias]=Field(max_length=16)
    title:str=Field(min_length=1,max_length=160)
    description:str=Field(min_length=1,max_length=1000)
    links:list[Link]=Field(default_factory=list,max_length=64)
    backend_key:str|None=Field(default=None,max_length=80)
    contains_personal_data:Literal[False]=False

    @model_validator(mode='after')
    def authority(self):
        prefix='PROC' if self.type=='PROCEDURE' else self.type
        if not self.id.startswith(prefix+'-'):raise ValueError('Node ID/type mismatch')
        if self.status=='approved':
            if not self.approved_by or not self.approved_at:raise ValueError('Approved note needs reviewer and timestamp')
            if datetime.fromisoformat(self.approved_at).tzinfo is None:raise ValueError('Approval timestamp needs timezone')
            if self.type in {'STEP','RULE'} and not self.backend_key:raise ValueError('Executable note needs static backend_key')
        if self.type not in {'STEP','RULE'} and self.backend_key is not None:raise ValueError('Binding only belongs to step/rule')
        if self.aliases and self.type not in {'ACTION','CONCEPT'}:raise ValueError('Action/concept aliases only; never staff names')
        return self


class Approval(Strict):
    release_id:str=Field(pattern=r'^KG-[A-Za-z0-9][A-Za-z0-9_-]{0,70}$')
    git_sha:str=Field(pattern=r'^[0-9a-f]{40}$')
    source_manifest_sha256:str=Field(pattern=r'^[0-9a-f]{64}$')
    approved_node_ids:list[str]=Field(min_length=1,max_length=512)
    approved_by:str=Field(min_length=1,max_length=80)
    approved_at:str=Field(max_length=40)
    authorized_reviewers:list[str]=Field(min_length=1,max_length=16)
    privacy_reviewed:Literal[True]
    binding_revision:str=Field(min_length=1,max_length=80)
    policy_version:str=Field(min_length=1,max_length=80)

    @model_validator(mode='after')
    def checked(self):
        if self.approved_by not in self.authorized_reviewers:raise ValueError('Release reviewer not in reviewer set')
        if len(set(self.approved_node_ids))!=len(self.approved_node_ids):raise ValueError('Duplicate approved node ID')
        if datetime.fromisoformat(self.approved_at).tzinfo is None:raise ValueError('Release approval needs timezone')
        return self
