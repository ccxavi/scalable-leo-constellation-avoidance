# Thesis implementation

This directory contains the implementation for **Scalable Collision Avoidance
in Large Low Earth Orbit Constellations**. It is built on the local OrbitZoo
fork, but thesis-specific components live under `src/orbitzoo/thesis/` so the
generic orbital-dynamics library remains reusable.

## Architecture

The planned system uses discrete MAPPO under Centralized Training with
Decentralized Execution (CTDE):

```text
local k-neighbor observation -> shared actor -> one maneuver per satellite
full training-only constellation state -> centralized critic -> learning signal
```

The actor will use seven actions: no-op, prograde, retrograde, radial-out,
radial-in, cross-track positive, and cross-track negative. The critic is used
only while training; the deployed/evaluated policy uses the shared actor and
each satellite's local observation only.

## Repository layout

```text
src/orbitzoo/                 reusable OrbitZoo code
src/orbitzoo/thesis/          thesis-specific source code
configs/                      versioned JSON experiment configurations
tests/                        automated tests
runs/                         generated metrics, metadata, and TensorBoard logs (ignored)
checkpoints/                  generated model files (ignored)
```

## Reproducible runs

Every run must save:

- `config.json`: the exact experiment configuration;
- `environment_info.json`: device, platform, Python, and PyTorch details;
- `metrics.csv` and TensorBoard data when training is added;
- model checkpoints when MAPPO is added.

`orbitzoo.thesis.runtime.select_device()` selects CUDA when available, then
Apple Metal (MPS), otherwise CPU. The choice is recorded for each run.

The initial configuration is [configs/mappo_toy.json](../configs/mappo_toy.json).
It fixes the architectural defaults—not final experimental values—to 16 agents,
four local neighbors, seven discrete actions, and a 300-second decision interval.

## Current status

The discrete MAPPO implementation is validated independently of orbital physics.
See [MAPPO.md](MAPPO.md) for its CTDE design and rollout API. The immediate
implementation objective is to validate learning in a small deterministic toy
environment before connecting the policy to orbital simulation.
