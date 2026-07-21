"""Unit tests for epolyscat_django_app.airavata_gateway.

No live Airavata server: gRPC stub classes are patched at their defining
modules and requests carry a dummy ``airavata_channel``. Proto messages are
the real generated classes so field names stay honest.
"""

from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase

from epolyscat_django_app import airavata_gateway as gw

EXPERIMENT_STUB = (
    "airavata.services.experiment_service_pb2_grpc.ExperimentServiceStub"
)
PROJECT_STUB = "airavata.services.project_service_pb2_grpc.ProjectServiceStub"
DATA_PRODUCT_STUB = (
    "airavata.services.data_product_service_pb2_grpc.DataProductServiceStub"
)


def make_request(channel="channel", username="testuser", email="test@example.com"):
    user = SimpleNamespace(username=username)
    if email is not None:
        user.email = email
    return SimpleNamespace(airavata_channel=channel, user=user)


class ChannelTestCase(SimpleTestCase):
    def test_returns_portal_injected_channel(self):
        request = make_request(channel="the-channel")
        self.assertEqual(gw.channel(request), "the-channel")

    def test_missing_channel_raises(self):
        request = SimpleNamespace()
        with self.assertRaisesMessage(RuntimeError, "airavata_grpc_client"):
            gw.channel(request)


class ProjectTestCase(SimpleTestCase):
    def test_create_project_model(self):
        project = gw.create_project_model(make_request(), "My Project")
        self.assertEqual(project.owner, "testuser")
        self.assertEqual(project.gateway_id, "test-gateway")
        self.assertEqual(project.name, "My Project")

    @mock.patch(PROJECT_STUB)
    def test_create_project_returns_new_id(self, stub_cls):
        stub_cls.return_value.CreateProject.return_value = SimpleNamespace(
            project_id="new-project-id"
        )
        request = make_request()
        project = gw.create_project_model(request, "p")

        self.assertEqual(gw.create_project(request, project), "new-project-id")
        stub_cls.assert_called_once_with("channel")
        (grpc_request,), _ = stub_cls.return_value.CreateProject.call_args
        self.assertEqual(grpc_request.gateway_id, "test-gateway")
        self.assertEqual(grpc_request.project.name, "p")

    @mock.patch(PROJECT_STUB)
    def test_get_user_projects_scopes_to_user_and_gateway(self, stub_cls):
        stub_cls.return_value.GetUserProjects.return_value = SimpleNamespace(
            projects=["p1", "p2"]
        )
        self.assertEqual(gw.get_user_projects(make_request()), ["p1", "p2"])
        (grpc_request,), _ = stub_cls.return_value.GetUserProjects.call_args
        self.assertEqual(grpc_request.gateway_id, "test-gateway")
        self.assertEqual(grpc_request.user_name, "testuser")
        self.assertEqual(grpc_request.limit, -1)


