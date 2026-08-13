"""Pruebas del límite configurable de promotorías y del historial del estudiante.

El límite dejó de ser una constante de Python (`LIMITE_PROMOTORIAS_POR_PERIODO`)
y ahora vive en `ConfiguracionInstitucion`, editable desde Gestión →
Configuración. Eso cambió quién impone la regla: antes bastaba el índice único
sobre `ranura`, porque había exactamente tantas ranuras como permitía el límite;
ahora el esquema solo conoce el techo absoluto (`RANURA_MAXIMA_ABSOLUTA`) y la
regla de negocio la aplica `Matricula.clean()`. Eso cubre `LimiteConfigurableTests`
y `PantallaConfiguracionTests`.

`HistorialTests` cubre lo otro: la trayectoria del estudiante por periodos.
"""

from datetime import date

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from .models import (
    RANURA_MAXIMA_ABSOLUTA,
    Area, ConfiguracionInstitucion, DatosEstudiante, Grupo, Matricula, Perfil,
    Periodo, Promotoria, historial_por_periodo, resumen_trayectoria,
)
from .views_gestion import ROL_PENDIENTE


class LimiteConfigurableTests(TestCase):
    """Fixture mínima: un periodo abierto, tres promotorías y un estudiante."""

    def setUp(self):
        self.periodo = Periodo.objects.create(
            nombre="2026-1", fecha_inicio=date(2026, 1, 15), fecha_fin=date(2026, 6, 15),
            activo=True, matriculas_abiertas=True,
        )
        area = Area.objects.create(nombre="Música")
        self.violin = Promotoria.objects.create(nombre="Violín", area=area)
        self.guitarra = Promotoria.objects.create(nombre="Guitarra", area=area)
        self.piano = Promotoria.objects.create(nombre="Piano", area=area)

        self.usuario = User.objects.create_user(username="ana", password="x")
        self.estudiante = Perfil.objects.create(
            usuario=self.usuario, rol="estudiante", nombre_completo="Ana Ruiz",
            # Mayor de edad: si no, `matricular` exige acudiente registrado.
            fecha_nacimiento=date(1995, 3, 4), telefono="3000000000",
        )
        DatosEstudiante.objects.create(perfil=self.estudiante, documento_identidad="123456")

        self.client.force_login(self.usuario)

    # -- utilidades ---------------------------------------------------------

    def fijar_limite(self, valor):
        configuracion = ConfiguracionInstitucion.actual()
        configuracion.limite_promotorias_por_periodo = valor
        configuracion.save()

    def matricular(self, promotoria):
        """POST real a la vista, como lo haría el botón «Matricularme»."""
        return self.client.post(reverse("matricular", args=[promotoria.id]), follow=True)

    def crear_matricula(self, promotoria, estado="activa"):
        """Matrícula ya existente, saltándose la vista (para preparar el estado)."""
        matricula = Matricula(
            estudiante=self.estudiante, promotoria=promotoria,
            periodo=self.periodo, estado=estado,
        )
        matricula.full_clean()
        matricula.save()
        return matricula

    def matriculas_vivas(self):
        return Matricula.objects.filter(
            estudiante=self.estudiante, periodo=self.periodo
        ).exclude(estado="retirada")

    # -- el caso que pide el encargo ----------------------------------------

    def test_limite_1_bloquea_la_segunda_promotoria(self):
        self.fijar_limite(1)
        self.crear_matricula(self.violin)

        respuesta = self.matricular(self.guitarra)

        self.assertEqual(self.matriculas_vivas().count(), 1)
        self.assertNotIn(
            self.guitarra.id,
            self.matriculas_vivas().values_list("promotoria_id", flat=True),
        )
        mensajes = [str(m) for m in respuesta.context["messages"]]
        self.assertTrue(
            any("máximo de 1 promotoría" in m for m in mensajes),
            f"Se esperaba el aviso del límite; llegaron: {mensajes}",
        )

    def test_limite_3_permite_la_tercera_promotoria(self):
        self.fijar_limite(3)
        self.crear_matricula(self.violin)
        self.crear_matricula(self.guitarra)

        self.matricular(self.piano)

        self.assertEqual(self.matriculas_vivas().count(), 3)
        self.assertEqual(
            sorted(self.matriculas_vivas().values_list("ranura", flat=True)), [1, 2, 3]
        )

    def test_limite_3_sigue_bloqueando_la_cuarta(self):
        self.fijar_limite(3)
        for promotoria in (self.violin, self.guitarra, self.piano):
            self.crear_matricula(promotoria)
        cuarta = Promotoria.objects.create(nombre="Cello", area=self.violin.area)

        self.matricular(cuarta)

        self.assertEqual(self.matriculas_vivas().count(), 3)

    # -- caso borde: bajar el límite con matrículas ya existentes -----------

    def test_bajar_el_limite_no_rompe_las_matriculas_existentes(self):
        """Dos matrículas activas y el límite baja a 1: siguen vivas y válidas."""
        self.fijar_limite(2)
        primera = self.crear_matricula(self.violin)
        segunda = self.crear_matricula(self.guitarra)

        self.fijar_limite(1)

        self.assertEqual(self.matriculas_vivas().count(), 2)
        # Ninguna viola el techo del esquema, así que se pueden seguir tocando:
        # confirmar, asignar grupo o guardar de nuevo no deben fallar.
        for matricula in (primera, segunda):
            matricula.refresh_from_db()
            matricula.full_clean()
            matricula.save()
        self.assertEqual(self.matriculas_vivas().count(), 2)

    def test_bajar_el_limite_impide_pedir_una_mas(self):
        self.fijar_limite(2)
        self.crear_matricula(self.violin)
        self.crear_matricula(self.guitarra)

        self.fijar_limite(1)
        self.matricular(self.piano)

        self.assertEqual(self.matriculas_vivas().count(), 2)

    def test_bajar_el_limite_con_la_ranura_1_libre(self):
        """El caso que el índice único NO ve, y que por eso valida `clean()`.

        La estudiante se retira de su primera promotoría y se queda solo con la
        de la ranura 2. Con el límite en 1 ya está en el tope, pero la ranura 1
        está libre: una matrícula nueva nacería ahí sin chocar contra ningún
        índice. Quien tiene que rechazarla es la capa de aplicación.
        """
        self.fijar_limite(2)
        primera = self.crear_matricula(self.violin)
        segunda = self.crear_matricula(self.guitarra)
        self.assertEqual(segunda.ranura, 2)

        primera.estado = "retirada"
        primera.save(update_fields=["estado"])
        self.fijar_limite(1)

        self.matricular(self.piano)

        self.assertEqual(self.matriculas_vivas().count(), 1)
        self.assertEqual(self.matriculas_vivas().first().promotoria_id, self.guitarra.id)

    def test_subir_el_limite_reutiliza_la_ranura_liberada(self):
        """Retirarse libera la ranura, y la siguiente matrícula la reocupa."""
        self.fijar_limite(2)
        primera = self.crear_matricula(self.violin)
        self.crear_matricula(self.guitarra)
        primera.estado = "retirada"
        primera.save(update_fields=["estado"])

        self.matricular(self.piano)

        vivas = {m.promotoria_id: m.ranura for m in self.matriculas_vivas()}
        self.assertEqual(vivas, {self.guitarra.id: 2, self.piano.id: 1})

    # -- validación del propio campo de configuración -----------------------

    def test_el_limite_no_puede_pasar_del_techo_del_esquema(self):
        configuracion = ConfiguracionInstitucion.actual()
        configuracion.limite_promotorias_por_periodo = RANURA_MAXIMA_ABSOLUTA + 1
        with self.assertRaises(ValidationError) as caso:
            configuracion.full_clean()
        self.assertIn(
            "El máximo que admite la base de datos",
            " ".join(caso.exception.messages),
        )

    def test_el_limite_no_puede_ser_cero(self):
        configuracion = ConfiguracionInstitucion.actual()
        configuracion.limite_promotorias_por_periodo = 0
        with self.assertRaises(ValidationError) as caso:
            configuracion.full_clean()
        self.assertIn("al menos 1 promotoría", " ".join(caso.exception.messages))


