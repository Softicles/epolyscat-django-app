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

## Follow-up fix — shadowed Thrift `Project` in `create_airavata_project` (`models.py`)
- **Situation:** Once WS1 set `run.experiment`, `submit` took the
  `run.experiment.create_airavata_project()` path and raised
  `ValueError: "Project.owner" must be a "User" instance`. `models.py` both
  imports the Thrift `Project` and defines a Django `class Project(models.Model)`
  that shadows it, so `create_airavata_project` was constructing the Django model
  (whose `owner` is a `User` FK) instead of the Thrift project.
- **Task:** Make `create_airavata_project` build the Airavata (Thrift) project.
- **Action:** Imported the Thrift project as `AiravataProject` and used it in both
  `Project.create_airavata_project` and `Experiment.create_airavata_project`.
- **Result:** Submitting a grouped run creates the experiment's Airavata project
  and proceeds to launch; `POST /api/runs/9/submit/` returns 200 (was 500).

## Follow-up fix — Experiment creation (`serializers.py`)
- **Situation:** `POST /api/experiments/` returned 500
  (`Experiment() got an unexpected keyword argument 'root'`). `ExperimentSerializer`
  created a `RunsRoot` and passed `root=` to `Experiment.objects.create`, but the
  `Experiment.root` field had been removed (commented out) — so naming a custom
  experiment to group runs under was impossible.
- **Task:** Make experiment creation work against the current `Experiment` model.
- **Action:** Removed the stale `root` serializer field, the `"root"` entries in
  `Meta.fields`/`read_only_fields`, and the `RunsRoot`/`root` handling in
  `create()`; `create()` now just builds the Experiment and provisions its
  Airavata project.
- **Result:** `POST /api/experiments/` returns 201; a run created with
  `experimentId` is grouped under that named experiment (verified: exp "N2
  photoionization study" with its run).

## Navigation — Runs/Experiments under the Views tab (`AppLeftNav.vue`)
- **Situation:** The `/experiments` page existed but was unreachable from the
  left nav; the Views tab only listed saved views.
- **Task:** Surface both browse modes (Runs and Experiments) under the Views tab.
- **Action:** Replaced the Views collapse contents with two options — "Runs"
  (→ `/runs`) and "Experiments" (→ `/experiments`); rebuilt the frontend bundle.
- **Result:** Expanding "Views" shows Runs and Experiments; the Experiments page
  is now reachable from the sidebar.

## UI wiring — group runs under the selected experiment (`Run.vue`, `run-storage.store.js`, `epolyscat-service.js`)
- **Situation:** The backend reads `experimentId` on run create, and the UI
  navigates to `/runs/?experimentId=<id>` after an experiment is created, but the
  run-create chain (`Run.vue` → store `run/createRun` → `RunService.createRun`)
  never forwarded `experimentId` — so UI-created runs always fell into the default
  "ePolyScat Runs" experiment regardless of context. (Also why the Experiments
  page looked empty: experiment creation itself was broken, so none existed.)
- **Task:** Thread `experimentId` from the route through to the create request.
- **Action:** `RunService.createRun` now sends `experimentId`; the store
  `run/createRun` action forwards it; `Run.vue` `saveRun` passes
  `this.experimentId` (from `$route.query`). Rebuilt the bundle.
- **Result:** Creating a run while viewing an experiment groups it under that
  experiment (verified: runs under exp 2 = "N2 run A", "N2 run B"). With the
  create fix above, the Experiments page now lists experiments.

## Fix — Experiments page blank / no fetch (`Experiments.vue`)
- **Situation:** Opening `/experiments` showed a blank page and fired **no**
  `/api/experiments/` request. `experimentsPagination` is `null` until the first
  fetch, but the template bound `:total-rows="experimentsPagination.total"` —
  `null.total` threw during the initial render, so the component never mounted and
  its `mounted()` fetch never ran.
- **Task:** Let the page render before data loads so `mounted()` can fetch.
- **Action:** Made the `experimentsPagination` computed return `{total: 0}` when
  the getter returns null.
- **Result:** The page renders, mounts, fetches, and lists experiments.
