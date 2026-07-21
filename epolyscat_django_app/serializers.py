"""Serializers over the server-side (gRPC) schemas.

Runs serialize from ``run_store.ServerRun`` (an Airavata ExperimentModel plus
the local pointer row); app experiments serialize from Airavata ``Project``
protos. The JSON contract with the frontend (``RunService.encodeObj`` /
``ViewService.encodeObj``) is unchanged from the SQLite-backed implementation.
"""

import logging

from django.db import transaction
from django.db.models import Q
from rest_framework import serializers

from epolyscat_django_app import airavata_gateway, models, run_store

logger = logging.getLogger(__name__)


class RunSerializer(serializers.Serializer):
    """Validates run write payloads and serializes ServerRun instances."""

    name = serializers.CharField(max_length=255, required=False)
    description = serializers.CharField(
        max_length=4000, allow_blank=True, required=False, default=""
    )
    # Airavata project id of the app experiment this run is grouped under.
    experiment = serializers.CharField(
        max_length=255, required=False, allow_null=True, allow_blank=True
    )
    is_email_notification_on = serializers.BooleanField(required=False)
    group_resource_profile_id = serializers.CharField(
        max_length=255, required=False, allow_null=True, allow_blank=True
    )
    compute_resource_id = serializers.CharField(
        max_length=255, required=False, allow_null=True, allow_blank=True
    )
    queue_name = serializers.CharField(
        max_length=64, required=False, allow_null=True, allow_blank=True
    )
    core_count = serializers.IntegerField(required=False, allow_null=True)
    node_count = serializers.IntegerField(required=False, allow_null=True)
    walltime_limit = serializers.IntegerField(required=False, allow_null=True)
    total_physical_memory = serializers.IntegerField(required=False, allow_null=True)

    def validate_experiment(self, value):
        if not value:
            return None
        request = self.context["request"]
        if not models.ProjectExtras.objects.filter(
            project_id=value, deleted=False
        ).exists():
            raise serializers.ValidationError(
                f"{value} is not one of your experiments"
            )
        # The server enforces access on use; a cheap existence check here
        # keeps error messages friendly.
        try:
            airavata_gateway.get_project(request, value)
        except Exception as e:
            raise serializers.ValidationError(
                f"Could not load experiment project {value}"
            ) from e
        return value

    def to_representation(self, run: run_store.ServerRun):
        request = self.context["request"]
        tutorial_view = models.View.tutorial_view()
        view_ids = run.view_ids
        is_tutorial = (
            tutorial_view is not None
            and tutorial_view.id in view_ids
            and request.user.username != run.owner
        )
        status = run.status()
        experiment_projects = run_store.experiment_project_ids(request)
        return {
            "id": run.id,
            "owner": run.owner,
            "name": run.name,
            "description": run.description,
            "airavata_project_id": run.project_id,
            "experiment": (
                run.project_id if run.project_id in experiment_projects else None
            ),
            "views": view_ids,
            "created": run.created,
            "updated": run.updated,
            "deleted": run.deleted,
            "is_email_notification_on": run.is_email_notification_on,
            "group_resource_profile_id": run.group_resource_profile_id,
            "compute_resource_id": run.compute_resource_id,
            "queue_name": run.queue_name,
            "core_count": run.core_count,
            "node_count": run.node_count,
            "walltime_limit": run.walltime_limit,
            "total_physical_memory": run.total_physical_memory,
            "inputs": [
                {
                    "type": entry.get("type"),
                    "name": entry.get("name"),
                    "value": entry.get("value"),
                    "files": [
                        {
                            "name": file_entry.get("name"),
                            "data_product_uri": file_entry.get("dataProductURI"),
                        }
                        for file_entry in entry.get("files", [])
                    ],
                }
                for entry in run.inputs()
            ],
            "executions": run.execution_ids,
            "status": status,
            "job_status": run.job_status(),
            "job_id": run.job_id(),
            "resource": run.resource_name(),
            "is_tutorial": is_tutorial,
        }


class ExperimentSerializer(serializers.Serializer):
    """App run-grouping "experiment", stored server-side as an Airavata
    Project. Serializes (project, ProjectExtras) pairs."""

    name = serializers.CharField(max_length=255, required=True)
    description = serializers.CharField(
        max_length=4000, allow_blank=True, required=False, default=""
    )

    def validate_name(self, value):
        request = self.context["request"]
        existing_ids = run_store.experiment_project_ids(request)
        for project in airavata_gateway.get_user_projects(request):
            if (
                airavata_gateway.project_id(project) in existing_ids
                and project.name == value
                and project.owner == request.user.username
            ):
                instance_id = (
                    airavata_gateway.project_id(self.instance[0])
                    if self.instance is not None
                    else None
                )
                if airavata_gateway.project_id(project) != instance_id:
                    raise serializers.ValidationError(
                        "You already have an experiment with this name"
                    )
        return value

    def to_representation(self, instance):
        project, extras = instance
        request = self.context["request"]
        project_id = airavata_gateway.project_id(project)
        run_summaries = run_store.list_run_summaries(
            request, project_id=project_id
        )
        return {
            "id": project_id,
            "name": project.name,
            "description": project.description,
            "owner": project.owner,
            "created": run_store._isoformat_millis(project.creation_time),
            "updated": extras.updated.isoformat() if extras else None,
            "deleted": extras.deleted if extras else False,
            "airavata_project_id": project_id,
            "run_count": len(run_summaries),
            "active_run_count": len(run_summaries),
        }

    def create(self, validated_data):
        request = self.context["request"]
        project = airavata_gateway.create_project_model(
            request,
            validated_data["name"],
            validated_data.get("description", ""),
        )
        project_id = airavata_gateway.create_project(request, project)
        extras, _ = models.ProjectExtras.objects.get_or_create(project_id=project_id)
        return airavata_gateway.get_project(request, project_id), extras

    def update(self, instance, validated_data):
        request = self.context["request"]
        project, extras = instance
        # Name stays fixed (it identifies the experiment); description is
        # editable, matching the previous behavior.
        project.description = validated_data.get("description", project.description)
        airavata_gateway.update_project(
            request, airavata_gateway.project_id(project), project
        )
        if extras:
            extras.save()
        return project, extras


