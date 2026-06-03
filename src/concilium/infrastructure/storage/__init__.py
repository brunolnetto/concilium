"""Storage layer: filesystem versionado, snapshots por hash, copy-on-write."""

from .project import ProjectStore
from .snapshot import SnapshotStore

__all__ = ["ProjectStore", "SnapshotStore"]
