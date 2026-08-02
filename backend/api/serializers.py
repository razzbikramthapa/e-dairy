import re

from rest_framework import serializers
from django.contrib.auth.models import User
from django.db import transaction
from django.contrib.auth import authenticate
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .models import Profile, DairyOperator, MilkCollection, LinkedFarmer, FarmerBankDetails, Payment, QualityRecord, PaymentRequest, Notification
from .twilio_helper import verify_otp

class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = ('role', 'farmer_code', 'farm_name', 'phone', 'address')

class UserSerializer(serializers.ModelSerializer):
    profile = ProfileSerializer(read_only=True)
    linked_collection_center = serializers.SerializerMethodField()
    dairy_name = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'first_name', 'last_name', 'profile', 'linked_collection_center', 'dairy_name')

    def get_dairy_name(self, obj):
        try:
            if hasattr(obj, 'dairy_operator'):
                return obj.dairy_operator.dairy_name
        except Exception:
            pass
        return None

    def get_linked_collection_center(self, obj):
        try:
            if hasattr(obj, 'profile') and obj.profile.role == 'farmer':
                linked_qs = obj.dairy_links.filter(is_active=True)
                centers = []
                for linked in linked_qs:
                    try:
                        centers.append(linked.dairy_operator.dairy_operator.dairy_name)
                    except Exception:
                        name = linked.dairy_operator.get_full_name()
                        centers.append(name if name else linked.dairy_operator.username)
                centers.sort(key=str.lower)
                return centers if centers else None
        except Exception:
            pass
        return None

class UserRegisterSerializer(serializers.ModelSerializer):
    role = serializers.ChoiceField(choices=Profile.ROLE_CHOICES, write_only=True)
    farmer_code = serializers.CharField(max_length=20, required=False, allow_blank=True, allow_null=True, write_only=True)
    farm_name = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True, write_only=True)
    phone = serializers.CharField(max_length=15, required=False, allow_blank=True, allow_null=True, write_only=True)
    address = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True, write_only=True)
    password = serializers.CharField(write_only=True, style={'input_type': 'password'})
    registration_no = serializers.CharField(max_length=100, required=False, allow_blank=True, allow_null=True, write_only=True)

    class Meta:
        model = User
        fields = ('username', 'password', 'email', 'first_name', 'last_name', 'role', 'farmer_code', 'farm_name', 'phone', 'address', 'registration_no')

    def validate(self, attrs):
        phone = attrs.get('phone', '').strip()
        otp = attrs.get('password', '').strip()
        
        if not phone:
            raise serializers.ValidationError({"phone": "Phone number is required."})
        if not re.fullmatch(r'[0-9]{10}', phone):
            raise serializers.ValidationError({"phone": "Phone number must be exactly 10 digits."})
        if not otp:
            raise serializers.ValidationError({"password": "Verification code (OTP) is required."})
            
        # Verify the OTP using twilio helper
        if not verify_otp(phone, otp):
            raise serializers.ValidationError({"password": "Invalid or expired verification code (OTP)."})
            
        return attrs

    def create(self, validated_data):
        role = validated_data.pop('role')
        farmer_code = validated_data.pop('farmer_code', None)
        if farmer_code:
            farmer_code = farmer_code.strip()
        if not farmer_code:
            farmer_code = None
        farm_name = validated_data.pop('farm_name', '')
        phone = validated_data.pop('phone', '')
        address = validated_data.pop('address', '')
        registration_no = validated_data.pop('registration_no', '')
        password = validated_data.pop('password')

        # Auto-generate farmer code if not provided
        if role == 'farmer' and not farmer_code:
            import random
            while True:
                farmer_code = f"F{random.randint(1000, 9999)}"
                if not Profile.objects.filter(farmer_code=farmer_code).exists():
                    break

        with transaction.atomic():
            user = User.objects.create_user(
                username=validated_data['username'],
                email=validated_data.get('email', ''),
                first_name=validated_data.get('first_name', ''),
                last_name=validated_data.get('last_name', ''),
                password=password
            )
            # Create associated profile
            Profile.objects.create(
                user=user,
                role=role,
                farmer_code=farmer_code if role == 'farmer' else None,
                farm_name=farm_name if role == 'farmer' else '',
                phone=phone,
                address=address
            )
            # Create DairyOperator for agent role
            if role == 'agent':
                dairy_name = validated_data.get('first_name', '') or 'My Collection Centre'
                DairyOperator.objects.create(
                    user=user,
                    dairy_name=dairy_name,
                    registration_no=registration_no or '',
                    phone=phone,
                    address=address
                )
        return user


class OTPTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        username = attrs.get(self.username_field)
        password = attrs.get("password")

        # 1. Try standard django authenticate first (checks password hash)
        user = authenticate(username=username, password=password)

        if user is None:
            # 2. If it fails, check if the password is a valid Twilio OTP
            user_obj = User.objects.filter(username=username).first()
            if user_obj and verify_otp(username, password):
                # OTP is approved! Update user password to this OTP
                user_obj.set_password(password)
                user_obj.save()
                user = user_obj

        if user is None:
            raise serializers.ValidationError(
                {"detail": "No active account found with the given credentials"}
            )
            
        if not user.is_active:
            raise serializers.ValidationError(
                {"detail": "This account is inactive."}
            )

        self.user = user
        
        refresh = self.get_token(self.user)
        data = {
            "refresh": str(refresh),
            "access": str(refresh.access_token),
        }
        return data


