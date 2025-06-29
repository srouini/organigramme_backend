from django.core.management.base import BaseCommand
from authentication.models import User

class Command(BaseCommand):
    help = 'Set default page permissions for users'

    def handle(self, *args, **kwargs):
        # Basic pages that all authenticated users should have access to
        default_pages = ['/', '/profile', '/settings']
        
        # Get all users excluding superusers (they have access to everything)
        users = User.objects.filter(is_superuser=False)
        
        for user in users:
            if not user.allowed_pages:
                user.allowed_pages = default_pages
                user.save()
                self.stdout.write(
                    self.style.SUCCESS(f'Set default permissions for user: {user.username}')
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f'User {user.username} already has permissions: {user.allowed_pages}')
                )
