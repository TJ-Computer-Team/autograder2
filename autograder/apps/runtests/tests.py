from django.test import TestCase

from ...coderunner.runner import _is_oom
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


class OomDetectionTests(TestCase):
    """Memory Limit Exceeded detection in coderunner.runner."""

    def test_sigkill_is_oom(self):
        # nsjail's cgroup_mem_max leaves the kernel OOM killer to SIGKILL: 128 + 9
        self.assertTrue(_is_oom(137, ""))

    def test_runtime_oom_messages(self):
        for stderr in (
            "terminate called after throwing an instance of 'std::bad_alloc'",
            "java.lang.OutOfMemoryError: Java heap space",
            "MemoryError",
            "Cannot allocate memory",
        ):
            self.assertTrue(_is_oom(1, stderr), stderr)

    def test_ordinary_runtime_error_is_not_oom(self):
        self.assertFalse(_is_oom(1, "Segmentation fault"))
        self.assertFalse(_is_oom(1, "IndexError: list index out of range"))
        self.assertFalse(_is_oom(0, ""))
