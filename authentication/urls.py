from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    LoginView, 
    LogoutView, 
    UserView, 
    VerifySessionView, 
    UpdateUserView, 
    ChangePasswordView,
    UserListView,
    update_profile
)
from .viewsets import UserViewSet, ProfileViewSet

router = DefaultRouter()
router.register(r'users', UserViewSet)
router.register(r'profiles', ProfileViewSet)

urlpatterns = [
    path('login/', LoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('user/', UserView.as_view(), name='user'),
    path('verify/', VerifySessionView.as_view(), name='verify'),
    path('update-user/', UpdateUserView.as_view(), name='update-user'),
    path('change-password/', ChangePasswordView.as_view(), name='change-password'),
    path('user-list/', UserListView.as_view(), name='user-list'),
    path('update-profile/', update_profile, name='update-profile'),
    # Include router URLs for RESTful API
    path('api/', include(router.urls)),
]
