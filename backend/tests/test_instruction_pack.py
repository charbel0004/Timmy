import pytest

from timmy.instruction_pack import action_instructions


@pytest.mark.parametrize("number", range(17))
def test_approved_instructions_load(number):
    action_id = f"ACT-{number:02}"
    assert action_id in action_instructions(action_id)


def test_loader_rejects_unregistered_action():
    with pytest.raises(ValueError, match="Unknown action"):
        action_instructions("../../manifest.json")
