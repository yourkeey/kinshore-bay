from django.conf import settings
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import path

from . import desk
from .public_demo import end_workspace

def logout(request):
    if getattr(settings, "PUBLIC_DEMO", False):
        return end_workspace(request)
    return LogoutView.as_view()(request)


urlpatterns = [
    path("", desk.today, name="desk-today"),
    path("login/", LoginView.as_view(template_name="desk/login.html"), name="desk-login"),
    path("logout/", logout, name="desk-logout"),
    path("calendar/", desk.calendar, name="desk-calendar"),
    path("walks/", desk.walks, name="desk-walks"),
    path("grills/", desk.grills, name="desk-grills"),
    path("requests/<str:reference>/", desk.detail, name="desk-detail"),
]
