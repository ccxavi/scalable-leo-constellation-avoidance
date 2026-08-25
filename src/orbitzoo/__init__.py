"""OrbitZoo — orbital-dynamics + MARL environment."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orbitzoo.env import OrbitZoo

__all__ = ["OrbitZoo"]
__version__ = "0.1.0"


def __getattr__(name):
    """Load the simulation environment only when it is requested."""
    if name == "OrbitZoo":
        from orbitzoo.env import OrbitZoo

        return OrbitZoo
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
