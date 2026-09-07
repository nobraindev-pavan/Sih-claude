# Field mapping — our schema to the real systems

The prototype runs on synthetic data. This document is the answer to *"and how
would you connect it to ours?"* — the mapping is a rename, not a redesign, and
the work is bounded and visible.

**Verify every row before putting it on a slide.** These are our best reading of
published material about each system, not verified integration specifications.
Where we are unsure, the cell says so. A judge forgives "we believe this maps to
X, and here is how we'd confirm it"; they do not forgive a confident error about
their own system.

Implementation lives in `sanchay/core/connectors/`. `csv_source.py` is the
working connector; `api_stub.py` carries these mappings in docstrings and raises
`NotImplementedError`, deliberately.

## BDMS — Block & Disconnection Management System (CRIS)

The most important one. BDMS is where block demands are actually raised, routed
and tracked across traffic, power and disconnection blocks. It is our natural
integration point, in both directions: we consume its requisitions and hand back
a proposed allocation for a human to sanction.

| Our field | Their concept | Confidence |
|---|---|---|
| `task.id` | block demand / requisition number | high |
| `task.dept` | demanding department (ENG / S&T / TRD) | high |
| `task.section_id` | block section, from/to block station | high |
| `task.km_from`, `task.km_to` | chainage of the worksite | high |
| `task.activity_type` | nature of work | medium — their taxonomy will be finer than our 16 codes |
| `task.nominal_duration_min` | block duration sought | high |
| `task.due_min` | target or latest date | medium |
| `block.permits` | demand type: traffic / power / disconnection | high |
| `block.status` | demand status: raised, sanctioned, cancelled, executed | high |
| `execution_log.*` | block return / completion report | medium |

## COA — Control Office Application (CRIS)

The source of the train chart, and therefore of every train-disruption number
the optimizer produces.

| Our field | Their concept | Confidence |
|---|---|---|
| `train.number` | train number | high |
| `train.train_class` | train type, which sets operating priority | high |
| `train.priority_weight` | *ours* — derived from class, tunable, not theirs | n/a |
| `train_path.section_id` | block section | high |
| `train_path.enter_min`, `exit_min` | scheduled or actual times at either end | high |
| `corridor_window` | the maintenance block built into the working timetable | medium |

## TMS — Track Management System (Engineering)

| Our field | Their concept | Confidence |
|---|---|---|
| `asset.id` | track asset / segment identifier | high |
| `asset.km_from`, `km_to` | chainage | high |
| `asset.annual_gmt` | gross million tonnes carried | high |
| `asset.days_since_maintenance` | last attention date | high |
| `asset.failures_3y` | defect / failure history | medium |
| `task.severity` | defect classification | medium — theirs is a graded scheme |

## SMMS — Signal Maintenance Management System (S&T)

| Our field | Their concept | Confidence |
|---|---|---|
| `asset.asset_type` | signal, point machine, track circuit, axle counter | high |
| `task.activity_type` | maintenance schedule item or failure job | medium |
| `activity.requires: disconnection` | disconnection notice requirement | high |

## TDMS — Traction Distribution Management System (Electrical/TRD)

| Our field | Their concept | Confidence |
|---|---|---|
| `asset.asset_type` | OHE elementary section, mast, isolator | high |
| `activity.requires: power_block` | power block and Permit To Work requirement | high |
| `task.nominal_duration_min` | scheduled maintenance duration | high |

## What changes on deployment

1. Implement `fetch_tasks` / `fetch_assets` in the four stub classes.
2. Extend `data/rulebook.yaml` to the real activity taxonomy — this is domain
   work, not code, and it needs a serving officer to review it.
3. Replace the synthetic timetable with the COA feed.
4. Nothing else. The optimizer, the objective, the explanations and the UI
   consume the unified schema and do not know where it came from.

Point 2 is the honest long pole, and saying so is better than pretending the
whole thing is a config change.
