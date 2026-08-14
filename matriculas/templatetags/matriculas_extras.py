from django import template

register = template.Library()

# Número de colores de etiqueta disponibles para Área (ver .tag-0..tag-N en
# base.html): cada Área recibe un color estable por su id, como un marcador
# de color distinto por disciplina en la cartelera del estudio.
NUM_COLORES_ETIQUETA = 8


@register.filter
def tag_color(area):
    """Clase CSS "tag-N" estable para un Área, según su id (ver NUM_COLORES_ETIQUETA)."""
    if area is None or not getattr(area, "pk", None):
        return "tag-0"
    return f"tag-{area.pk % NUM_COLORES_ETIQUETA}"


@register.filter
def ficha_visible_para(objetivo, solicitante):
    """¿`solicitante` puede abrir la ficha de `objetivo`? — para decidir si el
    nombre se pinta como enlace o como texto.

    Reutiliza la MISMA función que protege la vista (`views._puede_ver_ficha`)
    en vez de repetir la regla de roles en la plantilla: si algún día cambia
    quién ve a quién, cambia en un solo sitio y los enlaces la siguen solos. Sin
    esto, un profesor vería enlaces que al pulsarlos lo rebotarían con un error.

    La importación va dentro de la función y no arriba porque `views` importa
    modelos y formularios; hacerla al cargar el módulo de etiquetas arriesga un
    ciclo de importación al arrancar.
    """
    from ..views import _puede_ver_ficha

    if objetivo is None or solicitante is None:
        return False
    return _puede_ver_ficha(solicitante, objetivo)
