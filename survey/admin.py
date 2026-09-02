from django import forms
from django.contrib import admin
from django_ace import AceWidget

from survey.actions import make_published
from survey.admin_impl.question_order import pinned_question_ids, shift_colliding_questions
from survey.exporter.csv import Survey2Csv
from survey.exporter.tex import Survey2Tex
from survey.models import Answer, Category, CssSnippet, Question, QuestionCondition, Response, Survey
from survey.models.question import SCALE_PRESETS


class ConditionInline(admin.StackedInline):
    model = QuestionCondition
    fk_name = "question"
    extra = 0

    def get_formset(self, request, obj=None, **kwargs):
        # `obj` is the parent Question being edited; restrict the "depends on"
        # dropdown to earlier questions of the same survey. Model.clean()
        # remains the enforcement backstop.
        formset = super().get_formset(request, obj, **kwargs)
        if obj is not None:
            depends_on_field = formset.form.base_fields.get("depends_on")
            if depends_on_field is not None:
                depends_on_field.queryset = Question.objects.filter(survey=obj.survey, order__lt=obj.order)
        return formset


class ScalePresetForm(forms.ModelForm):
    """Question form with a ready-made range picker for the integer scale.

    The dropdown is pure UI: admin_scale.js copies the picked range into the
    minimum/maximum fields, and those fields are what gets saved. clean() never
    reads the preset."""

    scale_preset = forms.ChoiceField(
        choices=[("", "Custom")] + [(f"{low}:{high}", f"{low} to {high}") for low, high in SCALE_PRESETS],
        required=False,
        label="Scale range",
        help_text="Fills in minimum and maximum",
    )

    class Meta:
        model = Question
        fields = "__all__"

    class Media:
        js = ("survey/js/admin_scale.js", "survey/js/admin_question_type.js")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        limits = (self.instance.scale_min, self.instance.scale_max)
        if limits in SCALE_PRESETS:
            self.fields["scale_preset"].initial = f"{limits[0]}:{limits[1]}"


class QuestionAdmin(admin.ModelAdmin):
    """Attach conditions to a question.

    Researchers keep creating questions in the Survey admin's Question inline
    as before, then come here to attach conditions or customize the "other"
    option label.
    """

    form = ScalePresetForm
    list_display = ("text", "survey", "order", "type")
    list_filter = ("survey",)
    inlines = [ConditionInline]


admin.site.register(Question, QuestionAdmin)


class ParentQuestionChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        text = obj.text if len(obj.text) <= 50 else obj.text[:47] + "..."
        return f"question {obj.order} – {text}"


class QuestionInlineForm(ScalePresetForm):
    """Question form with a one-row condition editor (question/operator/value),
    flattened from the QuestionCondition one-to-one row so researchers can
    author everything on the Survey page (stock admin cannot nest that inline
    here). The standalone Question page keeps the full editor, e.g. for
    customizing the "other" label."""

    OPERATOR_LABELS = [
        (QuestionCondition.OP_IN, "is one of"),
        (QuestionCondition.OP_EQ, "is equal to"),
        (QuestionCondition.OP_NE, "is not equal to"),
        (QuestionCondition.OP_LT, "is less than"),
        (QuestionCondition.OP_LE, "is at most"),
        (QuestionCondition.OP_GT, "is greater than"),
        (QuestionCondition.OP_GE, "is at least"),
    ]

    condition_question = ParentQuestionChoiceField(
        queryset=Question.objects.none(),
        required=False,
        label="Show only if",
        widget=forms.Select(attrs={"style": "width: 20em"}),
    )
    condition_operator = forms.ChoiceField(
        choices=OPERATOR_LABELS,
        required=False,
        initial=QuestionCondition.OP_IN,
        label="",
        widget=forms.Select(attrs={"style": "width: 10em"}),
    )
    condition_value = forms.CharField(
        required=False, label="", widget=forms.TextInput(attrs={"style": "width: 8em"})
    )

    class Media:
        css = {"all": ("survey/css/admin_condition.css",)}
        js = ("survey/js/admin_scale.js", "survey/js/admin_question_type.js")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            condition = QuestionCondition.objects.filter(question=self.instance).first()
            if condition is not None:
                self.fields["condition_question"].initial = condition.depends_on_id
                self.fields["condition_operator"].initial = condition.operator
                if condition.operator == QuestionCondition.OP_IN:
                    self.fields["condition_value"].initial = condition.choices
                elif condition.number is not None:
                    number = condition.number
                    self.fields["condition_value"].initial = int(number) if number == int(number) else number

    def _clean_condition(self, depends_on):
        """Validate the condition row and return QuestionCondition kwargs,
        adding form errors and returning None on problems."""
        operator = self.cleaned_data.get("condition_operator")
        value = (self.cleaned_data.get("condition_value") or "").strip()
        if not operator:
            self.add_error("condition_operator", "Select an operator.")
            return None
        if not value:
            self.add_error("condition_value", "Give a value to compare the answer against.")
            return None
        if self.instance.pk and depends_on.pk == self.instance.pk:
            self.add_error("condition_question", "A question cannot depend on itself.")
            return None
        order = self.cleaned_data.get("order")
        if order is not None and (
            depends_on.order > order
            or (depends_on.order == order and self.instance.pk and depends_on.pk > self.instance.pk)
        ):
            self.add_error("condition_question", "The parent question must come before this question.")
            return None

        kwargs = {"depends_on": depends_on, "operator": operator, "choices": "", "number": None}
        if operator == QuestionCondition.OP_IN:
            if depends_on.type not in (Question.RADIO, Question.SELECT, Question.SELECT_MULTIPLE):
                self.add_error("condition_question", "'is one of choices' needs a choice-type parent question.")
                return None
            labels = [label.strip() for label in value.split(",") if label.strip()]
            parent_choices = depends_on.get_clean_choices()
            for label in labels:
                if label not in parent_choices:
                    self.add_error("condition_value", f'"{label}" is not a choice of the parent question.')
                    return None
            kwargs["choices"] = ", ".join(labels)
        else:
            if depends_on.type not in (Question.INTEGER, Question.FLOAT):
                self.add_error("condition_question", "Numeric operators need an integer or float parent question.")
                return None
            try:
                kwargs["number"] = float(value)
            except ValueError:
                self.add_error("condition_value", f'"{value}" is not a number.')
                return None
        return kwargs

    def clean(self):
        cleaned_data = super().clean()
        self._parsed_condition = None
        depends_on = cleaned_data.get("condition_question")
        if depends_on is not None:
            self._parsed_condition = self._clean_condition(depends_on)
        if cleaned_data.get("other_option") and cleaned_data.get("type") not in (Question.RADIO, Question.SELECT):
            self.add_error("other_option", 'The "other" option is only supported on radio and dropdown questions.')
        if cleaned_data.get("will_not_answer_option") and cleaned_data.get("type") != Question.INTEGER_SCALE:
            self.add_error(
                "will_not_answer_option", 'The "will not answer" option is only supported on integer scale questions.'
            )
        return cleaned_data

    def save_extensions(self):
        """Sync the flattened condition fields to the one-to-one row. Must run
        after the question instance has been saved (called from save_formset)."""
        if self._parsed_condition is not None:
            QuestionCondition.objects.update_or_create(question=self.instance, defaults=self._parsed_condition)
        elif self.cleaned_data.get("condition_question") is None:
            QuestionCondition.objects.filter(question=self.instance).delete()


