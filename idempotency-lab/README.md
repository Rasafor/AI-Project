# Idempotency Lab: user-profile update

`update_profile()` in `profile_store.py` changes a user profile (SQLite, standard library only). Running it once or ten times with the same idempotency key leaves the same end state: same row, same version, one "email changed" event.

- See it: `python idempotency-lab/demo.py`. It runs a naive update and the idempotent one three times each and prints a fingerprint of the whole database after each run.
- Test it: `cd idempotency-lab && python -m unittest test_profile_store` (15 tests: repeats, replays, late retries, key reuse, crash-before-commit, 5 concurrent duplicates, malformed input).

The four mechanisms (set semantics, normalize-then-diff, idempotency key, single transaction) are explained at the top of `profile_store.py`.
