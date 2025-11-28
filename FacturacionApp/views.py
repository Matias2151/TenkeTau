# FacturacionApp/views.py
import json
from datetime import datetime

import openpyxl
from django.db.models import Prefetch
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from openpyxl.styles import Font
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from .models import (
    Documento, DetalleDoc, Transaccion,
    TipoTransaccion, TipoPago, FormaPago,
    PagoDocumento,
)

from ProductoServicioApp.models import ProductoServicio
from .forms import DocumentoForm


# ============================================================
# LISTA DOCUMENTOS (ÚNICA PANTALLA)
# ============================================================

def lista_documentos(request):

    fecha_desde = request.GET.get("desde")
    fecha_hasta = request.GET.get("hasta")

    filtros = {}
    if fecha_desde:
        filtros["docum_fecha_emi__gte"] = fecha_desde
    if fecha_hasta:
        filtros["docum_fecha_emi__lte"] = fecha_hasta

    documentos = (
        Documento.objects.filter(**filtros)
        .select_related("empresa", "proyecto", "tipo_doc", "forma_pago__tipo_pago")
        .prefetch_related(
            "detalles__producto",
            "transacciones__tipo",
            Prefetch("pagos", queryset=PagoDocumento.objects.order_by("-pago_fecha")),
        )
        .order_by("-docum_num")
    )

    total_docs = documentos.count()
    total_pendientes = documentos.filter(docum_estado="PENDIENTE").count()
    total_pagados = documentos.filter(docum_estado="PAGADO").count()
    total_atrasados = documentos.filter(docum_estado="ATRASADO").count()
    monto_total_bruto = sum(doc.total for doc in documentos)
    saldo_pendiente = sum(doc.saldo_pendiente for doc in documentos)
    saldo_favor = sum(doc.saldo_a_favor for doc in documentos)

    context = {
        "documentos": documentos,
        "total_docs": total_docs,
        "total_pendientes": total_pendientes,
        "total_pagados": total_pagados,
        "total_atrasados": total_atrasados,
        "monto_total_bruto": monto_total_bruto,
        "saldo_pendiente": saldo_pendiente,
        "saldo_favor": saldo_favor,
        "filtro_desde": fecha_desde or "",
        "filtro_hasta": fecha_hasta or "",
        "doc_form": DocumentoForm(),
        "tipos_trans": TipoTransaccion.objects.all(),
        "tipos_pago": TipoPago.objects.all(),
        "productos": ProductoServicio.objects.all(),
    }

    return render(request, "facturacion/facturacion.html", context)

# ============================================================
# ELIMINAR DOCUMENTO COMPLETO (documento + detalles + transacción)
# ============================================================

def eliminar_documento(request, pk):

    if request.method != "POST":
        return redirect("facturacionapp:lista_documentos")

    documento = get_object_or_404(Documento, pk=pk)

    forma_pago = documento.forma_pago

    documento.transacciones.all().delete()

    documento.detalles.all().delete()

    documento.delete()

    if forma_pago:
        forma_pago.delete()

    return redirect("facturacionapp:lista_documentos")



# ============================================================
# CREAR DOCUMENTO + DETALLE (UN SOLO SUBMIT)
# ============================================================

