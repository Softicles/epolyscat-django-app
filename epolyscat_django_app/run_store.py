"""Server-side run storage for the ePolyScat app.

A run is stored in Airavata using the gRPC schemas directly:

- The run itself is an ``ExperimentModel`` (experiment_pb2): name,
  description, owner, project, scheduling
  (``user_configuration_data.computational_resource_scheduling``), inputs
  (``experiment_inputs``), statuses and jobs all live server-side in the
  registry.
- Run files live in gateway user storage under
  ``EPOLYSCAT_Runs/Run_<experiment_id>/`` as data products.
- The app-specific input form state (parameters, radio selections, the file
  list) has no proto field, so it is persisted server-side as a JSON document
  (``.run_inputs.json``) in the run directory; values that do map onto the
  application interface's inputs (application module/utility/workflow,
  Input-File) are mirrored into ``experiment_inputs``.
- Submitting launches the run's own experiment
  (``LaunchExperimentWithStorageSetup``); resubmitting clones it
  (``CloneExperiment``) with ``Previous_JobID_Restart`` set. The launched
  experiment ids form the run's execution chain, tracked in the local
  ``RunExtras`` pointer row (see models.py).
"""

import base64
import io
import json
import logging

from django.conf import settings
from django.utils.text import get_valid_filename

from epolyscat_django_app import airavata_gateway, models, user_storage

logger = logging.getLogger(__name__)

STATUS_UNSUBMITTED = "UNSUBMITTED"
INPUTS_FILENAME = ".run_inputs.json"
# Mutually exclusive calculation-type inputs of the app interface: setting one
# clears the others.
MODULE_INPUT_NAMES = (
    "EPOLYSCAT_Application_Module",
    "Application_Utility",
    "Application_Workflow",
)


# -- application interface -----------------------------------------------------


def get_app_interface_id(request):
    app_module_id = getattr(settings, "EPOLYSCAT", {}).get(
        "EPOLYSCAT_APPLICATION_ID", "ePolyScat_940ab1c9-4ceb-431c-8595-c6246a195442"
    )
    all_app_interfaces = airavata_gateway.get_all_application_interfaces(request)
    app_interfaces = [
        app_interface
        for app_interface in all_app_interfaces
        if app_module_id in airavata_gateway.application_modules(app_interface)
    ]
    if len(app_interfaces) != 1:
        raise Exception(
            f"Could not figure out the applicationInterfaceId for app module {app_module_id}"
        )
    return airavata_gateway.application_interface_id(app_interfaces[0])


# -- projects ------------------------------------------------------------------


def default_project_id(request):
    """The Airavata project runs go into when not grouped under an app
    experiment (a user project, preferring the app's own)."""
    projects = airavata_gateway.get_user_projects(request)
    choices = (
        [p for p in projects if "EPOLYSCAT_app_project" in airavata_gateway.project_id(p)]
        or [p for p in projects if "Default_Project" in airavata_gateway.project_id(p)]
        or [p for p in projects if "Default" in airavata_gateway.project_id(p)]
        or [p for p in projects if "default" in airavata_gateway.project_id(p)]
    )
    if choices:
        return airavata_gateway.project_id(choices[0])
    new_project = airavata_gateway.create_project_model(request, "EPOLYSCAT app project")
    return airavata_gateway.create_project(request, new_project)


def experiment_project_ids(request):
    """Ids of the user's Airavata projects registered as app experiments."""
    return set(
        models.ProjectExtras.objects.filter(deleted=False).values_list(
            "project_id", flat=True
        )
    )


# -- run wrapper ---------------------------------------------------------------


def run_directory(experiment_id):
    return f"EPOLYSCAT_Runs/Run_{get_valid_filename(experiment_id)}"


