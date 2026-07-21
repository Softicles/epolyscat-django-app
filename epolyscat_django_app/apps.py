import logging
import os
from django.apps import AppConfig

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
logger = logging.getLogger(__name__)


# Database alias for the app's private SQLite database. The host portal has no
# default database (django.db.backends.dummy), so this app brings its own and
# routes its models there via epolyscat_django_app.db_router.EPolyScatDBRouter.
DB_ALIAS = "epolyscat"


class epolyscatDjangoAppConfig(AppConfig):
    name = "epolyscat_django_app"
    label = name
    verbose_name = "Epolyscat Django App"
    url_home = "epolyscat_django_app:home"
    fa_icon_class = "fa-atom"
    default_auto_field = "django.db.models.BigAutoField"
    SCRIPTS = os.path.join(BASE_DIR, "ePolyScat", "SCRIPTS")

    def merge_settings(self, settings_module):
        """Called by the portal's dynamic-app loader (commons.dynamic_apps).

        Registers the app-private SQLite database and its router. The portal
        itself is database-less; all of this app's Run/Input/File/... models
        live in this SQLite file. Override the location with EPOLYSCAT_DB_PATH
        in settings_local.py.
        """
        if "webpack_loader" not in settings_module.INSTALLED_APPS:
            settings_module.INSTALLED_APPS.append("webpack_loader")
        db_path = getattr(
            settings_module,
            "EPOLYSCAT_DB_PATH",
            os.path.join(settings_module.BASE_DIR, "epolyscat.sqlite3"),
        )
        settings_module.DATABASES[DB_ALIAS] = {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": db_path,
        }
        routers = list(getattr(settings_module, "DATABASE_ROUTERS", []))
        router_path = "epolyscat_django_app.db_router.EPolyScatDBRouter"
        if router_path not in routers:
            routers.append(router_path)
        settings_module.DATABASE_ROUTERS = routers
        migration_modules = dict(getattr(settings_module, "MIGRATION_MODULES", {}))
        migration_modules.setdefault("epolyscat_django_app", None)
        settings_module.MIGRATION_MODULES = migration_modules
        webpack_loader = dict(getattr(settings_module, "WEBPACK_LOADER", {}))
        webpack_loader["EPOLYSCAT_DJANGO_APP"] = {
            "BUNDLE_DIR_NAME": "epolyscat_django_app/dashboard/dist/",
            "STATS_FILE": os.path.join(
                BASE_DIR,
                "static",
                "epolyscat_django_app",
                "dashboard",
                "dist",
                "webpack-stats.json",
            ),
        }
        settings_module.WEBPACK_LOADER = webpack_loader
        rest_framework = dict(getattr(settings_module, "REST_FRAMEWORK", {}))
        rest_framework.setdefault(
            "DEFAULT_AUTHENTICATION_CLASSES",
            ["epolyscat_django_app.drf_auth.PortalRequestUserAuthentication"],
        )
        rest_framework.setdefault("UNAUTHENTICATED_USER", None)
        settings_module.REST_FRAMEWORK = rest_framework

    APPLICATION_SETTINGS = {
        "EPOLYSCAT_DJANGO_APP": {
            "INPUT_PAGES": {
                "Discretization": [
                    {
                        "Axis": [
                            "name",
                            "lower end",
                            "upper end",
                            "order",
                            "nElem",
                            "functions",
                            "subset",
                            "exactIntegral",
                        ]
                    },
                    {
                        "Absorption": [
                            "axis",
                            "kind",
                            "theta",
                            "upper",
                            "lower",
                            "unitary",
                        ]
                    },
                    {"IndexConstraint": ["axes", "name"]},
                    {"BasisConstraint": ["axes", "kind"]},
                ],
                "Propagation": [
                    {
                        "TimePropagation": [
                            "begin",
                            "end",
                            "print",
                            "accuracy",
                            "store",
                            "fixStep",
                            "method",
                            "cutEnergy",
                            "operatorThreshold",
                        ]
                    }
                ],
                "Spectrum": [
                    {
                        "Spectrum": [
                            "radialPoints",
                            "maxEnergy",
                            "plot",
                            "energyGrid",
                            "minEnergy",
                            "symmetry12",
                        ]
                    },
                    {"Source": ["turnOff", "Region", "end"]},
                    {"Surface": ["points"]},
                ],
                "System": [
                    {
                        "Operator": [
                            "expectationValue",
                            "hamiltonian",
                            "initial",
                            "interaction",
                            "projection",
                            "smooth",
                            "truncate",
                        ]
                    },
                    {
                        "Laser": [
                            "shape",
                            "FWHM",
                            "I(W/cm2)",
                            "lambda(nm)",
                            "phiCEO",
                            "polarAngle",
                        ]
                    },
                    {"Dipole": ["acceleration", "length", "velocity"]},
                ],
            },
            "ALL_INPUTS": [
                {"Absorption": ["axis", "kind", "lower", "theta", "unitary", "upper"]},
                {
                    "Axis": [
                        "exactIntegral",
                        "functions",
                        "lower end",
                        "nCoefficients",
                        "nElem",
                        "name",
                        "order",
                        "subset",
                        "upper end",
                    ]
                },
                {"BasisConstraint": ["axes", "kind"]},
                {"ChannelsSubregion": ["tStore"]},
                {"Columbus": ["path"]},
                {"Constant": ["name"]},
                {"DEBUG": ["sample"]},
                {"Eigensolver": ["method", "shift"]},
                {"Eigen": ["select"]},
                {"FactorMatrix": ["name", "ncol", "nrow"]},
                {"Initial": ["kind", "state"]},
                {
                    "Laser": [
                        "FWHM",
                        "I(W/cm2)",
                        "azimuthAngle",
                        "ePhoton",
                        "ePhoton@I/2",
                        "ellip",
                        "ellipAng",
                        "lambda(nm)",
                        "lambda@I/2(nm)",
                        "peak",
                        "phiCEO",
                        "polarAngle",
                        "shape",
                    ]
                },
                {
                    "Operator": [
                        "expectationValue",
                        "hamiltonian",
                        "initial",
                        "interaction",
                        "parameterTerm",
                        "projection",
                        "smooth",
                        "spectrum",
                        "truncate",
                    ]
                },
                {"Parallel": ["sort"]},
                {"PlotFunction": ["algebra", "lower", "points", "upper"]},
                {"Plot_user": ["axis", "lowerBound", "points", "upperBound", "usage"]},
                {"Polar2D": ["Mmax", "Nmax", "origin", "quad", "radius"]},
                {
                    "PolarOffCenter": [
                        "Lmax",
                        "Mmax",
                        "Nmax",
                        "origin",
                        "quad",
                        "radius",
                    ]
                },
                {"Print": ["noScreen"]},
                {"Pulse": ["check"]},
                {"Source": ["Region", "end", "turnOff"]},
                {
                    "Spectrum": [
                        "amplitude",
                        "benchmark",
                        "energyGrid",
                        "maxEnergy",
                        "minEnergy",
                        "plot",
                        "radialPoints",
                        "spectrum",
                        "symmetry12",
                    ]
                },
                {"SpectrumPlot": ["noOverwrite"]},
                {"Surface": ["points"]},
                {
                    "TimePropagation": [
                        "accuracy",
                        "begin",
                        "cutEnergy",
                        "end",
                        "fixStep",
                        "method",
                        "operatorThreshold",
                        "print",
                        "store",
                    ]
                },
                {
                    "_EXPERT_": [
                        "FDgrid",
                        "FDmatrix",
                        "flatDer",
                        "fuseOperator",
                        "halfPlaneEta",
                        "halfPlaneR",
                        "halfPlaneS",
                        "newFloor",
                        "suppressTensor",
                    ]
                },
            ],
            "MASTER_LINP": os.path.join(BASE_DIR, "data", "epolyscat", "linp"),
            "FILE_PLOTABLE": {
                "spec_total": "energy-differential spectrum",
                "spec_partial": "partial-wave spectrum",
                "expec": "expectation values (defined in input)",
                "Laser": "field, vector potential etc. in all directions",
                "eig": "eigenvalues",
            },
            "FILE_SCREENOUTPUT": {
                "outf": "screen-style output",
                "outspec": "screen-style output for amplitude integration",
            },
            "FILE_INPUT": {
                "inpc": "literal copy of input file",
            },
        }
    }

    APPLICATION_SETTINGS["EPOLYSCAT_DJANGO_APP"]["FILE_VIEWABLE"] = {
        "WARNINGS": "list of all warnings with detailed explanations where available",
        **APPLICATION_SETTINGS["EPOLYSCAT_DJANGO_APP"]["FILE_INPUT"],
        **APPLICATION_SETTINGS["EPOLYSCAT_DJANGO_APP"]["FILE_SCREENOUTPUT"],
        **APPLICATION_SETTINGS["EPOLYSCAT_DJANGO_APP"]["FILE_PLOTABLE"],
        "timer": "run-time for sections of the code",
        "mon": "monitor of ongoing run",
        "log": "list of all monitor outputs",
        "linp": "tRecX-processed input, including all defaults",
    }
