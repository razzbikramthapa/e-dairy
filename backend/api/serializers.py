from rest_framework import serializers
from django.contrib.auth.models import User
from django.db import transaction
from django.contrib.auth import authenticate
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .models import Profile, MilkCollection, LinkedFarmer, FarmerBankDetails, Payment, QualityRecord, PaymentRequest, Notification
from .twilio_helper import verify_otp

class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = ('role', 'farmer_code', 'farm_name', 'phone', 'address')

class UserSerializer(serializers.ModelSerializer):
    profile = ProfileSerializer(read_only=True)
    
    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'first_name', 'last_name', 'profile')

class UserRegisterSerializer(serializers.ModelSerializer):
    role = serializers.ChoiceField(choices=Profile.ROLE_CHOICES, write_only=True)
    farmer_code = serializers.CharField(max_length=20, required=False, allow_blank=True, allow_null=True, write_only=True)
    farm_name = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True, write_only=True)
    phone = serializers.CharField(max_length=15, required=False, allow_blank=True, allow_null=True, write_only=True)
    address = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True, write_only=True)
    password = serializers.CharField(write_only=True, style={'input_type': 'password'})

    class Meta:
        model = User
        fields = ('username', 'password', 'email', 'first_name', 'last_name', 'role', 'farmer_code', 'farm_name', 'phone', 'address')

    def validate(self, attrs):
        phone = attrs.get('phone', '').strip()
        otp = attrs.get('password', '').strip()
        
        if not phone:
            raise serializers.ValidationError({"phone": "Phone number is required."})
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
    
    class Meta:
        model = MilkCollection
        fields = ('id', 'farmer', 'farmer_code', 'farmer_name', 'date', 'session', 'quantity', 'fat', 'snf', 'remarks', 'rate', 'amount', 'collected_by', 'collected_by_name')
        read_only_fields = ('collected_by', 'rate', 'amount')


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
    
    class Meta:
        model = PaymentRequest
        fields = ('id', 'farmer', 'farmer_name', 'amount_requested', 'request_date', 'status', 'remarks')
        read_only_fields = ('farmer', 'request_date', 'status')


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ('id', 'notification_type', 'title', 'message', 'is_read', 'related_farmer_id', 'created_at')
        read_only_fields = ('id', 'notification_type', 'title', 'message', 'related_farmer_id', 'created_at')