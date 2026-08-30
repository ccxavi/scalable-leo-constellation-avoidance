"""The discrete maneuver primitives exposed to the shared MAPPO actor."""

from enum import IntEnum


class ManeuverAction(IntEnum):
    """Action IDs and unit directions in the local RSW orbital frame."""

    NO_OP = 0
    PROGRADE = 1
    RETROGRADE = 2
    RADIAL_OUT = 3
    RADIAL_IN = 4
    CROSS_TRACK_POSITIVE = 5
    CROSS_TRACK_NEGATIVE = 6

    @property
    def display_name(self) -> str:
        return {
            ManeuverAction.NO_OP: "no-op",
            ManeuverAction.PROGRADE: "prograde",
            ManeuverAction.RETROGRADE: "retrograde",
            ManeuverAction.RADIAL_OUT: "radial-out",
            ManeuverAction.RADIAL_IN: "radial-in",
            ManeuverAction.CROSS_TRACK_POSITIVE: "cross-track-positive",
            ManeuverAction.CROSS_TRACK_NEGATIVE: "cross-track-negative",
        }[self]

    @property
    def rsw_unit_vector(self) -> tuple[float, float, float]:
        """Return the RSW direction: radial, along-track, cross-track."""
        return {
            ManeuverAction.NO_OP: (0.0, 0.0, 0.0),
            ManeuverAction.PROGRADE: (0.0, 1.0, 0.0),
            ManeuverAction.RETROGRADE: (0.0, -1.0, 0.0),
            ManeuverAction.RADIAL_OUT: (1.0, 0.0, 0.0),
            ManeuverAction.RADIAL_IN: (-1.0, 0.0, 0.0),
            ManeuverAction.CROSS_TRACK_POSITIVE: (0.0, 0.0, 1.0),
            ManeuverAction.CROSS_TRACK_NEGATIVE: (0.0, 0.0, -1.0),
        }[self]
