"""
Roots containment — the ONE filesystem gate for this MCP server.

Every tool that opens, reads, or writes a file routes its target path through
`contained_path()` before touching disk. The check, in order:

  1. Ask the client which roots it has declared (`roots/list`). A root is the
     client's statement: "you may only touch files at or under here."
  2. Resolve the REAL path of the requested file with `Path.resolve()`, which
     collapses `.` and `..` AND follows every symlink to its final target. The
     declared roots are resolved the same way.
  3. Require the requested real path to equal a declared root or be a descendant
     of one, compared component-by-component (`Path.is_relative_to`) — never by
     string.

Why a raw `str.startswith` prefix check on the *unresolved* path is not enough
(this is the trap `contained_path` exists to avoid):

  * `"/data/../etc/shadow"` starts with `"/data/"` but the `..` walks it out.
  * `"/data-backup/x"` starts with `"/data"` yet is a sibling directory, not a
    child — a prefix test ignores the path-separator boundary.
  * `"/data/link"` where `link` is a symlink to `/etc` passes every string test
    and still reads `/etc` — a prefix check never follows links.
  * `"/Data/x"` vs an allowed `"/data"` differ only in case, which is significant
    on some filesystems and folded on others; only real-path resolution
    normalises that.

Only comparing fully-resolved real paths, split into components, is sound.

No function here raises for a denial — `contained_path` returns a `Decision`,
and it emits the warning log itself so every caller logs identically. The
caller turns a denied `Decision` into an error *result*. Default-deny: if the
client declares no roots capability, or an empty roots list, or `roots/list`
fails, access is denied — never "allow everything".

This sits OUTSIDE the existing `fs_fence` (which pins the notes store / SQL
adapter to the server's own data dirs). fs_fence answers "is this inside the
server's sandbox"; roots_fence answers "did the operator's client consent to
this path". Both must pass.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

import obs

# Stable, enumerated denial reasons — logged as a field, never free text.
REASON_LIST_UNAVAILABLE = "roots_list_unavailable"  # no roots capability, or roots/list errored / went unanswered
REASON_EMPTY_LIST = "empty_roots_list"
REASON_UNRESOLVABLE = "requested_path_unresolvable"
REASON_OUTSIDE_ROOTS = "resolved_path_outside_all_declared_roots"

_NO_ROOTS_REASONS = frozenset({REASON_LIST_UNAVAILABLE, REASON_EMPTY_LIST})


@dataclass(frozen=True)
class Decision:
    allowed: bool
    requested_path: str
    resolved_path: str | None = None
    reason: str | None = None
    roots_checked: int = 0

    @property
    def path(self) -> Path:
        if not self.allowed or self.resolved_path is None:
            raise RuntimeError("Decision.path read on a denied decision")
        return Path(self.resolved_path)


def _root_uri_to_path(uri) -> Path | None:
    """`file://` URI -> resolved local Path, or None if it isn't a usable file URI."""
    try:
        parsed = urlparse(str(uri))
        if parsed.scheme != "file":
            return None
        raw = (parsed.netloc + parsed.path) if parsed.netloc else parsed.path
        return Path(url2pathname(unquote(raw))).resolve()
    except (OSError, ValueError):
        return None


async def _declared_roots(ctx) -> tuple[list[Path] | None, str | None]:
    """(resolved root paths, denial_reason).

    Returns ([...], None) when the client declared one or more roots;
    (None, REASON_*) when it declared none / did not answer.

    We call `roots/list` directly rather than pre-checking a stored capability:
    a client with no roots support answers with an error (so this raises), and
    on the stateless HTTP transport there is no stored session to check a
    capability against anyway — the request itself is the only reliable probe.
    """
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # roots capability is deprecated (SEP-2577); still the mechanism
            result = await ctx.session.list_roots()
    except Exception:
        return None, REASON_LIST_UNAVAILABLE

    roots = [p for p in (_root_uri_to_path(getattr(r, "uri", r)) for r in (result.roots or [])) if p]
    if not roots:
        return None, REASON_EMPTY_LIST
    return roots, None


async def contained_path(ctx, requested, *, correlation_id: str) -> Decision:
    """The whole-server filesystem containment check. Never raises."""
    requested_str = str(requested)
    roots, deny_reason = await _declared_roots(ctx)

    if roots is None:
        return await _deny(ctx, correlation_id, Decision(False, requested_str, reason=deny_reason))

    try:
        real = Path(requested).resolve()
    except (OSError, ValueError, RuntimeError):
        return await _deny(
            ctx,
            correlation_id,
            Decision(False, requested_str, reason=REASON_UNRESOLVABLE, roots_checked=len(roots)),
        )

    if any(real == root or real.is_relative_to(root) for root in roots):
        return Decision(True, requested_str, resolved_path=str(real), roots_checked=len(roots))

    return await _deny(
        ctx,
        correlation_id,
        Decision(
            False,
            requested_str,
            resolved_path=str(real),
            reason=REASON_OUTSIDE_ROOTS,
            roots_checked=len(roots),
        ),
    )


async def _deny(ctx, correlation_id: str, decision: Decision) -> Decision:
    """Emit the warning log for a denial and return the decision unchanged."""
    event = (
        obs.EVENT_ROOTS_NO_ROOTS
        if decision.reason in _NO_ROOTS_REASONS
        else obs.EVENT_ROOTS_DENIED
    )
    await obs.emit(
        ctx,
        "warning",
        event,
        correlation_id,
        requested_path=decision.requested_path,
        resolved_path=decision.resolved_path,
        reason=decision.reason,
        roots_checked=decision.roots_checked,
    )
    return decision
