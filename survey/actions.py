from django.utils.translation import gettext_lazy as _
from django.utils.translation import ungettext

from survey.models import Category, Question


def make_published(modeladmin, request, queryset):
    """
    Mark the given survey as published
    """
    count = queryset.update(is_published=True)
    message = (
        ungettext(
            "%(count)d survey was successfully marked as published.",
            "%(count)d surveys were successfully marked as published",
            count,
        )
        % {"count": count}
    )
    modeladmin.message_user(request, message)


make_published.short_description = _("Mark selected surveys as published")


def copy_survey(modeladmin, request, queryset):
    for survey in queryset:
        # Note the id
        original_id = survey.pk

        # Create a copy of the survey object by saving it with a new pk
        survey.pk = None
        survey.name = survey.name + " Copy"
        survey.save()

        # Note new survey id
        copy_pk = survey.pk

        # Now copy all categories connected to the original survey with the new
        # survey id
        categories_map = {}
        for category in Category.objects.all():
            if category.survey.pk == original_id:
                # This category is linked to the survey, so create a copy.
                # Note the old and new ids in categories_map, this is needed
                # when copying questions
                original_pk = category.pk
                category.pk = None
                category.survey = survey
                category.save()
                categories_map[original_pk] = category

        # Then copy questions connected to this survey
        for question in Question.objects.all():
            if question.survey.pk == original_id:
                # This question is linked to the survey, so create a copy.
                # Note the old and new ids in categories_map, this is needed
                # when copying questions
                question.pk = None
                question.survey = survey
                if question.category is not None:
                    question.category = categories_map[question.category.pk]
                question.save()


copy_survey.short_description = _("Create copies of selected surveys")
