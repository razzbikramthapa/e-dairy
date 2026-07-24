from rest_framework import generics, viewsets, status
from rest_framework.decorators import permission_classes, api_view
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.contrib.auth.models import User
from django.db.models import Sum, Avg, Count, Q
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from rest_framework_simplejwt.views import TokenObtainPairView
import logging

from .models import Profile, MilkCollection, LinkedFarmer, Payment, FarmerBankDetails, QualityRecord
from .serializers import (
    UserRegisterSerializer, 
    UserSerializer, 
    MilkCollectionSerializer,
    OTPTokenObtainPairSerializer,
    LinkedFarmerSerializer,
    PaymentSerializer,
    QualityRecordSerializer
)
from .twilio_helper import send_otp, send_sparrow_sms

logger = logging.getLogger(__name__)

class DeleteAccountView(APIView):
    permission_classes = (IsAuthenticated,)

    def delete(self, request):
        user = request.user
        user.delete()
        return Response({"detail": "Account deleted successfully."}, status=status.HTTP_204_NO_CONTENT)


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    permission_classes = (AllowAny,)
    serializer_class = UserRegisterSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        headers = self.get_success_headers(serializer.data)
        
        # Return full user profile detail, including generated farmer_code
        response_serializer = UserSerializer(user)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED, headers=headers)

