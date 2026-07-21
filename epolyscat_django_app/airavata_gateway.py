"""Airavata gRPC access helpers for the ePolyScat app.

The rebuilt host portal attaches a Bearer-authenticated raw gRPC channel to
every request as ``request.airavata_channel`` (no SDK facade client). This
module keeps all portal/stub coupling in one place so model, serializer and
view code call plain functions.

Generated pb2/stub imports stay lazy so Django app loading is cheap and does
not require a live channel.
"""

from django.conf import settings


def channel(request):
    """Return the portal-injected Bearer-authenticated gRPC channel."""
    ch = getattr(request, "airavata_channel", None)
    if ch is None:
        raise RuntimeError(
            "Airavata gRPC channel is not available on this request. "
            "The portal's airavata_grpc_client middleware must run (and the "
            "request must be authenticated) before using ePolyScat."
        )
    return ch


# -- stubs ------------------------------------------------------------------


def _experiments(request):
    from airavata.services.experiment_service_pb2_grpc import ExperimentServiceStub

    return ExperimentServiceStub(channel(request))


def _projects(request):
    from airavata.services.project_service_pb2_grpc import ProjectServiceStub

    return ProjectServiceStub(channel(request))


def _app_catalog(request):
    from airavata.services.application_catalog_service_pb2_grpc import (
        ApplicationCatalogServiceStub,
    )

    return ApplicationCatalogServiceStub(channel(request))


def _resources(request):
    from airavata.services.resource_service_pb2_grpc import ResourceServiceStub

    return ResourceServiceStub(channel(request))


def _data_products(request):
    from airavata.services.data_product_service_pb2_grpc import (
        DataProductServiceStub,
    )

    return DataProductServiceStub(channel(request))


# -- generated model modules (lazy) ------------------------------------------


def _pb2(module_path):
    from importlib import import_module

    return import_module(module_path)


def _workspace_pb2():
    return _pb2("airavata.model.workspace.workspace_pb2")


def _experiment_pb2():
    return _pb2("airavata.model.experiment.experiment_pb2")


def _scheduling_pb2():
    return _pb2("airavata.model.scheduling.scheduling_pb2")


def _application_io_pb2():
    return _pb2("airavata.model.application.io.application_io_pb2")


def _status_pb2():
    return _pb2("airavata.model.status.status_pb2")


def _experiment_service_pb2():
    return _pb2("airavata.services.experiment_service_pb2")


def _project_service_pb2():
    return _pb2("airavata.services.project_service_pb2")


def _app_catalog_service_pb2():
    return _pb2("airavata.services.application_catalog_service_pb2")


def _resource_service_pb2():
    return _pb2("airavata.services.resource_service_pb2")


def _data_product_service_pb2():
    return _pb2("airavata.services.data_product_service_pb2")


# -- attribute accessors (proto field names in one place) ---------------------


def project_id(project):
    return project.project_id


def data_product_uri(data_product):
    return data_product.product_uri


def compute_resource_host_name(compute_resource):
    return compute_resource.host_name


def job_id(job):
    return job.job_id


def experiment_id(experiment):
    return experiment.experiment_id


def experiment_outputs(experiment):
    return experiment.experiment_outputs


def experiment_statuses(experiment):
    return experiment.experiment_status


def application_inputs(application_interface):
    return application_interface.application_inputs


def application_outputs(application_interface):
    return application_interface.application_outputs


def application_modules(application_interface):
    return application_interface.application_modules


def application_interface_id(application_interface):
    return application_interface.application_interface_id


# -- projects -----------------------------------------------------------------


def create_project_model(request, name, description=""):
    return _workspace_pb2().Project(
        owner=request.user.username,
        gateway_id=settings.GATEWAY_ID,
        name=name,
        description=description or "",
    )


def create_project(request, project):
    pb2 = _project_service_pb2()
    return (
        _projects(request)
        .CreateProject(
            pb2.CreateProjectRequest(gateway_id=settings.GATEWAY_ID, project=project)
        )
        .project_id
    )


def get_project(request, project_id_):
    pb2 = _project_service_pb2()
    return _projects(request).GetProject(pb2.GetProjectRequest(project_id=project_id_))


