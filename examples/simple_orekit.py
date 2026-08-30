"""A minimal maneuvering spacecraft mission using Orekit."""

import math

from orbitzoo import OrbitZoo


EARTH_RADIUS = 6_378_136.3  # meters
EARTH_MU = 3.986004418e14  # m^3 / s^2
ALTITUDE = 500_000.0  # meters
ORBIT_RADIUS = EARTH_RADIUS + ALTITUDE
CIRCULAR_SPEED = math.sqrt(EARTH_MU / ORBIT_RADIUS)


spacecraft = {
    "name": "learner_1",
    # Orekit uses Cartesian state: [x, y, z, vx, vy, vz].
    "initial_state": [ORBIT_RADIUS, 0.0, 0.0, 0.0, CIRCULAR_SPEED, 0.0],
    "dry_mass": 500.0,
    "initial_fuel_mass": 100.0,
    "isp": 300.0,
    "forces": ["gravity_hf"],
}

interface_config = {
    "zoom": 4.5,
    "bodies": {
        "show_label": True,
        "show_trail": True,
        "show_thrust": True,
        "trail_last_steps": 500,
    },
}

env = OrbitZoo(
    dynamics_library="orekit",
    spacecrafts=[spacecraft],
    step_size=10.0,
    render=True,
    interface_config=interface_config,
)

body = env.dynamics.get_body("learner_1")
print(f"Initial altitude: {(body.get_altitude() - EARTH_RADIUS) / 1000:.1f} km")
print("Applying 20 N of along-track thrust for 60 seconds...")

step = 0
while True:
    # Actions are thrust vectors [R, S, W] in newtons. Burn for six 10 s steps.
    actions = {"learner_1": [0.0, 20.0, 0.0]} if step < 6 else None
    env.step(actions=actions)
    env.render()

    step += 1
    if step == 6:
        altitude = (body.get_altitude() - EARTH_RADIUS) / 1000
        print(f"Post-burn altitude: {altitude:.1f} km")
        print("Burn complete; spacecraft is now coasting. Close the window to stop.")
