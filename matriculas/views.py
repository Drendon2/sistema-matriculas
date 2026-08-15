from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from django.contrib.auth.models import User

from .forms import (
    CopiaDocumentoForm,
    DatosContactoForm,
    EncuestaDemograficaForm,
    EncuestaSatisfaccionForm,
    FotoPerfilForm,
    GrupoForm,
    InscripcionEstudianteForm,
    RegistroForm,
)
from .models import (
    Acudiente, ConfiguracionInstitucion, CupoPromotoria, DatosEstudiante,
    EncuestaSatisfaccion, Grupo, Matricula, Perfil, Periodo, Promotoria,
    historial_por_periodo, limite_promotorias, matriculas_renovables,
    resumen_trayectoria,
)

ROLES_PANEL = ("profesor", "director", "administrador")


def requiere_rol(*roles):
    """Exige login y que el Perfil del usuario tenga uno de los roles dados.

    Deja el Perfil en `request.perfil` para que la vista no tenga que
    volver a resolverlo.
    """
    def decorador(vista):
        @wraps(vista)
        @login_required
        def envoltorio(request, *args, **kwargs):
            perfil = getattr(request.user, "perfil", None)
            if perfil is None:
                messages.error(request, "Tu cuenta no tiene un perfil asociado. Contacta al administrador.")
                return redirect("login")
            if perfil.rol not in roles:
                messages.error(request, "No tienes acceso a esta sección.")
                return redirect("post_login_redirect")
            request.perfil = perfil
            return vista(request, *args, **kwargs)
        return envoltorio
    return decorador


@login_required
def post_login_redirect(request):
    """A dónde mandar a cada quién justo después de iniciar sesión."""
    perfil = getattr(request.user, "perfil", None)
    if perfil is None:
        messages.error(request, "Tu cuenta no tiene un perfil asociado. Contacta al administrador.")
        return redirect("login")
    if not perfil.rol:
        return redirect("pendiente_aprobacion")
    if perfil.rol == "estudiante":
        return redirect("promotorias_disponibles")
    return redirect("panel")


def registro(request):
    """Autorregistro público (pensado para profesores nuevos).

    La cuenta queda SIN rol: un director/administrador se lo asigna después
    desde Gestión de usuarios.
    """
    if request.method == "POST":
        form = RegistroForm(request.POST)
        if form.is_valid():
            datos = form.cleaned_data
            try:
                with transaction.atomic():
                    user = User.objects.create_user(username=datos["username"], password=datos["password"])
                    Perfil.objects.create(
                        usuario=user,
                        rol="",
                        nombre_completo=datos["nombre_completo"],
                        fecha_nacimiento=datos["fecha_nacimiento"],
                        telefono=datos["telefono"],
                    )
            except IntegrityError:
                messages.error(request, "Ya existe una cuenta con ese nombre de usuario.")
            else:
                messages.success(
                    request,
                    "Tu cuenta quedó creada. Un director o administrador debe asignarte un rol antes "
                    "de que puedas entrar al sistema. Cuando entres, ve a \"Mi perfil\" para subir tu foto.",
                )
                return redirect("login")
    else:
        form = RegistroForm()

    return render(request, "matriculas/registro.html", {"form": form})


def inscripcion(request):
    """Autorregistro de estudiante: crea la cuenta y la inscribe a una promotoría de una vez.

    La matrícula nace "pendiente"; el profesor de esa promotoría (o
    director/administrador) debe confirmarla antes de asignarle un grupo.

    No pide foto de perfil ni copia del documento (ver docstring de
    InscripcionEstudianteForm): quedan en blanco hasta que el estudiante las
    suba después, ya logueado, en "Mi perfil".
    """
    periodo = Periodo.en_curso()
    # La inscripción pública solo existe mientras las matrículas estén abiertas.
    abiertas = periodo is not None and periodo.matriculas_abiertas

    if request.method == "POST" and not abiertas:
        messages.error(request, "Las matrículas están cerradas en este momento.")
        return redirect("inscripcion")

    if request.method == "POST":
        form = InscripcionEstudianteForm(request.POST, periodo_activo=periodo)
        if form.is_valid():
            datos = form.cleaned_data
            try:
                with transaction.atomic():
                    user = User.objects.create_user(username=datos["username"], password=datos["password"])
                    perfil = Perfil.objects.create(
                        usuario=user,
                        rol="estudiante",
                        nombre_completo=datos["nombre_completo"],
                        fecha_nacimiento=datos["fecha_nacimiento"],
                        telefono=datos["telefono"],
                    )

                    acudiente = None
                    if datos.get("acudiente_nombre"):
                        acudiente = Acudiente.objects.create(
                            nombre=datos["acudiente_nombre"],
                            telefono=datos.get("acudiente_telefono", ""),
                        )

                    datos_estudiante = DatosEstudiante(
                        perfil=perfil,
                        documento_identidad=datos["documento_identidad"],
                        acudiente=acudiente,
                    )
                    datos_estudiante.full_clean()
                    datos_estudiante.save()

                    elegidas = form.promotorias_elegidas()

                    for promotoria_elegida in elegidas:
                        matricula = Matricula(
                            estudiante=perfil, promotoria=promotoria_elegida,
                            periodo=periodo, estado="pendiente",
                        )
                        matricula.full_clean()
                        matricula.save()
            except IntegrityError as exc:
                if _constraint_violada(exc) == "cupo_promotoria_disponible":
                    messages.error(
                        request,
                        "Una de las promotorías que elegiste se llenó mientras enviabas el "
                        "formulario. No se creó la cuenta: vuelve a intentarlo eligiendo otra.",
                    )
                else:
                    messages.error(
                        request,
                        "Ya existe una cuenta con ese usuario, o un estudiante con ese documento de identidad.",
                    )
            except ValidationError as exc:
                messages.error(request, " ".join(exc.messages))
            else:
                nombres = ", ".join(str(p) for p in elegidas)
                plural = "tus inscripciones a" if len(elegidas) > 1 else "tu inscripción a"
                messages.success(
                    request,
                    f"Tu cuenta quedó creada y {plural} {nombres} "
                    f"{'están' if len(elegidas) > 1 else 'está'} pendiente"
                    f"{'s' if len(elegidas) > 1 else ''} de confirmación del profesor. "
                    "Inicia sesión y ve a \"Mi perfil\" para subir tu foto y tu documento.",
                )
                return redirect("login")
    else:
        form = InscripcionEstudianteForm(periodo_activo=periodo)

    return render(request, "matriculas/inscripcion.html", {
        "form": form,
        "periodo": periodo,
        "matriculas_abiertas": abiertas,
    })


