from basheco.city_plan_storage import save_draft


def test_dry_run_has_no_database_dependency():
    a = save_draft("S80652440101", 5000, -6000)
    b = save_draft("S80652440101", 5000, -6000)
    assert a == b
    assert a["dry_run"] is True
    assert a["published"] is False
    assert a["objects"] > 600