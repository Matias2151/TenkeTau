# ProyectoApp/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.db.models import Q
from django.db import transaction
from django.http import JsonResponse
from .models import Proyecto
from EmpresaPersonaApp.models import EmpresaPersona
from .forms import ProyectoForm


def es_ajax(request):
    """Detecta si la solicitud es AJAX (case-insensitive y compatible con fetch)."""
    return request.headers.get("x-requested-with", "").lower() == "xmlhttprequest"


# 🔹 LISTAR PROYECTOS
def lista_proyectos(request):
    """Vista principal: lista los proyectos y prepara el formulario para el modal."""
    proyectos = Proyecto.objects.all().order_by("-proye_idt")

    # 🔍 Clientes activos que sean cliente o ambos
    clientes = EmpresaPersona.objects.filter(
        emppe_est=True
    ).filter(
        Q(emppe_sit="cliente") | Q(emppe_sit="ambos")
    ).order_by("emppe_nom")

    contexto = {
        "proyectos": proyectos,
        "form": ProyectoForm(),
        "clientes": clientes,
    }
    return render(request, "proyecto/proyecto.html", contexto)


# 🔹 CREAR PROYECTO
@transaction.atomic
def crear_proyecto(request):
    """Crea un nuevo proyecto (maneja AJAX y modo normal)."""
    if request.method != "POST":
        return JsonResponse(
            {"success": False, "errors": {"__all__": ["Método no permitido."]}},
            status=405,
        )

    form = ProyectoForm(request.POST)
    if not form.is_valid():
        if es_ajax(request):
            return JsonResponse({"success": False, "errors": form.errors})
        messages.error(request, "⚠️ Corrige los errores del formulario.")
        return redirect("proyectoapp:lista_proyectos")

    proyecto = form.save(commit=False)
    proyecto.save()

    # ✅ Si es AJAX
    if es_ajax(request):
        return JsonResponse({
            "success": True,
            "msg": "Proyecto creado correctamente.",
            "created": {
                "id": proyecto.proye_idt,
                "desc": proyecto.proye_desc,
                "estado": proyecto.proye_estado,
                "fecha_ter": proyecto.proye_fecha_ter.strftime("%d-%m-%Y") if proyecto.proye_fecha_ter else "—",
            }
        })

    # Fallback tradicional
    messages.success(request, "✅ Proyecto creado correctamente.")
    return redirect("proyectoapp:lista_proyectos")


# 🔹 EDITAR PROYECTO
@transaction.atomic
def editar_proyecto(request, pk):
    """Edita un proyecto existente (maneja AJAX y fallback normal)."""
    proyecto = get_object_or_404(Proyecto, pk=pk)

    if request.method != "POST":
        return JsonResponse(
            {"success": False, "errors": {"__all__": ["Método no permitido."]}},
            status=405,
        )

    form = ProyectoForm(request.POST, instance=proyecto)
    if not form.is_valid():
        if es_ajax(request):
            return JsonResponse({"success": False, "errors": form.errors})
        messages.error(request, "⚠️ Corrige los errores del formulario.")
        return redirect("proyectoapp:lista_proyectos")

    form.save()

    # ✅ AJAX → JSON
    if es_ajax(request):
        return JsonResponse({
            "success": True,
            "msg": "Proyecto actualizado correctamente.",
            "updated": {
                "id": proyecto.proye_idt,
                "desc": proyecto.proye_desc,
                "estado": proyecto.proye_estado,
                "fecha_ter": proyecto.proye_fecha_ter.strftime("%d-%m-%Y") if proyecto.proye_fecha_ter else "—",
            }
        })

    # Modo normal
    messages.success(request, "✅ Proyecto actualizado correctamente.")
    return redirect("proyectoapp:lista_proyectos")


# 🔹 ELIMINAR PROYECTO
@transaction.atomic
def eliminar_proyecto(request, pk):
    """Elimina un proyecto existente (confirmación modal y AJAX)."""
    if request.method != "POST":
        msg = {"__all__": ["Método no permitido."]}
        if es_ajax(request):
            return JsonResponse({"success": False, "errors": msg}, status=405)
        messages.error(request, "Método no permitido para esta ruta.")
        return redirect("proyectoapp:lista_proyectos")

    proyecto = get_object_or_404(Proyecto, pk=pk)
    proyecto.delete()

    if es_ajax(request):
        return JsonResponse({"success": True, "msg": "🗑️ Proyecto eliminado correctamente."})

    messages.success(request, "🗑️ Proyecto eliminado correctamente.")
    return redirect("proyectoapp:lista_proyectos")


# 🔹 DETALLE OPCIONAL
def detalle_proyecto(request, pk):
    """Muestra detalles completos de un proyecto."""
    proyecto = get_object_or_404(Proyecto, pk=pk)
    clientes = EmpresaPersona.objects.filter(
        emppe_est=True
    ).filter(
        Q(emppe_sit="cliente") | Q(emppe_sit="ambos")
    ).order_by("emppe_nom")

    return render(
        request,
        "proyecto/detalle_proyecto.html",
        {"proyecto": proyecto, "clientes": clientes},
    )
