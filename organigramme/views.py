from django.db import transaction
from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_flex_fields.views import FlexFieldsMixin
from .filters import *
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from .models import *
from .serializers import *
from django.contrib.contenttypes.models import ContentType

from src.utils import render_to_pdf_rest
from django.http import HttpResponse

class StructureTypeViewSet(FlexFieldsMixin, viewsets.ModelViewSet):
    """CRUD for Grade model."""

    queryset = StructureType.objects.all().order_by("id")
    serializer_class = StructureTypeSerializer
    permission_classes = [IsAuthenticated]
    filterset_class = StructureTypeFilter
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ['name']


class GradeViewSet(FlexFieldsMixin, viewsets.ModelViewSet):
    """CRUD for Grade model."""

    queryset = Grade.objects.all().order_by("id")
    serializer_class = GradeSerializer
    permission_classes = [IsAuthenticated]
    filterset_class = GradeFilter
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ['name']

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
                        
                  
                    
                    # Set default values for optional fields
                    grade_data.setdefault('color', '#3B82F6')
                    grade_data.setdefault('category', '')
                    grade_data.setdefault('description', '')
                    
                    # Create the grade
                    Grade.objects.create(
                        name=str(grade_data['name']).strip(),
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

class StructureViewSet(FlexFieldsMixin, viewsets.ModelViewSet):
    """CRUD for Structure model + tree auto‑organize."""

    queryset = Structure.objects.all()
    serializer_class = StructureSerializer
    permit_list_expands = ['manager', 'manager.grade', 'positions', 'edges', 'children', 'parent','type']
    permission_classes = [IsAuthenticated]
    filterset_class = StructureFilter
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ['name']

    @action(detail=True, methods=['get'])
    def tree(self, request, pk=None):
        """Retrieve the structure as a tree."""
        instance = self.get_object()
        serializer = self.get_serializer(instance, expand=['children.positions.grade', 'children.manager', 'positions.grade', 'manager'])
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="auto-organize")
    def auto_organize(self, request, pk=None):
        """Auto‑organize positions into a tree layout with children under parents."""
        structure = self.get_object()
        positions = Position.objects.filter(structure=structure)
        edges = OrganigramEdge.objects.filter(structure=structure).select_related('source', 'target')

        if not positions.exists():
            return Response(
                {"message": "No positions to organize"}, status=status.HTTP_200_OK
            )
        
        # Build parent-child mappings
        children_map = {}
        parent_map = {}
        position_map = {p.id: p for p in positions}
        
        for edge in edges:
            if edge.source_id in position_map and edge.target_id in position_map:
                children_map.setdefault(edge.source_id, []).append(edge.target_id)
                parent_map[edge.target_id] = edge.source_id

        # Find root nodes (nodes without parents)
        root_ids = [p.id for p in positions if p.id not in parent_map]
        
        if not root_ids:
            return Response(
                {"message": "No root positions found (circular references may exist)"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Constants for spacing
        NODE_WIDTH = 200  # Approximate width of a node in pixels
        HORIZONTAL_PADDING = 100  # Minimum space between nodes
        VERTICAL_SPACING = 250  # Vertical space between levels
        
        # Calculate positions using a tree-based approach
        node_positions = {}
        
        def calculate_subtree_width(node_id):
            """Calculate the width required for a subtree in units."""
            if not children_map.get(node_id):
                return 1  # Base unit for leaf nodes
            
            # Sum up all children's widths plus padding between them
            children = children_map[node_id]
            if not children:
                return 1
                
            total = sum(calculate_subtree_width(child_id) for child_id in children)
            # Add padding between children (N-1 gaps for N children)
            return max(1, total + (len(children) - 1) * 0.5)

        def position_node(node_id, x_offset, level):
            """Recursively position nodes and return the next x_offset."""
            node = position_map[node_id]
            
            if node_id in children_map and children_map[node_id]:
                # This is a parent node with children
                children = children_map[node_id]
                
                # Calculate positions of all children first
                child_positions = []
                current_x = x_offset
                
                for child_id in children:
                    child_width = calculate_subtree_width(child_id)
                    current_x = position_node(child_id, current_x, level + 1)
                    child_positions.append((child_id, current_x - child_width / 2))
                    current_x += 0.5  # Add padding between children
                
                # Position this node centered over its children
                if child_positions:
                    first_child_x = child_positions[0][1]
                    last_child_x = child_positions[-1][1] + calculate_subtree_width(children[-1])
                    node_x = (first_child_x + last_child_x) / 2
                else:
                    node_x = x_offset
                
                node_positions[node_id] = (node_x, level * VERTICAL_SPACING + 100)
                return current_x
            else:
                # This is a leaf node
                node_positions[node_id] = (x_offset, level * VERTICAL_SPACING + 100)
                return x_offset + 1  # Leaf nodes take 1 unit width

        # Position all root nodes
        x_offset = 0
        for root_id in root_ids:
            x_offset = position_node(root_id, x_offset, 0)

        # Apply the calculated positions
        updates = []
        with transaction.atomic():
            for node_id, (x, y) in node_positions.items():
                # Scale x position using the node width and padding
                x_pos = x * (NODE_WIDTH + HORIZONTAL_PADDING) + 100
                Position.objects.filter(id=node_id).update(
                    position_x=x_pos,
                    position_y=y
                )
                updates.append({
                    "id": node_id,
                    "position_x": x_pos,
                    "position_y": y
                })

        return Response(
            {
                "message": "Chart organized as hierarchical tree with children under parents",
                "updates": updates
            },
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
    permit_list_expands = ['structure', 'grade', 'parent']
    permission_classes = [IsAuthenticated]
    filterset_class = PositionFilter
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ['title']

    def create(self, request, *args, **kwargs):
        mutable_data = request.data.copy()
        parent_id = mutable_data.pop('parent', None)

        serializer = self.get_serializer(data=mutable_data)
        serializer.is_valid(raise_exception=True)
        
        with transaction.atomic():
            self.perform_create(serializer)
            new_position = serializer.instance

            if parent_id:
                try:
                    parent_position = Position.objects.get(id=parent_id)
                    OrganigramEdge.objects.create(
                        source=parent_position,
                        target=new_position,
                        structure=new_position.structure
                    )
                except Position.DoesNotExist:
                    return Response({"parent": "Invalid parent ID provided."}, status=status.HTTP_400_BAD_REQUEST)
                except Exception as e:
                    return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    
    @action(detail=True, methods=['get'], url_path='generate_pdf')
    def generate_pdf(self, request, pk=None):
        try:

            position = Position.objects.get(id=pk) 
            missions = Mission.objects.filter(position=position)
            competences = Competence.objects.filter(position=position)

            edge = OrganigramEdge.objects.filter(
                target=position,
                structure=position.structure
            ).select_related('source').first()
            
            context = { 
                "position" : position,
                "missions" : missions, 
                "competences" : competences,
                "parent" : edge.source if edge else None
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
            edge = OrganigramEdge.objects.filter(
                target=position,
                structure=position.structure
            ).select_related('source').first()
            
            if not edge:
                return Response(
                    {"detail": "No parent position found"}, 
                    status=status.HTTP_404_NOT_FOUND
                )
            
            serializer = PositionSerializer(edge.source, context=self.context)
            return Response(serializer.data)
        except Position.DoesNotExist:
            return Response(
                {"detail": "Position not found"},
                status=status.HTTP_404_NOT_FOUND
            )

    @action(detail=True, methods=['post'], url_path='update-edge-source')
    def update_edge_source(self, request, pk=None):
        """
        Update the source of the edge related to this position.
        Expected payload: {"source_id": <new_source_position_id>}
        """
        try:
            position = self.get_object()
            new_source_id = request.data.get('source_id')
            
            if not new_source_id:
                return Response(
                    {"error": "source_id is required in the request payload"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Get the edge where this position is the target
            edge = OrganigramEdge.objects.filter(
                target=position,
                organigram=position.organigram
            ).first()
            
            if not edge:
                return Response(
                    {"error": "No edge found for this position"},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Get the new source position
            try:
                new_source = Position.objects.get(id=new_source_id, organigram=position.organigram)
            except Position.DoesNotExist:
                return Response(
                    {"error": "Source position not found or not in the same organigram"},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Update the edge source
            edge.source = new_source
            edge.save()
            
            return Response({
                "message": "Edge source updated successfully",
                "data": OrganigramEdgeSerializer(edge).data
            })
            
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
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

class DiagramPositionViewSet(FlexFieldsMixin, viewsets.ModelViewSet):
    """
    CRUD for DiagramPosition model.
    This handles the positions of structures and positions within different diagrams.
    """
    serializer_class = DiagramPositionSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['main_structure', 'content_type', 'object_id']
    
    def get_queryset(self):
        queryset = DiagramPosition.objects.all()
        
        # Filter by content type and object ID if provided
        content_type = self.request.query_params.get('content_type')
        object_id = self.request.query_params.get('object_id')
        main_structure = self.request.query_params.get('main_structure')
        
        if content_type and object_id:
            try:
                content_type = ContentType.objects.get(model=content_type.lower())
                queryset = queryset.filter(
                    content_type=content_type,
                    object_id=object_id
                )
            except ContentType.DoesNotExist:
                return DiagramPosition.objects.none()
                
        if main_structure:
            queryset = queryset.filter(main_structure_id=main_structure)
            
        return queryset
    
    def create(self, request, *args, **kwargs):
        # Handle creation of a new diagram position
        data = request.data.copy()
        
        # Get the content type and object ID from the request
        content_type_str = data.get('content_type')
        object_id = data.get('object_id')
        main_structure_id = data.get('main_structure')
        
        if not all([content_type_str, object_id is not None, main_structure_id]):
            return Response(
                {"error": "content_type, object_id, and main_structure are required and cannot be null"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Get the content type model
            content_type = ContentType.objects.get(model=content_type_str.lower())
            model_class = content_type.model_class()
            
            # Convert object_id to integer
            try:
                object_id = int(object_id)
            except (ValueError, TypeError):
                return Response(
                    {"error": "object_id must be a valid integer"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Get the object instance to verify it exists
            try:
                obj = model_class.objects.get(id=object_id)
            except model_class.DoesNotExist:
                return Response(
                    {"error": f"{content_type.model} with id {object_id} does not exist"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Get the main structure
            try:
                main_structure = Structure.objects.get(id=main_structure_id, is_main=True)
            except Structure.DoesNotExist:
                return Response(
                    {"error": f"Main structure with id {main_structure_id} not found or not marked as main"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Check if a position already exists for this object and main structure
            existing_position = DiagramPosition.objects.filter(
                content_type=content_type,
                object_id=object_id,
                main_structure=main_structure
            ).first()
            
            # Prepare data for the serializer
            position_data = {
                'content_type': content_type.model,
                'object_id': object_id,
                'main_structure': main_structure.id,
                'position_x': data.get('position_x', 0),
                'position_y': data.get('position_y', 0)
            }
            
            if existing_position:
                # Update the existing position
                serializer = self.get_serializer(existing_position, data=position_data, partial=True)
            else:
                # Create a new position
                serializer = self.get_serializer(data=position_data)
            
            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer)
            headers = self.get_success_headers(serializer.data)
            return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
            
        except ContentType.DoesNotExist:
            return Response(
                {"error": f"Invalid content_type: {content_type_str}"},
                status=status.HTTP_400_BAD_REQUEST
            )
        except model_class.DoesNotExist:
            return Response(
                {"error": f"{content_type_str} with id {object_id} does not exist"},
                status=status.HTTP_404_NOT_FOUND
            )
        except Structure.DoesNotExist:
            return Response(
                {"error": f"Main structure with id {main_structure_id} does not exist or is not a main structure"},
                status=status.HTTP_404_NOT_FOUND
            )


class OrganigramEdgeViewSet(FlexFieldsMixin, viewsets.ModelViewSet):
    """CRUD for OrganigramEdge model."""

    serializer_class = OrganigramEdgeSerializer
    permission_classes = [IsAuthenticated]
    filterset_class = OrganigramEdgeFilter
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ['title','source','target']

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
            "recent_organigrams": [
                {
                    "id": str(org.id),
                    "name": org.name,
                    "created_at": org.created_at.isoformat(),
                }
                for org in Organigram.objects.order_by("-created_at")[:5]
            ],
        }
        return Response(stats)

from collections import defaultdict


def auto_organize_structure(main_structure_id, x_spacing=400, y_spacing=400):
    main_structure = Structure.objects.prefetch_related('children__children').get(id=main_structure_id)

    # Use a dictionary to store positions before saving to avoid race conditions
    positions = {}

    def set_positions_dfs(node, level=0):
        # Post-order traversal: process children first
        children = list(node.children.all())
        if not children:
            positions[node.id] = {'x': 0, 'y': level * y_spacing, 'level': level}
            return

        for child in children:
            set_positions_dfs(child, level + 1)

        # Position parent over its children
        first_child_pos = positions[children[0].id]['x']
        last_child_pos = positions[children[-1].id]['x']
        parent_x = (first_child_pos + last_child_pos) / 2

        # Initial parent position
        positions[node.id] = {'x': parent_x, 'y': level * y_spacing, 'level': level}

        # Collision detection and resolution
        for i in range(len(children) - 1):
            # Find the rightmost x of the left subtree and leftmost x of the right subtree
            left_subtree_nodes = get_all_descendants(children[i])
            right_subtree_nodes = get_all_descendants(children[i+1])

            right_contour_of_left_subtree = max(positions[n.id]['x'] for n in left_subtree_nodes)
            left_contour_of_right_subtree = min(positions[n.id]['x'] for n in right_subtree_nodes)

            overlap = (right_contour_of_left_subtree + x_spacing) - left_contour_of_right_subtree
            if overlap > 0:
                # Shift the entire right subtree to resolve the overlap
                shift_amount = overlap
                shift_subtree(children[i+1], shift_amount)
        
        # After shifting children, re-center the parent based on the new child positions
        if children:
            final_first_child_pos = positions[children[0].id]['x']
            final_last_child_pos = positions[children[-1].id]['x']
            positions[node.id]['x'] = (final_first_child_pos + final_last_child_pos) / 2

    def get_all_descendants(node):
        # Helper to get a node and all its children, recursively.
        descendants = [node]
        for child in node.children.all():
            descendants.extend(get_all_descendants(child))
        return descendants

    def shift_subtree(node, shift_amount):
        # Recursively shift a subtree by affecting all its nodes.
        nodes_to_shift = get_all_descendants(node)
        for n in nodes_to_shift:
            if n.id in positions:
                positions[n.id]['x'] += shift_amount

    # Start the layout process from the main structure
    set_positions_dfs(main_structure)

    # Find the minimum x value to shift the whole diagram to be positive
    min_x = min(pos['x'] for pos in positions.values()) if positions else 0
    x_offset = -min_x if min_x < 0 else 0

    # Save positions to the database
    for node_id, pos in positions.items():
        node_instance = Structure.objects.get(id=node_id)
        content_type = ContentType.objects.get_for_model(node_instance)
        
        final_x = pos['x'] + x_offset
        final_y = pos['y']

        position, created = DiagramPosition.objects.get_or_create(
            content_type=content_type,
            object_id=node_id,
            main_structure=main_structure,
            defaults={'position_x': final_x, 'position_y': final_y}
        )
        if not created:
            position.position_x = final_x
            position.position_y = final_y
            position.save()


from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status


class AutoOrganizeDiagramView(APIView):
    def post(self, request, structure_id):
        auto_organize_structure(structure_id)
        return Response({"status": "Diagram auto-organized"}, status=status.HTTP_200_OK)