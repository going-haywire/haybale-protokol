"""ProtokolSettings — how Lines behave on this machine."""

from haywire.barn.builtin.types import FLOAT
from haywire.core.settings import LibrarySettings, setting, settings


@settings(namespace="protokol", label="Protokol", description="Lines shared by gates and the Monitor")
class ProtokolSettings(LibrarySettings):
    """How long a Line stays open after its last user leaves."""

    grace_period_s = setting[FLOAT](
        2.0,
        min=0.0,
        max=30.0,
        label="Line grace period (s)",
        description=(
            "How long a Line stays open after its last user leaves, so a graph restart "
            "keeps TCP peers connected."
        ),
        category="Lines",
    )