@login_required
def pendiente_aprobacion(request):
    perfil = getattr(request.user, "perfil", None)
    if perfil is not None and perfil.rol:
        return redirect("post_login_redirect")
    return render(request, "matriculas/pendiente_aprobacion.html")


# ---------------------------------------------------------------------------
# Estudiante: matrícula autoservicio
# ---------------------------------------------------------------------------

@requiere_rol("estudiante")
def promotorias_disponibles(request):
    """Promotorías del periodo activo en las que el estudiante se puede matricular.

    El estudiante NO elige grupo/horario aquí: eso lo reparte después el
    profesor entre los ya matriculados.
    """
    perfil = request.perfil
    periodo = Periodo.en_curso()
    abiertas = periodo is not None and periodo.matriculas_abiertas
    periodo_anterior, renovables = matriculas_renovables(perfil, periodo)
    promotorias = []
    cupos_usados = 0
    limite = limite_promotorias()
    if periodo is not None:
        mis_matriculas = {
            m.promotoria_id: m
            for m in Matricula.objects.filter(estudiante=perfil, periodo=periodo).exclude(estado="retirada")
        }
        cupos_usados = len(mis_matriculas)
        sin_cupo = cupos_usados >= limite
        for promotoria in Promotoria.objects.select_related("area", "profesor"):
            matricula = mis_matriculas.get(promotoria.id)
            maximo = promotoria.cupo_en(periodo)
            ocupados = promotoria.ocupados_en(periodo)
            promotorias.append({
                "promotoria": promotoria,
                "matricula": matricula,
                # Sin cupo propio libre, matricularse en una promotoría nueva queda bloqueado.
                "bloqueada": matricula is None and sin_cupo,
                "cupo": maximo,
                "ocupados": ocupados,
                # La promotoría está llena (solo aplica si tiene tope definido).
                "llena": matricula is None and maximo is not None and ocupados >= maximo,
            })

    return render(request, "matriculas/promotorias_disponibles.html", {
        "periodo": periodo,
        "promotorias": promotorias,
        "cupos_usados": cupos_usados,
        "cupos_limite": limite,
        "matriculas_abiertas": abiertas,
        "renovables": renovables,
        "periodo_anterior": periodo_anterior,
    })


@requiere_rol("estudiante")
def matricular(request, promotoria_id):
    if request.method != "POST":
        return redirect("promotorias_disponibles")

    perfil = request.perfil
    periodo = Periodo.en_curso()
    if periodo is None:
        messages.error(request, "No hay un periodo de matrícula activo en este momento.")
        return redirect("promotorias_disponibles")

    if not periodo.matriculas_abiertas:
        messages.error(
            request,
            f"Las matrículas de {periodo} están cerradas. Espera a que "
            f"{ConfiguracionInstitucion.actual().nombre_institucion} las abra de nuevo.",
        )
        return redirect("promotorias_disponibles")

    promotoria = get_object_or_404(Promotoria, pk=promotoria_id)

    datos_estudiante = getattr(perfil, "datos_estudiante", None)
    if datos_estudiante is None:
        messages.error(
            request,
            "Tu registro como estudiante no está completo (falta documento de identidad). "
            "Contacta al administrador.",
        )
        return redirect("promotorias_disponibles")

    if perfil.es_menor and datos_estudiante.acudiente is None:
        messages.error(
            request,
            "Eres menor de edad y no tienes un acudiente registrado. "
            "Pide al administrador que registre tu acudiente antes de matricularte.",
        )
        return redirect("promotorias_disponibles")

    # Si ya se retiró de esta promotoría en este periodo, se REACTIVA su
    # matrícula en vez de crear otra: `unica_matricula_por_periodo` no admite
    # una segunda fila para el mismo (estudiante, promotoría, periodo), y sin
    # esto el botón "Matricularme" de esa fila no llevaba a ninguna parte.
    # La fecha original se conserva; el estado vuelve a "pendiente" y el
    # profesor tiene que confirmarla de nuevo.
    matricula = Matricula.objects.filter(
        estudiante=perfil, promotoria=promotoria, periodo=periodo, estado="retirada",
    ).first()
    reactivada = matricula is not None
    if reactivada:
        matricula.estado = "pendiente"
        matricula.grupo = None
    else:
        matricula = Matricula(estudiante=perfil, promotoria=promotoria, periodo=periodo)

    try:
        with transaction.atomic():
            matricula.full_clean()
            matricula.save()
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    except IntegrityError as exc:
        if _constraint_violada(exc) == "cupo_promotoria_disponible":
            # Carrera real: la promotoría se llenó entre la validación y el guardado.
            messages.error(
                request,
                f"{promotoria} se llenó mientras enviabas la solicitud: alguien tomó el "
                f"último cupo de {periodo}. No quedó registrada.",
            )
        else:
            # Matrícula repetida en la misma promotoría, o el índice que limita
            # las promotorías por periodo si dos peticiones llegaron a la vez.
            messages.error(
                request,
                "No se pudo registrar la matrícula: o ya tienes una en esa promotoría este "
                f"periodo, o ya ocupas las {limite_promotorias()} promotorías permitidas. "
                "Revisa tus matrículas y vuelve a intentarlo.",
            )
    else:
        if reactivada:
            messages.success(
                request,
                f"Volviste a inscribirte en {promotoria}. Tu matrícula quedó otra vez "
                "pendiente de confirmación del profesor.",
            )
        else:
            messages.success(request, f"Tu inscripción a {promotoria} quedó pendiente de confirmación del profesor.")

    return redirect("promotorias_disponibles")


