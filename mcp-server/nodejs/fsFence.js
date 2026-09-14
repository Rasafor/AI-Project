// One shared path fence for the whole server. Mirrors ../src/fs_fence.py.
//
// resolveWithin(root, candidate) resolves a path and proves the result stays
// inside `root`. Any escape -- via ".." segments, an absolute path, or a symlink
// pointing out of the tree -- throws an Error naming the offending input and
// where it resolved to. Never a silent clamp or empty return.
//
// This lived in notesStore.js first; it was lifted here so the notes store and
// the SQL adapter (and anything added later that takes a caller-influenced path)
// share exactly one implementation and cannot drift.

import fs from "node:fs";
import path from "node:path";

// Resolve symlinks as far down the path as it currently exists, then re-append
// the not-yet-existing tail. path.resolve() alone normalises "." and ".." but
// does NOT follow symlinks, so a symlink inside the tree could otherwise point
// out of it undetected.
function realResolve(target) {
  let current = path.resolve(target);
  const tail = [];
  while (!fs.existsSync(current)) {
    tail.unshift(path.basename(current));
    const parent = path.dirname(current);
    if (parent === current) break; // hit the filesystem root
    current = parent;
  }
  const realBase = fs.realpathSync(current);
  return tail.length ? path.join(realBase, ...tail) : realBase;
}

// Resolve `candidate` under `root` and prove the result stays inside `root`.
// Returns the resolved absolute path on success; throws (with `what` naming the
// kind of path in the message) if it lands outside.
export function resolveWithin(root, candidate, what = "path") {
  const rootReal = realResolve(root);
  const combined = path.isAbsolute(candidate)
    ? candidate
    : path.join(rootReal, candidate);
  const resolved = realResolve(combined);

  const rel = path.relative(rootReal, resolved);
  const escapes =
    rel === ".." || rel.startsWith(`..${path.sep}`) || path.isAbsolute(rel);
  if (rel !== "" && escapes) {
    throw new Error(
      `${what} escapes the allowed directory: ${JSON.stringify(candidate)} ` +
        `resolves to ${resolved}, which is outside ${rootReal}`,
    );
  }
  return resolved;
}
