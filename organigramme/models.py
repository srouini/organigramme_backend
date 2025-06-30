from django.db import models

from django.contrib.auth.models import AbstractUser

from django.forms import ValidationError
from django.db.models.functions import Lower

class Grade(models.Model):
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
    
    name = models.CharField(max_length=255)
    state = models.CharField(max_length=10, choices=STATE_CHOICES, default='Draft')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['created_at']
        unique_together = ['name']

    def __str__(self):
        return self.name

class Position(models.Model):
    organigram = models.ForeignKey(Organigram, on_delete=models.CASCADE, related_name='positions')
    title = models.CharField(max_length=255)
    grade = models.ForeignKey(Grade,on_delete=models.CASCADE, related_name='grades',max_length=255)  # Store grade name
    level = models.IntegerField(default=0)
    color = models.CharField(max_length=7, default='#3B82F6')
    position_x = models.FloatField(default=0)
    position_y = models.FloatField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['level', 'title']
        indexes = [
            models.Index(fields=['organigram', 'level']),
        ]
    
    def __str__(self):
        return f"{self.title} - {self.organigram.name}"
    
class Task(models.Model):
    position = models.ForeignKey(Position, on_delete=models.CASCADE, related_name='tasks')
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['created_at']
    
    def __str__(self):
        return f"Task for {self.position.title}: {self.description[:20]}..."
    

class OrganigramEdge(models.Model):
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

