from django.apps import AppConfig

class SrcConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'src'

    def ready(self):
        from .permissions import create_export_permissions
        create_export_permissions()
