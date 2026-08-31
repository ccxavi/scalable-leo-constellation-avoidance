from types import SimpleNamespace

import numpy as np

from orbitzoo.thesis.environments.rewards import RewardConfig, calculate_rewards
from orbitzoo.thesis.environments.safety import SafetyConfig, assess_pair
from orbitzoo.thesis.maneuvers.contract import (
    ManeuverConfig,
    build_maneuver_command,
    measure_maneuver_result,
)


def body(name: str, position: list[float], velocity: list[float], radius: float = 1.0):
    return SimpleNamespace(name=name, position=np.array(position), velocity=np.array(velocity), radius=radius)


def test_linear_screen_detects_future_unsafe_conjunction() -> None:
    assessment = assess_pair(
        body("satellite", [0, 0, 0], [0, 0, 0]),
        body("debris", [2_000, 0, 0], [-10, 0, 0]),
        SafetyConfig(safe_separation_meters=1_000, screening_horizon_seconds=300),
    )
    assert assessment.current_separation_meters == 2_000
    assert assessment.time_to_closest_approach_seconds == 200
    assert assessment.predicted_miss_distance_meters == 0
    assert assessment.is_unsafe
    assert not assessment.is_collision


def test_collision_reward_dominates_maneuver_cost() -> None:
    config = ManeuverConfig(0.01, 0.1, 300, 60)
    command = build_maneuver_command(0, 250, config, available_propellant_kg=50)
    result = measure_maneuver_result(command, 250, 250, 300)
    collision = assess_pair(
        body("satellite", [0, 0, 0], [0, 0, 0]),
        body("debris", [1, 0, 0], [0, 0, 0]),
        SafetyConfig(),
    )
    rewards = calculate_rewards(
        ["satellite"], {"satellite": command}, {"satellite": result}, [], [collision], RewardConfig()
    )
    assert rewards == {"satellite": -100.0}
