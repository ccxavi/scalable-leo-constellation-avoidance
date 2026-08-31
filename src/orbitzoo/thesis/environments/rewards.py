"""Configurable, safety-first reward calculation for collision avoidance."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from orbitzoo.thesis.environments.safety import PairSafetyAssessment, involved_agents
from orbitzoo.thesis.maneuvers.contract import ManeuverCommand, ManeuverResult


@dataclass(frozen=True)
class RewardConfig:
    """Provisional reward weights; safety penalties deliberately dominate cost."""

    collision_penalty: float = -100.0
    unsafe_penalty: float = -10.0
    resolution_reward: float = 5.0
    delta_v_penalty_per_mps: float = 1.0
    unnecessary_maneuver_penalty: float = -0.1
    infeasible_maneuver_penalty: float = -2.0

    def validate(self) -> None:
        if self.collision_penalty >= 0 or self.unsafe_penalty >= 0:
            raise ValueError("collision_penalty and unsafe_penalty must be negative")
        if self.resolution_reward < 0 or self.delta_v_penalty_per_mps < 0:
            raise ValueError("resolution_reward and delta_v_penalty_per_mps cannot be negative")
        if self.unnecessary_maneuver_penalty > 0 or self.infeasible_maneuver_penalty > 0:
            raise ValueError("maneuver penalties cannot be positive")


def calculate_rewards(
    agent_names: list[str],
    commands: Mapping[str, ManeuverCommand],
    results: Mapping[str, ManeuverResult],
    assessments_before: list[PairSafetyAssessment],
    assessments_after: list[PairSafetyAssessment],
    config: RewardConfig,
    rejected_agents: set[str] | None = None,
) -> dict[str, float]:
    """Calculate individual rewards from safety outcome and actual maneuver cost."""
    config.validate()
    rejected_agents = rejected_agents or set()
    unsafe_before = involved_agents(assessments_before, "is_unsafe")
    unsafe_after = involved_agents(assessments_after, "is_unsafe")
    collision_after = involved_agents(assessments_after, "is_collision")
    rewards: dict[str, float] = {}
    for agent in agent_names:
        reward = -config.delta_v_penalty_per_mps * results[agent].actual_delta_v_mps
        if not commands[agent].is_no_op and agent not in unsafe_before:
            reward += config.unnecessary_maneuver_penalty
        if agent in rejected_agents:
            reward += config.infeasible_maneuver_penalty
        if agent in collision_after:
            reward += config.collision_penalty
        elif agent in unsafe_after:
            reward += config.unsafe_penalty
        elif agent in unsafe_before:
            reward += config.resolution_reward
        rewards[agent] = reward
    return rewards
