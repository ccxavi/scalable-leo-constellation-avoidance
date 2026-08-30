# MAPPO toy environment

The deterministic toy environment validates the complete MAPPO learning loop
before orbital dynamics are introduced.

## Task

Four homogeneous agents each receive a local one-hot vector with seven entries.
The index containing `1` identifies the correct discrete action for that agent.
For example, `[0, 0, 0, 1, 0, 0, 0]` has correct action `3`.

Every episode contains one simultaneous decision:

```text
reset -> local observations + global state -> actions -> rewards -> terminal
```

Each correct response receives `+1`; each incorrect response receives `-1`.
The global state is the four local signals concatenated and is supplied only to
the centralized critic. Actor-only evaluation calls `select_actions()` with no
global state.

## Objective

A random seven-action policy should succeed about one seventh of the time. The
training runner must learn the local mapping and achieve greater than 90%
held-out actor-only success under its fixed seed. This verifies rollout
collection, PPO updates, shared policy learning, centralized critic handling,
and decentralized evaluation independently of OrbitZoo.

## Run

Use a Python environment containing PyTorch:

```sh
PYTHONPATH=src python -m orbitzoo.thesis.training.toy_mappo
```
