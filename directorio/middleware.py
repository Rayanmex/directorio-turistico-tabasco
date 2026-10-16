"""
Middleware que exige login para acceder a cualquier URL del proyecto.
Las URLs exentas están en LOGIN_EXEMPT_URLS en settings.py.
"""
import re
from django.conf import settings
from django.shortcuts import redirect


class LoginRequiredMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # 1. Si el usuario ya está logueado → dejar pasar
        if request.user.is_authenticated:
            return self.get_response(request)

        # 2. Verificar si la URL está exenta
        path = request.path_info
        for pattern in getattr(settings, 'LOGIN_EXEMPT_URLS', []):
            if re.match(pattern, path):
                return self.get_response(request)

        # 3. Redirigir al login guardando la URL original
        login_url = getattr(settings, 'LOGIN_URL', '/login/')
        if not login_url.endswith('/'):
            login_url += '/'
        return redirect(f'{login_url}?next={path}')