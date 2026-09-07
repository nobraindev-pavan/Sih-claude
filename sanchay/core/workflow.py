"""Block sanction workflow and audit trail.

The deliverable in this domain is not a chart. It is a **sanctioned block plan
with a record of who approved what and why** — that is what makes the system
deployable rather than a science project, and it is the direct answer to "how
would this actually be used?".

The lifecycle mirrors how a block demand actually moves, and how BDMS tracks it:

    proposed ──► under_review ──► sanctioned ──► issued ──► executed ──► returned
        │             │
        └──────────► rejected

Two rules that make the trail worth having:

  * **Every transition is recorded with an actor and a reason**, including the
    ones the system makes for itself. A trail with gaps in it is not a trail.
  * **An overridden recommendation is data.** When a planner moves or rejects a
    block, the reason is captured in a form that can be counted later. Closing
    that loop — learning which recommendations get overridden and why — is the
    deployment plan, and it starts with recording it properly.

Nothing here decides anything. It records decisions people make.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

#: Who may act. Real authority differs by railway and by division; these are the
#: divisional roles the plan is written for (docs/02-domain-primer.md).
ROLES = {
    "DOM": "Divisional Operating Manager — sanctions the plan",
    "CHC": "Chief Controller — issues and monitors blocks on the day",
    "SR_DEN": "Sr. Divisional Engineer — Engineering demands",
    "SR_DSTE": "Sr. Divisional Signal & Telecom Engineer — S&T demands",
    "SR_DEE": "Sr. Divisional Electrical Engineer (TrD) — traction demands",
    "SYSTEM": "SANCHAY — proposals and automatic transitions",
}

#: state -> the states it may move to, and who may make each move.
TRANSITIONS: dict[str, dict[str, tuple[str, ...]]] = {
    "proposed": {
        "under_review": ("DOM", "CHC", "SR_DEN", "SR_DSTE", "SR_DEE"),
        "rejected": ("DOM",),
    },
    "under_review": {
        "sanctioned": ("DOM",),
        "rejected": ("DOM",),
        "proposed": ("DOM", "CHC"),
    },
    "sanctioned": {
        "issued": ("CHC",),
        "rejected": ("DOM",),
    },
    "issued": {"executed": ("CHC",)},
    "executed": {"returned": ("CHC",)},
    "returned": {},
    "rejected": {},
}
TERMINAL = ("returned", "rejected")

#: Why a planner overrode a recommendation. A free-text box produces prose
#: nobody can count; a fixed list produces a distribution you can act on.
OVERRIDE_REASONS = {
    "traffic": "conflicts with traffic the plan did not know about",
    "resources": "gang or machine not actually available",
    "materials": "materials not in position",
    "site_access": "site access not available",
    "safety": "safety or protection concern",
    "clubbing": "should be clubbed with other work",
    "priority": "priority judged differently",
    "other": "other (see note)",
}


class WorkflowError(Exception):
    """An illegal transition. Raised rather than silently ignored — a workflow
    that lets you skip a step is not a workflow."""


@dataclass
class AuditEvent:
    id: str
    plan_id: str
    block_id: str | None
    at: float
    actor_role: str
    action: str
    from_state: str | None
    to_state: str | None
    reason_code: str | None
    note: str

    def line(self) -> str:
        when = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.at))
        move = (f"{self.from_state} -> {self.to_state}"
                if self.to_state else self.action)
        target = self.block_id or "(plan)"
        tail = f"  [{self.reason_code}] {self.note}".rstrip() if self.reason_code else (
            f"  {self.note}" if self.note else "")
        return f"{when}  {self.actor_role:8s} {target:10s} {move}{tail}"


@dataclass
class BlockRecord:
    block_id: str
    state: str = "proposed"
    sanctioned_by: str | None = None
    sanctioned_at: float | None = None


@dataclass
class PlanFile:
    """A plan under review, with its blocks' states and the full trail."""
    plan_id: str
    scenario: str
    created: float = field(default_factory=time.time)
    blocks: dict[str, BlockRecord] = field(default_factory=dict)
    events: list[AuditEvent] = field(default_factory=list)

    # -- construction --------------------------------------------------
    @classmethod
    def from_plan(cls, plan, scenario_name: str, plan_id: str | None = None) -> "PlanFile":
        pf = cls(plan_id=plan_id or uuid.uuid4().hex[:12], scenario=scenario_name)
        pf.blocks = {b.id: BlockRecord(b.id) for b in plan.blocks}
        pf._record("SYSTEM", "proposed", None, None, None,
                   f"{len(plan.blocks)} block(s) proposed by the optimizer, "
                   f"{len(plan.unscheduled_task_ids)} task(s) deferred")
        return pf

    def _record(self, actor: str, action: str, block_id: str | None,
                from_state: str | None, to_state: str | None,
                note: str = "", reason_code: str | None = None) -> AuditEvent:
        ev = AuditEvent(id=uuid.uuid4().hex[:10], plan_id=self.plan_id,
                        block_id=block_id, at=time.time(), actor_role=actor,
                        action=action, from_state=from_state, to_state=to_state,
                        reason_code=reason_code, note=note)
        self.events.append(ev)
        return ev

    # -- transitions ---------------------------------------------------
    def transition(self, block_id: str, to_state: str, actor_role: str,
                   note: str = "", reason_code: str | None = None) -> AuditEvent:
        if actor_role not in ROLES:
            raise WorkflowError(f"unknown role {actor_role}")
        rec = self.blocks.get(block_id)
        if rec is None:
            raise WorkflowError(f"block {block_id} is not in this plan")
        allowed = TRANSITIONS.get(rec.state, {})
        if to_state not in allowed:
            raise WorkflowError(
                f"{block_id} is {rec.state}; it cannot move to {to_state}"
                + (f" (only {', '.join(allowed)})" if allowed else
                   " because that is a final state"))
        if actor_role not in allowed[to_state]:
            raise WorkflowError(
                f"{actor_role} cannot move a block from {rec.state} to "
                f"{to_state} — that is for {' or '.join(allowed[to_state])}")
        if to_state == "rejected" and not reason_code:
            raise WorkflowError(
                "rejecting a block needs a reason code; an override nobody "
                "recorded a reason for teaches us nothing")
        if reason_code and reason_code not in OVERRIDE_REASONS:
            raise WorkflowError(f"unknown reason code {reason_code}")

        prev, rec.state = rec.state, to_state
        if to_state == "sanctioned":
            rec.sanctioned_by, rec.sanctioned_at = actor_role, time.time()
        return self._record(actor_role, "transition", block_id, prev, to_state,
                            note, reason_code)

    def sanction_all(self, actor_role: str = "DOM", note: str = "") -> list[AuditEvent]:
        """Sanction everything currently under review. The bulk action a DOM
        actually wants, having reviewed the exceptions individually."""
        out = []
        for bid, rec in self.blocks.items():
            if rec.state == "under_review":
                out.append(self.transition(bid, "sanctioned", actor_role, note))
        return out

    def review_all(self, actor_role: str = "DOM") -> list[AuditEvent]:
        return [self.transition(bid, "under_review", actor_role)
                for bid, rec in self.blocks.items() if rec.state == "proposed"]

    # -- reporting -----------------------------------------------------
    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for rec in self.blocks.values():
            out[rec.state] = out.get(rec.state, 0) + 1
        return dict(sorted(out.items()))

    def override_reasons(self) -> dict[str, int]:
        """The distribution that makes the trail worth keeping: which of our
        recommendations get rejected, and why."""
        out: dict[str, int] = {}
        for ev in self.events:
            if ev.to_state == "rejected" and ev.reason_code:
                out[ev.reason_code] = out.get(ev.reason_code, 0) + 1
        return dict(sorted(out.items(), key=lambda kv: -kv[1]))

    def trail(self, block_id: str | None = None) -> list[AuditEvent]:
        return [e for e in self.events
                if block_id is None or e.block_id in (block_id, None)]

    def to_json(self) -> str:
        return json.dumps({
            "planId": self.plan_id, "scenario": self.scenario,
            "created": self.created,
            "blocks": {k: asdict(v) for k, v in self.blocks.items()},
            "events": [asdict(e) for e in self.events],
        }, indent=2)

    def save(self, path: Path | str) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json())
        return path

    @classmethod
    def load(cls, path: Path | str) -> "PlanFile":
        raw = json.loads(Path(path).read_text())
        pf = cls(plan_id=raw["planId"], scenario=raw["scenario"],
                 created=raw["created"])
        pf.blocks = {k: BlockRecord(**v) for k, v in raw["blocks"].items()}
        pf.events = [AuditEvent(**e) for e in raw["events"]]
        return pf