def crear_documento(request):

    if request.method != "POST":
        return redirect("facturacionapp:lista_documentos")

    form = DocumentoForm(request.POST)

    # Campos externos al form
    tipo_pago_id = request.POST.get("tipo_pago")
    dias_pago = request.POST.get("fpago_dias")
    tipo_trans_id = request.POST.get("tipo_trans")
    detalle_json = request.POST.get("detalle_json")

    # Validaciones
    if not tipo_pago_id or not dias_pago:
        documentos = Documento.objects.all()
        return render(request, "facturacion/facturacion.html", {
            "documentos": documentos,
            "doc_form": form,
            "errores": True,
            "tipos_trans": TipoTransaccion.objects.all(),
            "tipos_pago": TipoPago.objects.all(),
            "productos": ProductoServicio.objects.all(),
        })

    # Validar documento
    if not form.is_valid():
        documentos = Documento.objects.all()
        return render(request, "facturacion/facturacion.html", {
            "documentos": documentos,
            "doc_form": form,
            "errores": True,
            "tipos_trans": TipoTransaccion.objects.all(),
            "tipos_pago": TipoPago.objects.all(),
            "productos": ProductoServicio.objects.all(),
        })

    # ============================
    # 1. Crear FormaPago
    # ============================
    forma_pago = FormaPago.objects.create(
        tipo_pago_id=tipo_pago_id,
        fpago_dias=int(dias_pago)
    )

    # ============================
    # 2. Crear Documento
    # ============================
    documento = form.save(commit=False)
    documento.forma_pago = forma_pago
    documento.save()

    # ==============================
    # 3. Crear Transacción inicial 
    # ==============================
    if tipo_trans_id:
        Transaccion.objects.create(
            documento=documento,
            tipo_id=tipo_trans_id,
            trans_fecha=timezone.now().date(),
            trans_monto=0
        )

    # ===============================
    # 4. Procesar DETALLES desde JSON
    # ===============================

    """
    El JSON llega así:
    [
      {"id": "10", "cant": 2, "precio": 9000, "obs": "nota"},
      {"id": "7", "cant": 1, "precio": 15000, "obs": ""}
    ]
    """

    try:
        detalle_data = json.loads(detalle_json)
    except:
        detalle_data = []

    for item in detalle_data:

        producto = get_object_or_404(ProductoServicio, pk=item["id"])

        DetalleDoc.objects.create(
            documento=documento,
            producto=producto,
            dedoc_cant=item["cant"],
            dedoc_obs=item.get("obs", "")
        )

    # ===============================
    # 5. Actualizar monto transacción
    # ===============================

    trans = documento.transacciones.first()
    if trans:
        trans.trans_monto = documento.total
        trans.save()

    return redirect("facturacionapp:lista_documentos")


# ============================
# API: OBTENER DATOS DEL DOCUMENTO (GET)
# ============================

def api_get_documento(request, pk):

    doc = get_object_or_404(Documento, pk=pk)

    # DETALLE seguro — evita errores si un producto fue eliminado
    detalles = []
    for d in doc.detalles.select_related("producto").all():

        producto = d.producto  # puede ser None ahora

        detalles.append({
            "id": producto.produ_id if producto else None,
            "nombre": producto.produ_nom if producto else "(Producto eliminado)",
            "precio": int(producto.produ_bruto) if producto else 0,
            "cant": d.dedoc_cant,
            "total": int(d.dedoc_cant * (producto.produ_bruto if producto else 0)),
            "obs": d.dedoc_obs,
        })

    data = {

        # ================================
        # DATOS BASE PARA EDITAR (SEGUROS)
        # ================================
        "docum_num": doc.docum_num,

        "tipo_doc": doc.tipo_doc.tidoc_id if doc.tipo_doc else None,
        "tipo_doc_nombre": doc.tipo_doc.tidoc_tipo if doc.tipo_doc else "",

        "empresa": doc.empresa.emppe_id if doc.empresa else None,
        "empresa_nombre": doc.empresa.emppe_nom if doc.empresa else "(Sin cliente)",

        "proyecto": doc.proyecto.proye_idt if doc.proyecto else None,
        "proyecto_nombre": doc.proyecto.proye_desc if doc.proyecto else "",

        "docum_estado": doc.docum_estado,

        # ================================
        # FECHAS (seguras si son NULL)
        # ================================
        "docum_fecha_emi": doc.docum_fecha_emi.strftime("%Y-%m-%d") if doc.docum_fecha_emi else "",
        "docum_fecha_ven": doc.docum_fecha_ven.strftime("%Y-%m-%d") if doc.docum_fecha_ven else "",
        "docum_fecha_recl": doc.docum_fecha_recl.strftime("%Y-%m-%d") if doc.docum_fecha_recl else "",

        # ================================
        # FORMA DE PAGO (seguro)
        # ================================
        "tipo_pago": doc.forma_pago.tipo_pago.tpago_id if doc.forma_pago else None,
        "tipo_pago_nombre": doc.forma_pago.tipo_pago.tpago_tipo if doc.forma_pago else "",
        "fpago_dias": doc.forma_pago.fpago_dias if doc.forma_pago else "",

        # ================================
        # DETALLE
        # ================================
        "detalle": detalles,
        "pagos": [
            {
                "id": pago.pago_id,
                "fecha": pago.pago_fecha.strftime("%Y-%m-%d"),
                "monto": pago.pago_monto,
                "glosa": pago.pago_glosa,
            }
            for pago in doc.pagos.all()
        ],
        "saldo_pendiente": doc.saldo_pendiente,
        "saldo_a_favor": doc.saldo_a_favor,
        "monto_pagado": doc.monto_pagado,
        "estado_financiero": doc.estado_financiero,
    }

    return JsonResponse(data)


