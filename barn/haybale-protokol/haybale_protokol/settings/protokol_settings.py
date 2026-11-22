"""ProtokolSettings — how Lines behave on this machine."""

from haywire.api import FLOAT, LibrarySettings, setting, settings


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

    device_watch_s = setting[FLOAT](
        1.0,
        min=0.2,
        max=10.0,
        label="Device check interval (s)",
        description=(
            "How often the plugged-in devices are checked, so a gate notices a device "
            "being unplugged or plugged back in. The refresh button checks at once."
        ),
        category="Devices",
    )
