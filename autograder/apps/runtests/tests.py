from django.test import TestCase

from .templatetags.verdicts import verdict_class


class VerdictClassTests(TestCase):
    def test_accepted(self):
        self.assertEqual(verdict_class("Accepted"), "v-ac")
        self.assertEqual(verdict_class("AC"), "v-ac")

    def test_suffixed_verdicts_match_by_prefix(self):
        """handlers.py appends 'on test N' -- equality checks would miss these."""
        self.assertEqual(verdict_class("Wrong Answer on test 3"), "v-wa")
        self.assertEqual(verdict_class("Time Limit Exceeded on test 12"), "v-tle")
        self.assertEqual(verdict_class("Memory Limit Exceeded on test 4"), "v-tle")

    def test_errors(self):
        for verdict in (
            "Runtime Error",
            "Compilation Error",
            "Grader Error",
            "Checker Error: boom",
            "Internal Server Error",
            "ER",
        ):
            self.assertEqual(verdict_class(verdict), "v-err", verdict)

    def test_interactive_verdicts(self):
        self.assertEqual(verdict_class("Query Limit Exceeded on test 1"), "v-tle")
        self.assertEqual(verdict_class("Protocol Violation on test 1"), "v-err")

    def test_pending_and_skipped(self):
        self.assertEqual(verdict_class("Waiting in Queue"), "v-pending")
        self.assertEqual(verdict_class("Compiling"), "v-pending")
        self.assertEqual(verdict_class("Running on test 2"), "v-pending")
        self.assertEqual(verdict_class("Skipped"), "v-skipped")

    def test_empty(self):
        self.assertEqual(verdict_class(""), "v-pending")
        self.assertEqual(verdict_class(None), "v-pending")

    def test_unknown_returns_empty(self):
        self.assertEqual(verdict_class("Something Else Entirely"), "")

