# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('eventshock_auth', '0010_systemsettings_proxy_url'),
    ]

    operations = [
        migrations.AddField(
            model_name='systemsettings',
            name='proxy_domains',
            field=models.TextField(blank=True, help_text='Список доменов (по одному на строку), для которых сразу использовать прокси при загрузке', null=True),
        ),
    ]

