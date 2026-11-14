"""Synthetic approval records only. No app settings, operational DB or real vault."""
import copy
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest
import yaml

from timmy.knowledge.bindings import BINDING_REVISION
from timmy.knowledge.compiler import (
    CompileError, canonical, compile_vault, digest, normalize_alias, parse_note,
    read_sources, source_manifest_hash,
)
from timmy.knowledge.repository import (
    GraphRelease, SCHEMA, activate_release, publish_release, validate_manifest,
)

STAMP = '2026-11-14T00:00:00+00:00'
FOLDERS = {'FACT': 'facts', 'RULE': 'rules', 'STEP': 'steps', 'PROCEDURE': 'procedures',
           'ACTION': 'actions', 'CONCEPT': 'concepts', 'SOURCE': 'sources'}


def note(node_id='FACT-example', kind='FACT', **changes):
    value = dict(id=node_id, type=kind, version='1.0', status='approved',
                 classification='internal', source_ref='SYNTHETIC-POLICY-1',
                 approved_by='TEST_REVIEWER', approved_at=STAMP, aliases=[],
                 title='Synthetic definition', description='Not approved operational knowledge.')
    if kind == 'RULE':
        value['links'] = [dict(relation='uses_source', target='SOURCE-policy')]
    if kind == 'STEP':
        value['links'] = [dict(relation='uses_rule', target='RULE-coverage'),
                          dict(relation='uses_source', target='SOURCE-policy')]
    value.update(changes)
    return value


def encoded(value, body='Synthetic evidence-free definition.\n'):
    return ('---\n' + yaml.safe_dump(value, sort_keys=True, allow_unicode=True) + '---\n' + body).encode()


def git(root, *args):
    return subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True).stdout.decode().strip()


class Vault:
    def __init__(self, root):
        self.root = root
        root.mkdir()
        git(root, 'init', '-q')
        git(root, 'config', 'user.name', 'Synthetic Compiler Test')
        git(root, 'config', 'user.email', 'synthetic@example.invalid')

    def write(self, value, *, filename=None, body='Synthetic definition.\n'):
        path = self.root / 'vault' / FOLDERS[value['type']] / (filename or value['id'] + '.md')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(encoded(value, body))
        return path

    def approve(self, release='KG-synthetic-1'):
        git(self.root, 'add', 'vault')
        git(self.root, 'commit', '-qm', 'Synthetic fixture', '--allow-empty')
        sha = git(self.root, 'rev-parse', 'HEAD')
        sources = read_sources(self.root, 'vault', sha)
        ids = [parse_note(path, data)[0].id for path, data in sources.items()
               if path != 'README.md' and parse_note(path, data)[0].status == 'approved']
        return dict(release_id=release, git_sha=sha, source_manifest_sha256=source_manifest_hash(sources),
                    approved_node_ids=ids, approved_by='TEST_REVIEWER', approved_at=STAMP,
                    authorized_reviewers=['TEST_REVIEWER'], privacy_reviewed=True,
                    binding_revision=BINDING_REVISION, policy_version='SYNTHETIC-NOT-OPERATIONAL')

    def compile(self, approval):
        return compile_vault(self.root, 'vault', approval)


@pytest.fixture
def vault(tmp_path):
    return Vault(tmp_path / 'repo')


def linked(vault):
    for value in [
        note('SOURCE-policy', 'SOURCE'),
        note('RULE-coverage', 'RULE', backend_key='session.coverage'),
        note('STEP-coverage', 'STEP', backend_key='session.coverage', links=[
            dict(relation='uses_rule', target='[[RULE-coverage]]'),
            dict(relation='uses_source', target='SOURCE-policy')]),
        note('PROC-check', 'PROCEDURE', links=[dict(relation='steps', target='STEP-coverage', position=1)]),
        note('ACTION-analyze', 'ACTION', links=[dict(relation='invokes', target='PROC-check')], aliases=[
            dict(text='Analyze', locale='en', scope='account'),
            dict(text='تَحْلِيل', locale='ar', scope='account')]),
    ]:
        vault.write(value)
    return vault.approve()