class BuildExperimentModelTestCase(SimpleTestCase):
    def application_interface(self):
        io_pb2 = gw._application_io_pb2()
        return SimpleNamespace(
            application_inputs=[
                io_pb2.InputDataObjectType(name="in1", type=io_pb2.STRING)
            ],
            application_outputs=[
                io_pb2.OutputDataObjectType(name="out1", type=io_pb2.URI)
            ],
        )

    def test_builds_experiment_model(self):
        experiment = gw.build_experiment_model(
            make_request(),
            name="Water",
            description="a run",
            project_id="run-project",
            app_interface_id="app-iface-1",
            application_interface=self.application_interface(),
            group_resource_profile_id="grp-1",
            compute_resource_id="cr-1",
            core_count=4,
            node_count=2,
            walltime_limit=30,
            queue_name="shared",
            total_physical_memory=1024,
        )
        self.assertEqual(experiment.experiment_name, "Water")
        self.assertEqual(experiment.description, "a run")
        self.assertEqual(experiment.execution_id, "app-iface-1")
        self.assertEqual(experiment.project_id, "run-project")
        self.assertEqual(experiment.gateway_id, "test-gateway")
        self.assertEqual(experiment.user_name, "testuser")
        self.assertEqual(len(experiment.experiment_inputs), 1)
        self.assertEqual(experiment.experiment_inputs[0].name, "in1")
        self.assertEqual(len(experiment.experiment_outputs), 1)
        self.assertEqual(experiment.experiment_outputs[0].name, "out1")

        config = experiment.user_configuration_data
        self.assertEqual(config.group_resource_profile_id, "grp-1")
        self.assertFalse(config.share_experiment_publicly)
        scheduling = config.computational_resource_scheduling
        self.assertEqual(scheduling.resource_host_id, "cr-1")
        self.assertEqual(scheduling.total_cpu_count, 4)
        self.assertEqual(scheduling.node_count, 2)
        self.assertEqual(scheduling.wall_time_limit, 30)
        self.assertEqual(scheduling.queue_name, "shared")
        self.assertEqual(scheduling.total_physical_memory, 1024)

    def test_share_publicly_flag(self):
        experiment = gw.build_experiment_model(
            make_request(),
            name="Tutorial",
            project_id="p",
            app_interface_id="app-iface-1",
            application_interface=self.application_interface(),
            share_publicly=True,
        )
        self.assertTrue(
            experiment.user_configuration_data.share_experiment_publicly
        )

    def test_none_scheduling_values_coalesce_to_defaults(self):
        experiment = gw.build_experiment_model(
            make_request(),
            name="Water",
            project_id="p",
            app_interface_id="app-iface-1",
            application_interface=self.application_interface(),
        )
        config = experiment.user_configuration_data
        self.assertEqual(config.group_resource_profile_id, "")
        scheduling = config.computational_resource_scheduling
        self.assertEqual(scheduling.resource_host_id, "")
        self.assertEqual(scheduling.total_cpu_count, 0)
        self.assertEqual(scheduling.node_count, 0)
        self.assertEqual(scheduling.wall_time_limit, 0)
        self.assertEqual(scheduling.queue_name, "")
        self.assertEqual(scheduling.total_physical_memory, 0)

    def test_email_notification(self):
        experiment = gw.build_experiment_model(
            make_request(),
            name="Water",
            project_id="p",
            app_interface_id="app-iface-1",
            application_interface=self.application_interface(),
            enable_email_notification=True,
            email_addresses=["test@example.com"],
        )
        self.assertTrue(experiment.enable_email_notification)
        self.assertEqual(list(experiment.email_addresses), ["test@example.com"])


class SearchAndCloneTestCase(SimpleTestCase):
    @mock.patch(EXPERIMENT_STUB)
    def test_search_experiments_passes_filters(self, stub_cls):
        stub_cls.return_value.SearchExperiments.return_value = SimpleNamespace(
            experiments=["s1", "s2"]
        )
        result = gw.search_experiments(
            make_request(), {"APPLICATION_ID": "iface-1", "PROJECT_ID": "p-1"}
        )
        self.assertEqual(result, ["s1", "s2"])
        (grpc_request,), _ = stub_cls.return_value.SearchExperiments.call_args
        self.assertEqual(grpc_request.gateway_id, "test-gateway")
        self.assertEqual(grpc_request.user_name, "testuser")
        self.assertEqual(dict(grpc_request.filters)["APPLICATION_ID"], "iface-1")
        self.assertEqual(dict(grpc_request.filters)["PROJECT_ID"], "p-1")
        self.assertEqual(grpc_request.limit, -1)

    @mock.patch(EXPERIMENT_STUB)
    def test_clone_experiment_returns_new_id(self, stub_cls):
        stub_cls.return_value.CloneExperiment.return_value = SimpleNamespace(
            experiment_id="clone-1"
        )
        clone_id = gw.clone_experiment(
            make_request(), "exp-1", "exp resubmit 2", "project-1"
        )
        self.assertEqual(clone_id, "clone-1")
        (grpc_request,), _ = stub_cls.return_value.CloneExperiment.call_args
        self.assertEqual(grpc_request.experiment_id, "exp-1")
        self.assertEqual(grpc_request.new_experiment_name, "exp resubmit 2")
        self.assertEqual(grpc_request.new_experiment_project_id, "project-1")

    @mock.patch(EXPERIMENT_STUB)
    def test_delete_experiment(self, stub_cls):
        gw.delete_experiment(make_request(), "exp-1")
        (grpc_request,), _ = stub_cls.return_value.DeleteExperiment.call_args
        self.assertEqual(grpc_request.experiment_id, "exp-1")


