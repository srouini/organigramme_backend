from django.urls import path
from rest_framework.routers import DefaultRouter
from rest_framework import routers

from .views import (
    GradeViewSet,
    StructureViewSet,
    PositionViewSet,
    OrganigramEdgeViewSet,
    DashboardViewSet,
    MissionViewSet,
    TaskViewSet,
    CompetenceViewSet,
    DiagramPositionViewSet,
    AutoOrganizeDiagramView,
    StructureTypeViewSet
)

router = DefaultRouter()
router.register(r"grades", GradeViewSet, basename="grade")
router.register(r"structures", StructureViewSet, basename="structure")
router.register(r"structure-types", StructureTypeViewSet, basename="structure-type")
router.register(r"positions", PositionViewSet, basename="position")
router.register(r"edges", OrganigramEdgeViewSet, basename="edge")
router.register(r"dashboard", DashboardViewSet, basename="dashboard")
router.register(r"missions", MissionViewSet, basename="mission")
router.register(r"tasks", TaskViewSet, basename="task")
router.register(r"competences", CompetenceViewSet, basename="competence")
router.register(r"diagram-positions", DiagramPositionViewSet, basename="diagram-position")

urlpatterns = [
    path("structures/<int:structure_id>/auto-organize/", AutoOrganizeDiagramView.as_view(), name="auto-organize"),
    *router.urls
]
