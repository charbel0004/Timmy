"""Shape checks only; never a substitute for transactional authorization."""
import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError

ROOT = Path(__file__).resolve().parents[2] / 'docs' / 'implementation'


@pytest.mark.parametrize('name', ['workflow_step_receipt', 'human_review_request', 'claim_provenance', 'one_hop_query'])
def test_supplied_contract_is_valid_draft202012_and_byte_exact(name):
    filename = name + '.schema.json'
    data = (ROOT / 'contracts' / filename).read_bytes()
    Draft202012Validator.check_schema(json.loads(data))
    expected = dict(line.split(maxsplit=1)[::-1] for line in (ROOT / 'SUPPLIED_SHA256SUMS.txt').read_text().splitlines() if line.strip())
    assert hashlib.sha256(data).hexdigest() == expected['docs/implementation/contracts/' + filename]


def test_one_hop_shape_requires_explicit_depth_and_bound():
    validator = Draft202012Validator(json.loads((ROOT / 'contracts' / 'one_hop_query.schema.json').read_text()))
    validator.validate(dict(seed_node_id='PROC-test', depth=1, max_neighbors=20))
    for value in [dict(seed_node_id='PROC-test', depth=2, max_neighbors=20),
                  dict(seed_node_id='PROC-test', depth=1, max_neighbors=21),
                  dict(seed_node_id='PROC-test', max_neighbors=1),
                  dict(seed_node_id='PROC-test', depth=1, max_neighbors=1, unrestricted=True)]:
        with pytest.raises(ValidationError):
            validator.validate(value)


def test_supplied_shapes_do_not_establish_verified_claim_or_authorization():
    # Deliberately schema-valid but NOT backend-valid. S3-S5 must reject these.
    schema = json.loads((ROOT / 'contracts' / 'claim_provenance.schema.json').read_text())
    unsupported = dict(claim_id='synthetic', run_id='absent', verdict='verified',
                       statement_redacted='Unsupported synthetic assertion', kg_release_id='absent',
                       source_refs=[], rule_check_receipt_ids=[])
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(unsupported)
    assert not unsupported['source_refs'] and not unsupported['rule_check_receipt_ids']
