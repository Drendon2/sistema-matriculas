from django.contrib import admin
from django.utils.functional import lazy

from .models import (
    Area, Periodo, Perfil, EncuestaDemografica, Acudiente, ConfiguracionInstitucion,
    DatosEstudiante, Promotoria, Grupo, Matricula, CupoPromotoria, EncuestaSatisfaccion,
)

# Perezoso a propósito: admin.py se importa al arrancar y durante `migrate`,
# cuando la tabla de configuración puede no existir todavía. `lazy` difiere la
# consulta hasta que se renderiza una página del admin.
_texto_perezoso = lazy(lambda funcion: funcion(), str)


def _cabecera_admin():
    return f"{ConfiguracionInstitucion.actual().nombre_institucion} — Administración de Matrículas"


admin.site.site_header = _texto_perezoso(_cabecera_admin)
admin.site.site_title = "Matrículas"
admin.site.index_title = "Panel de administración"


@admin.register(ConfiguracionInstitucion)
class ConfiguracionInstitucionAdmin(admin.ModelAdmin):
    list_display = ("nombre_institucion", "color_acento")

    def has_add_permission(self, request):
        # Singleton: se edita la fila que ya existe, no se crean más.
        return not ConfiguracionInstitucion.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Perfil)
class PerfilAdmin(admin.ModelAdmin):
    list_display = ("nombre_completo", "rol", "telefono")
    list_filter = ("rol",)
    search_fields = ("nombre_completo",)


@admin.register(Promotoria)
class PromotoriaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "area", "profesor")
    list_filter = ("area",)


@admin.register(Grupo)
class GrupoAdmin(admin.ModelAdmin):
    list_display = ("promotoria", "nivel", "horario", "salon", "cupo_maximo")
    list_filter = ("nivel", "promotoria__area")


@admin.register(EncuestaSatisfaccion)
class EncuestaSatisfaccionAdmin(admin.ModelAdmin):
    list_display = (
        "perfil", "periodo", "satisfaccion_general", "calificacion_profesor",
        "horario_funciono", "recomendaria", "fecha",
    )
    list_filter = ("periodo", "satisfaccion_general", "recomendaria")


@admin.register(CupoPromotoria)
class CupoPromotoriaAdmin(admin.ModelAdmin):
    list_display = ("promotoria", "periodo", "cupo_maximo")
    list_filter = ("periodo", "promotoria__area")


@admin.register(Matricula)
class MatriculaAdmin(admin.ModelAdmin):
    list_display = ("estudiante", "promotoria", "grupo", "periodo", "estado", "ranura", "fecha")
    list_filter = ("periodo", "estado")
    # `ranura` la asigna el sistema al guardar (ver Matricula.save): editarla a
    # mano solo serviría para chocar contra el índice único.
    readonly_fields = ("ranura",)


# Registro simple para el resto
admin.site.register(Area)


@admin.register(Periodo)
class PeriodoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "fecha_inicio", "fecha_fin", "activo", "matriculas_abiertas")
    # Ambos flags se manejan desde Gestión → Iniciar / finalizar matrículas, que
    # hace el cambio en una transacción. Editarlos a mano aquí solo serviría para
    # chocar contra la restricción de "un solo periodo en curso".
    readonly_fields = ("activo", "matriculas_abiertas")
admin.site.register(EncuestaDemografica)
admin.site.register(Acudiente)
admin.site.register(DatosEstudiante)