class PantallaConfiguracionTests(TestCase):
    """El administrador cambia el límite desde Gestión → Configuración."""

    def setUp(self):
        self.usuario = User.objects.create_user(username="admin1", password="x")
        Perfil.objects.create(
            usuario=self.usuario, rol="administrador", nombre_completo="Admin",
            fecha_nacimiento=date(1980, 1, 1), telefono="3000000001",
        )
        self.client.force_login(self.usuario)

    def test_el_administrador_guarda_un_limite_nuevo(self):
        respuesta = self.client.post(reverse("gestion_configuracion"), {
            "nombre_institucion": "Casa de la Cultura",
            "color_acento": "#0a7a59",
            "limite_promotorias_por_periodo": 3,
        })

        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(ConfiguracionInstitucion.actual().limite_promotorias_por_periodo, 3)

    def test_la_pantalla_rechaza_un_limite_por_encima_del_techo(self):
        respuesta = self.client.post(reverse("gestion_configuracion"), {
            "nombre_institucion": "Casa de la Cultura",
            "color_acento": "#0a7a59",
            "limite_promotorias_por_periodo": RANURA_MAXIMA_ABSOLUTA + 1,
        })

        self.assertEqual(respuesta.status_code, 200)
        self.assertFormError(
            respuesta.context["form"], "limite_promotorias_por_periodo",
            f"El máximo que admite la base de datos es {RANURA_MAXIMA_ABSOLUTA} "
            "promotorías por periodo. Subir de ahí exige una migración.",
        )
        self.assertEqual(ConfiguracionInstitucion.actual().limite_promotorias_por_periodo, 2)

    def test_un_estudiante_no_entra_a_la_pantalla(self):
        otro = User.objects.create_user(username="estu", password="x")
        Perfil.objects.create(
            usuario=otro, rol="estudiante", nombre_completo="Estu",
            fecha_nacimiento=date(2000, 1, 1), telefono="3000000002",
        )
        self.client.force_login(otro)

        respuesta = self.client.get(reverse("gestion_configuracion"))

        self.assertNotEqual(respuesta.status_code, 200)


