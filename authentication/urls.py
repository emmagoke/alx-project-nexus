from django.urls import path, include
from rest_framework.routers import DefaultRouter

from authentication.views import (
    UserRegistrationView, CustomTokenObtainPairView
)

router = DefaultRouter()
# router.register(r"auth", UserRegistrationView., basename="user-registration")

urlpatterns = [
    path("", include(router.urls)),
    path("register/", UserRegistrationView.as_view(), name="user-registration"),
    path("login/", CustomTokenObtainPairView.as_view(), name="token_obtain_pair"),
]
