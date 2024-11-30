# Generated by Django 5.1.1 on 2024-11-30 17:49

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("music", "0003_alter_spotifyuser_display_name_and_more"),
        ("spotify", "0003_alter_spotifytoken_access_token_and_more"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="spotifytoken",
            name="spotify_user_id",
        ),
        migrations.RemoveField(
            model_name="spotifytoken",
            name="user",
        ),
        migrations.AddField(
            model_name="spotifytoken",
            name="spotify_user",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="spotifytoken",
                to="music.spotifyuser",
            ),
        ),
    ]
