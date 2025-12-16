# ProyectoApp/views.py
from decimal import ROUND_HALF_UP, Decimal
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from django.db.models import Q, Sum, F
from django.db import transaction
from django.http import JsonResponse
from FacturacionApp.models import Documento, DetalleDoc

from .models import Proyecto
from EmpresaPersonaApp.models import EmpresaPersona
from .forms import ProyectoForm


# Detecta solicitudes AJAX
def es_ajax(request):
    return request.headers.get("x-requested-with", "").lower() == "xmlhttprequest"


# -----------------------------
# Helper para obtener datos del cliente
# -----------------------------
def _cliente_info(proyecto):

    cliente_id = getattr(proyecto, "cliente_id", None)
    cliente_nombre = getattr(proyecto, "cliente_nombre", None)
    cliente_rut = getattr(proyecto, "cliente_rut", None)
    cliente_mail = getattr(proyecto, "cliente_mail", None)
    cliente_fono = getattr(proyecto, "cliente_fono", None)

    cliente_obj = getattr(proyecto, "cliente", None)
    if cliente_obj is None:
        cliente_obj = getattr(proyecto, "emppe", None)

    if cliente_obj:
        cliente_id = cliente_id or getattr(cliente_obj, "emppe_id", None)
        cliente_nombre = cliente_nombre or getattr(cliente_obj, "emppe_nom", None)
        cliente_rut = cliente_rut or getattr(cliente_obj, "emppe_rut", None)
        cliente_mail = cliente_mail or getattr(cliente_obj, "emppe_mail1", None)
        cliente_fono = cliente_fono or getattr(cliente_obj, "emppe_fono1", None)

    return {
        "cliente_id": cliente_id or "",
        "cliente_nombre": cliente_nombre or "Sin asignar",
        "cliente_rut": cliente_rut or "—",
        "cliente_mail": cliente_mail or "—",
        "cliente_fono": cliente_fono or "—",
    }


# -----------------------------
# LISTAR PROYECTOS
# -----------------------------
def lista_proyectos(request):

    proyectos = Proyecto.objects.all().order_by("-proye_idt")

    utilidad_total = 0
    egresos_total = 0

    # Agregamos valores calculados al objeto proyecto
    for p in proyectos:

        documentos = Documento.objects.filter(proyecto=p)

        ingresos = 0
        egresos = 0

        for d in documentos:

            bruto = 0

            for det in d.detalles.all():
                if det.producto:
                    bruto += det.dedoc_cant * det.producto.produ_bruto

            trans = d.transaccion
            if trans:
                if trans.tipo.tipo_id == 1:  # ingreso
                    ingresos += bruto
                elif trans.tipo.tipo_id == 2:  # egreso
                    egresos += bruto

        costo = p.proye_cost or 0
        utilidad = costo + ingresos - egresos

        # Guardar en el objeto (no en BD)
        p.utilidad_calc = utilidad
        p.egresos_calc = egresos

        # Acumulados globales
        utilidad_total += utilidad
        egresos_total += egresos

    clientes = EmpresaPersona.objects.filter(
        emppe_est=True,
        emppe_sit__in=["cliente", "ambos"]
    ).order_by("emppe_nom")

    return render(request, "proyecto/proyecto.html", {
        "proyectos": proyectos,
        "form": ProyectoForm(),
        "clientes": clientes,
        "utilidad_total": utilidad_total,
        "egresos_total": egresos_total,
    })




# -----------------------------
# CREAR PROYECTO
# -----------------------------
@transaction.atomic
def crear_proyecto(request):

    if request.method != "POST":
        msg = {"__all__": ["Método no permitido."]}
        if es_ajax(request):
            return JsonResponse({"success": False, "errors": msg}, status=405)
        messages.error(request, "Método no permitido.")
        return redirect("proyectoapp:lista_proyectos")

    form = ProyectoForm(request.POST)

    if not form.is_valid():
        if es_ajax(request):
            return JsonResponse({"success": False, "errors": form.errors})
        messages.error(request, "⚠️ Corrige los errores del formulario.")
        return redirect("proyectoapp:lista_proyectos")

    proyecto = form.save(commit=False)

    proyecto.proye_idp = request.POST.get("proye_idp", "").strip()

    # Cliente solo si es válido y activo
    cliente_id = request.POST.get("cliente")
    if cliente_id:
        try:
            proyecto.cliente = EmpresaPersona.objects.get(
                pk=cliente_id,
                emppe_est=True,
                emppe_sit__in=["cliente", "ambos"]
            )
        except EmpresaPersona.DoesNotExist:
            err = {"cliente": ["El cliente seleccionado no es válido o no está activo."]}
            if es_ajax(request):
                return JsonResponse({"success": False, "errors": err}, status=400)

            messages.error(request, "El cliente seleccionado no es válido o no está activo.")
            return redirect("proyectoapp:lista_proyectos")

    proyecto.save()

    # Obtener datos del cliente YA CORRECTO
    cliente_data = _cliente_info(proyecto)

    # AJAX
    if es_ajax(request):
        return JsonResponse({
            "success": True,
            "msg": "Proyecto creado correctamente.",
            "created": {
                "id": proyecto.proye_idt,
                "idp": proyecto.proye_idp,
                "desc": proyecto.proye_desc,
                "obs": proyecto.proye_obs or "",
                "cost": proyecto.proye_cost,
                "fecha_sol": proyecto.proye_fecha_sol.strftime("%Y-%m-%d"),
                "fecha_ter": proyecto.proye_fecha_ter.strftime("%Y-%m-%d") if proyecto.proye_fecha_ter else "",
                "estado": proyecto.proye_estado,
                **cliente_data,
            }
        })

    messages.success(request, "✅ Proyecto creado correctamente.")
    return redirect("proyectoapp:lista_proyectos")


