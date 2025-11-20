# ProyectoApp/models.py
from django.db import models

class Proyecto(models.Model):
    ESTADOS = [
        ("Pendiente", "Pendiente"),
        ("En Progreso", "En Progreso"),
        ("Terminado", "Terminado"),
        ("Cancelado", "Cancelado"),
    ]

    proye_idt = models.AutoField(primary_key=True)
    proye_desc = models.CharField(max_length=200)
    proye_obs = models.TextField(blank=True, null=True)
    proye_estado = models.CharField(max_length=20, choices=ESTADOS)
    proye_fecha_sol = models.DateField()
    proye_fecha_ter = models.DateField(blank=True, null=True)

    class Meta:
        db_table = "proyecto"

    def __str__(self):
        return f"{self.proye_desc} ({self.proye_estado})"
