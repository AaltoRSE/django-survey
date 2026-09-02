import datetime
import logging
import uuid

from django import forms
from django.conf import settings
from django.forms import models
from django.urls import reverse
from django.utils.text import slugify

from survey.conditions import evaluate
from survey.models import Answer, Category, Question, QuestionCondition, Response, Survey
from survey.signals import survey_completed
from survey.widgets import ImageSelectWidget, NativeDateTimeInput, NativeTimeInput

LOGGER = logging.getLogger(__name__)


def question_css_classes(qtype, pk, suffix=""):
    """Build the three-tier (generic, type-specific, per-question) CSS class
    strings used by question.html to style a question's label, answers
    container ("row"), and individual options.

    :param str qtype: the raw question type (e.g. "radio") or a pseudo-type
        for companion fields (e.g. "wna", "other").
    :param int pk: the parent question's pk.
    :param str suffix: an optional segment inserted into the pk-specific
        classes for companion fields, e.g. "wna" -> "question-<pk>-wna-row".
    :rtype: dict with "label_class", "row_class", "option_class", "tr_class",
        "required_class", "errors_class" keys.
    """
    pk_segment = f"{pk}-{suffix}" if suffix else f"{pk}"
    return {
        "label_class": f"survey-question-label {qtype}-question-label question-{pk_segment}-label",
        "row_class": f"survey-question-row {qtype}-question-row question-{pk_segment}-row",
        "option_class": f"survey-question-option {qtype}-question-option question-{pk_segment}-option",
        "tr_class": f"survey-question {qtype}-question question-{pk_segment}",
        "required_class": f"survey-question-required {qtype}-question-required question-{pk_segment}-required",
        "errors_class": f"survey-question-errors {qtype}-question-errors question-{pk_segment}-errors",
    }