def update_project(request, project_id_, project):
    pb2 = _project_service_pb2()
    return _projects(request).UpdateProject(
        pb2.UpdateProjectRequest(project_id=project_id_, project=project)
    )


def delete_project(request, project_id_):
    pb2 = _project_service_pb2()
    return _projects(request).DeleteProject(
        pb2.DeleteProjectRequest(project_id=project_id_)
    )


def get_user_projects(request):
    pb2 = _project_service_pb2()
    return (
        _projects(request)
        .GetUserProjects(
            pb2.GetUserProjectsRequest(
                gateway_id=settings.GATEWAY_ID,
                user_name=request.user.username,
                limit=-1,
                offset=0,
            )
        )
        .projects
    )


# -- application catalog -------------------------------------------------------


def get_application_interface(request, app_interface_id):
    pb2 = _app_catalog_service_pb2()
    return _app_catalog(request).GetApplicationInterface(
        pb2.GetApplicationInterfaceRequest(app_interface_id=app_interface_id)
    )


def get_all_application_interfaces(request):
    pb2 = _app_catalog_service_pb2()
    return (
        _app_catalog(request)
        .GetAllApplicationInterfaces(
            pb2.GetAllApplicationInterfacesRequest(gateway_id=settings.GATEWAY_ID)
        )
        .application_interfaces
    )


# -- experiments ----------------------------------------------------------------


def build_experiment_model(
    request,
    *,
    name,
    description="",
    project_id,
    app_interface_id,
    application_interface,
    group_resource_profile_id=None,
    compute_resource_id=None,
    queue_name=None,
    core_count=None,
    node_count=None,
    walltime_limit=None,
    total_physical_memory=None,
    share_publicly=False,
    enable_email_notification=False,
    email_addresses=(),
):
    """Build an ExperimentModel — the server-side schema a Run is stored as.

    The inputs/outputs are seeded from the application interface; callers set
    input values afterwards on ``experiment.experiment_inputs``.
    """
    experiment_pb2 = _experiment_pb2()
    scheduling_pb2 = _scheduling_pb2()

    user_configuration_data = experiment_pb2.UserConfigurationDataModel(
        group_resource_profile_id=group_resource_profile_id or "",
        share_experiment_publicly=share_publicly,
    )
    # Only include scheduling once a compute resource is chosen: the server
    # resolves resource_host_id on create and rejects an empty one.
    if compute_resource_id:
        user_configuration_data.computational_resource_scheduling.CopyFrom(
            scheduling_pb2.ComputationalResourceSchedulingModel(
                resource_host_id=compute_resource_id,
                total_cpu_count=core_count or 0,
                node_count=node_count or 0,
                wall_time_limit=walltime_limit or 0,
                queue_name=queue_name or "",
                total_physical_memory=total_physical_memory or 0,
            )
        )

    return experiment_pb2.ExperimentModel(
        experiment_name=name,
        description=description or "",
        experiment_inputs=list(application_inputs(application_interface)),
        experiment_outputs=list(application_outputs(application_interface)),
        execution_id=app_interface_id,
        project_id=project_id,
        gateway_id=settings.GATEWAY_ID,
        user_name=request.user.username,
        enable_email_notification=enable_email_notification,
        email_addresses=list(email_addresses),
        user_configuration_data=user_configuration_data,
    )


def search_experiments(request, filters=None, limit=-1, offset=0):
    """ExperimentSummaryModels matching *filters*, a dict keyed by
    ExperimentSearchFields member name (e.g. APPLICATION_ID, PROJECT_ID)."""
    pb2 = _experiment_service_pb2()
    return (
        _experiments(request)
        .SearchExperiments(
            pb2.SearchExperimentsRequest(
                gateway_id=settings.GATEWAY_ID,
                user_name=request.user.username,
                filters=filters or {},
                limit=limit,
                offset=offset,
            )
        )
        .experiments
    )


def delete_experiment(request, experiment_id_):
    """Delete an experiment server-side (only allowed while unlaunched)."""
    pb2 = _experiment_service_pb2()
    return _experiments(request).DeleteExperiment(
        pb2.DeleteExperimentRequest(experiment_id=experiment_id_)
    )


