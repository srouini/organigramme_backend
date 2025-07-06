from rest_framework import serializers
from rest_flex_fields import FlexFieldsModelSerializer
from .models import Grade, Organigram, Position, OrganigramEdge, Task, Mission, Competence

class ParentPositionSerializer(serializers.ModelSerializer):
    """Serializer for parent position to avoid recursion in PositionSerializer"""
    class Meta:
        model = Position
        fields = ('id', 'title', 'grade', 'position_x', 'position_y')
        read_only_fields = fields

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

class PositionSerializer(FlexFieldsModelSerializer):
    parent = serializers.SerializerMethodField(read_only=True)
    
    class Meta:
        model = Position
        fields = '__all__'
        read_only_fields = ("created_at", "updated_at", "parent")

        expandable_fields = {
            "organigram": ("organigramme.serializers.OrganigramSerializer", {"many": False}),
            "grade": ("organigramme.serializers.GradeSerializer", {"many": False}),
            "parent": ("organigramme.serializers.ParentPositionSerializer", {"many": False}),
            "edges": ("organigramme.serializers.OrganigramEdgeSerializer", {"many": True}),
        }
    
    def get_parent(self, obj):
        """
        Get the parent position by finding the source of the edge
        where this position is the target.
        """
        from .models import OrganigramEdge
        edge = OrganigramEdge.objects.filter(
            target=obj,
            organigram=obj.organigram
        ).select_related('source').first()
        
        if not edge:
            return None
            
        # Use ParentPositionSerializer to avoid recursion
        return ParentPositionSerializer(edge.source, context=self.context).data

class OrganigramEdgeSerializer(FlexFieldsModelSerializer):
    class Meta:
        model = OrganigramEdge
        fields = '__all__'
        read_only_fields = ("created_at",)

    def validate(self, data):
        """Validate single‑parent rule & hierarchy levels."""
        target = data["target"]
        if OrganigramEdge.objects.filter(target=target).exists():
            raise serializers.ValidationError("A node can only have one parent")

        source = data["source"]
    
        if source.grade.level > target.grade.level: 
            raise serializers.ValidationError("Parent must have a higher level than child")

        if (
            data["organigram"] != source.organigram
            or data["organigram"] != target.organigram
        ):
            raise serializers.ValidationError(
                "Source, target and edge must belong to the same organigram"
            )
        return data


class OrganigramSerializer(FlexFieldsModelSerializer):
    expandable_fields = {
        "positions": (PositionSerializer, {"many": True}),
        "edges": (OrganigramEdgeSerializer, {"many": True}),
    }

    class Meta:
        model = Organigram
        fields = '__all__'
        read_only_fields = ("created_at", "updated_at")

    def validate_name(self, value):
        if Organigram.objects.filter(name__iexact=value).exclude(id=self.instance.id if self.instance else None).exists():
            raise serializers.ValidationError("This name already exists.")
        return value
    