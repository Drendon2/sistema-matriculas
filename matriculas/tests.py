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

import math
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from .models import (
    RANURA_MAXIMA_ABSOLUTA,
    Acudiente, Area, ConfiguracionInstitucion, CupoPromotoria, DatosEstudiante,
    EncuestaDemografica, Grupo,
    Matricula, Perfil, Periodo, Promotoria, historial_por_periodo,
    matriculas_renovables,
    resumen_trayectoria,
)
from .views_gestion import (
    RADIO_TORTA, ROL_PENDIENTE, SEPARACION_TORTA, _torta,
)


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
        # (El botón se llama "Cancelar matrícula" desde que retirarse pasa por
        # la aprobación de un director — ver CancelacionTests.)
        self.assertContains(respuesta, "Cancelar matrícula", count=1)
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


class EncuestaChoicesTests(TestCase):
    """La encuesta demográfica como listas cerradas en vez de texto libre.

    El cambio persigue dos cosas: que la persona escriba menos, y que las
    cifras de Gestión → Estadísticas se puedan agrupar. Con texto libre,
    «Bachillerato» y «bachiller» eran dos filas distintas de lo mismo.

    `barrio` se queda como texto libre a propósito y hay una prueba que lo
    fija: convertirlo en una lista de barrios ataría el proyecto a un
    municipio concreto.
    """

    # Respuestas mínimas válidas: los obligatorios de la encuesta.
    BASE = {
        "accion": "encuesta",
        "genero": "f",
        "barrio": "La Playa",
        "estrato": 2,
        "nivel_educativo": "secundaria_com",
        "ocupacion": "independiente",
    }

    def setUp(self):
        usuario = User.objects.create_user(username="marta", password="x")
        self.perfil = Perfil.objects.create(
            usuario=usuario, rol="profesor", nombre_completo="Marta Docente",
            # Mayor de edad: a los menores el formulario les quita la casilla de
            # autorización, que la otorga el acudiente.
            fecha_nacimiento=date(1990, 4, 2), telefono="3000000000",
        )
        self.client.force_login(usuario)

    def responder(self, **extra):
        datos = dict(self.BASE, **extra)
        return self.client.post(reverse("mi_perfil"), datos)

    # -- el formulario ------------------------------------------------------

    def test_los_campos_salen_como_desplegables(self):
        """Lo que pide el encargo: que no haya que escribir, sino elegir."""
        respuesta = self.client.get(reverse("mi_perfil"))

        for campo in (
            "nivel_educativo", "ocupacion", "grupo_etnico", "discapacidad",
            "zona", "victima_conflicto_armado", "afiliacion_salud",
        ):
            self.assertContains(respuesta, f'<select name="{campo}"', html=False)

    def test_el_barrio_sigue_siendo_texto_libre(self):
        """Una lista fija de barrios ataría el sistema a un municipio."""
        formulario = self.client.get(reverse("mi_perfil")).context["encuesta_form"]

        self.assertEqual(formulario.fields["barrio"].widget.input_type, "text")

    # -- guardado -----------------------------------------------------------

    def test_guarda_los_campos_convertidos_y_los_nuevos(self):
        respuesta = self.responder(
            grupo_etnico="afro",
            discapacidad="ninguna",
            zona="rural",
            victima_conflicto_armado="no",
            afiliacion_salud="subsidiado",
            autoriza_tratamiento_datos="on",
        )

        self.assertEqual(respuesta.status_code, 302)
        encuesta = EncuestaDemografica.objects.get(perfil=self.perfil)
        self.assertEqual(encuesta.nivel_educativo, "secundaria_com")
        self.assertEqual(encuesta.ocupacion, "independiente")
        self.assertEqual(encuesta.grupo_etnico, "afro")
        self.assertEqual(encuesta.zona, "rural")
        self.assertEqual(encuesta.victima_conflicto_armado, "no")
        self.assertEqual(encuesta.afiliacion_salud, "subsidiado")
        self.assertEqual(encuesta.barrio, "La Playa")

    def test_los_opcionales_se_pueden_dejar_en_blanco(self):
        respuesta = self.responder()

        self.assertEqual(respuesta.status_code, 302)
        encuesta = EncuestaDemografica.objects.get(perfil=self.perfil)
        self.assertEqual(encuesta.zona, "")
        self.assertEqual(encuesta.victima_conflicto_armado, "")
        self.assertEqual(encuesta.grupo_etnico, "")

    def test_los_obligatorios_siguen_siendo_obligatorios(self):
        respuesta = self.responder(nivel_educativo="")

        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(EncuestaDemografica.objects.filter(perfil=self.perfil).exists())

    def test_rechaza_un_valor_que_no_esta_en_la_lista(self):
        """Es la mitad del asunto: sin esto volveríamos a tener texto libre."""
        respuesta = self.responder(ocupacion="Asesor de proyectos")

        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(EncuestaDemografica.objects.filter(perfil=self.perfil).exists())

    def test_se_guarda_el_codigo_y_se_lee_la_etiqueta(self):
        self.responder(zona="centro_poblado")

        encuesta = EncuestaDemografica.objects.get(perfil=self.perfil)
        self.assertEqual(encuesta.zona, "centro_poblado")
        self.assertEqual(encuesta.get_zona_display(), "Centro poblado")
        self.assertEqual(encuesta.get_nivel_educativo_display(), "Secundaria completa")

    # -- lo que lee esos campos ---------------------------------------------

    def test_las_estadisticas_agrupan_por_opcion(self):
        """Antes esto era un "top 5" de texto libre; ahora la lista es finita."""
        self.responder(zona="rural")
        admin_usuario = User.objects.create_user(username="admin1", password="x")
        Perfil.objects.create(
            usuario=admin_usuario, rol="administrador", nombre_completo="Admin",
            fecha_nacimiento=date(1980, 1, 1), telefono="3000000001",
        )
        self.client.force_login(admin_usuario)

        respuesta = self.client.get(reverse("gestion_estadisticas"))

        self.assertEqual(respuesta.status_code, 200)
        # Zona se dibuja en torta, así que sus cifras viven en la leyenda. Todas
        # las opciones aparecen, incluidas las que nadie eligió: así el panel
        # enseña siempre la misma lista y se ve qué NO contesta la gente.
        zona = {
            e["etiqueta"]: e["total"] for e in respuesta.context["zona_torta"]["leyenda"]
        }
        self.assertEqual(zona, {"Urbana": 0, "Rural": 1, "Centro poblado": 0})
        # Nivel educativo sigue en barras: es una escala con orden propio.
        niveles = {f["etiqueta"]: f["total"] for f in respuesta.context["nivel_educativo_stats"]}
        self.assertEqual(niveles["Secundaria completa"], 1)

    def test_la_ficha_del_estudiante_muestra_las_etiquetas_legibles(self):
        estudiante_usuario = User.objects.create_user(username="samu", password="x")
        estudiante = Perfil.objects.create(
            usuario=estudiante_usuario, rol="estudiante", nombre_completo="Samuel",
            fecha_nacimiento=date(2000, 1, 1), telefono="3000000002",
        )
        EncuestaDemografica.objects.create(
            perfil=estudiante, genero="m", barrio="Centro", estrato=1,
            nivel_educativo="tecnologo", ocupacion="hogar", zona="urbana",
        )
        admin_usuario = User.objects.create_user(username="admin2", password="x")
        Perfil.objects.create(
            usuario=admin_usuario, rol="administrador", nombre_completo="Admin",
            fecha_nacimiento=date(1980, 1, 1), telefono="3000000003",
        )
        self.client.force_login(admin_usuario)

        respuesta = self.client.get(reverse("detalle_estudiante", args=[estudiante.id]))

        self.assertContains(respuesta, "Tecnólogo")
        self.assertContains(respuesta, "Urbana")
        # El código interno no se le enseña a nadie.
        self.assertNotContains(respuesta, "tecnologo")


