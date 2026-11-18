"""Give the public guest and reception screens one private browser workspace."""
from datetime import timedelta
from secrets import token_hex

from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import (
    Http404, HttpResponse, HttpResponseBadRequest, HttpResponseNotAllowed,
    HttpResponseNotFound, HttpResponseRedirect,
)
from django.utils import timezone
from django.views.decorators.http import require_POST

DEMO_OPERATOR = "public-demo-reception"
WORKSPACE_SESSION_KEY = "public_demo_workspace"


class PublicDemoUpstreamMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.get_host().partition(":")[0].removesuffix(".")
        if host != settings.PUBLIC_DEMO_UPSTREAM_IP:
            return self.get_response(request)
        if request.path_info != "/":
            return HttpResponseNotFound()
        if request.method not in ("GET", "HEAD"):
            return HttpResponseNotAllowed(["GET", "HEAD"])
        return HttpResponse(
            "Kinshore Bay backend is reachable.\n",
            content_type="text/plain; charset=utf-8",
            headers={"Cache-Control": "no-store"},
        )


class PublicDemoMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path_info
        desk = path.startswith("/reception/")
        page = path in ("/site/index.html", "/site/miniapp.html", "/reception/")
        if not (page or desk or path.startswith("/api/guest/")):
            return self.get_response(request)
        if path == "/reception/login/":
            raise Http404

        workspace = request.session.get(WORKSPACE_SESSION_KEY)
        if not workspace:
            if not page or request.method != "GET":
                return HttpResponseBadRequest("Open the demo first and enable cookies.")
            workspace = f"{timezone.localdate():%Y%m%d}-{token_hex(24)}"
            request.session[WORKSPACE_SESSION_KEY] = workspace
            request.session.set_expiry(timezone.now() + timedelta(days=1))
        request.workspace = workspace

        if desk:
            actor = get_user_model().objects.filter(username=DEMO_OPERATOR, is_active=True,
                                                    is_staff=False, is_superuser=False).first()
            if actor is None or actor.has_usable_password():
                raise Http404
            request.user = actor
        response = self.get_response(request)
        if page:
            response["Cache-Control"] = "private, no-store"
        return response


@require_POST
def end_workspace(request):
    request.session.flush()
    return HttpResponseRedirect("/site/index.html")
