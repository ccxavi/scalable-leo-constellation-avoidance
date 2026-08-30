import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from orbitzoo.thesis.maneuvers.actions import ManeuverAction
from orbitzoo.thesis.maneuvers.contract import (
    ManeuverConfig,
    ManeuverInfeasibleError,
    actual_delta_v_mps,
    build_maneuver_command,
    measure_maneuver_result,
    orbitzoo_action_inputs,
)


@pytest.fixture
def maneuver_config():
    return ManeuverConfig(
        commanded_delta_v_mps=0.01,
        maximum_thrust_newtons=0.1,
        specific_impulse_seconds=300.0,
        maximum_burn_duration_seconds=120.0,
    )


def test_no_op_has_zero_thrust_burn_and_delta_v(maneuver_config):
    command = build_maneuver_command(ManeuverAction.NO_OP, 300.0, maneuver_config)

    assert command.name == "no-op"
    assert command.thrust_rsw_newtons == (0.0, 0.0, 0.0)
    assert command.burn_duration_seconds == 0.0
    assert command.commanded_delta_v_mps == 0.0
    assert command.expected_propellant_kg == 0.0


def test_opposite_directions_are_negatives_with_equal_magnitude(maneuver_config):
    prograde = build_maneuver_command(ManeuverAction.PROGRADE, 300.0, maneuver_config)
    retrograde = build_maneuver_command(ManeuverAction.RETROGRADE, 300.0, maneuver_config)
    radial_out = build_maneuver_command(ManeuverAction.RADIAL_OUT, 300.0, maneuver_config)
    radial_in = build_maneuver_command(ManeuverAction.RADIAL_IN, 300.0, maneuver_config)

    assert retrograde.thrust_rsw_newtons == tuple(-value for value in prograde.thrust_rsw_newtons)
    assert radial_in.thrust_rsw_newtons == tuple(-value for value in radial_out.thrust_rsw_newtons)
    assert math.isclose(prograde.commanded_delta_v_mps, radial_out.commanded_delta_v_mps)
    assert math.isclose(prograde.burn_duration_seconds, radial_out.burn_duration_seconds)


def test_same_delta_v_requires_longer_burn_for_a_heavier_spacecraft(maneuver_config):
    light = build_maneuver_command(ManeuverAction.PROGRADE, 200.0, maneuver_config)
    heavy = build_maneuver_command(ManeuverAction.PROGRADE, 400.0, maneuver_config)

    assert heavy.expected_propellant_kg > light.expected_propellant_kg
    assert heavy.burn_duration_seconds > light.burn_duration_seconds


def test_contract_rejects_invalid_or_infeasible_commands(maneuver_config):
    with pytest.raises(ValueError, match="unknown"):
        build_maneuver_command(7, 300.0, maneuver_config)
    with pytest.raises(ManeuverInfeasibleError, match="insufficient"):
        build_maneuver_command(ManeuverAction.PROGRADE, 300.0, maneuver_config, available_propellant_kg=0.0)
    with pytest.raises(ManeuverInfeasibleError, match="duration"):
        build_maneuver_command(
            ManeuverAction.PROGRADE,
            300.0,
            ManeuverConfig(0.01, 0.1, 300.0, 0.001),
        )


def test_actual_delta_v_matches_the_commanded_mass_change(maneuver_config):
    command = build_maneuver_command(ManeuverAction.PROGRADE, 300.0, maneuver_config)
    mass_after = 300.0 - command.expected_propellant_kg

    result = measure_maneuver_result(command, 300.0, mass_after, maneuver_config.specific_impulse_seconds)

    assert math.isclose(result.actual_delta_v_mps, command.commanded_delta_v_mps, rel_tol=1e-10)
    assert math.isclose(actual_delta_v_mps(300.0, mass_after, 300.0), command.commanded_delta_v_mps, rel_tol=1e-10)


def test_orbitzoo_inputs_keep_each_spacecraft_duration(maneuver_config):
    commands = {
        "satellite-a": build_maneuver_command(ManeuverAction.PROGRADE, 300.0, maneuver_config),
        "satellite-b": build_maneuver_command(ManeuverAction.NO_OP, 300.0, maneuver_config),
    }

    actions, durations = orbitzoo_action_inputs(commands)

    assert actions["satellite-a"] == [0.0, 0.1, 0.0]
    assert durations["satellite-b"] == 0.0