class CancelacionTests(TestCase):
    """Cancelar una matrícula pasa por la aprobación de un director.

    La regla de fondo depende de la edad, y las dos ramas persiguen cosas
    distintas: a un MENOR se le puede rechazar la cancelación, porque la pausa
    existe para hablar con el acudiente antes de que un niño se salga por su
    cuenta; a un MAYOR solo se le puede aprobar, porque irse es decisión suya y
    el paso por dirección existe para saber de qué promotorías se está yendo la
    gente, no para retenerla.
    """

    def setUp(self):
        self.periodo = Periodo.objects.create(
            nombre="2026-1", fecha_inicio=date(2026, 1, 15), fecha_fin=date(2026, 6, 15),
            activo=True, matriculas_abiertas=True,
        )
        area = Area.objects.create(nombre="Música")
        self.violin = Promotoria.objects.create(nombre="Violín", area=area)

        self.adulta = self.crear_estudiante("ana", "Ana Ruiz", date(1995, 3, 4))
        self.menor = self.crear_estudiante(
            "beto", "Beto Páez", date.today() - timedelta(days=365 * 12),
            acudiente=Acudiente.objects.create(nombre="Madre de Beto", telefono="3001"),
        )
        usuario = User.objects.create_user(username="dire", password="x")
        self.director = Perfil.objects.create(
            usuario=usuario, rol="director", nombre_completo="Directora",
            fecha_nacimiento=date(1980, 1, 1), telefono="3000000009",
        )

    def crear_estudiante(self, username, nombre, nacimiento, acudiente=None):
        usuario = User.objects.create_user(username=username, password="x")
        perfil = Perfil.objects.create(
            usuario=usuario, rol="estudiante", nombre_completo=nombre,
            fecha_nacimiento=nacimiento, telefono="3000000000",
        )
        DatosEstudiante.objects.create(
            perfil=perfil, documento_identidad=username, acudiente=acudiente,
        )
        return perfil

    def matricular(self, perfil, estado="activa"):
        matricula = Matricula(
            estudiante=perfil, promotoria=self.violin, periodo=self.periodo, estado=estado,
        )
        matricula.full_clean()
        matricula.save()
        return matricula

    def pedir_cancelacion(self, perfil, matricula):
        self.client.force_login(perfil.usuario)
        return self.client.post(reverse("retirar_matricula", args=[matricula.id]))

    def resolver(self, matricula, decision):
        self.client.force_login(self.director.usuario)
        return self.client.post(
            reverse("gestion_resolver_cancelacion", args=[matricula.id, decision])
        )

    # -- pedirla ------------------------------------------------------------

    def test_cancelar_una_activa_no_la_retira_todavia(self):
        matricula = self.matricular(self.adulta)

        self.pedir_cancelacion(self.adulta, matricula)

        matricula.refresh_from_db()
        self.assertEqual(matricula.estado, Matricula.ESTADO_CANCELACION)

    def test_mientras_espera_sigue_ocupando_cupo(self):
        """El cupo no se libera hasta que alguien aprueba la salida."""
        matricula = self.matricular(self.adulta)
        CupoPromotoria.objects.create(
            promotoria=self.violin, periodo=self.periodo, cupo_maximo=1)

        self.pedir_cancelacion(self.adulta, matricula)

        self.assertEqual(self.violin.cupos_disponibles(self.periodo), 0)
        self.assertEqual(self.violin.ocupados_en(self.periodo), 1)

    def test_una_pendiente_se_cancela_en_el_acto(self):
        """Nadie la confirmó: no es una deserción, es retirar una solicitud."""
        matricula = self.matricular(self.adulta, estado="pendiente")

        self.pedir_cancelacion(self.adulta, matricula)

        matricula.refresh_from_db()
        self.assertEqual(matricula.estado, "retirada")

    # -- resolverla ---------------------------------------------------------

    def test_aprobar_retira_y_libera_el_grupo(self):
        matricula = self.matricular(self.adulta)
        self.pedir_cancelacion(self.adulta, matricula)

        self.resolver(matricula, "aprobar")

        matricula.refresh_from_db()
        self.assertEqual(matricula.estado, "retirada")
        self.assertIsNone(matricula.grupo)

    def test_a_un_menor_se_le_puede_rechazar_y_vuelve_a_activa(self):
        matricula = self.matricular(self.menor)
        self.pedir_cancelacion(self.menor, matricula)

        self.resolver(matricula, "rechazar")

        matricula.refresh_from_db()
        self.assertEqual(matricula.estado, "activa")

    def test_a_un_mayor_no_se_le_rechaza_aunque_se_fuerce_la_peticion(self):
        """Ocultar el botón no basta: el formulario se puede enviar a mano."""
        matricula = self.matricular(self.adulta)
        self.pedir_cancelacion(self.adulta, matricula)

        self.resolver(matricula, "rechazar")

        matricula.refresh_from_db()
        self.assertEqual(matricula.estado, Matricula.ESTADO_CANCELACION)

    def test_la_pantalla_ofrece_rechazar_solo_al_menor(self):
        de_adulta = self.matricular(self.adulta)
        de_menor = self.matricular(self.menor)
        self.pedir_cancelacion(self.adulta, de_adulta)
        self.pedir_cancelacion(self.menor, de_menor)
        self.client.force_login(self.director.usuario)

        respuesta = self.client.get(reverse("gestion_cancelaciones"))

        self.assertEqual(len(respuesta.context["pendientes"]), 2)
        self.assertContains(
            respuesta, reverse("gestion_resolver_cancelacion", args=[de_menor.id, "rechazar"]))
        self.assertNotContains(
            respuesta, reverse("gestion_resolver_cancelacion", args=[de_adulta.id, "rechazar"]))

    def test_un_estudiante_no_entra_a_resolver_cancelaciones(self):
        self.client.force_login(self.adulta.usuario)

        respuesta = self.client.get(reverse("gestion_cancelaciones"))

        self.assertNotEqual(respuesta.status_code, 200)

    # -- lo que ve el profesor ----------------------------------------------

    def test_el_estudiante_no_desaparece_del_panel_de_su_profesor(self):
        """Si la cancelación lo borrara de la lista, el profesor lo perdería
        de vista justo cuando más falta hace enterarse."""
        usuario = User.objects.create_user(username="profe", password="x")
        profesor = Perfil.objects.create(
            usuario=usuario, rol="profesor", nombre_completo="Profe",
            fecha_nacimiento=date(1985, 1, 1), telefono="3000000008",
        )
        self.violin.profesor = profesor
        self.violin.save(update_fields=["profesor"])
        matricula = self.matricular(self.adulta)
        self.pedir_cancelacion(self.adulta, matricula)
        self.client.force_login(usuario)

        respuesta = self.client.get(reverse("panel"))

        self.assertContains(respuesta, "Ana Ruiz")
        self.assertContains(respuesta, "Pidió cancelar")


