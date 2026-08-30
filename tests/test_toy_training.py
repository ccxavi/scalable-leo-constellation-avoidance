import sys
from pathlib import Path

import pytest

pytest.importorskip("torch")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from orbitzoo.thesis.training.toy_mappo import train_toy_policy


def test_shared_actor_learns_the_toy_local_response_rule():
    result = train_toy_policy(updates=24, rollout_episodes=32)

    assert result.initial_success_rate < 0.4
    assert result.final_success_rate > 0.9
    assert len(result.update_metrics) == 24
