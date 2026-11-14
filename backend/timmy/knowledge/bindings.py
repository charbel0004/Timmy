"""Static read-only binding inventory. Notes cannot register/import callables."""
from hashlib import sha256
from inspect import getsource
from ..session_rules import coverage
from ..conversation_workflow import check_integrity

BINDING_REVISION='timmy-kg-bindings-1'
# No finance, approval, policy-write, external authority or arbitrary code keys.
BINDINGS={'session.coverage':(coverage,'1'), 'source.integrity':(check_integrity,'1')}


def binding_manifest(key):
    if key not in BINDINGS:raise ValueError('Backend key is not in static allowlist')
    handler,version=BINDINGS[key]
    return dict(key=key,contract_version=version,binding_revision=BINDING_REVISION,
                code_sha256=sha256(getsource(handler).encode()).hexdigest())