@requiere_rol("estudiante")
def renovar_matricula(request):
    """Renovación para estudiantes ANTIGUOS: encuesta de satisfacción + un botón.

    Quien ya cursó un periodo no vuelve a crear cuenta ni a llenar la encuesta
    demográfica; solo evalúa el periodo que terminó y confirma en qué
    promotorías sigue. Las matrículas nacen "pendiente", igual que cualquier
    otra: el profesor las confirma.
    """
    perfil = request.perfil
    periodo = Periodo.en_curso()
    periodo_anterior, renovables = matriculas_renovables(perfil, periodo)

    if periodo is None:
        messages.error(request, "No hay un periodo de matrícula activo en este momento.")
        return redirect("promotorias_disponibles")

    if not periodo.matriculas_abiertas:
        messages.error(
            request,
            f"Las matrículas de {periodo} están cerradas. Espera a que "
            f"{ConfiguracionInstitucion.actual().nombre_institucion} las abra de nuevo.",
        )
        return redirect("promotorias_disponibles")

    if not renovables:
        messages.error(
            request,
            "No tienes matrículas por renovar: o eres estudiante nuevo, o ya renovaste "
            "todo lo que cursaste el periodo anterior.",
        )
        return redirect("promotorias_disponibles")

    ya_respondio = EncuestaSatisfaccion.objects.filter(
        perfil=perfil, periodo=periodo_anterior
    ).exists()

    limite = limite_promotorias()
    cupos_usados = Matricula.promotorias_ocupadas(perfil.id, periodo.id)
    # Nunca negativo: si el administrador bajó el límite, quien ya estaba por
    # encima se queda sin cupos libres, no con un número en rojo.
    cupos_libres = max(0, limite - cupos_usados)

    # Un antiguo puede dejar una promotoría (o las dos) y entrar a otras: para
    # esas es un estudiante NUEVO, aunque no repita cuenta ni encuesta
    # demográfica. Aquí se le ofrece todo lo que no está ya cursando.
    ya_suyas = {m.promotoria_id for m in renovables} | set(
        Matricula.objects.filter(estudiante=perfil, periodo=periodo)
        .exclude(estado="retirada").values_list("promotoria_id", flat=True)
    )
    disponibles = []
    for promotoria in Promotoria.objects.select_related("area").order_by("area__nombre", "nombre"):
        if promotoria.id in ya_suyas:
            continue
        libres = promotoria.cupos_disponibles(periodo)
        disponibles.append({"promotoria": promotoria, "llena": libres is not None and libres <= 0})

    if request.method == "POST":
        form = EncuestaSatisfaccionForm(request.POST) if not ya_respondio else None
        elegidas = request.POST.getlist("promotoria")
        seleccionadas = [m for m in renovables if str(m.promotoria_id) in elegidas]

        # Promotorías nuevas: dos campos opcionales, sin repetir entre sí.
        ids_nuevas = []
        for campo in ("promotoria_nueva", "promotoria_nueva_2"):
            valor = (request.POST.get(campo) or "").strip()
            if valor and valor not in ids_nuevas:
                ids_nuevas.append(valor)
        nuevas = list(
            Promotoria.objects.filter(id__in=ids_nuevas).exclude(id__in=ya_suyas)
        )

        total = len(seleccionadas) + len(nuevas)
        errores = []
        if total == 0:
            errores.append(
                "No elegiste nada: marca al menos una promotoría para renovar o escoge una nueva."
            )
        if total > cupos_libres:
            errores.append(
                f"Solo te quedan {cupos_libres} cupo(s) libre(s) en este periodo y elegiste {total}."
            )
        if len(ids_nuevas) != len(nuevas):
            errores.append("Una de las promotorías nuevas que elegiste ya la estás cursando.")
        if form is not None and not form.is_valid():
            errores.append("Revisa las respuestas de la encuesta.")

        if not errores:
            try:
                with transaction.atomic():
                    if form is not None:
                        encuesta = form.save(commit=False)
                        encuesta.perfil = perfil
                        encuesta.periodo = periodo_anterior
                        encuesta.full_clean()
                        encuesta.save()

                    promotorias_finales = (
                        [m.promotoria for m in seleccionadas] + nuevas
                    )
                    for promotoria in promotorias_finales:
                        matricula = Matricula(
                            estudiante=perfil, promotoria=promotoria,
                            periodo=periodo, estado="pendiente",
                        )
                        matricula.full_clean()
                        matricula.save()
            except ValidationError as exc:
                messages.error(request, " ".join(exc.messages))
            except IntegrityError as exc:
                if _constraint_violada(exc) == "cupo_promotoria_disponible":
                    messages.error(
                        request,
                        "Una de las promotorías se llenó mientras enviabas la renovación. "
                        "No se registró: vuelve a intentarlo.",
                    )
                else:
                    messages.error(
                        request,
                        "No se pudo completar la renovación. Revisa tus matrículas y vuelve a intentarlo.",
                    )
            else:
                partes = []
                if seleccionadas:
                    partes.append("renovaste " + ", ".join(str(m.promotoria) for m in seleccionadas))
                if nuevas:
                    partes.append("entraste como nuevo a " + ", ".join(str(p) for p in nuevas))
                messages.success(
                    request,
                    "Listo: " + " y ".join(partes) +
                    ". Queda pendiente de confirmación del profesor.",
                )
                return redirect("mis_matriculas")
        else:
            for error in errores:
                messages.error(request, error)
    else:
        form = EncuestaSatisfaccionForm() if not ya_respondio else None

    return render(request, "matriculas/renovar_matricula.html", {
        "periodo": periodo,
        "periodo_anterior": periodo_anterior,
        "renovables": renovables,
        "disponibles": disponibles,
        "form": form,
        "ya_respondio": ya_respondio,
        "cupos_libres": cupos_libres,
        "cupos_limite": limite,
    })


