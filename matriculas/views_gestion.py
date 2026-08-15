import math
from collections import Counter

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.db.models.deletion import Collector, ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, TemplateView, UpdateView

from .forms import ConfiguracionInstitucionForm, UsuarioForm
from .models import (
    Acudiente, Area, ConfiguracionInstitucion, CupoPromotoria, DatosEstudiante,
    EncuestaDemografica, Grupo, Matricula, Perfil, Periodo, Promotoria,
)
from .views import _ficha_estudiante, requiere_rol

ROLES_GESTION = ("director", "administrador")


def _enumerar(piezas):
    """["3 grupos", "41 matrículas"] -> "3 grupos y 41 matrículas"."""
    if len(piezas) <= 1:
        return "".join(piezas)
    return f"{', '.join(piezas[:-1])} y {piezas[-1]}"


def _contar_por_modelo(objetos):
    """Instancias sueltas -> ["1 grupo", "19 matrículas"], en singular o plural."""
    por_modelo = Counter(type(obj) for obj in objetos)
    return [
        "{} {}".format(
            cuantos,
            (modelo._meta.verbose_name if cuantos == 1
             else modelo._meta.verbose_name_plural).lower(),
        )
        for modelo, cuantos in por_modelo.items()
    ]


def _simular_borrado(objeto):
    """Qué impediría borrar `objeto` y qué se iría con él, sin tocar la base.

    Es el mismo recuento que hará el borrado de verdad: el ProtectedError salta
    al RECOLECTAR lo que caería, no al escribir, así que preguntarlo antes da
    exactamente la misma respuesta que dará el POST. De ahí que la pantalla de
    confirmación pueda decir la verdad antes de que nadie pulse nada, en vez de
    preguntar «¿seguro?» para negarse después.
    """
    collector = Collector(using=objeto._state.db)
    try:
        collector.collect([objeto])
    except ProtectedError as error:
        return list(error.protected_objects), []
    arrastre = [
        hijo
        for instancias in collector.data.values()
        for hijo in instancias
        if hijo != objeto
    ]
    return [], arrastre


class RolGestionRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Solo director/administrador pueden gestionar el catálogo académico."""

    def test_func(self):
        perfil = getattr(self.request.user, "perfil", None)
        return perfil is not None and perfil.rol in ROLES_GESTION

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            messages.error(self.request, "No tienes acceso a esta sección.")
            return redirect("post_login_redirect")
        return super().handle_no_permission()


class BorradoProtegidoMixin:
    """Convierte un ProtectedError (hay registros dependientes) en un mensaje amable.

    El destino sale de `get_success_url()`, no del atributo `success_url`: la
    mitad de las vistas que usan este mixin lo calculan (volver al área, volver
    a la promotoría) y dejan el atributo en None. Redirigir por el atributo
    reventaba con TypeError justo en el camino de recuperación, así que quien
    intentaba borrar algo protegido no veía el aviso sino un error 500 — el
    borrado se impedía bien, pero parecía que el sistema se había roto.
    """

    def get_context_data(self, **kwargs):
        """Lo que la pantalla necesita para no preguntar en vano."""
        contexto = super().get_context_data(**kwargs)
        bloqueos, arrastre = _simular_borrado(self.object)
        contexto["bloqueos"] = _enumerar(_contar_por_modelo(bloqueos))
        contexto["arrastre"] = _enumerar(_contar_por_modelo(arrastre))
        return contexto

    def form_valid(self, form):
        # La pantalla ya avisa antes de preguntar, así que aquí no debería
        # llegar nadie. Se queda igual porque el botón no es la única forma de
        # enviar este POST, y porque entre que se pinta la página y se pulsa
        # puede entrar una matrícula nueva.
        try:
            return super().form_valid(form)
        except ProtectedError as error:
            messages.error(self.request, self.aviso_de_protegido(error))
            return redirect(self.get_success_url())

    def aviso_de_protegido(self, error):
        """Nombra y cuenta lo que está estorbando, en vez de decir «algo depende»."""
        # "todavía tiene …" en vez de "… depende de él": el sujeto puede ser una
        # promotoría, un área o un periodo, y así el aviso no tiene que
        # concordar en género con nada.
        return (
            f"No se puede eliminar «{self.object}»: todavía tiene "
            f"{_enumerar(_contar_por_modelo(error.protected_objects))}."
        )


class GestionInicioView(RolGestionRequiredMixin, TemplateView):
    template_name = "matriculas/gestion_inicio.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        # La cifra en la ficha de "Cancelaciones" es lo único que avisa de que
        # hay gente esperando respuesta: sin ella habría que entrar a mirar.
        contexto["cancelaciones_pendientes"] = Matricula.objects.filter(
            estado=Matricula.ESTADO_CANCELACION,
        ).count()
        return contexto


@requiere_rol("administrador")
def configuracion_institucion(request):
    """Ajustes de la institución: la marca y el límite de promotorías por periodo.

    Solo administrador: no es catálogo académico (que sí comparte con el
    director), es la identidad de toda la entidad y una regla que gobierna las
    matrículas de todo el mundo.
    """
    configuracion = ConfiguracionInstitucion.actual()

    if request.method == "POST":
        form = ConfiguracionInstitucionForm(request.POST, request.FILES, instance=configuracion)
        if form.is_valid():
            form.save()
            messages.success(request, "Configuración de la institución actualizada.")
            # El contraste no bloquea: una marca clara puede ser legítima, pero
            # el texto blanco de los botones deja de leerse y hay que avisarlo.
            razon = form.instance.contraste_texto_boton
            if razon < 4.5:
                messages.error(
                    request,
                    f"Ojo: el texto blanco sobre ese color de acento queda en {razon:.1f}:1 de "
                    "contraste, por debajo del mínimo de 4.5:1. Los botones serán difíciles de "
                    "leer; considera un tono más oscuro.",
                )
            return redirect("gestion_configuracion")
    else:
        form = ConfiguracionInstitucionForm(instance=configuracion)

    return render(request, "matriculas/gestion_configuracion.html", {
        "form": form,
        "configuracion": configuracion,
    })


@requiere_rol(*ROLES_GESTION)
def ventana_matriculas(request):
    """Iniciar y finalizar las matrículas del periodo en curso.

    La Casa de la Cultura no recibe gente todo el año: abre al principio y a
    mitad. Este interruptor es lo que separa "el periodo está en curso" de "se
    admiten inscripciones y renovaciones ahora mismo".
    """
    periodo = Periodo.en_curso()

    if request.method == "POST" and request.POST.get("accion") == "poner_en_curso":
        elegido = get_object_or_404(Periodo, pk=request.POST.get("periodo_id"))
        anterior = periodo
        Periodo.poner_en_curso(elegido)
        if anterior is not None and anterior.pk != elegido.pk:
            messages.success(
                request,
                f"{elegido} es ahora el periodo en curso. {anterior} dejó de estarlo y sus "
                "matrículas quedaron cerradas.",
            )
        else:
            messages.success(request, f"{elegido} es ahora el periodo en curso.")
        return redirect("gestion_matriculas")

    if request.method == "POST":
        if periodo is None:
            messages.error(
                request,
                "No hay un periodo en curso. Elige cuál es antes de abrir matrículas.",
            )
            return redirect("gestion_matriculas")

        abrir = request.POST.get("accion") == "abrir"
        periodo.matriculas_abiertas = abrir
        periodo.save(update_fields=["matriculas_abiertas"])
        if abrir:
            messages.success(
                request,
                f"Matrículas de {periodo} ABIERTAS. Los estudiantes nuevos ya pueden "
                "inscribirse y los antiguos renovar.",
            )
        else:
            messages.success(
                request,
                f"Matrículas de {periodo} CERRADAS. Las matrículas ya registradas no se "
                "tocan; solo deja de entrar gente nueva.",
            )
        return redirect("gestion_matriculas")

    resumen = None
    if periodo is not None:
        matriculas = Matricula.objects.filter(periodo=periodo)
        anteriores = Periodo.objects.filter(fecha_inicio__lt=periodo.fecha_inicio).order_by(
            "-fecha_inicio"
        ).first()
        por_renovar = 0
        if anteriores is not None:
            ya_en_curso = set(
                matriculas.exclude(estado="retirada").values_list("estudiante_id", flat=True)
            )
            por_renovar = (
                Matricula.objects.filter(periodo=anteriores, estado="activa")
                .exclude(estudiante_id__in=ya_en_curso)
                .values("estudiante").distinct().count()
            )
        resumen = {
            "pendientes": matriculas.filter(estado="pendiente").count(),
            "activas": matriculas.filter(estado="activa").count(),
            "estudiantes": matriculas.exclude(estado="retirada").values("estudiante").distinct().count(),
            "periodo_anterior": anteriores,
            "por_renovar": por_renovar,
        }

    return render(request, "matriculas/gestion_matriculas.html", {
        "periodo": periodo,
        "resumen": resumen,
        "periodos": Periodo.objects.order_by("-fecha_inicio"),
    })


@requiere_rol(*ROLES_GESTION)
def cupos_periodo(request, periodo_id=None):
    """Fijar de una vez el cupo de todas las promotorías para un periodo.

    Es la pantalla de "abrir matrículas": se elige el periodo, se reparten los
    cupos y se guarda todo junto. Dejar una casilla vacía deja esa promotoría
    sin tope. Los periodos pasados se pueden consultar, pero no editar: su
    cupo es parte del histórico.
    """
    periodos = list(Periodo.objects.order_by("-activo", "-id"))
    if periodo_id is not None:
        periodo = get_object_or_404(Periodo, pk=periodo_id)
    else:
        periodo = next((p for p in periodos if p.activo), None) or (periodos[0] if periodos else None)

    if periodo is None:
        return render(request, "matriculas/gestion_cupos.html", {
            "periodo": None, "periodos": periodos, "filas": [],
        })

    promotorias = list(
        Promotoria.objects.select_related("area", "profesor").order_by("area__nombre", "nombre")
    )

    if request.method == "POST":
        if not periodo.activo:
            messages.error(
                request,
                f"{periodo} no es el periodo activo: sus cupos son histórico y no se editan.",
            )
            return redirect("gestion_cupos_periodo", periodo_id=periodo.pk)

        errores, guardados, quitados, avisos = [], 0, 0, []
        with transaction.atomic():
            for promotoria in promotorias:
                bruto = (request.POST.get(f"cupo_{promotoria.pk}") or "").strip()
                if bruto == "":
                    borrados, _ = CupoPromotoria.objects.filter(
                        promotoria=promotoria, periodo=periodo
                    ).delete()
                    quitados += 1 if borrados else 0
                    continue
                try:
                    cupo = int(bruto)
                except ValueError:
                    errores.append(f"{promotoria}: «{bruto}» no es un número entero.")
                    continue
                if cupo < 0:
                    errores.append(f"{promotoria}: el cupo no puede ser negativo.")
                    continue

                CupoPromotoria.objects.update_or_create(
                    promotoria=promotoria, periodo=periodo, defaults={"cupo_maximo": cupo},
                )
                guardados += 1
                ocupados = promotoria.ocupados_en(periodo)
                if cupo < ocupados:
                    avisos.append(f"{promotoria}: cupo {cupo} por debajo de las {ocupados} matrículas ya ocupando sitio.")

            if errores:
                # Nada a medias: si un valor viene mal, no se guarda ninguno.
                transaction.set_rollback(True)

        if errores:
            messages.error(request, "No se guardó ningún cupo. " + " ".join(errores))
        else:
            messages.success(
                request,
                f"Cupos de {periodo} guardados: {guardados} con tope"
                + (f", {quitados} sin tope" if quitados else "") + ".",
            )
            for aviso in avisos:
                messages.error(request, aviso + " No se retiró a nadie, pero no entrarán estudiantes nuevos.")
        return redirect("gestion_cupos_periodo", periodo_id=periodo.pk)

    filas = []
    for promotoria in promotorias:
        filas.append({
            "promotoria": promotoria,
            "cupo": promotoria.cupo_en(periodo),
            "ocupados": promotoria.ocupados_en(periodo),
        })

    return render(request, "matriculas/gestion_cupos.html", {
        "periodo": periodo, "periodos": periodos, "filas": filas,
    })


@requiere_rol(*ROLES_GESTION)
def gestion_cancelaciones(request):
    """Cancelaciones pedidas por estudiantes y todavía sin resolver.

    Solo director y administrador: el profesor las ve marcadas en su panel,
    pero no decide. Aprobar retira la matrícula de verdad y libera el cupo;
    rechazar la devuelve a activa, y eso último solo cabe con menores de edad
    (ver `Matricula.cancelacion_es_rechazable`).
    """
    pendientes = (
        Matricula.objects.filter(estado=Matricula.ESTADO_CANCELACION)
        .select_related(
            "estudiante", "estudiante__datos_estudiante",
            "estudiante__datos_estudiante__acudiente",
            "promotoria", "promotoria__area", "periodo", "grupo",
        )
        .order_by("periodo__fecha_inicio", "promotoria__nombre")
    )
    return render(request, "matriculas/gestion_cancelaciones.html", {
        "pendientes": list(pendientes),
    })


@requiere_rol(*ROLES_GESTION)
def gestion_resolver_cancelacion(request, matricula_id, decision):
    """Aprueba o rechaza una cancelación. `decision` es "aprobar" o "rechazar"."""
    if request.method != "POST":
        return redirect("gestion_cancelaciones")

    matricula = get_object_or_404(
        Matricula, pk=matricula_id, estado=Matricula.ESTADO_CANCELACION,
    )
    nombre = matricula.estudiante.nombre_completo

    if decision == "rechazar":
        # La comprobación va aquí y no solo en la plantilla: ocultar el botón
        # no impide que alguien envíe el formulario a mano.
        if not matricula.cancelacion_es_rechazable:
            messages.error(
                request,
                f"{nombre} es mayor de edad, así que su decisión de salir no se rechaza: "
                "esta cancelación solo se puede aprobar.",
            )
            return redirect("gestion_cancelaciones")
        matricula.estado = "activa"
        matricula.save(update_fields=["estado"])
        messages.success(
            request,
            f"Cancelación rechazada: {nombre} sigue matriculado en {matricula.promotoria}.",
        )
        return redirect("gestion_cancelaciones")

    matricula.estado = "retirada"
    matricula.grupo = None
    matricula.save(update_fields=["estado", "grupo"])
    messages.success(
        request,
        f"{nombre} quedó retirado de {matricula.promotoria}. Su cupo vuelve a estar libre.",
    )
    return redirect("gestion_cancelaciones")


def _con_porcentaje(filas, campo="total"):
    """Agrega 'porcentaje' (ancho de barra 0-100, relativo al valor más alto de la lista)."""
    filas = list(filas)
    maximo = max((f[campo] for f in filas), default=0)
    for f in filas:
        f["porcentaje"] = round((f[campo] / maximo) * 100) if maximo else 0
    return filas


# Paleta de las tortas. NO son los --tag-* del proyecto por dos razones: en esta
# misma página esos colores ya significan "Área" en el árbol de arriba, y además
# su teal y su magenta son indistinguibles para daltonismo protán (ΔE 2.8, muy
# por debajo del umbral de 8). Estos cuatro pasan las seis comprobaciones del
# validador comparando TODOS los pares entre sí, que es lo que exige una torta:
# en ella cualquier sector se compara con cualquier otro, no solo con el vecino.
#
# El proyecto es de un solo tema (claro). Si algún día gana modo oscuro, estos
# tonos hay que volver a escalonarlos contra la superficie oscura y revalidarlos:
# invertirlos sin más no sirve.
COLORES_TORTA = ["#2a78d6", "#eb6834", "#1baf7a", "#4a3aa7"]

# El "sin responder" va en gris a propósito, fuera de la paleta categórica: no
# es una opción más de la pregunta, es la ausencia de respuesta, y tiene que
# leerse como tal y no competir con las demás.
COLOR_SIN_RESPUESTA = "#c3cfc7"

RADIO_TORTA = 30          # el trazo, del mismo grosor que el diámetro, rellena el disco
SEPARACION_TORTA = 2      # hueco en px entre sectores contiguos


def _torta(filas, total_encuestas):
    """Sectores y leyenda de una gráfica de torta, a partir de un conteo por opción.

    Se dibuja con un `<circle>` por sector y `stroke-dasharray` en vez de rutas
    de arco: un trazo tan grueso como el diámetro rellena el disco entero, así
    que cada sector sale sin una línea de trigonometría y el hueco entre ellos
    es simplemente un tramo del guion que no se pinta.

    El todo de la torta es el total de encuestas, NO la suma de respuestas. En
    las preguntas opcionales eso cambia el dibujo por completo: si tres de
    dieciséis contestaron la zona, una torta de solo esos tres diría que el 100%
    de la gente vive donde vivan ellos. El resto entra como un sector gris de
    "sin responder", que es la respuesta honesta.

    Devuelve los sectores a pintar (solo los que tienen valor: un sector de 0°
    no se dibuja) y una leyenda con TODAS las opciones, incluidas las que nadie
    eligió. La leyenda es la que explica un sector ausente.
    """
    filas = list(filas)
    respondidas = sum(fila["total"] for fila in filas)
    sin_responder = max(0, total_encuestas - respondidas)
    total = respondidas + sin_responder

    leyenda = [
        dict(fila, color=COLORES_TORTA[indice % len(COLORES_TORTA)])
        for indice, fila in enumerate(filas)
    ]
    if sin_responder:
        leyenda.append({
            "etiqueta": "Sin responder",
            "total": sin_responder,
            "color": COLOR_SIN_RESPUESTA,
        })

    for entrada in leyenda:
        entrada["parte"] = round((entrada["total"] / total) * 100) if total else 0

    if not total:
        return {"sectores": [], "leyenda": leyenda, "total": 0}

    circunferencia = 2 * math.pi * RADIO_TORTA
    con_valor = [entrada for entrada in leyenda if entrada["total"] > 0]

    sectores, recorrido = [], 0.0
    for entrada in con_valor:
        arco = circunferencia * entrada["total"] / total
        # Un único sector ocuparía la vuelta entera: restarle el hueco solo
        # dejaría una muesca contra sí mismo, así que ahí no se separa nada.
        visible = arco if len(con_valor) == 1 else max(arco - SEPARACION_TORTA, 0.5)
        sectores.append({
            "color": entrada["color"],
            "etiqueta": entrada["etiqueta"],
            "total": entrada["total"],
            "parte": entrada["parte"],
            "trazo": round(visible, 2),
            "resto": round(circunferencia, 2),
            "desfase": round(-recorrido, 2),
        })
        recorrido += arco

    return {"sectores": sectores, "leyenda": leyenda, "total": total}


def _con_permanencia(fila):
    """Agrega a una fila del árbol sus dos cifras de permanencia.

    Son dos preguntas distintas y se parecen lo bastante como para confundirlas
    al leerlas rápido, así que cada una lleva su propia base:

    - `pct_desercion` / `pct_continuan` — DENTRO del periodo en curso: de los
      que llegaron a estar matriculados, cuántos se retiraron y cuántos siguen.
    - `pct_no_renovo` — ENTRE periodos: de los que cursaron el periodo
      anterior, cuántos no volvieron a esta misma promotoría.

    La segunda queda en None cuando no hay periodo anterior con datos, para que
    la plantilla escriba "sin referencia" en vez de un 0% que se leería como
    "no se fue nadie".

    Ojo con lo que mide la primera: una matrícula "retirada" es hoy tanto la de
    quien se fue como la de una solicitud que el profesor rechazó, porque las
    dos acaban en el mismo estado. Mientras eso siga así, la cifra de deserción
    incluye rechazos.
    """
    dentro = fila["total"] + fila["retirados"]
    fila["pct_desercion"] = round(fila["retirados"] / dentro * 100) if dentro else 0
    fila["pct_continuan"] = 100 - fila["pct_desercion"] if dentro else 0
    base = fila["base_renovacion"]
    fila["pct_no_renovo"] = round(fila["no_renovaron"] / base * 100) if base else None
    return fila


def _stats_choices(encuesta_qs, campo, choices, total_encuestas=None):
    """Conteo de un campo de la encuesta por cada opción declarada.

    Sustituye al viejo "top 5 de texto libre", que existía solo porque estos
    campos se escribían a mano: había que recortar a cinco porque la lista de
    valores distintos no tenía fin, y aun así «Bachillerato» y «bachiller»
    salían como dos filas.

    Respeta el orden en que están declaradas las choices en vez de ordenar por
    frecuencia: son escalas con un orden propio (de menos a más estudios, del
    estrato 1 al 6) y reordenarlas por popularidad haría ilegible la
    comparación entre un periodo y otro.

    Las opciones sin respuestas salen en cero en lugar de desaparecer, para que
    el panel enseñe siempre la misma lista y se vea qué NO contesta la gente.

    Con `total_encuestas`, la gente que no cae en ninguna opción se añade como
    una fila final de "Sin responder". **Esa fila no es decorativa y omitirla
    fue un error real**: las barras contaban solo a quien tenía un valor de la
    lista, así que una pregunta contestada por 2 de 5 personas se dibujaba
    entera, sin nada que avisara de las otras 3, y contradecía a la propia
    cabecera de la pantalla. Pasa con los campos opcionales y también con los
    obligatorios, porque la migración 0016 vació el texto libre de las
    encuestas anteriores al cambio a listas cerradas.

    Es la misma cuenta que ya hacía `_torta` y la misma regla del sistema de
    diseño: el todo es la población, no la suma de respuestas. Se omite el
    argumento cuando el resultado alimenta a `_torta`, que añade su propio
    sector gris y contaría dos veces esa fila.
    """
    conteos = {
        fila[campo]: fila["total"]
        for fila in encuesta_qs.values(campo).annotate(total=Count("id"))
    }
    filas = [
        {"etiqueta": etiqueta, "total": conteos.get(codigo, 0)}
        for codigo, etiqueta in choices
    ]

    if total_encuestas is not None:
        # Contra el total y no contra los vacíos: así también caen aquí los
        # valores que no están en la lista (texto libre de antes de la 0016),
        # que si no desaparecerían sin dejar rastro en ninguna fila.
        sin_responder = max(0, total_encuestas - sum(f["total"] for f in filas))
        if sin_responder:
            filas.append({
                "etiqueta": "Sin responder",
                "total": sin_responder,
                "sin_responder": True,
            })

    return _con_porcentaje(filas)


@requiere_rol("administrador")
def estadisticas(request):
    """Panel de estadísticas — solo administrador (ver visibilidad por rol en models.py):
    matrícula por departamento/promotoría/periodo, grupos por nivel, y la
    encuesta demográfica agregada (nunca datos de una persona identificable).
    """
    matriculas_activas = Matricula.objects.filter(estado="activa")

    periodo_actual = Periodo.en_curso()
    periodo_previo = (
        Periodo.objects.filter(fecha_inicio__lt=periodo_actual.fecha_inicio)
        .order_by("-fecha_inicio").first()
        if periodo_actual else None
    )

    # Quién NO volvió: estudiantes con matrícula activa en el periodo anterior
    # que no tienen ninguna viva en el actual, contados por promotoría. Se
    # resuelve aquí arriba, de una vez para todas las promotorías, en lugar de
    # una consulta por fila del árbol.
    no_renovaron = {}
    base_renovacion = {}
    if periodo_actual and periodo_previo:
        siguen = set(
            Matricula.objects.filter(periodo=periodo_actual)
            .exclude(estado="retirada")
            .values_list("estudiante_id", "promotoria_id")
        )
        for estudiante_id, promotoria_id in Matricula.objects.filter(
            periodo=periodo_previo, estado="activa",
        ).values_list("estudiante_id", "promotoria_id"):
            base_renovacion[promotoria_id] = base_renovacion.get(promotoria_id, 0) + 1
            if (estudiante_id, promotoria_id) not in siguen:
                no_renovaron[promotoria_id] = no_renovaron.get(promotoria_id, 0) + 1

    # Árbol Departamento → Promotoría: una sola estructura responde "por
    # departamento" y "por promotoría" a la vez, en vez de dos listas planas
    # que repetirían la misma información dos veces.
    #
    # Se acota al PERIODO EN CURSO, y eso es nuevo: antes sumaba las activas de
    # todos los periodos a la vez. Sin acotar, las dos cifras de permanencia no
    # significarían nada — mezclarían a quien se retiró hace tres años con quien
    # sigue yendo esta semana. El desglose histórico vive en "Estudiantes por
    # periodo", justo debajo.
    departamentos = {}
    orden_departamentos = []
    filas_promotoria = (
        Matricula.objects.filter(periodo=periodo_actual)
        .exclude(estado="pendiente")
        .values("promotoria_id", "promotoria__nombre", "promotoria__area_id", "promotoria__area__nombre")
        .annotate(
            # "Continúan" incluye las cancelaciones en trámite: mientras nadie
            # las apruebe, esa gente sigue inscrita.
            continuan=Count("id", filter=Q(estado__in=Matricula.ESTADOS_INSCRITO)),
            retirados=Count("id", filter=Q(estado="retirada")),
        )
        .order_by("promotoria__area__nombre", "-continuan")
    ) if periodo_actual else []

    for fila in filas_promotoria:
        area_id = fila["promotoria__area_id"]
        promotoria_id = fila["promotoria_id"]
        if area_id not in departamentos:
            departamentos[area_id] = {
                # Para el id del <details>: es lo que lo deja abierto cuando la
                # página se vuelve a pintar sin recargar (ver base.html).
                "id": area_id,
                "nombre": fila["promotoria__area__nombre"],
                "tag_class": f"tag-{area_id % 8}",
                "total": 0, "retirados": 0,
                "base_renovacion": 0, "no_renovaron": 0,
                "promotorias": [],
            }
            orden_departamentos.append(area_id)

        departamento = departamentos[area_id]
        departamento["total"] += fila["continuan"]
        departamento["retirados"] += fila["retirados"]
        departamento["base_renovacion"] += base_renovacion.get(promotoria_id, 0)
        departamento["no_renovaron"] += no_renovaron.get(promotoria_id, 0)
        departamento["promotorias"].append({
            "etiqueta": fila["promotoria__nombre"],
            "total": fila["continuan"],
            "retirados": fila["retirados"],
            "base_renovacion": base_renovacion.get(promotoria_id, 0),
            "no_renovaron": no_renovaron.get(promotoria_id, 0),
        })

    arbol_departamentos = [departamentos[area_id] for area_id in orden_departamentos]
    arbol_departamentos.sort(key=lambda d: -d["total"])
    arbol_departamentos = _con_porcentaje(arbol_departamentos)
    for departamento in arbol_departamentos:
        departamento["promotorias"] = _con_porcentaje(departamento["promotorias"])
        _con_permanencia(departamento)
        for promotoria in departamento["promotorias"]:
            _con_permanencia(promotoria)

    nivel_labels = dict(Grupo.NIVELES)
    grupos_por_curso = _con_porcentaje([
        {"etiqueta": nivel_labels.get(fila["nivel"], fila["nivel"]), "total": fila["total"]}
        for fila in Grupo.objects.values("nivel").annotate(total=Count("id")).order_by("nivel")
    ])

    estudiantes_por_periodo = _con_porcentaje([
        {"etiqueta": fila["periodo__nombre"], "total": fila["total"]}
        for fila in matriculas_activas.values("periodo__nombre", "periodo__fecha_inicio")
            .annotate(total=Count("id")).order_by("-periodo__fecha_inicio")
    ])

    encuesta_qs = EncuestaDemografica.objects.all()
    total_encuestas = encuesta_qs.count()

    # Tener encuesta no es tenerla contestada: las anteriores a la migración
    # 0016 perdieron nivel educativo y ocupación al pasar esos campos a listas
    # cerradas. La cuenta se hace en Python porque `estrato` es entero y un
    # filtro de "vacío" que sirva para texto y para número a la vez sale peor
    # que recorrer una tabla que tiene una fila por persona.
    encuestas_incompletas = sum(1 for encuesta in encuesta_qs if not encuesta.esta_completa)

    # Todas las escalas de la encuesta pasan por el mismo helper para que el
    # panel entero se lea igual. Género pierde con esto su orden por frecuencia
    # y pasa al de la lista, como el resto: dentro de un mismo panel, dos
    # criterios de orden distintos solo invitan a leer mal una gráfica.
    # Género va sin `total_encuestas` porque termina en una torta, que pone su
    # propio sector de "sin responder".
    genero_stats = _stats_choices(encuesta_qs, "genero", EncuestaDemografica.GENEROS)
    estrato_stats = _stats_choices(
        encuesta_qs, "estrato",
        [(valor, f"Estrato {etiqueta}") for valor, etiqueta in EncuestaDemografica.ESTRATOS],
        total_encuestas,
    )

    autoriza_si = encuesta_qs.filter(autoriza_tratamiento_datos=True).count()
    autoriza_no = total_encuestas - autoriza_si
    pct_autoriza_si = round((autoriza_si / total_encuestas) * 100) if total_encuestas else 0

    return render(request, "matriculas/gestion_estadisticas.html", {
        "arbol_departamentos": arbol_departamentos,
        "periodo_actual": periodo_actual,
        "periodo_previo": periodo_previo,
        "grupos_por_curso": grupos_por_curso,
        "estudiantes_por_periodo": estudiantes_por_periodo,
        "total_estudiantes_activos": matriculas_activas.values("estudiante").distinct().count(),
        "total_promotorias": Promotoria.objects.count(),
        "total_grupos": Grupo.objects.count(),
        "total_encuestas": total_encuestas,
        "encuestas_incompletas": encuestas_incompletas,
        "total_con_rol": Perfil.objects.exclude(rol="").count(),
        # Género y zona van en torta y no en barras: en las dos la pregunta es
        # qué parte del total es cada opción, y son pocas (4 y 3). El resto de
        # escalas sigue en barras, que es lo correcto para comparar magnitudes
        # y para escalas con orden propio como el estrato o el nivel educativo,
        # donde una torta obligaría a comparar ángulos parecidos.
        "genero_torta": _torta(genero_stats, total_encuestas),
        "zona_torta": _torta(
            _stats_choices(encuesta_qs, "zona", EncuestaDemografica.ZONAS),
            total_encuestas,
        ),
        "estrato_stats": estrato_stats,
        "autoriza_si": autoriza_si,
        "autoriza_no": autoriza_no,
        "pct_autoriza_si": pct_autoriza_si,
        "pct_autoriza_no": 100 - pct_autoriza_si,
        "nivel_educativo_stats": _stats_choices(
            encuesta_qs, "nivel_educativo", EncuestaDemografica.NIVELES_EDUCATIVOS,
            total_encuestas),
        "ocupacion_stats": _stats_choices(
            encuesta_qs, "ocupacion", EncuestaDemografica.OCUPACIONES,
            total_encuestas),
        "afiliacion_salud_stats": _stats_choices(
            encuesta_qs, "afiliacion_salud", EncuestaDemografica.AFILIACIONES_SALUD,
            total_encuestas),
        "grupo_etnico_stats": _stats_choices(
            encuesta_qs, "grupo_etnico", EncuestaDemografica.GRUPOS_ETNICOS,
            total_encuestas),
        "discapacidad_stats": _stats_choices(
            encuesta_qs, "discapacidad", EncuestaDemografica.DISCAPACIDADES,
            total_encuestas),
        "victima_conflicto_stats": _stats_choices(
            encuesta_qs, "victima_conflicto_armado", EncuestaDemografica.VICTIMAS_CONFLICTO,
            total_encuestas),
    })


# ---------------------------------------------------------------------------
# Área
# ---------------------------------------------------------------------------

class AreaListView(RolGestionRequiredMixin, ListView):
    model = Area
    template_name = "matriculas/gestion_lista.html"
    extra_context = {
        "titulo": "Departamentos",
        "url_nuevo": "area_nueva", "url_editar": "area_editar", "url_eliminar": "area_eliminar",
        "url_fila": "promotorias_por_area", "etiqueta_singular": "promotoría", "etiqueta_plural": "promotorías",
        "mostrar_tag_area": True,
    }

    def get_queryset(self):
        return Area.objects.annotate(total_hijos=Count("promotorias", distinct=True)).order_by("nombre")


class AreaCreateView(RolGestionRequiredMixin, CreateView):
    model = Area
    fields = ["nombre"]
    template_name = "matriculas/gestion_form.html"
    success_url = reverse_lazy("area_lista")
    extra_context = {"titulo": "Nueva área", "url_lista": "area_lista"}

    def form_valid(self, form):
        messages.success(self.request, "Área creada.")
        return super().form_valid(form)


class AreaUpdateView(RolGestionRequiredMixin, UpdateView):
    model = Area
    fields = ["nombre"]
    template_name = "matriculas/gestion_form.html"
    success_url = reverse_lazy("area_lista")
    extra_context = {"titulo": "Editar área", "url_lista": "area_lista"}

    def form_valid(self, form):
        messages.success(self.request, "Área actualizada.")
        return super().form_valid(form)


class AreaDeleteView(RolGestionRequiredMixin, BorradoProtegidoMixin, DeleteView):
    model = Area
    template_name = "matriculas/gestion_confirma_borrado.html"
    success_url = reverse_lazy("area_lista")
    extra_context = {"url_lista": "area_lista"}


# ---------------------------------------------------------------------------
# Periodo
# ---------------------------------------------------------------------------

class PeriodoListView(RolGestionRequiredMixin, ListView):
    model = Periodo
    template_name = "matriculas/gestion_lista.html"
    extra_context = {"titulo": "Periodos", "url_nuevo": "periodo_nuevo", "url_editar": "periodo_editar", "url_eliminar": "periodo_eliminar"}

    def get_queryset(self):
        return Periodo.objects.order_by("-fecha_inicio")


class PeriodoCreateView(RolGestionRequiredMixin, CreateView):
    model = Periodo
    # `activo` NO va en el formulario: solo puede haber un periodo en curso, así
    # que marcarlo aquí chocaría contra la restricción sin salida posible.
    # Cambiar el periodo en curso es una acción propia, en Gestión → Iniciar /
    # finalizar matrículas, que desactiva el anterior en la misma transacción.
    fields = ["nombre", "fecha_inicio", "fecha_fin"]
    template_name = "matriculas/gestion_form.html"
    success_url = reverse_lazy("periodo_lista")
    extra_context = {"titulo": "Nuevo periodo", "url_lista": "periodo_lista"}

    def form_valid(self, form):
        messages.success(self.request, "Periodo creado.")
        return super().form_valid(form)


class PeriodoUpdateView(RolGestionRequiredMixin, UpdateView):
    model = Periodo
    # `activo` NO va en el formulario: solo puede haber un periodo en curso, así
    # que marcarlo aquí chocaría contra la restricción sin salida posible.
    # Cambiar el periodo en curso es una acción propia, en Gestión → Iniciar /
    # finalizar matrículas, que desactiva el anterior en la misma transacción.
    fields = ["nombre", "fecha_inicio", "fecha_fin"]
    template_name = "matriculas/gestion_form.html"
    success_url = reverse_lazy("periodo_lista")
    extra_context = {"titulo": "Editar periodo", "url_lista": "periodo_lista"}

    def form_valid(self, form):
        messages.success(self.request, "Periodo actualizado.")
        return super().form_valid(form)


class PeriodoDeleteView(RolGestionRequiredMixin, BorradoProtegidoMixin, DeleteView):
    model = Periodo
    template_name = "matriculas/gestion_confirma_borrado.html"
    success_url = reverse_lazy("periodo_lista")
    extra_context = {"url_lista": "periodo_lista"}


# ---------------------------------------------------------------------------
# Promotoría
# ---------------------------------------------------------------------------

class PromotoriaListView(RolGestionRequiredMixin, ListView):
    model = Promotoria
    template_name = "matriculas/gestion_lista.html"
    extra_context = {
        "titulo": "Promotorías", "url_nuevo": "promotoria_nueva",
        "url_editar": "promotoria_editar", "url_eliminar": "promotoria_eliminar",
        "url_fila": "grupos_por_promotoria", "etiqueta_singular": "grupo", "etiqueta_plural": "grupos",
        # Quién dicta cada una. `gestion_lista.html` sirve a cuatro catálogos y
        # solo las promotorías tienen profesor, así que va por bandera y no
        # metido en la plantilla para todos.
        "mostrar_profesor": True,
        "etiqueta_protegido": "matrículas",
    }

    def get_queryset(self):
        return Promotoria.objects.select_related("area", "profesor").annotate(
            total_hijos=Count("grupos", distinct=True),
            # Las matrículas son PROTECT y ninguna se borra al terminar el
            # periodo, así que aquí van TODAS —retiradas incluidas—: son
            # exactamente las que harán fallar el borrado.
            total_protegido=Count("matriculas", distinct=True),
        ).order_by("area__nombre", "nombre")


class PromotoriasPorAreaView(RolGestionRequiredMixin, ListView):
    """Promotorías de un solo departamento (llegando desde Departamentos)."""
    model = Promotoria
    template_name = "matriculas/gestion_lista.html"

    def get_queryset(self):
        self.area = get_object_or_404(Area, pk=self.kwargs["area_id"])
        return Promotoria.objects.filter(area=self.area).select_related("profesor").annotate(
            total_hijos=Count("grupos", distinct=True),
            total_protegido=Count("matriculas", distinct=True),
        ).order_by("nombre")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update({
            "titulo": f"Promotorías de {self.area.nombre}",
            "url_nuevo": "promotoria_nueva", "url_editar": "promotoria_editar", "url_eliminar": "promotoria_eliminar",
            "url_fila": "grupos_por_promotoria", "etiqueta_singular": "grupo", "etiqueta_plural": "grupos",
            "mostrar_profesor": True,
            "etiqueta_protegido": "matrículas",
            "preset_campo": "area", "preset_valor": self.area.pk,
            "migas": [{"texto": "Departamentos", "url": reverse("area_lista")}],
        })
        return ctx


class PromotoriaCreateView(RolGestionRequiredMixin, CreateView):
    model = Promotoria
    fields = ["nombre", "area", "profesor"]
    template_name = "matriculas/gestion_form.html"
    extra_context = {"titulo": "Nueva promotoría", "url_lista": "promotoria_lista"}

    def get_initial(self):
        initial = super().get_initial()
        area_id = self.request.GET.get("area")
        if area_id:
            initial["area"] = area_id
        return initial

    def get_success_url(self):
        return reverse("promotorias_por_area", args=[self.object.area_id])

    def form_valid(self, form):
        messages.success(self.request, "Promotoría creada.")
        return super().form_valid(form)


class PromotoriaUpdateView(RolGestionRequiredMixin, UpdateView):
    model = Promotoria
    fields = ["nombre", "area", "profesor"]
    template_name = "matriculas/gestion_form.html"
    extra_context = {"titulo": "Editar promotoría", "url_lista": "promotoria_lista"}

    def get_success_url(self):
        return reverse("promotorias_por_area", args=[self.object.area_id])

    def form_valid(self, form):
        messages.success(self.request, "Promotoría actualizada.")
        return super().form_valid(form)


class PromotoriaDeleteView(RolGestionRequiredMixin, BorradoProtegidoMixin, DeleteView):
    model = Promotoria
    template_name = "matriculas/gestion_confirma_borrado.html"
    extra_context = {"url_lista": "promotoria_lista"}

    def get_success_url(self):
        return reverse("promotorias_por_area", args=[self.object.area_id])


# ---------------------------------------------------------------------------
# Grupo
# ---------------------------------------------------------------------------

class GrupoListView(RolGestionRequiredMixin, ListView):
    model = Grupo
    template_name = "matriculas/gestion_lista.html"
    extra_context = {
        "titulo": "Grupos", "url_nuevo": "grupo_nuevo", "url_editar": "grupo_editar", "url_eliminar": "grupo_eliminar",
        "url_fila": "grupo_estudiantes", "etiqueta_singular": "estudiante", "etiqueta_plural": "estudiantes",
        "etiqueta_protegido": "matrículas",
    }

    def get_queryset(self):
        return Grupo.objects.select_related("promotoria", "promotoria__area").annotate(
            total_hijos=Count("matriculas", distinct=True, filter=Q(matriculas__estado="activa")),
            # Ojo a la diferencia con la de arriba: la de al lado del nombre
            # cuenta estudiantes ACTIVOS, y un grupo del que todos se retiraron
            # muestra cero y aun así no se deja borrar. Esta cuenta todas.
            total_protegido=Count("matriculas", distinct=True),
        ).order_by("promotoria__area__nombre", "promotoria__nombre", "nivel")


class GruposPorPromotoriaView(RolGestionRequiredMixin, ListView):
    """Grupos de una sola promotoría (llegando desde su departamento)."""
    model = Grupo
    template_name = "matriculas/gestion_lista.html"

    def get_queryset(self):
        self.promotoria = get_object_or_404(Promotoria.objects.select_related("area"), pk=self.kwargs["promotoria_id"])
        return Grupo.objects.filter(promotoria=self.promotoria).annotate(
            total_hijos=Count("matriculas", distinct=True, filter=Q(matriculas__estado="activa")),
            total_protegido=Count("matriculas", distinct=True),
        ).order_by("nivel")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update({
            "titulo": f"Grupos de {self.promotoria.nombre}",
            "url_nuevo": "grupo_nuevo", "url_editar": "grupo_editar", "url_eliminar": "grupo_eliminar",
            "url_fila": "grupo_estudiantes", "etiqueta_singular": "estudiante", "etiqueta_plural": "estudiantes",
            "etiqueta_protegido": "matrículas",
            "preset_campo": "promotoria", "preset_valor": self.promotoria.pk,
            "migas": [
                {"texto": "Departamentos", "url": reverse("area_lista")},
                {"texto": self.promotoria.area.nombre, "url": reverse("promotorias_por_area", args=[self.promotoria.area_id])},
            ],
        })
        return ctx


class GrupoCreateView(RolGestionRequiredMixin, CreateView):
    model = Grupo
    fields = ["promotoria", "nivel", "horario", "salon", "cupo_maximo"]
    template_name = "matriculas/gestion_form.html"
    extra_context = {"titulo": "Nuevo grupo", "url_lista": "grupo_lista"}

    def get_initial(self):
        initial = super().get_initial()
        promotoria_id = self.request.GET.get("promotoria")
        if promotoria_id:
            initial["promotoria"] = promotoria_id
        return initial

    def get_success_url(self):
        return reverse("grupos_por_promotoria", args=[self.object.promotoria_id])

    def form_valid(self, form):
        messages.success(self.request, "Grupo creado.")
        return super().form_valid(form)


class GrupoUpdateView(RolGestionRequiredMixin, UpdateView):
    model = Grupo
    fields = ["promotoria", "nivel", "horario", "salon", "cupo_maximo"]
    template_name = "matriculas/gestion_form.html"
    extra_context = {"titulo": "Editar grupo", "url_lista": "grupo_lista"}

    def get_success_url(self):
        return reverse("grupos_por_promotoria", args=[self.object.promotoria_id])

    def form_valid(self, form):
        messages.success(self.request, "Grupo actualizado.")
        return super().form_valid(form)


class GrupoDeleteView(RolGestionRequiredMixin, BorradoProtegidoMixin, DeleteView):
    model = Grupo
    template_name = "matriculas/gestion_confirma_borrado.html"
    extra_context = {"url_lista": "grupo_lista"}

    def get_success_url(self):
        return reverse("grupos_por_promotoria", args=[self.object.promotoria_id])


@requiere_rol(*ROLES_GESTION)
def grupo_estudiantes(request, grupo_id):
    """Roster de estudiantes activos matriculados en un grupo (solo lectura)."""
    grupo = get_object_or_404(
        Grupo.objects.select_related("promotoria", "promotoria__area"), pk=grupo_id
    )
    matriculas = Matricula.objects.filter(
        grupo=grupo, estado__in=Matricula.ESTADOS_INSCRITO,
    ).select_related(
        "estudiante", "estudiante__datos_estudiante", "estudiante__datos_estudiante__acudiente"
    )
    migas = [
        {"texto": "Departamentos", "url": reverse("area_lista")},
        {"texto": grupo.promotoria.area.nombre, "url": reverse("promotorias_por_area", args=[grupo.promotoria.area_id])},
        {"texto": grupo.promotoria.nombre, "url": reverse("grupos_por_promotoria", args=[grupo.promotoria_id])},
    ]
    return render(request, "matriculas/gestion_grupo_estudiantes.html", {
        "grupo": grupo,
        "estudiantes": [_ficha_estudiante(m) for m in matriculas],
        "migas": migas,
    })


# ---------------------------------------------------------------------------
# Usuarios (User + Perfil + DatosEstudiante/Acudiente si aplica)
# ---------------------------------------------------------------------------

# Valor del filtro de rol que pide justamente a los que NO tienen rol. Hace
# falta un centinela porque el "sin rol" real es la cadena vacía, y esa ya
# significa "no filtres por rol" en un formulario GET.
ROL_PENDIENTE = "__sin__"


class UsuarioListView(RolGestionRequiredMixin, ListView):
    """Listado de usuarios, filtrable por rol y por dónde está la persona.

    Los tres filtros de catálogo (departamento, promotoría, grupo) no se
    resuelven igual para todos los roles, porque la gente se relaciona con una
    promotoría de dos maneras distintas: el estudiante porque está matriculado
    en ella, el profesor porque la dicta. Filtrar por «Violín» devuelve las dos
    cosas —los matriculados y su profesor—, que es lo que uno espera al pedir
    «la gente de Violín». El filtro de grupo es la excepción: un grupo solo
    tiene estudiantes, así que ahí el profesor no aparece.

    Director y administrador no cuelgan de ninguna promotoría, así que
    cualquier filtro de catálogo los deja fuera. Es correcto, no un fallo: si
    alguien cruza rol=administrador con una promotoría, la lista sale vacía
    porque esa combinación no existe.

    Como la matrícula es por periodo, los filtros necesitan saber de cuál se
    habla. Se elige con un desplegable que arranca en el periodo en curso,
    igual que Gestión → Cupos. Las matrículas retiradas no cuentan: quien se
    retiró de Violín ya no es de Violín.
    """

    template_name = "matriculas/usuario_lista.html"

    def _periodo(self):
        """El periodo sobre el que se filtra: el pedido, o el que esté en curso.

        Siempre devuelve un periodo mientras exista alguno, y esa garantía
        importa: si devolviera None, la consulta dejaría de acotar por periodo
        y barrería el histórico entero mientras el desplegable enseña un
        periodo concreto seleccionado. Por eso un id inexistente en la URL no
        se queda en None, y por eso hay un último recurso al periodo más
        reciente para cuando el personal no ha marcado ninguno en curso.
        """
        pedido = self.request.GET.get("periodo")
        if pedido:
            elegido = Periodo.objects.filter(pk=pedido).first()
            if elegido is not None:
                return elegido
        return Periodo.en_curso() or Periodo.objects.order_by("-fecha_inicio").first()

    def _seleccion(self):
        """Los filtros pedidos, ya resueltos a objetos (None si no aplican)."""
        get = self.request.GET.get
        return {
            "rol": get("rol") or "",
            "area": Area.objects.filter(pk=get("area")).first() if get("area") else None,
            "promotoria": (
                Promotoria.objects.filter(pk=get("promotoria")).first()
                if get("promotoria") else None
            ),
            "grupo": Grupo.objects.filter(pk=get("grupo")).first() if get("grupo") else None,
            "periodo": self._periodo(),
        }

    def get_queryset(self):
        # Los pendientes de rol (rol="") quedan primero para que no se pierdan de vista.
        qs = Perfil.objects.select_related("usuario").order_by("rol", "nombre_completo")
        sel = self.seleccion = self._seleccion()

        if sel["rol"] == ROL_PENDIENTE:
            qs = qs.filter(rol="")
        elif sel["rol"]:
            qs = qs.filter(rol=sel["rol"])

        if not (sel["area"] or sel["promotoria"] or sel["grupo"]):
            return qs

        # Rama de estudiantes: se resuelve sobre Matricula y no con un filtro
        # encadenado sobre Perfil porque hay que excluir las retiradas DENTRO
        # de la misma matrícula. Encadenando `~Q(...)` sobre una relación de
        # varios valores, Django lo convierte en una subconsulta que descarta al
        # estudiante entero si tiene alguna retirada, aunque siga matriculado.
        matriculas = Matricula.objects.exclude(estado="retirada")
        if sel["periodo"] is not None:
            matriculas = matriculas.filter(periodo=sel["periodo"])
        if sel["grupo"] is not None:
            matriculas = matriculas.filter(grupo=sel["grupo"])
        if sel["promotoria"] is not None:
            matriculas = matriculas.filter(promotoria=sel["promotoria"])
        if sel["area"] is not None:
            matriculas = matriculas.filter(promotoria__area=sel["area"])
        condicion = Q(pk__in=matriculas.values("estudiante_id"))

        # Rama de profesores: solo cuando no se filtró por grupo (ver docstring).
        # Va por Promotoria y no por Matricula, porque el vínculo del profesor
        # con su promotoría no depende de que alguien se haya matriculado ni de
        # qué periodo se esté mirando.
        if sel["grupo"] is None:
            promotorias = Promotoria.objects.exclude(profesor__isnull=True)
            if sel["promotoria"] is not None:
                promotorias = promotorias.filter(pk=sel["promotoria"].pk)
            if sel["area"] is not None:
                promotorias = promotorias.filter(area=sel["area"])
            condicion |= Q(pk__in=promotorias.values("profesor_id"))

        return qs.filter(condicion)

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        sel = self.seleccion
        contexto.update({
            "seleccion": sel,
            "roles": Perfil.ROLES,
            "rol_pendiente": ROL_PENDIENTE,
            "areas": Area.objects.order_by("nombre"),
            # Agrupadas por área y por promotoría para poder pintarlas en
            # <optgroup>: la jerarquía del catálogo se ve en el desplegable sin
            # necesidad de recargar la página al elegir el departamento.
            "promotorias": Promotoria.objects.select_related("area").order_by(
                "area__nombre", "nombre",
            ),
            "grupos": Grupo.objects.select_related("promotoria").order_by(
                "promotoria__nombre", "nivel",
            ),
            "periodos": Periodo.objects.order_by("-activo", "-fecha_inicio"),
            "hay_filtros": bool(
                sel["rol"] or sel["area"] or sel["promotoria"] or sel["grupo"]
            ),
        })
        return contexto


def _guardar_datos_estudiante(perfil, datos, datos_estudiante_existente, acudiente_existente):
    acudiente = acudiente_existente
    if datos.get("acudiente_nombre"):
        if acudiente is None:
            acudiente = Acudiente(nombre="")
        acudiente.nombre = datos["acudiente_nombre"]
        acudiente.telefono = datos.get("acudiente_telefono", "")
        acudiente.save()

    datos_estudiante = datos_estudiante_existente or DatosEstudiante(perfil=perfil)
    datos_estudiante.documento_identidad = datos["documento_identidad"]
    if datos.get("copia_documento"):
        datos_estudiante.copia_documento = datos["copia_documento"]
    datos_estudiante.acudiente = acudiente
    datos_estudiante.full_clean()
    datos_estudiante.save()


@requiere_rol(*ROLES_GESTION)
def usuario_nuevo(request):
    if request.method == "POST":
        form = UsuarioForm(request.POST, request.FILES, es_creacion=True)
        if form.is_valid():
            datos = form.cleaned_data
            try:
                with transaction.atomic():
                    user = User.objects.create_user(username=datos["username"], password=datos["password"])
                    perfil = Perfil.objects.create(
                        usuario=user,
                        rol=datos["rol"],
                        nombre_completo=datos["nombre_completo"],
                        fecha_nacimiento=datos["fecha_nacimiento"],
                        telefono=datos["telefono"],
                        foto_perfil=datos["foto_perfil"],
                    )
                    if datos["rol"] == "estudiante":
                        _guardar_datos_estudiante(perfil, datos, None, None)
            except IntegrityError:
                messages.error(request, "Ya existe un usuario con ese nombre de usuario, o un estudiante con ese documento.")
            except ValidationError as exc:
                messages.error(request, " ".join(exc.messages))
            else:
                messages.success(request, "Usuario creado.")
                return redirect("usuario_lista")
    else:
        form = UsuarioForm(es_creacion=True)

    return render(request, "matriculas/usuario_form.html", {
        "form": form, "titulo": "Nuevo usuario", "es_creacion": True,
    })


@requiere_rol(*ROLES_GESTION)
def usuario_editar(request, perfil_id):
    perfil = get_object_or_404(Perfil, pk=perfil_id)
    datos_estudiante = getattr(perfil, "datos_estudiante", None)
    acudiente = datos_estudiante.acudiente if datos_estudiante else None

    if request.method == "POST":
        form = UsuarioForm(request.POST, request.FILES, es_creacion=False)
        if form.is_valid():
            datos = form.cleaned_data
            try:
                with transaction.atomic():
                    user = perfil.usuario
                    user.username = datos["username"]
                    if datos.get("password"):
                        user.set_password(datos["password"])
                    user.save()

                    perfil.rol = datos["rol"]
                    perfil.nombre_completo = datos["nombre_completo"]
                    perfil.fecha_nacimiento = datos["fecha_nacimiento"]
                    perfil.telefono = datos["telefono"]
                    if datos.get("foto_perfil"):
                        perfil.foto_perfil = datos["foto_perfil"]
                    perfil.save()

                    if datos["rol"] == "estudiante":
                        _guardar_datos_estudiante(perfil, datos, datos_estudiante, acudiente)
            except IntegrityError:
                messages.error(request, "Ya existe un usuario con ese nombre de usuario, o un estudiante con ese documento.")
            except ValidationError as exc:
                messages.error(request, " ".join(exc.messages))
            else:
                messages.success(request, "Usuario actualizado.")
                return redirect("usuario_lista")
    else:
        inicial = {
            "username": perfil.usuario.username,
            "rol": perfil.rol,
            "nombre_completo": perfil.nombre_completo,
            "fecha_nacimiento": perfil.fecha_nacimiento,
            "telefono": perfil.telefono,
        }
        if datos_estudiante:
            inicial["documento_identidad"] = datos_estudiante.documento_identidad
        if acudiente:
            inicial["acudiente_nombre"] = acudiente.nombre
            inicial["acudiente_telefono"] = acudiente.telefono
        form = UsuarioForm(initial=inicial, es_creacion=False)

    return render(request, "matriculas/usuario_form.html", {
        "form": form, "titulo": f"Editar a {perfil.nombre_completo}", "es_creacion": False, "perfil": perfil,
    })


@requiere_rol(*ROLES_GESTION)
def usuario_alternar_activo(request, perfil_id):
    if request.method != "POST":
        return redirect("usuario_lista")

    perfil = get_object_or_404(Perfil, pk=perfil_id)
    user = perfil.usuario
    if user == request.user:
        messages.error(request, "No puedes desactivar tu propia cuenta.")
        return redirect("usuario_lista")

    user.is_active = not user.is_active
    user.save(update_fields=["is_active"])
    messages.success(request, f"Cuenta {'activada' if user.is_active else 'desactivada'}.")
    return redirect("usuario_lista")
