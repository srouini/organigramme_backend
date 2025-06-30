from rest_framework import serializers
from rest_flex_fields import FlexFieldsModelSerializer
from .models import Grade, Organigram, Position, OrganigramEdge, Task


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


class PositionSerializer(FlexFieldsModelSerializer):
    class Meta:
        model = Position
        fields = '__all__'
        read_only_fields = ("created_at", "updated_at")


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
        if source.level >= target.level:
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
    