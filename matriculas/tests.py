"""Pruebas del límite configurable de promotorías por estudiante y periodo.

El límite dejó de ser una constante de Python (`LIMITE_PROMOTORIAS_POR_PERIODO`)
y ahora vive en `ConfiguracionInstitucion`, editable desde Gestión →
Configuración. Eso cambió quién impone la regla: antes bastaba el índice único
sobre `ranura`, porque había exactamente tantas ranuras como permitía el límite;
ahora el esquema solo conoce el techo absoluto (`RANURA_MAXIMA_ABSOLUTA`) y la
regla de negocio la aplica `Matricula.clean()`. Estas pruebas cubren ese cambio.
"""

from datetime import date

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from .models import (
    RANURA_MAXIMA_ABSOLUTA,
    Area, ConfiguracionInstitucion, DatosEstudiante, Matricula, Perfil,
    Periodo, Promotoria,
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
