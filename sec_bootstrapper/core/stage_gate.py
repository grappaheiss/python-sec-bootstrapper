"""Stage-gate persistence and enforcement for staged delivery."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional


@dataclass
class StageRecord:
    """Execution state for one stage."""

    status: str = "pending"
    completed_at: Optional[str] = None
    evidence: str = ""


@dataclass
class GateState:
    """Entire gate state."""

    stages: Dict[str, StageRecord] = field(
        default_factory=lambda: {
            "stage1": StageRecord(),
            "stage2": StageRecord(),
            "stage3": StageRecord(),
        }
    )


class StageGateError(Exception):
    """Raised when stage gate checks fail."""


class StageGateManager:
    """Reads/writes stage gate state and enforces stage prerequisites."""

    def __init__(self, state_file: Path):
        self.state_file = state_file
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state = self._load()

    def can_run(self, stage: str) -> tuple[bool, str]:
        """Validate if a stage can start based on prerequisite completion."""
        if stage == "stage1":
            return True, "stage1 has no prerequisites"

        if stage == "stage2":
            if self.state.stages["stage1"].status == "accepted":
                return True, "stage1 accepted"
            return False, "stage2 blocked: stage1 acceptance checks are not recorded"

        if stage == "stage3":
            if self.state.stages["stage2"].status == "accepted":
                return True, "stage2 accepted"
            return False, "stage3 blocked: stage2 acceptance checks are not recorded"

        return False, f"unknown stage: {stage}"

    def mark(self, stage: str, status: str, evidence: str = "") -> None:
        """Set stage status and persist."""
        if stage not in self.state.stages:
            raise StageGateError(f"Unknown stage: {stage}")

        self.state.stages[stage].status = status
        self.state.stages[stage].completed_at = datetime.utcnow().isoformat()
        self.state.stages[stage].evidence = evidence
        self._save()

    def _load(self) -> GateState:
        if not self.state_file.exists():
            return GateState()

        with open(self.state_file) as f:
            raw = json.load(f)

        state = GateState()
        for name, payload in raw.get("stages", {}).items():
            if name in state.stages:
                state.stages[name] = StageRecord(
                    status=payload.get("status", "pending"),
                    completed_at=payload.get("completed_at"),
                    evidence=payload.get("evidence", ""),
                )
        return state

    def _save(self) -> None:
        payload = {
            "stages": {
                name: {
                    "status": record.status,
                    "completed_at": record.completed_at,
                    "evidence": record.evidence,
                }
                for name, record in self.state.stages.items()
            }
        }
        with open(self.state_file, "w") as f:
            json.dump(payload, f, indent=2)
