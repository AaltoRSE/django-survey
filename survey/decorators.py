import logging
from datetime import date
from functools import wraps

from django.contrib import messages
from django.shortcuts import Http404, get_object_or_404, redirect, reverse
from django.utils.translation import gettext_lazy as _

from survey.models import Survey


def survey_available(func):
    """
    Checks if a survey is available (published and not expired). Use this as a decorator for view functions.

    Staff users get through even when it is not, to preview it; the view is
    passed survey_preview=True then and must not save their answers.
    """

    @wraps(func)
    def survey_check(self, request, *args, **kwargs):
        survey = get_object_or_404(Survey.objects.prefetch_related("questions", "questions__category"), id=kwargs["id"])
        if request.user.is_staff:
            today = date.today()
            preview = not survey.is_published or survey.expire_date < today or survey.publish_date > today
            return func(self, request, *args, **kwargs, survey=survey, survey_preview=preview)
        if not survey.is_published:
            raise Http404
        if survey.expire_date < date.today():
            msg = "Survey is not published anymore. It was published until: '%s'."
            logging.warning(msg, survey.expire_date)
            messages.warning(request, _("This survey has expired for new submissions."))
            return redirect(reverse("survey-list"))
        if survey.publish_date > date.today():
            msg = "Survey is not yet published. It is due: '%s'."
            logging.warning(msg, survey.publish_date)
            raise Http404
        return func(self, request, *args, **kwargs, survey=survey, survey_preview=False)

    return survey_check