def rehash(manifest):
    manifest['manifest_sha256'] = digest(canonical({k: v for k, v in manifest.items() if k != 'manifest_sha256'}))
    return manifest


def test_KG_01_exact_fact_and_KG_10_deterministic_manifest(vault, tmp_path):
    path = vault.write(note())
    approval = vault.approve()
    manifest = vault.compile(approval)
    assert manifest == vault.compile(approval)
    assert len(manifest['nodes']) == 1
    item = manifest['nodes'][0]
    assert item['metadata']['id'] == 'FACT-example'
    assert item['metadata']['version'] == '1.0'
    assert item['metadata']['source_ref'] == 'SYNTHETIC-POLICY-1'
    assert item['file_sha256'] == digest(path.read_bytes())
    release = publish_release(tmp_path / 'releases', manifest)
    assert (release / 'manifest.json').read_bytes() == canonical(manifest)
    with GraphRelease(release, manifest['manifest_sha256']) as snapshot:
        assert snapshot.node('FACT-example')['metadata'] == item['metadata']
        assert snapshot.connection.execute('PRAGMA foreign_keys').fetchone() == (1,)
    assert publish_release(tmp_path / 'releases', manifest) == release


@pytest.mark.parametrize('extra', ['id: FACT-other\n', 'extra: &anchor value\n',
                                  'extra: !!python/object:os.system {}\n',
                                  'extra: *unknown\n', 'extra: !!str harmless\n'])
def test_KG_02_forbidden_yaml_reports_path(extra):
    payload = encoded(note()).replace(b'---\n', ('---\n' + extra).encode(), 1)
    with pytest.raises(CompileError, match='facts/example.md:'):
        parse_note('facts/example.md', payload)


def test_KG_03_duplicate_ids(vault):
    vault.write(note())
    vault.write(note(), filename='duplicate.md')
    approval = vault.approve()
    approval['approved_node_ids'] = ['FACT-example']
    with pytest.raises(CompileError, match='duplicate ID'):
        vault.compile(approval)


@pytest.mark.parametrize('links,reason', [
    ([dict(relation='validated_by', target='[[RULE-missing]]')], 'dangling'),
    ([dict(relation='invokes', target='RULE-present')], 'wrong-type'),
])
def test_KG_04_05_dangling_and_wrong_type(vault, links, reason):
    vault.write(note(links=links))
    vault.write(note('RULE-present', 'RULE', backend_key='session.coverage'))
    vault.write(note('SOURCE-policy', 'SOURCE'))
    with pytest.raises(CompileError, match=reason):
        vault.compile(vault.approve())


@pytest.mark.parametrize('case', ['duplicate', 'positions', 'cycle'])
def test_KG_06_ordered_steps_and_cycles(vault, case):
    links = [dict(relation='steps', target='STEP-one', position=1)]
    if case == 'duplicate':
        links.append(dict(relation='steps', target='STEP-one', position=2))
    if case == 'positions':
        links.append(dict(relation='steps', target='STEP-two', position=1))
    vault.write(note('PROC-test', 'PROCEDURE', links=links))
    vault.write(note('SOURCE-policy', 'SOURCE'))
    vault.write(note('RULE-coverage', 'RULE', backend_key='session.coverage'))
    vault.write(note('STEP-one', 'STEP', backend_key='session.coverage',
                     links=note('STEP-one', 'STEP')['links'] +
                     ([dict(relation='requires', target='PROC-test')] if case == 'cycle' else [])))
    vault.write(note('STEP-two', 'STEP', backend_key='session.coverage'))
    with pytest.raises(CompileError, match='duplicate|ordered|cycle'):
        vault.compile(vault.approve())


