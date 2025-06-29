from django.contrib.auth import login, logout, authenticate
from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from .serializers import (
    UserSerializer, 
    LoginSerializer, 
    UpdateUserSerializer,
    ChangePasswordSerializer,
    UserListSerializer
)
from django.views.decorators.csrf import ensure_csrf_cookie, csrf_protect
from django.utils.decorators import method_decorator
import logging
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth.models import User
from django.utils import timezone

logger = logging.getLogger(__name__)

# Create your views here.

@method_decorator(ensure_csrf_cookie, name='dispatch')
class LoginView(APIView):
    permission_classes = (permissions.AllowAny,)
    
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            username = serializer.validated_data['username']
            password = serializer.validated_data['password']
            user = authenticate(username=username, password=password)
            
            if user is not None:
                login(request, user)
                logger.debug(f'User logged in: {user.username}')
                logger.debug(f'Profile: {user.profile.__dict__}')
                logger.debug(f'Allowed pages: {user.profile.allowed_pages}')
                
                # Update last connection time
                user.profile.last_connected = timezone.now()
                user.profile.save()
                
                return Response({
                    'user': UserSerializer(user).data,
                    'message': 'Login successful.'
                }, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@method_decorator(csrf_protect, name='dispatch')
class LogoutView(APIView):
    def post(self, request):
        try:
            if request.user.is_authenticated:
                logout(request)
                response = Response({'message': 'Logged out successfully'})
                response.delete_cookie('sessionid')
                response.delete_cookie('csrftoken')
                return response
            return Response({'error': 'Not logged in'}, status=status.HTTP_401_UNAUTHORIZED)
        except Exception as e:          
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@method_decorator(ensure_csrf_cookie, name='dispatch')
class UserView(APIView):
    def get(self, request):
        if not request.user.is_authenticated:
            return Response({'error': 'Not authenticated'}, status=status.HTTP_401_UNAUTHORIZED)
        serializer = UserSerializer(request.user)
        return Response(serializer.data)


@method_decorator(ensure_csrf_cookie, name='dispatch')
class VerifySessionView(APIView):
    def get(self, request):
        if request.user.is_authenticated:
            logger.debug(f'User authenticated: {request.user.username}')
            logger.debug(f'Is superuser: {request.user.is_superuser}')
            logger.debug(f'Profile: {request.user.profile.__dict__}')
            logger.debug(f'Allowed pages: {request.user.profile.allowed_pages}')
            return Response({
                'isAuthenticated': True,
                'user': UserSerializer(request.user).data
            })
        return Response({
            'isAuthenticated': False,
            'user': None
        }, status=status.HTTP_401_UNAUTHORIZED)


@method_decorator(csrf_protect, name='dispatch')
class UpdateUserView(APIView):
    def put(self, request):
        if not request.user.is_authenticated:
            return Response({'error': 'Not authenticated'}, status=status.HTTP_401_UNAUTHORIZED)
        
        serializer = UpdateUserSerializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({
                'message': 'User updated successfully',
                'user': UserSerializer(request.user).data
            })
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@method_decorator(csrf_protect, name='dispatch')
class ChangePasswordView(APIView):
    def post(self, request):
        if not request.user.is_authenticated:
            return Response({'error': 'Not authenticated'}, status=status.HTTP_401_UNAUTHORIZED)
        
        serializer = ChangePasswordSerializer(data=request.data)
        if serializer.is_valid():
            user = request.user
            if user.check_password(serializer.validated_data['old_password']):
                user.set_password(serializer.validated_data['new_password'])
                user.save()
                return Response({'message': 'Password updated successfully'})
            return Response({'error': 'Invalid old password'}, status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@method_decorator(csrf_protect, name='dispatch')
class UserListView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        users = User.objects.all()
        serializer = UserListSerializer(users, many=True)
        return Response(serializer.data)


@api_view(['PATCH','PUT'])
@permission_classes([IsAuthenticated])
def update_profile(request):
    try:
        user = request.user
        profile = user.profile
        
        # Update profile fields
        if 'theme_mode' in request.data:
            if request.data['theme_mode'] not in ['light', 'dark']:
                return Response(
                    {'error': 'Invalid theme_mode value. Must be either "light" or "dark".'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            profile.theme_mode = request.data['theme_mode']
            
        if 'theme_color' in request.data:
            profile.theme_color = request.data['theme_color']
            
        if 'layout_preference' in request.data:
            if request.data['layout_preference'] not in ['top', 'side']:
                return Response(
                    {'error': 'Invalid layout_preference value. Must be either "top" or "side".'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            profile.layout_preference = request.data['layout_preference']
            
        profile.save()
        
        # Return updated user data
        serializer = UserSerializer(user)
        return Response({
            'user': serializer.data,
            'message': 'Profile updated successfully'
        })
        
    except Exception as e:
        logger.error(f"Error updating profile: {str(e)}")
        return Response(
            {'error': 'Failed to update profile'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
