from dj_rest_auth.registration.serializers import RegisterSerializer as BaseRegisterSerializer
from rest_framework import serializers


class RegisterSerializer(BaseRegisterSerializer):
    """Extend le serializer d'inscription pour demander prénom et nom."""
    first_name = serializers.CharField(required=True, max_length=150)
    last_name  = serializers.CharField(required=True, max_length=150)

    def get_cleaned_data(self):
        data = super().get_cleaned_data()
        data['first_name'] = self.validated_data.get('first_name', '')
        data['last_name']  = self.validated_data.get('last_name', '')
        return data

    def save(self, request):
        user = super().save(request)
        user.first_name = self.validated_data.get('first_name', '')
        user.last_name  = self.validated_data.get('last_name', '')
        user.save()
        return user
