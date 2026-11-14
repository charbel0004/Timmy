"""Immutable release artifacts; no application activation or workflow runner.

Operator-only publish/activate helpers are not registered as model or HTTP tools.
A later scoped graph service must authorize every access before using this reader.
"""
import fcntl
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import re
from datetime import datetime

from .compiler import canonical,digest,validate_graph,CompileError,NORMALIZER_VERSION,MAX_FILE_BYTES,FOLDERS
from .contracts import Approval,Node
from .bindings import BINDING_REVISION,binding_manifest

SCHEMA='''
CREATE TABLE kg_releases(release_id TEXT PRIMARY KEY,git_sha TEXT NOT NULL,manifest_sha256 TEXT NOT NULL,approval_json TEXT NOT NULL);
CREATE TABLE kg_nodes(release_id TEXT NOT NULL,node_id TEXT NOT NULL,type TEXT NOT NULL,version TEXT NOT NULL,
 classification TEXT NOT NULL,source_ref TEXT NOT NULL,path TEXT NOT NULL,file_sha256 TEXT NOT NULL,payload_sha256 TEXT NOT NULL,payload_json TEXT NOT NULL,
 PRIMARY KEY(release_id,node_id),FOREIGN KEY(release_id) REFERENCES kg_releases(release_id));
CREATE TABLE kg_edges(release_id TEXT NOT NULL,source TEXT NOT NULL,relation TEXT NOT NULL,target TEXT NOT NULL,position INTEGER,
 PRIMARY KEY(release_id,source,relation,target),UNIQUE(release_id,source,relation,position),
 FOREIGN KEY(release_id,source) REFERENCES kg_nodes(release_id,node_id),FOREIGN KEY(release_id,target) REFERENCES kg_nodes(release_id,node_id));
CREATE TABLE kg_aliases(release_id TEXT NOT NULL,locale TEXT NOT NULL,scope TEXT NOT NULL,normalized TEXT NOT NULL,node_id TEXT NOT NULL,normalizer_version TEXT NOT NULL,
 PRIMARY KEY(release_id,locale,scope,normalized),FOREIGN KEY(release_id,node_id) REFERENCES kg_nodes(release_id,node_id));
CREATE TABLE kg_bindings(release_id TEXT NOT NULL,node_id TEXT NOT NULL,key TEXT NOT NULL,contract_version TEXT NOT NULL,binding_revision TEXT NOT NULL,code_sha256 TEXT NOT NULL,
 PRIMARY KEY(release_id,node_id),FOREIGN KEY(release_id,node_id) REFERENCES kg_nodes(release_id,node_id));
'''


