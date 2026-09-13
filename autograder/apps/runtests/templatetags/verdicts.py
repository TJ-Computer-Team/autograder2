from django import template

register = template.Library()

# Verdicts are not a fixed vocabulary: handlers.py builds several of them with a
# test number appended (e.g. "Wrong Answer on test 3"), and the interactive path
# appends the same suffix to whatever interactive_checker returned. So match on
# prefix rather than equality. Order matters only in that the first hit wins.
_PREFIXES = (
    ("Accepted", "v-ac"),
    ("AC", "v-ac"),
    ("Wrong Answer", "v-wa"),
    ("Time Limit Exceeded", "v-tle"),
    ("Memory Limit Exceeded", "v-tle"),
    ("Query Limit Exceeded", "v-tle"),
    ("Runtime Error", "v-err"),
    ("Compilation Error", "v-err"),
    ("Protocol Violation", "v-err"),
    ("Grader Error", "v-err"),
    ("Checker Error", "v-err"),
    ("Internal Server Error", "v-err"),
    ("ER", "v-err"),
    ("Waiting in Queue", "v-pending"),
    ("Compiling", "v-pending"),
    ("Running", "v-pending"),
    ("Rerun", "v-pending"),
    ("Skipped", "v-skipped"),
)


@register.filter
def verdict_class(value):
    """CSS class for a submission verdict, for color-coding status tables."""
    if not value:
        return "v-pending"

    text = str(value).strip()
    for prefix, css_class in _PREFIXES:
        if text.startswith(prefix):
            return css_class
    return ""
