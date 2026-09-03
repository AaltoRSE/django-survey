from django.apps import AppConfig


class DjangoSurveyAndReportConfig(AppConfig):
    """
    See https://docs.djangoproject.com/en/2.1/ref/applications/#django.apps.AppConfig
    """

    name = "survey"
    label = "survey"
    verbose_name = "Survey and report"
    # Pin the primary key type so a host project's DEFAULT_AUTO_FIELD setting
    # does not demand migrations for this app.
    default_auto_field = "django.db.models.AutoField"
