import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from orbitzoo.thesis.environments.toy_marl import DiscreteResponseToyEnv


def test_reset_is_deterministic_for_a_given_seed():
    environment = DiscreteResponseToyEnv()

    first_local, first_global = environment.reset(seed=17)
    second_local, second_global = environment.reset(seed=17)

    assert np.array_equal(first_local, second_local)
    assert np.array_equal(first_global, second_global)


def test_step_rewards_correct_actions_and_ends_episode():
    environment = DiscreteResponseToyEnv(num_agents=4, num_actions=7)
    local_observations, global_state = environment.reset(seed=3)
    correct_actions = np.argmax(local_observations, axis=1)

    _, _, rewards, dones, info = environment.step(correct_actions)

    assert local_observations.shape == (4, 7)
    assert global_state.shape == (28,)
    assert np.array_equal(rewards, np.ones(4, dtype=np.float32))
    assert np.array_equal(dones, np.ones(4, dtype=bool))
    assert info["success_rate"] == 1.0


def test_step_rejects_invalid_actions_and_repeated_steps():
    environment = DiscreteResponseToyEnv()
    environment.reset(seed=1)

    with pytest.raises(ValueError, match="shape"):
        environment.step([0, 1])
    with pytest.raises(ValueError, match="integers"):
        environment.step([0, 1, 2, 7])

    environment.step([0, 1, 2, 3])
    with pytest.raises(RuntimeError, match="reset"):
        environment.step([0, 1, 2, 3])
