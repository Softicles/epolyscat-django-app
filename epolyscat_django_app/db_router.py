"""Route all of this app's models to its private SQLite database.

The host portal has no default database (django.db.backends.dummy raises on any
query), so every ORM operation for epolyscat_django_app must go to the
"epolyscat" alias registered in apps.epolyscatDjangoAppConfig.merge_settings.
"""

APP_LABEL = "epolyscat_django_app"
DB_ALIAS = "epolyscat"


class EPolyScatDBRouter:
    def db_for_read(self, model, **hints):
        if model._meta.app_label == APP_LABEL:
            return DB_ALIAS
        return None

    def db_for_write(self, model, **hints):
        if model._meta.app_label == APP_LABEL:
            return DB_ALIAS
        return None

    def allow_relation(self, obj1, obj2, **hints):
        if (
            obj1._meta.app_label == APP_LABEL
            and obj2._meta.app_label == APP_LABEL
        ):
            return True
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if app_label == APP_LABEL:
            return db == DB_ALIAS
        # Keep other apps (e.g. django.contrib.sessions has no models here, but
        # be safe) out of the epolyscat database.
        if db == DB_ALIAS:
            return False
        return None