# ============================
# EDITAR DOCUMENTO (POST)
# ============================

def editar_documento_post(request, pk):

    doc = get_object_or_404(Documento, pk=pk)

    if request.method != "POST":
        return JsonResponse({"error": "Método no permitido"}, status=405)

    form = DocumentoForm(request.POST, instance=doc)
    if not form.is_valid():
        return JsonResponse({"error": "Formulario inválido", "detalles": form.errors}, status=400)

    form.save()

    # ============================
    # FORMA DE PAGO
    # ============================
    tipo_pago_id = request.POST.get("tipo_pago")
    fpago_dias = request.POST.get("fpago_dias", 0)

    if tipo_pago_id:
        tipo_pago = TipoPago.objects.get(pk=tipo_pago_id)

        FormaPago.objects.update_or_create(
            documento=doc,
            defaults={
                "tipo_pago": tipo_pago,
                "fpago_dias": fpago_dias
            }
        )

    # ============================
    # DETALLE
    # ============================
    lista = json.loads(request.POST.get("detalle_json", "[]"))

    # borrar detalle previo
    DetalleDoc.objects.filter(documento=doc).delete()

    for item in lista:
        producto = ProductoServicio.objects.get(pk=item["id"])
        DetalleDoc.objects.create(
            documento=doc,
            producto=producto,
            dedoc_cant=item["cant"],
            dedoc_obs=item.get("obs", "")
        )

    return redirect("facturacionapp:lista_documentos")


# ============================
# REGISTRAR PAGO / SALDO
# ============================
def registrar_pago_documento(request, pk):
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Método no permitido."}, status=405)

    documento = get_object_or_404(Documento, pk=pk)

    try:
        monto = int(request.POST.get("monto", 0))
    except (TypeError, ValueError):
        return JsonResponse({"success": False, "error": "Monto inválido."}, status=400)

    if monto == 0:
        return JsonResponse({"success": False, "error": "El monto no puede ser 0."}, status=400)

    fecha_raw = request.POST.get("fecha")
    try:
        fecha_pago = datetime.fromisoformat(fecha_raw).date() if fecha_raw else timezone.now().date()
    except ValueError:
        fecha_pago = timezone.now().date()

    PagoDocumento.objects.create(
        documento=documento,
        pago_fecha=fecha_pago,
        pago_monto=monto,
        pago_glosa=request.POST.get("glosa", ""),
    )

    # Actualizamos estado financiero base
    if documento.saldo_pendiente == 0 and documento.saldo_a_favor == 0:
        documento.docum_estado = "PAGADO"
    elif documento.monto_pagado > 0 and documento.total:
        documento.docum_estado = "MITAD"
    documento.save(update_fields=["docum_estado"])

    return JsonResponse(
        {
            "success": True,
            "saldo_pendiente": documento.saldo_pendiente,
            "saldo_a_favor": documento.saldo_a_favor,
            "monto_pagado": documento.monto_pagado,
            "estado_financiero": documento.estado_financiero,
        }
    )


