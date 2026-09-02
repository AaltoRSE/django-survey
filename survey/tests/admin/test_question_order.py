from django.test import TestCase

from survey.admin_impl.question_order import resolve_order_collisions, shift_colliding_questions
from survey.models.question import Question
from survey.models.survey import Survey


class TestResolveOrderCollisions(TestCase):
    def setUp(self):
        self.survey = Survey.objects.create(name="Survey", description="d", need_logged_user=False)

    def make(self, order, text="Q"):
        return Question.objects.create(survey=self.survey, text=text, order=order, required=True, type=Question.TEXT)

    def orders(self):
        return [(q.text, q.order) for q in self.survey.questions.order_by("order", "id")]

    def test_no_collision_changes_nothing(self):
        qs = [self.make(1), self.make(2), self.make(4)]
        self.assertEqual(resolve_order_collisions(qs, set()), [])
        self.assertEqual([q.order for q in qs], [1, 2, 4])

    def test_inserted_question_shifts_unchanged_ones_up(self):
        a, b, c = self.make(1, "a"), self.make(2, "b"), self.make(3, "c")
        new = self.make(2, "new")
        moved = resolve_order_collisions([a, b, c, new], {new.pk})
        self.assertEqual({q.text for q in moved}, {"b", "c"})
        self.assertEqual([(q.text, q.order) for q in (a, new, b, c)], [("a", 1), ("new", 2), ("b", 3), ("c", 4)])

    def test_shift_stops_at_a_gap(self):
        a, b, far = self.make(1, "a"), self.make(2, "b"), self.make(5, "far")
        new = self.make(2, "new")
        resolve_order_collisions([a, b, far, new], {new.pk})
        self.assertEqual([(q.text, q.order) for q in (a, new, b, far)], [("a", 1), ("new", 2), ("b", 3), ("far", 5)])

    def test_renumbered_question_wins_over_unchanged_one(self):
        a, b, c = self.make(1, "a"), self.make(2, "b"), self.make(3, "c")
        c.order = 1  # moved to the front
        resolve_order_collisions([a, b, c], {c.pk})
        self.assertEqual([(q.text, q.order) for q in (c, a, b)], [("c", 1), ("a", 2), ("b", 3)])

    def test_two_pinned_questions_with_same_number_keep_id_order(self):
        a = self.make(1, "a")
        n1, n2 = self.make(1, "n1"), self.make(1, "n2")
        resolve_order_collisions([a, n1, n2], {n1.pk, n2.pk})
        self.assertEqual([(q.text, q.order) for q in (n1, n2, a)], [("n1", 1), ("n2", 2), ("a", 3)])

    def test_two_new_questions_in_consecutive_slots_both_keep_them(self):
        a, b, c = self.make(1, "a"), self.make(2, "b"), self.make(3, "c")
        n2, n3 = self.make(2, "n2"), self.make(3, "n3")
        resolve_order_collisions([a, b, c, n2, n3], {n2.pk, n3.pk})
        self.assertEqual(
            [(q.text, q.order) for q in (a, n2, n3, b, c)], [("a", 1), ("n2", 2), ("n3", 3), ("b", 4), ("c", 5)]
        )

    def test_shift_colliding_questions_persists_moves(self):
        self.make(1, "a"), self.make(2, "b")
        new = self.make(2, "new")
        moved = shift_colliding_questions(self.survey, {new.pk})
        self.assertEqual([q.text for q in moved], ["b"])
        self.assertEqual(self.orders(), [("a", 1), ("new", 2), ("b", 3)])