@requiere_rol("estudiante")
def mis_matriculas(request):
    """El historial del estudiante: en qué promotorías está y en cuáles estuvo.

    Va agrupado por periodo y no como una lista plana por fecha, porque el
    periodo es la unidad en la que el estudiante piensa su paso por la casa
    ("el semestre pasado hice guitarra") y porque es lo que separa lo vigente
    —donde todavía puede retirarse— del historial ya cerrado.
    """
    perfil = request.perfil
    periodo = Periodo.en_curso()

    return render(request, "matriculas/mis_matriculas.html", {
        "historial": historial_por_periodo(perfil),
        "resumen": resumen_trayectoria(perfil),
        # Sin esto la plantilla no puede distinguir el periodo en curso de uno
        # terminado, y ofrecería "Retirarme" en matrículas ya cerradas.
        "periodo_actual_id": periodo.id if periodo else None,
    })


@requiere_rol("estudiante")
def retirar_matricula(request, matricula_id):
    if request.method != "POST":
        return redirect("mis_matriculas")

    matricula = get_object_or_404(Matricula, pk=matricula_id, estudiante=request.perfil)

    # Retirarse solo aplica al periodo en curso: un periodo terminado es
    # historial cerrado, no algo de lo que uno pueda salirse a posteriori.
    periodo = Periodo.en_curso()
    if periodo is None or matricula.periodo_id != periodo.id:
        messages.error(
            request,
            f"{matricula.periodo} ya terminó: sus matrículas quedan como historial y no se "
            "pueden retirar. Solo puedes retirarte de una matrícula del periodo en curso.",
        )
        return redirect("mis_matriculas")

    # Una matrícula que el profesor todavía no confirmó no es una deserción:
    # es una solicitud que el estudiante retira antes de que le respondan, y
    # obligarlo a esperar el visto bueno de un director para eso solo llenaría
    # la cola de la dirección. Se cancela en el acto.
    if matricula.estado == "pendiente":
        matricula.estado = "retirada"
        matricula.grupo = None
        matricula.save(update_fields=["estado", "grupo"])
        messages.success(
            request,
            f"Retiraste tu solicitud a {matricula.promotoria}. Como todavía no estaba "
            "confirmada, no hace falta que nadie la apruebe.",
        )
        return redirect("mis_matriculas")

    # Desde una matrícula ya activa, salirse pasa a ser una SOLICITUD: la
    # decisión es de un director o administrador (ver `gestion_cancelaciones`).
    # Hasta que la resuelvan, la matrícula sigue ocupando cupo y ranura, porque
    # el estudiante sigue inscrito.
    if matricula.estado == "activa":
        matricula.estado = Matricula.ESTADO_CANCELACION
        matricula.save(update_fields=["estado"])
        if matricula.cancelacion_es_rechazable:
            messages.success(
                request,
                f"Tu solicitud para cancelar {matricula.promotoria} quedó registrada. "
                "Como eres menor de edad, la dirección hablará con tu acudiente antes "
                "de resolverla; mientras tanto sigues inscrito.",
            )
        else:
            messages.success(
                request,
                f"Tu solicitud para cancelar {matricula.promotoria} quedó registrada. "
                "Sigues inscrito hasta que la dirección la tramite.",
            )

    return redirect("mis_matriculas")


@requiere_rol("estudiante")
def mis_companeros(request):
    """Nombre y foto de los compañeros de la MISMA promotoría (matrícula activa)."""
    mis_matriculas_activas = Matricula.objects.filter(
        estudiante=request.perfil, estado="activa"
    ).select_related("promotoria", "periodo")

    promotorias = []
    for matricula in mis_matriculas_activas:
        companeros = Perfil.objects.filter(
            matriculas__promotoria=matricula.promotoria,
            matriculas__periodo=matricula.periodo,
            matriculas__estado="activa",
        ).exclude(pk=request.perfil.pk).distinct()
        promotorias.append({"promotoria": matricula.promotoria, "companeros": companeros})

    return render(request, "matriculas/mis_companeros.html", {"promotorias": promotorias})


# ---------------------------------------------------------------------------
# Profesor / director / administrador: panel de promotorías, grupos y estudiantes
# ---------------------------------------------------------------------------

def _constraint_violada(exc):
    """Nombre de la restricción de base de datos que rechazó la escritura.

    Django envuelve el error del driver; el nombre viaja en el diagnóstico de
    psycopg. Devuelve None si el driver no lo expone, para que quien llame caiga
    en su mensaje genérico en vez de romperse.
    """
    causa = getattr(exc, "__cause__", None)
    diagnostico = getattr(causa, "diag", None)
    return getattr(diagnostico, "constraint_name", None)


def _puede_gestionar_promotoria(perfil, promotoria):
    return perfil.rol in ("director", "administrador") or (
        perfil.rol == "profesor" and promotoria.profesor_id == perfil.id
    )


def _ficha_estudiante(matricula):
    est = matricula.estudiante
    datos_est = getattr(est, "datos_estudiante", None)
    # ¿Ya cursó ESTA promotoría en otro periodo? Es lo que separa una renovación
    # de alguien que empieza de cero aquí, y es justo lo que el profesor necesita
    # saber para decidir en qué nivel de grupo lo ubica.
    renovacion = Matricula.objects.filter(
        estudiante_id=matricula.estudiante_id,
        promotoria_id=matricula.promotoria_id,
        estado="activa",
    ).exclude(periodo_id=matricula.periodo_id).exists()
    return {
        "matricula": matricula,
        "perfil": est,
        "acudiente": datos_est.acudiente if datos_est else None,
        "renovacion": renovacion,
        # El profesor se entera de que el estudiante está de salida, pero la
        # decisión no es suya: la marca es informativa y no trae botones.
        "cancelacion": matricula.cancelacion_pendiente,
    }


