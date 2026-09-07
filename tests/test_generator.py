from sanchay.core.timeutil import overlaps
from sanchay.gen.generate import GenConfig, generate


def test_is_deterministic(rb):
    a = generate(GenConfig(seed=5, horizon_days=3), rb)
    b = generate(GenConfig(seed=5, horizon_days=3), rb)
    assert [t.id for t in a.tasks] == [t.id for t in b.tasks]
    assert [p.enter_min for p in a.paths] == [p.enter_min for p in b.paths]


def test_different_seeds_differ(rb):
    a = generate(GenConfig(seed=5, horizon_days=3), rb)
    b = generate(GenConfig(seed=6, horizon_days=3), rb)
    assert [t.asset_id for t in a.tasks] != [t.asset_id for t in b.tasks]


def test_demand_levels_scale_the_backlog(rb):
    counts = [len(generate(GenConfig(seed=2, horizon_days=3, demand=d), rb).tasks)
              for d in ("low", "normal", "surge")]
    assert counts[0] < counts[1] < counts[2]


def test_no_train_is_scheduled_through_a_corridor_window(scenario):
    """The whole corridor policy rests on this: the working timetable is built
    around the window. If this fails, the cheapest blocks are not actually cheap."""
    windows = {}
    for w in scenario.corridor_windows:
        windows.setdefault(w.section_id, []).append(w)
    for p in scenario.paths:
        for w in windows.get(p.section_id, []):
            assert not overlaps(p.enter_min, p.exit_min, w.start_min, w.end_min), \
                f"{p.train_number} runs through the corridor window on {p.section_id}"


def test_tasks_reference_real_assets_and_sections(scenario):
    assets = {a.id: a for a in scenario.assets}
    sections = {s.id for s in scenario.sections}
    for t in scenario.tasks:
        assert t.asset_id in assets
        assert t.section_id in sections
        assert assets[t.asset_id].dept == t.dept


def test_every_task_fits_inside_the_policy_block_length(scenario, rb):
    for t in scenario.tasks:
        assert t.predicted_duration_min <= rb.policy.max_block_duration_min


def test_branch_is_single_line_and_main_is_double(scenario):
    for s in scenario.sections:
        if s.id.startswith("BRCH"):
            assert s.line_type == "single"
        elif s.id.startswith("MAIN"):
            assert s.line_type == "double"
