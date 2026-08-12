import datetime
import logging
import uuid

from django import forms
from django.conf import settings
from django.forms import models
from django.urls import reverse
from django.utils.text import slugify

from survey.models import Answer, Category, Question, Response, Survey
from survey.signals import survey_completed
from survey.widgets import ImageSelectWidget, NativeDateTimeInput, NativeTimeInput

LOGGER = logging.getLogger(__name__)


class ResponseForm(models.ModelForm):
    OTHER_SENTINEL = "__other__"

    FIELDS = {
        Question.TEXT: forms.CharField,
        Question.SHORT_TEXT: forms.CharField,
        Question.SELECT_MULTIPLE: forms.MultipleChoiceField,
        Question.INTEGER: forms.IntegerField,
        Question.FLOAT: forms.FloatField,
        Question.DATE: forms.DateField,
        Question.LIKERT_5: forms.ChoiceField,
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
        Question.TIME: NativeTimeInput,
        Question.DATETIME: NativeDateTimeInput,
    }

    class Meta:
        model = Response
        fields = ()

    def __init__(self, *args, **kwargs):
        """Expects a survey object to be passed in initially"""
        self.survey = kwargs.pop("survey")
        self.user = kwargs.pop("user")
        try:
            self.step = int(kwargs.pop("step"))
        except KeyError:
            self.step = None

        self._other_initial = {}
        self._other_questions = {
            question.pk: question
            for question in self.survey.questions.all()
            if question.other_option and question.type in (Question.RADIO, Question.SELECT)
        }
        # When the form is rebuilt from session data (multi-step finalize in
        # SurveyDetail.treat_valid_form), the stored answer for an "other"-enabled
        # question is the raw free text, which would fail ChoiceField validation.
        # Map it back to the sentinel plus companion field before binding.
        if args and isinstance(args[0], dict) and not hasattr(args[0], "getlist"):
            args = (self._restore_other_sentinels(args[0]),) + args[1:]
        elif isinstance(kwargs.get("data"), dict) and not hasattr(kwargs["data"], "getlist"):
            kwargs["data"] = self._restore_other_sentinels(kwargs["data"])

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
        # logging.debug("Field for %s : %s", question, field.__dict__)
        self.fields[f"question_{question.pk}"] = field

        if question.pk in self._other_questions:
            other_field = forms.CharField(required=False, label="")
            other_field.widget.attrs["data-other-for"] = f"question_{question.pk}"
            other_field.widget.attrs["category"] = question.category.name if question.category else ""
            other_initial = self._other_initial.get(question.pk)
            if other_initial is not None:
                other_field.initial = other_initial
            self.fields[f"question_{question.pk}_other"] = other_field

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
        return cleaned_data

    def has_next_step(self):
        if not self.survey.is_all_in_one_page():
            if self.step < self.steps_count - 1:
                return True
        return False

    def next_step_url(self):
        if self.has_next_step():
            context = {"id": self.survey.id, "step": self.step + 1}
            return reverse("survey-detail-step", kwargs=context)

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
        return response
