import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='MilkCollection',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(auto_now_add=True)),
                ('session', models.CharField(choices=[('morning', 'Morning'), ('evening', 'Evening')], max_length=10)),
                ('quantity', models.DecimalField(decimal_places=2, help_text='Quantity in Litres', max_digits=8)),
                ('fat', models.DecimalField(decimal_places=2, help_text='Fat percentage', max_digits=4)),
                ('snf', models.DecimalField(decimal_places=2, help_text='SNF (Solids-Not-Fat) percentage', max_digits=4)),
                ('rate', models.DecimalField(blank=True, decimal_places=2, help_text='Rate per Litre', max_digits=6)),
                ('amount', models.DecimalField(blank=True, decimal_places=2, help_text='Total Payout Amount', max_digits=10)),
                ('timestamp', models.DateTimeField(auto_now_add=True)),
                ('collected_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='collections_registered', to=settings.AUTH_USER_MODEL)),
                ('farmer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='milk_collections', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='Profile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role', models.CharField(choices=[('agent', 'Agent'), ('farmer', 'Farmer')], default='farmer', max_length=10)),
                ('farmer_code', models.CharField(blank=True, max_length=20, null=True, unique=True)),
                ('phone', models.CharField(blank=True, max_length=15)),
                ('address', models.CharField(blank=True, max_length=255)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='profile', to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
