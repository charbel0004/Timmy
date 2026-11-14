import pytest
from pydantic import ValidationError

from timmy.action_catalog import ActionResult, chat_system_prompt, load_catalog


def test_catalog_keeps_financial_actions_out_of_chat():
    actions = {action.id: action for action in load_catalog().actions}
    assert actions["ACT-11"].availability == "trial_only"
    assert actions["ACT-12"].availability == "blocked"
    assert actions["ACT-13"].availability == "blocked"
    assert actions["policy.version"].availability == "blocked"
    assert "only callable tool in this chat is list_projects" in chat_system_prompt()


def test_result_requires_backend_evidence_for_verified_status():
    with pytest.raises(ValidationError):
        ActionResult(request_id="test", action_id="ACT-12", status="verified", evidence_refs=[], issue_codes=[])
    with pytest.raises(ValidationError):
        ActionResult(request_id="test", action_id="invented", status="blocked", evidence_refs=[], issue_codes=["DENIED"])
