from django.test import TestCase
from django.urls import reverse
from .models import ProblemOfTheWeek


class POTWViewTests(TestCase):
    def setUp(self):
        ProblemOfTheWeek.objects.create(level=ProblemOfTheWeek.BEGINNER, title="Beginner Test", link="https://example.com/beg")
        ProblemOfTheWeek.objects.create(level=ProblemOfTheWeek.INTERMEDIATE, title="Intermediate Test", link="https://example.com/int")
        ProblemOfTheWeek.objects.create(level=ProblemOfTheWeek.ADVANCED, title="Advanced Test", link="https://example.com/adv")

    def test_potw_renders(self):
        resp = self.client.get(reverse('index:potw'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Problem of the Week: Beginner')
        self.assertContains(resp, 'Problem of the Week: Intermediate')
        self.assertContains(resp, 'Problem of the Week: Advanced')
        self.assertContains(resp, 'Click to see')