# -----------------------------
# EDITAR PROYECTO
# -----------------------------
@transaction.atomic
def editar_proyecto(request, pk):

    proyecto = get_object_or_404(Proyecto, pk=pk)

    if request.method != "POST":
        msg = {"__all__": ["Método no permitido."]}
        if es_ajax(request):
            return JsonResponse({"success": False, "errors": msg}, status=405)
        messages.error(request, "Método no permitido.")
        return redirect("proyectoapp:lista_proyectos")

    form = ProyectoForm(request.POST, instance=proyecto)

    if not form.is_valid():
        if es_ajax(request):
            return JsonResponse({"success": False, "errors": form.errors})

        messages.error(request, "⚠️ Corrige los errores del formulario.")
        return redirect("proyectoapp:lista_proyectos")

    proyecto = form.save(commit=False)
    proyecto.proye_idp = request.POST.get("proye_idp", "").strip()

    cliente_id = request.POST.get("cliente")
    if cliente_id:
        try:
            proyecto.cliente = EmpresaPersona.objects.get(
                pk=cliente_id,
                emppe_est=True,
                emppe_sit__in=["cliente", "ambos"]
            )
        except EmpresaPersona.DoesNotExist:
            err = {"cliente": ["El cliente seleccionado no existe o no está activo."]}
            if es_ajax(request):
                return JsonResponse({"success": False, "errors": err}, status=400)
            messages.error(request, "El cliente seleccionado no existe o no está activo.")
            return redirect("proyectoapp:lista_proyectos")

    proyecto.save()

    cliente_data = _cliente_info(proyecto)

    if es_ajax(request):
        return JsonResponse({
            "success": True,
            "msg": "Proyecto actualizado correctamente.",
            "updated": {
                "id": proyecto.proye_idt,
                "idp": proyecto.proye_idp,
                "desc": proyecto.proye_desc,
                "obs": proyecto.proye_obs or "",
                "cost": proyecto.proye_cost,
                "fecha_sol": proyecto.proye_fecha_sol.strftime("%Y-%m-%d"),
                "fecha_ter": proyecto.proye_fecha_ter.strftime("%Y-%m-%d") if proyecto.proye_fecha_ter else "",
                "estado": proyecto.proye_estado,
                **cliente_data,
            }
        })

    messages.success(request, "✅ Proyecto actualizado correctamente.")
    return redirect("proyectoapp:lista_proyectos")


# -----------------------------
# ELIMINAR PROYECTO
# -----------------------------
@transaction.atomic
def eliminar_proyecto(request, pk):

    if request.method != "POST":
        msg = {"__all__": ["Método no permitido."]}
        if es_ajax(request):
            return JsonResponse({"success": False, "errors": msg}, status=405)
        messages.error(request, "Método no permitido.")
        return redirect("proyectoapp:lista_proyectos")

    proyecto = get_object_or_404(Proyecto, pk=pk)
    proyecto.delete()

    if es_ajax(request):
        return JsonResponse({
            "success": True,
            "msg": "🗑️ Proyecto eliminado correctamente."
        })

    messages.success(request, "🗑️ Proyecto eliminado correctamente.")
    return redirect("proyectoapp:lista_proyectos")


