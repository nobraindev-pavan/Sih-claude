# 04 · Architecture and data model

## Shape of the system

One backend process, one frontend app, one database file. Resist everything else.

```
  data/scenarios/vijaypur_v1/*.csv          <- synthetic, seeded, committed
            |
            v
  +---------------------------------+
  |  connectors/                    |       one class per source system.
  |    tms.py  smms.py  tdms.py     |       today: read CSV.
  |    coa.py  bdms.py              |       tomorrow: hit a real API.
  +---------------------------------+       the interface never changes.
            |  normalize()
            v
  +---------------------------------+
  |  UNIFIED STORE  (SQLite)        |       one schema, all departments
  +---------------------------------+
            |
   +--------+--------+--------------+-----------------+
   v                 v              v                 v
 risk.py         duration.py    windows.py       rulebook.yaml
 asset risk      ML duration    candidate        permits &
 score           + overrun P    windows/section  compatibility
   |                 |              |                 |
   +--------+--------+--------------+--------+--------+
            v
  +---------------------------------+
  |  candidates.py                  |  build (task, block) feasible pairs
  |  traffic_cost.py                |  precompute train disruption per block
  +---------------------------------+
            |
            v
  +---------------------------------+        +------------------+
  |  optimizer/cpsat.py             |        | baselines/       |
  |  the CP-SAT model               |        |  fcfs.py         |
  +---------------------------------+        |  corridor.py     |
            |                                 +------------------+
            v                                          |
  +---------------------------------+                  |
  |  PLAN  (blocks + assignments    |<-----------------+
  |         + cost decomposition)   |
  +---------------------------------+
            |
            +--> explain.py     (counterfactual re-solve)
            +--> whatif.py      (perturb -> re-solve -> diff)
            +--> metrics.py     (KPIs, baseline comparison)
            |
            v
  +---------------------------------+
  |  FastAPI  (api/)                |
  +---------------------------------+
            | JSON
            v
  +---------------------------------+
  |  React + Vite                   |
  |   TrainGraph  BlockPlan  KPIs   |
  |   WhyPanel    WhatIf   Approve  |
  +---------------------------------+
```

## Repository layout

```
sanchay/
  data/
    scenarios/vijaypur_v1/      network.csv sections.csv stations.csv
                                assets.csv tasks.csv trains.csv paths.csv
                                crews.csv execution_log.csv
    rulebook.yaml               activity types, permits, compatibility
  gen/
    generate_scenario.py        seeded synthetic world generator
  core/
    models.py                   pydantic/SQLModel entities (the schema below)
    connectors/                 tms.py smms.py tdms.py coa.py  (+ base.py)
    windows.py                  candidate window generation
    traffic_cost.py             train disruption cost per candidate block
    candidates.py               feasible (task, block) pairs
    rulebook.py                 loads + validates rulebook.yaml
  ml/
    duration.py                 duration + overrun model (primary ML)
    risk.py                     asset hazard / risk score
    notebooks/                  training + evaluation notebooks
  optimizer/
    cpsat.py                    THE model
    explain.py                  cost decomposition + counterfactual
  baselines/
    fcfs.py                     B1 departmental first-come-first-served
    corridor.py                 B2 corridor-policy greedy packing
  eval/
    harness.py                  N scenarios -> metrics table
    report.py                   mean +/- CI, ablations, charts
  api/
    main.py                     FastAPI
  ui/                           React + Vite
  tests/
  docs/                         these documents
```

## The data model

This is the contract. Write it in week 1, review it as a team, and change it only
deliberately — every other file depends on it. Field names deliberately echo what a real
TMS/SMMS/TDMS/BDMS record carries, so the mapping to real systems is a rename, not a
redesign.

### Network

```
station        code, name, km, is_block_station, has_loop, division
section        id, from_station, to_station, km_from, km_to, line_type{single,double},
               electrified, max_speed_kmph, is_diversion_for(section_id|null)
```

### Assets

```
asset          id, dept{ENG,SNT,TRD}, asset_type, section_id, km_from, km_to,
               install_date, last_maintenance_date, maintenance_interval_days,
               criticality{1..5}, annual_gmt (traffic tonnage), failure_count_3y
```
`km_from`/`km_to` are what make spatial overlap computable. Point assets set them equal.

### The rulebook (`data/rulebook.yaml`)

