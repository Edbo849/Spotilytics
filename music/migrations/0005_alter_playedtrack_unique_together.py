# Generated by Django 5.1.1 on 2024-12-01 17:45

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("music", "0004_remove_spotifyuser_id_and_more"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="playedtrack",
            unique_together={("user", "track_id", "played_at")},
        ),
    ]
