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

## Fix — Experiment Vuex module not registered (`store/index.js`) — root cause
- **Situation:** Opening `/experiments` threw
  `this.$store.getters['experiment/getExperiments'] is not a function` and fired
  **no** REST request. The experiment store module was **commented out** in the
  store registration, so the entire `experiment/*` namespace
  (`getExperiments`/`fetchExperiments`/`createExperiment`) did not exist. The page
  crashed during render, before `mounted()` could fetch.
- **Task:** Register the experiment module so its getters/actions resolve.
- **Action:** Added `"experiment": experimentStore` to the store `modules` (it was
  imported but only present as a commented-out entry); removed the stale commented
  lines.
- **Result:** `experiment/*` getters and actions resolve; the Experiments page
  renders, mounts, fetches, and lists experiments; the Create-Experiment flow
  dispatch works. (The `experimentsPagination` null-guard above was also needed
  for a clean first render.)

## UI — Experiment column in the Runs table (`Runs.vue`, `serializers.py`)
- **Situation:** The Runs table showed Run Name / Status / Resource / Actions with
  no indication of which experiment a run belongs to, and the run API did not
  expose the experiment.
- **Task:** Show each run's experiment in the Runs table, between the Resource and
  Actions columns.
- **Action:** Exposed the experiment on the run API — `"experiment"` (id) plus an
  `experiment_name` SerializerMethodField (`instance.experiment.name`, null-safe) —
  in `RunSerializer`; the run encode maps `experimentName ← obj.experiment_name`.
  Inserted an `['experimentName', 'Experiment']` column and cell slot between the
  Resource and Actions columns in `Runs.vue`. Rebuilt the bundle.
- **Result:** The Runs table shows an "Experiment" column with the experiment
  **name** (or "—" when ungrouped) between Resource and Actions. Verified the API
  returns `experiment_name` (runs under exp 2 report
  `experiment_name: "N2 photoionization study"`).

## Fix — experiment filtering + New Run inherits the experiment (`Runs.vue`)
- **Situation:** `/runs/?experimentId=<id>` showed **all** runs — the
  `experimentId` computed was commented out, so `this.experimentId` was undefined
  and nothing filtered. Separately, clicking **New Run** while viewing an
  experiment's runs went to `/runs/new` without the experiment, so the new run
  did not belong to it.
- **Task:** Filter the runs list by the route's `experimentId`, and have New Run
  carry the experiment into creation.
- **Action:** Defined the `experimentId()` (from `$route.query`) and
  `experiment()` computeds; filter `runs()` client-side by `experimentId` (each
  run carries `experimentId` from the API, robust to the store holding all runs);
  made `newRunLink` include `?experimentId=<id>` when viewing an experiment
  (`Run.vue` already threads `experimentId` into create).
- **Result:** `/runs/?experimentId=<id>` shows only that experiment's runs, and
  New Run from an experiment view creates a run grouped under that experiment.

## Fix — show all runs (submitted + unsubmitted) in each experiment view (`epolyscat-service.js`)
- **Situation:** `RunService.fetchRuns` (the active store fetch) called
  `GET /runs/`, which is paginated (page_size 10). With more than 10 runs only the
  first 10 reached the store, so an experiment view — which client-filters the
  store by `experimentId` — showed only whatever subset of those 10 matched,
  missing runs regardless of submitted/unsubmitted status.
- **Task:** Make every run available so each experiment view lists all of its
  runs.
- **Action:** `fetchRuns` now requests `?page_size=10000`, loading all of the
  user's runs into the store.
- **Result:** All runs are loaded (verified 14 of 14 returned vs 10 by default);
  each experiment view shows all its runs — both submitted and unsubmitted.

## Fix — run detail crashed on inputs not in the input model (`input-storage.store.js`)
- **Situation:** Opening a run (e.g. run 13) threw "Error while trying to fetch
  run with id: 13". The `ADD_TO_INPUT_FILE` mutation did
  `state.inputFiles[inputFileName].files` where `inputFileName` was not a known
  key → `TypeError`, aborting the run-detail load. Triggered by runs whose
  inputs/outputs don't map to the frontend's current input model.
- **Task:** Don't crash the run page on a file that maps to no known input slot.
- **Action:** Guard `ADD_TO_INPUT_FILE` to return early when
  `state.inputFiles[inputFileName]` is undefined.
- **Result:** The run detail page loads even when a run's inputs/outputs don't
  match the input model; the unrecognized file is simply skipped.

## Fix — runType crashed on runs missing Calculation_Type (`Run.vue`)
- **Situation:** Opening a run whose inputs lack a `Calculation_Type` entry (e.g.
  API-created runs) threw `can't access property "value", e is undefined` —
  `runType` did `type1.value`/`type2.value` where `type1` (the `Calculation_Type`
  input) was `undefined`.
- **Task:** Don't crash the run page when one of the type inputs is absent.
- **Action:** Guard `runType` to return `-----` when neither type input is
  present, and substitute `—` for whichever part is missing.
- **Result:** The run detail page loads for runs missing `Calculation_Type`.