class ProjectMutationTestCase(SimpleTestCase):
    @mock.patch(PROJECT_STUB)
    def test_update_project(self, stub_cls):
        request = make_request()
        project = gw.create_project_model(request, "p", "desc")
        gw.update_project(request, "project-1", project)
        (grpc_request,), _ = stub_cls.return_value.UpdateProject.call_args
        self.assertEqual(grpc_request.project_id, "project-1")
        self.assertEqual(grpc_request.project.name, "p")
        self.assertEqual(grpc_request.project.description, "desc")

    @mock.patch(PROJECT_STUB)
    def test_delete_project(self, stub_cls):
        gw.delete_project(make_request(), "project-1")
        (grpc_request,), _ = stub_cls.return_value.DeleteProject.call_args
        self.assertEqual(grpc_request.project_id, "project-1")


class ExperimentCallsTestCase(SimpleTestCase):
    @mock.patch(EXPERIMENT_STUB)
    def test_create_experiment_returns_new_id(self, stub_cls):
        stub_cls.return_value.CreateExperiment.return_value = SimpleNamespace(
            experiment_id="exp-1"
        )
        experiment = gw._experiment_pb2().ExperimentModel(experiment_name="e")
        self.assertEqual(gw.create_experiment(make_request(), experiment), "exp-1")
        (grpc_request,), _ = stub_cls.return_value.CreateExperiment.call_args
        self.assertEqual(grpc_request.gateway_id, "test-gateway")
        self.assertEqual(grpc_request.experiment.experiment_name, "e")

    @mock.patch(EXPERIMENT_STUB)
    def test_launch_experiment_includes_notification_email(self, stub_cls):
        gw.launch_experiment(make_request(), "exp-1")
        launch = stub_cls.return_value.LaunchExperimentWithStorageSetup
        (grpc_request,), _ = launch.call_args
        self.assertEqual(grpc_request.experiment_id, "exp-1")
        self.assertEqual(grpc_request.gateway_id, "test-gateway")
        self.assertEqual(grpc_request.notification_email, "test@example.com")

    @mock.patch(EXPERIMENT_STUB)
    def test_launch_experiment_without_email(self, stub_cls):
        gw.launch_experiment(make_request(email=None), "exp-1")
        launch = stub_cls.return_value.LaunchExperimentWithStorageSetup
        (grpc_request,), _ = launch.call_args
        self.assertEqual(grpc_request.notification_email, "")

    @mock.patch(EXPERIMENT_STUB)
    def test_terminate_experiment(self, stub_cls):
        gw.terminate_experiment(make_request(), "exp-1")
        (grpc_request,), _ = stub_cls.return_value.TerminateExperiment.call_args
        self.assertEqual(grpc_request.experiment_id, "exp-1")
        self.assertEqual(grpc_request.gateway_id, "test-gateway")

    @mock.patch(EXPERIMENT_STUB)
    def test_get_job_statuses_unwraps_mapping(self, stub_cls):
        stub_cls.return_value.GetJobStatuses.return_value = SimpleNamespace(
            job_statuses={"job-1": "status"}
        )
        self.assertEqual(
            gw.get_job_statuses(make_request(), "exp-1"), {"job-1": "status"}
        )


class AccessorTestCase(SimpleTestCase):
    def test_proto_field_accessors(self):
        status_pb2 = gw._status_pb2()
        experiment = gw._experiment_pb2().ExperimentModel(
            experiment_id="exp-1",
            experiment_status=[
                status_pb2.ExperimentStatus(
                    state=status_pb2.EXPERIMENT_STATE_CREATED
                )
            ],
        )
        self.assertEqual(gw.experiment_id(experiment), "exp-1")
        self.assertEqual(len(gw.experiment_statuses(experiment)), 1)

        project = gw._workspace_pb2().Project(project_id="p-1")
        self.assertEqual(gw.project_id(project), "p-1")


