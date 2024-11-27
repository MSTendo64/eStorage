from django.apps import AppConfig


class EventshockAuthConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'eventshock_auth'

    def ready(self):
        import eventshock_auth.signals