def validate_manifest(manifest,require_current_bindings=True):
    expected={'format_version','release_id','git_sha','source_manifest_sha256','approval','binding_revision','nodes','edges','aliases','bindings','manifest_sha256'}
    if not isinstance(manifest,dict) or set(manifest)!=expected:raise CompileError('Unexpected manifest fields')
    body={k:v for k,v in manifest.items() if k!='manifest_sha256'}
    if digest(canonical(body))!=manifest['manifest_sha256']:raise CompileError('Manifest digest mismatch')
    approval=Approval.model_validate(manifest['approval'])
    if (manifest['format_version']!='0.1' or manifest['release_id']!=approval.release_id or manifest['git_sha']!=approval.git_sha
        or manifest['source_manifest_sha256']!=approval.source_manifest_sha256 or manifest['binding_revision']!=approval.binding_revision):
        raise CompileError('Release metadata does not match approval')
    if not isinstance(manifest['nodes'],list) or not 1<=len(manifest['nodes'])<=512:raise CompileError('Invalid release node bound')
    nodes=[]
    for item in manifest['nodes']:
        if set(item)!={'path','file_sha256','payload_sha256','metadata','body'}:raise CompileError('Unexpected node payload')
        node=Node.model_validate(item['metadata'])
        if node.status!='approved':raise CompileError('Unapproved node in runtime manifest')
        if (node.approved_by not in approval.authorized_reviewers or
            datetime.fromisoformat(node.approved_at)>datetime.fromisoformat(approval.approved_at)):
            raise CompileError('Node approval not covered by release review')
        if (not isinstance(item['path'],str) or not re.fullmatch(r'[A-Za-z0-9_-]+/[A-Za-z0-9_-]+\.md',item['path'])
            or Path(item['path']).parent.as_posix()!=FOLDERS[node.type]
            or not isinstance(item['body'],str) or len(item['body'].encode())>MAX_FILE_BYTES
            or not isinstance(item['file_sha256'],str) or not re.fullmatch(r'[0-9a-f]{64}',item['file_sha256'])):
            raise CompileError('Invalid node source path/hash/size')
        if digest(canonical(dict(metadata=item['metadata'],body=item['body'])))!=item['payload_sha256']:raise CompileError('Node payload mismatch')
        nodes.append(node)
    if (len({n.id for n in nodes})!=len(nodes) or len({n['path'] for n in manifest['nodes']})!=len(nodes)
        or {n.id for n in nodes}!=set(approval.approved_node_ids)):raise CompileError('Invalid approved node set')
    if validate_graph(nodes)!=manifest['edges']:raise CompileError('Manifest edges differ from reviewed node metadata')
    if require_current_bindings:
        if manifest['binding_revision']!=BINDING_REVISION:raise CompileError('Unavailable binding revision')
        expected_bindings=[dict(node_id=n.id,**binding_manifest(n.backend_key)) for n in sorted(nodes,key=lambda n:n.id) if n.backend_key]
        if expected_bindings!=manifest['bindings']:raise CompileError('Binding code/contract hash mismatch')
    # Do not trust an edited alias projection merely because a caller rehashed JSON.
    from .compiler import normalize_alias
    expected_aliases={}
    for node in nodes:
        for alias in node.aliases:
            key=(alias.locale,alias.scope,normalize_alias(alias.text))
            if not key[2]:raise CompileError('Empty normalized alias')
            if key in expected_aliases and expected_aliases[key]['node_id']!=node.id:raise CompileError('Alias collision')
            expected_aliases[key]=dict(locale=key[0],scope=key[1],normalized=key[2],node_id=node.id,normalizer_version=NORMALIZER_VERSION)
    if [expected_aliases[k] for k in sorted(expected_aliases)]!=manifest['aliases']:raise CompileError('Alias projection mismatch')
    return approval


def _json_file(path,max_bytes=4*1024*1024):
    if path.is_symlink() or path.stat().st_size>max_bytes:raise CompileError('Artifact path/size invalid')
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise CompileError('Duplicate JSON field')
            result[key]=value
        return result
    return json.loads(path.read_text(),object_pairs_hook=unique)