class EnumHelpersTestCase(SimpleTestCase):
    def setUp(self):
        self.status_pb2 = gw._status_pb2()
        self.io_pb2 = gw._application_io_pb2()

    def test_is_uri_type(self):
        self.assertTrue(gw.is_uri_type(self.io_pb2.URI))
        self.assertTrue(gw.is_uri_type(self.io_pb2.URI_COLLECTION))
        self.assertFalse(gw.is_uri_type(self.io_pb2.STRING))

    def test_data_type_name(self):
        self.assertEqual(gw.data_type_name(self.io_pb2.URI), "URI")

    def test_experiment_state_name_strips_prefix(self):
        self.assertEqual(
            gw.experiment_state_name(self.status_pb2.EXPERIMENT_STATE_COMPLETED),
            "COMPLETED",
        )

    def test_experiment_state_value_roundtrip(self):
        self.assertEqual(
            gw.experiment_state_value("COMPLETED"),
            self.status_pb2.EXPERIMENT_STATE_COMPLETED,
        )

    def test_job_state_name_maps_complete_to_completed(self):
        self.assertEqual(gw.job_state_name(self.status_pb2.COMPLETE), "COMPLETED")
        self.assertEqual(gw.job_state_name(self.status_pb2.ACTIVE), "ACTIVE")

    def test_experiment_created_state_name(self):
        self.assertEqual(gw.experiment_created_state_name(), "CREATED")

    def test_experiment_completed_state(self):
        self.assertEqual(
            gw.experiment_completed_state(),
            self.status_pb2.EXPERIMENT_STATE_COMPLETED,
        )

    def test_experiment_terminal_states(self):
        self.assertCountEqual(
            gw.experiment_terminal_states(),
            [
                self.status_pb2.EXPERIMENT_STATE_CANCELED,
                self.status_pb2.EXPERIMENT_STATE_COMPLETED,
                self.status_pb2.EXPERIMENT_STATE_FAILED,
            ],
        )

    def test_experiment_cancelable_states(self):
        self.assertCountEqual(
            gw.experiment_cancelable_states(),
            [
                self.status_pb2.EXPERIMENT_STATE_VALIDATED,
                self.status_pb2.EXPERIMENT_STATE_SCHEDULED,
                self.status_pb2.EXPERIMENT_STATE_LAUNCHED,
                self.status_pb2.EXPERIMENT_STATE_EXECUTING,
            ],
        )


