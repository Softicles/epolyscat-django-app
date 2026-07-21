"""Unit tests for the server-side run storage helpers (run_store).

These cover the pure-ish pieces: merging incoming inputs_data into the
stored inputs document, and mirroring the document onto an ExperimentModel's
experiment_inputs. Storage calls are mocked; protos are real.
"""

from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase

from epolyscat_django_app import airavata_gateway as gw
from epolyscat_django_app import run_store


def make_request(username="testuser"):
    return SimpleNamespace(
        airavata_channel="channel", user=SimpleNamespace(username=username)
    )


def saved(name, uri):
    return {"name": name, "dataProductURI": uri}


class MergeInputEntryTestCase(SimpleTestCase):
    def merge(self, stored, entry):
        with mock.patch.object(
            run_store, "_save_file",
            side_effect=lambda request, directory, fd: saved(
                fd["name"], f"dp://{fd['name']}"
            ),
        ), mock.patch.object(run_store.user_storage, "delete") as delete:
            run_store._merge_input_entry(make_request(), "dir", stored, entry)
        return stored, delete

    def test_new_string_entry_appended(self):
        stored, _ = self.merge(
            [], {"type": "parameter", "name": "nz", "value": "7"}
        )
        self.assertEqual(
            stored,
            [{"type": "parameter", "name": "nz", "value": "7", "files": []}],
        )

    def test_existing_value_replaced(self):
        stored, _ = self.merge(
            [{"type": "parameter", "name": "nz", "value": "7", "files": []}],
            {"type": "parameter", "name": "nz", "value": "8"},
        )
        self.assertEqual(stored[0]["value"], "8")
        self.assertEqual(len(stored), 1)

    def test_module_inputs_are_mutually_exclusive(self):
        stored = [
            {
                "type": "radio input",
                "name": "EPOLYSCAT_Application_Module",
                "value": "ePolyScat",
                "files": [],
            }
        ]
        stored, _ = self.merge(
            stored,
            {
                "type": "radio input",
                "name": "Application_Utility",
                "value": "SomeUtility",
            },
        )
        names = [entry["name"] for entry in stored]
        self.assertNotIn("EPOLYSCAT_Application_Module", names)
        self.assertIn("Application_Utility", names)

    def test_new_files_entry_saves_files(self):
        stored, _ = self.merge(
            [],
            {
                "type": "files",
                "name": "Input-File",
                "files": [{"name": "inpc", "contents": "x", "isPlaintext": True}],
            },
        )
        self.assertEqual(
            stored[0]["files"], [saved("inpc", "dp://inpc")]
        )

    def test_replacing_file_deletes_old_copy(self):
        stored = [
            {
                "type": "files",
                "name": "Input-File",
                "value": None,
                "files": [saved("inpc", "dp://old")],
            }
        ]
        stored, delete = self.merge(
            stored,
            {
                "type": "files",
                "name": "Input-File",
                "files": [{"name": "inpc", "contents": "new", "isPlaintext": True}],
            },
        )
        delete.assert_called_once()
        self.assertEqual(
            delete.call_args.kwargs["data_product_uri"], "dp://old"
        )
        self.assertEqual(stored[0]["files"], [saved("inpc", "dp://inpc")])

    def test_deleted_file_removed_without_replacement(self):
        stored = [
            {
                "type": "files",
                "name": "Input-File",
                "value": None,
                "files": [saved("inpc", "dp://old")],
            }
        ]
        stored, delete = self.merge(
            stored,
            {
                "type": "files",
                "name": "Input-File",
                "files": [{"name": "inpc", "deleted": True}],
            },
        )
        delete.assert_called_once()
        self.assertEqual(stored[0]["files"], [])