class DesercionEstadisticasTests(TestCase):
    """Las dos cifras de permanencia del árbol de departamentos."""

    def setUp(self):
        hoy = date.today()
        self.previo = Periodo.objects.create(
            nombre="anterior", fecha_inicio=hoy - timedelta(days=400),
            fecha_fin=hoy - timedelta(days=200),
        )
        self.actual = Periodo.objects.create(
            nombre="actual", fecha_inicio=hoy - timedelta(days=30),
            fecha_fin=hoy + timedelta(days=90), activo=True, matriculas_abiertas=True,
        )
        area = Area.objects.create(nombre="Música")
        self.violin = Promotoria.objects.create(nombre="Violín", area=area)

        usuario = User.objects.create_user(username="admin1", password="x")
        Perfil.objects.create(
            usuario=usuario, rol="administrador", nombre_completo="Admin",
            fecha_nacimiento=date(1980, 1, 1), telefono="3000000001",
        )
        self.client.force_login(usuario)

    def estudiante(self, username):
        usuario = User.objects.create_user(username=username, password="x")
        perfil = Perfil.objects.create(
            usuario=usuario, rol="estudiante", nombre_completo=username.title(),
            fecha_nacimiento=date(1995, 1, 1), telefono="3000000000",
        )
        DatosEstudiante.objects.create(perfil=perfil, documento_identidad=username)
        return perfil

    def matricular(self, perfil, periodo, estado="activa"):
        matricula = Matricula(
            estudiante=perfil, promotoria=self.violin, periodo=periodo, estado=estado,
        )
        matricula.full_clean()
        matricula.save()
        return matricula

    def fila(self):
        respuesta = self.client.get(reverse("gestion_estadisticas"))
        self.assertEqual(respuesta.status_code, 200)
        return respuesta.context["arbol_departamentos"][0]["promotorias"][0]

    def test_desercion_dentro_del_periodo(self):
        """Uno de cuatro se retiró: 25% deja, 75% sigue."""
        for i in range(3):
            self.matricular(self.estudiante(f"sigue{i}"), self.actual)
        self.matricular(self.estudiante("sefue"), self.actual, estado="retirada")

        fila = self.fila()

        self.assertEqual(fila["pct_desercion"], 25)
        self.assertEqual(fila["pct_continuan"], 75)

    def test_una_cancelacion_en_tramite_cuenta_como_que_sigue(self):
        """Mientras nadie la apruebe, esa persona no se ha ido."""
        self.matricular(self.estudiante("ana"), self.actual)
        self.matricular(
            self.estudiante("beto"), self.actual, estado=Matricula.ESTADO_CANCELACION)

        fila = self.fila()

        self.assertEqual(fila["pct_desercion"], 0)
        self.assertEqual(fila["total"], 2)

    def test_no_renovacion_respecto_al_periodo_anterior(self):
        """Dos cursaron antes y solo uno volvió: 50% no volvió."""
        vuelve = self.estudiante("vuelve")
        self.matricular(vuelve, self.previo)
        self.matricular(vuelve, self.actual)
        self.matricular(self.estudiante("desaparece"), self.previo)

        fila = self.fila()

        self.assertEqual(fila["pct_no_renovo"], 50)

    def test_sin_periodo_anterior_no_se_inventa_un_cero(self):
        """Un 0% se leería como "no se fue nadie", que es lo contrario."""
        self.previo.delete()
        self.matricular(self.estudiante("ana"), self.actual)

        respuesta = self.client.get(reverse("gestion_estadisticas"))

        self.assertIsNone(respuesta.context["periodo_previo"])
        self.assertIsNone(respuesta.context["arbol_departamentos"][0]["promotorias"][0]["pct_no_renovo"])

    def test_el_arbol_se_acota_al_periodo_en_curso(self):
        """Mezclar periodos haría que las cifras de permanencia no signifiquen nada."""
        self.matricular(self.estudiante("viejo"), self.previo)
        self.matricular(self.estudiante("nuevo"), self.actual)

        self.assertEqual(self.fila()["total"], 1)


