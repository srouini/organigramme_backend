from django.contrib.auth import get_user_model
from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from .models import Profile

User = get_user_model()

class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = ('layout_preference', 'theme_color', 'theme_mode', 'allowed_pages')

class UserSerializer(serializers.ModelSerializer):
    profile = ProfileSerializer()
    user_permissions = serializers.SerializerMethodField()
    groups = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'first_name', 'last_name', 'is_superuser', 'profile', 'user_permissions', 'groups')
        read_only_fields = ('id', 'is_superuser', 'user_permissions', 'groups')

    def get_user_permissions(self, obj):
        if obj.is_superuser:
            return ['*']  # Superuser has all permissions
        permissions = obj.get_all_permissions()
        return [str(perm) for perm in permissions]  # Convert permissions to strings

    def get_groups(self, obj):
        return [group.name for group in obj.groups.all()]

    def update(self, instance, validated_data):
        profile_data = validated_data.pop('profile', {})
        # Update user data
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Update profile data
        if profile_data:
            profile = instance.profile
            for attr, value in profile_data.items():
                setattr(profile, attr, value)
            profile.save()

        return instance

class UserListSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('id', 'first_name', 'last_name', 'full_name')
        read_only_fields = ('id', 'full_name')

    def get_full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}".strip()

class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

class UpdateUserSerializer(serializers.ModelSerializer):
    profile = ProfileSerializer()

    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'email', 'profile')

    def update(self, instance, validated_data):
        profile_data = validated_data.pop('profile', None)
        # Update user data
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Update profile data
        if profile_data and hasattr(instance, 'profile'):
            for attr, value in profile_data.items():
                setattr(instance.profile, attr, value)
            instance.profile.save()

        return instance

class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True)

    def validate_new_password(self, value):
        validate_password(value)
        return value
