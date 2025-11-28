from django.urls import path
from . import views

app_name = "facturacionapp"

urlpatterns = [
    path("", views.lista_documentos, name="lista_documentos"),

    # Crear
    path("nuevo/", views.crear_documento, name="crear_documento"),

    # Editar (POST desde el modal)
    path("editar/<int:pk>/", views.editar_documento_post, name="editar_documento_post"),

    # Eliminar
    path("eliminar/<int:pk>/", views.eliminar_documento, name="eliminar_documento"),

    # API GET para cargar datos en el modal de edición
    path("api/documento/<int:pk>/", views.api_get_documento, name="api_get_documento"),

    path("export/pdf/", views.export_pdf_all, name="export_pdf_all"),
    path("export/excel/", views.export_excel_all, name="export_excel_all"),
]
