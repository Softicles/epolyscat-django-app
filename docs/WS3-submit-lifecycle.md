# WS3 — Submit/resubmit lifecycle hardening (change summary)

Makes the run launch path (`submit`/`resubmit`) consistent with the current
input model and fixes a broken resubmit, per the AMOS Gateway run lifecycle.
Each change is described with STAR (Situation, Task, Action, Result).

## 1. Share input-building between submit and resubmit (`views.py`)
- **Situation:** `submit` built an `{input_name: value}` dict inline from
  `run.inputs.all()` (file inputs → comma-joined data-product URIs, others →
  their stored value). `resubmit` did **not** reuse this; it read
  `run.inpc_data_product_uri`, which the current create path never populates
  (inputs are stored as `Input`/`File` rows, not a single inpc file), so
  resubmit's `open_file(None)` would fail before launch.
- **Task:** Build launch inputs from the run's actual stored inputs in one place,
  used by both submit and resubmit.
- **Action:** Extracted `_build_input_values(request, run)` and had `submit` call
  it. The helper copies each file input into the experiment input store and
  represents it by its (comma-joined) product URIs; non-file inputs pass through
  their value.
- **Result:** Submit behavior is unchanged; resubmit can now construct the same
  inputs without relying on the unpopulated `inpc_data_product_uri`.

## 2. Fix the broken resubmit call signature (`views.py`)
- **Situation:** `resubmit` called
  `_create_remote_execution(request, run, app_interface_id, input_values)` — four
  args — but the method required six
  `(request, run, inputs, app_interface_id, input_values, is_tutorial)`. Any
  resubmit therefore raised `TypeError` (missing positional args) before it could
  launch. The extra `inputs` parameter was also dead: only `input_values` is read
  when mapping onto the interface.
- **Task:** Make resubmit launch correctly and simplify the helper signature.
- **Action:** Dropped the unused `inputs` parameter, so
  `_create_remote_execution(request, run, app_interface_id, input_values,
  is_tutorial)`. Rewrote `resubmit` to use `_build_input_values` plus
  `Previous_JobID_Restart=<most recent job id>` (names not present on the resolved
  interface are ignored by the existing mapping loop), and call the helper with
  the correct signature. Updated `submit`'s call to match.
- **Result:** `manage.py check` clean; both `submit` and `resubmit` call
  `_create_remote_execution` with the same 5-arg signature. Resubmit no longer
  raises `TypeError` and re-launches from the run's stored inputs.

## 3. Remove dead, unreachable submit leftovers (`views.py`)
- **Situation:** The `status` action contained an unreachable block after its
  `return Response(run.status)` — leftover from an older single-`inpc`-file submit
  — that also called `_create_remote_execution` with the wrong arity. It was dead
  but misleading and referenced the unpopulated `inpc_data_product_uri`.
- **Task:** Delete the dead code so the launch path has a single source of truth.
- **Action:** Removed the unreachable block; `status` now just returns
  `run.status`.
- **Result:** No behavior change; the only launch path is `submit`/`resubmit` →
  `_create_remote_execution`.

## 4. Fix `Run.is_cancelable` property/argument mismatch (`models.py`)
- **Situation:** `Run.is_cancelable` was decorated `@property` yet declared a
  `request` parameter. `RunSerializer.get_cancelable` calls
  `instance.is_cancelable(request)`; as a property, attribute access invokes it
  with only `self` → `TypeError`, so resolving `cancelable` would crash (latent —
  the serializer field is currently disabled).
- **Task:** Make `is_cancelable(request)` callable as a method.
- **Action:** Removed the `@property` decorator.
- **Result:** `instance.is_cancelable(request)` works, delegating to the latest
  execution; safe to re-enable the `cancelable` serializer field.

## Already in place (verified, no change needed)
- **Status caching:** `RemoteExecution.get_airavata_experiment_status` only calls
  Airavata when the cached state is non-terminal; otherwise returns the stored
  status. `get_job_id` caches the job id after first resolution. This satisfies
  the WS3 status-caching goal as-is.
- **Interface input mapping:** `_create_remote_execution` maps provided
  `input_values` onto the interface inputs and marks unprovided `URI`/
  `URI_COLLECTION` inputs `isRequired=False`, so a partial input set still
  launches.

## Verification
`manage.py check` clean. Static review confirms both launch paths share
`_build_input_values` and call `_create_remote_execution` with the 5-arg
signature. Live submit/resubmit launches a real job on the prod `amp` gateway
(consumes a compute allocation), so end-to-end launch is left for an explicit,
user-driven test: create a run with an Input-File, `POST /runs/<id>/submit/`
(expect a `RemoteExecution` row + cached status), then `POST /runs/<id>/resubmit/`
(expect a second execution; requires a prior execution with a job id).

## Note on the plan's "populate inpc_data_product_uri" item
The original plan proposed populating `inpc_data_product_uri` on create/submit so
resubmit could read it. The codebase has since moved to the `Input`/`File` model,
so resubmit instead reuses the run's stored inputs via `_build_input_values` —
the same source submit uses — which is the architecturally consistent fix and
avoids reintroducing the single-inpc-file path. The serializer's
`inpc_data_product_uri` handling for the legacy `directedit`/`input_table` flow is
left untouched.