@requiere_rol(*ROLES_PANEL)
def panel(request):
    """Lista de promotorías con sus grupos y estudiantes matriculados.

    Visibilidad (ver docstring de matriculas/models.py): nombre, foto, edad,
    teléfono y acudiente son visibles para admin/director/profesor. La
    encuesta demográfica y la copia del documento NO se muestran aquí.

    El profesor (o director/administrador) puede crear/editar/eliminar los
    grupos de una promotoría y repartir ahí a los estudiantes matriculados
    que todavía no tienen grupo asignado.
    """
    perfil = request.perfil
    periodo = Periodo.objects.filter(activo=True).first()
    promotorias_qs = Promotoria.objects.select_related("area", "profesor").prefetch_related("grupos")
    if perfil.rol == "profesor":
        promotorias_qs = promotorias_qs.filter(profesor=perfil)

    datos = []
    for promotoria in promotorias_qs:
        grupos_info = []
        for grupo in promotoria.grupos.all():
            matriculas = grupo.matriculas.filter(
                estado__in=Matricula.ESTADOS_INSCRITO
            ).select_related(
                "estudiante", "estudiante__datos_estudiante", "estudiante__datos_estudiante__acudiente"
            )
            grupos_info.append({
                "grupo": grupo,
                "estudiantes": [_ficha_estudiante(m) for m in matriculas],
            })

        sin_grupo = Matricula.objects.filter(
            promotoria=promotoria, estado__in=Matricula.ESTADOS_INSCRITO, grupo__isnull=True
        ).select_related("estudiante", "estudiante__datos_estudiante", "estudiante__datos_estudiante__acudiente")

        pendientes = Matricula.objects.filter(
            promotoria=promotoria, estado="pendiente"
        ).select_related("estudiante", "estudiante__datos_estudiante", "estudiante__datos_estudiante__acudiente")

        datos.append({
            "promotoria": promotoria,
            "grupos": grupos_info,
            "sin_grupo": [_ficha_estudiante(m) for m in sin_grupo],
            "pendientes": [_ficha_estudiante(m) for m in pendientes],
            "puede_gestionar": _puede_gestionar_promotoria(perfil, promotoria),
            "cupo": promotoria.cupo_en(periodo),
            "ocupados": promotoria.ocupados_en(periodo),
        })

    return render(request, "matriculas/panel.html", {"datos": datos, "periodo": periodo})


@requiere_rol(*ROLES_PANEL)
def panel_cupo_promotoria(request, promotoria_id):
    """Fija (o quita) el cupo de una promotoría para el periodo activo.

    El profesor lo hace sobre las promotorías que dicta; director y
    administrador sobre cualquiera. Dejar el campo vacío quita el tope.
    """
    if request.method != "POST":
        return redirect("panel")

    promotoria = get_object_or_404(Promotoria, pk=promotoria_id)
    if not _puede_gestionar_promotoria(request.perfil, promotoria):
        messages.error(request, "No tienes acceso a esta promotoría.")
        return redirect("panel")

    periodo = Periodo.objects.filter(activo=True).first()
    if periodo is None:
        messages.error(request, "No hay un periodo de matrícula activo en este momento.")
        return redirect("panel")

    bruto = (request.POST.get("cupo_maximo") or "").strip()
    if bruto == "":
        CupoPromotoria.objects.filter(promotoria=promotoria, periodo=periodo).delete()
        messages.success(request, f"{promotoria} queda sin tope de cupos en {periodo}.")
        return redirect("panel")

    try:
        cupo = int(bruto)
    except ValueError:
        messages.error(request, "El cupo debe ser un número entero.")
        return redirect("panel")

    if cupo < 0:
        messages.error(request, "El cupo no puede ser negativo.")
        return redirect("panel")

    CupoPromotoria.objects.update_or_create(
        promotoria=promotoria, periodo=periodo, defaults={"cupo_maximo": cupo},
    )
    ocupados = promotoria.ocupados_en(periodo)
    if cupo < ocupados:
        # Bajar el cupo por debajo de lo ya ocupado es legítimo (el personal
        # puede necesitarlo), pero no se retira a nadie: solo se cierra la puerta.
        messages.error(
            request,
            f"Cupo de {promotoria} fijado en {cupo} para {periodo}, pero ya hay {ocupados} "
            "matrículas ocupando sitio. No se retiró a nadie: simplemente no entrarán "
            "estudiantes nuevos hasta que el número baje.",
        )
    else:
        messages.success(request, f"Cupo de {promotoria} fijado en {cupo} para {periodo}.")

    return redirect("panel")


@requiere_rol(*ROLES_PANEL)
def panel_grupo_nuevo(request, promotoria_id):
    promotoria = get_object_or_404(Promotoria, pk=promotoria_id)
    if not _puede_gestionar_promotoria(request.perfil, promotoria):
        messages.error(request, "No tienes acceso a esta promotoría.")
        return redirect("panel")

    if request.method == "POST":
        form = GrupoForm(request.POST)
        if form.is_valid():
            grupo = form.save(commit=False)
            grupo.promotoria = promotoria
            try:
                grupo.full_clean()
            except ValidationError as exc:
                for campo, errores in exc.message_dict.items():
                    for error in errores:
                        form.add_error(campo if campo in form.fields else None, error)
            else:
                grupo.save()
                messages.success(request, "Grupo creado.")
                return redirect("panel")
    else:
        form = GrupoForm()

    return render(request, "matriculas/panel_grupo_form.html", {
        "form": form, "promotoria": promotoria, "titulo": f"Nuevo grupo — {promotoria.nombre}",
    })


