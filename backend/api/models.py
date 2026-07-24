from django.db import models
from django.contrib.auth.models import User
from decimal import Decimal
from django.utils import timezone

class Profile(models.Model):
    ROLE_CHOICES = (
        ('agent', 'Agent'),
        ('farmer', 'Farmer'),
    )
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='farmer')
    farmer_code = models.CharField(max_length=20, unique=True, null=True, blank=True)
    farm_name = models.CharField(max_length=255, blank=True, help_text="Farm name (farmers only)")
    phone = models.CharField(max_length=10, blank=True)
    address = models.CharField(max_length=255, blank=True)

    def save(self, *args, **kwargs):
        if self.role == 'farmer' and not self.farmer_code:
            profiles = Profile.objects.filter(role='farmer').exclude(farmer_code__isnull=True).exclude(farmer_code='')
            max_code = 0
            for p in profiles:
                code_str = p.farmer_code
                if code_str.startswith('F') and code_str[1:].isdigit():
                    max_code = max(max_code, int(code_str[1:]))
                elif code_str.isdigit():
                    max_code = max(max_code, int(code_str))
            self.farmer_code = f"F{max_code + 1}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.username} ({self.get_role_display()})"


class DairyOperator(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='dairy_operator')
    dairy_name = models.CharField(max_length=255)
    registration_no = models.CharField(max_length=100)
    phone = models.CharField(max_length=15, unique=True)
    address = models.CharField(max_length=255)
    logo = models.ImageField(upload_to='dairy_logos/', blank=True, null=True)
    
    def __str__(self):
        return self.dairy_name


class LinkedFarmer(models.Model):
    dairy_operator = models.ForeignKey(User, on_delete=models.CASCADE, related_name='linked_farmers')
    farmer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='dairy_links')
    linked_date = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        unique_together = ('dairy_operator', 'farmer')
    
    def __str__(self):
        try:
            code = self.farmer.profile.farmer_code or self.farmer.username
        except AttributeError:
            code = self.farmer.username
            
        try:
            dairy_name = self.dairy_operator.dairy_operator.dairy_name
        except AttributeError:
            dairy_name = "System Dairy"
            
        return f"{code} -> {dairy_name}"


class FarmerBankDetails(models.Model):
    farmer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bank_details')
    bank_name = models.CharField(max_length=255)
    account_holder_name = models.CharField(max_length=255)
    account_number = models.CharField(max_length=50, unique=True)
    qr_code = models.ImageField(upload_to='payment_qrs/', blank=True, null=True)
    is_primary = models.BooleanField(default=False)
    
    def __str__(self):
        return f"{self.account_holder_name} - {self.account_number}"


class MilkCollection(models.Model):
    SHIFT_CHOICES = (
        ('morning', 'Morning'),
        ('evening', 'Evening'),
    )
    
    farmer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='milk_collections')
    collected_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name='collections_registered')
    date = models.DateField(default=timezone.localdate)
    session = models.CharField(max_length=10, choices=SHIFT_CHOICES)
    quantity = models.DecimalField(max_digits=8, decimal_places=2, help_text="Quantity in Litres")
    fat = models.DecimalField(max_digits=4, decimal_places=2)
    snf = models.DecimalField(max_digits=4, decimal_places=2)
    remarks = models.TextField(blank=True, null=True)
    rate = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('0.00'))
    amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    def save(self, *args, **kwargs):
        # Calculate payout rate using standard formula: rate = (fat * 6) + (snf * 4)
        if self.fat and self.snf:
            self.rate = Decimal(str(self.fat)) * Decimal('6.0') + Decimal(str(self.snf)) * Decimal('4.0')
        else:
            self.rate = Decimal('50.00')
            
        # Calculate amount
        if self.quantity:
            self.amount = Decimal(str(self.quantity)) * self.rate
            
        super().save(*args, **kwargs)
        
        # Auto-create or sync QualityRecord
        QualityRecord.objects.update_or_create(
            milk_collection=self,
            defaults={
                'fat_percentage': self.fat,
                'snf_percentage': self.snf
            }
        )
    
    def __str__(self):
        return f"{self.farmer.username} - {self.date} ({self.session})"


class Payment(models.Model):
    PAYMENT_STATUS = (
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('failed', 'Failed'),
    )
    PAYMENT_METHOD = (
        ('cash', 'Cash'),
        ('bank_transfer', 'Bank Transfer'),
        ('wallet', 'Demo Wallet'),
    )
    
    farmer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payments')
    dairy_operator = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payments_made')
    payment_date = models.DateField(default=timezone.localdate)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    paid_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    pending_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    deductions = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='pending')
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD, default='cash')
    transaction_reference = models.CharField(max_length=100, blank=True, null=True)
    payment_time = models.DateTimeField(auto_now_add=True)
    
    def save(self, *args, **kwargs):
        # Calculate pending amount
        self.pending_amount = Decimal(str(self.total_amount)) - Decimal(str(self.paid_amount)) - Decimal(str(self.deductions))
        if self.pending_amount < 0:
            self.pending_amount = Decimal('0.00')
        super().save(*args, **kwargs)
        
    def __str__(self):
        return f"Payment - {self.farmer.username} - {self.payment_date}"


class QualityRecord(models.Model):
    milk_collection = models.OneToOneField(MilkCollection, on_delete=models.CASCADE, related_name='quality_record')
    fat_percentage = models.DecimalField(max_digits=4, decimal_places=2)
    snf_percentage = models.DecimalField(max_digits=4, decimal_places=2)
    recorded_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        try:
            username = self.milk_collection.farmer.username
        except AttributeError:
            username = "Unknown"
        return f"Quality - {username} - FAT:{self.fat_percentage}% SNF:{self.snf_percentage}%"


class PaymentRequest(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    )
    farmer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payment_requests')
    amount_requested = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    request_date = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    remarks = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.farmer.username} - {self.status} - {self.request_date}"