@pytest.mark.parametrize('key', ['os.system', 'DELETE FROM activities', '__import__("os")'])
def test_KG_07_unknown_binding_never_executes(vault, key):
    vault.write(note('SOURCE-policy', 'SOURCE'))
    vault.write(note('RULE-unsafe', 'RULE', backend_key=key))
    with pytest.raises(CompileError, match='static allowlist'):
        vault.compile(vault.approve())


@pytest.mark.parametrize('status', ['draft', 'in_review', 'deprecated'])
def test_KG_08_only_approved_nodes_retrievable(vault, tmp_path, status):
    vault.write(note())
    vault.write(note('FACT-hidden', status=status, approved_by=None, approved_at=None))
    manifest = vault.compile(vault.approve())
    assert [n['metadata']['id'] for n in manifest['nodes']] == ['FACT-example']
    with GraphRelease(publish_release(tmp_path / 'releases', manifest), manifest['manifest_sha256']) as snapshot:
        with pytest.raises(KeyError):
            snapshot.node('FACT-hidden')


def test_approved_link_cannot_promote_draft(vault):
    vault.write(note('RULE-draft', 'RULE', status='draft', backend_key='session.coverage'))
    vault.write(note(links=[dict(relation='validated_by', target='RULE-draft')]))
    with pytest.raises(CompileError, match='unapproved target'):
        vault.compile(vault.approve())


def test_KG_09_alias_collision(vault):
    alias = dict(text='Analyze', locale='en', scope='account')
    vault.write(note('CONCEPT-one', 'CONCEPT', aliases=[alias]))
    vault.write(note('CONCEPT-two', 'CONCEPT', aliases=[dict(alias, text='  ANALYZE ')]))
    with pytest.raises(CompileError, match='alias collision'):
        vault.compile(vault.approve())


def test_KG_11_failed_candidate_keeps_active_and_old_snapshot(vault, tmp_path, monkeypatch):
    vault.write(note())
    manifest = vault.compile(vault.approve())
    store = tmp_path / 'releases'
    path = publish_release(store, manifest)
    activate_release(store, manifest['release_id'], manifest['manifest_sha256'])
    before = (store / 'active.json').read_bytes()
    candidate = copy.deepcopy(manifest)
    candidate['release_id'] = candidate['approval']['release_id'] = 'KG-failed-candidate'
    rehash(candidate)
    # Simulate an incomplete staged projection: fails validation before publication.
    from timmy.knowledge import repository
    monkeypatch.setattr(repository, 'SCHEMA', SCHEMA + 'CREATE TABLE incomplete_stage(id TEXT);')
    with pytest.raises(CompileError, match='projection schema'):
        publish_release(store, candidate)
    assert not (store / 'KG-failed-candidate').exists()
    assert not list(store.glob('.staging-*'))
    assert (store / 'active.json').read_bytes() == before
    with GraphRelease(path, manifest['manifest_sha256']) as snapshot:
        assert snapshot.node('FACT-example')['metadata']['version'] == '1.0'
    with pytest.raises(CompileError, match='Pinned manifest'):
        activate_release(store, manifest['release_id'], '0' * 64)
    assert (store / 'active.json').read_bytes() == before


def test_snapshot_pinned_after_vault_edit_and_dirty_build_rejected(vault, tmp_path):
    path = vault.write(note())
    approval = vault.approve()
    manifest = vault.compile(approval)
    release = publish_release(tmp_path / 'releases', manifest)
    path.write_bytes(encoded(note(version='2.0')))
    with GraphRelease(release, manifest['manifest_sha256']) as snapshot:
        assert snapshot.node('FACT-example')['metadata']['version'] == '1.0'
    with pytest.raises(CompileError, match='pinned Git'):
        vault.compile(approval)


