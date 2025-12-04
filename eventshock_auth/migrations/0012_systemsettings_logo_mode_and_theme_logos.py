from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('eventshock_auth', '0011_systemsettings_proxy_domains'),
    ]

    operations = [
        migrations.AddField(
            model_name='systemsettings',
            name='logo_dark',
            field=models.ImageField(blank=True, null=True, upload_to='system/logo/'),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='logo_light',
            field=models.ImageField(blank=True, null=True, upload_to='system/logo/'),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='logo_mode',
            field=models.CharField(choices=[('single', 'Общий логотип'), ('theme', 'По выбору темы')], default='single', max_length=16),
        ),
    ]

