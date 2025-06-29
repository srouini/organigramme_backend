from django.contrib.auth.models import User
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver

# Create your models here.

class Profile(models.Model):
    LAYOUT_CHOICES = [
        ('top', 'Top'),
        ('side', 'Side'),
    ]
    
    THEME_MODE_CHOICES = [
        ('light', 'Light'),
        ('dark', 'Dark'),
    ]

    # Available pages in the application
    AVAILABLE_PAGES = [
        '/',
        '/dashboard',
        '/analytics',
        '/users',
        '/reports',
        '/tasks',
        '/profile',
        '/settings'
    ]

    # Public pages that don't require authentication
    PUBLIC_PAGES = ['/login', '/register', '/forgot-password']

    # Default pages every user should have access to
    DEFAULT_PAGES = ['/', '/profile', '/settings']

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    layout_preference = models.CharField(
        max_length=4,
        choices=LAYOUT_CHOICES,
        default='top'
    )
    theme_color = models.CharField(
        max_length=7,
        default='#968b6a',
        help_text='Theme color in hex format (e.g. #968b6a)'
    )
    theme_mode = models.CharField(
        max_length=5,
        choices=THEME_MODE_CHOICES,
        default='light'
    )
    allowed_pages = models.JSONField(
        default=list,
        blank=True,
        help_text='List of pages this user can access'
    )

    def __str__(self):
        return f'{self.user.username} Profile'

    def has_page_permission(self, page_path):
        # Allow access to public pages
        if page_path in self.PUBLIC_PAGES:
            return True
            
        # Superusers can access everything
        if self.user.is_superuser:
            return True
            
        # Everyone can access default pages
        if page_path in self.DEFAULT_PAGES:
            return True

        # Check if page is in allowed_pages
        return page_path in self.allowed_pages

    def save(self, *args, **kwargs):
        # Initialize allowed_pages if it's None
        if self.allowed_pages is None:
            self.allowed_pages = ['/', '/profile', '/settings']
        
        # Ensure it's a list
        if not isinstance(self.allowed_pages, list):
            self.allowed_pages = list(self.allowed_pages)

        # Ensure required pages are always included
        required_pages = ['/', '/profile', '/settings']
        for page in required_pages:
            if page not in self.allowed_pages:
                self.allowed_pages.append(page)

        super().save(*args, **kwargs)

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(
            user=instance,
            allowed_pages=['/', '/profile', '/settings']  # Default pages
        )

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    instance.profile.save()
