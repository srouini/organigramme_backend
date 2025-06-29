from django.contrib import admin
from django.conf.urls.static import static
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from graphene_django.views import GraphQLView
from django.conf import settings
from .schema import schema  # Import the schema directly
from django.views.decorators.csrf import ensure_csrf_cookie, csrf_exempt
from django.http import HttpResponse


# Add a view to set CSRF cookie
@ensure_csrf_cookie
def csrf_view(request):
    return HttpResponse("CSRF cookie set")

urlpatterns = [
    path('admin/', admin.site.urls),
    path('csrf/', csrf_view, name='csrf'),
    path('auth/', include('authentication.urls')),
    path('api/', include('organigramme.urls')),
    path('graphql/', csrf_exempt(GraphQLView.as_view(graphiql=True, schema=schema))),
    # Add REST API URLs
    # path('api/', include(router.urls)),
    # Add REST API auth URLs
    path('api-auth/', include('rest_framework.urls')),
    path('api/auth/', include('authentication.urls')),
    
    # Include app-specific REST API URLs
    path('authentication/', include('authentication.urls')),

] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)