# -----------------------------
# DETALLE PROYECTO
# -----------------------------
def detalle_proyecto(request, pk):

    proyecto = get_object_or_404(Proyecto, pk=pk)

    clientes = EmpresaPersona.objects.filter(
        emppe_est=True,
        emppe_sit__in=["cliente", "ambos"]
    ).order_by("emppe_nom")

    return render(request, "proyecto/detalle_proyecto.html", {
        "proyecto": proyecto,
        "clientes": clientes
    })

# -----------------------------
# API: DOCUMENTOS ASOCIADOS A UN PROYECTO
# -----------------------------
def api_documentos_por_proyecto(request, proye_idt):

    proyecto = get_object_or_404(Proyecto, pk=proye_idt)
    documentos = Documento.objects.filter(proyecto=proyecto)

    ingresos = 0
    egresos = 0

    docs_list = []

    for d in documentos:

        # --- Calcular monto bruto ---
        bruto = sum(
            det.dedoc_cant * (det.producto.produ_bruto if det.producto else 0)
            for det in d.detalles.all()
        )

        # --- Detectar ingreso/egreso según TRANSACCIÓN ---
        trans = d.transaccion   # propiedad del modelo: d.transacciones.first()

        if trans:
            if trans.tipo.tipo_id == 1:      # 1 = ingreso
                ingresos += bruto
            elif trans.tipo.tipo_id == 2:    # 2 = egreso
                egresos += bruto
        else:
            # si NO hay transacción asociada lo tratamos como "no clasificado"
            pass

        # --- Agregar documento al listado ---
        docs_list.append({
            "id": d.pk,
            "num": d.docum_num,
            "fecha": d.docum_fecha_emi.strftime("%Y-%m-%d") if d.docum_fecha_emi else "",
            "estado": d.docum_estado,
            "cliente": d.empresa.emppe_nom if d.empresa else "Sin cliente",
            "total": bruto,
            "tipo_trans": trans.tipo.tipo_trans if trans else None,
        })

    # --- Cálculos financieros del proyecto ---
    costo_proyecto = proyecto.proye_cost or 0
    utilidad = costo_proyecto + ingresos - egresos

    restante = costo_proyecto - egresos
    porcentaje_restante = 0
    if costo_proyecto > 0:
        porcentaje_restante = max(0, min(100, int((restante / costo_proyecto) * 100)))

    return JsonResponse({
        "success": True,
        "proyecto": {
            "costo": costo_proyecto,
            "ingresos": ingresos,
            "egresos": egresos,
            "utilidad": utilidad,
            "porcentaje_restante": porcentaje_restante,
        },
        "docs": docs_list
    })

@csrf_exempt
def api_quitar_documento(request, doc_id):
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Método no permitido"})

    doc = get_object_or_404(Documento, pk=doc_id)

    # quitar relación con proyecto
    doc.proyecto = None
    doc.save(update_fields=["proyecto"])

    return JsonResponse({"success": True})

