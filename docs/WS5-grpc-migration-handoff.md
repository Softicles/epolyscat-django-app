# WS5 gRPC Migration Handoff

## Branch

Implemented on branch `thrift-to-gRPC`.

## Frontend Checkpoint

Committed existing frontend work first as `ceb0136`:

`Add experiment-aware run navigation in the frontend`

No co-author trailer was added.

## Backend Migration Changes

- Added `epolyscat_django_app/airavata_gateway.py`.
- Migrated active backend Airavata paths in:
  - `epolyscat_django_app/models.py`
  - `epolyscat_django_app/serializers.py`
  - `epolyscat_django_app/views.py`
- Updated `setup.cfg` with:
  - `airavata-python-sdk>=3.0.0`

## Adapter Responsibilities

`airavata_gateway.py` centralizes access to the portal-injected `request.airavata`
gRPC client.

It uses these gRPC facades:

- `client.research` for projects, experiments, app interfaces, data products, and jobs.
- `client.compute` for compute resources.

It lazily imports generated protobuf modules from `airavata_sdk.generated`.

It provides helpers for:

- Project creation, listing, and id extraction.
- Experiment creation, status, update, launch, and termination.
- App-interface input, output, module, and id access.
- Compute host-name extraction.
- Job id and status extraction.
- Experiment/job enum name and value conversion.
- Intermediate-output helpers through `airavata_sdk.helpers.experiment_orchestration`.
- Data-product URI extraction.

## Behavior Changes

- `models.py` no longer imports Thrift `Project`, `ExperimentModel`, or `ExperimentState`.
- `serializers.py` no longer uses Thrift project, status, or job APIs.
- `views.py` no longer builds Thrift experiment or scheduling models.
- `views.py` now builds protobuf experiment models through
  `airavata_gateway.create_experiment_model()`.
- `experiment_util.launch()` is replaced with `airavata_gateway.launch_experiment()`,
  which calls SDK gRPC experiment orchestration when available.
- Data products returned by gRPC are normalized to URI strings before passing into
  `user_storage`.

## Verification Already Run

`py_compile` passed for:

- `epolyscat_django_app/airavata_gateway.py`
- `epolyscat_django_app/models.py`
- `epolyscat_django_app/serializers.py`
- `epolyscat_django_app/views.py`

`setup.cfg` parsed correctly with the new dependency.

An `rg` scan found no active direct `request.airavata_client`, `authz_token`,
Thrift `ttypes`, `ExperimentState`, `ExperimentModel`, `DataType`, or
`experiment_util` usage in `epolyscat_django_app/*.py`. Remaining matches are
comments or adapter protobuf references.

## Blocked Verification

`manage.py check` failed before Django setup completed because the host portal still
initializes a Thrift pool and DNS resolution failed for:

`prod-airavata.scigap.org:9930`

The current portal venv still has `airavata-python-sdk 2.2.7`, not SDK 3.0.

The local gRPC SDK checkout is:

`/home/thinh/Desktop/ARTISAN/new_portal/airavata/airavata-python-sdk`

It is from:

`https://github.com/apache/airavata.git`

Commit:

`6edb39c1a26fd2bcc9e454162a562811a03cd32a`

## Testing Prerequisites

- Install or activate portal Track D middleware exposing `request.airavata`.
- Upgrade the portal venv to `airavata-python-sdk>=3.0.0`.
- Ensure compatible `protobuf>=4.25.0`.
- Configure gRPC endpoint settings in the host portal.
- Do not commit portal changes unless explicitly allowed.

## Recommended Tests

After prerequisites are in place:

```bash
python manage.py check
python manage.py shell -c "import epolyscat_django_app.views, epolyscat_django_app.models, epolyscat_django_app.serializers"
```

Then verify through authenticated API/UI flows:

- Create a run through the API.
- Submit a run and confirm `RemoteExecution.airavata_experiment_id` is created.
- Poll run detail/status and confirm status/job status update over gRPC.
- Resubmit a completed or failed run and confirm a second `RemoteExecution`.
- Toggle email notifications and confirm experiment update succeeds.
- Open output/viewable files and confirm data-product URI handling works.
- Confirm create-run application interface lookup resolves the ePolyScat app module.