class EstadoFinalizadaTests(TestCase):
    """El tercer estado del historial: "Finalizada".

    No es un valor guardado y no está en `Matricula.ESTADOS` a propósito: se
    deduce del calendario. Convertirlo en un cuarto valor real habría obligado
    a migrar las filas y a rehacer `matriculas_renovables`, que busca
    precisamente matrículas ACTIVAS de periodos anteriores — con las filas
    migradas, ningún estudiante antiguo podría renovar. Hay una prueba abajo
    que fija justo eso.
    """

    def setUp(self):
        hoy = date.today()
        self.terminado = Periodo.objects.create(
            nombre="pasado", fecha_inicio=hoy - timedelta(days=400),
            fecha_fin=hoy - timedelta(days=200),
        )
        self.en_curso = Periodo.objects.create(
            nombre="actual", fecha_inicio=hoy - timedelta(days=30),
            fecha_fin=hoy + timedelta(days=90), activo=True, matriculas_abiertas=True,
        )
        self.futuro = Periodo.objects.create(
            nombre="futuro", fecha_inicio=hoy + timedelta(days=120),
            fecha_fin=hoy + timedelta(days=300),
        )
        area = Area.objects.create(nombre="Música")
        self.violin = Promotoria.objects.create(nombre="Violín", area=area)
        self.guitarra = Promotoria.objects.create(nombre="Guitarra", area=area)

        usuario = User.objects.create_user(username="ana", password="x")
        self.ana = Perfil.objects.create(
            usuario=usuario, rol="estudiante", nombre_completo="Ana Ruiz",
            fecha_nacimiento=date(1995, 3, 4), telefono="3000000000",
        )
        DatosEstudiante.objects.create(perfil=self.ana, documento_identidad="123")

    def matricular(self, promotoria, periodo, estado="activa"):
        matricula = Matricula(
            estudiante=self.ana, promotoria=promotoria, periodo=periodo, estado=estado,
        )
        matricula.full_clean()
        matricula.save()
        return matricula

    # -- cuándo un periodo cuenta como terminado ----------------------------

    def test_un_periodo_futuro_no_esta_terminado(self):
        """Mirar solo `activo` lo habría dado por terminado sin haber empezado."""
        self.assertFalse(self.futuro.termino)

    def test_el_periodo_en_curso_no_esta_terminado_aunque_se_pase_de_fecha(self):
        """El personal se retrasa en cerrar y la pantalla sigue admitiendo retiros."""
        self.en_curso.fecha_fin = date.today() - timedelta(days=5)
        self.en_curso.save(update_fields=["fecha_fin"])

        self.assertFalse(self.en_curso.termino)

    def test_un_periodo_pasado_si_esta_terminado(self):
        self.assertTrue(self.terminado.termino)

    # -- qué estado se muestra ----------------------------------------------

    def test_una_activa_de_un_periodo_cerrado_se_lee_finalizada(self):
        matricula = self.matricular(self.violin, self.terminado)

        self.assertEqual(matricula.estado, "activa")          # lo guardado no cambia
        self.assertEqual(matricula.estado_visible, "finalizada")
        self.assertEqual(matricula.estado_visible_display, "Finalizada")

    def test_una_activa_del_periodo_en_curso_sigue_activa(self):
        matricula = self.matricular(self.violin, self.en_curso)

        self.assertEqual(matricula.estado_visible, "activa")

    def test_una_pendiente_de_un_periodo_cerrado_sigue_pendiente(self):
        """Nadie la confirmó: decir que finalizó sería inventarse un desenlace."""
        matricula = self.matricular(self.violin, self.terminado, estado="pendiente")

        self.assertEqual(matricula.estado_visible, "pendiente")

    def test_una_retirada_de_un_periodo_cerrado_sigue_retirada(self):
        """Irse a mitad de camino es justo lo que ese estado cuenta."""
        matricula = self.matricular(self.violin, self.terminado, estado="retirada")

        self.assertEqual(matricula.estado_visible, "retirada")

    # -- lo que no se puede romper ------------------------------------------

    def test_la_renovacion_sigue_encontrando_las_matriculas_de_antes(self):
        """La razón de que "finalizada" no se guarde.

        `matriculas_renovables` busca matrículas ACTIVAS de periodos
        anteriores. Si al cerrar un periodo sus filas cambiaran de estado, esta
        consulta devolvería vacío y ningún estudiante antiguo podría renovar.
        """
        self.matricular(self.violin, self.terminado)

        periodo_anterior, renovables = matriculas_renovables(self.ana, self.en_curso)

        self.assertEqual(periodo_anterior, self.terminado)
        self.assertEqual([m.promotoria for m in renovables], [self.violin])

    def test_el_resumen_sigue_contando_lo_finalizado_como_cursado(self):
        self.matricular(self.violin, self.terminado)

        self.assertEqual(resumen_trayectoria(self.ana)["periodos"], 1)

    # -- en pantalla --------------------------------------------------------

    def test_el_historial_muestra_finalizada_y_no_activa(self):
        self.matricular(self.violin, self.terminado)
        self.matricular(self.guitarra, self.en_curso)
        self.client.force_login(self.ana.usuario)

        respuesta = self.client.get(reverse("mis_matriculas"))

        self.assertContains(respuesta, "estado-finalizada")
        self.assertContains(respuesta, "Finalizada")
        # La del periodo en curso conserva su marcador propio.
        self.assertContains(respuesta, "estado-activa")


