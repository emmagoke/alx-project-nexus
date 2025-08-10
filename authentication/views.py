from rest_framework.views import APIView
from rest_framework import status, permissions
from rest_framework.response import Response
from django.db import transaction
import logging

from .serializers import UserRegistrationSerializer
from .models import Role, UserRole


logger = logging.getLogger(__name__)


class UserRegistrationView(APIView):
    """
    User registration endpoint
    """
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        serializer = UserRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            try:
                with transaction.atomic():
                    # Create the user
                    user = serializer.save()
                    
                    # Assign "Regular User" role to new users
                    try:
                        regular_user_role = Role.objects.get(name='Regular User')
                        UserRole.objects.create(
                            user=user,
                            role=regular_user_role,
                            assigned_by=None  # System assigned
                        )
                        logger.info(f"Assigned 'Regular User' role to user {user.username}")
                    except Role.DoesNotExist:
                        logger.warning(f"'Regular User' role not found for user {user.username}. Please run setup_default_privileges command.")
                
                return Response({
                    'message': 'User registered successfully',
                    'data': {
                        'user_id': str(user.id),
                        'username': user.username,
                        'email': user.email,
                        'user_type': user.user_type
                    }
                }, status=status.HTTP_201_CREATED)
                
            except Exception as e:
                logger.error(f"Error during user registration: {str(e)}")
                return Response({
                    'error': 'Registration failed. Please try again.'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        return Response(
            {
                'errors': serializer.errors,
                'message': 'Invalid data provided for registration'
            },
            status=status.HTTP_400_BAD_REQUEST
        )
