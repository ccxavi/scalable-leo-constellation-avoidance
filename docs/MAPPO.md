# Discrete MAPPO implementation

`orbitzoo.rl_algorithms.mappo.MAPPO` is the shared-policy training component for
the thesis. It implements a discrete variant of Multi-Agent
Proximal Policy Optimization under Centralized Training with Decentralized
Execution (CTDE).

## Networks

The actor is shared across every homogeneous satellite:

```text
local observation for agent i -> actor -> probabilities for 7 maneuver actions
```

The critic is used only during training and predicts a separate value for each
agent:

```text
global state + local observation for agent i -> critic -> V(global state, agent i)
```

This allows agents to receive individual safety and fuel rewards while the
critic retains centralized context. Only the actor is needed during evaluation
or decentralized execution.

## Rollout API

At every simultaneous environment step, call:

```python
actions, log_probabilities, values = policy.act(local_observations, global_state)

# Advance the environment, then calculate one reward and terminal flag per agent.
policy.store_step(
    local_observations,
    global_state,
    actions,
    log_probabilities,
    rewards,
    dones,
    values,
)
```

After a fixed rollout, bootstrap unfinished trajectories and update:

```python
metrics = policy.update(final_local_observations, final_global_state, final_dones)
```

`local_observations` has shape `[num_agents, local_observation_dim]` and
`global_state` has shape `[global_state_dim]`. The number of agents must remain
constant within a rollout, but the actor is shared and can be reused for a
different population size during evaluation if the local observation shape stays
fixed.

For decentralized evaluation, no global state or critic is needed:

```python
actions = policy.select_actions(local_observations, deterministic=True)
```

## Checkpoints

`policy.save(path)` saves actor and critic weights, optimizer state, architecture
dimensions, hyperparameters, and training counters. `policy.load(path)` restores
them into an instance with matching dimensions.
