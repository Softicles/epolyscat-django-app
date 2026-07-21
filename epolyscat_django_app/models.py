"""Local metadata for the ePolyScat app.

Run and experiment *data* is stored server-side in Airavata, using the gRPC
schemas directly: a run is an ``ExperimentModel`` (name, description, owner,
inputs, scheduling, statuses, jobs) and the app's run-grouping "experiment"
is an Airavata ``Project``. See ``run_store`` for the facade.

The tables kept here hold only UI state that has no server-side schema:

- ``View``: named collections of runs (plus the unsubmitted/selected/tutorial
  pseudo-collections).
- ``RunExtras``: a thin pointer row per Airavata experiment — view
  membership, a soft-delete tombstone (launched experiments cannot be deleted
  server-side), and the resubmission chain (each resubmit is a cloned
  Airavata experiment).
- ``ProjectExtras``: marks which Airavata projects are ePolyScat run-grouping
  experiments, with a soft-delete tombstone.
- ``PlotParameters``: plot parameter history.

No science data lives in these tables.
"""

import json
import logging

from django.db import models
from django.db.models import Q

logger = logging.getLogger(__name__)


class View(models.Model):
    name = models.CharField(max_length=255)
    owner = models.CharField(
        # Keycloak username; the portal has no Django User model.
        max_length=255, null=True
    )
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    VIEW_TYPE_CHOICES = (
        ("unsubmitted", "Unsubmitted"),
        ("default", "Selected"),
        ("user-defined", "User Defined"),
        ("tutorial", "Tutorial"),
    )
    type = models.CharField(
        max_length=20, default="user-defined", choices=VIEW_TYPE_CHOICES
    )
    deleted = models.BooleanField(default=False)
    order = models.IntegerField(default=0)

    @property
    def is_tutorial(self):
        return self.type == "tutorial"

    @staticmethod
    def tutorial_view():
        return View.objects.filter(type="tutorial", deleted=False).first()

    def __str__(self):
        return self.name

    @staticmethod
    def filter_by_user(request):
        return View.objects.filter(
            Q(owner=request.user.username) | Q(owner=None)
        )

    @staticmethod
    def create_default_views(request):
        owner = request.user.username
        if not View.objects.filter(owner=owner, type="unsubmitted").exists():
            View.objects.create(
                type="unsubmitted", name="Unsubmitted", owner=owner, order=20
            )
        if not View.objects.filter(owner=owner, type="default").exists():
            View.objects.create(type="default", name="Selected", owner=owner, order=10)


class RunExtras(models.Model):
    """App-side pointer row for a run stored server-side as an Airavata
    experiment. ``experiment_id`` is the Airavata experiment id and doubles
    as the run's public id."""

    experiment_id = models.CharField(max_length=255, unique=True)
    views = models.ManyToManyField(View, related_name="runs", blank=True)
    deleted = models.BooleanField(default=False)
    # JSON list of Airavata experiment ids that were actually launched for
    # this run: the run's own experiment once submitted, then one cloned
    # experiment per resubmission (most recent last).
    execution_ids_json = models.TextField(default="[]")
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    @staticmethod
    def for_experiment(experiment_id):
        extras, _created = RunExtras.objects.get_or_create(
            experiment_id=experiment_id
        )
        return extras

    @property
    def execution_ids(self):
        try:
            return json.loads(self.execution_ids_json)
        except ValueError:
            logger.warning(
                "Invalid execution_ids_json for %s", self.experiment_id
            )
            return []

    @execution_ids.setter
    def execution_ids(self, ids):
        self.execution_ids_json = json.dumps(list(ids))

    def add_execution(self, experiment_id):
        ids = self.execution_ids
        if experiment_id not in ids:
            ids.append(experiment_id)
            self.execution_ids = ids
            self.save()

    def __str__(self):
        return self.experiment_id


class ProjectExtras(models.Model):
    """Marks an Airavata project as an ePolyScat run-grouping "experiment"
    (the project itself — name, description, owner — lives server-side)."""

    project_id = models.CharField(max_length=255, unique=True)
    deleted = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.project_id


class PlotParameters(models.Model):
    xaxis = models.CharField(max_length=2, default="")
    yaxes = models.CharField(max_length=20, default="")
    flags = models.CharField(max_length=200, default="")
    last_use = models.DateTimeField(auto_now=True)
    owner = models.CharField(
        # Keycloak username; the portal has no Django User model.
        max_length=255, null=True
    )
    created = models.DateTimeField(auto_now_add=True)

    @staticmethod
    def filter_by_user(request):
        return PlotParameters.objects.filter(owner=request.user.username)

    def __str__(self) -> str:
        return f"x={self.xaxis} y={self.yaxes} {self.flags}"