class ResponseForm(models.ModelForm):
    OTHER_SENTINEL = "__other__"
    WILL_NOT_ANSWER_SENTINEL = "__will-not-answer__"

    FIELDS = {
        Question.TEXT: forms.CharField,
        Question.SHORT_TEXT: forms.CharField,
        Question.SELECT_MULTIPLE: forms.MultipleChoiceField,
        Question.INTEGER: forms.IntegerField,
        Question.FLOAT: forms.FloatField,
        Question.DATE: forms.DateField,
        Question.LIKERT_5: forms.ChoiceField,
        Question.INTEGER_SCALE: forms.ChoiceField,
        Question.TIME: forms.TimeField,
        Question.DATETIME: forms.DateTimeField,
    }

    WIDGETS = {
        Question.TEXT: forms.Textarea,
        Question.SHORT_TEXT: forms.TextInput,
        Question.RADIO: forms.RadioSelect,
        Question.SELECT: forms.Select,
        Question.SELECT_IMAGE: ImageSelectWidget,
        Question.SELECT_MULTIPLE: forms.CheckboxSelectMultiple,
        Question.LIKERT_5: forms.RadioSelect,
        Question.INTEGER_SCALE: forms.RadioSelect,
        Question.TIME: NativeTimeInput,
        Question.DATETIME: NativeDateTimeInput,
    }

    class Meta:
        model = Response
        fields = ()

    def __init__(self, *args, session_data=None, **kwargs):
        """Expects a survey object to be passed in initially"""
        self.survey = kwargs.pop("survey")
        self.user = kwargs.pop("user")
        try:
            self.step = int(kwargs.pop("step"))
        except KeyError:
            self.step = None

        # Answers from earlier steps of a multi-step survey, keyed by
        # "question_<pk>". Needed to evaluate conditions whose parent
        # question is not part of the current step's fields.
        self.session_data = session_data or {}
        self._visibility_cache = {}
        self.hidden_question_ids = set()

        self._conditions = {
            condition.question_id: condition
            for condition in QuestionCondition.objects.filter(question__survey=self.survey).select_related(
                "depends_on"
            )
        }

        all_questions = list(self.survey.questions.all())
        self._questions_by_id = {question.pk: question for question in all_questions}

        self._other_initial = {}
        self._other_questions = {
            question.pk: question
            for question in all_questions
            if question.other_option and question.type in (Question.RADIO, Question.SELECT)
        }
        self._wna_initial = set()
        self._wna_questions = {
            question.pk: question
            for question in all_questions
            if question.will_not_answer_option and question.type == Question.INTEGER_SCALE
        }
        # When the form is rebuilt from session data (multi-step finalize in
        # SurveyDetail.treat_valid_form), the stored answer for an "other"-enabled
        # question is the raw free text, which would fail ChoiceField validation.
        # Map it back to the sentinel plus companion field before binding.
        if args and isinstance(args[0], dict) and not hasattr(args[0], "getlist"):
            args = (self._restore_wna_sentinels(self._restore_other_sentinels(args[0])),) + args[1:]
        elif isinstance(kwargs.get("data"), dict) and not hasattr(kwargs["data"], "getlist"):
            kwargs["data"] = self._restore_wna_sentinels(self._restore_other_sentinels(kwargs["data"]))

        super().__init__(*args, **kwargs)
        self.uuid = uuid.uuid4().hex

        self.categories = self.survey.non_empty_categories()
        self.qs_with_no_cat = self.survey.questions.filter(category__isnull=True).order_by("order", "id")

        if self.survey.display_method == Survey.BY_CATEGORY:
            self.steps_count = len(self.categories) + (1 if self.qs_with_no_cat else 0)
        else:
            self.steps_count = len(self.survey.questions.all())
        # will contain prefetched data to avoid multiple db calls
        self.response = False
        self.answers = False

        self.add_questions(kwargs.get("data"))

        self._get_preexisting_response()

        if not self.survey.editable_answers and self.response is not None:
            for name in self.fields.keys():
                self.fields[name].widget.attrs["disabled"] = True

    def _restore_other_sentinels(self, data):
        """Return a copy of a plain data dict with raw "other" text replaced by
        the sentinel choice and a companion text entry, so choice validation
        passes and clean() re-merges the text."""
        data = dict(data)
        for question in self._other_questions.values():
            name = f"question_{question.pk}"
            value = data.get(name)
            if not isinstance(value, str) or value in ("", self.OTHER_SENTINEL):
                continue
            clean_slugs = {slug for slug, _label in question.get_choices()}
            if value not in clean_slugs:
                data[name] = self.OTHER_SENTINEL
                data[f"{name}_other"] = value
        return data

    def _restore_wna_sentinels(self, data):
        """Return a copy of a plain data dict where a stored "will not answer"
        sentinel is replaced by the checkbox companion field, so choice
        validation on the main field passes."""
        data = dict(data)
        for question in self._wna_questions.values():
            name = f"question_{question.pk}"
            if data.get(name) == self.WILL_NOT_ANSWER_SENTINEL:
                data.pop(name, None)
                data[f"{name}_wna"] = True
        return data

    def _raw_value(self, question):
        """Return the raw submitted/stored value for a question, or None."""
        name = f"question_{question.pk}"
        if self.data:
            if question.type == Question.SELECT_MULTIPLE:
                if hasattr(self.data, "getlist"):
                    values = self.data.getlist(name)
                else:
                    # Plain dict (form rebuilt from session data).
                    values = self.data.get(name)
                if values:
                    return values
            else:
                value = self.data.get(name)
                if value not in (None, ""):
                    return value
        if name in self.session_data:
            return self.session_data[name]
        return None

    def is_visible(self, question):
        """Return whether a question should be shown, cascading through its condition chain."""
        if question.pk in self._visibility_cache:
            return self._visibility_cache[question.pk]
        condition = self._conditions.get(question.pk)
        if condition is None:
            visible = True
        else:
            parent = self._questions_by_id.get(condition.depends_on_id) or condition.depends_on
            if not self.is_visible(parent):
                visible = False
            else:
                visible = evaluate(condition, self._raw_value(parent))
        self._visibility_cache[question.pk] = visible
        return visible

    def add_questions(self, data):
        # add a field for each survey question, corresponding to the question
        # type as appropriate.

        if self.survey.display_method == Survey.BY_CATEGORY and self.step is not None:
            if self.step == len(self.categories):
                qs_for_step = self.survey.questions.filter(category__isnull=True).order_by("order", "id")
            else:
                qs_for_step = self.survey.questions.filter(category=self.categories[self.step])

            for question in qs_for_step:
                self.add_question(question, data)
        else:
            for i, question in enumerate(self.survey.questions.all()):
                not_to_keep = i != self.step and self.step is not None
                if self.survey.display_method == Survey.BY_QUESTION and not_to_keep:
                    continue
                self.add_question(question, data)

    def current_categories(self):
        if self.survey.display_method == Survey.BY_CATEGORY:
            if self.step is not None and self.step < len(self.categories):
                return [self.categories[self.step]]
            return [Category(name="No category", description="No cat desc")]
        else:
            extras = []
            if self.qs_with_no_cat:
                extras = [Category(name="No category", description="No cat desc")]

            return self.categories + extras

    def _get_preexisting_response(self):
        """Recover a pre-existing response in database.

        The user must be logged. Will store the response retrieved in an attribute
        to avoid multiple db calls.

        :rtype: Response or None"""
        if self.response:
            return self.response

        if not self.user.is_authenticated:
            self.response = None
        else:
            try:
                self.response = Response.objects.prefetch_related("user", "survey").get(
                    user=self.user, survey=self.survey
                )
            except Response.DoesNotExist:
                LOGGER.debug("No saved response for '%s' for user %s", self.survey, self.user)
                self.response = None
        return self.response

    def _get_preexisting_answers(self):
        """Recover pre-existing answers in database.

        The user must be logged. A Response containing the Answer must exists.
        Will create an attribute containing the answers retrieved to avoid multiple
        db calls.

        :rtype: dict of Answer or None"""
        if self.answers:
            return self.answers

        response = self._get_preexisting_response()
        if response is None:
            self.answers = None
        try:
            answers = Answer.objects.filter(response=response).prefetch_related("question")
            self.answers = {answer.question.id: answer for answer in answers.all()}
        except Answer.DoesNotExist:
            self.answers = None

        return self.answers

    def _get_preexisting_answer(self, question):
        """Recover a pre-existing answer in database.

        The user must be logged. A Response containing the Answer must exists.

        :param Question question: The question we want to recover in the
        response.
        :rtype: Answer or None"""
        answers = self._get_preexisting_answers()
        return answers.get(question.id, None)

    def get_question_initial(self, question, data):
        """Get the initial value that we should use in the Form

        :param Question question: The question
        :param dict data: Value from a POST request.
        :rtype: String or None"""
        initial = None
        answer = self._get_preexisting_answer(question)
        if answer:
            # Initialize the field with values from the database if any
            if question.type == Question.SELECT_MULTIPLE:
                initial = []
                if answer.body == "[]":
                    pass
                elif "[" in answer.body and "]" in answer.body:
                    initial = []
                    unformated_choices = answer.body[1:-1].strip()
                    for unformated_choice in unformated_choices.split(settings.CHOICES_SEPARATOR):
                        choice = unformated_choice.split("'")[1]
                        initial.append(slugify(choice))
                else:
                    # Only one element
                    initial.append(slugify(answer.body))
            else:
                initial = answer.body
        if data:
            # Initialize the field field from a POST request, if any.
            # Replace values from the database
            initial = data.get(f"question_{question.pk}")
        if question.type in (Question.TIME, Question.DATETIME) and not data and isinstance(initial, str) and initial:
            try:
                if question.type == Question.TIME:
                    initial = datetime.time.fromisoformat(initial)
                else:
                    initial = datetime.datetime.fromisoformat(initial)
            except ValueError:
                pass
        if question.pk in self._other_questions and initial not in (None, "", self.OTHER_SENTINEL):
            clean_slugs = {slug for slug, _label in question.get_choices()}
            if initial not in clean_slugs:
                # The stored body is free "other" text, not one of the choice slugs.
                self._other_initial[question.pk] = initial
                initial = self.OTHER_SENTINEL
        if question.pk in self._wna_questions and initial == self.WILL_NOT_ANSWER_SENTINEL:
            self._wna_initial.add(question.pk)
            initial = None
        return initial

    def get_question_widget(self, question):
        """Return the widget we should use for a question.

        :param Question question: The question
        :rtype: django.forms.widget or None"""
        try:
            return self.WIDGETS[question.type]
        except KeyError:
            return None

    @staticmethod
    def get_question_choices(question):
        """Return the choices we should use for a question.

        :param Question question: The question
        :rtype: List of String or None"""
        qchoices = None
        if question.type not in [
            Question.TEXT,
            Question.SHORT_TEXT,
            Question.INTEGER,
            Question.FLOAT,
            Question.DATE,
            Question.TIME,
            Question.DATETIME,
        ]:
            qchoices = question.get_choices()
            # add an empty option at the top so that the user has to explicitly
            # select one of the options
            if question.type in [Question.SELECT, Question.SELECT_IMAGE]:
                qchoices = tuple([("", "-------------")]) + qchoices
            if question.other_option and qchoices and question.type in (Question.RADIO, Question.SELECT):
                qchoices = tuple(qchoices) + ((ResponseForm.OTHER_SENTINEL, question.other_label),)
        return qchoices

    def get_question_field(self, question, **kwargs):
        """Return the field we should use in our form.

        :param Question question: The question
        :param **kwargs: A dict of parameter properly initialized in
            add_question.
        :rtype: django.forms.fields"""
        # logging.debug("Args passed to field %s", kwargs)
        try:
            return self.FIELDS[question.type](**kwargs)
        except KeyError:
            return forms.ChoiceField(**kwargs)

    def add_question(self, question, data):
        """Add a question to the form.

        :param Question question: The question to add.
        :param dict data: The pre-existing values from a post request."""
        kwargs = {"label": question.text, "required": question.required}
        if question.pk in self._wna_questions:
            # The checkbox companion field can substitute for an answer; clean()
            # re-enforces requiredness once it knows whether the box is checked.
            kwargs["required"] = False
        initial = self.get_question_initial(question, data)
        if initial:
            kwargs["initial"] = initial
        choices = self.get_question_choices(question)
        if choices:
            kwargs["choices"] = choices
        widget = self.get_question_widget(question)
        if widget:
            kwargs["widget"] = widget
        field = self.get_question_field(question, **kwargs)
        field.widget.attrs["category"] = question.category.name if question.category else ""

        if question.type == Question.DATE:
            field.widget.attrs["class"] = "date"
        field.widget.attrs["question_type"] = question.type
        css_classes = question_css_classes(question.type, question.pk)
        field.label_class = css_classes["label_class"]
        field.row_class = css_classes["row_class"]
        field.option_class = css_classes["option_class"]
        field.tr_class = css_classes["tr_class"]
        field.required_class = css_classes["required_class"]
        field.errors_class = css_classes["errors_class"]
        field.as_choice_list = question.type in (
            Question.RADIO,
            Question.SELECT_MULTIPLE,
            Question.LIKERT_5,
            Question.INTEGER_SCALE,
        )
        field.horizontal = question.type in (Question.LIKERT_5, Question.INTEGER_SCALE)
        # logging.debug("Field for %s : %s", question, field.__dict__)
        self.fields[f"question_{question.pk}"] = field

        if question.pk in self._other_questions:
            other_field = forms.CharField(required=False, label="")
            other_field.widget.attrs["data-other-for"] = f"question_{question.pk}"
            other_field.widget.attrs["category"] = question.category.name if question.category else ""
            other_css_classes = question_css_classes("other", question.pk, suffix="other")
            other_field.label_class = other_css_classes["label_class"]
            other_field.row_class = other_css_classes["row_class"]
            other_field.option_class = other_css_classes["option_class"]
            other_field.required_class = other_css_classes["required_class"]
            other_field.errors_class = other_css_classes["errors_class"]
            other_initial = self._other_initial.get(question.pk)
            if other_initial is not None:
                other_field.initial = other_initial
            self.fields[f"question_{question.pk}_other"] = other_field

        if question.pk in self._wna_questions:
            wna_field = forms.BooleanField(required=False, label=question.will_not_answer_label)
            wna_field.widget.attrs["data-wna-for"] = f"question_{question.pk}"
            wna_field.widget.attrs["category"] = question.category.name if question.category else ""
            wna_css_classes = question_css_classes("wna", question.pk, suffix="wna")
            wna_field.label_class = wna_css_classes["label_class"]
            wna_field.row_class = wna_css_classes["row_class"]
            wna_field.option_class = wna_css_classes["option_class"]
            wna_field.required_class = wna_css_classes["required_class"]
            wna_field.errors_class = wna_css_classes["errors_class"]
            if question.pk in self._wna_initial:
                wna_field.initial = True
            self.fields[f"question_{question.pk}_wna"] = wna_field

        # The template renders the required-asterisk from this, not from
        # field.required, which is forced off for conditional questions below.
        field.show_required = question.required

        condition = self._conditions.get(question.pk)
        if condition is not None:
            # Requiredness is re-enforced in clean() once we know the question is visible.
            field.required = False
            field.widget.attrs["data-depends-on"] = f"question_{condition.depends_on_id}"
            field.widget.attrs["data-operator"] = condition.operator
            if condition.operator == QuestionCondition.OP_IN:
                slugs = ",".join(slugify(label) for label in condition._clean_choice_labels())
                field.widget.attrs["data-cond-choices"] = slugs
            elif condition.number is not None:
                field.widget.attrs["data-cond-number"] = condition.number

    def _step_question_ids(self):
        """Return the pks of the questions that are fields on this form instance."""
        ids = []
        for name in self.fields:
            if name.startswith("question_") and not name.endswith(("_other", "_wna")):
                try:
                    ids.append(int(name.split("_")[1]))
                except (IndexError, ValueError):
                    continue
        return ids

    def clean(self):
        cleaned_data = super().clean()
        for field_name, field in self.fields.items():
            if isinstance(field, (forms.TimeField, forms.DateTimeField)):
                value = cleaned_data.get(field_name)
                if hasattr(value, "isoformat"):
                    cleaned_data[field_name] = value.isoformat()
        for question_id, question in self._other_questions.items():
            field_name = f"question_{question_id}"
            other_name = f"{field_name}_other"
            if field_name not in self.fields:
                continue
            if cleaned_data.get(field_name) == self.OTHER_SENTINEL:
                other_text = (cleaned_data.get(other_name) or "").strip()
                if not other_text:
                    if question.required:
                        self.add_error(field_name, "This field is required.")
                    else:
                        # Don't store the literal sentinel as the answer.
                        cleaned_data[field_name] = ""
                else:
                    cleaned_data[field_name] = other_text
            # Always pop the companion field: save() creates an Answer for every
            # "question_*" cleaned_data key (parsing the pk as split("_")[1]), so
            # leaving it in would create a duplicate Answer for the same question.
            cleaned_data.pop(other_name, None)

        for question_id, question in self._wna_questions.items():
            field_name = f"question_{question_id}"
            wna_name = f"{field_name}_wna"
            if field_name not in self.fields:
                continue
            if cleaned_data.get(wna_name):
                # Checkbox wins over any radio value submitted alongside it.
                cleaned_data[field_name] = self.WILL_NOT_ANSWER_SENTINEL
            elif question.required and not cleaned_data.get(field_name):
                self.add_error(field_name, "This field is required.")
            # Always pop the companion field: save() creates an Answer for every
            # "question_*" cleaned_data key (parsing the pk as split("_")[1]), so
            # leaving it in would create a duplicate Answer for the same question.
            cleaned_data.pop(wna_name, None)

        self.hidden_question_ids = set()
        for question_id in self._step_question_ids():
            question = self._questions_by_id.get(question_id)
            if question is None:
                continue
            field_name = f"question_{question_id}"
            # The "other"/"will not answer" companion fields created above.
            other_name = f"{field_name}_other"
            wna_name = f"{field_name}_wna"

            if not self.is_visible(question):
                self.hidden_question_ids.add(question_id)
                self.errors.pop(field_name, None)
                self.errors.pop(other_name, None)
                self.errors.pop(wna_name, None)
                cleaned_data.pop(field_name, None)
                cleaned_data.pop(other_name, None)
                cleaned_data.pop(wna_name, None)
                continue

            if (
                question.pk in self._conditions
                and question.required
                and not cleaned_data.get(field_name)
                and field_name not in self.errors
            ):
                self.add_error(field_name, "This field is required.")
        return cleaned_data

    def survey_hidden_question_ids(self):
        """Return the ids of every survey question currently hidden, not just the
        ones that happen to be fields on this step's form. Used by the view to
        purge stale session answers when a step-back changes a parent answer."""
        return {question.pk for question in self._questions_by_id.values() if not self.is_visible(question)}

    def _questions_for_step(self, step):
        """Mirror add_questions' step -> question mapping."""
        if self.survey.display_method == Survey.BY_CATEGORY:
            if step == len(self.categories):
                return list(self.qs_with_no_cat)
            if 0 <= step < len(self.categories):
                return list(self.survey.questions.filter(category=self.categories[step]))
            return []
        all_questions = list(self.survey.questions.all())
        if 0 <= step < len(all_questions):
            return [all_questions[step]]
        return []

    def step_has_visible_questions(self, step):
        return any(self.is_visible(question) for question in self._questions_for_step(step))

    def has_next_step(self):
        if self.survey.is_all_in_one_page():
            return False
        step = self.step + 1
        while step < self.steps_count:
            if self.step_has_visible_questions(step):
                return True
            step += 1
        return False

    def next_step_url(self):
        if not self.has_next_step():
            return None
        step = self.step + 1
        while step < self.steps_count:
            if self.step_has_visible_questions(step):
                return reverse("survey-detail-step", kwargs={"id": self.survey.id, "step": step})
            step += 1
        return None

    def current_step_url(self):
        return reverse("survey-detail-step", kwargs={"id": self.survey.id, "step": self.step})

    def save(self, commit=True):
        """Save the response object"""
        # Recover an existing response from the database if any
        #  There is only one response by logged user.
        response = self._get_preexisting_response()
        if not self.survey.editable_answers and response is not None:
            return None
        if response is None:
            response = super().save(commit=False)
        response.survey = self.survey
        response.interview_uuid = self.uuid
        if self.user.is_authenticated:
            response.user = self.user
        response.save()
        # response "raw" data as dict (for signal)
        data = {"survey_id": response.survey.id, "interview_uuid": response.interview_uuid, "responses": []}
        for question_id in self.hidden_question_ids:
            self.cleaned_data.pop(f"question_{question_id}", None)
        # create an answer object for each question and associate it with this
        # response.
        for field_name, field_value in list(self.cleaned_data.items()):
            if field_name.startswith("question_"):
                # warning: this way of extracting the id is very fragile and
                # entirely dependent on the way the question_id is encoded in
                # the field name in the __init__ method of this form class.
                q_id = int(field_name.split("_")[1])
                question = Question.objects.get(pk=q_id)
                answer = self._get_preexisting_answer(question)
                if answer is None:
                    answer = Answer(question=question)
                if question.type == Question.SELECT_IMAGE:
                    value, img_src = field_value.split(":", 1)
                    # TODO Handling of SELECT IMAGE
                    LOGGER.debug("Question.SELECT_IMAGE not implemented, please use : %s and %s", value, img_src)
                answer.body = field_value
                data["responses"].append((answer.question.id, answer.body))
                LOGGER.debug("Creating answer for question %d of type %s : %s", q_id, answer.question.type, field_value)
                answer.response = response
                answer.save()
        survey_completed.send(sender=Response, instance=response, data=data)
        if self.hidden_question_ids:
            # Re-edits may have left stale answers for questions that are now hidden.
            Answer.objects.filter(response=response, question_id__in=self.hidden_question_ids).delete()
        return response
