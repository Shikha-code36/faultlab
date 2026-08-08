"""Finding: the fundamental unit of Stage 3's domain model (RFC 0001 SS3).

Schema validated by construction against real evidence
(scripts/prototype_findings.py, run against 011 and R001-R003) before this
module grew a storage convention and loaders. Storage: a `finding.json`
file colocated with its experiment/reference directory, the same
discovery pattern `slimybug.experiment.load_experiment` already uses --
not resolved by RFC 0001 itself, but the smallest choice consistent with
how `summary.csv`/`README.md`/`experiment.py` are already colocated per
experiment. `findings list`/`show` (RFC 0001 SS7) read from this; `compare`
isn't built yet -- see RFC 0001 SS10 Tier 2, item 3.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class Swept:
    variable: str
    tested_values: list

    @classmethod
    def from_dict(cls, d: dict) -> "Swept":
        return cls(variable=d["variable"], tested_values=d["tested_values"])


@dataclass(frozen=True)
class Scope:
    experiment_id: str
    fixed_params: dict
    swept: Swept

    @classmethod
    def from_dict(cls, d: dict) -> "Scope":
        return cls(experiment_id=d["experiment_id"], fixed_params=d["fixed_params"], swept=Swept.from_dict(d["swept"]))


@dataclass(frozen=True)
class Evidence:
    grade: str  # "research" | "reference"
    run_ids: dict  # {cell_label: [run_id, ...]} -- opaque cell labeling, adapter/experiment-defined
    n_per_condition: int | dict  # int when uniform; dict when escalation made it heterogeneous (e.g. R002)
    variance_reported: bool
    analysis_ref: str  # pointer, not embedded data

    @classmethod
    def from_dict(cls, d: dict) -> "Evidence":
        return cls(
            grade=d["grade"],
            run_ids=d["run_ids"],
            n_per_condition=d["n_per_condition"],
            variance_reported=d["variance_reported"],
            analysis_ref=d["analysis_ref"],
        )


@dataclass(frozen=True)
class ValidityCheck:
    name: str
    passed: bool
    note: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "ValidityCheck":
        return cls(name=d["name"], passed=d["passed"], note=d.get("note", ""))


@dataclass(frozen=True)
class Finding:
    id: str
    claim: str
    scope: Scope
    evidence: Evidence
    validity_checks: list[ValidityCheck]
    status: str  # "closed" | "closed-inconclusive" | "superseded"
    narrative_ref: str
    supersedes: str | None = None
    refines: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Finding":
        return cls(
            id=d["id"],
            claim=d["claim"],
            scope=Scope.from_dict(d["scope"]),
            evidence=Evidence.from_dict(d["evidence"]),
            validity_checks=[ValidityCheck.from_dict(v) for v in d["validity_checks"]],
            status=d["status"],
            narrative_ref=d["narrative_ref"],
            supersedes=d.get("supersedes"),
            refines=d.get("refines"),
        )

    def write(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_dict(), indent=2) + "\n")

    @classmethod
    def read(cls, path: Path) -> "Finding":
        return cls.from_dict(json.loads(path.read_text()))


def _lineage_linked(a: "Finding", b: "Finding") -> bool:
    """Direct refines/supersedes edge in either direction. Not transitive
    -- no real multi-hop chain exists yet (every current refines/supersedes
    edge is one hop) to ground a transitive rule against, so this only
    checks what's actually evidenced."""
    return a.refines == b.id or b.refines == a.id or a.supersedes == b.id or b.supersedes == a.id


def _fixed_params_overlap(a: "Finding", b: "Finding") -> bool:
    """True if a and b share at least one fixed_params key and agree on
    every key they both have -- not requiring identical dicts, since two
    Findings can be comparable while differing in params neither claim
    depends on."""
    shared_keys = set(a.scope.fixed_params) & set(b.scope.fixed_params)
    if not shared_keys:
        return False
    return all(a.scope.fixed_params[k] == b.scope.fixed_params[k] for k in shared_keys)


def compatible(a: "Finding", b: "Finding") -> tuple[bool, str]:
    """RFC 0001 SS10 Tier 2 item 3's compatibility rule for `findings
    compare`, resolved as an OR of its two candidate conditions rather
    than picking one -- the only real positive example available
    (011/R003) satisfies both simultaneously, so evidence doesn't yet
    disambiguate which one is "the" rule; each condition is validated
    independently against the negative pairs (every other combination
    among 011/R001/R002/R003, all correctly rejected). Returns
    (compatible, reason)."""
    if a.id == b.id:
        return False, "same Finding"
    if _lineage_linked(a, b):
        return True, "connected by a refines/supersedes edge"
    if a.scope.swept.variable == b.scope.swept.variable and _fixed_params_overlap(a, b):
        return True, "same swept.variable, overlapping fixed_params"
    if a.scope.swept.variable != b.scope.swept.variable:
        return False, (
            f"no refines/supersedes edge, and swept.variable differs "
            f"({a.scope.swept.variable!r} vs {b.scope.swept.variable!r})"
        )
    return False, "no refines/supersedes edge, and fixed_params don't overlap on any shared key"


def find_all() -> list[Path]:
    """Every finding.json under experiments/ or reference/, sorted by id."""
    from slimybug.experiment import EXPERIMENTS_DIR, REFERENCE_DIR

    paths = list(EXPERIMENTS_DIR.glob("*/finding.json")) + list(REFERENCE_DIR.glob("*/finding.json"))
    return sorted(paths, key=lambda p: p.parent.name)


def load(finding_id: str) -> Finding:
    """Locate <finding_id>-*/finding.json under experiments/ or reference/,
    mirroring slimybug.experiment.load_experiment's discovery pattern."""
    from slimybug.experiment import EXPERIMENTS_DIR, REFERENCE_DIR

    matches = sorted(EXPERIMENTS_DIR.glob(f"{finding_id}-*/finding.json")) or sorted(
        REFERENCE_DIR.glob(f"{finding_id}-*/finding.json")
    )
    if not matches:
        raise FileNotFoundError(f"no {finding_id}-*/finding.json found under experiments/ or reference/")
    if len(matches) > 1:
        raise RuntimeError(f"multiple finding.json match id {finding_id!r}: {matches}")
    return Finding.read(matches[0])
