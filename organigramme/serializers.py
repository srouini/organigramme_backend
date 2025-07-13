from rest_framework import serializers
from rest_flex_fields.serializers import FlexFieldsModelSerializer
from django.contrib.contenttypes.models import ContentType
from .models import Structure, Position, Grade, Task, Mission, Competence, OrganigramEdge, DiagramPosition

class ParentPositionSerializer(serializers.ModelSerializer):
    # This serializer is used to avoid recursion in PositionSerializer
    class Meta:
        model = Position
        fields = ('id', 'title', 'abbreviation')

class GradeSerializer(FlexFieldsModelSerializer):
    class Meta:
        model = Grade
        fields = '__all__'
        read_only_fields = ("created_at", "updated_at")

class TaskSerializer(FlexFieldsModelSerializer):
    class Meta:
        model = Task
        fields = '__all__'
        read_only_fields = ("created_at", "updated_at")
        expandable_fields = {
            "position": ("organigramme.serializers.PositionSerializer", {"many": False}),
        }

class MissionSerializer(FlexFieldsModelSerializer):
    class Meta:
        model = Mission
        fields = '__all__'
        read_only_fields = ("created_at", "updated_at")
        expandable_fields = {
            "position": ("organigramme.serializers.PositionSerializer", {"many": False}),
        }

class CompetenceSerializer(FlexFieldsModelSerializer):
    class Meta:
        model = Competence
        fields = '__all__'
        read_only_fields = ("created_at", "updated_at")
        expandable_fields = {
            "position": ("organigramme.serializers.PositionSerializer", {"many": False}),
        }

class DiagramPositionSerializer(FlexFieldsModelSerializer):
    content_type = serializers.SlugRelatedField(
        queryset=ContentType.objects.all(),
        slug_field='model',
        required=True
    )
    object_id = serializers.IntegerField(required=True)
    
    class Meta:
        model = DiagramPosition
        fields = ('id', 'content_type', 'object_id', 'main_structure', 'position_x', 'position_y', 'created_at', 'updated_at')
        read_only_fields = ("created_at", "updated_at")


class PositionSerializer(FlexFieldsModelSerializer):
    parent = serializers.SerializerMethodField(read_only=True)
    diagram_positions = serializers.SerializerMethodField(read_only=True)
    
    class Meta:
        model = Position
        fields = '__all__'
        read_only_fields = ("created_at", "updated_at", "parent", "diagram_positions")

        expandable_fields = {
            "structure": ("organigramme.serializers.StructureSerializer", {"many": False}),
            "grade": ("organigramme.serializers.GradeSerializer", {"many": False}),
            "parent": ("organigramme.serializers.ParentPositionSerializer", {"many": False}),
            "edges": ("organigramme.serializers.OrganigramEdgeSerializer", {"many": True}),
            "diagram_positions": ("organigramme.serializers.DiagramPositionSerializer", {"many": True}),
        }
    
    def get_parent(self, obj):
        """
        Get the parent position by finding the source of the edge
        where this position is the target.
        """
        from .models import OrganigramEdge
        position_content_type = ContentType.objects.get_for_model(Position)

        edge = OrganigramEdge.objects.filter(
            target_content_type=position_content_type,
            target_object_id=obj.id,
            structure=obj.structure
        ).first()
        
        if not edge or not isinstance(edge.source, Position):
            return None
            
        # Use ParentPositionSerializer to avoid recursion
        return ParentPositionSerializer(edge.source, context=self.context).data
        
    def get_diagram_positions(self, obj):
        """
        Get diagram-specific positions for this position.
        """
        content_type = ContentType.objects.get_for_model(obj)
        diagram_positions = DiagramPosition.objects.filter(
            content_type=content_type,
            object_id=obj.id
        )
        return DiagramPositionSerializer(diagram_positions, many=True, context=self.context).data

