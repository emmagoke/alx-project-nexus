from django.db import models

# Create your models here.

class Timestamp(models.Model):
    """
    Timestamp mixin to inherit
    """

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Permission(Timestamp):
    """
    Defines individual permissions in the system
    """
    name = models.CharField(max_length=100, unique=True)
    codename = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return self.name


class Role(Timestamp):
    """
    Defines roles that can be assigned to users
    """
    name = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    permissions = models.ManyToManyField(Permission, blank=True)
    is_default = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        # Ensure only one default role exists
        if self.is_default:
            Role.objects.exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)


class User(AbstractUser, Timestamp):
    USER_TYPES = [
        ('admin', 'Administrator'),
        ('moderator', 'Moderator'),
        ('user', 'Regular User'),
    ]
    
    # id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    user_type = models.CharField(max_length=10, choices=USER_TYPES, default='user')
    
    # Role and permission relationships
    roles = models.ManyToManyField("Role", blank=True, through='UserRole')
    additional_permissions = models.ManyToManyField(
        Permission, 
        blank=True,
        help_text="Extra permissions granted directly to this user"
    )
    
    # Rate limiting fields
    api_calls_count = models.PositiveIntegerField(default=0)
    api_calls_reset_time = models.DateTimeField(null=True, blank=True)
    
    # Security fields
    failed_login_attempts = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    last_password_change = models.DateTimeField(auto_now_add=True)
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']
    
    @property
    def is_admin(self):
        return self.user_type == 'admin' or self.is_superuser
    
    @property
    def is_moderator(self):
        return self.user_type in ['admin', 'moderator'] or self.is_superuser
    
    def has_permission(self, permission_codename):
        """
        Check if user has a specific permission through roles or direct assignment
        """
        if self.is_superuser:
            return True
        
        # Check direct permissions
        if self.additional_permissions.filter(codename=permission_codename).exists():
            return True
        
        # Check role-based permissions
        return Permission.objects.filter(
            codename=permission_codename,
            role__userrole__user=self,
            role__userrole__is_active=True
        ).exists()
    
    def get_all_permissions(self):
        """
        Get all permissions for this user (from roles and direct assignments)
        """
        if self.is_superuser:
            return Permission.objects.all()
        
        # Permissions from roles
        role_permissions = Permission.objects.filter(
            role__userrole__user=self,
            role__userrole__is_active=True
        ).distinct()
        
        # Direct permissions
        direct_permissions = self.additional_permissions.all()
        
        # Combine and return unique permissions
        return (role_permissions | direct_permissions).distinct()
    
    def get_active_roles(self):
        """
        Get all active roles for this user
        """
        return self.roles.filter(userrole__is_active=True)


class UserRole(models.Model):
    """
    Through model for User-Role relationship with additional metadata
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    role = models.ForeignKey(Role, on_delete=models.CASCADE)
    is_active = models.BooleanField(default=True)
    assigned_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='assigned_roles'
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        unique_together = ['user', 'role']
        ordering = ['-assigned_at']
    
    def __str__(self):
        return f"{self.user.username} - {self.role.name}"
    
    @property
    def is_expired(self):
        if self.expires_at:
            from django.utils import timezone
            return timezone.now() > self.expires_at
        return False
