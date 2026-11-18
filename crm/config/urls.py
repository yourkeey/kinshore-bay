from django.shortcuts import redirect
from django.urls import include, path
from reception import guest
from reception.api import create_demo_submission

urlpatterns = [
    path("reception/", include("reception.desk_urls")),
    path("", lambda request: redirect("/site/index.html")),
    path("site/<path:name>", guest.site_file),
    path("content/en.json", guest.catalog),
    path("api/guest/quotes/", guest.quotes),
    path("api/guest/stays/", guest.my_stays),
    path("api/guest/stays/<str:reference>/walks/<int:walk_id>/", guest.walk_booking),
    path("api/internal/demo-requests/", create_demo_submission, name="create-demo-submission"),
]