class UserProfileView(generics.RetrieveAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user

class FarmerListView(generics.ListAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = UserSerializer

    def get_queryset(self):
        queryset = User.objects.filter(profile__role='farmer').order_by('first_name', 'username')
        search_query = self.request.query_params.get('search', '').strip()
        if search_query:
            queryset = queryset.filter(
                Q(profile__farmer_code__icontains=search_query) |
                Q(first_name__icontains=search_query) |
                Q(last_name__icontains=search_query) |
                Q(username__icontains=search_query) |
                Q(profile__phone__icontains=search_query)
            )
        return queryset

class MilkCollectionViewSet(viewsets.ModelViewSet):
    permission_classes = (IsAuthenticated,)
    serializer_class = MilkCollectionSerializer

    def get_queryset(self):
        user = self.request.user
        try:
            profile = user.profile
            if profile.role == 'farmer':
                queryset = MilkCollection.objects.filter(farmer=user)
            else:
                queryset = MilkCollection.objects.filter(collected_by=user)
        except Profile.DoesNotExist:
            queryset = MilkCollection.objects.all()
            
        # Filters
        date_param = self.request.query_params.get('date')
        if date_param:
            queryset = queryset.filter(date=date_param)
            
        farmer_param = self.request.query_params.get('farmer')
        if farmer_param:
            queryset = queryset.filter(farmer_id=farmer_param)
            
        session_param = self.request.query_params.get('session')
        if session_param:
            queryset = queryset.filter(session=session_param)
            
        return queryset.order_by('-timestamp')

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


class GenerateCodeView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        phone = request.data.get('phone', '').strip()
        purpose = request.data.get('purpose', 'register').strip()
        
        if not phone:
            return Response({"detail": "Phone number is required."}, status=status.HTTP_400_BAD_REQUEST)
        
        user_exists = User.objects.filter(username=phone).exists()
        
        if purpose == 'register':
            if user_exists:
                return Response({"detail": "This mobile number is already registered."}, status=status.HTTP_400_BAD_REQUEST)
        elif purpose == 'login':
            if not user_exists:
                return Response({"detail": "This mobile number is not registered."}, status=status.HTTP_400_BAD_REQUEST)
        
        # Trigger sending the SMS code via Twilio/NepalOTP
        try:
            res = send_otp(phone)
            response_data = {
                "status": "success",
                "phone": phone,
                "message": res["message"]
            }
            if res.get("status") == "simulated":
                response_data["code"] = res["code"]
            
            return Response(response_data, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class OTPTokenObtainPairView(TokenObtainPairView):
    serializer_class = OTPTokenObtainPairSerializer


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dairy_dashboard(request):
    """Dairy Operator Dashboard Summary Stats"""
    user = request.user
    today = timezone.localdate()
    
    # Today's milk collection
    today_collections = MilkCollection.objects.filter(
        collected_by=user,
        date=today
    ).aggregate(
        total_quantity=Sum('quantity'),
        total_amount=Sum('amount')
    )
    
    # Today's paid summary
    today_payments = Payment.objects.filter(
        dairy_operator=user,
        payment_date=today,
        payment_status='paid'
    ).aggregate(total=Sum('paid_amount'))
    
    # Linked farmers count
    linked_farmers_count = LinkedFarmer.objects.filter(dairy_operator=user, is_active=True).count()
    
    # Pending payments sum
    pending_payments = Payment.objects.filter(
        dairy_operator=user,
        payment_status='pending'
    ).aggregate(total=Sum('pending_amount'))
    
    # Recent collections (last 5)
    recent_collections = MilkCollection.objects.filter(
        collected_by=user
    ).order_by('-timestamp')[:5]
    
    return Response({
        'today_total_quantity': float(today_collections['total_quantity'] or 0),
        'today_total_amount': float(today_collections['total_amount'] or 0),
        'today_total_payments': float(today_payments['total'] or 0),
        'linked_farmers': linked_farmers_count,
        'pending_payments': float(pending_payments['total'] or 0),
        'recent_collections': MilkCollectionSerializer(recent_collections, many=True).data
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def link_farmer(request):
    """Link a farmer to the dairy operator using their farmer_code"""
    farmer_code = request.data.get('farmer_code')
    if not farmer_code:
        return Response({'detail': 'Farmer code is required.'}, status=status.HTTP_400_BAD_REQUEST)
        
    try:
        profile = Profile.objects.get(farmer_code=farmer_code, role='farmer')
        farmer = profile.user
    except Profile.DoesNotExist:
        return Response({'detail': 'Farmer with this code does not exist.'}, status=status.HTTP_404_NOT_FOUND)
        
    linked_farmer, created = LinkedFarmer.objects.get_or_create(
        dairy_operator=request.user,
        farmer=farmer
    )
    
    if not created:
        if linked_farmer.is_active:
            return Response({'detail': 'Farmer is already linked.'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            linked_farmer.is_active = True
            linked_farmer.save()
            return Response({'detail': 'Farmer re-linked successfully.'}, status=status.HTTP_200_OK)
            
    return Response({'detail': 'Farmer linked successfully.'}, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def deactivate_linked_farmer(request):
    """Deactivate or unlink a farmer from the dairy operator"""
    farmer_id = request.data.get('farmer_id')
    if not farmer_id:
        return Response({'detail': 'Farmer ID is required.'}, status=status.HTTP_400_BAD_REQUEST)
        
    try:
        link = LinkedFarmer.objects.get(dairy_operator=request.user, farmer_id=farmer_id)
        link.is_active = False
        link.save()
        return Response({'detail': 'Farmer unlinked successfully.'})
    except LinkedFarmer.DoesNotExist:
        return Response({'detail': 'Link not found.'}, status=status.HTTP_404_NOT_FOUND)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_linked_farmers(request):
    """Get all currently active linked farmers for the operator"""
    linked = LinkedFarmer.objects.filter(dairy_operator=request.user, is_active=True)
    serializer = LinkedFarmerSerializer(linked, many=True)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def search_farmer_by_code(request):
    """Search farmer profile by Farmer Code before linking"""
    code = request.query_params.get('farmer_code', '').strip()
    if not code:
        return Response({'detail': 'Farmer code is required.'}, status=status.HTTP_400_BAD_REQUEST)
        
    try:
        profile = Profile.objects.get(farmer_code=code, role='farmer')
        user = profile.user
    except Profile.DoesNotExist:
        return Response({'detail': 'Farmer with this code does not exist.'}, status=status.HTTP_404_NOT_FOUND)
        
    bank_details_list = user.bank_details.all()
    bank_data = [
        {
            'id': bd.id,
            'bank_name': bd.bank_name,
            'account_holder_name': bd.account_holder_name,
            'account_number': bd.account_number
        } for bd in bank_details_list
    ]
    
    is_linked = LinkedFarmer.objects.filter(dairy_operator=request.user, farmer=user, is_active=True).exists()
    
    return Response({
        'id': user.id,
        'username': user.username,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'phone': profile.phone,
        'address': profile.address,
        'farmer_code': profile.farmer_code,
        'farm_name': profile.farm_name,
        'bank_details': bank_data,
        'is_linked': is_linked
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def record_milk_collection(request):
    """Record a milk collection entry and trigger SMS notification"""
    serializer = MilkCollectionSerializer(data=request.data)
    if serializer.is_valid():
        collection = serializer.save(collected_by=request.user)
        
        # Trigger SMS Notification to farmer
        farmer = collection.farmer
        phone = farmer.profile.phone
        if phone:
            msg = f"Dear {farmer.get_full_name() or farmer.username}, milk collection recorded: {collection.quantity:.2f}L (FAT: {collection.fat:.2f}%, SNF: {collection.snf:.2f}%) on {collection.date} ({collection.session.capitalize()}). Rate: Rs. {collection.rate:.2f}/L. Total: Rs. {collection.amount:.2f}. Thank you!"
            try:
                send_sparrow_sms(phone, msg)
            except Exception as e:
                logger.error(f"Failed to send collection SMS: {e}")
                
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def farmer_payable_summary(request, farmer_id):
    """Get farmer's payout summary (total earned, paid, pending balance, and bank info)"""
    try:
        farmer = User.objects.get(id=farmer_id, profile__role='farmer')
    except User.DoesNotExist:
        return Response({'detail': 'Farmer not found.'}, status=status.HTTP_404_NOT_FOUND)
        
    total_earned = MilkCollection.objects.filter(farmer=farmer).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    total_paid = Payment.objects.filter(farmer=farmer, payment_status='paid').aggregate(total=Sum('paid_amount'))['total'] or Decimal('0.00')
    total_deductions = Payment.objects.filter(farmer=farmer, payment_status='paid').aggregate(total=Sum('deductions'))['total'] or Decimal('0.00')
    
    pending_balance = total_earned - total_paid - total_deductions
    if pending_balance < 0:
        pending_balance = Decimal('0.00')
        
    bank_details_list = farmer.bank_details.all()
    bank_data = [
        {
            'id': bd.id,
            'bank_name': bd.bank_name,
            'account_holder_name': bd.account_holder_name,
            'account_number': bd.account_number
        } for bd in bank_details_list
    ]
    
    return Response({
        'farmer_id': farmer.id,
        'farmer_name': farmer.get_full_name() or farmer.username,
        'farmer_code': farmer.profile.farmer_code,
        'total_earned': float(total_earned),
        'total_paid': float(total_paid),
        'total_deductions': float(total_deductions),
        'pending_balance': float(pending_balance),
        'bank_details': bank_data
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def process_payment(request):
    """Process a payout transaction to a farmer and trigger SMS notification"""
    serializer = PaymentSerializer(data=request.data)
    if serializer.is_valid():
        payment = serializer.save(dairy_operator=request.user)
        
        # Trigger SMS Notification to farmer
        farmer = payment.farmer
        phone = farmer.profile.phone
        if phone and payment.payment_status == 'paid':
            msg = f"Dear {farmer.get_full_name() or farmer.username}, payment of Rs. {payment.paid_amount:.2f} processed via {payment.get_payment_method_display()} on {payment.payment_date}. Deductions: Rs. {payment.deductions:.2f}. Remaining balance: Rs. {payment.pending_amount:.2f}."
            try:
                send_sparrow_sms(phone, msg)
            except Exception as e:
                logger.error(f"Failed to send payment SMS: {e}")
                
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_farmer_payment_history(request, farmer_id):
    """Get the payment transaction history for a farmer"""
    payments = Payment.objects.filter(
        dairy_operator=request.user,
        farmer_id=farmer_id
    ).order_by('-payment_time')
    serializer = PaymentSerializer(payments, many=True)
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def notify_pending_payment(request):
    """Notify farmer about pending balance via Sparrow SMS"""
    farmer_id = request.data.get('farmer_id')
    if not farmer_id:
        return Response({'detail': 'Farmer ID is required.'}, status=status.HTTP_400_BAD_REQUEST)
        
    try:
        farmer = User.objects.get(id=farmer_id, profile__role='farmer')
    except User.DoesNotExist:
        return Response({'detail': 'Farmer not found.'}, status=status.HTTP_404_NOT_FOUND)
        
    total_earned = MilkCollection.objects.filter(farmer=farmer).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    total_paid = Payment.objects.filter(farmer=farmer, payment_status='paid').aggregate(total=Sum('paid_amount'))['total'] or Decimal('0.00')
    total_deductions = Payment.objects.filter(farmer=farmer, payment_status='paid').aggregate(total=Sum('deductions'))['total'] or Decimal('0.00')
    pending_balance = total_earned - total_paid - total_deductions
    if pending_balance < 0:
        pending_balance = Decimal('0.00')
        
    phone = farmer.profile.phone
    if not phone:
        return Response({'detail': 'Farmer does not have a registered phone number.'}, status=status.HTTP_400_BAD_REQUEST)
        
    msg = f"Dear {farmer.get_full_name() or farmer.username}, this is a reminder that you have a pending payment balance of Rs. {pending_balance:.2f} for your milk supplies. Please visit the Collection Centre."
    res = send_sparrow_sms(phone, msg)
    
    return Response({
        'detail': 'Notification sent successfully.',
        'sms_status': res.get('status'),
        'sms_message': res.get('message'),
        'sms_text': res.get('text')
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def generate_report(request):
    """Generate various collection and payout reports with filters"""
    report_type = request.query_params.get('report_type')
    date_str = request.query_params.get('date', str(timezone.localdate()))
    farmer_id = request.query_params.get('farmer_id')
    month = request.query_params.get('month', str(timezone.localdate().month))
    year = request.query_params.get('year', str(timezone.localdate().year))
    
    user = request.user
    
    if not report_type:
        return Response({'detail': 'report_type parameter is required.'}, status=status.HTTP_400_BAD_REQUEST)
        
    try:
        target_date = timezone.datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        target_date = timezone.localdate()
        
    collections = MilkCollection.objects.filter(collected_by=user)
    payments = Payment.objects.filter(dairy_operator=user)
    
    if report_type == 'daily_collection':
        data = collections.filter(date=target_date)
        serializer = MilkCollectionSerializer(data, many=True)
        summary = data.aggregate(total_qty=Sum('quantity'), total_amt=Sum('amount'))
        return Response({
            'report_type': report_type,
            'date': str(target_date),
            'summary': {
                'total_quantity': float(summary['total_qty'] or 0),
                'total_amount': float(summary['total_amt'] or 0)
            },
            'records': serializer.data
        })
        
    elif report_type == 'farmer_collection':
        if not farmer_id:
            return Response({'detail': 'farmer_id parameter is required.'}, status=status.HTTP_400_BAD_REQUEST)
        data = collections.filter(farmer_id=farmer_id).order_by('-date')
        serializer = MilkCollectionSerializer(data, many=True)
        summary = data.aggregate(
            total_qty=Sum('quantity'),
            total_amt=Sum('amount'),
            avg_fat=Avg('fat'),
            avg_snf=Avg('snf')
        )
        return Response({
            'report_type': report_type,
            'farmer_id': farmer_id,
            'summary': {
                'total_quantity': float(summary['total_qty'] or 0),
                'total_amount': float(summary['total_amt'] or 0),
                'avg_fat': float(summary['avg_fat'] or 0),
                'avg_snf': float(summary['avg_snf'] or 0)
            },
            'records': serializer.data
        })
        
    elif report_type == 'dairy_collection':
        data = collections.filter(date__year=year, date__month=month).values('date').annotate(
            total_qty=Sum('quantity'),
            total_amt=Sum('amount'),
            records_count=Count('id')
        ).order_by('-date')
        return Response({
            'report_type': report_type,
            'month': int(month),
            'year': int(year),
            'records': list(data)
        })
        
    elif report_type == 'quality_report':
        data = collections.filter(date=target_date)
        records = [{
            'id': r.id,
            'farmer_name': r.farmer.get_full_name() or r.farmer.username,
            'farmer_code': r.farmer.profile.farmer_code,
            'date': str(r.date),
            'session': r.session,
            'quantity': float(r.quantity),
            'fat': float(r.fat),
            'snf': float(r.snf),
            'rate': float(r.rate)
        } for r in data]
        summary = data.aggregate(avg_fat=Avg('fat'), avg_snf=Avg('snf'), total_qty=Sum('quantity'))
        return Response({
            'report_type': report_type,
            'date': str(target_date),
            'summary': {
                'avg_fat': float(summary['avg_fat'] or 0),
                'avg_snf': float(summary['avg_snf'] or 0),
                'total_quantity': float(summary['total_qty'] or 0)
            },
            'records': records
        })
        
    elif report_type == 'daily_payment':
        data = payments.filter(payment_date=target_date)
        serializer = PaymentSerializer(data, many=True)
        summary = data.aggregate(
            total_paid=Sum('paid_amount'),
            total_pending=Sum('pending_amount'),
            total_deductions=Sum('deductions')
        )
        return Response({
            'report_type': report_type,
            'date': str(target_date),
            'summary': {
                'total_paid': float(summary['total_paid'] or 0),
                'total_pending': float(summary['total_pending'] or 0),
                'total_deductions': float(summary['total_deductions'] or 0)
            },
            'records': serializer.data
        })
        
    elif report_type == 'monthly_payment':
        data = payments.filter(payment_date__year=year, payment_date__month=month)
        serializer = PaymentSerializer(data, many=True)
        summary = data.aggregate(
            total_paid=Sum('paid_amount'),
            total_pending=Sum('pending_amount'),
            total_deductions=Sum('deductions')
        )
        return Response({
            'report_type': report_type,
            'month': int(month),
            'year': int(year),
            'summary': {
                'total_paid': float(summary['total_paid'] or 0),
                'total_pending': float(summary['total_pending'] or 0),
                'total_deductions': float(summary['total_deductions'] or 0)
            },
            'records': serializer.data
        })
        
    elif report_type == 'pending_payment':
        linked_farmers = LinkedFarmer.objects.filter(dairy_operator=user, is_active=True)
        records = []
        for lf in linked_farmers:
            farmer = lf.farmer
            total_earned = MilkCollection.objects.filter(farmer=farmer).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
            total_paid = Payment.objects.filter(farmer=farmer, payment_status='paid').aggregate(total=Sum('paid_amount'))['total'] or Decimal('0.00')
            total_deductions = Payment.objects.filter(farmer=farmer, payment_status='paid').aggregate(total=Sum('deductions'))['total'] or Decimal('0.00')
            pending_balance = total_earned - total_paid - total_deductions
            if pending_balance > 0:
                records.append({
                    'farmer_id': farmer.id,
                    'farmer_name': farmer.get_full_name() or farmer.username,
                    'farmer_code': farmer.profile.farmer_code,
                    'phone': farmer.profile.phone,
                    'pending_balance': float(pending_balance)
                })
        return Response({
            'report_type': report_type,
            'records': records
        })
        
    elif report_type == 'farmer_payment':
        if not farmer_id:
            return Response({'detail': 'farmer_id parameter is required.'}, status=status.HTTP_400_BAD_REQUEST)
        data = payments.filter(farmer_id=farmer_id).order_by('-payment_date')
        serializer = PaymentSerializer(data, many=True)
        return Response({
            'report_type': report_type,
            'farmer_id': farmer_id,
            'records': serializer.data
        })
        
    else:
        return Response({'detail': 'Invalid report_type.'}, status=status.HTTP_400_BAD_REQUEST)


class QualityRecordViewSet(viewsets.ModelViewSet):
    permission_classes = (IsAuthenticated,)
    serializer_class = QualityRecordSerializer
    
    def get_queryset(self):
        user = self.request.user
        try:
            profile = user.profile
            if profile.role == 'farmer':
                queryset = QualityRecord.objects.filter(milk_collection__farmer=user)
            else:
                queryset = QualityRecord.objects.filter(milk_collection__collected_by=user)
        except Profile.DoesNotExist:
            queryset = QualityRecord.objects.all()
            
        # Filters
        date_param = self.request.query_params.get('date')
        if date_param:
            queryset = queryset.filter(milk_collection__date=date_param)
            
        # Filter by farmer
        farmer_param = self.request.query_params.get('farmer')
        if farmer_param:
            queryset = queryset.filter(milk_collection__farmer_id=farmer_param)
            
        return queryset.order_by('-recorded_date')
        
    def perform_update(self, serializer):
        quality = serializer.save()
        # Sync back to MilkCollection
        collection = quality.milk_collection
        collection.fat = quality.fat_percentage
        collection.snf = quality.snf_percentage
        collection.save()
        
    def perform_destroy(self, instance):
        collection = instance.milk_collection
        instance.delete()
        collection.delete()


class PaymentViewSet(viewsets.ModelViewSet):
    permission_classes = (IsAuthenticated,)
    serializer_class = PaymentSerializer
    
    def get_queryset(self):
        user = self.request.user
        try:
            profile = user.profile
            if profile.role == 'farmer':
                queryset = Payment.objects.filter(farmer=user)
            else:
                queryset = Payment.objects.filter(dairy_operator=user)
        except Profile.DoesNotExist:
            queryset = Payment.objects.all()
            
        # Filters
        date_param = self.request.query_params.get('date')
        if date_param:
            queryset = queryset.filter(payment_date=date_param)
            
        # Filter by farmer
        farmer_param = self.request.query_params.get('farmer')
        if farmer_param:
            queryset = queryset.filter(farmer_id=farmer_param)
            
        # Filter by status
        status_param = self.request.query_params.get('status')
        if status_param:
            queryset = queryset.filter(payment_status=status_param)
            
        return queryset.order_by('-payment_time')
        
    def perform_create(self, serializer):
        payment = serializer.save(dairy_operator=self.request.user)
        
        # Trigger SMS Notification to farmer
        farmer = payment.farmer
        phone = farmer.profile.phone
        if phone and payment.payment_status == 'paid':
            msg = f"Dear {farmer.get_full_name() or farmer.username}, payment of Rs. {payment.paid_amount:.2f} processed via {payment.get_payment_method_display()} on {payment.payment_date}. Deductions: Rs. {payment.deductions:.2f}. Remaining balance: Rs. {payment.pending_amount:.2f}."
            try:
                send_sparrow_sms(phone, msg)
            except Exception as e:
                logger.error(f"Failed to send payment SMS: {e}")


class FarmerPaymentSummaryView(APIView):
    permission_classes = (IsAuthenticated,)
    
    def get(self, request):
        user = request.user
        
        total_earned = MilkCollection.objects.filter(farmer=user).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        total_paid = Payment.objects.filter(farmer=user, payment_status='paid').aggregate(total=Sum('paid_amount'))['total'] or Decimal('0.00')
        total_deductions = Payment.objects.filter(farmer=user, payment_status='paid').aggregate(total=Sum('deductions'))['total'] or Decimal('0.00')
        
        pending_balance = total_earned - total_paid - total_deductions
        if pending_balance < 0:
            pending_balance = Decimal('0.00')
            
        return Response({
            'total_earned': float(total_earned),
            'total_paid': float(total_paid),
            'pending_balance': float(pending_balance)
        })

class FarmerBankDetailsView(APIView):
    permission_classes = (IsAuthenticated,)
    
    def get(self, request):
        details = request.user.bank_details.all()
        from .serializers import FarmerBankDetailsSerializer
        serializer = FarmerBankDetailsSerializer(details, many=True)
        return Response(serializer.data)
            
    def post(self, request):
        if request.user.bank_details.count() >= 3:
            return Response({'detail': 'Maximum 3 bank accounts allowed (1 primary, 2 secondary).'}, status=status.HTTP_400_BAD_REQUEST)
            
        from .serializers import FarmerBankDetailsSerializer
        serializer = FarmerBankDetailsSerializer(data=request.data)
        if serializer.is_valid():
            is_primary_req = request.data.get('is_primary')
            is_primary = is_primary_req == 'true' or is_primary_req is True
            if request.user.bank_details.count() == 0:
                is_primary = True
                
            if is_primary:
                request.user.bank_details.update(is_primary=False)
                
            serializer.save(farmer=request.user, is_primary=is_primary)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class FarmerBankDetailsUpdateView(APIView):
    permission_classes = (IsAuthenticated,)
    
    def put(self, request, pk):
        try:
            details = request.user.bank_details.get(pk=pk)
        except FarmerBankDetails.DoesNotExist:
            return Response({'detail': 'Bank details not found.'}, status=status.HTTP_404_NOT_FOUND)
            
        from .serializers import FarmerBankDetailsSerializer
        serializer = FarmerBankDetailsSerializer(details, data=request.data, partial=True)
        if serializer.is_valid():
            is_primary_req = request.data.get('is_primary')
            if is_primary_req == 'true' or is_primary_req is True:
                request.user.bank_details.exclude(pk=pk).update(is_primary=False)
                serializer.save(is_primary=True)
            else:
                serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
    def delete(self, request, pk):
        try:
            details = request.user.bank_details.get(pk=pk)
            was_primary = details.is_primary
            details.delete()
            if was_primary and request.user.bank_details.exists():
                first_account = request.user.bank_details.first()
                first_account.is_primary = True
                first_account.save()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except FarmerBankDetails.DoesNotExist:
            return Response({'detail': 'Bank details not found.'}, status=status.HTTP_404_NOT_FOUND)

class RequestPaymentView(APIView):
    permission_classes = (IsAuthenticated,)
    
    def post(self, request):
        amount = request.data.get('amount')
        remarks = request.data.get('remarks', '')
        
        try:
            amount = Decimal(str(amount)) if amount else None
        except:
            return Response({'detail': 'Invalid amount'}, status=status.HTTP_400_BAD_REQUEST)
            
        from .models import PaymentRequest
        from .serializers import PaymentRequestSerializer
        
        pr = PaymentRequest.objects.create(
            farmer=request.user,
            amount_requested=amount,
            remarks=remarks
        )
        serializer = PaymentRequestSerializer(pr)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
