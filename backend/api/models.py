from django.db import models
from django.contrib.auth.models import User
from decimal import Decimal

class Profile(models.Model):
    ROLE_CHOICES = (
        ('agent', 'Agent'),
        ('farmer', 'Farmer'),
    )
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='farmer')
    farmer_code = models.CharField(max_length=20, unique=True, null=True, blank=True)
    farm_name = models.CharField(max_length=255, blank=True, help_text="Farm name (farmers only)")
    phone = models.CharField(max_length=15, blank=True)
    address = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"{self.user.username} ({self.get_role_display()})"

class MilkCollection(models.Model):
    SESSION_CHOICES = (
        ('morning', 'Morning'),
        ('evening', 'Evening'),
    )
    farmer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='milk_collections')
    collected_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='collections_registered')
    date = models.DateField(auto_now_add=True)
    session = models.CharField(max_length=10, choices=SESSION_CHOICES)
    quantity = models.DecimalField(max_digits=8, decimal_places=2, help_text="Quantity in Litres")
    fat = models.DecimalField(max_digits=4, decimal_places=2, help_text="Fat percentage")
    snf = models.DecimalField(max_digits=4, decimal_places=2, help_text="SNF (Solids-Not-Fat) percentage")
    rate = models.DecimalField(max_digits=6, decimal_places=2, blank=True, help_text="Rate per Litre")
    amount = models.DecimalField(max_digits=10, decimal_places=2, blank=True, help_text="Total Payout Amount")
    timestamp = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        # Automatically calculate rate and total amount if not specified
        # Standard pricing logic: base fat multiplier + SNF multiplier
        if not self.rate:
            # Let's say base fat coefficient is 8.5 and SNF is 4.5
            fat_val = Decimal(str(self.fat))
            snf_val = Decimal(str(self.snf))
            self.rate = (fat_val * Decimal('8.5')) + (snf_val * Decimal('4.5'))
        
        if not self.amount:
            self.amount = Decimal(str(self.quantity)) * Decimal(str(self.rate))
            
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Coll #{self.id} - {self.farmer.username} ({self.quantity}L)"
