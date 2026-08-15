from django.contrib import admin
from django.utils.functional import lazy

from .models import (
    Area, Asistencia, Clase, ConfirmacionClase, Periodo, Perfil,
    EncuestaDemografica, Acudiente, ConfiguracionInstitucion, DatosEstudiante,
    Promotoria, Grupo, Matricula, CupoPromotoria, EncuestaSatisfaccion,
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


class AsistenciaInline(admin.TabularInline):
    model = Asistencia
    extra = 0
    # La hora que importa es la de la clase, no la del último retoque de una
    # fila; se muestra pero no se edita.
    readonly_fields = ("fecha_registro",)


class ConfirmacionClaseInline(admin.TabularInline):
    model = ConfirmacionClase
    extra = 0
    readonly_fields = ("fecha",)


@admin.register(Clase)
class ClaseAdmin(admin.ModelAdmin):
    list_display = (
        "grupo", "fecha_hora", "periodo", "registrada_por", "confirmaciones_requeridas",
    )
    list_filter = ("periodo", "grupo__promotoria__area")
    # La hora la fija el botón "Iniciar clase" (auto_now_add) y el requisito de
    # confirmaciones lo fija el tamaño del grupo el día de la clase: que
    # cualquiera de los dos se pueda corregir a mano desde el admin vaciaría de
    # sentido el registro y su verificación.
    readonly_fields = ("fecha_hora", "confirmaciones_requeridas")
    inlines = [AsistenciaInline, ConfirmacionClaseInline]


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
@admin.register(EncuestaDemografica)
class EncuestaDemograficaAdmin(admin.ModelAdmin):
    """Ahora que la encuesta son listas cerradas, se puede filtrar por ellas.

    Los campos SENSIBLES (grupo étnico, discapacidad, condición de víctima) se
    dejan a propósito fuera de `list_display` y `list_filter`: siguen visibles
    al abrir una encuesta concreta, que es donde hace falta consultarlos, pero
    no se exponen en una tabla que se recorre de un vistazo ni sirven para
    segmentar personas desde el listado. Ver el recordatorio de visibilidad en
    models.py.
    """

    list_display = ("perfil", "genero", "estrato", "nivel_educativo", "ocupacion", "zona")
    list_filter = ("genero", "estrato", "nivel_educativo", "ocupacion", "zona", "afiliacion_salud")
    search_fields = ("perfil__nombre_completo", "barrio")


admin.site.register(Acudiente)
admin.site.register(DatosEstudiante)
