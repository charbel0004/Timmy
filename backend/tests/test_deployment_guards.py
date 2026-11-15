"""CI/CD guard tests: prod .env isolation, exact migration allowlist, rollback safety."""
from pathlib import Path
import os
import subprocess
import sys
from test_foundation import client


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "ops" / "deploy" / "deploy-server.sh"
ISOLATED = ROOT / "ops" / "deploy" / "run-isolated-backend-checks.sh"


def test_deployment_shell_scripts_have_valid_syntax():
    for script in (SCRIPT, ISOLATED):
        subprocess.run(["bash", "-n", str(script)], check=True)


def test_isolated_backend_checks_ignore_hostile_checkout_env(tmp_path):
    # Copy the backend into an artificial source root with production-looking
    # .env values that would break ordinary login and Ollama tests.
    import shutil
    fake_repo = tmp_path / "repo"
    fake_repo.mkdir()
    shutil.copytree(ROOT / "backend", fake_repo / "backend")
    shutil.copytree(ROOT / "ops" / "deploy", fake_repo / "ops" / "deploy")
    shutil.copytree(ROOT / ".github" / "workflows", fake_repo / ".github" / "workflows")
    (fake_repo / ".env").write_text(
        "TIMMY_FRONTEND_ORIGIN=https://prod.example.invalid\n"
        "TIMMY_COOKIE_SECURE=true\n"
        "TIMMY_OLLAMA_TIMEOUT_SECONDS=1\n",
        encoding="utf-8",
    )
    scratch = tmp_path / "checks"
    scratch.mkdir()
    env = os.environ.copy()
    env.update({
        "TIMMY_FRONTEND_ORIGIN": "https://another.invalid",
        "TIMMY_COOKIE_SECURE": "true",
        "TIMMY_OLLAMA_TIMEOUT_SECONDS": "2",
        "TIMMY_DATABASE_URL": "sqlite:///should-not-be-used.db",
    })
    result = subprocess.run(
        ["bash", str(ISOLATED), str(fake_repo), sys.executable, str(scratch),
         "backend/tests/test_foundation.py::test_session_and_project_scope"],
        cwd=str(tmp_path), capture_output=True, text=True, env=env, timeout=180,
    )
    assert result.returncode == 0, result.stdout[-2500:] + result.stderr[-2500:]
    assert "1 passed" in result.stdout
    assert "ISOLATED_BACKEND_CHECKS_PASSED" in result.stdout
    assert "prod.example.invalid" in (fake_repo / ".env").read_text()
    assert not (scratch / "source" / ".env").exists()


def test_live_deploy_uses_reviewed_migration_without_database_restore():
    script = SCRIPT.read_text(encoding="utf-8")
    assert '[[ $revision == "$from_revision" && $expected == "$to_revision" ]]' in script
    assert 'aea0fbd39b71978cac927a4ec859ec817332ab48' in script
    assert '.schema-bridge' in script
    assert 'PRAGMA integrity_check' in script
    assert '".restore' not in script
    assert 'pytest' not in script
    assert script.index('wait_health "http://127.0.0.1:$slot"') < script.index('write_route "$release/')
    deploy_yaml = (ROOT / ".github" / "workflows" / "deploy.yml").read_text()
    assert "vars.TIMMY_DEPLOY_V2_READY == 'true'" in deploy_yaml


def test_server_cannot_expose_live_dotenv_to_test_runner():
    script = ISOLATED.read_text(encoding="utf-8")
    assert "env -i " in script
    assert 'cp -a "$repo/backend" "$scratch/source/backend"' in script
    assert '[[ ! -e "$scratch/source/.env" ]]' in script


def test_observability_migration_declaration_is_exactly_pinned():
    fields = (ROOT / 'ops/deploy/additive-migration').read_text().split()
    assert fields[:2] == ['0019', '0020']
    migration = 'backend/migrations/versions/0020_reporting_register.py'
    assert fields[2] == migration and len(fields) == 4
    blob = subprocess.check_output(['git', 'hash-object', migration], cwd=ROOT, text=True).strip()
    assert fields[3] == blob
    changes = subprocess.check_output(['git', 'diff', '--name-status',
        'f203273f42b937eab8605445c89ecf759e0d6096', '--', 'backend/migrations'], cwd=ROOT, text=True).strip()
    assert changes == 'A\t' + migration


def test_active_release_serves_expanded_observability_schema(tmp_path, client):
    import io
    import tarfile
    archive = subprocess.check_output(['git', 'archive',
        'f203273f42b937eab8605445c89ecf759e0d6096', 'backend'], cwd=ROOT)
    old = tmp_path / 'active-release'
    old.mkdir()
    with tarfile.open(fileobj=io.BytesIO(archive)) as source:
        source.extractall(old, filter='data')
    script = '''
from fastapi.testclient import TestClient
from timmy.main import create_app
from timmy.config import Settings
with TestClient(create_app(Settings(database_url=DATABASE, frontend_origin='http://localhost:5173', cookie_secure=False, weekly_enabled=False))) as client:
    assert client.get('/api/health').status_code == 200
    result = client.post('/api/auth/login', headers={'Origin':'http://localhost:5173'}, json={'username':'reviewer','password':'local test password'})
    assert result.status_code == 200, result.text
    assert len(client.get('/api/projects').json()) == 1
'''
    script = 'DATABASE = ' + repr(client.app.state.config.database_url) + '\n' + script
    env = os.environ.copy()
    env['PYTHONPATH'] = str(old / 'backend')
    result = subprocess.run([sys.executable, '-c', script], cwd=old, env=env,
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
