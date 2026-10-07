from django.urls import include, path, re_path
from maintenance import views

urlpatterns = [path("api/", include("maintenance.urls")), re_path(r"^(?P<path>.*)$", views.static_app)]