class ServerRun:
    """Read view over a server-side run: the Airavata ExperimentModel plus
    the local RunExtras pointer row."""

    def __init__(self, request, experiment, extras=None):
        self.request = request
        self.experiment = experiment
        self.extras = extras or models.RunExtras.for_experiment(
            airavata_gateway.experiment_id(experiment)
        )
        self._inputs = None

    # -- identity / core fields (ExperimentModel) --

    @property
    def id(self):
        return self.experiment.experiment_id

    @property
    def name(self):
        return self.experiment.experiment_name

    @property
    def description(self):
        return self.experiment.description

    @property
    def owner(self):
        return self.experiment.user_name

    @property
    def project_id(self):
        return self.experiment.project_id

    @property
    def created(self):
        return _isoformat_millis(self.experiment.creation_time)

    @property
    def updated(self):
        return self.extras.updated.isoformat() if self.extras.updated else self.created

    @property
    def deleted(self):
        return self.extras.deleted

    @property
    def is_email_notification_on(self):
        return self.experiment.enable_email_notification

    # -- scheduling (user_configuration_data.computational_resource_scheduling) --

    @property
    def _scheduling(self):
        return self.experiment.user_configuration_data.computational_resource_scheduling

    @property
    def group_resource_profile_id(self):
        return self.experiment.user_configuration_data.group_resource_profile_id or None

    @property
    def compute_resource_id(self):
        return self._scheduling.resource_host_id or None

    @property
    def queue_name(self):
        return self._scheduling.queue_name or None

    @property
    def core_count(self):
        return self._scheduling.total_cpu_count or None

    @property
    def node_count(self):
        return self._scheduling.node_count or None

    @property
    def walltime_limit(self):
        return self._scheduling.wall_time_limit or None

    @property
    def total_physical_memory(self):
        return self._scheduling.total_physical_memory or None

    # -- storage --

    @property
    def directory(self):
        return run_directory(self.id)

    # Legacy alias used by the file helpers.
    filepath = directory

    def inputs(self):
        """The run's input form state (list of {type, name, value, files})
        from the server-side .run_inputs.json document."""
        if self._inputs is None:
            self._inputs = load_inputs(self.request, self.directory)
        return self._inputs

    # -- executions --

    @property
    def execution_ids(self):
        return self.extras.execution_ids

    @property
    def latest_execution_id(self):
        ids = self.execution_ids
        return ids[-1] if ids else None

    def status(self):
        latest = self.latest_execution_id
        if latest is None:
            return STATUS_UNSUBMITTED
        current = airavata_gateway.get_experiment_status(self.request, latest)
        return airavata_gateway.experiment_state_name(current.state)

    def is_execution_finished(self, experiment_id):
        current = airavata_gateway.get_experiment_status(self.request, experiment_id)
        return current.state in airavata_gateway.experiment_terminal_states()

    def are_all_executions_finished(self):
        return all(
            self.is_execution_finished(experiment_id)
            for experiment_id in self.execution_ids
        )

    def is_cancelable(self):
        latest = self.latest_execution_id
        if latest is None:
            return False
        current = airavata_gateway.get_experiment_status(self.request, latest)
        return current.state in airavata_gateway.experiment_cancelable_states()

    def job_status(self):
        latest = self.latest_execution_id
        if latest is None:
            return STATUS_UNSUBMITTED
        try:
            job_statuses = list(
                airavata_gateway.get_job_statuses(self.request, latest).values()
            )
            if not job_statuses:
                return "NO STATUS"
            job_statuses.sort(key=lambda s: s.time_of_state_change, reverse=True)
            return airavata_gateway.job_state_name(job_statuses[0].job_state)
        except Exception:
            return "---"

    def job_id(self):
        for experiment_id in reversed(self.execution_ids):
            jobs = airavata_gateway.get_job_details(self.request, experiment_id)
            if len(jobs) > 0:
                return airavata_gateway.job_id(jobs[0])
        return None

    def resource_name(self):
        resource_id = self.compute_resource_id
        if not resource_id or not self.execution_ids:
            return ""
        cache = getattr(self.request, "_epolyscat_compute_resource_names", None)
        if cache is None:
            cache = {}
            self.request._epolyscat_compute_resource_names = cache
        if resource_id not in cache:
            try:
                compute_resource = airavata_gateway.get_compute_resource(
                    self.request, resource_id
                )
                cache[resource_id] = airavata_gateway.compute_resource_host_name(
                    compute_resource
                )
            except Exception:
                logger.debug("Failed to resolve compute resource %s", resource_id)
                cache[resource_id] = resource_id
        return cache[resource_id]

    @property
    def view_ids(self):
        return list(self.extras.views.values_list("id", flat=True))


def _isoformat_millis(millis):
    from datetime import datetime, timezone

    if not millis:
        return None
    return datetime.fromtimestamp(millis / 1000, tz=timezone.utc).isoformat()


# -- inputs document -----------------------------------------------------------


def load_inputs(request, directory):
    data_product_uri = user_storage.user_file_exists(
        request, f"{directory}/{INPUTS_FILENAME}"
    )
    if data_product_uri is None:
        return []
    try:
        with user_storage.open_file(request, data_product_uri=data_product_uri) as f:
            return json.loads(f.read().decode())
    except Exception:
        logger.exception("Failed to load %s from %s", INPUTS_FILENAME, directory)
        return []


