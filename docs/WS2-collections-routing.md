# WS2 — Modules/Utilities/Workflows routing (change summary)

Makes the Create-Run collection types first-class: a declarative catalog plus
interface routing so a run runs the Airavata application it actually selected,
instead of always the hardcoded ePolyScat module. STAR per change.

## 1. Declarative collections catalog (`apps.py`, `views.py: api_settings`)
- **Situation:** The Module/Utility/Workflow collections (the paper's central
  abstraction) had no backend representation — option lists were hardcoded in the
  frontend and the backend could not enumerate them.
- **Task:** Give the backend a declarative catalog of the three collection types
  and their members, and expose it to clients.
- **Action:** Added `COLLECTIONS` under
  `APPLICATION_SETTINGS["EPOLYSCAT_DJANGO_APP"]` (each type → `input_name` +
  `members`: Modules = Gaussian16/ePolyScat/OpenMolcas; Utilities = MoldenMerge/
  NRFPAD/…; Workflows = Data_Gen/ePolyScat_Run/Analysis). `api_settings` now
  returns it.
- **Result:** `GET /api/settings/` returns the Modules/Utilities/Workflows
  catalog under `EPOLYSCAT.COLLECTIONS`.

## 2. Interface routing by selected member (`views.py`)
- **Situation:** `_get_eployscat_app_interface_id` always resolved a single
  hardcoded ePolyScat module, so every submit ran ePolyScat regardless of the
  user's Module/Utility/Workflow selection.
- **Task:** Resolve and route to the Airavata application interface matching the
  run's selected collection member.
- **Action:** Added `_resolve_application_module_id(run)` — reads the run's
  `EPOLYSCAT_Application_Module`/`Application_Utility`/`Application_Workflow`
  input and maps the selected member name to an Airavata module id via
  `settings.EPOLYSCAT["APPLICATION_IDS"]`, falling back to
  `EPOLYSCAT_APPLICATION_ID`. Generalized
  `_get_eployscat_app_interface_id(request, run=None)` to use it; `submit` and
  `resubmit` now pass the run.
- **Result:** A run selecting `Gaussian16` resolves the Gaussian interface;
  `ePolyScat` the ePolyScat interface; unmapped members or no selection fall back
  to the core ePolyScat module. The downstream interface lookup is unchanged.

## Configuration
Gateway-specific id mapping lives in `settings_local.py`
(`EPOLYSCAT["APPLICATION_IDS"]`), consistent with `EPOLYSCAT_APPLICATION_ID` —
not in the app repo. With no mapping, all selections fall back to the core
ePolyScat module (prior behavior preserved).

## Verification
`manage.py check` clean. `GET /api/settings/` returns `COLLECTIONS`. Shell test of
`_resolve_application_module_id` across Gaussian16 / ePolyScat / OpenMolcas
(unmapped) / MoldenMerge (unmapped) / no-selection / no-run — all resolve to the
expected module id.

## Deferred
MoldenMerge/NRFPAD and other utilities are catalog members but are not registered
as Airavata applications on the dev gateway, so selecting them routes to the
fallback until those apps are deployed and added to `APPLICATION_IDS`.

## Alignment — frontend input model fetched from the registered interface
- **Situation:** `fetchApplicationInputs()` returned a **hardcoded** interface
  array (numeric types) that diverged from the registered backend interface, so
  runs/inputs created against the backend didn't match the frontend's input model
  (e.g. the `Input-File` vs `ePolyscat_Input_File` name mismatch).
- **Task:** Drive the frontend input builder from the **registered** ePolyScat
  interface, with both sides using DataType **name-string** types (no number↔name
  transform).
- **Action:**
  - *Backend (gateway state, not repo):* updated the registered interface
    `ePolyScat_ced30c67` to carry the full 9-input definition **+ editor
    `metaData`** (Calculation_Type, Application_Workflow, EPOLYSCAT_Application_Module,
    Application_Utility, Gaussian_Input, Molcas_Input, ePolyScat_Input_Data,
    ePolyscat_Input_File, molden.dat).
  - *Frontend:* `fetchApplicationInputs()` now fetches
    `/api/applications/<EPOLYSCAT_APPLICATION_ID>/application_interface/` (module
    id from `/api/settings/`) and sorts by `inputOrder` (the API returns inputs
    alphabetically). `fetchPathLabels` type checks converted from numbers to
    DataType name strings (`STRING`/`INTEGER`/`URI`/`URI_COLLECTION`); the synthetic
    `Parameters` input uses `type: "INTEGER"`.
- **Result:** The input builder is sourced from the registered interface.
  Round-trip verified: types are name strings, editor `metaData`
  (options + `dependencies.show.OR`) survives intact, and `inputOrder` restores
  the definition order. Build succeeds.
- **Note:** This required updating the shared dev-gateway interface (approved).
  Input-builder rendering should be confirmed in the browser.
