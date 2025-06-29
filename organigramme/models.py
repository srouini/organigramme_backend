from django.db import models

from django.contrib.auth.models import AbstractUser
import uuid

class Grade(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    level = models.IntegerField()
    color = models.CharField(max_length=7, default='#3B82F6')  # Hex color
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['level', 'name']
        unique_together = ['name', 'level']
    
    def __str__(self):
        return f"{self.name} (Level {self.level})"

class Organigram(models.Model):
    STATE_CHOICES = [
        ('Draft', 'Draft'),
        ('Final', 'Final'),
        ('Archived', 'Archived'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    state = models.CharField(max_length=10, choices=STATE_CHOICES, default='Draft')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return self.name

class Position(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organigram = models.ForeignKey(Organigram, on_delete=models.CASCADE, related_name='positions')
    title = models.CharField(max_length=255)
    grade = models.CharField(max_length=255)  # Store grade name
    level = models.IntegerField(default=0)
    color = models.CharField(max_length=7, default='#3B82F6')
    position_x = models.FloatField(default=0)
    position_y = models.FloatField(default=0)
    tasks = models.JSONField(default=list, blank=True)  # Array of tasks
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['level', 'title']
        indexes = [
            models.Index(fields=['organigram', 'level']),
        ]
    
    def __str__(self):
        return f"{self.title} - {self.organigram.name}"

class OrganigramEdge(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organigram = models.ForeignKey(Organigram, on_delete=models.CASCADE, related_name='edges')
    source = models.ForeignKey(Position, on_delete=models.CASCADE, related_name='outgoing_edges')
    target = models.ForeignKey(Position, on_delete=models.CASCADE, related_name='incoming_edges')
    edge_type = models.CharField(max_length=50, default='smoothstep')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['source', 'target']  # Prevent duplicate edges
        indexes = [
            models.Index(fields=['organigram']),
            models.Index(fields=['source']),
            models.Index(fields=['target']),
        ]
    
    def __str__(self):
        return f"{self.source.title} -> {self.target.title}"

