# FacturacionApp/forms.py
import json

from django import forms
from django.core.exceptions import ValidationError

from .models import Documento, DetalleDoc


# ============================================================
#   FORMULARIO PRINCIPAL (DOCUMENTO)
# ============================================================

class DocumentoForm(forms.ModelForm):

    ESTADOS = [
        ("PENDIENTE", "Pendiente"),
        ("PAGADO", "Pagado"),
        ("MITAD", "Pagado Mitad"),
        ("ATRASADO", "Atrasado"),
    ]

    docum_num = forms.IntegerField(
        label="Número de documento",
        required=True,
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "placeholder": "Ej: 10230",
            }
        )
    )

    docum_estado = forms.ChoiceField(
        label="Estado del documento",
        choices=ESTADOS,
        required=True,
        widget=forms.Select(attrs={"class": "form-control"})
    )

    class Meta:
        model = Documento

        fields = [
            "docum_num",
            "docum_estado",
            "empresa",
            "proyecto",
            "tipo_doc",
            "docum_fecha_emi",
            "docum_fecha_ven",
            "docum_fecha_recl",
            "docum_obs",
        ]

        widgets = {

            "empresa": forms.Select(attrs={"class": "form-control select2"}),
            "proyecto": forms.Select(attrs={"class": "form-control select2"}),

            "tipo_doc": forms.Select(attrs={"class": "form-control"}),

            "docum_fecha_emi": forms.DateInput(
                attrs={"type": "date", "class": "form-control"}
            ),
            "docum_fecha_ven": forms.DateInput(
                attrs={"type": "date", "class": "form-control"}
            ),
            "docum_fecha_recl": forms.DateInput(
                attrs={"type": "date", "class": "form-control"}
            ),

            "docum_obs": forms.Textarea(
                attrs={"class": "form-control", "rows": 3}
            ),
        }

    def clean_docum_num(self):
        numero = self.cleaned_data.get("docum_num")

        if numero is not None and numero <= 0:
            raise ValidationError("El número de documento debe ser positivo.")

        existe = (
            Documento.objects
            .filter(docum_num=numero)
            .exclude(pk=self.instance.pk or None)
            .exists()
        )

        if existe:
            raise ValidationError("Ya existe un documento con este número.")

        return numero

    def clean(self):
        cleaned_data = super().clean()

        proyecto = cleaned_data.get("proyecto")
        fecha_emi = cleaned_data.get("docum_fecha_emi")
        fecha_ven = cleaned_data.get("docum_fecha_ven")
        estado = cleaned_data.get("docum_estado", "").upper()

        if proyecto and fecha_emi:
            if fecha_emi < proyecto.proye_fecha_sol:
                self.add_error(
                    "docum_fecha_emi",
                    "La fecha de emisión no puede ser anterior al inicio del proyecto.",
                )

            if proyecto.proye_fecha_ter and fecha_emi > proyecto.proye_fecha_ter:
                self.add_error(
                    "docum_fecha_emi",
                    "La fecha de emisión debe estar dentro de la vigencia del proyecto.",
                )

        if proyecto and fecha_ven:
            if fecha_ven < proyecto.proye_fecha_sol:
                self.add_error(
                    "docum_fecha_ven",
                    "La fecha de vencimiento no puede ser anterior al inicio del proyecto.",
                )

            if proyecto.proye_fecha_ter and fecha_ven > proyecto.proye_fecha_ter:
                self.add_error(
                    "docum_fecha_ven",
                    "La fecha de vencimiento debe estar dentro de la vigencia del proyecto.",
                )

        detalle_json = self.data.get("detalle_json", "[]")

        try:
            detalles = json.loads(detalle_json)
        except (TypeError, json.JSONDecodeError):
            detalles = []

        if not detalles and self.instance.pk:
            detalles = list(self.instance.detalles.all())

        if estado == "PAGADO" and not detalles:
            raise ValidationError(
                "No puedes marcar como pagado un documento sin detalles asociados."
            )

        return cleaned_data


# ============================================================
#   FORMULARIO DETALLE (Producto / Cant / Obs)
# ============================================================

class DetalleDocForm(forms.ModelForm):
    class Meta:
        model = DetalleDoc
        fields = ["producto", "dedoc_cant", "dedoc_obs"]

        widgets = {
            "producto": forms.Select(attrs={"class": "form-control select2"}),
            "dedoc_cant": forms.NumberInput(
                attrs={"class": "form-control", "min": 1}
            ),
            "dedoc_obs": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Opcional"}
            ),
        }

    def clean_dedoc_cant(self):
        cantidad = self.cleaned_data.get("dedoc_cant")

        if cantidad is not None and cantidad <= 0:
            raise ValidationError("La cantidad debe ser mayor a cero.")

        return cantidad

    def clean(self):
        cleaned_data = super().clean()

        producto = cleaned_data.get("producto")
        cantidad = cleaned_data.get("dedoc_cant")
        observacion = cleaned_data.get("dedoc_obs")

        if (cantidad or observacion) and not producto:
            self.add_error("producto", "Debes seleccionar un producto para el detalle.")

        return cleaned_data


# ============================================================
#   FORMSET (si en algún momento quieres volver a usarlo)
# ============================================================

DetalleFormSet = forms.modelformset_factory(
    DetalleDoc,
    form=DetalleDocForm,
    extra=1,
    can_delete=True
)
