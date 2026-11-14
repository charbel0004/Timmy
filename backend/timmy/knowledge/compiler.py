"""Bounded, Git-pinned Markdown/frontmatter -> deterministic approved manifest."""
import hashlib
import json
import os
import re
import subprocess
import unicodedata
from datetime import datetime
from pathlib import Path

import yaml
from yaml.tokens import AnchorToken,AliasToken,TagToken
from pydantic import ValidationError
from .contracts import Node,Approval
from .bindings import BINDING_REVISION,binding_manifest

MAX_FILES=512
MAX_FILE_BYTES=32768
MAX_METADATA_BYTES=16384
MAX_VAULT_BYTES=2*1024*1024
MAX_EDGES=4096
FOLDERS={'FACT':'facts','RULE':'rules','STEP':'steps','PROCEDURE':'procedures','ACTION':'actions','CONCEPT':'concepts','SOURCE':'sources'}
NORMALIZER_VERSION='nfkc-casefold-ar-diacritics-v1'
RELATIONS={
 'defines':({'FACT','RULE','CONCEPT'},{'CONCEPT'}),
 'requires':({'ACTION','PROCEDURE','STEP','RULE'},{'FACT','RULE','CONCEPT','SOURCE','PROCEDURE'}),
 'validated_by':({'FACT','STEP'},{'RULE'}), 'uses_rule':({'STEP'},{'RULE'}),
 'uses_source':({'STEP','RULE','FACT'},{'SOURCE'}), 'invokes':({'ACTION'},{'PROCEDURE'}),
 'steps':({'PROCEDURE'},{'STEP'}),'follows':({'STEP'},{'STEP'}),
 'produces':({'STEP'},{'FACT','CONCEPT'}),'supersedes':(set(FOLDERS),set(FOLDERS))}


class CompileError(ValueError):pass


def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')
def digest(data):return hashlib.sha256(data).hexdigest()


class UniqueLoader(yaml.SafeLoader):pass
UniqueLoader.yaml_implicit_resolvers={k:[pair for pair in v if pair[0]!='tag:yaml.org,2002:timestamp']
                                     for k,v in yaml.SafeLoader.yaml_implicit_resolvers.items()}


def unique_mapping(loader,node,deep=False):
    result={}
    for key_node,value_node in node.value:
        key=loader.construct_object(key_node,deep=deep)
        if not isinstance(key,str) or key in result:raise CompileError('Duplicate or non-string YAML key')
        result[key]=loader.construct_object(value_node,deep=deep)
    return result
UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,unique_mapping)


def normalize_alias(value):
    text=unicodedata.normalize('NFKC',value).casefold()
    text=re.sub(r'[\u0640\u064b-\u065f\u0670]','',text)
    return ' '.join(text.split())


def _git(root,*args):
    try:return subprocess.run(['git','-C',str(root),*args],check=True,capture_output=True,timeout=10).stdout
    except (subprocess.SubprocessError,OSError):raise CompileError('Git source commit unavailable or unreadable') from None