# ====================
# VER PROYECTO
# ====================
@transaction.atomic
def ver_proyecto(request, pk):

    proyecto = get_object_or_404(Proyecto, pk=pk)

    # ==============================
    # CLIENTES PARA SELECT
    # ==============================
    clientes = EmpresaPersona.objects.filter(
        emppe_est=True,
        emppe_sit__in=["cliente", "ambos"]
    ).order_by("emppe_nom")

    # ==============================
    # POST: EDITAR PROYECTO
    # ==============================
    if request.method == "POST":
        form = ProyectoForm(request.POST, instance=proyecto)

        if form.is_valid():
            proy = form.save(commit=False)
            proy.proye_idp = request.POST.get("proye_idp", "").strip()

            cliente_id = request.POST.get("cliente")
            if cliente_id:
                try:
                    proy.cliente = EmpresaPersona.objects.get(
                        pk=cliente_id,
                        emppe_est=True,
                        emppe_sit__in=["cliente", "ambos"]
                    )
                except EmpresaPersona.DoesNotExist:
                    messages.error(
                        request,
                        "El cliente seleccionado no existe o no está activo."
                    )
                    return redirect("proyectoapp:ver_proyecto", pk=proyecto.pk)
            else:
                proy.cliente = None

            proy.save()
            messages.success(request, "✅ Proyecto actualizado correctamente.")
            return redirect("proyectoapp:ver_proyecto", pk=proyecto.pk)

    else:
        form = ProyectoForm(instance=proyecto)

    # ==============================
    # DOCUMENTOS DEL PROYECTO
    # ==============================
    documentos = (
        Documento.objects
        .filter(proyecto=proyecto)
        .select_related(
            "tipo_doc",
            "proyecto",
            "empresa",
            "forma_pago",
            "forma_pago__tipo_pago"
        )
        .prefetch_related(
            "detalles__producto",
            "transacciones__tipo"
        )
        .order_by("-docum_fecha_emi", "-docum_id")
    )

    # ==============================
    # VARIABLES CONTABLES
    # ==============================
    docs_pendientes = 0

    total_ingresos = Decimal(0)
    total_egresos = Decimal(0)

    ingresos_pagados = Decimal(0)
    egresos_pagados = Decimal(0)

    total_facturado = Decimal(0)
    saldo_pendiente = Decimal(0)

    presupuesto = proyecto.proye_cost or Decimal(0)

    # ==============================
    # LÓGICA CONTABLE REAL
    # ==============================
    for doc in documentos:

        # ----- TOTAL BRUTO -----
        bruto = sum(
            (det.dedoc_cant or 0) * (det.producto.produ_bruto or 0)
            for det in doc.detalles.all()
            if det.producto
        )

        # ----- PAGADO REAL -----
        pagado = sum(
            (det.dedoc_pagado or 0) * (det.producto.produ_bruto or 0)
            for det in doc.detalles.all()
            if det.producto
        )

        pendiente = bruto - pagado

        # valores calculados para el template
        doc.total_calc = bruto
        doc.pagado_calc = pagado
        doc.pendiente_calc = pendiente

        # ----- CONTADOR -----
        if doc.docum_estado in ("PENDIENTE", "MITAD"):
            docs_pendientes += 1

        # ----- TIPO TRANSACCIÓN -----
        doc.trans_tipo = None
        for trans in doc.transacciones.all():
            if trans.tipo.tipo_trans == "INGRESO":
                doc.trans_tipo = "INGRESO"
                break
            elif trans.tipo.tipo_trans == "EGRESO":
                doc.trans_tipo = "EGRESO"

        # ----- ACUMULADORES GLOBALES -----
        total_facturado += bruto
        saldo_pendiente += pendiente

        if doc.trans_tipo == "INGRESO":
            total_ingresos += bruto
            ingresos_pagados += pagado

        elif doc.trans_tipo == "EGRESO":
            total_egresos += bruto
            egresos_pagados += pagado

    # ==============================
    # MÉTRICAS FINALES
    # ==============================
    utilidad = presupuesto + total_ingresos - total_egresos

    # ==============================
    # BARRA CONTABLE (LÓGICA CORRECTA)
    # ==============================

    # 100% = presupuesto + ingresos pagados
    base_barra = presupuesto + ingresos_pagados

    # evitar división por cero
    if base_barra <= 0:
        base_barra = Decimal(1)

    # egresos pagados consumen la barra
    barra_roja = min(egresos_pagados, base_barra)

    # lo restante es verde
    barra_verde = base_barra - barra_roja

    # porcentajes reales
    verde_pct = float(round((barra_verde / base_barra) * 100, 2))
    rojo_pct  = float(round((barra_roja  / base_barra) * 100, 2))

    # ==============================
    # EXTRA: DOCUMENTOS + EGRESOS NETO/IVA + COSTO BRUTO
    # ==============================
    docs_total = documentos.count()

    # total_egresos ya es bruto acumulado de documentos EGRESO (según tu lógica actual)
    egresos_bruto = total_egresos

    # Neto e IVA desde bruto (19%)
    egresos_neto = (egresos_bruto / Decimal("1.19")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    egresos_iva  = (egresos_bruto - egresos_neto).quantize(Decimal("1"), rounding=ROUND_HALF_UP)

    # "Total del costo del proyecto (Bruto)" -> aquí lo interpreto como egresos_bruto acumulado
    # (si tú querías "presupuesto" u otro cálculo, me dices y lo ajusto)
    costo_total_bruto = egresos_bruto



    # ==============================
    # RENDER
    # ==============================
    return render(request, "proyecto/ver_proyecto.html", {
        "proyecto": proyecto,
        "form": form,
        "clientes": clientes,
        "documentos": documentos,

        # CARDS
        "presupuesto": presupuesto,
        "utilidad": utilidad,
        "total_facturado": total_facturado,
        "saldo_pendiente": saldo_pendiente,

        # CONTADORES
        "docs_pendientes": docs_pendientes,

        # HISTÓRICOS
        "total_ingresos": total_ingresos,
        "total_egresos": total_egresos,

        # BARRA
        "ingresos_pagados": ingresos_pagados,
        "egresos_pagados": egresos_pagados,
        "barra_verde": barra_verde,
        "barra_roja": barra_roja,
        "verde_pct": verde_pct,
        "rojo_pct": rojo_pct,
        "docs_total": docs_total,
        "egresos_neto": egresos_neto,
        "egresos_iva": egresos_iva,
        "costo_total_bruto": costo_total_bruto,
    })