@requiere_rol(*ROLES_PANEL)
def panel_grupo_editar(request, grupo_id):
    grupo = get_object_or_404(Grupo, pk=grupo_id)
    if not _puede_gestionar_promotoria(request.perfil, grupo.promotoria):
        messages.error(request, "No tienes acceso a esta promotoría.")
        return redirect("panel")

    if request.method == "POST":
        form = GrupoForm(request.POST, instance=grupo)
        if form.is_valid():
            try:
                form.instance.full_clean()
            except ValidationError as exc:
                for campo, errores in exc.message_dict.items():
                    for error in errores:
                        form.add_error(campo if campo in form.fields else None, error)
            else:
                form.save()
                messages.success(request, "Grupo actualizado.")
                return redirect("panel")
    else:
        form = GrupoForm(instance=grupo)

    return render(request, "matriculas/panel_grupo_form.html", {
        "form": form, "promotoria": grupo.promotoria, "titulo": f"Editar grupo — {grupo}",
    })


@requiere_rol(*ROLES_PANEL)
def panel_grupo_eliminar(request, grupo_id):
    if request.method != "POST":
        return redirect("panel")

    grupo = get_object_or_404(Grupo, pk=grupo_id)
    if not _puede_gestionar_promotoria(request.perfil, grupo.promotoria):
        messages.error(request, "No tienes acceso a esta promotoría.")
        return redirect("panel")

    try:
        grupo.delete()
    except ProtectedError:
        messages.error(request, "No se puede eliminar: hay estudiantes con matrícula asignada a este grupo.")
    else:
        messages.success(request, "Grupo eliminado.")

    return redirect("panel")


@requiere_rol(*ROLES_PANEL)
def panel_confirmar_matricula(request, matricula_id):
    if request.method != "POST":
        return redirect("panel")

    matricula = get_object_or_404(Matricula, pk=matricula_id)
    if not _puede_gestionar_promotoria(request.perfil, matricula.promotoria):
        messages.error(request, "No tienes acceso a esta promotoría.")
        return redirect("panel")

    if matricula.estado == "pendiente":
        # El límite de promotorías por periodo también se aplica desde el panel:
        # no se confirma una matrícula que dejaría al estudiante por encima del tope.
        limite = limite_promotorias()
        ocupadas = Matricula.promotorias_ocupadas(
            matricula.estudiante_id, matricula.periodo_id, excluir_pk=matricula.pk
        )
        if ocupadas >= limite:
            permitidas = "la promotoría permitida" if limite == 1 else f"las {limite} promotorías permitidas"
            messages.error(
                request,
                f"{matricula.estudiante.nombre_completo} ya ocupa {permitidas} en este "
                "periodo. Retira una de sus matrículas antes de confirmar esta.",
            )
            return redirect("panel")

        matricula.estado = "activa"
        matricula.save(update_fields=["estado"])
        messages.success(request, f"Matrícula de {matricula.estudiante.nombre_completo} confirmada.")

    return redirect("panel")


@requiere_rol(*ROLES_PANEL)
def panel_rechazar_matricula(request, matricula_id):
    if request.method != "POST":
        return redirect("panel")

    matricula = get_object_or_404(Matricula, pk=matricula_id)
    if not _puede_gestionar_promotoria(request.perfil, matricula.promotoria):
        messages.error(request, "No tienes acceso a esta promotoría.")
        return redirect("panel")

    if matricula.estado == "pendiente":
        matricula.estado = "retirada"
        matricula.save(update_fields=["estado"])
        messages.success(request, f"Solicitud de {matricula.estudiante.nombre_completo} rechazada.")

    return redirect("panel")


@requiere_rol(*ROLES_PANEL)
def panel_asignar_grupo(request, matricula_id):
    if request.method != "POST":
        return redirect("panel")

    matricula = get_object_or_404(Matricula, pk=matricula_id)
    if not _puede_gestionar_promotoria(request.perfil, matricula.promotoria):
        messages.error(request, "No tienes acceso a esta promotoría.")
        return redirect("panel")

    grupo_id = request.POST.get("grupo_id") or None
    grupo = None
    if grupo_id:
        grupo = get_object_or_404(Grupo, pk=grupo_id, promotoria=matricula.promotoria)

    matricula.grupo = grupo
    try:
        matricula.full_clean()
        matricula.save()
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        if grupo:
            messages.success(request, f"{matricula.estudiante.nombre_completo} fue asignado a {grupo}.")
        else:
            messages.success(request, f"{matricula.estudiante.nombre_completo} quedó sin grupo asignado.")

    return redirect("panel")


def _puede_ver_ficha(solicitante, objetivo):
    """Quién puede abrir la ficha de quién: se mira hacia abajo, no hacia los lados.

    Administrador y director abren la de cualquiera. El profesor solo la de
    estudiantes — ni la de otro profesor, ni la de un director, ni la de un
    administrador. Un estudiante no abre ninguna: sus pantallas siguen
    mostrando los nombres como texto (ver `mis_companeros`).
    """
    if solicitante.rol in ("administrador", "director"):
        return True
    if solicitante.rol == "profesor":
        return objetivo.rol == "estudiante"
    return False


def _profesor_tiene_al_estudiante(profesor, estudiante):
    """¿El estudiante cursa alguna promotoría de este profesor (sin retirar)?"""
    return Matricula.objects.filter(
        estudiante=estudiante, promotoria__profesor=profesor,
    ).exclude(estado="retirada").exists()


