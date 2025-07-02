from django.db import transaction
from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_flex_fields.views import FlexFieldsMixin
from .filters import OrganigramFilter, OrganigramEdgeFilter, GradeFilter, PositionFilter, TaskFilter, MissionFilter, CompetenceFilter
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from .models import Grade, Organigram, Position, OrganigramEdge, Task, Mission, Competence
from .serializers import (
    GradeSerializer,
    OrganigramSerializer,
    PositionSerializer,
    OrganigramEdgeSerializer,
    TaskSerializer,
    MissionSerializer,
    CompetenceSerializer
)
from src.utils import render_to_pdf_rest
from django.http import HttpResponse

class GradeViewSet(FlexFieldsMixin, viewsets.ModelViewSet):
    """CRUD for Grade model."""

    queryset = Grade.objects.all().order_by("level")
    serializer_class = GradeSerializer
    permission_classes = [IsAuthenticated]
    filterset_class = GradeFilter
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ['name','level']

    @action(detail=False, methods=['post'])
    def bulk_create(self, request):
        """Bulk create grades from a list of grade data."""
        if not isinstance(request.data, list):
            return Response(
                {"error": "Expected a list of grade data"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not request.data:
            return Response(
                {"error": "No grade data provided"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        created_count = 0
        errors = []
        
        with transaction.atomic():
            for index, grade_data in enumerate(request.data, start=1):
                try:
                    # Validate required fields
                    if not isinstance(grade_data, dict):
                        raise ValueError("Each grade must be an object")
                        
                    if 'name' not in grade_data or not grade_data['name']:
                        raise ValueError("Name is required")
                        
                    if 'level' not in grade_data or grade_data['level'] is None:
                        raise ValueError("Level is required")
                    
                    try:
                        grade_data['level'] = int(grade_data['level'])
                    except (ValueError, TypeError):
                        raise ValueError("Level must be a number")
                    
                    # Set default values for optional fields
                    grade_data.setdefault('color', '#3B82F6')
                    grade_data.setdefault('category', '')
                    grade_data.setdefault('description', '')
                    
                    # Create the grade
                    Grade.objects.create(
                        name=str(grade_data['name']).strip(),
                        level=grade_data['level'],
                        color=str(grade_data['color']).strip(),
                        category=str(grade_data['category']).strip(),
                        description=str(grade_data['description']).strip()
                    )
                    created_count += 1
                    
                except Exception as e:
                    errors.append(f"Row {index}: {str(e)}")
        
        # Prepare response
        response_data = {
            "message": f"Successfully created {created_count} of {len(request.data)} grades",
            "created_count": created_count,
            "total_rows": len(request.data)
        }
        
        if errors:
            response_data["errors"] = errors
            return Response(response_data, status=status.HTTP_207_MULTI_STATUS)
            
        return Response(response_data, status=status.HTTP_201_CREATED)

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

        spacing_x, spacing_y = 400, 200
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

class MissionViewSet(FlexFieldsMixin, viewsets.ModelViewSet):
    """CRUD for Mission model + bulk operations."""
    queryset = Mission.objects.all()
    serializer_class = MissionSerializer
    permission_classes = [IsAuthenticated]
    filterset_class = MissionFilter
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ['description']

    @action(detail=False, methods=['post'])
    def bulk_create(self, request):
        """Bulk create missions for a position."""
        position_id = request.data.get('position')
        missions_data = request.data.get('missions', [])
        
        if not position_id or not isinstance(missions_data, list):
            return Response(
                {"error": "Position ID and missions list are required"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            position = Position.objects.get(id=position_id)
        except Position.DoesNotExist:
            return Response(
                {"error": "Position not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        created_missions = []
        for mission_desc in missions_data:
            if not isinstance(mission_desc, str) or not mission_desc.strip():
                continue
                
            mission = Mission.objects.create(
                description=mission_desc.strip(),
                position=position
            )
            created_missions.append(mission)
        
        serializer = self.get_serializer(created_missions, many=True)
        return Response(
            {"message": f"Successfully created {len(created_missions)} missions", "data": serializer.data},
            status=status.HTTP_201_CREATED
        )

class CompetenceViewSet(FlexFieldsMixin, viewsets.ModelViewSet):
    """CRUD for Competence model + bulk operations."""
    queryset = Competence.objects.all()
    serializer_class = CompetenceSerializer
    permission_classes = [IsAuthenticated]
    filterset_class = CompetenceFilter
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ['description']

    @action(detail=False, methods=['post'])
    def bulk_create(self, request):
        """Bulk create competences for a position."""
        position_id = request.data.get('position')
        competences_data = request.data.get('competences', [])
        
        if not position_id or not isinstance(competences_data, list):
            return Response(
                {"error": "Position ID and competences list are required"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            position = Position.objects.get(id=position_id)
        except Position.DoesNotExist:
            return Response(
                {"error": "Position not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        created_competences = []
        for competence_desc in competences_data:
            if not isinstance(competence_desc, str) or not competence_desc.strip():
                continue
                
            competence = Competence.objects.create(
                description=competence_desc.strip(),
                position=position
            )
            created_competences.append(competence)
        
        serializer = self.get_serializer(created_competences, many=True)
        return Response(
            {"message": f"Successfully created {len(created_competences)} competences", "data": serializer.data},
            status=status.HTTP_201_CREATED
        )

    
class PositionViewSet(FlexFieldsMixin, viewsets.ModelViewSet):
    """CRUD for Position model + bulk update."""
    queryset = Position.objects.all()
    serializer_class = PositionSerializer
    permit_list_expands = ['organigram', 'grade']
    permission_classes = [IsAuthenticated]
    filterset_class = PositionFilter
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ['title']

    @action(detail=True, methods=['get'], url_path='generate_pdf')
    def generate_pdf(self, request, pk=None):
        try:

            position = Position.objects.get(id=pk) 
            missions = Mission.objects.filter(position=position)
            competences = Competence.objects.filter(position=position)

            edge = OrganigramEdge.objects.filter(
                target=position,
                organigram=position.organigram
            ).select_related('source').first()
            
            context = { 
                "position" : position,
                "missions" : missions, 
                "competences" : competences,
                "parent" : edge.source
            }  

            pdf = render_to_pdf_rest('organigramme/fiche_de_poste.html', context)



            if pdf:
                # Create response with correct headers to allow download in frontend
                response = HttpResponse(pdf, content_type='application/pdf')
                filename = f"FICHE_DE_POSTE_{context['position'].title}.pdf"
                response['Content-Disposition'] = f'attachment; filename="{filename}"'
                return response
            return Response({"error": "Error generating PDF"}, status=500)
        except Position.DoesNotExist:
            return Response({"error": "Position not found"}, status=404)

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
        return Response(
            {"message": f"Successfully updated {len(instances)} positions"},
            status=status.HTTP_200_OK,
        )
        
    @action(detail=True, methods=['get'], url_path='parent')
    def get_parent_position(self, request, pk=None):
        """
        Get the parent position of the current position by finding the source of the edge
        where this position is the target.
        """
        try:
            position = self.get_object()
            # Find the edge where this position is the target
            edge = OrganigramEdge.objects.filter(
                target=position,
                organigram=position.organigram
            ).select_related('source').first()
            
            if not edge:
                return Response(
                    {"detail": "No parent position found"},
                    status=status.HTTP_404_NOT_FOUND
                )
                
            # Serialize the parent position
            serializer = self.get_serializer(edge.source)
            return Response(serializer.data)
            
        except Position.DoesNotExist:
            return Response(
                {"detail": "Position not found"},
                status=status.HTTP_404_NOT_FOUND
            )
            
    @action(detail=True, methods=['post'], url_path='clone')
    def clone_position(self, request, pk=None):
        """
        Create a clone of the position with all its related data.
        """
        try:
            with transaction.atomic():
                # Get the original position
                original_position = self.get_object()
                
                # Create a copy of the position
                position_copy = Position.objects.get(id=original_position.id)
                position_copy.pk = None
                position_copy.title = f"{original_position.title} (Copie)"
                position_copy.save()
                
                # Clone related missions
                for mission in Mission.objects.filter(position=original_position):
                    mission_copy = Mission.objects.get(id=mission.id)
                    mission_copy.pk = None
                    mission_copy.position = position_copy
                    mission_copy.save()
                
                # Clone related competences
                for competence in Competence.objects.filter(position=original_position):
                    competence_copy = Competence.objects.get(id=competence.id)
                    competence_copy.pk = None
                    competence_copy.position = position_copy
                    competence_copy.save()
                
                # Clone related tasks
                for task in Task.objects.filter(position=original_position):
                    task_copy = Task.objects.get(id=task.id)
                    task_copy.pk = None
                    task_copy.position = position_copy
                    task_copy.save()
                
                # Clone the edge relationship if it exists
                edge = OrganigramEdge.objects.filter(
                    target=original_position,
                    organigram=original_position.organigram
                ).first()
                
                if edge:
                    OrganigramEdge.objects.create(
                        source=edge.source,
                        target=position_copy,
                        organigram=edge.organigram
                    )
                
                # Return the cloned position
                serializer = self.get_serializer(position_copy)
                return Response(serializer.data, status=status.HTTP_201_CREATED)
                
        except Exception as e:
            return Response(
                {"detail": f"Error cloning position: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )

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