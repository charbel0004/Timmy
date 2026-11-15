"""Disposable main-schema upgrade; compare every original column and row."""
import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import insert
from sqlalchemy.orm import Session

from timmy.config import settings
from timmy.database import make_engine
from timmy.models import (Role, User, Conversation, ChatTurn, StoredFile, DocumentImport,
                          MappingProposal, WorkflowRun, projects, project_memberships,
                          activities, payment_policies)


def test_populated_main_upgrade_preserves_original_evidence(tmp_path, monkeypatch):
    path = tmp_path / 'main-0014.db'
    url = f'sqlite:///{path}'
    monkeypatch.setenv('TIMMY_DATABASE_URL', url)
    settings.cache_clear()
    cfg = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    engine = make_engine(url)
    try:
        command.upgrade(cfg, '0014')
        with Session(engine) as db, db.begin():
            role = Role(name='synthetic-upgrade')
            db.add(role); db.flush()
            db.add(User(id=1, username='synthetic-upgrade', password_hash='test-only', role_id=role.id))
            db.flush()
            db.execute(insert(projects).values(id=1, name='Synthetic upgrade project', project_code='SYN'))
            db.execute(insert(project_memberships).values(project_id=1, user_id=1))
            db.execute(insert(payment_policies).values(project_id=1, version=1, configuration={'synthetic': True}))
            db.execute(insert(activities).values(project_id=1, name='Legacy uncoded activity'))
            db.add(Conversation(id='synthetic-conversation', owner_id=1,
                                workflow_state={'stage': 'MAPPING_CONFIRMED', 'synthetic': True}))
            db.flush()
            db.add(StoredFile(id='synthetic-file', purpose='intake', original_filename='synthetic.csv',
                             relative_storage_key='synthetic-file', sha256='0'*64, size_bytes=12,
                             mime_type='text/csv', uploaded_at='2026-11-14', project_id=1, uploaded_by=1))
            db.flush()
            db.add(DocumentImport(file_id='synthetic-file', conversation_id='synthetic-conversation',
                                  sheets=[{'name': 'Synthetic', 'rows': []}], row_count=0))
            db.add(MappingProposal(id='synthetic-mapping', conversation_id='synthetic-conversation',
                                   actor_id=1, project_id=1, fingerprint='1'*64, version=1,
                                   sheets=[], status='confirmed', created_at=1, confirmed_at=1, confirmed_by=1))
            db.add(ChatTurn(conversation_id='synthetic-conversation', request_id='synthetic-request',
                            prompt='Synthetic', reply='Explicitly blocked', created_at=1, context={'synthetic': True}))
            db.add(WorkflowRun(actor_id=1, project_id=1, request_key='synthetic-run', fingerprint='2'*64,
                               workflow_id='analyze_intake', knowledge_version='synthetic', created_at=1,
                               status='blocked', snapshot={'steps': [], 'source_ids': ['synthetic-file']}))
        engine.dispose()
        with sqlite3.connect(path) as db:
            tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
                      if r[0] != 'alembic_version']
            before = {}
            for name in tables:
                cols = [r[1] for r in db.execute(f'PRAGMA table_info("{name}")')]
                before[name] = (cols, db.execute(f'SELECT * FROM "{name}"').fetchall())
        command.upgrade(cfg, 'head')
        command.check(cfg)
        with sqlite3.connect(path) as db:
            assert db.execute('PRAGMA integrity_check').fetchone() == ('ok',)
            assert db.execute('PRAGMA foreign_key_check').fetchall() == []
            for name, (cols, rows) in before.items():
                quoted = ','.join(f'"{col}"' for col in cols)
                assert db.execute(f'SELECT {quoted} FROM "{name}"').fetchall() == rows, name
            assert db.execute('SELECT code_authority FROM activities').fetchone() == ('legacy_review_required',)
            assert db.execute('SELECT policy_family FROM projects').fetchone() == (None,)
            assert db.execute('SELECT version_num FROM alembic_version').fetchone() == ('0020',)
    finally:
        engine.dispose()
        settings.cache_clear()