class StageInputFilesTestCase(SimpleTestCase):
    def test_values_are_adaptor_visible_paths(self):
        def fake_get_data_product(request, uri):
            return SimpleNamespace(
                replica_locations=[
                    SimpleNamespace(
                        file_path=f"/storage/EPOLYSCAT_Runs/Run_X/{uri[-1]}.inp"
                    )
                ]
            )

        with mock.patch.object(
            run_store.airavata_gateway, "get_data_product",
            side_effect=fake_get_data_product,
        ):
            values = run_store._stage_input_files(
                make_request(),
                run=None,
                stored_inputs=[
                    {
                        "type": "files",
                        "name": "Input-File",
                        "files": [saved("a.inp", "dp://a"), saved("b.inp", "dp://b")],
                    },
                    {"type": "parameter", "name": "nz", "value": "7", "files": []},
                ],
            )
        self.assertEqual(
            values,
            {
                "Input-File": (
                    "storage/EPOLYSCAT_Runs/Run_X/a.inp,"
                    "storage/EPOLYSCAT_Runs/Run_X/b.inp"
                )
            },
        )

    def test_missing_replica_raises(self):
        with mock.patch.object(
            run_store.airavata_gateway, "get_data_product",
            return_value=SimpleNamespace(replica_locations=[]),
        ):
            with self.assertRaises(FileNotFoundError):
                run_store._adaptor_path(make_request(), "dp://gone")


class MirrorInputsTestCase(SimpleTestCase):
    def experiment(self):
        io_pb2 = gw._application_io_pb2()
        experiment_pb2 = gw._experiment_pb2()
        return experiment_pb2.ExperimentModel(
            experiment_inputs=[
                io_pb2.InputDataObjectType(
                    name="EPOLYSCAT_Application_Module", type=io_pb2.STRING
                ),
                io_pb2.InputDataObjectType(
                    name="Input-File", type=io_pb2.URI, is_required=True
                ),
                io_pb2.InputDataObjectType(
                    name="Previous_JobID_Restart", type=io_pb2.STRING
                ),
            ]
        )

    def test_values_mirrored_from_document(self):
        experiment = self.experiment()
        run_store._mirror_inputs_to_experiment(
            experiment,
            [
                {
                    "type": "radio input",
                    "name": "EPOLYSCAT_Application_Module",
                    "value": "ePolyScat",
                    "files": [],
                },
                {
                    "type": "files",
                    "name": "Input-File",
                    "value": None,
                    "files": [saved("a.inp", "dp://a"), saved("b.inp", "dp://b")],
                },
            ],
        )
        by_name = {i.name: i for i in experiment.experiment_inputs}
        self.assertEqual(by_name["EPOLYSCAT_Application_Module"].value, "ePolyScat")
        self.assertEqual(by_name["Input-File"].value, "dp://a,dp://b")

    def test_unset_uri_inputs_become_optional(self):
        experiment = self.experiment()
        run_store._mirror_inputs_to_experiment(experiment, [])
        by_name = {i.name: i for i in experiment.experiment_inputs}
        self.assertFalse(by_name["Input-File"].is_required)

    def test_overrides_win(self):
        experiment = self.experiment()
        run_store._mirror_inputs_to_experiment(
            experiment,
            [
                {
                    "type": "files",
                    "name": "Input-File",
                    "value": None,
                    "files": [saved("a.inp", "dp://a")],
                }
            ],
            input_values={
                "Input-File": "dp://staged",
                "Previous_JobID_Restart": "12345",
            },
        )
        by_name = {i.name: i for i in experiment.experiment_inputs}
        self.assertEqual(by_name["Input-File"].value, "dp://staged")
        self.assertEqual(by_name["Previous_JobID_Restart"].value, "12345")

    def test_app_specific_entries_do_not_touch_experiment(self):
        experiment = self.experiment()
        run_store._mirror_inputs_to_experiment(
            experiment,
            [
                {"type": "parameter", "name": "nz", "value": "7", "files": []},
                {
                    "type": "radio input",
                    "name": "Calculation_Type",
                    "value": "MODULE",
                    "files": [],
                },
            ],
        )
        names = {i.name for i in experiment.experiment_inputs}
        self.assertNotIn("nz", names)
        self.assertNotIn("Calculation_Type", names)