def save_inputs(request, directory, inputs):
    content = json.dumps(inputs)
    data_product_uri = user_storage.user_file_exists(
        request, f"{directory}/{INPUTS_FILENAME}"
    )
    if data_product_uri is not None:
        user_storage.update_data_product_content(
            request, data_product_uri=data_product_uri, fileContentText=content
        )
    else:
        user_storage.save(
            request,
            directory,
            io.StringIO(content),
            name=INPUTS_FILENAME,
            content_type="application/json",
        )


def _normalize_file_uri(file_data):
    """Return the data product URI in *file_data* under any of its historic
    spellings, or None."""
    for key in ("dataProductURI", "data-product-uri", "data_product_uri"):
        if file_data.get(key):
            return file_data[key]
    return None


def _save_file(request, directory, file_data):
    """Save one incoming file entry into the run directory; returns the
    normalized stored entry {name, dataProductURI}."""
    if file_data.get("contents") is None:
        source_uri = _normalize_file_uri(file_data)
        file = user_storage.open_file(request, data_product_uri=source_uri)
        content_type = user_storage.get_data_product_metadata(
            request, data_product_uri=source_uri
        )["mime_type"]
    elif file_data.get("isPlaintext"):
        file = io.StringIO(file_data["contents"])
        content_type = "text/plain"
    else:
        file = io.BytesIO(base64.b64decode(file_data["contents"]))
        content_type = ""

    saved = user_storage.save(
        request, directory, file, name=file_data["name"], content_type=content_type
    )
    return {"name": file_data["name"], "dataProductURI": saved.productUri}


def _merge_input_entry(request, directory, stored_inputs, entry):
    """Merge one incoming inputs_data entry into *stored_inputs* (mutated in
    place), saving/deleting files in the run directory as needed."""
    existing = next(
        (
            stored
            for stored in stored_inputs
            if stored["name"] == entry["name"] and stored["type"] == entry["type"]
        ),
        None,
    )

    if entry["type"] == "files":
        stored_files = existing["files"] if existing else []
        for file_data in entry.get("files", []):
            old = next(
                (f for f in stored_files if f["name"] == file_data["name"]), None
            )
            if old is not None:
                # Replaced or deleted: drop the stored copy.
                try:
                    user_storage.delete(
                        request, data_product_uri=old["dataProductURI"]
                    )
                except Exception:
                    logger.debug(
                        "Failed to delete replaced file %s", old["dataProductURI"]
                    )
                stored_files.remove(old)
            if not file_data.get("deleted"):
                stored_files.append(_save_file(request, directory, file_data))
        if existing is None:
            stored_inputs.append(
                {"type": "files", "name": entry["name"], "value": None,
                 "files": stored_files}
            )
        else:
            existing["files"] = stored_files
    else:
        # The calculation-type inputs are mutually exclusive: selecting one
        # replaces any previously selected one.
        if entry["name"] in MODULE_INPUT_NAMES:
            stored_inputs[:] = [
                stored
                for stored in stored_inputs
                if stored["name"] not in MODULE_INPUT_NAMES
                or stored["name"] == entry["name"]
            ]
        if existing is not None and existing in stored_inputs:
            existing["value"] = entry.get("value")
        else:
            stored_inputs.append(
                {
                    "type": entry["type"],
                    "name": entry["name"],
                    "value": entry.get("value"),
                    "files": [],
                }
            )


def apply_inputs_data(request, run, inputs_data):
    """Merge incoming inputs_data into the run's server-side inputs document."""
    stored_inputs = load_inputs(request, run.directory)
    for entry in inputs_data:
        _merge_input_entry(request, run.directory, stored_inputs, entry)
    save_inputs(request, run.directory, stored_inputs)
    run._inputs = stored_inputs
    return stored_inputs


def _mirror_inputs_to_experiment(experiment, stored_inputs, input_values=None):
    """Set experiment_inputs values from the app inputs document (and
    *input_values* overrides); unset URI inputs become optional."""
    values = {}
    for entry in stored_inputs:
        if entry["type"] == "files":
            uris = [
                f["dataProductURI"]
                for f in entry.get("files", [])
                if f.get("dataProductURI")
            ]
            if uris:
                values[entry["name"]] = ",".join(uris)
        elif entry.get("value") not in (None, ""):
            values[entry["name"]] = str(entry["value"])
    if input_values:
        values.update(input_values)

    for experiment_input in experiment.experiment_inputs:
        if experiment_input.name in values:
            experiment_input.value = values[experiment_input.name]
        elif airavata_gateway.is_uri_type(experiment_input.type) and not (
            experiment_input.value
        ):
            experiment_input.is_required = False


