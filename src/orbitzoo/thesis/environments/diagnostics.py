"""Episode-level accounting for collision-avoidance environment runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from orbitzoo.thesis.maneuvers.contract import ManeuverResult


@dataclass
class EpisodeDiagnostics:
    """Mutable metrics accumulated over one reset-to-termination episode."""

    agent_names: list[str]
    cumulative_delta_v_mps: dict[str, float] = field(init=False)
    cumulative_fuel_kg: dict[str, float] = field(init=False)
    minimum_separation_meters: float = float("inf")
    collision_pairs: list[tuple[str, str]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.cumulative_delta_v_mps = {name: 0.0 for name in self.agent_names}
        self.cumulative_fuel_kg = {name: 0.0 for name in self.agent_names}

    def record_maneuvers(self, results: Mapping[str, ManeuverResult]) -> None:
        for name, result in results.items():
            self.cumulative_delta_v_mps[name] += result.actual_delta_v_mps
            self.cumulative_fuel_kg[name] += result.fuel_consumed_kg

    def record_minimum_separation(self, separation_meters: float) -> None:
        self.minimum_separation_meters = min(self.minimum_separation_meters, separation_meters)
