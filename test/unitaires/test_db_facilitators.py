"""Tests unitaires — Agent/Tools/Database/facilitators.py"""


def test_create_facilitator_returns_dict_with_id():
    from Agent.Tools.Database.facilitators import create_facilitator
    f = create_facilitator("Alice Dupont")
    assert isinstance(f["id"], int)
    assert f["name"] == "Alice Dupont"


def test_create_multiple_facilitators_get_different_ids():
    from Agent.Tools.Database.facilitators import create_facilitator
    f1 = create_facilitator("Alice")
    f2 = create_facilitator("Bob")
    assert f1["id"] != f2["id"]


def test_list_facilitators_empty():
    from Agent.Tools.Database.facilitators import list_facilitators
    assert list_facilitators() == []


def test_list_facilitators_returns_all():
    from Agent.Tools.Database.facilitators import create_facilitator, list_facilitators
    create_facilitator("Alice")
    create_facilitator("Bob")
    result = list_facilitators()
    assert len(result) == 2
    names = {f["name"] for f in result}
    assert names == {"Alice", "Bob"}


def test_list_facilitators_sorted_by_name():
    from Agent.Tools.Database.facilitators import create_facilitator, list_facilitators
    create_facilitator("Zoé")
    create_facilitator("Alice")
    result = list_facilitators()
    assert result[0]["name"] == "Alice"
    assert result[1]["name"] == "Zoé"


def test_get_facilitator_existing():
    from Agent.Tools.Database.facilitators import create_facilitator, get_facilitator
    f = create_facilitator("Alice")
    found = get_facilitator(f["id"])
    assert found is not None
    assert found["name"] == "Alice"
    assert found["id"] == f["id"]


def test_get_facilitator_not_found_returns_none():
    from Agent.Tools.Database.facilitators import get_facilitator
    assert get_facilitator(9999) is None