def clone_experiment(request, experiment_id_, new_name, project_id_):
    pb2 = _experiment_service_pb2()
    return (
        _experiments(request)
        .CloneExperiment(
            pb2.CloneExperimentRequest(
                experiment_id=experiment_id_,
                new_experiment_name=new_name,
                new_experiment_project_id=project_id_,
            )
        )
        .experiment_id
    )


def create_experiment(request, experiment):
    pb2 = _experiment_service_pb2()
    return (
        _experiments(request)
        .CreateExperiment(
            pb2.CreateExperimentRequest(
                gateway_id=settings.GATEWAY_ID, experiment=experiment
            )
        )
        .experiment_id
    )


def get_experiment(request, experiment_id_):
    pb2 = _experiment_service_pb2()
    return _experiments(request).GetExperiment(
        pb2.GetExperimentRequest(experiment_id=experiment_id_)
    )


def get_detailed_experiment(request, experiment_id_):
    """Experiment with its processes/tasks/jobs tree (needed for the
    intermediate-output helpers)."""
    pb2 = _experiment_service_pb2()
    return _experiments(request).GetDetailedExperimentTree(
        pb2.GetDetailedExperimentTreeRequest(experiment_id=experiment_id_)
    )


def update_experiment(request, experiment_id_, experiment):
    pb2 = _experiment_service_pb2()
    return _experiments(request).UpdateExperiment(
        pb2.UpdateExperimentRequest(
            experiment_id=experiment_id_, experiment=experiment
        )
    )


def launch_experiment(request, experiment_id_):
    """Launch via the server-side composite that also does the storage setup
    (default storage ids, data-dir creation, tmp-upload relocation)."""
    pb2 = _experiment_service_pb2()
    _experiments(request).LaunchExperimentWithStorageSetup(
        pb2.LaunchExperimentWithStorageSetupRequest(
            experiment_id=experiment_id_,
            gateway_id=settings.GATEWAY_ID,
            notification_email=getattr(request.user, "email", "") or "",
        )
    )


def terminate_experiment(request, experiment_id_):
    pb2 = _experiment_service_pb2()
    return _experiments(request).TerminateExperiment(
        pb2.TerminateExperimentRequest(
            experiment_id=experiment_id_, gateway_id=settings.GATEWAY_ID
        )
    )


def get_experiment_status(request, experiment_id_):
    pb2 = _experiment_service_pb2()
    return _experiments(request).GetExperimentStatus(
        pb2.GetExperimentStatusRequest(experiment_id=experiment_id_)
    )


def get_job_statuses(request, experiment_id_):
    """Mapping of job id -> JobStatus (dict-like, like the legacy client)."""
    pb2 = _experiment_service_pb2()
    return (
        _experiments(request)
        .GetJobStatuses(pb2.GetJobStatusesRequest(experiment_id=experiment_id_))
        .job_statuses
    )


def get_job_details(request, experiment_id_):
    pb2 = _experiment_service_pb2()
    return (
        _experiments(request)
        .GetJobDetails(pb2.GetJobDetailsRequest(experiment_id=experiment_id_))
        .jobs
    )


# -- data products ----------------------------------------------------------------


def get_data_product(request, product_uri):
    pb2 = _data_product_service_pb2()
    return _data_products(request).GetDataProduct(
        pb2.GetDataProductRequest(product_uri=product_uri)
    )


# -- compute resources ---------------------------------------------------------------


def get_compute_resource(request, compute_resource_id):
    pb2 = _resource_service_pb2()
    return _resources(request).GetComputeResource(
        pb2.GetComputeResourceRequest(compute_resource_id=compute_resource_id)
    )


def get_all_compute_resource_names(request):
    """Mapping of compute resource id -> host name."""
    pb2 = _resource_service_pb2()
    return (
        _resources(request)
        .GetAllComputeResourceNames(pb2.GetAllComputeResourceNamesRequest())
        .compute_resource_names
    )


# -- enum helpers ----------------------------------------------------------------


def is_uri_type(data_type):
    app_io_pb2 = _application_io_pb2()
    return data_type in (app_io_pb2.URI, app_io_pb2.URI_COLLECTION)


def data_type_name(data_type):
    return _application_io_pb2().DataType.Name(data_type)


def experiment_state_name(state):
    name = _status_pb2().ExperimentState.Name(state)
    return name.removeprefix("EXPERIMENT_STATE_")


