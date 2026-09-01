"""
One shared path fence for the whole server.

`resolve_within(root, candidate)` resolves a path and proves the result stays
inside `root`. Any escape -- via ``..`` segments, an absolute path, or a symlink
pointing out of the tree -- raises ``ValueError`` naming the offending input and
where it resolved to. It is never a silent clamp or an empty return.

This lived in ``notes_store`` first; it was lifted here so the notes store and
the SQL adapter (and anything added later that takes a caller-influenced path)
share exactly one implementation and cannot drift.
"""

from __future__ import annotations

from pathlib import Path


def resolve_within(root: Path, candidate: str | Path, *, what: str = "path") -> Path:
    """Resolve ``candidate`` under ``root`` and guarantee it stays inside ``root``.

    Returns the resolved absolute path on success. Raises ``ValueError`` -- with
    ``what`` naming the kind of path in the message -- if the result lands
    outside ``root``.
    """
    root_resolved = root.resolve()
    candidate_path = Path(candidate)
    combined = (
        candidate_path if candidate_path.is_absolute() else root_resolved / candidate_path
    )
    resolved = combined.resolve()
    if not resolved.is_relative_to(root_resolved):
        raise ValueError(
            f"{what} escapes the allowed directory: {str(candidate)!r} resolves to "
            f"{resolved}, which is outside {root_resolved}"
        )
    return resolved
