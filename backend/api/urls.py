from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import (
    TokenRefreshView,
)
from .views import (
    RegisterView,
    UserProfileView,
    FarmerListView,
    MilkCollectionViewSet,
    DashboardStatsView,
    GenerateCodeView,
    OTPTokenObtainPairView
)

router = DefaultRouter()
router.register(r'collection', MilkCollectionViewSet, basename='milk-collection')

urlpatterns = [
    # Auth Endpoints
    path('generate-code/', GenerateCodeView.as_view(), name='generate-code'),
    path('register/', RegisterView.as_view(), name='api-register'),
    path('token/', OTPTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    
    # User Profile & Directory
    path('profile/', UserProfileView.as_view(), name='user-profile'),
    path('farmers/', FarmerListView.as_view(), name='farmer-list'),
    
    # Dashboard Analytics
    path('dashboard/', DashboardStatsView.as_view(), name='dashboard-stats'),
    
    # Viewsets (Collection CRUD)
    path('', include(router.urls)),
]
