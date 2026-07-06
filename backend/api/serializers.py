from rest_framework import serializers
from django.contrib.auth.models import User
from django.db import transaction
from django.contrib.auth import authenticate
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .models import Profile, MilkCollection
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
    farm_name = serializers.CharField(max_length=255, required=False, allow_blank=True, write_only=True)
    phone = serializers.CharField(max_length=15, required=False, allow_blank=True, write_only=True)
    address = serializers.CharField(max_length=255, required=False, allow_blank=True, write_only=True)
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
    farmer_name = serializers.CharField(source='farmer.get_full_name', read_only=True)
    farmer_username = serializers.CharField(source='farmer.username', read_only=True)
    farmer_code = serializers.CharField(source='farmer.profile.farmer_code', read_only=True)
    agent_name = serializers.CharField(source='collected_by.get_full_name', read_only=True)

    class Meta:
        model = MilkCollection
        fields = (
            'id', 'farmer', 'farmer_name', 'farmer_username', 'farmer_code',
            'collected_by', 'agent_name', 'date', 'session',
            'quantity', 'fat', 'snf', 'rate', 'amount', 'timestamp'
        )
        read_only_fields = ('id', 'collected_by', 'rate', 'amount', 'date', 'timestamp')

    def validate_farmer(self, value):
        # Ensure the selected user is indeed a farmer
        try:
            if value.profile.role != 'farmer':
                raise serializers.ValidationError("Selected user is not registered as a Farmer.")
        except Profile.DoesNotExist:
            raise serializers.ValidationError("Selected user does not have a profile.")
        return value