```yaml
activity_types:
  ENG_TAMPING:
    dept: ENG
    name: Track tamping / packing
    requires: [traffic_block, power_block]      # tamping fouls the OHE zone
    nominal_duration_min: 120
    min_separation_m: 200                        # from any other worksite
    max_gangs: 1
  SNT_POINT_OVERHAUL:
    dept: SNT
    requires: [disconnection, traffic_block]
    nominal_duration_min: 90
    min_separation_m: 50
  TRD_OHE_INSULATOR:
    dept: TRD
    requires: [power_block]
    nominal_duration_min: 60
    min_separation_m: 100
  SNT_SIGNAL_TESTING:
    dept: SNT
    requires: [disconnection]
    forbids: [power_block]                       # needs the section live to test
    nominal_duration_min: 45

compatibility:
  # pairs that may NOT share a block even if permits align
  incompatible_pairs:
    - [ENG_TAMPING, SNT_POINT_OVERHAUL]          # ballast disturbance vs point adjustment
  # default: compatible if permits are compatible and separation is respected
```

Two rules the code enforces from this: a block's permit set is the **union** of its tasks'
requirements, and no task in a block may `forbid` a permit that block holds. This single
mechanism gives us realistic, explainable, hard safety behaviour for almost no code.

### Tasks (the unified requisition — this is the PS's "common schema")

```
task           id, dept, activity_type, asset_id, section_id, km_from, km_to,
               description, severity{routine,important,critical}, raised_date,
               due_date, nominal_duration_min, predicted_duration_min,
               overrun_probability, crew_type, crew_size,
               risk_score, priority_score, status{open,planned,sanctioned,done}
```
`predicted_duration_min` and `overrun_probability` come from the ML model (doc 6);
`risk_score` from the hazard model; `priority_score` from the weighted rule in the concept
note. The optimizer consumes `predicted_duration_min` — **that is the point of the ML.**

### Operations

```
train          number, name, train_class{VB,RAJ,MEX,PASS,MEMU,FRT},
               priority_weight, direction{UP,DN}, runs_days_mask
train_path     train_number, section_id, arrival, departure, day_offset
corridor_window section_id, start_time, end_time, days_mask, source{policy}
```
`train_path` over `section_id` is what lets us compute, for any (section, time-range), the
exact set of affected trains — the basis of the disruption cost and of the train graph.

### Crews

```
crew           id, dept, crew_type, home_depot_station, shift_start, shift_end,
               max_hours_per_day, travel_speed_kmph
```
Crew travel time between sections is a real constraint and a cheap source of realism:
a gang cannot finish at KM 45 and start at KM 160 twenty minutes later.

### Output

```
block          id, section_id, start, end, permits{set}, block_type,
               task_ids[], trains_affected[], 
               cost_train, cost_downtime, cost_setup, cost_total,
               utilization_pct, status{proposed,reviewed,sanctioned,rejected},
               plan_id, created_by, sanctioned_by, sanctioned_at
plan           id, scenario_id, horizon{week,month}, generated_at, solver_status,
               objective_value, solve_seconds, weights{...}
audit_event    id, plan_id, block_id, actor_role, action, note, at
```
The `cost_*` breakdown on every block is not decoration — it is the explanation panel's data
source, and it is what makes "why this block?" answerable without writing any prose.

### Feedback

```
execution_log  block_id, actual_start, actual_end, tasks_completed[],
               overrun_min, overrun_reason{late_start,material,weather,
               crew,traffic_clearance,scope}, returned_at
```
This table is both the ML training set and the closing of the concept note's loop-10
"feedback" stage. Generate it synthetically with a *different* process than the duration
model family, so the ML is learning something real (doc 6).

## The connector abstraction — say this to judges

```python
class SourceConnector(Protocol):
    def fetch_tasks(self, since: date) -> list[TaskRecord]: ...
    def fetch_assets(self) -> list[AssetRecord]: ...

class TMSCsvConnector:   # today  — reads data/scenarios/...
class TMSApiConnector:   # tomorrow — hits the real endpoint. Not implemented.
```

Ship `TMSApiConnector` as a stub with the real field mapping documented in its docstring.
It costs an hour and it converts "we used fake data" from a weakness into a design decision.
Include a `docs/field-mapping.md` table showing our field ↔ their field for all five systems.
