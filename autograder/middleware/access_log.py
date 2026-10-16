import logging

logger = logging.getLogger("autograder.access")


class AccessLogMiddleware:
    """Logs each request in the same style as daphne's access log, plus the username."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        user = getattr(request, "user", None)
        username = user.username if user is not None and user.is_authenticated else "-"

        logger.info(
            '%s %s "%s %s" %s',
            request.META.get("REMOTE_ADDR", "-"),
            username,
            request.method,
            request.get_full_path(),
            response.status_code,
        )
        return response