def read_sources(repo_root,vault,git_sha):
    repo=Path(repo_root).resolve();raw=Path(vault)
    if '..' in raw.parts:raise CompileError('Vault traversal path is not allowed')
    raw=raw if raw.is_absolute() else repo/raw
    if raw.is_symlink():raise CompileError('Symlink vault is not allowed')
    root=raw.resolve()
    if not root.is_relative_to(repo) or root==repo:raise CompileError('Vault must be a real subdirectory of Git root')
    parent=raw
    while parent!=repo and parent!=parent.parent:
        if parent.is_symlink():raise CompileError('Symlink source path is not allowed')
        parent=parent.parent
    rel=root.relative_to(repo).as_posix()
    tracked=_git(repo,'ls-tree','-r','-z',git_sha,'--',rel).split(b'\0')
    committed={}
    for line in tracked:
        if not line:continue
        if len(committed)>=MAX_FILES:raise CompileError('Committed source count limit')
        metadata,name=line.split(b'\t',1);mode,kind,blob=metadata.split()
        if mode!=b'100644' or kind!=b'blob':raise CompileError('Only regular non-executable tracked notes are allowed')
        name=name.decode('utf-8')
        committed[Path(name).relative_to(rel).as_posix()]=blob.decode()
    sources={};total=0
    if not root.is_dir():raise CompileError('Vault directory missing')
    directory_count=0
    for directory,dirs,files in os.walk(root,followlinks=False):
        directory_count+=1
        if directory_count>MAX_FILES:raise CompileError('Vault directory count limit')
        for name in dirs:
            if (Path(directory)/name).is_symlink():raise CompileError('Symlink directory in vault')
        for name in files:
            path=Path(directory)/name;relative=path.relative_to(root).as_posix()
            if path.is_symlink() or not path.is_file():raise CompileError(f'{relative}: regular file required')
            if not re.fullmatch(r'(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_-]+\.md',relative):raise CompileError(f'{relative}: invalid note path')
            if len(sources)>=MAX_FILES or path.stat().st_size>MAX_FILE_BYTES:raise CompileError(f'{relative}: source size/count limit')
            data=path.read_bytes();total+=len(data)
            if len(data)>MAX_FILE_BYTES or total>MAX_VAULT_BYTES:raise CompileError(f'{relative}: vault byte limit')
            if relative not in committed or int(_git(repo,'cat-file','-s',committed[relative]))>MAX_FILE_BYTES:
                raise CompileError(f'{relative}: pinned blob missing or oversized')
            if _git(repo,'cat-file','blob',committed[relative])!=data:
                raise CompileError(f'{relative}: bytes do not match pinned Git commit')
            sources[relative]=data
    if set(sources)!=set(committed):raise CompileError('Vault files differ from pinned Git tree')
    return dict(sorted(sources.items()))


def source_manifest_hash(sources):return digest(canonical({path:digest(data) for path,data in sorted(sources.items())}))


def parse_note(path,data):
    try:text=data.decode('utf-8')
    except UnicodeError:raise CompileError(f'{path}: UTF-8 note required') from None
    # A privacy linter, not proof that prose contains no PII. Human privacy review is mandatory.
    if re.search(r'-----BEGIN .*PRIVATE KEY|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|\b(?:password|api_key|payment_destination|staff_name)\s*[:=]',text,re.I):
        raise CompileError(f'{path}: sensitive payload pattern; keep private evidence outside vault')
    match=re.fullmatch(r'---\r?\n(.*?)\r?\n---\r?\n?(.*)',text,re.S)
    if not match:raise CompileError(f'{path}: bounded YAML frontmatter required')
    metadata,body=match.groups()
    if len(metadata.encode())>MAX_METADATA_BYTES:raise CompileError(f'{path}: metadata limit')
    try:
        if any(isinstance(t,(AnchorToken,AliasToken,TagToken)) for t in yaml.scan(metadata)):
            raise CompileError('YAML anchors, aliases and tags are forbidden')
        node=Node.model_validate(yaml.load(metadata,Loader=UniqueLoader))
    except (yaml.YAMLError,ValidationError,ValueError,TypeError,RecursionError):
        raise CompileError(f'{path}: invalid/duplicate frontmatter, approval, or forbidden YAML constructs') from None
    if Path(path).parent.as_posix()!=FOLDERS[node.type]:raise CompileError(f'{path}: note type/folder mismatch')
    return node,body


