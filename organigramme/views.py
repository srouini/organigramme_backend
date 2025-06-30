from django.db import transaction
from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_flex_fields.views import FlexFieldsMixin
from .filters import OrganigramFilter, OrganigramEdgeFilter, GradeFilter, PositionFilter, TaskFilter
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from .models import Grade, Organigram, Position, OrganigramEdge, Task
from .serializers import (
    GradeSerializer,
    OrganigramSerializer,
    PositionSerializer,
    OrganigramEdgeSerializer,
    TaskSerializer,
)


class GradeViewSet(FlexFieldsMixin, viewsets.ModelViewSet):
    """CRUD for Grade model."""

    queryset = Grade.objects.all().order_by("level")
    serializer_class = GradeSerializer
    permission_classes = [IsAuthenticated]
    filterset_class = GradeFilter
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ['name','level']

class OrganigramViewSet(FlexFieldsMixin, viewsets.ModelViewSet):
    """CRUD for Organigram model + tree auto‑organize."""

    queryset = Organigram.objects.all()
    serializer_class = OrganigramSerializer
    permission_classes = [IsAuthenticated]
    filterset_class = OrganigramFilter
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ['name','state']


    @action(detail=True, methods=["post"], url_path="auto-organize")
    def auto_organize(self, request, pk=None):
        """Auto‑organize positions into a tree layout."""
        organigram = self.get_object()
        positions = Position.objects.filter(organigram=organigram)
        edges = OrganigramEdge.objects.filter(organigram=organigram)

        if not positions.exists():
            return Response(
                {"message": "No positions to organize"}, status=status.HTTP_200_OK
            )

        # Discover roots & build adjacency
        position_ids = set(positions.values_list("id", flat=True))
        target_ids = set(edges.values_list("target_id", flat=True))
        root_ids = position_ids - target_ids

        children_map = {}
        for edge in edges:
            children_map.setdefault(edge.source_id, []).append(edge.target_id)

        # BFS per level
        level_groups = {}
        queue = [(root_id, 0) for root_id in root_ids]
        visited = set()
        while queue:
            node_id, level = queue.pop(0)
            if node_id in visited:
                continue
            visited.add(node_id)
            level_groups.setdefault(level, []).append(node_id)
            for child in children_map.get(node_id, []):
                queue.append((child, level + 1))

        spacing_x, spacing_y = 350, 200
        updates = []
        with transaction.atomic():
            for level, node_ids in level_groups.items():
                y = level * spacing_y + 100
                total_width = (len(node_ids) - 1) * spacing_x
                start_x = 600 - total_width / 2
                for idx, node_id in enumerate(node_ids):
                    x = start_x + idx * spacing_x
                    Position.objects.filter(id=node_id).update(
                        position_x=x, position_y=y
                    )
                    updates.append({"id": node_id, "position_x": x, "position_y": y})

        return Response(
            {"message": "Chart organized as tree", "updates": updates},
            status=status.HTTP_200_OK,
        )


class TaskViewSet(FlexFieldsMixin, viewsets.ModelViewSet):
    """CRUD for Position model + bulk update."""
    queryset = Task.objects.all()
    serializer_class = TaskSerializer
    permission_classes = [IsAuthenticated]
    filterset_class = TaskFilter
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ['description']



    
class PositionViewSet(FlexFieldsMixin, viewsets.ModelViewSet):
    """CRUD for Position model + bulk update."""
    queryset = Position.objects.all()
    serializer_class = PositionSerializer
    permit_list_expands = ['organigram', 'grade']
    permission_classes = [IsAuthenticated]
    filterset_class = PositionFilter
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ['title']


    # def get_queryset(self):
    #     organigram_id = self.request.query_params.get("organigram_id")
    #     qs = Position.objects.all()
    #     if organigram_id:
    #         qs = qs.filter(organigram_id=organigram_id)
    #     return qs.order_by("-created_at")

    @action(detail=False, methods=["post"], url_path="bulk-update")
    def bulk_update(self, request):
        updates = request.data.get("updates", [])
        if not updates:
            return Response(
                {"detail": "No updates provided."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        instances = [
            Position(
                id=u["id"], position_x=u["x"], position_y=u["y"]
            )
            for u in updates
        ]
        Position.objects.bulk_update(instances, ["position_x", "position_y"])
        return Response({"message": f"Updated {len(instances)} positions"})


class OrganigramEdgeViewSet(FlexFieldsMixin, viewsets.ModelViewSet):
    """CRUD for OrganigramEdge model."""

    serializer_class = OrganigramEdgeSerializer
    permission_classes = [IsAuthenticated]
    filterset_class = OrganigramEdgeFilter
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ['title','level']

    def get_queryset(self):
        organigram_id = self.request.query_params.get("organigram_id")
        qs = OrganigramEdge.objects.all()
        if organigram_id:
            qs = qs.filter(organigram_id=organigram_id)
        return qs


class DashboardViewSet(viewsets.ViewSet):
    """Read‑only stats dashboard."""

    permission_classes = [IsAuthenticated]

    def list(self, request):
        stats = {
            "total_organigrams": Organigram.objects.count(),
            "total_positions": Position.objects.count(),
            "total_grades": Grade.objects.count(),
            "organigrams_by_state": {
                "Draft": Organigram.objects.filter(state="Draft").count(),
                "Final": Organigram.objects.filter(state="Final").count(),
                "Archived": Organigram.objects.filter(state="Archived").count(),
            },
            "recent_organigrams": [
                {
                    "id": str(org.id),
                    "name": org.name,
                    "state": org.state,
                    "created_at": org.created_at.isoformat(),
                }
                for org in Organigram.objects.order_by("-created_at")[:5]
            ],
        }
        return Response(stats)