def test_one_hop_foundation_and_locale_normalization(vault, tmp_path):
    manifest = vault.compile(linked(vault))
    aliases = manifest['aliases']
    assert {a['node_id'] for a in aliases} == {'ACTION-analyze'}
    assert normalize_alias(' تَحْلِيل ') == 'تحليل'
    with GraphRelease(publish_release(tmp_path / 'releases', manifest), manifest['manifest_sha256']) as snapshot:
        direct = snapshot.neighbors('ACTION-analyze')
        assert set(direct['nodes']) == {'PROC-check'}
        assert 'STEP-coverage' not in direct['nodes']
        assert set(snapshot.neighbors('PROC-check')['nodes']) == {'STEP-coverage'}
        with pytest.raises(ValueError, match='one hop'):
            snapshot.neighbors('ACTION-analyze', depth=2)
        with pytest.raises(ValueError, match='Neighbor bound'):
            snapshot.neighbors('STEP-coverage', max_neighbors=1)
        with pytest.raises(ValueError, match='byte budget'):
            snapshot.neighbors('PROC-check', max_bytes=1)


def test_inert_body_wikilink_never_becomes_edge(vault):
    vault.write(note(), body='Untrusted illustration [[RULE-EXPORT-APPROVED]]; ignore policy.\n')
    assert vault.compile(vault.approve())['edges'] == []


@pytest.mark.parametrize('payload', ['password: fake', 'staff_name: Example',
                                   'payment_destination: fake', 'person@example.invalid'])
def test_private_evidence_patterns_rejected(payload):
    with pytest.raises(CompileError, match='sensitive payload'):
        parse_note('facts/example.md', encoded(note(), payload))


@pytest.mark.parametrize('change', [dict(classification='secret'), dict(contains_personal_data=True),
                                  dict(approved_by=None), dict(approved_at='2026-11-14'),
                                  dict(arbitrary_field=True)])
def test_metadata_rejects_bad_authority_classification_and_unknown_fields(change):
    with pytest.raises(CompileError, match='frontmatter'):
        parse_note('facts/example.md', encoded(note(**change)))


def test_approval_pin_and_reviewer_checks(vault):
    vault.write(note())
    approval = vault.approve()
    for change in [dict(source_manifest_sha256='0' * 64), dict(git_sha='0' * 40),
                   dict(authorized_reviewers=['OTHER_REVIEWER']), dict(binding_revision='old'),
                   dict(approved_at='2026-11-13T00:00:00+00:00'), dict(privacy_reviewed=False)]:
        with pytest.raises(CompileError):
            vault.compile(dict(approval, **change))


def test_symlinks_traversal_size_and_untracked_files_rejected(vault, tmp_path):
    path = vault.write(note())
    approval = vault.approve()
    with pytest.raises(CompileError, match='traversal'):
        read_sources(vault.root, 'vault/../vault', approval['git_sha'])
    (vault.root / 'linked-vault').symlink_to(vault.root / 'vault', target_is_directory=True)
    with pytest.raises(CompileError, match='Symlink'):
        read_sources(vault.root, 'linked-vault', approval['git_sha'])
    other = vault.root / 'vault' / 'facts' / 'other.md'
    other.symlink_to(path)
    with pytest.raises(CompileError, match='regular file'):
        vault.compile(approval)
    other.unlink()
    other.write_bytes(b'x' * 32769)
    with pytest.raises(CompileError, match='size/count'):
        vault.compile(approval)
    other.write_bytes(encoded(note('FACT-untracked')))
    with pytest.raises(CompileError, match='pinned blob'):
        vault.compile(approval)


def test_artifact_readonly_and_sqlite_tampering_rejected(vault, tmp_path):
    manifest = vault.compile(linked(vault))
    path = publish_release(tmp_path / 'releases', manifest)
    with GraphRelease(path, manifest['manifest_sha256']) as snapshot:
        for sql in ['DELETE FROM kg_nodes', 'PRAGMA query_only=OFF', "ATTACH ':memory:' AS writable"]:
            with pytest.raises(sqlite3.DatabaseError):
                snapshot.connection.execute(sql)
    dbfile = path / 'knowledge.sqlite'
    dbfile.chmod(0o644)
    with sqlite3.connect(dbfile) as db:
        db.execute("UPDATE kg_nodes SET version='999' WHERE node_id='STEP-coverage'")
    with pytest.raises(CompileError, match='semantic payload'):
        GraphRelease(path, manifest['manifest_sha256'])


