# WS1 — Run grouping under Experiments/Views (change summary)

Makes created runs persist in the listing and organizes them under an
Experiment, per the AMOS Gateway design. Each change is described with STAR
(Situation, Task, Action, Result).

## 1. Stop hiding the user's own runs from the list (`views.py`)
- **Situation:** `RunViewSet.get_queryset` did `exclude(experiment__owner=None)`
  on the `list` action to hide tutorials. But runs created via the API have
  `experiment = None`, so the `experiment__owner` join is NULL and they were
  excluded too — they existed in the DB but vanished from every list fetch
  ("runs disappear after reload").
- **Task:** Hide only genuine tutorial runs while keeping the user's own runs,
  even when not yet grouped under an experiment.
- **Action:** Replaced the exclusion with
  `exclude(views__type="tutorial").distinct()`, which targets runs attached to a
  tutorial-type `View` (how tutorials are actually modeled, per
  `Run.check_is_tutorial`).
- **Result:** `GET /api/runs/` returns the user's runs across reloads; tutorials
  remain excluded from the general listing.

## 2. Group new runs under an Experiment (`serializers.py`)
- **Situation:** `RunSerializer.create` set `airavata_project_id` and
  `directory` but never associated the run with an `Experiment`, so the
  Experiments page/statistics were empty and runs were ungrouped.
- **Task:** Associate each new run with an Experiment so runs are organized and
  experiment-scoped queries work — without disturbing the working submit path.
- **Action:** Added `_resolve_experiment(request)`: honor an explicit
  `experiment`/`experimentId` from the client if present, otherwise
  `get_or_create` a per-user default `"ePolyScat Runs"` experiment; pass it as
  `experiment=` to `Run.objects.create`. The experiment's Airavata project is
  left to be created lazily on first submit (`_create_remote_execution` already
  handles `experiment.airavata_project_id is None`).
- **Result:** New runs appear under `GET /api/experiments/` and are filterable
  via `?experiment=<id>`; `statistics` reflects grouped runs. Submit is
  unaffected (it lazily provisions the experiment's project).

## Verification
`manage.py check` clean. Live API: created a run → it lists in `GET /api/runs/`,
groups under experiment "ePolyScat Runs", and returns under
`GET /api/runs/?experiment=<id>`; `GET /api/experiments/statistics/` shows the
grouped run.

## Deferred
Existing pre-WS1 runs (created before this change) keep `experiment = None`; they
still list but are not retroactively grouped. RunsRoot/`number` sub-grouping is
not yet wired (the frontend doesn't drive it; `run.name` remains the label).
