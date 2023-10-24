# Generated by Django 4.1.4 on 2022-12-16 14:00

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0004_orgaccount_is_public'),
    ]

    operations = [
        migrations.AddField(
            model_name='orgaccount',
            name='pcqr_display_age_in_hours',
            field=models.IntegerField(default=72),
        ),
        migrations.AddField(
            model_name='orgaccount',
            name='pcqr_retention_age_in_days',
            field=models.IntegerField(default=14),
        ),
        migrations.AddField(
            model_name='pscmdqueueresult',
            name='expiration',
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
    ]