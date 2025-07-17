from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

from django.contrib.auth.models import AbstractUser

from django.forms import ValidationError
from django.db.models.functions import Lower


class Grade(models.Model):
    name = models.CharField(max_length=255)
    color = models.CharField(max_length=7, default='#3B82F6')  # Hex color
    category = models.CharField(max_length=20)  # Hex color
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
        unique_together = ['name']
    
    def __str__(self):
        return f"{self.name}"

class StructureType(models.Model):
    name = models.CharField(max_length=255)
    color = models.CharField(max_length=7, default='#3B82F6')  # Hex color
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['created_at']
        unique_together = ['name']

    def __str__(self):
        return self.name

class Structure(models.Model):
    is_main = models.BooleanField(default=False)
    initial_node = models.BooleanField(default=False)
    name = models.CharField(max_length=255)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, related_name='children', null=True, blank=True)
    type = models.ForeignKey('StructureType', on_delete=models.CASCADE, related_name='structure_type', null=True, blank=True)
    manager = models.ForeignKey('Position', on_delete=models.SET_NULL, related_name='managed_structures', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['created_at']


    def __str__(self):
        return self.name


class Position(models.Model):
    structure = models.ForeignKey(Structure, on_delete=models.PROTECT, related_name='positions',null=True,blank=True)
    is_manager = models.BooleanField(default=False, help_text='Whether this position is a manager position')
    title = models.CharField(max_length=255)
    mission_principal = models.TextField(default="",blank=True)
    abbreviation = models.CharField(max_length=255,null=True,blank=True)
    formation = models.CharField(max_length=255,default="",blank=True)
    experience = models.CharField(max_length=255,default="",blank=True)
    grade = models.ForeignKey(Grade,on_delete=models.PROTECT, related_name='grades',max_length=255)  # Store grade name
    category = models.CharField(max_length=20,blank=True,null=True)  # Hex color
    quantity = models.IntegerField(default=1)
    initial_node=models.BooleanField(default=False)
    position_x = models.FloatField(default=0)
    position_y = models.FloatField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['title']
        indexes = [
            models.Index(fields=['structure']),
        ]
    
    def __str__(self):
        return f"{self.title}"


class Task(models.Model):
    position = models.ForeignKey(Position, on_delete=models.CASCADE, related_name='tasks')
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-id']
    
    def __str__(self):
        return f"Task for {self.position.title}: {self.description[:20]}..."



class Mission(models.Model):
    position = models.ForeignKey(Position, on_delete=models.CASCADE, related_name='missions')
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-id']
    
    def __str__(self):
        return f"Task for {self.position.title}: {self.description[:20]}..."



class Competence(models.Model):
    position = models.ForeignKey(Position, on_delete=models.CASCADE, related_name='competences')
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-id']
    
    def __str__(self):
        return f"Task for {self.position.title}: {self.description[:20]}..."



class DiagramPosition(models.Model):
    """
    Stores the position of a structure or position relative to its nearest main parent structure.
    This allows the same item to have different positions in different diagrams.
    """
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')
    
    # The main structure this position is relative to
    main_structure = models.ForeignKey(Structure, on_delete=models.CASCADE, related_name='diagram_positions')
    
    # Position coordinates
    position_x = models.FloatField(default=0)
    position_y = models.FloatField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('content_type', 'object_id', 'main_structure')
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['main_structure']),
        ]
    
    def __str__(self):
        return f"{self.content_object} in {self.main_structure} at ({self.position_x}, {self.position_y})"


class OrganigramEdge(models.Model):
    structure = models.ForeignKey(Structure, on_delete=models.CASCADE, related_name='edges')

    source_content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, related_name='source_edges')
    source_object_id = models.PositiveIntegerField()
    source = GenericForeignKey('source_content_type', 'source_object_id')

    target_content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, related_name='target_edges')
    target_object_id = models.PositiveIntegerField()
    target = GenericForeignKey('target_content_type', 'target_object_id')

    edge_type = models.CharField(max_length=50, default='smoothstep')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('source_content_type', 'source_object_id', 'target_content_type', 'target_object_id')
        indexes = [
            models.Index(fields=['structure']),
            models.Index(fields=["source_content_type", "source_object_id"]),
            models.Index(fields=["target_content_type", "target_object_id"]),
        ]
    
    def __str__(self):
        return f"Edge from {self.source} to {self.target}"