# -- CRUD ----------------------------------------------------------------------


def summary_status(summary):
    """Normalized experiment state name from an ExperimentSummaryModel."""
    status = summary.experiment_status or ""
    return status.removeprefix("EXPERIMENT_STATE_")


def list_run_summaries(request, *, project_id=None):
    """The user's runs as server-side ExperimentSummaryModels, newest first.
    Resubmission-clone experiments are not runs and are filtered out, as are
    tombstoned (deleted) runs."""
    filters = {
        "APPLICATION_ID": get_app_interface_id(request),
        "USER_NAME": request.user.username,
    }
    if project_id:
        filters["PROJECT_ID"] = project_id
    summaries = list(airavata_gateway.search_experiments(request, filters))
    summaries.sort(key=lambda s: s.creation_time, reverse=True)

    extras_map = {
        extras.experiment_id: extras
        for extras in models.RunExtras.objects.filter(
            experiment_id__in=[s.experiment_id for s in summaries]
        )
    }
    clone_ids = set()
    for extras in models.RunExtras.objects.all():
        for execution_id in extras.execution_ids:
            if execution_id != extras.experiment_id:
                clone_ids.add(execution_id)

    runs = []
    for summary in summaries:
        if summary.experiment_id in clone_ids:
            continue
        extras = extras_map.get(summary.experiment_id)
        if extras is not None and extras.deleted:
            continue
        runs.append(summary)
    return runs


def get_run(request, run_id):
    experiment = airavata_gateway.get_experiment(request, run_id)
    return ServerRun(request, experiment)


def create_run(request, *, name, description="", experiment_project_id=None,
               group_resource_profile_id=None, compute_resource_id=None,
               queue_name=None, core_count=None, node_count=None,
               walltime_limit=None, total_physical_memory=None,
               inputs_data=()):
    app_interface_id = get_app_interface_id(request)
    application_interface = airavata_gateway.get_application_interface(
        request, app_interface_id
    )
    project_id = experiment_project_id or default_project_id(request)

    # The server requires a resolvable compute resource even for unsubmitted
    # experiments; default to the first registered one until the user picks.
    if not compute_resource_id:
        names = airavata_gateway.get_all_compute_resource_names(request)
        compute_resource_id = next(iter(names), None)
        if compute_resource_id is None:
            raise Exception("No compute resources are registered in the gateway")

    experiment = airavata_gateway.build_experiment_model(
        request,
        name=name,
        description=description,
        project_id=project_id,
        app_interface_id=app_interface_id,
        application_interface=application_interface,
        group_resource_profile_id=group_resource_profile_id,
        compute_resource_id=compute_resource_id,
        queue_name=queue_name,
        core_count=core_count,
        node_count=node_count,
        walltime_limit=walltime_limit,
        total_physical_memory=total_physical_memory,
    )
    experiment_id = airavata_gateway.create_experiment(request, experiment)

    run = get_run(request, experiment_id)
    user_storage.create_user_dir(request, dir_names=run.directory.split("/"))
    stored_inputs = apply_inputs_data(request, run, inputs_data)
    _mirror_inputs_to_experiment(run.experiment, stored_inputs)
    airavata_gateway.update_experiment(request, experiment_id, run.experiment)
    return run


def update_run(request, run, *, name=None, description=None,
               group_resource_profile_id=None, compute_resource_id=None,
               queue_name=None, core_count=None, node_count=None,
               walltime_limit=None, total_physical_memory=None,
               is_email_notification_on=None, inputs_data=None):
    experiment = run.experiment
    if name is not None:
        experiment.experiment_name = name
    if description is not None:
        experiment.description = description
    if group_resource_profile_id is not None:
        experiment.user_configuration_data.group_resource_profile_id = (
            group_resource_profile_id
        )
    scheduling = experiment.user_configuration_data.computational_resource_scheduling
    if compute_resource_id is not None:
        scheduling.resource_host_id = compute_resource_id
    if queue_name is not None:
        scheduling.queue_name = queue_name
    if core_count is not None:
        scheduling.total_cpu_count = core_count
    if node_count is not None:
        scheduling.node_count = node_count
    if walltime_limit is not None:
        scheduling.wall_time_limit = walltime_limit
    if total_physical_memory is not None:
        scheduling.total_physical_memory = total_physical_memory
    # The server resolves resource_host_id on update and rejects an empty
    # one; without a chosen compute resource, send no scheduling at all.
    if not scheduling.resource_host_id:
        experiment.user_configuration_data.ClearField(
            "computational_resource_scheduling"
        )
    if is_email_notification_on is not None:
        experiment.enable_email_notification = is_email_notification_on
        del experiment.email_addresses[:]
        if is_email_notification_on:
            email = getattr(request.user, "email", "") or ""
            if email:
                experiment.email_addresses.append(email)

    if inputs_data is not None:
        stored_inputs = apply_inputs_data(request, run, inputs_data)
    else:
        stored_inputs = run.inputs()
    _mirror_inputs_to_experiment(experiment, stored_inputs)

    airavata_gateway.update_experiment(request, run.id, experiment)
    # Touch the pointer row so `updated` reflects this change.
    run.extras.save()
    return run