class FichaUsuarioTests(TestCase):
    """La ficha de usuario y la jerarquía de roles que decide quién la abre.

    Existe porque el listado de Usuarios contiene los cuatro roles, mientras
    que las fichas que ya había solo servían para estudiantes: al hacer clic
    sobre un profesor no había adónde ir.

    Dos reglas distintas se cruzan aquí y conviene no confundirlas: QUIÉN puede
    abrir la ficha (jerarquía: se mira hacia abajo) y QUÉ se ve dentro de ella
    (la matriz de visibilidad de models.py, donde el contacto de un estudiante
    es del profesor solo si ese estudiante es suyo).
    """

    def setUp(self):
        self.periodo = Periodo.objects.create(
            nombre="2026-1", fecha_inicio=date(2026, 1, 15), fecha_fin=date(2026, 6, 15),
            activo=True, matriculas_abiertas=True,
        )
        area = Area.objects.create(nombre="Música")
        self.profe = self.crear("profe", "profesor", "Profe Violín")
        self.otro_profe = self.crear("profe2", "profesor", "Profe Teatro")
        self.director = self.crear("dire", "director", "Directora")
        self.admin = self.crear("admin1", "administrador", "Admin")
        self.violin = Promotoria.objects.create(
            nombre="Violín", area=area, profesor=self.profe)
        self.otra = Promotoria.objects.create(
            nombre="Actuación", area=area, profesor=self.otro_profe)

        self.mio = self.crear("ana", "estudiante", "Ana Ruiz")
        self.ajeno = self.crear("beto", "estudiante", "Beto Páez")
        DatosEstudiante.objects.create(
            perfil=self.mio, documento_identidad="111",
            acudiente=Acudiente.objects.create(nombre="Madre de Ana", telefono="3001"),
        )
        DatosEstudiante.objects.create(
            perfil=self.ajeno, documento_identidad="222",
            acudiente=Acudiente.objects.create(nombre="Padre de Beto", telefono="3002"),
        )
        self.matricular(self.mio, self.violin)
        self.matricular(self.ajeno, self.otra)

    def crear(self, username, rol, nombre):
        usuario = User.objects.create_user(username=username, password="x")
        return Perfil.objects.create(
            usuario=usuario, rol=rol, nombre_completo=nombre,
            fecha_nacimiento=date(1995, 3, 4), telefono="3000000000",
        )

    def matricular(self, perfil, promotoria):
        matricula = Matricula(
            estudiante=perfil, promotoria=promotoria, periodo=self.periodo, estado="activa",
        )
        matricula.full_clean()
        matricula.save()
        return matricula

    def abrir(self, quien, objetivo):
        self.client.force_login(quien.usuario)
        return self.client.get(reverse("detalle_usuario", args=[objetivo.id]))

    # -- quién puede abrir la ficha (jerarquía) -----------------------------

    def test_el_administrador_abre_la_ficha_de_cualquiera(self):
        for objetivo in (self.profe, self.director, self.admin, self.mio):
            self.assertEqual(self.abrir(self.admin, objetivo).status_code, 200)

    def test_el_director_abre_la_ficha_de_cualquiera(self):
        for objetivo in (self.profe, self.admin, self.mio):
            self.assertEqual(self.abrir(self.director, objetivo).status_code, 200)

    def test_el_profesor_abre_la_de_un_estudiante(self):
        self.assertEqual(self.abrir(self.profe, self.mio).status_code, 200)
        # Incluida la de un estudiante que no es suyo: la jerarquía decide el
        # acceso a la ficha; lo que se ve dentro lo decide la otra regla.
        self.assertEqual(self.abrir(self.profe, self.ajeno).status_code, 200)

    def test_el_profesor_no_mira_hacia_los_lados_ni_hacia_arriba(self):
        for objetivo in (self.otro_profe, self.director, self.admin):
            self.assertEqual(self.abrir(self.profe, objetivo).status_code, 302)

    def test_un_estudiante_no_abre_ninguna(self):
        self.assertNotEqual(self.abrir(self.mio, self.ajeno).status_code, 200)
        self.assertNotEqual(self.abrir(self.mio, self.profe).status_code, 200)

    # -- qué se ve dentro (matriz de visibilidad) ---------------------------

    def test_el_profesor_ve_el_contacto_de_SU_estudiante(self):
        respuesta = self.abrir(self.profe, self.mio)

        self.assertTrue(respuesta.context["ve_contacto"])
        self.assertContains(respuesta, "Madre de Ana")

    def test_el_profesor_no_ve_el_contacto_de_un_estudiante_ajeno(self):
        """Poder abrir la ficha no desbloquea el teléfono ni el acudiente."""
        respuesta = self.abrir(self.profe, self.ajeno)

        self.assertFalse(respuesta.context["ve_contacto"])
        self.assertNotContains(respuesta, "Padre de Beto")

    def test_el_director_ve_el_contacto_de_cualquier_estudiante(self):
        respuesta = self.abrir(self.director, self.ajeno)

        self.assertTrue(respuesta.context["ve_contacto"])
        self.assertContains(respuesta, "Padre de Beto")

    def test_la_ficha_de_un_profesor_lista_sus_promotorias(self):
        respuesta = self.abrir(self.admin, self.profe)

        self.assertContains(respuesta, "Violín")
        self.assertNotContains(respuesta, "Actuación")

    def test_solo_el_administrador_llega_a_la_encuesta_y_el_documento(self):
        del_admin = self.abrir(self.admin, self.mio)
        del_director = self.abrir(self.director, self.mio)

        # Se comprueba la etiqueta del botón y no su URL: la de la trayectoria
        # (/panel/estudiante/<id>/historial/) lleva dentro a la otra como
        # prefijo, así que buscar la ruta daría un falso positivo.
        self.assertContains(del_admin, "Ver encuesta y documento")
        self.assertNotContains(del_director, "Ver encuesta y documento")
        # El director sí conserva el acceso a la trayectoria.
        self.assertContains(del_director, "Ver trayectoria completa")

    # -- el nombre como enlace ----------------------------------------------

    def test_en_usuarios_el_nombre_lleva_a_la_ficha(self):
        self.client.force_login(self.admin.usuario)

        respuesta = self.client.get(reverse("usuario_lista"))

        self.assertContains(respuesta, reverse("detalle_usuario", args=[self.profe.id]))

    def test_el_panel_no_ofrece_al_profesor_un_enlace_que_lo_rebotaria(self):
        """El nombre solo se pinta como enlace si quien mira puede abrirlo."""
        self.client.force_login(self.profe.usuario)

        respuesta = self.client.get(reverse("panel"))

        self.assertContains(respuesta, reverse("detalle_usuario", args=[self.mio.id]))
        # El suyo propio aparece como profesor de la promotoría, y no es enlace.
        self.assertNotContains(respuesta, reverse("detalle_usuario", args=[self.profe.id]))

    def test_las_pantallas_del_estudiante_no_enlazan_a_nadie(self):
        """Un estudiante ve nombres, nunca puertas: la matriz no le da más."""
        self.client.force_login(self.mio.usuario)

        for vista in ("mis_companeros", "promotorias_disponibles"):
            respuesta = self.client.get(reverse(vista))
            self.assertEqual(respuesta.status_code, 200)
            self.assertNotContains(respuesta, "/panel/usuario/")


