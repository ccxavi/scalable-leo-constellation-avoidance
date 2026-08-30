"""A deterministic one-step environment for MAPPO integration testing.

Each homogeneous agent receives a one-hot local signal identifying the correct
action. The environment deliberately has no orbital physics: it validates the
RL data flow before collision-avoidance dynamics are introduced.
"""

from __future__ import annotations

from typing import Any

import numpy as np


class DiscreteResponseToyEnv:
    """One-step multi-agent task with a local seven-action response rule.

    ``reset`` samples one target action per agent. Every agent observes only
    its own target as a one-hot vector. The global state is all agent signals
    concatenated, and is intended only for a centralized critic.
    """

    def __init__(self, num_agents: int = 4, num_actions: int = 7, seed: int | None = None) -> None:
        if num_agents < 2:
            raise ValueError("num_agents must be at least 2")
        if num_actions < 2:
            raise ValueError("num_actions must be at least 2")
        self.num_agents = num_agents
        self.num_actions = num_actions
        self._rng = np.random.default_rng(seed)
        self._target_actions: np.ndarray | None = None
        self._is_done = True

    @property
    def local_observation_dim(self) -> int:
        return self.num_actions

    @property
    def global_state_dim(self) -> int:
        return self.num_agents * self.num_actions

    def reset(self, seed: int | None = None) -> tuple[np.ndarray, np.ndarray]:
        """Start a one-step episode and return local observations/global state."""
        if seed is not None:
            self._rng = np.random.default_rng(seed)
        self._target_actions = self._rng.integers(0, self.num_actions, size=self.num_agents)
        self._is_done = False
        local_observations = np.eye(self.num_actions, dtype=np.float32)[self._target_actions]
        return local_observations, local_observations.reshape(-1).copy()

    def step(
        self, actions: np.ndarray | list[int]
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
        """Score one simultaneous action for every agent and end the episode."""
        if self._target_actions is None or self._is_done:
            raise RuntimeError("call reset() before step()")
        action_array = np.asarray(actions, dtype=np.int64)
        if action_array.shape != (self.num_agents,):
            raise ValueError("actions must have shape [num_agents]")
        if np.any(action_array < 0) or np.any(action_array >= self.num_actions):
            raise ValueError(f"actions must be integers in [0, {self.num_actions - 1}]")

        correct = action_array == self._target_actions
        rewards = np.where(correct, 1.0, -1.0).astype(np.float32)
        dones = np.ones(self.num_agents, dtype=bool)
        local_observations = np.eye(self.num_actions, dtype=np.float32)[self._target_actions]
        global_state = local_observations.reshape(-1).copy()
        self._is_done = True
        return local_observations, global_state, rewards, dones, {
            "target_actions": self._target_actions.copy(),
            "success_rate": float(correct.mean()),
        }
