"""Airavata gRPC access helpers for the ePolyScat app.

The host portal's gRPC migration injects an ``AiravataClient`` on
``request.airavata``. Keep that portal coupling in one module so model,
serializer, and view code do not need to know facade names.
"""

from django.conf import settings


def client(request):
    """Return the portal-injected Airavata gRPC client."""
    try:
        return request.airavata
    except AttributeError as exc:
        raise RuntimeError(
            "Airavata gRPC client is not available on this request. "
            "Install the portal gRPC middleware before using ePolyScat."
        ) from exc


def _pb2(module_path):
    """Import generated protobuf modules lazily so Django imports stay cheap."""
    from importlib import import_module

    return import_module(module_path)


def _workspace_pb2():
    return _pb2(
        "airavata_sdk.generated.org.apache.airavata.model.workspace.workspace_pb2"
    )


def _experiment_pb2():
    return _pb2(
        "airavata_sdk.generated.org.apache.airavata.model.experiment.experiment_pb2"
    )


def _scheduling_pb2():
    return _pb2(
        "airavata_sdk.generated.org.apache.airavata.model.scheduling.scheduling_pb2"
    )


def _application_io_pb2():
    return _pb2(
        "airavata_sdk.generated.org.apache.airavata.model.application.io.application_io_pb2"
    )


def _status_pb2():
    return _pb2(
        "airavata_sdk.generated.org.apache.airavata.model.status.status_pb2"
    )


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


def create_project_model(request, name):
    return _workspace_pb2().Project(
        owner=request.user.username,
        gateway_id=settings.GATEWAY_ID,
        name=name,
    )


def create_project(request, project):
    return client(request).research.create_project(settings.GATEWAY_ID, project)


def get_project(request, project_id):
    return client(request).research.get_project(project_id)


def get_user_projects(request):
    return client(request).research.get_user_projects(
        settings.GATEWAY_ID, request.user.username, -1, 0
    )


def get_application_interface(request, app_interface_id):
    return client(request).research.get_application_interface(app_interface_id)


def get_all_application_interfaces(request):
    return client(request).research.get_all_application_interfaces(settings.GATEWAY_ID)


def create_experiment_model(
    request,
    *,
    run,
    run_label,
    app_interface_id,
    application_interface,
    is_tutorial,
):
    experiment_pb2 = _experiment_pb2()
    scheduling_pb2 = _scheduling_pb2()

    return experiment_pb2.ExperimentModel(
        experiment_name=(
            f"{run_label} execution number {run.executions.count() + 1}"
        ),
        experiment_inputs=list(application_inputs(application_interface)),
        experiment_outputs=list(application_outputs(application_interface)),
        execution_id=app_interface_id,
        project_id=(
            run.experiment.airavata_project_id
            if run.experiment is not None
            else run.airavata_project_id
        ),
        gateway_id=settings.GATEWAY_ID,
        user_name=request.user.username,
        user_configuration_data=experiment_pb2.UserConfigurationDataModel(
            group_resource_profile_id=run.group_resource_profile_id or "",
            share_experiment_publicly=is_tutorial,
            computational_resource_scheduling=(
                scheduling_pb2.ComputationalResourceSchedulingModel(
                    resource_host_id=run.compute_resource_id or "",
                    total_cpu_count=run.core_count or 0,
                    node_count=run.node_count or 0,
                    wall_time_limit=run.walltime_limit or 0,
                    queue_name=run.queue_name or "",
                    total_physical_memory=run.total_physical_memory or 0,
                )
            ),
        ),
    )


def create_experiment(request, experiment):
    return client(request).research.create_experiment(settings.GATEWAY_ID, experiment)


def get_experiment(request, experiment_id):
    return client(request).research.get_experiment(experiment_id)


def update_experiment(request, experiment_id, experiment):
    return client(request).research.update_experiment(experiment_id, experiment)


def launch_experiment(request, experiment_id):
    try:
        from airavata_sdk.helpers import experiment_orchestration
    except ImportError:
        client(request).research.launch_experiment(
            experiment_id, gateway_id=settings.GATEWAY_ID
        )
    else:
        experiment_orchestration.launch(
            client(request), experiment_id, username=request.user.username
        )


def terminate_experiment(request, experiment_id):
    return client(request).research.terminate_experiment(
        experiment_id, settings.GATEWAY_ID
    )


def get_experiment_status(request, experiment_id):
    return client(request).research.get_experiment_status(experiment_id)


def get_job_statuses(request, experiment_id):
    return client(request).research.get_job_statuses(experiment_id)


def get_job_details(request, experiment_id):
    return client(request).research.get_job_details(experiment_id)


def get_data_product(request, product_uri):
    return client(request).research.get_data_product(product_uri)


def get_compute_resource(request, compute_resource_id):
    return client(request).compute.get_compute_resource(compute_resource_id)


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


def can_fetch_intermediate_output(request, experiment, output_name):
    from airavata_sdk.helpers import experiment_orchestration

    return experiment_orchestration.can_fetch_intermediate_output(
        client(request), experiment, output_name
    )


def fetch_intermediate_output(request, experiment_id, output_name):
    from airavata_sdk.helpers import experiment_orchestration

    return experiment_orchestration.fetch_intermediate_output(
        client(request), experiment_id, output_name
    )


def get_intermediate_output_data_products(request, experiment, output_name):
    from airavata_sdk.helpers import experiment_orchestration

    return experiment_orchestration.get_intermediate_output_data_products(
        client(request), experiment, output_name
    )