class HistorialTests(TestCase):
    """Historial de promotorías: el suyo el estudiante, el ajeno el personal.

    Detrás no hay ningún modelo nuevo —`Matricula` ya guarda su periodo y las
    retiradas no se borran—, así que lo que hay que cubrir es que la consulta
    agrupe bien, que el resumen cuente lo que dice contar, y que la vista la
    vea quien debe.

    Fixture: dos periodos (uno terminado y el que está en curso), tres
    promotorías en dos áreas distintas, y una estudiante.
    """

    def setUp(self):
        self.pasado = Periodo.objects.create(
            nombre="2025-1", fecha_inicio=date(2025, 1, 15), fecha_fin=date(2025, 6, 15),
        )
        self.actual = Periodo.objects.create(
            nombre="2026-1", fecha_inicio=date(2026, 1, 15), fecha_fin=date(2026, 6, 15),
            activo=True, matriculas_abiertas=True,
        )
        musica = Area.objects.create(nombre="Música")
        teatro = Area.objects.create(nombre="Teatro")
        self.violin = Promotoria.objects.create(nombre="Violín", area=musica)
        self.guitarra = Promotoria.objects.create(nombre="Guitarra", area=musica)
        self.actuacion = Promotoria.objects.create(nombre="Actuación", area=teatro)

        self.usuario = User.objects.create_user(username="ana", password="x")
        self.ana = Perfil.objects.create(
            usuario=self.usuario, rol="estudiante", nombre_completo="Ana Ruiz",
            fecha_nacimiento=date(1995, 3, 4), telefono="3000000000",
        )
        DatosEstudiante.objects.create(perfil=self.ana, documento_identidad="123456")

    # -- utilidades ---------------------------------------------------------

    def matricular(self, promotoria, periodo, estado="activa"):
        matricula = Matricula(
            estudiante=self.ana, promotoria=promotoria, periodo=periodo, estado=estado,
        )
        matricula.full_clean()
        matricula.save()
        return matricula

    def crear_profesor(self, username, promotoria=None):
        """Un profesor, opcionalmente a cargo de una promotoría."""
        usuario = User.objects.create_user(username=username, password="x")
        perfil = Perfil.objects.create(
            usuario=usuario, rol="profesor", nombre_completo=f"Profe {username}",
            fecha_nacimiento=date(1985, 5, 5), telefono="3000000009",
        )
        if promotoria is not None:
            promotoria.profesor = perfil
            promotoria.save(update_fields=["profesor"])
        return perfil

    # -- la consulta --------------------------------------------------------

    def test_agrupa_por_periodo_del_mas_reciente_al_mas_antiguo(self):
        self.matricular(self.violin, self.pasado)
        self.matricular(self.guitarra, self.actual)

        historial = historial_por_periodo(self.ana)

        self.assertEqual([b["periodo"] for b in historial], [self.actual, self.pasado])
        self.assertEqual([b["en_curso"] for b in historial], [True, False])

    def test_un_periodo_con_varias_promotorias_es_un_solo_bloque(self):
        self.matricular(self.violin, self.pasado)
        self.matricular(self.actuacion, self.pasado)

        historial = historial_por_periodo(self.ana)

        self.assertEqual(len(historial), 1)
        self.assertEqual(len(historial[0]["matriculas"]), 2)

    def test_conserva_las_retiradas(self):
        """Un historial que solo enseña lo que prosperó no sirve para lo que se consulta."""
        self.matricular(self.violin, self.pasado, estado="retirada")

        historial = historial_por_periodo(self.ana)

        [matricula] = historial[0]["matriculas"]
        self.assertEqual(matricula.estado, "retirada")

    def test_un_estudiante_sin_matriculas_no_tiene_historial(self):
        self.assertEqual(historial_por_periodo(self.ana), [])

    def test_el_resumen_solo_cuenta_lo_que_de_verdad_curso(self):
        """Pendientes y retiradas salen en el detalle, pero no inflan las cifras."""
        self.matricular(self.violin, self.pasado)
        self.matricular(self.guitarra, self.pasado, estado="retirada")
        self.matricular(self.violin, self.actual, estado="pendiente")

        resumen = resumen_trayectoria(self.ana)

        self.assertEqual(resumen["periodos"], 1)
        self.assertEqual(resumen["promotorias"], 1)
        self.assertEqual(resumen["desde"], self.pasado)

    def test_el_resumen_no_cuenta_dos_veces_la_misma_promotoria(self):
        """Dos periodos en Violín son una promotoría cursada, no dos."""
        self.matricular(self.violin, self.pasado)
        self.matricular(self.violin, self.actual)

        resumen = resumen_trayectoria(self.ana)

        self.assertEqual(resumen["periodos"], 2)
        self.assertEqual(resumen["promotorias"], 1)

    # -- quién puede verlo --------------------------------------------------

    def test_un_profesor_ve_la_trayectoria_completa_aunque_sea_de_otra_area(self):
        """Excepción deliberada al criterio acotado del resto del sistema.

        El profesor de Violín ve que Ana viene de Actuación, que es de otra
        área y no la dicta él: es el dato que le permite ubicarla en un nivel.
        """
        self.matricular(self.actuacion, self.pasado)
        profesor = self.crear_profesor("profe_violin", promotoria=self.violin)
        self.client.force_login(profesor.usuario)

        respuesta = self.client.get(reverse("historial_estudiante", args=[self.ana.id]))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Actuación")

    def test_un_estudiante_no_ve_la_trayectoria_de_otro(self):
        otro_usuario = User.objects.create_user(username="beto", password="x")
        otro = Perfil.objects.create(
            usuario=otro_usuario, rol="estudiante", nombre_completo="Beto Páez",
            fecha_nacimiento=date(1996, 7, 7), telefono="3000000003",
        )
        self.client.force_login(self.usuario)

        respuesta = self.client.get(reverse("historial_estudiante", args=[otro.id]))

        self.assertNotEqual(respuesta.status_code, 200)

    def test_la_trayectoria_no_filtra_la_encuesta_ni_el_documento(self):
        """Lo que abre esta pantalla son las promotorías, nada más.

        La copia del documento sigue siendo solo del administrador, así que el
        enlace para descargarla no puede aparecerle a un profesor.
        """
        self.matricular(self.violin, self.actual)
        profesor = self.crear_profesor("profe_violin", promotoria=self.violin)
        self.client.force_login(profesor.usuario)

        respuesta = self.client.get(reverse("historial_estudiante", args=[self.ana.id]))

        self.assertNotContains(respuesta, "123456")
        self.assertNotContains(respuesta, reverse("detalle_estudiante", args=[self.ana.id]))

    # -- lo que ve el estudiante de lo suyo ---------------------------------

    def test_mis_matriculas_agrupa_y_solo_deja_retirarse_del_periodo_en_curso(self):
        self.matricular(self.violin, self.pasado)
        self.matricular(self.guitarra, self.actual)
        self.client.force_login(self.usuario)

        respuesta = self.client.get(reverse("mis_matriculas"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(
            [b["periodo"].nombre for b in respuesta.context["historial"]],
            ["2026-1", "2025-1"],
        )
        # La matrícula del periodo terminado es historial cerrado: un solo botón.
        self.assertContains(respuesta, "Retirarme", count=1)
        self.assertContains(respuesta, "Periodo terminado", count=1)


class FiltrosUsuariosTests(TestCase):
    """Filtros del listado de usuarios (Gestión → Usuarios).

    Lo que hay que cubrir es que cada filtro entienda cómo se relaciona cada
    rol con el catálogo: el estudiante cuelga de una promotoría por su
    matrícula y el profesor porque la dicta, así que filtrar por una
    promotoría tiene que devolver a los dos. El grupo es la excepción, porque
    solo tiene estudiantes.

    Fixture: dos periodos, dos áreas con una promotoría cada una, un grupo, y
    un usuario de cada rol.
    """

    def setUp(self):
        self.pasado = Periodo.objects.create(
            nombre="2025-1", fecha_inicio=date(2025, 1, 15), fecha_fin=date(2025, 6, 15),
        )
        self.actual = Periodo.objects.create(
            nombre="2026-1", fecha_inicio=date(2026, 1, 15), fecha_fin=date(2026, 6, 15),
            activo=True, matriculas_abiertas=True,
        )
        self.musica = Area.objects.create(nombre="Música")
        self.teatro = Area.objects.create(nombre="Teatro")

        self.profe_violin = self.crear(
            "profe_violin", "profesor", "Profe Violín", "3000000001")
        self.profe_teatro = self.crear(
            "profe_teatro", "profesor", "Profe Teatro", "3000000002")
        self.violin = Promotoria.objects.create(
            nombre="Violín", area=self.musica, profesor=self.profe_violin)
        self.actuacion = Promotoria.objects.create(
            nombre="Actuación", area=self.teatro, profesor=self.profe_teatro)
        self.basico = Grupo.objects.create(
            promotoria=self.violin, nivel="basico", horario="L 8am",
            salon="A1", cupo_maximo=10)

        self.ana = self.crear("ana", "estudiante", "Ana Ruiz", "3000000003")
        self.beto = self.crear("beto", "estudiante", "Beto Páez", "3000000004")
        self.director = self.crear("dire", "director", "Dire", "3000000005")
        self.admin = self.crear("admin1", "administrador", "Admin", "3000000006")
        self.sin_rol = self.crear("nuevo", "", "Recien Llegado", "3000000007")

        self.client.force_login(self.admin.usuario)

    # -- utilidades ---------------------------------------------------------

    def crear(self, username, rol, nombre, telefono):
        usuario = User.objects.create_user(username=username, password="x")
        return Perfil.objects.create(
            usuario=usuario, rol=rol, nombre_completo=nombre,
            fecha_nacimiento=date(1995, 3, 4), telefono=telefono,
        )

    def matricular(self, perfil, promotoria, periodo, estado="activa", grupo=None):
        matricula = Matricula(
            estudiante=perfil, promotoria=promotoria, periodo=periodo,
            estado=estado, grupo=grupo,
        )
        matricula.full_clean()
        matricula.save()
        return matricula

    def filtrar(self, **parametros):
        """Nombres de los perfiles que devuelve el listado con esos filtros."""
        respuesta = self.client.get(reverse("usuario_lista"), parametros)
        self.assertEqual(respuesta.status_code, 200)
        return sorted(p.nombre_completo for p in respuesta.context["object_list"])

    # -- rol ----------------------------------------------------------------

    def test_sin_filtros_salen_todos(self):
        self.assertEqual(len(self.filtrar()), 7)

    def test_filtra_por_rol(self):
        self.assertEqual(self.filtrar(rol="profesor"), ["Profe Teatro", "Profe Violín"])

    def test_filtra_a_los_pendientes_de_rol(self):
        """El centinela hace falta porque "sin rol" es la cadena vacía, que en
        un GET ya significa "no filtres"."""
        self.assertEqual(self.filtrar(rol=ROL_PENDIENTE), ["Recien Llegado"])

    # -- catálogo -----------------------------------------------------------

    def test_la_promotoria_devuelve_al_matriculado_y_a_su_profesor(self):
        self.matricular(self.ana, self.violin, self.actual)

        self.assertEqual(
            self.filtrar(promotoria=self.violin.id), ["Ana Ruiz", "Profe Violín"]
        )

    def test_el_departamento_arrastra_sus_promotorias(self):
        self.matricular(self.ana, self.violin, self.actual)
        self.matricular(self.beto, self.actuacion, self.actual)

        self.assertEqual(self.filtrar(area=self.musica.id), ["Ana Ruiz", "Profe Violín"])

    def test_el_grupo_no_devuelve_al_profesor(self):
        """Un grupo solo tiene estudiantes: ahí el profesor no pinta nada."""
        self.matricular(self.ana, self.violin, self.actual, grupo=self.basico)

        self.assertEqual(self.filtrar(grupo=self.basico.id), ["Ana Ruiz"])

    def test_una_matricula_retirada_no_cuenta(self):
        """Quien se retiró de Violín ya no es de Violín."""
        self.matricular(self.ana, self.violin, self.actual, estado="retirada")

        self.assertEqual(self.filtrar(promotoria=self.violin.id), ["Profe Violín"])

    def test_una_matricula_pendiente_si_cuenta(self):
        self.matricular(self.ana, self.violin, self.actual, estado="pendiente")

        self.assertEqual(
            self.filtrar(promotoria=self.violin.id), ["Ana Ruiz", "Profe Violín"]
        )

    # -- periodo ------------------------------------------------------------

    def test_el_periodo_acota_a_los_estudiantes_pero_no_al_profesor(self):
        """Dictar una promotoría no depende del periodo; estar matriculado sí."""
        self.matricular(self.ana, self.violin, self.pasado)

        self.assertEqual(
            self.filtrar(promotoria=self.violin.id, periodo=self.pasado.id),
            ["Ana Ruiz", "Profe Violín"],
        )
        self.assertEqual(
            self.filtrar(promotoria=self.violin.id, periodo=self.actual.id),
            ["Profe Violín"],
        )

    def test_sin_periodo_pedido_se_usa_el_que_esta_en_curso(self):
        self.matricular(self.ana, self.violin, self.pasado)
        self.matricular(self.beto, self.violin, self.actual)

        self.assertEqual(
            self.filtrar(promotoria=self.violin.id), ["Beto Páez", "Profe Violín"]
        )

    def test_un_periodo_inexistente_no_abre_la_busqueda_a_todo_el_historico(self):
        """Si esto devolviera None, la consulta dejaria de acotar por periodo y
        barreria el historico entero mientras el desplegable enseña otra cosa."""
        self.matricular(self.ana, self.violin, self.pasado)
        self.matricular(self.beto, self.violin, self.actual)

        self.assertEqual(
            self.filtrar(promotoria=self.violin.id, periodo=99999),
            ["Beto Páez", "Profe Violín"],
        )

    # -- combinaciones ------------------------------------------------------

    def test_el_rol_se_cruza_con_la_promotoria(self):
        self.matricular(self.ana, self.violin, self.actual)

        self.assertEqual(
            self.filtrar(promotoria=self.violin.id, rol="estudiante"), ["Ana Ruiz"]
        )

    def test_un_rol_que_no_cuelga_del_catalogo_da_lista_vacia(self):
        """Cruzar administrador con una promotoría no existe: vacío correcto."""
        self.matricular(self.ana, self.violin, self.actual)

        self.assertEqual(self.filtrar(promotoria=self.violin.id, rol="administrador"), [])

    def test_un_estudiante_no_entra_al_listado(self):
        self.client.force_login(self.ana.usuario)

        respuesta = self.client.get(reverse("usuario_lista"))

        self.assertNotEqual(respuesta.status_code, 200)
