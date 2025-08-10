from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth import authenticate
from django.utils import timezone
from datetime import timedelta
from django.db import transaction
from django.db.models import F
import logging

from .models import User


logger = logging.getLogger(__name__)

class UserRegistrationSerializer(serializers.ModelSerializer):
    """
    Serializer for user registration
    """
    password = serializers.CharField(
        write_only=True,
        min_length=8,
        style={'input_type': 'password'}
    )
    password_confirm = serializers.CharField(
        write_only=True,
        required=False,
        style={'input_type': 'password'}
    )
    
    class Meta:
        model = User
        fields = [
            'username', 
            'email', 
            'first_name', 
            'last_name', 
            'password', 
            'password_confirm'
        ]
        extra_kwargs = {
            'email': {'required': True},
            'first_name': {'required': False},
            'last_name': {'required': False},
        }
    
    def validate_email(self, value):
        """
        Check if email is already registered
        """
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value
    
    def validate_username(self, value):
        """
        Check if username is already taken
        """
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("A user with this username already exists.")
        return value
    
    def validate_password(self, value):
        """
        Validate password using Django's password validators
        """
        try:
            validate_password(value)
        except ValidationError as e:
            raise serializers.ValidationError(e.messages)
        return value
    
    def validate(self, attrs):
        """
        Check that the two password fields match (if password_confirm is provided)
        """
        password = attrs.get('password')
        password_confirm = attrs.get('password_confirm')
        
        # Only validate password confirmation if it's provided
        if password_confirm is not None and password != password_confirm:
            raise serializers.ValidationError({
                'password_confirm': "Password fields didn't match."
            })
        
        # Remove password_confirm from attrs as it's not a model field
        attrs.pop('password_confirm', None)
        return attrs
    
    def create(self, validated_data):
        """
        Create and return a new user instance with encrypted password
        """
        # Extract password from validated data
        password = validated_data.pop('password')
        
        # Set default user_type if not provided
        if 'user_type' not in validated_data:
            validated_data['user_type'] = 'user'  # Default to 'user' type
        
        # Create user instance
        user = User.objects.create_user(
            password=password,
            **validated_data
        )
        
        return user


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Custom serializer for JWT token generation with additional claims
    """
    @classmethod
    def get_token(cls, user):
        """
        This method is called to generate the actual JWT token.
        Override this to add custom claims to the token payload.
        """
        token = super().get_token(user)
        
        # Add custom claims to the token payload
        try:
            # Add user basic info
            token['user_type'] = user.user_type
            token['user_id'] = str(user.id)
            token['username'] = user.username
            token['email'] = user.email
            
            # Add permissions - Fixed to work without additional_permissions
            try:
                # Get permissions only from roles since additional_permissions is commented out
                user_permissions = list(
                    user.roles.filter(userrole__is_active=True)
                    .values_list('permissions__codename', flat=True)
                    .distinct()
                )
                # Remove None values if any
                user_permissions = [p for p in user_permissions if p is not None]
            except Exception as e:
                logger.warning(f"Error getting permissions for user {user.email}: {str(e)}")
                user_permissions = []
            
            token['permissions'] = user_permissions
            
            # Add roles
            try:
                user_roles = list(user.get_active_roles().values_list('name', flat=True))
            except Exception as e:
                logger.warning(f"Error getting roles for user {user.email}: {str(e)}")
                user_roles = []
            
            token['roles'] = user_roles
            
            # Add timestamps
            token['last_login'] = user.last_login.isoformat() if user.last_login else None
            token['is_admin'] = user.is_admin
            token['is_moderator'] = user.is_moderator
            
            # Add login metadata if available (from validate method)
            if hasattr(user, '_login_metadata'):
                token['login_time'] = user._login_metadata.get('login_time')
                token['login_ip'] = user._login_metadata.get('login_ip')
                token['failed_attempts_reset'] = user._login_metadata.get('failed_attempts_reset', False)
            
            logger.info(f"Generated token for user {user.email} with {len(user_permissions)} permissions and {len(user_roles)} roles")
            
        except Exception as e:
            logger.error(f"Error adding custom claims to token for {user.email}: {str(e)}")
            # Add minimal data if there's an error
            token['user_type'] = getattr(user, 'user_type', 'user')
            token['permissions'] = []
            token['roles'] = []
        
        return token
    
    def validate(self, attrs):
        email = attrs.get('email')
        password = attrs.get('password')
        
        try:
            # Use select_for_update to prevent race conditions
            with transaction.atomic():
                try:
                    user = User.objects.select_for_update().get(email=email)
                except User.DoesNotExist:
                    # Don't reveal that user doesn't exist
                    raise serializers.ValidationError("Invalid credentials")
                
                # Check if account is locked
                if user.locked_until and user.locked_until > timezone.now():
                    remaining_time = (user.locked_until - timezone.now()).total_seconds() / 60
                    raise serializers.ValidationError(
                        f"Account is temporarily locked. Try again in {remaining_time:.0f} minutes."
                    )
                
                # Clear lock if it has expired
                if user.locked_until and user.locked_until <= timezone.now():
                    user.locked_until = None
                    user.failed_login_attempts = 0
                    user.save(update_fields=['locked_until', 'failed_login_attempts'])
                
                # Authenticate user
                authenticated_user = authenticate(email=email, password=password)
                
                if not authenticated_user:
                    # Use F expressions to handle concurrent updates safely
                    User.objects.filter(id=user.id).update(
                        failed_login_attempts=F('failed_login_attempts') + 1
                    )
                    
                    # Refresh user object to get updated values
                    user.refresh_from_db()
                    
                    # Lock account after 5 failed attempts
                    if user.failed_login_attempts >= 5:
                        lock_time = timezone.now() + timedelta(minutes=30)
                        User.objects.filter(id=user.id).update(
                            locked_until=lock_time
                        )
                        logger.warning(f"Account locked for user {user.email} after {user.failed_login_attempts} failed attempts")
                        raise serializers.ValidationError(
                            "Account has been locked due to multiple failed login attempts. Try again in 30 minutes."
                        )
                    
                    logger.warning(f"Failed login attempt for user {user.email}. Attempt #{user.failed_login_attempts}")
                    raise serializers.ValidationError("Invalid credentials")
                
                # Successful login - reset failed attempts
                if user.failed_login_attempts > 0:
                    User.objects.filter(id=user.id).update(
                        failed_login_attempts=0,
                        locked_until=None
                    )
                    logger.info(f"Successful login for user {user.email}. Reset failed attempts counter.")
                
                # Update last login time
                user.last_login = timezone.now()
                user.save(update_fields=['last_login'])
                
                # Use the authenticated user for token generation
                user = authenticated_user
        
        except User.DoesNotExist:
            # This shouldn't happen due to the check above, but just in case
            raise serializers.ValidationError("Invalid credentials")
        
        # Call parent validation - this will call get_token() which adds our custom claims
        data = super().validate(attrs)
        
        # The token already contains our custom claims from get_token()
        # But we can add additional response data here that won't go in the token
        # data['message'] = 'Login successful'
        # data['user_info'] = {
        #     'user_id': str(user.id),
        #     'username': user.username,
        #     'email': user.email,
        #     'user_type': user.user_type,
        #     'last_login': user.last_login.isoformat() if user.last_login else None
        # }
        
        logger.info(f"Successful login for user {user.email}")
        
        return data