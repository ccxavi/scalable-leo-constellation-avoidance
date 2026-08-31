# Collision-avoidance environment

`CollisionAvoidanceEnv` is the thesis task layer built on OrbitZoo's Orekit
propagation. OrbitZoo provides bodies, orbital dynamics, and finite thrust
maneuvers; this environment defines the shared-policy RL problem.

## Environment interface

```python
local_observations, global_state = env.reset(seed=42)
next_local, next_global, rewards, dones, info = env.step(action_ids)
```

`action_ids` is one discrete action ID for every maneuvering spacecraft, in the
fixed `agent_names` order. All satellites act simultaneously. `local_observations`
has one row per satellite and is input only to the shared actor. `global_state`
is a flattened state for every moving body and is input only to the centralized
critic during training.

The first working observation contains the satellite's normalized Cartesian
position (3), velocity (3), and fuel fraction (1). It establishes and tests the
full physics-to-MAPPO data contract. It is not the final scalable observation:
the next observation change will replace this with a fixed-size relative
neighbour representation, so deployed actors do not depend on constellation
size.

## One environment step

```text
simultaneous action IDs
        -> finite maneuver commands
        -> OrbitZoo/Orekit propagation for one decision interval
        -> pairwise safety screening and collision check
        -> individual rewards, shared termination, diagnostics
```

The maneuver conversion uses the [maneuver contract](MANEUVER_CONTRACT.md): a
non-no-op direction becomes a finite constant-thrust burn. Fuel consumed and
realized delta-v are measured from spacecraft mass before and after propagation.
An action that cannot be completed within available fuel or the maximum burn
duration is changed to no-op and receives the configured infeasible-action
penalty.

## Safety and termination

Each step checks every pair of moving bodies. A physical collision occurs when
their present separation is no greater than their combined radii. A separate,
fast conjunction screen estimates time of closest approach under bounded linear
relative motion and flags a predicted miss distance below `safe_separation_meters`.

This screen is a deterministic development signal, not a probability-of-collision
model and not the final conjunction-assessment method. It lets us prove the RL
loop behaves correctly before selecting the thesis scenarios and uncertainty
model.

Any physical collision terminates the entire synchronous episode. Reaching the
configured decision-step horizon also terminates it. A common done flag is
returned for every policy satellite because they are one cooperative team.

## Rewards and diagnostics

Safety dominates maneuver economy: collision, then unresolved unsafe conjunction,
then actual delta-v cost. Resolving a previously unsafe conjunction earns a
bounded positive reward. The initial values are versioned in the experiment
configuration as provisional development weights; they require reward-ablation
and sensitivity experiments before thesis results are reported.

`info` records safety assessments, maneuver accounting, rejected actions, and
the termination reason. `env.diagnostics` accumulates per-satellite delta-v and
fuel use, minimum separation, and collision pairs over the episode.

## Development fixture

`development_environment_kwargs()` creates four spacecraft and one debris
object in a small deterministic 500 km circular-orbit setup. The debris begins
near the first spacecraft with a closing along-track velocity. Use it for smoke
tests and interface development only. It is deliberately not a final training
scenario generator or an evaluation benchmark.
