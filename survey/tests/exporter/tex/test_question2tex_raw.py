from survey.exporter.tex.question2tex_raw import Question2TexRaw
from survey.tests.management.test_management import TestManagement


class TestQuestion2TexRaw(TestManagement):
    def test_raw_tex(self):
        """We can create a raw chart."""
        question = self.survey.questions.get(text="Aèbc?")
        expected = ["1é", "1", "1e"]
        container = Question2TexRaw(question).tex()
        for i in expected:
            self.assertIn(i, container)
