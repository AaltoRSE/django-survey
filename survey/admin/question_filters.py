"""List filters for the question admin's changelist."""

from django.contrib import admin
from django.db.models import Q
from django.http import QueryDict

# Query string prefix of the category filter's parameters.
CATEGORY_PARAM_PREFIX = "category__"


class SurveyListFilter(admin.RelatedFieldListFilter):
    """Survey filter whose links clear the category selection.

    Categories belong to one survey, so a category kept across a survey
    change would leave the list empty.
    """

    def choices(self, changelist):
        for choice in super().choices(changelist):
            params = QueryDict(choice["query_string"].lstrip("?"), mutable=True)
            for key in list(params):
                if key.startswith(CATEGORY_PARAM_PREFIX):
                    del params[key]
            choice["query_string"] = f"?{params.urlencode()}"
            yield choice


class CategoryListFilter(admin.RelatedFieldListFilter):
    """Category filter listing only the categories of the listed questions.

    The choices follow the other filters and the search, so picking a survey
    narrows them to that survey's categories. The selected category always
    stays listed so it can be cleared. When the choices span several surveys,
    labels get the survey pk as prefix to tell same-named categories apart.
    """

    def choices(self, changelist):
        questions = changelist.get_queryset(self.request, exclude_parameters=self.expected_parameters())
        categories = list(
            self.field.related_model.objects.filter(
                Q(pk__in=questions.values("category")) | Q(pk__in=self.lookup_val or [])
            )
        )
        prefix_survey = len({category.survey_id for category in categories}) > 1
        self.lookup_choices = [
            (category.pk, f"{category.survey_id} / {category}" if prefix_survey else str(category))
            for category in categories
        ]
        yield from super().choices(changelist)
