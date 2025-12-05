from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse


class RoleRequiredMiddleware:
    """Controla el acceso según el rol almacenado en la sesión."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.allowed_for_all = {
            reverse("index"),
            reverse("login"),
            reverse("usuariosapp:logout"),
            reverse("usuariosapp:solicitar_recuperacion"),
            reverse("usuariosapp:verificar_codigo"),
        }
        self.allowed_prefixes = (
            "/static/",
            "/admin/",
        )

    def __call__(self, request):
        path = request.path
        if path.startswith(self.allowed_prefixes) or path in self.allowed_for_all:
            return self.get_response(request)

        user_role = request.session.get("user_role")
        if not user_role:
            return redirect("login")

        if user_role == "admin":
            return self.get_response(request)

        if user_role == "contador":
            if path.startswith("/dashboard/") or path.startswith("/facturacion/"):
                return self.get_response(request)
            messages.warning(
                request,
                "No tienes permisos para acceder a esta sección."
            )
            return redirect("dashboard")

        messages.error(request, "Rol no reconocido, inicia sesión nuevamente.")
        return redirect("login")