@requiere_rol(*ROLES_PANEL)
def detalle_usuario(request, perfil_id):
    """Ficha de una persona, sea cual sea su rol — el destino de su nombre.

    Existe porque la lista de Gestión → Usuarios contiene los cuatro roles y
    las cuentas sin rol todavía, mientras que las dos fichas que ya había solo
    sirven para estudiantes (`historial_estudiante`, `detalle_estudiante`). Sin
    esta pantalla, hacer clic sobre un profesor no llevaba a ninguna parte.

    Funciona como el eje de las otras dos: reúne identidad y contacto, resume
    lo que corresponde según el rol de la persona (promotorías que dicta un
    profesor; el resumen de trayectoria de un estudiante) y enlaza desde ahí a
    la trayectoria completa y, para el administrador, a la ficha con encuesta y
    documento.

    Quién entra lo decide `_puede_ver_ficha`. Qué se muestra, en cambio, sigue
    la matriz de visibilidad de models.py: edad, teléfono y acudiente de un
    estudiante son para administrador y director, y para el profesor SOLO si
    ese estudiante cursa alguna de sus promotorías. Que un profesor pueda abrir
    la ficha no le da acceso a los datos de contacto de cualquiera.
    """
    perfil = request.perfil
    objetivo = get_object_or_404(Perfil, pk=perfil_id)

    if not _puede_ver_ficha(perfil, objetivo):
        messages.error(
            request,
            f"No tienes acceso a la ficha de {objetivo.nombre_completo}: "
            "un profesor solo puede consultar la de sus estudiantes.",
        )
        return redirect("panel")

    es_estudiante = objetivo.rol == "estudiante"
    # El contacto es el dato acotado, no la ficha entera (ver docstring).
    ve_contacto = perfil.rol in ("administrador", "director") or (
        perfil.rol == "profesor"
        and es_estudiante
        and _profesor_tiene_al_estudiante(perfil, objetivo)
    )

    datos_estudiante = getattr(objetivo, "datos_estudiante", None) if es_estudiante else None

    return render(request, "matriculas/detalle_usuario.html", {
        "objetivo": objetivo,
        "es_estudiante": es_estudiante,
        "ve_contacto": ve_contacto,
        "acudiente": datos_estudiante.acudiente if datos_estudiante and ve_contacto else None,
        "resumen": resumen_trayectoria(objetivo) if es_estudiante else None,
        # Un profesor "tiene" promotorías; el resto de roles no cuelga del
        # catálogo, así que para ellos esta lista queda vacía a propósito.
        "promotorias": (
            Promotoria.objects.filter(profesor=objetivo)
            .select_related("area").prefetch_related("grupos").order_by("area__nombre", "nombre")
            if objetivo.rol == "profesor" else []
        ),
        "puede_gestionar_usuarios": perfil.rol in ("director", "administrador"),
    })


@requiere_rol(*ROLES_PANEL)
def historial_estudiante(request, perfil_id):
    """Trayectoria de un estudiante: en qué promotorías ha estado y en cuáles sigue.

    La ve el personal completo (profesor, director y administrador), y muestra
    el historial ENTERO: todas las promotorías del estudiante, no solo las de
    quien consulta.

    Eso último es una excepción deliberada al criterio acotado que sigue el
    resto del sistema —el profesor ve el acudiente solo de SUS promotorías, ver
    el recordatorio de visibilidad en models.py— y se decidió así porque el
    dato es justamente el que hace falta para ubicar a alguien en un nivel:
    saber que lleva tres periodos en Danza le sirve al profesor de Teatro que
    lo recibe por primera vez. No abre nada más: la encuesta demográfica y la
    copia del documento siguen siendo solo del administrador, en
    `detalle_estudiante`.
    """
    estudiante = get_object_or_404(Perfil, pk=perfil_id, rol="estudiante")

    return render(request, "matriculas/historial_estudiante.html", {
        "estudiante": estudiante,
        "historial": historial_por_periodo(estudiante),
        "resumen": resumen_trayectoria(estudiante),
    })


@requiere_rol("administrador")
def detalle_estudiante(request, perfil_id):
    """Ficha completa de un estudiante: encuesta demográfica y documento.

    Solo el administrador puede ver esto (ver docstring de models.py). La
    trayectoria por promotorías no se repite aquí: vive en
    `historial_estudiante`, que sí ve todo el personal.
    """
    estudiante = get_object_or_404(Perfil, pk=perfil_id, rol="estudiante")
    datos_estudiante = getattr(estudiante, "datos_estudiante", None)
    encuesta = getattr(estudiante, "encuesta", None)

    return render(request, "matriculas/detalle_estudiante.html", {
        "estudiante": estudiante,
        "datos_estudiante": datos_estudiante,
        "encuesta": encuesta,
    })


def logo_institucion(request):
    """Sirve el logo configurado de la institución.

    Va por vista y no por /media/ porque este proyecto NO expone ese directorio:
    ahí conviven fotos de perfil y copias de documentos de identidad, que tienen
    reglas de visibilidad estrictas. El logo es lo contrario —marca pública, la
    ve hasta quien no ha iniciado sesión— así que se sirve sin restricción, pero
    por su propia ruta en vez de abrir la carpeta entera.
    """
    configuracion = ConfiguracionInstitucion.actual()
    if not configuracion.logo:
        raise Http404("La institución no tiene un logo propio cargado.")
    return FileResponse(configuracion.logo.open("rb"))


@login_required
def ver_foto(request, perfil_id):
    """Sirve la foto de perfil aplicando la regla de visibilidad de models.py:

        nombre, foto ...... admin, director, profesor, compañeros de la MISMA promotoría

    Sumado a que cualquiera puede ver su propia foto.
    """
    perfil_objetivo = get_object_or_404(Perfil, pk=perfil_id)
    perfil_solicitante = getattr(request.user, "perfil", None)
    if perfil_solicitante is None:
        raise Http404

    permitido = (
        perfil_solicitante.pk == perfil_objetivo.pk
        or perfil_solicitante.rol in ROLES_PANEL
    )
    if not permitido:
        promotorias_periodos_objetivo = set(
            Matricula.objects.filter(estudiante=perfil_objetivo, estado="activa")
            .values_list("promotoria_id", "periodo_id")
        )
        promotorias_periodos_solicitante = set(
            Matricula.objects.filter(estudiante=perfil_solicitante, estado="activa")
            .values_list("promotoria_id", "periodo_id")
        )
        permitido = bool(promotorias_periodos_objetivo & promotorias_periodos_solicitante)

    if not permitido or not perfil_objetivo.foto_perfil:
        raise Http404

    return FileResponse(perfil_objetivo.foto_perfil.open("rb"))


