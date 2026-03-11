from django_distill import distill_path

from . import views

app_name = "legistar"
urlpatterns = [
    distill_path(
        "calendar/<slug:style>/",
        views.calendar,
        name="calendar",
        distill_func=views.distill_calendars,
        distill_file="calendar/{style}/index.html",
    ),
    distill_path(
        "meeting/<int:meeting_id>/<slug:style>/",
        views.meeting,
        name="meeting",
        distill_func=views.distill_meetings,
        distill_file="meeting/{meeting_id}/{style}/index.html",
    ),
    distill_path(
        "legislation/<int:meeting_id>/<int:legislation_id>/<slug:style>/",
        views.legislation,
        name="legislation",
        distill_func=views.distill_legislations,
        distill_file="legislation/{meeting_id}/{legislation_id}/{style}/index.html",
    ),
    distill_path(
        "document/<int:meeting_id>/<int:legislation_id>/<int:document_pk>/<slug:style>/",
        views.document,
        name="document",
        distill_func=views.distill_documents,
        distill_file="document/{meeting_id}/{legislation_id}/{document_pk}/{style}/index.html",
    ),
    distill_path(
        "previous-legislation/<slug:style>/",
        views.previous_legislation,
        name="previous_legislation",
        distill_func=views.distill_previous_legislation,
        distill_file="previous-legislation/{style}/index.html",
    ),
    distill_path(
        "previous-legislation/<slug:style>/page/<int:page>/",
        views.previous_legislation_page,
        name="previous_legislation_page",
        distill_func=views.distill_previous_legislation_pages,
        distill_file="previous-legislation/{style}/page/{page}/index.html",
    ),
    distill_path("", views.index, name="index", distill_file="index.html"),
    distill_path(
        "evaluations/",
        views.evaluations,
        name="evaluations",
        distill_func=views.distill_evaluations,
        distill_file="evaluations/index.html",
    ),
]