def delete_run(request, run, delete_associated=True):
    run.extras.deleted = True
    run.extras.save()
    if not run.execution_ids:
        # Never launched: the experiment can also be removed server-side.
        try:
            airavata_gateway.delete_experiment(request, run.id)
        except Exception:
            logger.debug("Server-side delete failed for %s", run.id, exc_info=True)
    if delete_associated:
        try:
            if user_storage.dir_exists(request, run.directory):
                user_storage.delete_dir(request, run.directory)
        except Exception:
            logger.warning("Failed to delete run directory %s", run.directory)


def _adaptor_path(request, data_product_uri):
    """Storage-adaptor-visible SFTP path for a stored file.

    The rebuilt server's InputDataStagingTask uses the input value verbatim
    as an SFTP path — unlike the thrift server it does not resolve
    ``airavata-dp://`` URIs. Replica file_paths are rooted at the gateway
    storage root (``/storage/...``) while the staging adaptor's SFTP session
    is rooted at the login home, where the storage root is visible as
    ``storage/``; stripping the leading slash maps one onto the other.
    """
    data_product = airavata_gateway.get_data_product(request, data_product_uri)
    if not data_product.replica_locations:
        raise FileNotFoundError(f"{data_product_uri} has no replica location")
    return data_product.replica_locations[0].file_path.lstrip("/")


def _stage_input_files(request, run, stored_inputs):
    """{input name: value} overrides for the launch: each files-input value
    is the comma-joined adaptor-visible paths of the run-directory files
    (staging copies them to the compute resource from there)."""
    input_values = {}
    for entry in stored_inputs:
        if entry["type"] != "files":
            continue
        paths = [
            _adaptor_path(request, file_entry["dataProductURI"])
            for file_entry in entry.get("files", [])
            if file_entry.get("dataProductURI")
        ]
        if paths:
            input_values[entry["name"]] = ",".join(paths)
    return input_values


def _launch_execution(request, run, extra_input_values=None):
    """One execution = one launched clone of the run's draft experiment.

    The draft experiment itself is never launched, so it stays in CREATED
    state and remains updatable server-side (Airavata only allows
    UpdateExperiment before launch). This mirrors the legacy model of one
    Airavata experiment per submission.
    """
    if not run.are_all_executions_finished():
        raise Exception("Run already has a currently running execution")

    # Freshen the draft: staged copies of the input files + current values.
    stored_inputs = run.inputs()
    input_values = _stage_input_files(request, run, stored_inputs)
    if extra_input_values:
        input_values.update(extra_input_values)
    _mirror_inputs_to_experiment(run.experiment, stored_inputs, input_values)
    airavata_gateway.update_experiment(request, run.id, run.experiment)

    execution_number = len(run.execution_ids) + 1
    clone_id = airavata_gateway.clone_experiment(
        request,
        run.id,
        f"{run.name} execution number {execution_number}",
        run.project_id,
    )
    airavata_gateway.launch_experiment(request, clone_id)
    run.extras.add_execution(clone_id)
    return run


def submit_run(request, run):
    return _launch_execution(request, run)


def resubmit_run(request, run):
    job_id = run.job_id()
    if job_id is None:
        raise Exception(
            f"Cannot resubmit run {run.id}, has no executions with a job"
        )
    return _launch_execution(
        request, run, extra_input_values={"Previous_JobID_Restart": job_id}
    )


def cancel_run(request, run):
    latest = run.latest_execution_id
    if latest is None:
        raise Exception("Run has no executions to cancel")
    airavata_gateway.terminate_experiment(request, latest)
    return run
