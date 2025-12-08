from django.db import migrations

def crear_admin_por_defecto(apps, schema_editor):
    UsuarioSistema = apps.get_model("UsuariosApp", "UsuarioSistema")

    if not UsuarioSistema.objects.filter(username="admin").exists():
        usuario = UsuarioSistema(
            username="admin",
            email="admin@teknetau.cl",
            role="admin",
            is_active=True,
        )
        usuario.set_password("admin123")  # Se guarda encriptada
        usuario.save()

def eliminar_admin(apps, schema_editor):
    UsuarioSistema = apps.get_model("UsuariosApp", "UsuarioSistema")
    UsuarioSistema.objects.filter(username="admin").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("UsuariosApp", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(crear_admin_por_defecto, eliminar_admin),
    ]
