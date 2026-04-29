from rest_framework.throttling import AnonRateThrottle


class LoginRateThrottle(AnonRateThrottle):
    """5 tentatives de login par minute par IP — protège contre le brute-force."""
    scope = 'login'
