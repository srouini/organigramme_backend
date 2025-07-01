from rest_framework.routers import DefaultRouter

from .views import (
    GradeViewSet,
    OrganigramViewSet,
    PositionViewSet,
    OrganigramEdgeViewSet,
    DashboardViewSet,
    MissionViewSet,
    TaskViewSet,
    CompetenceViewSet,
)

router = DefaultRouter()
router.register(r"grades", GradeViewSet, basename="grade")
router.register(r"organigrams", OrganigramViewSet, basename="organigram")
router.register(r"positions", PositionViewSet, basename="position")
router.register(r"edges", OrganigramEdgeViewSet, basename="edge")
router.register(r"dashboard", DashboardViewSet, basename="dashboard")
router.register(r"missions", MissionViewSet, basename="mission")
router.register(r"tasks", TaskViewSet, basename="task")
router.register(r"competences", CompetenceViewSet, basename="competence")

urlpatterns = router.urls
