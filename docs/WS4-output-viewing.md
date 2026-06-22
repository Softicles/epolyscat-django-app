# WS4 — Output viewing + plotting (change summary)

Re-enables the input-listing and plotting endpoints and makes the output-file
lookup path robust for runs created via the current API/model. Each change is
described with STAR (Situation, Task, Action, Result).

## 1. Re-enable list-inputs / diff-inputs / plotables routes (`urls.py`)
- **Situation:** `api/list-inputs/`, `api/diff-inputs/`, and `api/plotables/`
  were commented out, so the frontend's input-listing/plotable discovery 404'd at
  the URL layer even though the views and serializers exist.
- **Task:** Expose the three endpoints again.
- **Action:** Uncommented the three `path(...)` entries (`plot` was already live).
- **Result:** All three resolve; verified live (200 / clean 404 — see below).

## 2. Clear error when ePolyScat scripts are not installed (`views.py`)
- **Situation:** `plot` (plot.py) and `list-inputs`/`diff-inputs` (lRuns.py) shell
  out to scripts in the SCRIPTS dir (`apps.py`). When a script is absent,
  `python <missing>` just exits non-zero with an opaque "can't open file"
  message surfaced as a generic error, with no indication the deployment is
  missing the scripts.
- **Task:** Fail fast with an actionable error before shelling out.
- **Action:** Added `ScriptsNotInstalled` (`APIException`, HTTP 501) and
  `_require_script(name)`, which returns the script path or raises the clear
  error. Wired it into `plot` (`plot.py`) and `_execute_lruns` (`lRuns.py`) — the
  latter checks before any `run.root` access, so the endpoints fail cleanly
  regardless of run shape when scripts are missing.
- **Result:** Missing scripts yield a 501 with an install hint instead of an
  opaque subprocess failure (verified `_require_script` raises with
  `status_code=501`). In this repo the scripts are vendored under
  `epolyscat_django_app/ePolyScat/SCRIPTS`, so the guard is a no-op here.

## 3. Honor the "else None" contract in the output-file lookup (`views.py`)
- **Situation:** `user_run_file_exists` (the lookup behind `plotables`,
  `list-inputs`, `viewables`, `input_files`, `show_viewable`) **raised**
  `Exception("Modl_RunID file is missing")` whenever a completed experiment had
  no `Modl_RunID` output. Runs launched against the current prod ePolyScat
  interface don't emit `Modl_RunID`, so every output lookup 500'd (e.g.
  `plotables`/`list-inputs` returned 500 instead of "no files"). Its docstring
  promises "Return data product uri for run file if it exists, else None."
- **Task:** Make the lookup degrade to not-found instead of crashing.
- **Action:** Return `None` (with a debug log) when the `Modl_RunID` output is
  absent or unresolvable, and `None` (with a warning) when its contents don't
  parse — honoring the documented contract. Callers then behave correctly:
  `run_file_exists` → False, `open_run_file` → `FileNotFoundError` → 404.
- **Result:** `plotables` on a prod run returns `{"filenames": []}` (200);
  `list-inputs` returns a clean 404 when `inpc` is absent; `viewables` returns
  the experiment's `stdout`/`stderr`. No more 500s from the Modl_RunID path.

## 4. Support API-created runs (no RunsRoot) in the lRuns path (`views.py`)
- **Situation:** `_execute_lruns` and `runs_dir` built paths from
  `run.root.root` / `run.number`. Runs created via the current API have
  `root = None` (and may have no `number`), so these `AttributeError`'d — every
  `list-inputs`/`diff-inputs` on an API-created run would 500.
- **Task:** Make the lRuns directory layout work without a RunsRoot.
- **Action:** Added `_run_root_name(run)` (the RunsRoot label, else `"runs"`) and
  `_run_number(run)` (the run number, else the run id), mirroring the existing
  `run_label` guard, and used them in `runs_dir` and `_execute_lruns`.
- **Result:** The endpoints resolve a stable `<root>/<number>` layout for every
  run; `diff-inputs` reaches the file lookup and returns a clean 404 for a run
  missing `inpc` (instead of an `AttributeError` 500).

## Already in place (verified)
- `viewables`, `input_files`, `show_viewable`, `get_output_files` are registered
  `@action`s on `RunViewSet` (not gated by the commented routes). They read the
  `apps.py` `FILE_VIEWABLE` / `FILE_INPUT` maps and the experiment ARCHIVE via
  `user_storage`, with their own error handling. Verified `viewables` returns 200
  with `stdout`/`stderr` for a completed prod run.

## Verification
`manage.py check` clean. Live against the prod `amp` gateway, run 26 (completed on
Expanse): `plotables` → `{"filenames": []}` (200); `list-inputs` → 404 "inpc does
not exist in run 26"; `viewables` → 200 with `stdout`/`stderr`; `_require_script`
raises `ScriptsNotInstalled` (501) for a missing script.

## Notes / follow-ups
- `list-inputs`/`diff-inputs` need `inpc`/`outf`/`linp` in the run directory for
  lRuns to produce output. Prod runs stage outputs into the experiment ARCHIVE,
  not the run directory, so lRuns output for those runs depends on output staging
  (separate from this change). The endpoints are now structurally correct and
  fail cleanly when those files are absent.
- The plan referenced an "ePolyScat SCRIPTS git submodule"; in this repo the
  scripts are vendored (tracked) under `epolyscat_django_app/ePolyScat/SCRIPTS`,
  not a submodule (only `tRecX` is a submodule). The `_require_script` guard
  covers deployments where they are absent.