# ============================
# EXPORTAR PDF GENERAL (COMPLETO)
# ============================
def export_pdf_all(request):

    documentos = Documento.objects.all().order_by("docum_num")

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = "attachment; filename=documentos.pdf"

    p = canvas.Canvas(response, pagesize=letter)
    y = 760

    p.setFont("Helvetica-Bold", 14)
    p.drawString(50, y, "Listado de documentos")
    y -= 40

    p.setFont("Helvetica", 10)

    for doc in documentos:

        if y < 120:
            p.showPage()
            y = 760
            p.setFont("Helvetica", 10)

        # ---- Valores seguros ----
        cliente = doc.empresa.emppe_nom if doc.empresa else "SIN CLIENTE"
        tipo_doc = doc.tipo_doc.tidoc_tipo if doc.tipo_doc else "N/A"
        fecha_emi = doc.docum_fecha_emi or "-"
        fecha_ven = doc.docum_fecha_ven or "-"

        # ---- Totales seguros ----
        bruto = 0
        for d in doc.detalles.all():
            if d.producto and d.producto.produ_bruto:
                bruto += (d.dedoc_cant * d.producto.produ_bruto)

        neto = round(bruto / 1.19) if bruto else 0
        iva = bruto - neto

        # ---- Encabezado ----
        p.setFont("Helvetica-Bold", 11)
        p.drawString(50, y, f"Documento N° {doc.docum_num}")
        y -= 16

        p.setFont("Helvetica", 10)
        p.drawString(50, y, f"Tipo: {tipo_doc}")
        y -= 14

        p.drawString(50, y, f"Cliente: {cliente}")
        y -= 14

        p.drawString(50, y, f"Emisión: {fecha_emi}     Vencimiento: {fecha_ven}")
        y -= 14

        p.drawString(50, y, f"Estado: {doc.docum_estado}")
        y -= 18

        # ---- Totales ----
        p.setFont("Helvetica-Bold", 10)
        p.drawString(50, y, f"Neto: ${neto:,}".replace(",", "."))
        y -= 14

        p.drawString(50, y, f"IVA: ${iva:,}".replace(",", "."))
        y -= 14

        p.drawString(50, y, f"Total: ${bruto:,}".replace(",", "."))
        y -= 18

        # ---- Detalle ----
        if doc.detalles.exists():
            p.setFont("Helvetica-Bold", 10)
            p.drawString(50, y, "Productos:")
            y -= 14

            p.setFont("Helvetica", 10)

            for det in doc.detalles.all():

                nombre_prod = det.producto.produ_nom if det.producto else "SIN PRODUCTO"
                precio = det.producto.produ_bruto if (det.producto and det.producto.produ_bruto) else 0
                subtotal = det.dedoc_cant * precio

                linea = f"- {nombre_prod} (x{det.dedoc_cant}) = ${subtotal:,}".replace(",", ".")

                p.drawString(60, y, linea)
                y -= 14

                if y < 80:
                    p.showPage()
                    y = 760
                    p.setFont("Helvetica", 10)

        y -= 10

    p.showPage()
    p.save()
    return response


# ============================
# EXPORTAR EXCEL GENERAL (COMPLETO)
# ============================
def export_excel_all(request):

    documentos = Documento.objects.all().order_by("docum_num")

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Documentos"

    ws.append([
        "N° Documento",
        "Cliente",
        "Tipo Documento",
        "Estado",
        "Fecha Emisión",
        "Fecha Vencimiento",
        "Neto",
        "IVA",
        "Total",
        "Productos"
    ])

    for cell in ws[1]:
        cell.font = Font(bold=True)

    for d in documentos:

        # ---- Valores seguros ----
        cliente = d.empresa.emppe_nom if d.empresa else "SIN CLIENTE"
        tipo_doc = d.tipo_doc.tidoc_tipo if d.tipo_doc else "N/A"
        fecha_emi = str(d.docum_fecha_emi or "")
        fecha_ven = str(d.docum_fecha_ven or "")

        # ---- Totales seguros ----
        bruto = 0
        productos_list = []

        for det in d.detalles.all():

            nombre_prod = det.producto.produ_nom if det.producto else "SIN PRODUCTO"
            precio = det.producto.produ_bruto if (det.producto and det.producto.produ_bruto) else 0
            subtotal = det.dedoc_cant * precio

            bruto += subtotal

            productos_list.append(f"{nombre_prod} (x{det.dedoc_cant})")

        neto = round(bruto / 1.19) if bruto else 0
        iva = bruto - neto
        productos = ", ".join(productos_list)

        ws.append([
            d.docum_num,
            cliente,
            tipo_doc,
            d.docum_estado,
            fecha_emi,
            fecha_ven,
            neto,
            iva,
            bruto,
            productos
        ])

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response['Content-Disposition'] = "attachment; filename=documentos.xlsx"

    wb.save(response)
    return response