def experiment_state_value(name):
    return getattr(_status_pb2(), f"EXPERIMENT_STATE_{name}")


def job_state_name(state):
    status_pb2 = _status_pb2()
    if state == status_pb2.COMPLETE:
        return "COMPLETED"
    return status_pb2.JobState.Name(state)


def experiment_created_state_name():
    return experiment_state_name(_status_pb2().EXPERIMENT_STATE_CREATED)


def experiment_completed_state():
    return _status_pb2().EXPERIMENT_STATE_COMPLETED


def experiment_terminal_states():
    status_pb2 = _status_pb2()
    return [
        status_pb2.EXPERIMENT_STATE_CANCELED,
        status_pb2.EXPERIMENT_STATE_COMPLETED,
        status_pb2.EXPERIMENT_STATE_FAILED,
    ]


def experiment_cancelable_states():
    status_pb2 = _status_pb2()
    return [
        status_pb2.EXPERIMENT_STATE_VALIDATED,
        status_pb2.EXPERIMENT_STATE_SCHEDULED,
        status_pb2.EXPERIMENT_STATE_LAUNCHED,
        status_pb2.EXPERIMENT_STATE_EXECUTING,
    ]


# -- intermediate outputs (ports of the retired SDK experiment_orchestration
# helpers onto raw stubs + proto walks, mirroring the host portal) -------------


def _output_fetching_processes(experiment):
    """Most-recent-first processes that carry an OUTPUT_FETCHING task."""
    from airavata.model.task import task_pb2

    processes = (
        sorted(experiment.processes, key=lambda p: p.creation_time, reverse=True)
        if experiment.processes
        else []
    )
    return [
        process
        for process in processes
        if any(task.task_type == task_pb2.OUTPUT_FETCHING for task in process.tasks)
    ]


def _detailed(request, experiment):
    """Experiment with its process tree (fetch it if *experiment* has none)."""
    if experiment.processes:
        return experiment
    return get_detailed_experiment(request, experiment.experiment_id)


def can_fetch_intermediate_output(request, experiment, output_name):
    """True only when at least one job is ACTIVE and there is no in-progress
    (non-terminal) intermediate-output process."""
    status_pb2 = _status_pb2()
    pb2 = _experiment_service_pb2()

    experiment = _detailed(request, experiment)
    terminal = (
        status_pb2.PROCESS_STATE_CANCELED,
        status_pb2.PROCESS_STATE_COMPLETED,
        status_pb2.PROCESS_STATE_FAILED,
    )
    jobs = [
        job
        for process in experiment.processes
        for task in process.tasks
        for job in task.jobs
    ]

    def latest_active(job):
        return bool(job.job_statuses) and (
            job.job_statuses[-1].job_state == status_pb2.ACTIVE
        )

    if not any(latest_active(job) for job in jobs):
        return False
    if not _output_fetching_processes(experiment):
        return True
    try:
        process_status = _experiments(request).GetIntermediateOutputProcessStatus(
            pb2.GetIntermediateOutputProcessStatusRequest(
                experiment_id=experiment.experiment_id
            )
        )
        return process_status.state in terminal
    except Exception:
        return True


def fetch_intermediate_output(request, experiment_id_, output_name):
    pb2 = _experiment_service_pb2()
    return _experiments(request).FetchIntermediateOutputs(
        pb2.FetchIntermediateOutputsRequest(
            experiment_id=experiment_id_, output_names=[output_name]
        )
    )


def get_intermediate_output_data_products(request, experiment, output_name):
    """DataProduct protos for the named output: the most-recent completed
    output-fetching process's matching output, with its URIs resolved."""
    status_pb2 = _status_pb2()

    experiment = _detailed(request, experiment)
    matched = None
    for process in _output_fetching_processes(experiment):
        if (
            not process.process_statuses
            or process.process_statuses[-1].state
            != status_pb2.PROCESS_STATE_COMPLETED
        ):
            continue
        for process_output in process.process_outputs:
            if process_output.name == output_name:
                matched = process_output
                break
        if matched is not None:
            break
    if matched is None or not matched.value.startswith("airavata-dp://"):
        return []
    return [get_data_product(request, uri) for uri in matched.value.split(",")]
