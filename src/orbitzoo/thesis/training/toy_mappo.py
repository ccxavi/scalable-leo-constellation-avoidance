"""Train and evaluate MAPPO against the deterministic toy environment."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import torch

from orbitzoo.rl_algorithms.mappo import MAPPO
from orbitzoo.thesis.environments.toy_marl import DiscreteResponseToyEnv


@dataclass(frozen=True)
class ToyTrainingResult:
    """Summary of a deterministic MAPPO toy-training run."""

    policy: MAPPO
    initial_success_rate: float
    final_success_rate: float
    update_metrics: list[dict[str, float]]


def evaluate_toy_policy(policy: MAPPO, episodes: int = 128, seed: int = 10_000) -> float:
    """Evaluate actor-only decentralized action selection on held-out episodes."""
    environment = DiscreteResponseToyEnv(
        num_agents=4,
        num_actions=policy.num_actions,
        seed=seed,
    )
    successes: list[float] = []
    for _ in range(episodes):
        local_observations, _ = environment.reset()
        actions = policy.select_actions(local_observations, deterministic=True).numpy()
        _, _, _, _, info = environment.step(actions)
        successes.append(info["success_rate"])
    return float(np.mean(successes))


def train_toy_policy(
    *,
    seed: int = 42,
    updates: int = 32,
    rollout_episodes: int = 32,
    device: torch.device | str = "cpu",
) -> ToyTrainingResult:
    """Train a shared MAPPO actor on the local-response task."""
    if updates <= 0 or rollout_episodes <= 0:
        raise ValueError("updates and rollout_episodes must be positive")

    np.random.seed(seed)
    torch.manual_seed(seed)
    environment = DiscreteResponseToyEnv(num_agents=4, num_actions=7, seed=seed)
    policy = MAPPO(
        local_observation_dim=environment.local_observation_dim,
        global_state_dim=environment.global_state_dim,
        num_actions=environment.num_actions,
        actor_hidden_dims=(32,),
        critic_hidden_dims=(32,),
        actor_learning_rate=3e-3,
        critic_learning_rate=1e-3,
        update_epochs=4,
        minibatch_size=128,
        device=device,
    )
    initial_success_rate = evaluate_toy_policy(policy)
    update_metrics: list[dict[str, float]] = []

    for _ in range(updates):
        final_local_observations: np.ndarray | None = None
        final_global_state: np.ndarray | None = None
        final_dones: np.ndarray | None = None
        for _ in range(rollout_episodes):
            local_observations, global_state = environment.reset()
            actions, log_probabilities, values = policy.act(local_observations, global_state)
            next_local_observations, next_global_state, rewards, dones, _ = environment.step(actions.numpy())
            policy.store_step(
                local_observations,
                global_state,
                actions,
                log_probabilities,
                rewards,
                dones,
                values,
            )
            final_local_observations = next_local_observations
            final_global_state = next_global_state
            final_dones = dones
        update_metrics.append(policy.update(final_local_observations, final_global_state, final_dones))

    return ToyTrainingResult(
        policy=policy,
        initial_success_rate=initial_success_rate,
        final_success_rate=evaluate_toy_policy(policy),
        update_metrics=update_metrics,
    )


if __name__ == "__main__":
    result = train_toy_policy()
    print(f"Initial actor-only success rate: {result.initial_success_rate:.1%}")
    print(f"Final actor-only success rate: {result.final_success_rate:.1%}")