class IntermediateOutputTestCase(SimpleTestCase):
    """Proto-walk helpers for intermediate output fetching."""

    def setUp(self):
        from airavata.model.process import process_pb2
        from airavata.model.task import task_pb2

        self.process_pb2 = process_pb2
        self.task_pb2 = task_pb2
        self.status_pb2 = gw._status_pb2()
        self.io_pb2 = gw._application_io_pb2()
        self.experiment_pb2 = gw._experiment_pb2()

    def make_process(
        self,
        *,
        creation_time=0,
        task_type=None,
        job_state=None,
        process_state=None,
        outputs=(),
    ):
        process = self.process_pb2.ProcessModel(creation_time=creation_time)
        if task_type is not None:
            task = process.tasks.add()
            task.task_type = task_type
            if job_state is not None:
                job = task.jobs.add()
                job.job_statuses.add(job_state=job_state)
        if process_state is not None:
            process.process_statuses.add(state=process_state)
        for name, value in outputs:
            process.process_outputs.add(name=name, value=value)
        return process

    def make_experiment(self, processes):
        experiment = self.experiment_pb2.ExperimentModel(experiment_id="exp-1")
        experiment.processes.extend(processes)
        return experiment

    def test_output_fetching_processes_filters_and_sorts_newest_first(self):
        older = self.make_process(
            creation_time=1, task_type=self.task_pb2.OUTPUT_FETCHING
        )
        newer = self.make_process(
            creation_time=2, task_type=self.task_pb2.OUTPUT_FETCHING
        )
        unrelated = self.make_process(
            creation_time=3, task_type=self.task_pb2.JOB_SUBMISSION
        )
        experiment = self.make_experiment([older, unrelated, newer])

        result = gw._output_fetching_processes(experiment)
        self.assertEqual([p.creation_time for p in result], [2, 1])

    @mock.patch(EXPERIMENT_STUB)
    def test_detailed_fetches_tree_only_when_processes_missing(self, stub_cls):
        detailed = self.make_experiment([self.make_process()])
        stub_cls.return_value.GetDetailedExperimentTree.return_value = detailed

        bare = self.experiment_pb2.ExperimentModel(experiment_id="exp-1")
        self.assertIs(gw._detailed(make_request(), bare), detailed)

        stub_cls.return_value.GetDetailedExperimentTree.reset_mock()
        self.assertIs(gw._detailed(make_request(), detailed), detailed)
        stub_cls.return_value.GetDetailedExperimentTree.assert_not_called()

    def test_can_fetch_requires_an_active_job(self):
        experiment = self.make_experiment(
            [
                self.make_process(
                    task_type=self.task_pb2.JOB_SUBMISSION,
                    job_state=self.status_pb2.COMPLETE,
                )
            ]
        )
        self.assertFalse(
            gw.can_fetch_intermediate_output(make_request(), experiment, "out")
        )

    def test_can_fetch_with_active_job_and_no_prior_fetch(self):
        experiment = self.make_experiment(
            [
                self.make_process(
                    task_type=self.task_pb2.JOB_SUBMISSION,
                    job_state=self.status_pb2.ACTIVE,
                )
            ]
        )
        self.assertTrue(
            gw.can_fetch_intermediate_output(make_request(), experiment, "out")
        )

    @mock.patch(EXPERIMENT_STUB)
    def test_can_fetch_blocked_by_in_progress_fetch_process(self, stub_cls):
        experiment = self.make_experiment(
            [
                self.make_process(
                    task_type=self.task_pb2.JOB_SUBMISSION,
                    job_state=self.status_pb2.ACTIVE,
                ),
                self.make_process(task_type=self.task_pb2.OUTPUT_FETCHING),
            ]
        )
        status = stub_cls.return_value.GetIntermediateOutputProcessStatus

        status.return_value = SimpleNamespace(
            state=self.status_pb2.PROCESS_STATE_EXECUTING
        )
        self.assertFalse(
            gw.can_fetch_intermediate_output(make_request(), experiment, "out")
        )

        status.return_value = SimpleNamespace(
            state=self.status_pb2.PROCESS_STATE_COMPLETED
        )
        self.assertTrue(
            gw.can_fetch_intermediate_output(make_request(), experiment, "out")
        )

        status.side_effect = Exception("no status recorded")
        self.assertTrue(
            gw.can_fetch_intermediate_output(make_request(), experiment, "out")
        )

    @mock.patch(EXPERIMENT_STUB)
    def test_fetch_intermediate_output_sends_single_output_name(self, stub_cls):
        gw.fetch_intermediate_output(make_request(), "exp-1", "out")
        fetch = stub_cls.return_value.FetchIntermediateOutputs
        (grpc_request,), _ = fetch.call_args
        self.assertEqual(grpc_request.experiment_id, "exp-1")
        self.assertEqual(list(grpc_request.output_names), ["out"])

    @mock.patch(DATA_PRODUCT_STUB)
    def test_data_products_resolved_from_latest_completed_fetch(self, stub_cls):
        stub_cls.return_value.GetDataProduct.side_effect = lambda req: (
            f"product:{req.product_uri}"
        )
        experiment = self.make_experiment(
            [
                # newest fetch process is still running: must be skipped
                self.make_process(
                    creation_time=2,
                    task_type=self.task_pb2.OUTPUT_FETCHING,
                    process_state=self.status_pb2.PROCESS_STATE_EXECUTING,
                    outputs=[("out", "airavata-dp://newer")],
                ),
                self.make_process(
                    creation_time=1,
                    task_type=self.task_pb2.OUTPUT_FETCHING,
                    process_state=self.status_pb2.PROCESS_STATE_COMPLETED,
                    outputs=[
                        ("other", "airavata-dp://other"),
                        ("out", "airavata-dp://a,airavata-dp://b"),
                    ],
                ),
            ]
        )
        result = gw.get_intermediate_output_data_products(
            make_request(), experiment, "out"
        )
        self.assertEqual(
            result, ["product:airavata-dp://a", "product:airavata-dp://b"]
        )

    def test_data_products_empty_without_completed_fetch(self):
        experiment = self.make_experiment(
            [
                self.make_process(
                    creation_time=1,
                    task_type=self.task_pb2.OUTPUT_FETCHING,
                    process_state=self.status_pb2.PROCESS_STATE_EXECUTING,
                    outputs=[("out", "airavata-dp://a")],
                )
            ]
        )
        self.assertEqual(
            gw.get_intermediate_output_data_products(
                make_request(), experiment, "out"
            ),
            [],
        )

    def test_data_products_empty_for_non_data_product_value(self):
        experiment = self.make_experiment(
            [
                self.make_process(
                    creation_time=1,
                    task_type=self.task_pb2.OUTPUT_FETCHING,
                    process_state=self.status_pb2.PROCESS_STATE_COMPLETED,
                    outputs=[("out", "/plain/file/path.txt")],
                )
            ]
        )
        self.assertEqual(
            gw.get_intermediate_output_data_products(
                make_request(), experiment, "out"
            ),
            [],
        )
