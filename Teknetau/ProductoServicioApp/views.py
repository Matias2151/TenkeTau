# ProductoServicioApp/views.py
from decimal import Decimal, ROUND_HALF_UP

from django.shortcuts import render, redirect, get_object_or_404
from django.db import transaction
from django.db.models import Sum, Prefetch

from .models import ProductoServicio, Abastecimiento
from .forms import ProductoServicioForm

# 👇 Importamos el modelo de la otra app para prefetchear proveedores con su dirección
from EmpresaPersonaApp.models import EmpresaPersona

from django.http import HttpResponse
from openpyxl import Workbook

IVA_FACTOR = Decimal("1.19")   # 19% IVA
ROUND = lambda x: x.quantize(Decimal("1"), rounding=ROUND_HALF_UP)  # redondeo a entero


def _recalcula_campos(precio_bruto: Decimal, dscto_pct: Decimal | int | None):
    """
    Aplica descuento (%) al bruto y retorna (neto, iva, bruto_final)
    bruto_final = bruto * (1 - dscto/100)
    neto = bruto_final / 1.19 ; iva = bruto_final - neto

    Retorna enteros (int) listos para PositiveIntegerField.
    """
    dscto_pct = Decimal(dscto_pct or 0)
    bruto_final = (precio_bruto * (Decimal("1") - dscto_pct / Decimal("100")))
    if bruto_final < 0:
        bruto_final = Decimal("0")

    neto = (bruto_final / IVA_FACTOR)
    iva = bruto_final - neto

    # Redondeo a entero CLP (Decimal entero)
    neto_r = ROUND(neto)
    iva_r = ROUND(iva)
    bruto_r = ROUND(bruto_final)

    # Retornamos ints para asignar directo a PositiveIntegerField
    return int(neto_r), int(iva_r), int(bruto_r)


@transaction.atomic
def lista_productos(request):
    if request.method == 'POST':
        form = ProductoServicioForm(request.POST)
        if form.is_valid():
            # Guardado con cálculo de neto/iva desde bruto y descuento
            producto = form.save(commit=False)

            bruto_in = Decimal(form.cleaned_data.get('produ_bruto') or 0)
            dscto_in = form.cleaned_data.get('produ_dscto') or 0
            neto, iva, bruto_final = _recalcula_campos(bruto_in, dscto_in)

            # Asignar ints a campos Integer del modelo
            producto.produ_neto = neto
            producto.produ_iva = iva
            producto.produ_bruto = bruto_final
            producto.save()

            # Relación con empresa (Abastecimiento)
            empresa = form.cleaned_data['empresa']
            Abastecimiento.objects.get_or_create(emppe=empresa, produ=producto)

            return redirect('productoyservicioapp:lista_productos')
    else:
        form = ProductoServicioForm()

    # ========= CARGA DE PRODUCTOS + PROVEEDOR CON DIRECCIÓN =========
    # Prefetch de proveedores con su dirección y jerarquía (region/ciudad/comuna) en una sola consulta
    proveedores_qs = (
        EmpresaPersona.objects
        .select_related(
            'emppe_dire',                 # FK/OneToOne a dirección
            'emppe_dire__regi',           # región
            'emppe_dire__ciuda',          # ciudad
            'emppe_dire__comun',          # comuna
        )
    )

    productos = (
        ProductoServicio.objects
        .prefetch_related(
            Prefetch('proveedores', queryset=proveedores_qs)
        )
        .all()
    )

    # ======= TOTALES =======
    totales = productos.aggregate(
        total_neto=Sum('produ_neto'),
        total_iva=Sum('produ_iva'),
        total_bruto=Sum('produ_bruto'),
    )

    context = {
        'productos': productos,
        'form': form,
        'total_neto':  totales.get('total_neto')  or 0,
        'total_iva':   totales.get('total_iva')   or 0,
        'total_bruto': totales.get('total_bruto') or 0,
    }
    return render(request, 'producto_servicio/producto_servicio.html', context)


@transaction.atomic
def editar_producto(request, pk):
    producto = get_object_or_404(ProductoServicio, pk=pk)
    abastecimiento = Abastecimiento.objects.filter(produ=producto).first()
    empresa_actual = abastecimiento.emppe if abastecimiento else None

    if request.method == 'POST':
        form = ProductoServicioForm(request.POST, instance=producto)
        if form.is_valid():
            producto = form.save(commit=False)

            bruto_in = Decimal(form.cleaned_data.get('produ_bruto') or 0)
            dscto_in = form.cleaned_data.get('produ_dscto') or 0
            neto, iva, bruto_final = _recalcula_campos(bruto_in, dscto_in)

            producto.produ_neto = neto
            producto.produ_iva = iva
            producto.produ_bruto = bruto_final
            producto.save()

            # Empresa/proveedor
            nueva_empresa = form.cleaned_data['empresa']
            if empresa_actual != nueva_empresa:
                if empresa_actual:
                    Abastecimiento.objects.filter(emppe=empresa_actual, produ=producto).delete()
                Abastecimiento.objects.get_or_create(emppe=nueva_empresa, produ=producto)

            return redirect('productoyservicioapp:lista_productos')
    else:
        initial_data = {'empresa': empresa_actual} if empresa_actual else {}
        form = ProductoServicioForm(instance=producto, initial=initial_data)

    return render(request, 'producto_servicio/editar.html', {'form': form, 'producto': producto})


@transaction.atomic
def eliminar_producto(request, pk):
    producto = get_object_or_404(ProductoServicio, pk=pk)
    if request.method == 'POST':
        Abastecimiento.objects.filter(produ=producto).delete()
        producto.delete()
    return redirect('productoyservicioapp:lista_productos')

def descargar_plantilla_productos(request):
    # Crear libro y hoja
    wb = Workbook()
    ws = wb.active
    ws.title = "Productos o Servicios"

    # Encabezados de la tabla (según tu imagen)
    headers = [
        "PRODU_ID",
        "PRODU_NOM",
        "PRODU_DESC",
        "PRODU_BRUTO",
        "PRODU_NETO",
        "PRODU_MA",
        "PRODU_DSCTO",
    ]

    # Agregar encabezados en la primera fila
    ws.append(headers)

    # Si quieres dejar PRODU_ID vacío porque es autoincremental,
    # es solo una columna de referencia para importar; puedes borrarla de la lista si no la quieres.

    # Preparar respuesta HTTP para descarga
    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response["Content-Disposition"] = (
        'attachment; filename="plantilla_productos_servicios.xlsx"'
        )

        wb.save(response)
    return response
