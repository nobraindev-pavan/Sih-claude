"""The safety rules are the one place a bug is unacceptable, so test them hard."""

from sanchay.core.rulebook import ALL_PERMITS, Rulebook


def test_loads_and_every_permit_is_known(rb):
    assert len(rb.activities) >= 12
    for act in rb.activities.values():
        assert act.requires <= set(ALL_PERMITS)
        assert act.forbids <= set(ALL_PERMITS)
        assert not (act.requires & act.forbids)
        assert act.nominal_duration_min > 0


def test_power_block_and_live_signal_testing_can_never_share(rb):
    # SNT_SIGNAL_TESTING needs the section live; TRD work needs it isolated.
    ok, why = rb.can_share_block("SNT_SIGNAL_TESTING", "TRD_OHE_INSULATOR")
    assert not ok and "power_block" in why


def test_explicitly_incompatible_pair_is_refused(rb):
    ok, why = rb.can_share_block("ENG_TAMPING", "SNT_POINT_OVERHAUL")
    assert not ok and "unsafe" in why


def test_block_permits_are_the_union_of_requirements(rb):
    permits = rb.block_permits(["ENG_TAMPING", "SNT_TRACK_CIRCUIT"])
    assert "traffic_block" in permits and "power_block" in permits
    assert "disconnection" in permits


def test_block_is_legal_catches_a_forbidden_permit_arriving_via_another_task(rb):
    # signal testing is fine alone, but not once someone brings a power block
    assert rb.block_is_legal(["SNT_SIGNAL_TESTING"])[0]
    ok, _ = rb.block_is_legal(["SNT_SIGNAL_TESTING", "TRD_MAST_REPAIR"])
    assert not ok


def test_separation_takes_the_stricter_of_the_two(rb):
    a = rb["ENG_BALLAST_SCREENING"].min_separation_m
    b = rb["SNT_TRACK_CIRCUIT"].min_separation_m
    assert rb.separation_m("ENG_BALLAST_SCREENING", "SNT_TRACK_CIRCUIT") == max(a, b)


def test_a_malformed_rulebook_is_rejected(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "activity_types:\n  X:\n    dept: ENG\n    name: X\n"
        "    requires: [teleportation]\n    nominal_duration_min: 60\n"
        "    min_separation_m: 10\n    crew_type: track_gang\n")
    try:
        Rulebook.load(bad)
    except ValueError as exc:
        assert "unknown permit" in str(exc)
    else:
        raise AssertionError("an unknown permit should be rejected at load time")