class MilkCollectionSerializer(serializers.ModelSerializer):
    farmer_code = serializers.CharField(source='farmer.profile.farmer_code', read_only=True)
    farmer_name = serializers.CharField(source='farmer.get_full_name', read_only=True)
    collected_by_name = serializers.CharField(source='collected_by.get_full_name', read_only=True)
    collection_centre = serializers.SerializerMethodField()
    
    class Meta:
        model = MilkCollection
        fields = ('id', 'farmer', 'farmer_code', 'farmer_name', 'date', 'session', 'quantity', 'fat', 'snf', 'remarks', 'rate', 'amount', 'collected_by', 'collected_by_name', 'collection_centre')
        read_only_fields = ('collected_by', 'rate', 'amount')

    def get_collection_centre(self, obj):
        if obj.collected_by and hasattr(obj.collected_by, 'dairy_operator'):
            return obj.collected_by.dairy_operator.dairy_name
        
        linked = obj.farmer.dairy_links.first()
        if linked and hasattr(linked.dairy_operator, 'dairy_operator'):
            return linked.dairy_operator.dairy_operator.dairy_name
            
        if obj.collected_by:
            name = obj.collected_by.get_full_name()
            return name if name else obj.collected_by.username
            
        return "System"


class FarmerBankDetailsSerializer(serializers.ModelSerializer):
    wallet_number = serializers.SerializerMethodField()

    class Meta:
        model = FarmerBankDetails
        fields = ('id', 'bank_name', 'account_holder_name', 'account_number', 'qr_code', 'is_primary', 'wallet_number')

    def get_wallet_number(self, obj):
        try:
            return obj.farmer.profile.phone
        except:
            return ""


class LinkedFarmerSerializer(serializers.ModelSerializer):
    farmer_code = serializers.CharField(source='farmer.profile.farmer_code', read_only=True)
    farmer_name = serializers.CharField(source='farmer.get_full_name', read_only=True)
    farmer_phone = serializers.CharField(source='farmer.profile.phone', read_only=True)
    farmer_address = serializers.CharField(source='farmer.profile.address', read_only=True)
    bank_details = serializers.SerializerMethodField()
    
    class Meta:
        model = LinkedFarmer
        fields = ('id', 'farmer', 'farmer_code', 'farmer_name', 'farmer_phone', 'farmer_address', 'bank_details', 'linked_date', 'is_active')

    def get_bank_details(self, obj):
        farmer = obj.farmer
        bd = farmer.bank_details.filter(is_primary=True).first() or farmer.bank_details.first()
        if bd:
            return FarmerBankDetailsSerializer(bd, context=self.context).data
        return None


class PaymentSerializer(serializers.ModelSerializer):
    farmer_code = serializers.CharField(source='farmer.profile.farmer_code', read_only=True)
    farmer_name = serializers.CharField(source='farmer.get_full_name', read_only=True)
    
    class Meta:
        model = Payment
        fields = ('id', 'farmer', 'farmer_code', 'farmer_name', 'payment_date', 'total_amount', 'paid_amount', 'pending_amount', 'deductions', 'payment_status', 'payment_method', 'transaction_reference', 'payment_time')
        read_only_fields = ('pending_amount', 'payment_time')


class QualityRecordSerializer(serializers.ModelSerializer):
    farmer_code = serializers.CharField(source='milk_collection.farmer.profile.farmer_code', read_only=True)
    farmer_name = serializers.CharField(source='milk_collection.farmer.get_full_name', read_only=True)
    date = serializers.DateField(source='milk_collection.date', read_only=True)
    session = serializers.CharField(source='milk_collection.session', read_only=True)
    quantity = serializers.DecimalField(source='milk_collection.quantity', max_digits=8, decimal_places=2, read_only=True)

    class Meta:
        model = QualityRecord
        fields = ('id', 'milk_collection', 'farmer_code', 'farmer_name', 'date', 'session', 'quantity', 'fat_percentage', 'snf_percentage', 'recorded_date', 'updated_date')


class PaymentRequestSerializer(serializers.ModelSerializer):
    farmer_name = serializers.CharField(source='farmer.get_full_name', read_only=True)
    dairy_operator_name = serializers.SerializerMethodField()

    class Meta:
        model = PaymentRequest
        fields = ('id', 'farmer', 'farmer_name', 'dairy_operator', 'dairy_operator_name', 'amount_requested', 'request_date', 'status', 'remarks')
        read_only_fields = ('farmer', 'request_date', 'status')

    def get_dairy_operator_name(self, obj):
        if obj.dairy_operator:
            try:
                return obj.dairy_operator.dairy_operator.dairy_name
            except Exception:
                pass
            return obj.dairy_operator.get_full_name() or obj.dairy_operator.username
        return None


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ('id', 'notification_type', 'title', 'message', 'is_read', 'related_farmer_id', 'created_at')
        read_only_fields = ('id', 'notification_type', 'title', 'message', 'related_farmer_id', 'created_at')