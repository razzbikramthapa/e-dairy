from rest_framework import generics, viewsets, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.contrib.auth.models import User
from django.db.models import Sum, Avg, Count
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from .models import Profile, MilkCollection
from .serializers import UserRegisterSerializer, UserSerializer, MilkCollectionSerializer

class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    permission_classes = (AllowAny,)
    serializer_class = UserRegisterSerializer

class UserProfileView(generics.RetrieveAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user

class FarmerListView(generics.ListAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = UserSerializer

    def get_queryset(self):
        return User.objects.filter(profile__role='farmer').order_by('first_name', 'username')

class MilkCollectionViewSet(viewsets.ModelViewSet):
    permission_classes = (IsAuthenticated,)
    serializer_class = MilkCollectionSerializer

    def get_queryset(self):
        user = self.request.user
        try:
            profile = user.profile
            if profile.role == 'farmer':
                # Farmers only see their own collections
                return MilkCollection.objects.filter(farmer=user).order_by('-timestamp')
        except Profile.DoesNotExist:
            pass
        # Agents/Admins can see all collections
        return MilkCollection.objects.all().order_by('-timestamp')

    def perform_create(self, serializer):
        serializer.save(collected_by=self.request.user)

class DashboardStatsView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        user = request.user
        
        # Base filter based on user role
        try:
            profile = user.profile
            is_farmer = (profile.role == 'farmer')
        except Profile.DoesNotExist:
            is_farmer = False

        collections = MilkCollection.objects.all()
        if is_farmer:
            collections = collections.filter(farmer=user)
            
        # 1. Calculate General Aggregates
        stats = collections.aggregate(
            total_milk=Sum('quantity'),
            avg_fat=Avg('fat'),
            total_collections=Count('id')
        )
        
        total_milk = stats['total_milk'] or Decimal('0.00')
        avg_fat = stats['avg_fat'] or Decimal('0.00')
        
        # Active farmers count (total farmers registered in system)
        active_farmers_count = User.objects.filter(profile__role='farmer').count()
        
        # 2. Calculate Weekly Chart Data (Last 7 Days)
        today = timezone.localdate()
        weekly_chart = []
        for i in range(6, -1, -1):
            date_point = today - timedelta(days=i)
            day_collections = collections.filter(date=date_point)
            day_sum = day_collections.aggregate(total=Sum('quantity'))['total'] or Decimal('0.00')
            weekly_chart.append({
                "day": date_point.strftime('%a'), # e.g. 'Mon', 'Tue'
                "date": date_point.strftime('%Y-%m-%d'),
                "total": float(day_sum)
            })

        # 3. Fetch Recent live records (Last 10)
        recent_records = collections.order_by('-timestamp')[:10]
        recent_records_serializer = MilkCollectionSerializer(recent_records, many=True)

        return Response({
            "summary": {
                "total_milk": float(total_milk),
                "avg_fat": round(float(avg_fat), 2),
                "active_farmers": active_farmers_count,
                "is_farmer": is_farmer,
                "role": profile.role if not is_farmer else 'farmer'
            },
            "chart_data": weekly_chart,
            "recent_records": recent_records_serializer.data
        }, status=status.HTTP_200_OK)
