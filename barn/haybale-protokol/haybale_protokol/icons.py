"""Icons of the Protokol editors that core's ``AppIcon`` (``hui.icon``) does not name.

Everything ``hui.icon`` has a meaning for is taken from there; this registry only adds the
protocol-domain ones, so the editors still use names rather than raw Material strings.
"""

from typing import Final


class ProtokolIcon:
    """Material icon names for the Protokol editors."""

    monitor: Final[str] = "monitor_heart"
    device: Final[str] = "usb"
    send: Final[str] = "send"
    bind: Final[str] = "link"
    back: Final[str] = "arrow_back"
    export_csv: Final[str] = "table_view"


icon = ProtokolIcon
