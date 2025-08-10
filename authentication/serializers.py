from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from .models import User


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
