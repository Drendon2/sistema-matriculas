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