def validate_graph(nodes):
    by_id={n.id:n for n in nodes};edges=[];execution={key:set() for key in by_id}
    for node in nodes:
        seen=set();positions=[];steps=[];invokes=0
        for link in node.links:
            if link.target not in by_id:raise CompileError(f'{node.id}: dangling or unapproved target {link.target}')
            target=by_id[link.target];source_types,target_types=RELATIONS[link.relation]
            if node.type not in source_types or target.type not in target_types:raise CompileError(f'{node.id}: wrong-type {link.relation} edge')
            if link.relation=='supersedes' and node.type!=target.type:raise CompileError('Supersedes must keep node type')
            key=(link.relation,link.target)
            if key in seen:raise CompileError(f'{node.id}: duplicate direct edge')
            seen.add(key)
            if link.relation=='steps':positions.append(link.position);steps.append(link.target)
            if link.relation=='invokes':invokes+=1
            if link.relation in {'invokes','steps','follows','requires'}:execution[node.id].add(link.target)
            edges.append(dict(source=node.id,relation=link.relation,target=link.target,position=link.position))
            if len(edges)>MAX_EDGES:raise CompileError('Release edge bound exceeded')
        if node.type=='ACTION' and invokes!=1:raise CompileError(f'{node.id}: action must invoke exactly one procedure')
        if node.type=='PROCEDURE' and (not steps or len(set(steps))!=len(steps) or sorted(positions)!=list(range(1,len(positions)+1))):
            raise CompileError(f'{node.id}: procedure needs unique contiguous ordered steps')
        relations={link.relation for link in node.links}
        if node.type=='STEP' and (not relations.intersection({'uses_rule','validated_by'}) or 'uses_source' not in relations):
            raise CompileError(f'{node.id}: executable step needs explicit rule and source edges')
        if node.type=='RULE' and 'uses_source' not in relations:
            raise CompileError(f'{node.id}: executable rule needs explicit source edge')
    visiting=set();done=set()
    def visit(key):
        if key in visiting:raise CompileError('Execution/procedure dependency cycle')
        if key in done:return
        visiting.add(key)
        for target in sorted(execution[key]):visit(target)
        visiting.remove(key);done.add(key)
    for key in sorted(execution):visit(key)
    return sorted(edges,key=lambda e:(e['source'],e['relation'],e['position'] or 0,e['target']))


def compile_vault(repo_root,vault,approval):
    try:approval=Approval.model_validate(approval)
    except (ValidationError,ValueError):raise CompileError('Invalid release approval record') from None
    if approval.binding_revision!=BINDING_REVISION:raise CompileError('Binding/code revision mismatch')
    sources=read_sources(repo_root,vault,approval.git_sha)
    if source_manifest_hash(sources)!=approval.source_manifest_sha256:raise CompileError('Approval does not cover these exact source hashes')
    all_notes={};compiled=[]
    for path,data in sources.items():
        if path=='README.md':continue
        node,body=parse_note(path,data)
        if node.id in all_notes:raise CompileError(f'{path}: duplicate ID {node.id}')
        all_notes[node.id]=node
        if node.status!='approved':continue
        if node.approved_by not in approval.authorized_reviewers or datetime.fromisoformat(node.approved_at)>datetime.fromisoformat(approval.approved_at):
            raise CompileError(f'{path}: note approval is not covered by release review')
        payload=dict(metadata=node.model_dump(mode='json'),body=body)
        compiled.append(dict(path=path,file_sha256=digest(data),payload_sha256=digest(canonical(payload)),**payload))
    nodes=sorted((Node.model_validate(item['metadata']) for item in compiled),key=lambda n:n.id)
    if not nodes or {n.id for n in nodes}!=set(approval.approved_node_ids):raise CompileError('Approved node set does not match release approval')
    edges=validate_graph(nodes);aliases={};bindings=[]
    for node in nodes:
        if node.backend_key:
            try:binding=binding_manifest(node.backend_key)
            except ValueError:raise CompileError(f'{node.id}: backend key not in static allowlist') from None
            bindings.append(dict(node_id=node.id,**binding))
        for alias in node.aliases:
            normalized=normalize_alias(alias.text)
            if not normalized:raise CompileError('Empty normalized alias')
            key=(alias.locale,alias.scope,normalized)
            if key in aliases and aliases[key]['node_id']!=node.id:raise CompileError('Approved alias collision in locale/scope')
            aliases[key]=dict(locale=alias.locale,scope=alias.scope,normalized=normalized,node_id=node.id,normalizer_version=NORMALIZER_VERSION)
    result=dict(format_version='0.1',release_id=approval.release_id,git_sha=approval.git_sha,
                source_manifest_sha256=approval.source_manifest_sha256,approval=approval.model_dump(mode='json'),
                binding_revision=BINDING_REVISION,nodes=sorted(compiled,key=lambda n:n['metadata']['id']),edges=edges,
                aliases=[aliases[k] for k in sorted(aliases)],bindings=sorted(bindings,key=lambda b:b['node_id']))
    return dict(result,manifest_sha256=digest(canonical(result)))
