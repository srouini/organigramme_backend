from rest_framework.routers import DefaultRouter

from .views import (
    GradeViewSet,
    OrganigramViewSet,
    PositionViewSet,
    OrganigramEdgeViewSet,
    DashboardViewSet,
)

router = DefaultRouter()
router.register(r"grades", GradeViewSet, basename="grade")
router.register(r"organigrams", OrganigramViewSet, basename="organigram")
router.register(r"positions", PositionViewSet, basename="position")
router.register(r"edges", OrganigramEdgeViewSet, basename="edge")
router.register(r"dashboard", DashboardViewSet, basename="dashboard")

urlpatterns = router.urls
