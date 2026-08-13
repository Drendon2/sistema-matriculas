"""Contexto que toda plantilla necesita: la marca de la institución.

Va por context processor y no por vista porque el nombre, el logo y el color
de acento viven en las plantillas base, que heredan absolutamente todas las
pantallas — incluidas las públicas, que no pasan por una vista propia.
"""

from .models import ConfiguracionInstitucion


def configuracion_institucion(request):
    return {"configuracion": ConfiguracionInstitucion.actual()}