class QuestionInline(admin.StackedInline):
    model = Question
    form = QuestionInlineForm
    ordering = ("order", "category")
    extra = 1
    fields = (
        "text",
        "order",
        "required",
        "category",
        "type",
        "choices",
        ("scale_preset", "scale_min", "scale_max"),
        ("condition_question", "condition_operator", "condition_value"),
        "other_option",
        ("will_not_answer_option", "will_not_answer_label"),
    )

    def get_formset(self, request, survey_obj, *args, **kwargs):
        formset = super().get_formset(request, survey_obj, *args, **kwargs)
        if survey_obj:
            formset.form.base_fields["category"].queryset = survey_obj.categories.all()
            formset.form.base_fields["condition_question"].queryset = survey_obj.questions.order_by("order", "id")
        return formset


class CategoryInline(admin.TabularInline):
    model = Category
    extra = 0


class SurveyAdmin(admin.ModelAdmin):
    list_display = ("name", "is_published", "need_logged_user", "template")
    list_filter = ("is_published", "need_logged_user")
    inlines = [CategoryInline, QuestionInline]
    actions = [make_published, Survey2Csv.export_as_csv, Survey2Tex.export_as_tex]

    def save_formset(self, request, form, formset, change):
        super().save_formset(request, form, formset, change)
        if formset.model is Question:
            for inline_form in formset.forms:
                if (
                    inline_form.instance.pk
                    and inline_form.cleaned_data
                    and not inline_form.cleaned_data.get("DELETE")
                ):
                    inline_form.save_extensions()
            # Make a new or renumbered question take its chosen slot: unchanged
            # questions at that number and above move up by one.
            shift_colliding_questions(form.instance, pinned_question_ids(formset))


class AnswerBaseInline(admin.StackedInline):
    fields = ("question", "body")
    readonly_fields = ("question",)
    extra = 0
    model = Answer


class ResponseAdmin(admin.ModelAdmin):
    list_display = ("interview_uuid", "survey", "created", "user")
    list_filter = ("survey", "created")
    date_hierarchy = "created"
    inlines = [AnswerBaseInline]
    # specifies the order as well as which fields to act on
    readonly_fields = ("survey", "created", "updated", "interview_uuid", "user")


class CssSnippetForm(forms.ModelForm):
    class Meta:
        model = CssSnippet
        fields = "__all__"
        widgets = {
            "css": AceWidget(mode="css", theme="monokai", width="100%", height="300px"),
        }


class CssSnippetAdmin(admin.ModelAdmin):
    form = CssSnippetForm
    list_display = ("name",)


# admin.site.register(Question, QuestionInline)
# admin.site.register(Category, CategoryInline)
admin.site.register(Survey, SurveyAdmin)
admin.site.register(Response, ResponseAdmin)
admin.site.register(CssSnippet, CssSnippetAdmin)