class GenericRelatedField(serializers.Field):
    """
    A custom field to use for the `source` and `target` generic relationships.
    """
    def to_representation(self, value):
        if isinstance(value, Structure):
            return {'type': 'structure', 'id': value.id, 'name': value.name}
        if isinstance(value, Position):
            return {'type': 'position', 'id': value.id, 'name': value.title}
        return None

    def to_internal_value(self, data):
        if not isinstance(data, dict) or 'type' not in data or 'id' not in data:
            raise serializers.ValidationError("Input must be a dictionary with 'type' and 'id' keys.")
        
        type_name = data.get('type')
        obj_id = data.get('id')

        if type_name == 'structure':
            model = Structure
        elif type_name == 'position':
            model = Position
        else:
            raise serializers.ValidationError(f"Unknown type '{type_name}'")
        
        try:
            return model.objects.get(id=obj_id)
        except model.DoesNotExist:
            raise serializers.ValidationError(f"{model.__name__} with id {obj_id} not found.")
        except (TypeError, ValueError):
            raise serializers.ValidationError("Invalid ID provided.")

class OrganigramEdgeSerializer(FlexFieldsModelSerializer):
    source = GenericRelatedField()
    target = GenericRelatedField()

    class Meta:
        model = OrganigramEdge
        fields = ('id', 'structure', 'source', 'target', 'edge_type', 'created_at')
        read_only_fields = ("created_at",)

    def validate(self, data):
        """Validate edge creation."""
        source = data.get('source')
        target = data.get('target')
        structure = data.get('structure')

        if not source or not target or not structure:
            raise serializers.ValidationError("Source, target, and structure are required.")

        if source == target:
            raise serializers.ValidationError("A node cannot be connected to itself.")

        source_content_type = ContentType.objects.get_for_model(source)
        target_content_type = ContentType.objects.get_for_model(target)
        
        queryset = OrganigramEdge.objects.filter(
            source_content_type=source_content_type,
            source_object_id=source.id,
            target_content_type=target_content_type,
            target_object_id=target.id,
            structure=structure
        )
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError("This edge already exists in the structure.")

        if isinstance(source, Position) and source.structure != structure:
            raise serializers.ValidationError(f"Source position '{source.title}' does not belong to the structure '{structure.name}'.")
        
        if isinstance(target, Position) and target.structure != structure:
            raise serializers.ValidationError(f"Target position '{target.title}' does not belong to the structure '{structure.name}'.")

        return data

# This serializer is used to avoid recursion in StructureSerializer
class StructureChildrenSerializer(serializers.ModelSerializer):
    class Meta:
        model = Structure
        fields = ('id', 'name')

class StructureSerializer(FlexFieldsModelSerializer):
    children = StructureChildrenSerializer(many=True, read_only=True)
    parent = serializers.PrimaryKeyRelatedField(queryset=Structure.objects.all(), allow_null=True, required=False)
    manager = serializers.SerializerMethodField(read_only=True)
    
    def get_manager(self, obj):
        if not obj.manager:
            return None
        # Use the PositionSerializer to serialize the manager with grade expanded
        from .serializers import PositionSerializer
        return PositionSerializer(
            obj.manager, 
            context=self.context,
            expand=['grade']
        ).data
    diagram_positions = serializers.SerializerMethodField(read_only=True)
    
    expandable_fields = {
        "positions": (PositionSerializer, {"many": True}),
        "edges": (OrganigramEdgeSerializer, {"many": True}),
        "children": ('organigramme.serializers.StructureSerializer', {"many": True}),
        "parent": ('organigramme.serializers.StructureSerializer', {"many": False}),
        "manager": ('organigramme.serializers.PositionSerializer', {"many": False, "expand": ["grade"]}),
        "diagram_positions": ("organigramme.serializers.DiagramPositionSerializer", {"many": True}),
    }

    class Meta:
        model = Structure
        fields = '__all__'
        read_only_fields = ("created_at", "updated_at", "diagram_positions")
        
    def get_diagram_positions(self, obj):
        """
        Get diagram-specific positions for this structure.
        """
        diagram_positions = obj.diagram_positions.all()
        return DiagramPositionSerializer(diagram_positions, many=True, context=self.context).data

    def validate_name(self, value):
        if Structure.objects.filter(name__iexact=value).exclude(id=self.instance.id if self.instance else None).exists():
            raise serializers.ValidationError("This name already exists.")
        return value