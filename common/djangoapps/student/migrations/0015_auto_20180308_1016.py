# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('student', '0014_manualenrollmentaudit_role'),
    ]

    operations = [
        migrations.AlterField(
            model_name='manualenrollmentaudit',
            name='role',
            field=models.CharField(max_length=64, null=True, blank=True),
        ),
    ]
