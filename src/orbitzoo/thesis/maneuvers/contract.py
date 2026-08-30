"""Translate discrete actions into finite Orekit thrust maneuvers.

The actor selects a direction only. A fixed commanded delta-v magnitude is
converted to a finite burn using the spacecraft's current mass, maximum thrust,
and specific impulse. This preserves a consistent maneuver size as fuel is used.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping

from orbitzoo.thesis.maneuvers.actions import ManeuverAction


STANDARD_GRAVITY_MPS2 = 9.80665


class ManeuverInfeasibleError(ValueError):
    """Raised when a requested maneuver cannot be performed safely."""


@dataclass(frozen=True)
class ManeuverConfig:
    """Fixed physical parameters for one discrete maneuver primitive."""

    commanded_delta_v_mps: float
    maximum_thrust_newtons: float
    specific_impulse_seconds: float
    maximum_burn_duration_seconds: float

    def validate(self) -> None:
        for name, value in (
            ("commanded_delta_v_mps", self.commanded_delta_v_mps),
            ("maximum_thrust_newtons", self.maximum_thrust_newtons),
            ("specific_impulse_seconds", self.specific_impulse_seconds),
            ("maximum_burn_duration_seconds", self.maximum_burn_duration_seconds),
        ):
            if value <= 0:
                raise ValueError(f"{name} must be positive")


@dataclass(frozen=True)
class ManeuverCommand:
    """A fully specified finite burn ready to pass to OrbitZoo."""

    action: ManeuverAction
    thrust_rsw_newtons: tuple[float, float, float]
    burn_duration_seconds: float
    commanded_delta_v_mps: float
    expected_propellant_kg: float

    @property
    def name(self) -> str:
        return self.action.display_name

    @property
    def is_no_op(self) -> bool:
        return self.action is ManeuverAction.NO_OP


@dataclass(frozen=True)
class ManeuverResult:
    """Measured maneuver accounting derived from Orekit spacecraft masses."""

    command: ManeuverCommand
    mass_before_kg: float
    mass_after_kg: float
    fuel_consumed_kg: float
    actual_delta_v_mps: float


def _validate_mass(current_mass_kg: float, available_propellant_kg: float | None) -> None:
    if current_mass_kg <= 0:
        raise ValueError("current_mass_kg must be positive")
    if available_propellant_kg is not None and available_propellant_kg < 0:
        raise ValueError("available_propellant_kg cannot be negative")


def required_propellant_kg(
    current_mass_kg: float, commanded_delta_v_mps: float, specific_impulse_seconds: float
) -> float:
    """Calculate propellant required by the Tsiolkovsky rocket equation."""
    if current_mass_kg <= 0 or commanded_delta_v_mps < 0 or specific_impulse_seconds <= 0:
        raise ValueError("mass and specific impulse must be positive; delta-v cannot be negative")
    mass_after = current_mass_kg * math.exp(
        -commanded_delta_v_mps / (specific_impulse_seconds * STANDARD_GRAVITY_MPS2)
    )
    return current_mass_kg - mass_after


def burn_duration_seconds(
    propellant_kg: float, maximum_thrust_newtons: float, specific_impulse_seconds: float
) -> float:
    """Convert propellant demand to duration for a constant-thrust engine."""
    if propellant_kg < 0 or maximum_thrust_newtons <= 0 or specific_impulse_seconds <= 0:
        raise ValueError("propellant cannot be negative; thrust and specific impulse must be positive")
    mass_flow_kg_per_second = maximum_thrust_newtons / (specific_impulse_seconds * STANDARD_GRAVITY_MPS2)
    return propellant_kg / mass_flow_kg_per_second


def build_maneuver_command(
    action_id: int | ManeuverAction,
    current_mass_kg: float,
    config: ManeuverConfig,
    *,
    available_propellant_kg: float | None = None,
) -> ManeuverCommand:
    """Translate one discrete policy action into a valid finite burn command.

    No-op creates zero thrust and consumes no fuel. Non-null actions have equal
    commanded delta-v magnitude; only their local RSW direction differs.
    """
    config.validate()
    _validate_mass(current_mass_kg, available_propellant_kg)
    try:
        action = ManeuverAction(action_id)
    except ValueError as error:
        raise ValueError(f"unknown maneuver action ID: {action_id}") from error

    if action is ManeuverAction.NO_OP:
        return ManeuverCommand(action, (0.0, 0.0, 0.0), 0.0, 0.0, 0.0)

    propellant_kg = required_propellant_kg(
        current_mass_kg, config.commanded_delta_v_mps, config.specific_impulse_seconds
    )
    duration_seconds = burn_duration_seconds(
        propellant_kg, config.maximum_thrust_newtons, config.specific_impulse_seconds
    )
    if available_propellant_kg is not None and propellant_kg > available_propellant_kg:
        raise ManeuverInfeasibleError("insufficient propellant for the commanded delta-v")
    if duration_seconds > config.maximum_burn_duration_seconds:
        raise ManeuverInfeasibleError("required burn duration exceeds the configured maximum")

    thrust_rsw_newtons = tuple(
        component * config.maximum_thrust_newtons for component in action.rsw_unit_vector
    )
    return ManeuverCommand(
        action=action,
        thrust_rsw_newtons=thrust_rsw_newtons,
        burn_duration_seconds=duration_seconds,
        commanded_delta_v_mps=config.commanded_delta_v_mps,
        expected_propellant_kg=propellant_kg,
    )


def actual_delta_v_mps(
    mass_before_kg: float, mass_after_kg: float, specific_impulse_seconds: float
) -> float:
    """Calculate realized delta-v from pre/post-burn masses."""
    if mass_before_kg <= 0 or mass_after_kg <= 0 or specific_impulse_seconds <= 0:
        raise ValueError("masses and specific impulse must be positive")
    if mass_after_kg > mass_before_kg:
        raise ValueError("mass_after_kg cannot exceed mass_before_kg")
    return specific_impulse_seconds * STANDARD_GRAVITY_MPS2 * math.log(mass_before_kg / mass_after_kg)


def measure_maneuver_result(
    command: ManeuverCommand,
    mass_before_kg: float,
    mass_after_kg: float,
    specific_impulse_seconds: float,
) -> ManeuverResult:
    """Create a result record using actual mass change after an Orekit burn."""
    delta_v = actual_delta_v_mps(mass_before_kg, mass_after_kg, specific_impulse_seconds)
    return ManeuverResult(
        command=command,
        mass_before_kg=mass_before_kg,
        mass_after_kg=mass_after_kg,
        fuel_consumed_kg=mass_before_kg - mass_after_kg,
        actual_delta_v_mps=delta_v,
    )


def orbitzoo_action_inputs(
    commands: Mapping[str, ManeuverCommand],
) -> tuple[dict[str, list[float]], dict[str, float]]:
    """Convert named maneuver commands to OrbitZoo thrust/duration dictionaries."""
    return (
        {name: list(command.thrust_rsw_newtons) for name, command in commands.items()},
        {name: command.burn_duration_seconds for name, command in commands.items()},
    )