@requiere_rol("administrador")
def descargar_documento(request, datos_estudiante_id):
    """Sirve la copia del documento de identidad de forma controlada.

    No se expone por /media/ directo: solo el administrador puede pedirla.
    """
    datos = get_object_or_404(DatosEstudiante, pk=datos_estudiante_id)
    if not datos.copia_documento:
        raise Http404
    nombre_archivo = datos.copia_documento.name.rsplit("/", 1)[-1]
    return FileResponse(datos.copia_documento.open("rb"), as_attachment=True, filename=nombre_archivo)


# ---------------------------------------------------------------------------
# Encuesta demográfica: autoservicio (todos los roles)
# ---------------------------------------------------------------------------

def _estadisticas_mi_perfil(perfil):
    """Cifras reales para la tarjeta de "Mi perfil", según el rol (ver mis_companeros
    para la misma lógica de "compañero" = misma promotoría y periodo, matrícula activa).
    """
    if perfil.rol == "estudiante":
        matriculas_activas = Matricula.objects.filter(estudiante=perfil, estado="activa").select_related(
            "promotoria", "periodo"
        )
        companero_ids = set()
        for matricula in matriculas_activas:
            companero_ids.update(
                Perfil.objects.filter(
                    matriculas__promotoria=matricula.promotoria,
                    matriculas__periodo=matricula.periodo,
                    matriculas__estado="activa",
                ).exclude(pk=perfil.pk).values_list("pk", flat=True)
            )
        return [
            {"numero": matriculas_activas.count(), "etiqueta": "Matrículas activas"},
            {"numero": len(companero_ids), "etiqueta": "Compañeros"},
        ]
    if perfil.rol == "profesor":
        return [
            {"numero": Promotoria.objects.filter(profesor=perfil).count(), "etiqueta": "Promotorías a cargo"},
            {"numero": Grupo.objects.filter(promotoria__profesor=perfil).count(), "etiqueta": "Grupos"},
        ]
    if perfil.rol in ("director", "administrador"):
        return [
            {"numero": Promotoria.objects.count(), "etiqueta": "Promotorías"},
            {"numero": Perfil.objects.count(), "etiqueta": "Usuarios"},
        ]
    return []


@login_required
def mi_perfil(request):
    """Cada usuario completa aquí, ya logueado, lo que los formularios públicos
    de autorregistro NO piden por seguridad: foto de perfil, copia del
    documento de identidad (solo estudiantes) y la encuesta demográfica
    (obligatoria para todos). Tres formularios independientes en una sola
    página, distinguidos por el campo oculto "accion".
    """
    perfil = getattr(request.user, "perfil", None)
    if perfil is None:
        messages.error(request, "Tu cuenta no tiene un perfil asociado. Contacta al administrador.")
        return redirect("login")

    datos_estudiante = getattr(perfil, "datos_estudiante", None)
    encuesta = getattr(perfil, "encuesta", None)

    accion = request.POST.get("accion")

    if request.method == "POST" and accion == "foto":
        foto_form = FotoPerfilForm(request.POST, request.FILES, instance=perfil)
        if foto_form.is_valid():
            foto_form.save()
            messages.success(request, "Tu foto de perfil quedó guardada.")
            return redirect("mi_perfil")
    else:
        foto_form = FotoPerfilForm(instance=perfil)

    if request.method == "POST" and accion == "contacto":
        contacto_form = DatosContactoForm(request.POST, instance=perfil)
        if contacto_form.is_valid():
            contacto_form.save()
            messages.success(request, "Tu teléfono quedó actualizado.")
            return redirect("mi_perfil")
    else:
        contacto_form = DatosContactoForm(instance=perfil)

    documento_form = None
    if perfil.rol == "estudiante" and datos_estudiante is not None:
        if request.method == "POST" and accion == "documento":
            documento_form = CopiaDocumentoForm(request.POST, request.FILES, instance=datos_estudiante)
            if documento_form.is_valid():
                documento_form.save()
                messages.success(request, "Tu documento quedó guardado.")
                return redirect("mi_perfil")
        else:
            documento_form = CopiaDocumentoForm(instance=datos_estudiante)

    if request.method == "POST" and accion == "encuesta":
        encuesta_form = EncuestaDemograficaForm(request.POST, instance=encuesta)
        if perfil.es_menor:
            encuesta_form.fields.pop("autoriza_tratamiento_datos", None)
        if encuesta_form.is_valid():
            obj = encuesta_form.save(commit=False)
            obj.perfil = perfil
            if obj.autoriza_tratamiento_datos and not obj.fecha_autorizacion:
                obj.fecha_autorizacion = timezone.now()
            elif not obj.autoriza_tratamiento_datos:
                obj.fecha_autorizacion = None
            obj.save()
            messages.success(request, "Tu encuesta quedó guardada.")
            return redirect("mi_perfil")
    else:
        encuesta_form = EncuestaDemograficaForm(instance=encuesta)
        if perfil.es_menor:
            encuesta_form.fields.pop("autoriza_tratamiento_datos", None)

    return render(request, "matriculas/mi_perfil.html", {
        "perfil": perfil,
        "foto_form": foto_form,
        "contacto_form": contacto_form,
        "documento_form": documento_form,
        "encuesta_form": encuesta_form,
        "encuesta": encuesta,
        # Vacía cuando no hay nada que pedir, así que la plantilla la usa
        # también como "¿está pendiente?". Sin encuesta empezada no se listan
        # preguntas sueltas: ahí lo que falta es la encuesta entera.
        "faltan_preguntas": encuesta.preguntas_faltantes if encuesta else [],
        "estadisticas": _estadisticas_mi_perfil(perfil),
    })