class PlotfileSerializer(serializers.Serializer):
    prefix = serializers.CharField(max_length=50, allow_blank=True)
    data_product_uri = serializers.CharField(max_length=200)


class PlotParametersIdRelatedField(serializers.PrimaryKeyRelatedField):
    def get_queryset(self):
        request = self.context["request"]
        return models.PlotParameters.filter_by_user(request)


class PlotParametersSerializer(serializers.ModelSerializer):
    xaxis = serializers.CharField(default="", allow_blank=True)
    yaxes = serializers.CharField(default="", allow_blank=True)
    flags = serializers.CharField(default="", allow_blank=True)

    class Meta:
        model = models.PlotParameters
        fields = (
            "id",
            "xaxis",
            "yaxes",
            "flags",
            "created",
            "last_use",
        )

    def create(self, validated_data):
        request = self.context["request"]
        plot_parameters, created = models.PlotParameters.objects.get_or_create(
            **validated_data,
            owner=request.user.username,
        )
        return plot_parameters

    def validate(self, attrs):
        attrs = super().validate(attrs)
        xaxis = attrs.get("xaxis", "")
        yaxes = attrs.get("yaxes", "")
        if xaxis and not yaxes:
            raise serializers.ValidationError(
                {"yaxes": ["yaxes is required when xaxis is also specified"]}
            )
        if yaxes and not xaxis:
            raise serializers.ValidationError(
                {"xaxis": ["xaxis is required when yaxes is also specified"]}
            )
        return attrs


class RunIdsField(serializers.ListField):
    """Run ids are Airavata experiment ids (strings); views resolve them via
    run_store after validation."""

    child = serializers.CharField(max_length=255)


class PlotSerializer(serializers.Serializer):
    runs = RunIdsField(required=False, default=list)
    plotfile = serializers.CharField(max_length=20, required=False, allow_blank=True)
    plotfiles = PlotfileSerializer(many=True)
    plot_parameters = PlotParametersSerializer(required=False)
    plot_parameters_id = PlotParametersIdRelatedField(required=False)

    def validate(self, attrs):
        if "plot_parameters" not in attrs and "plot_parameters_id" not in attrs:
            raise serializers.ValidationError(
                "One of plot_parameters or plot_parameters_id is required"
            )
        return attrs


class ListInputsSerializer(serializers.Serializer):
    runs = RunIdsField()


class DiffInputsSerializer(serializers.Serializer):
    runs = RunIdsField()


class PlotablesSerializer(serializers.Serializer):
    runs = RunIdsField()


class AddRemoveRunsSerializer(serializers.Serializer):
    runs = RunIdsField()


class ViewSerializer(serializers.ModelSerializer):
    run_count = serializers.SerializerMethodField()
    active_run_count = serializers.SerializerMethodField()
    owner = serializers.ReadOnlyField()
    runs = serializers.SerializerMethodField()
    is_tutorial = serializers.ReadOnlyField()

    class Meta:
        model = models.View
        fields = (
            "id", "name", "owner", "created", "updated", "deleted", "type",
            "run_count", "runs", "active_run_count", "is_tutorial",
        )

    def _get_server_runs(self, view_instance: models.View):
        cache = getattr(view_instance, "_server_runs", None)
        if cache is not None:
            return cache
        request = self.context["request"]
        runs = []
        for extras in view_instance.runs.filter(deleted=False):
            try:
                run = run_store.get_run(request, extras.experiment_id)
                run.extras = extras
                runs.append(run)
            except Exception:
                logger.warning(
                    "Could not load run %s for view %s",
                    extras.experiment_id,
                    view_instance.id,
                )
        view_instance._server_runs = runs
        return runs

    def get_runs(self, view_instance: models.View):
        return RunSerializer(
            self._get_server_runs(view_instance),
            many=True,
            context=self.context,
        ).data

    def get_run_count(self, view_instance: models.View):
        return len(self._get_server_runs(view_instance))

    def get_active_run_count(self, view_instance: models.View):
        return len(self._get_server_runs(view_instance))

    @transaction.atomic(using="epolyscat")
    def create(self, validated_data):
        request = self.context["request"]
        validated_data.setdefault("owner", request.user.username)
        validated_data["type"] = "user-defined"
        return models.View.objects.create(**validated_data)

    @transaction.atomic(using="epolyscat")
    def update(self, instance, validated_data):
        if instance.type == "user-defined":
            instance.name = validated_data.pop("name", instance.name)
        instance.save()
        return instance