class TortaTests(SimpleTestCase):
    """Geometría y honestidad de las gráficas de torta (género y zona).

    `_torta` no toca la base de datos: recibe el conteo ya hecho, así que se
    prueba con filas sintéticas. Lo que hay que fijar es la aritmética de los
    arcos y, sobre todo, cuál es el TODO de la torta.
    """

    CIRCUNFERENCIA = 2 * math.pi * RADIO_TORTA

    def filas(self, *pares):
        return [{"etiqueta": etiqueta, "total": total} for etiqueta, total in pares]

    def test_el_todo_es_el_total_de_encuestas_no_las_respuestas(self):
        """Lo que impide que la torta mienta en una pregunta opcional.

        Una sola respuesta de dieciséis no significa que el 100% de la gente
        viva en zona rural.
        """
        torta = _torta(self.filas(("Urbana", 0), ("Rural", 1)), total_encuestas=16)

        partes = {e["etiqueta"]: e["parte"] for e in torta["leyenda"]}
        self.assertEqual(partes["Rural"], 6)
        self.assertEqual(partes["Sin responder"], 94)

    def test_sin_huecos_cuando_todos_respondieron(self):
        """En una pregunta obligatoria no sobra nadie, así que no hay sector gris."""
        torta = _torta(self.filas(("Femenino", 1), ("Masculino", 3)), total_encuestas=4)

        self.assertNotIn("Sin responder", [e["etiqueta"] for e in torta["leyenda"]])
        self.assertEqual(torta["total"], 4)

    def test_las_partes_suman_cien(self):
        torta = _torta(
            self.filas(("Urbana", 2), ("Rural", 1), ("Centro poblado", 1)),
            total_encuestas=4,
        )

        self.assertEqual(sum(e["parte"] for e in torta["leyenda"]), 100)

    def test_los_sectores_se_encadenan_sin_solaparse(self):
        """Cada sector arranca donde acaba el anterior, medido en la circunferencia."""
        torta = _torta(self.filas(("Urbana", 1), ("Rural", 3)), total_encuestas=4)

        primero, segundo = torta["sectores"]
        self.assertEqual(primero["desfase"], 0)
        # El segundo empieza a un cuarto de vuelta: 1 de 4.
        self.assertAlmostEqual(-segundo["desfase"], self.CIRCUNFERENCIA / 4, places=1)
        # Y cada arco lleva restado el hueco de separación.
        self.assertAlmostEqual(
            primero["trazo"], self.CIRCUNFERENCIA / 4 - SEPARACION_TORTA, places=1,
        )

    def test_una_opcion_sin_respuestas_no_dibuja_sector_pero_sale_en_la_leyenda(self):
        """Si desapareciera del todo, nadie sabría que la opción existe."""
        torta = _torta(self.filas(("Urbana", 0), ("Rural", 4)), total_encuestas=4)

        self.assertEqual([s["etiqueta"] for s in torta["sectores"]], ["Rural"])
        self.assertIn("Urbana", [e["etiqueta"] for e in torta["leyenda"]])

    def test_el_color_sigue_a_la_opcion_y_no_a_su_puesto(self):
        """Un filtro que cambie los conteos no puede repintar a los demás."""
        muchos = _torta(self.filas(("Urbana", 5), ("Rural", 1)), total_encuestas=6)
        pocos = _torta(self.filas(("Urbana", 0), ("Rural", 6)), total_encuestas=6)

        color = lambda t, cual: next(
            e["color"] for e in t["leyenda"] if e["etiqueta"] == cual
        )
        self.assertEqual(color(muchos, "Urbana"), color(pocos, "Urbana"))
        self.assertEqual(color(muchos, "Rural"), color(pocos, "Rural"))

    def test_un_solo_sector_da_la_vuelta_entera(self):
        """Restarle el hueco dejaría una muesca contra sí mismo."""
        torta = _torta(self.filas(("Urbana", 4)), total_encuestas=4)

        [unico] = torta["sectores"]
        self.assertAlmostEqual(unico["trazo"], self.CIRCUNFERENCIA, places=1)

    def test_sin_ninguna_encuesta_no_hay_torta(self):
        torta = _torta(self.filas(("Urbana", 0), ("Rural", 0)), total_encuestas=0)

        self.assertEqual(torta["sectores"], [])
        self.assertEqual(torta["total"], 0)