class GraphRelease:
    """Pinned local definition reader. No live vault reads and no policy mutation."""
    def __init__(self,path,expected_manifest_sha256):
        self.path=Path(path)
        if self.path.is_symlink():raise CompileError('Symlink release rejected')
        self.manifest=_json_file(self.path/'manifest.json')
        if self.manifest['manifest_sha256']!=expected_manifest_sha256:raise CompileError('Pinned manifest mismatch')
        validate_manifest(self.manifest,require_current_bindings=False)
        dbfile=self.path/'knowledge.sqlite'
        if dbfile.is_symlink() or dbfile.stat().st_size>8*1024*1024:raise CompileError('Invalid SQLite artifact')
        self.connection=sqlite3.connect(dbfile.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
        try:
            self.connection.execute('PRAGMA foreign_keys=ON');self.connection.execute('PRAGMA query_only=ON')
            if self.connection.execute('PRAGMA integrity_check').fetchone()!=('ok',):raise CompileError('SQLite integrity failure')
            if self.connection.execute('PRAGMA foreign_key_check').fetchall():raise CompileError('SQLite release FK failure')
            self._verify_projection()
            self.connection.set_authorizer(self._readonly)
        except Exception:
            self.connection.close();raise

    @staticmethod
    def _readonly(action,first,second,*unused):
        if action in {sqlite3.SQLITE_SELECT,sqlite3.SQLITE_READ}:return sqlite3.SQLITE_OK
        if action==sqlite3.SQLITE_FUNCTION and second not in {'load_extension','readfile','writefile'}:return sqlite3.SQLITE_OK
        if action==sqlite3.SQLITE_PRAGMA and first in {'foreign_keys','query_only'} and second is None:return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY

    def _verify_projection(self):
        db=self.connection;m=self.manifest;rid=m['release_id']
        names={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if names!={'kg_releases','kg_nodes','kg_edges','kg_aliases','kg_bindings'}:raise CompileError('Unexpected projection schema')
        rows=db.execute('SELECT release_id,git_sha,manifest_sha256,approval_json FROM kg_releases').fetchall()
        if rows!=[(rid,m['git_sha'],m['manifest_sha256'],canonical(m['approval']).decode())]:raise CompileError('SQLite release metadata mismatch')
        stored=db.execute('SELECT node_id,type,version,classification,source_ref,path,file_sha256,payload_sha256,payload_json FROM kg_nodes WHERE release_id=? ORDER BY node_id',(rid,)).fetchall()
        expected=[]
        for item in m['nodes']:
            n=item['metadata'];expected.append((n['id'],n['type'],n['version'],n['classification'],n['source_ref'],item['path'],item['file_sha256'],item['payload_sha256'],canonical(dict(metadata=n,body=item['body'])).decode()))
        if stored!=sorted(expected):raise CompileError('SQLite semantic payload differs from approved manifest')
        for table,columns,keys in [('kg_edges','source,relation,target,position',['source','relation','target','position']),
                                  ('kg_aliases','locale,scope,normalized,node_id,normalizer_version',['locale','scope','normalized','node_id','normalizer_version']),
                                  ('kg_bindings','node_id,key,contract_version,binding_revision,code_sha256',['node_id','key','contract_version','binding_revision','code_sha256'])]:
            actual=db.execute(f'SELECT {columns} FROM {table} WHERE release_id=?',(rid,)).fetchall()
            wanted=[tuple(item[k] for k in keys) for item in m[table.removeprefix('kg_')]]
            if sorted(actual,key=repr)!=sorted(wanted,key=repr):raise CompileError(f'{table}: projection mismatch')

    def node(self,node_id):
        row=self.connection.execute('SELECT payload_json FROM kg_nodes WHERE release_id=? AND node_id=?',(self.manifest['release_id'],node_id)).fetchone()
        if not row:raise KeyError('Node unavailable in pinned release')
        return json.loads(row[0])

    def neighbors(self,node_id,*,depth=1,max_neighbors=20,max_bytes=12288):
        if type(depth) is not int or depth!=1:raise ValueError('Exactly one hop is permitted')
        if type(max_neighbors) is not int or not 1<=max_neighbors<=20 or type(max_bytes) is not int or not 1<=max_bytes<=12288:raise ValueError('Invalid graph query bound')
        self.node(node_id)
        edges=[dict(source=node_id,relation=r[0],target=r[1],position=r[2]) for r in self.connection.execute(
            'SELECT relation,target,position FROM kg_edges WHERE release_id=? AND source=? ORDER BY relation,position,target LIMIT 21',
            (self.manifest['release_id'],node_id))]
        if len(edges)>max_neighbors:raise ValueError('Neighbor bound exceeded; no mandatory links truncated')
        result=dict(release_id=self.manifest['release_id'],seed_node_id=node_id,depth=1,edges=edges,
                    nodes={key:self.node(key) for key in sorted({e['target'] for e in edges})})
        if len(canonical(result))>max_bytes:raise ValueError('Knowledge byte budget exceeded')
        return result

    def close(self):self.connection.close()
    def __enter__(self):return self
    def __exit__(self,*args):self.close()


def publish_release(store,manifest):
    """Transactional complete projection, then atomic immutable-directory publication."""
    validate_manifest(manifest)
    base=Path(store);base.mkdir(parents=True,exist_ok=True)
    if base.is_symlink():raise CompileError('Symlink artifact store rejected')
    final=base/manifest['release_id']
    if final.exists():
        with GraphRelease(final,manifest['manifest_sha256']):pass
        return final
    with tempfile.TemporaryDirectory(prefix='.staging-',dir=base) as temporary:
        stage=Path(temporary);db=sqlite3.connect(stage/'knowledge.sqlite')
        try:
            db.execute('PRAGMA foreign_keys=ON')
            db.executescript(SCHEMA)
            with db:
                rid=manifest['release_id']
                db.execute('INSERT INTO kg_releases VALUES(?,?,?,?)',(rid,manifest['git_sha'],manifest['manifest_sha256'],canonical(manifest['approval']).decode()))
                for item in manifest['nodes']:
                    n=item['metadata'];db.execute('INSERT INTO kg_nodes VALUES(?,?,?,?,?,?,?,?,?,?)',
                        (rid,n['id'],n['type'],n['version'],n['classification'],n['source_ref'],item['path'],item['file_sha256'],item['payload_sha256'],canonical(dict(metadata=n,body=item['body'])).decode()))
                db.executemany('INSERT INTO kg_edges VALUES(?,?,?,?,?)',[(rid,e['source'],e['relation'],e['target'],e['position']) for e in manifest['edges']])
                db.executemany('INSERT INTO kg_aliases VALUES(?,?,?,?,?,?)',[(rid,a['locale'],a['scope'],a['normalized'],a['node_id'],a['normalizer_version']) for a in manifest['aliases']])
                db.executemany('INSERT INTO kg_bindings VALUES(?,?,?,?,?,?)',[(rid,b['node_id'],b['key'],b['contract_version'],b['binding_revision'],b['code_sha256']) for b in manifest['bindings']])
                if db.execute('PRAGMA foreign_key_check').fetchall():raise CompileError('Incomplete projection')
        finally:db.close()
        (stage/'manifest.json').write_bytes(canonical(manifest))
        with GraphRelease(stage,manifest['manifest_sha256']):pass
        for path in stage.iterdir():
            with path.open('rb') as stream:os.fsync(stream.fileno())
            path.chmod(0o444)
        stage_fd=os.open(stage,os.O_RDONLY)
        try:os.fsync(stage_fd)
        finally:os.close(stage_fd)
        # A release ID is immutable; serialize publication/activation among operators.
        with (base/'.operator.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            if final.exists():
                with GraphRelease(final,manifest['manifest_sha256']):pass
            else:os.rename(stage,final)
        directory_fd=os.open(base,os.O_RDONLY)
        try:os.fsync(directory_fd)
        finally:os.close(directory_fd)
    return final


def activate_release(store,release_id,expected_manifest_sha256):
    """Operator/library boundary only; tests use it on disposable stores.

    No application setting or user/Qwen endpoint consumes this pointer in S1.
    It is not proof of NK approval; deployment must supply a trusted approved pin.
    """
    if not isinstance(release_id,str) or not release_id.startswith('KG-') or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in release_id):raise CompileError('Invalid release path')
    base=Path(store)
    if base.is_symlink():raise CompileError('Symlink store rejected')
    with GraphRelease(base/release_id,expected_manifest_sha256) as snapshot:
        validate_manifest(snapshot.manifest)
    pointer=canonical(dict(release_id=release_id,manifest_sha256=expected_manifest_sha256))
    with (base/'.operator.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        fd,name=tempfile.mkstemp(prefix='.active-',dir=base)
        try:
            with os.fdopen(fd,'wb') as stream:stream.write(pointer);stream.flush();os.fsync(stream.fileno())
            os.replace(name,base/'active.json')
            directory_fd=os.open(base,os.O_RDONLY)
            try:os.fsync(directory_fd)
            finally:os.close(directory_fd)
        finally:
            if os.path.exists(name):os.unlink(name)