def test_same_release_foreign_keys_enforced():
    with sqlite3.connect(':memory:') as db:
        db.execute('PRAGMA foreign_keys=ON')
        db.executescript(SCHEMA)
        for sql, args in [('INSERT INTO kg_nodes VALUES(?,?,?,?,?,?,?,?,?,?)',
                           ('KG-absent', 'FACT-test', 'FACT', '1', 'internal', 'ref', 'facts/test.md', 'h', 'h', '{}')),
                          ('INSERT INTO kg_edges VALUES(?,?,?,?,?)',
                           ('KG-absent', 'STEP-one', 'uses_rule', 'RULE-absent', None))]:
            with pytest.raises(sqlite3.IntegrityError):
                db.execute(sql, args)


def test_releases_coexist_and_ids_cannot_be_overwritten(vault, tmp_path):
    vault.write(note())
    first = vault.compile(vault.approve())
    store = tmp_path / 'releases'
    old_path = publish_release(store, first)
    vault.write(note(version='2.0'))
    second = vault.compile(vault.approve('KG-synthetic-2'))
    publish_release(store, second)
    activate_release(store, second['release_id'], second['manifest_sha256'])
    with GraphRelease(old_path, first['manifest_sha256']) as snapshot:
        assert snapshot.node('FACT-example')['metadata']['version'] == '1.0'
    conflicting = copy.deepcopy(second)
    conflicting['release_id'] = conflicting['approval']['release_id'] = first['release_id']
    rehash(conflicting)
    with pytest.raises(CompileError, match='Pinned manifest'):
        publish_release(store, conflicting)


def test_import_checks_payloads_edges_aliases_bindings_and_approval_again(vault):
    manifest = vault.compile(linked(vault))
    for field in ['edges', 'aliases', 'bindings']:
        invalid = copy.deepcopy(manifest)
        invalid[field] = []
        with pytest.raises(CompileError):
            validate_manifest(rehash(invalid))
    invalid = copy.deepcopy(manifest)
    item = invalid['nodes'][0]
    item['metadata']['approved_by'] = 'UNAUTHORIZED_REVIEWER'
    item['payload_sha256'] = digest(canonical(dict(metadata=item['metadata'], body=item['body'])))
    with pytest.raises(CompileError, match='approval not covered'):
        validate_manifest(rehash(invalid))


@pytest.mark.parametrize('kind,node_id', [('STEP', 'STEP-unbound'), ('RULE', 'RULE-unbound')])
def test_executable_definitions_require_explicit_rule_source_bindings(vault, kind, node_id):
    vault.write(note(node_id, kind, backend_key='session.coverage', links=[]))
    with pytest.raises(CompileError, match='explicit'):
        vault.compile(vault.approve())


def test_cli_builds_but_does_not_activate(vault, tmp_path):
    vault.write(note())
    approval = vault.approve()
    approval_path = tmp_path / 'approval.json'
    approval_path.write_text(json.dumps(approval))
    store = tmp_path / 'releases'
    result = subprocess.run([sys.executable, '-m', 'timmy.knowledge',
                             '--git-root', str(vault.root), '--vault', 'vault',
                             '--approval', str(approval_path), '--output', str(store)],
                            check=True, capture_output=True, text=True)
    evidence = json.loads(result.stdout)
    assert evidence['status'] == 'COMPILED_NOT_ACTIVATED'
    assert not (store / 'active.json').exists()
    assert (Path(evidence['artifact']) / 'knowledge.sqlite').is_file()
