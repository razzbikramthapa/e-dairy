from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
import random
from decimal import Decimal
from api.models import Profile, MilkCollection

class Command(BaseCommand):
    help = 'Seeds the database with test agents, farmers, and milk collection records.'

    def handle(self, *args, **options):
        self.stdout.write('Seeding database...')
        
        # 1. Clear existing data to prevent duplicates
        self.stdout.write('Clearing existing records...')
        MilkCollection.objects.all().delete()
        Profile.objects.all().delete()
        User.objects.all().delete()

        # 2. Create Agent User
        self.stdout.write('Creating agent account...')
        agent_user = User.objects.create_user(
            username='agent_dev',
            password='Password@123',
            email='agent@edairy.com',
            first_name='Dairy',
            last_name='Agent'
        )
        Profile.objects.create(
            user=agent_user,
            role='agent',
            phone='9801234567',
            address='Dairy Head Office, KTM'
        )

        # 3. Create Farmers
        self.stdout.write('Creating farmer accounts...')
        farmers_data = [
            {'username': 'farmer_dev', 'first_name': 'Ram', 'last_name': 'Dev', 'code': 'F1001', 'address': 'Farm Area A'},
            {'username': 'farmer_sita', 'first_name': 'Sita', 'last_name': 'Shah', 'code': 'F1002', 'address': 'Farm Area B'},
            {'username': 'farmer_hari', 'first_name': 'Hari', 'last_name': 'Lal', 'code': 'F1003', 'address': 'Farm Area C'},
            {'username': 'farmer_gopal', 'first_name': 'Gopal', 'last_name': 'Prasad', 'code': 'F1004', 'address': 'Farm Area D'},
        ]
        
        farmers = []
        for f_data in farmers_data:
            user = User.objects.create_user(
                username=f_data['username'],
                password='Password@123',
                email=f"{f_data['username']}@edairy.com",
                first_name=f_data['first_name'],
                last_name=f_data['last_name']
            )
            profile = Profile.objects.create(
                user=user,
                role='farmer',
                farmer_code=f_data['code'],
                phone='9845551234',
                address=f_data['address']
            )
            farmers.append(user)

        # 4. Create Milk Collections for the last 7 days
        self.stdout.write('Creating 15+ milk collections...')
        today = timezone.localdate()
        sessions = ['morning', 'evening']

        # Generate entries for each farmer over the past week
        count = 0
        for i in range(7):
            date_point = today - timedelta(days=i)
            # Pick a subset of farmers to make collections on this day
            active_farmers_today = random.sample(farmers, k=random.randint(2, 4))
            
            for farmer in active_farmers_today:
                for session in sessions:
                    # Randomize session data
                    quantity = Decimal(str(round(random.uniform(12.5, 45.0), 2)))
                    fat = Decimal(str(round(random.uniform(3.8, 5.8), 2)))
                    snf = Decimal(str(round(random.uniform(7.8, 9.2), 2)))
                    
                    collection = MilkCollection(
                        farmer=farmer,
                        collected_by=agent_user,
                        session=session,
                        quantity=quantity,
                        fat=fat,
                        snf=snf
                    )
                    # Force set date since save override defaults to auto_now_add
                    collection.save()
                    
                    # Hack: Override the auto-set date which defaults to today due to auto_now_add=True
                    MilkCollection.objects.filter(id=collection.id).update(date=date_point)
                    count += 1

        self.stdout.write(self.style.SUCCESS(f'Successfully seeded {count} milk records, 1 agent and {len(farmers)} farmers!'))
