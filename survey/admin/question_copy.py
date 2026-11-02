"""Copy selected questions into a survey from the question admin."""

from django import forms
from django.contrib import admin, messages
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.shortcuts import render

from survey.models import Survey

# Template of the form asking where to copy the questions.
COPY_QUESTIONS_TEMPLATE = "admin/survey/question/copy_questions.html"


class CopyQuestionsForm(forms.Form):
    """Target survey and first order number of the copied questions."""

    survey = forms.ModelChoiceField(queryset=Survey.objects.all(), label="Copy to survey")
    start_order = forms.IntegerField(
        label="Start at order number",
        help_text="Existing questions from this order up are moved further to make room.",
    )


@admin.action(description="Copy selected questions to a survey")
def copy_questions(modeladmin, request, queryset):
    """Ask for the target survey and start order of the selected questions.

    Django action-confirmation pattern: the first click renders the form
    (carrying the selection as hidden inputs); the 'copy' marker on the posted
    form tells us it's the confirmed submission.
    """
    questions = list(queryset.order_by("survey", "order"))
    if "copy" in request.POST:
        form = CopyQuestionsForm(request.POST)
        if form.is_valid():
            modeladmin.message_user(request, "Copying questions is not implemented yet.", messages.WARNING)
            return None
    else:
        form = CopyQuestionsForm()
    context = {
        **modeladmin.admin_site.each_context(request),
        "opts": modeladmin.model._meta,
        "form": form,
        "title": "Copy selected questions to a survey",
        "questions": questions,
        "action_checkbox_name": ACTION_CHECKBOX_NAME,
    }
    return render(request, COPY_QUESTIONS_TEMPLATE, context)
