"""Copy selected questions into a survey from the question admin."""

from django import forms
from django.contrib import admin, messages
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.shortcuts import render
from django.db import transaction

from survey.models import Category, Survey

# Template of the form asking where to copy the questions.
COPY_QUESTIONS_TEMPLATE = "admin/survey/question/copy_questions.html"


class CopyQuestionsForm(forms.Form):
    """Target survey, first order number of the copied questions and an order
    number for each copied category."""

    survey = forms.ModelChoiceField(queryset=Survey.objects.all(), label="Copy to survey")
    start_order = forms.IntegerField(
        label="Start at order number",
        help_text="Existing questions from this order up are moved further to make room.",
    )

    def __init__(self, *args, categories=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.categories = categories
        for category in categories:
            self.fields[self.category_field_name(category)] = forms.IntegerField(
                label=f"Order of category {category.survey} / {category}",
                initial=category.order,
                help_text="If a category already exists at this number, it and any after it will be shifted",
            )

    @staticmethod
    def category_field_name(category):
        """Name of the form field holding the order number of category."""
        return f"category_order_{category.pk}"

    def category_orders(self):
        """Return a dict mapping each category to its entered order number."""
        return {category: self.cleaned_data[self.category_field_name(category)] for category in self.categories}


def categories_of(questions):
    """Return the categories of questions, sorted by order number, those without one last."""
    category_ids = {question.category_id for question in questions if question.category_id}
    return sorted(
        Category.objects.filter(pk__in=category_ids),
        key=lambda category: (category.order is None, category.order or 0),
    )


def make_room_for_categories(survey, orders):
    """Move the survey's categories so none has one of the order numbers in orders.

    Going from the lowest new number up, a category already at that number
    moves up by one, along with every category above it. Shifts only move
    categories up, so a number already handled is never taken again.
    """
    for order in sorted(orders):
        if survey.categories.filter(order=order).exists():
            for existing in survey.categories.filter(order__gte=order):
                existing.order += 1
                existing.save(update_fields=["order"])


def copy_categories_to_survey(category_orders, survey):
    """Copy categories into survey with the given order numbers.

    :param dict category_orders: maps each Category to copy to its new order number.
    :return: dict mapping each original category pk to its copy.
    """
    make_room_for_categories(survey, category_orders.values())
    copies = {}
    for category, order in category_orders.items():
        original_pk = category.pk
        category.pk = None
        category._state.adding = True
        category.survey = survey
        category.order = order
        category.save()
        copies[original_pk] = category
    return copies


def copy_questions_to_survey(questions, survey, start_order, category_orders):
    """Copy questions into survey with sequential order numbers from start_order.

    Their categories are copied along, see copy_categories_to_survey().

    :param list questions: the Question objects to copy.
    :param dict category_orders: maps each Category of questions to its new order number.
    """
    with transaction.atomic():
        questions = sorted(questions, key=lambda question: question.order)
        category_copies = copy_categories_to_survey(category_orders, survey)
        count = len(questions)
        for existing in survey.questions.filter(order__gte=start_order):
            existing.order += count
            existing.save(update_fields=["order"])
        for offset, question in enumerate(questions):
            question.pk = None
            question._state.adding = True
            question.survey = survey
            question.order = start_order + offset
            question.category = category_copies.get(question.category_id)
            question.save()


@admin.action(description="Copy selected questions to a survey")
def copy_questions(modeladmin, request, queryset):
    """Ask for the target survey and order numbers of the selected questions.

    Django action-confirmation pattern: the first click renders the form
    (carrying the selection as hidden inputs); the 'copy' marker on the posted
    form tells us it's the confirmed submission.
    """
    questions = list(queryset.order_by("survey", "order"))
    categories = categories_of(questions)
    if "copy" in request.POST:
        form = CopyQuestionsForm(request.POST, categories=categories)
        if form.is_valid():
            copy_questions_to_survey(
                questions,
                form.cleaned_data["survey"],
                form.cleaned_data["start_order"],
                form.category_orders(),
            )
            modeladmin.message_user(
                request,
                f"Copied {len(questions)} questions and {len(categories)} categories "
                f"to survey {form.cleaned_data['survey']}.",
                messages.SUCCESS,
            )
            return None
    else:
        form = CopyQuestionsForm(categories=categories)
    context = {
        **modeladmin.admin_site.each_context(request),
        "opts": modeladmin.model._meta,
        "form": form,
        "title": "Copy selected questions to a survey",
        "questions": questions,
        "action_checkbox_name": ACTION_CHECKBOX_NAME,
    }
    return render(request, COPY_QUESTIONS_TEMPLATE, context)
