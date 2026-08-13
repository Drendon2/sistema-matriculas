"""
Modelos del sistema de matrículas — Casa de la Cultura (entidad pública).
Stack: Django + PostgreSQL.

Notas de diseño:
- Todos los roles comparten un `Perfil` (foto + encuesta demográfica). La foto
  y, para estudiantes, la copia del documento NO se piden en los formularios
  públicos de autorregistro (registro/inscripcion): quedan en blanco hasta
  que la persona las sube ya logueada, en "Mi perfil" — evita que cualquiera
  pueda subir archivos arbitrarios desde un formulario sin autenticar.
- Los estudiantes tienen, además, `DatosEstudiante` (documento + acudiente).
- Las reglas de VISIBILIDAD por campo (quién ve qué) NO van aquí: se aplican
  en la capa de vistas/permisos. Este archivo solo define los DATOS y las
  reglas de INTEGRIDAD (cupos, acudiente para menores, matrícula única).

Recordatorio de visibilidad (se implementa en las vistas, no en el modelo):
    nombre, foto ...... admin, director, profesor, compañeros de la MISMA promotoría
    edad, teléfono,
    acudiente ......... admin, director, profesor (profesor solo de SUS promotorías)
    encuesta .......... solo el dueño de la cuenta y el administrador
    copia_documento ... solo el administrador

Flujo de matrícula/grupos:
    El estudiante se matricula en una Promotoria (no elige horario). El
    profesor de esa promotoría crea los Grupo según su disponibilidad y
    reparte ahí a los estudiantes ya matriculados (Matricula.grupo queda en
    blanco hasta que el profesor lo asigna).
"""

import colorsys
import io
import os
from datetime import date

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models, transaction
from django.db.models import Q
from django.db.utils import OperationalError, ProgrammingError
from django.contrib.auth.models import User
from PIL import Image, ImageOps


# ---------------------------------------------------------------------------
# Marca de la institución
# ---------------------------------------------------------------------------

# Parámetros medidos sobre el par de verdes que el sistema ya usaba
# (#0a7a59 -> #065a41 / #dbf2e7): derivar con estos números reproduce esos
# mismos tonos, así que cambiar a otra marca conserva la relación entre los
# tres colores en vez de inventar una nueva.
FACTOR_ACENTO_OSCURO = 0.727
LUZ_ACENTO_SUAVE = 0.904
SATURACION_MAXIMA_SUAVE = 0.469


def _hex_a_rgb(valor):
    valor = valor.lstrip("#")
    return tuple(int(valor[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _rgb_a_hex(r, g, b):
    return "#%02x%02x%02x" % tuple(max(0, min(255, round(c * 255))) for c in (r, g, b))


def acento_oscuro(color_hex):
    """Tono de hover/activo: el mismo color con la luminosidad bajada."""
    h, l, s = colorsys.rgb_to_hls(*_hex_a_rgb(color_hex))
    return _rgb_a_hex(*colorsys.hls_to_rgb(h, l * FACTOR_ACENTO_OSCURO, s))


def acento_suave(color_hex):
    """Tinte claro para anillos de foco y fondos de mensaje de éxito."""
    h, l, s = colorsys.rgb_to_hls(*_hex_a_rgb(color_hex))
    return _rgb_a_hex(*colorsys.hls_to_rgb(h, LUZ_ACENTO_SUAVE, min(s, SATURACION_MAXIMA_SUAVE)))


def _luminancia(color_hex):
    def canal(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (canal(c) for c in _hex_a_rgb(color_hex))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contraste(color_a, color_b):
    """Razón de contraste WCAG entre dos colores hex."""
    la, lb = _luminancia(color_a), _luminancia(color_b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


# Techo de ranuras GRABADO en el esquema (ver Matricula.Meta.constraints).
# NO es la regla de negocio: esa es `limite_promotorias_por_periodo`, editable
# en caliente desde Gestión → Configuración. Este número solo existe porque un
# CheckConstraint de Postgres no puede consultar una fila de configuración: se
# fija al correr la migración y ahí se queda. Se eligió holgado para que subir
# el límite operativo nunca exija una migración; si algún día hicieran falta
# más de 6, hay que migrar los dos constraints de Matricula.
#
# Vive aquí arriba, y no junto a Matricula, porque el validador del campo de
# configuración lo necesita antes.
RANURA_MAXIMA_ABSOLUTA = 6


class ConfiguracionInstitucion(models.Model):
    """Ajustes de la institución que usa el sistema, editables sin tocar código.

    Singleton de fila fija (pk=1): el proyecto sirve a UNA institución a la vez,
    pero ninguno de estos datos debería estar quemado en el código si se quiere
    reinstalar para otra entidad sin tocar plantillas.

    Cubre dos cosas distintas:

    - La marca (nombre, logo, color de acento), que solo afecta cómo se ve el
      sistema.
    - Una regla operativa de matrícula: cuántas promotorías puede cursar un
      estudiante en un mismo periodo. Esta SÍ cambia el comportamiento, así que
      lo que se guarde aquí gobierna las validaciones (ver `Matricula.clean`).

    Sigue sin incluir nada del catálogo académico (áreas, promotorías, periodos,
    cupos): eso son registros propios, no ajustes de una sola fila.
    """

    nombre_institucion = models.CharField(
        max_length=80, default="Casa de la Cultura",
        verbose_name="nombre de la institución",
        help_text="Aparece en la cabecera, los títulos de página y el admin de Django.",
    )
    logo = models.ImageField(
        upload_to="institucion/", blank=True,
        help_text="Si se deja vacío se usa el logo que trae el proyecto por defecto.",
    )
    color_acento = models.CharField(
        max_length=7, default="#0a7a59", verbose_name="color de acento",
        validators=[RegexValidator(
            regex=r"^#[0-9a-fA-F]{6}$",
            message="Escribe el color en formato hexadecimal de 6 dígitos, por ejemplo #0a7a59.",
        )],
        help_text=(
            "Único color de marca del sistema: botones, enlaces, foco y mensajes de éxito. "
            "Los tonos hover y de fondo se derivan de este automáticamente."
        ),
    )
    limite_promotorias_por_periodo = models.PositiveSmallIntegerField(
        default=2,
        verbose_name="promotorías por estudiante y periodo",
        validators=[
            MinValueValidator(
                1, message="El límite tiene que ser de al menos 1 promotoría por periodo.",
            ),
            MaxValueValidator(
                RANURA_MAXIMA_ABSOLUTA,
                message=(
                    f"El máximo que admite la base de datos es {RANURA_MAXIMA_ABSOLUTA} "
                    "promotorías por periodo. Subir de ahí exige una migración."
                ),
            ),
        ],
        help_text=(
            "Cuántas promotorías puede cursar un mismo estudiante en un periodo. "
            "Cuentan las matrículas pendientes y las activas; las retiradas liberan cupo. "
            "Bajarlo no retira ni rompe las matrículas que ya existen: solo impide pedir "
            "más a quien ya esté en el nuevo límite o por encima."
        ),
    )

    class Meta:
        verbose_name = "Configuración de la institución"
        verbose_name_plural = "Configuración de la institución"

    def __str__(self):
        return self.nombre_institucion

    def save(self, *args, **kwargs):
        # Fila única: cualquier guardado escribe sobre la misma.
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """No se borra: sin configuración el sistema se quedaría sin marca."""
        raise ValidationError("La configuración de la institución no se puede eliminar.")

    @classmethod
    def actual(cls):
        """La configuración vigente, creándola con los valores por defecto si falta.

        Se resuelve en caliente y no por migración de datos, para que un
        proyecto recién clonado funcione sin pasos extra. Si la tabla todavía no
        existe (antes de migrar) devuelve una instancia en memoria con los
        defaults, porque de esto cuelga un context processor que corre en cada
        página y no debe tumbar el sitio.
        """
        try:
            configuracion, _ = cls.objects.get_or_create(pk=1)
            return configuracion
        except (OperationalError, ProgrammingError):
            return cls()

    @property
    def color_acento_oscuro(self):
        return acento_oscuro(self.color_acento)

    @property
    def color_acento_suave(self):
        return acento_suave(self.color_acento)

    @property
    def contraste_texto_boton(self):
        """Contraste del texto blanco sobre el acento (los botones primarios)."""
        return contraste("#ffffff", self.color_acento)


# ---------------------------------------------------------------------------
# Catálogo académico
# ---------------------------------------------------------------------------

class Area(models.Model):
    """Departamento artístico: Música, Danza, Teatro, Pintura... (los crea el admin)."""
    nombre = models.CharField(max_length=60, unique=True)

    class Meta:
        verbose_name = "Área"
        verbose_name_plural = "Áreas"

    def __str__(self):
        return self.nombre


class Periodo(models.Model):
    """Periodo semestral de matrícula. Ej.: '2026-1'.

    `activo` dice cuál es el periodo en curso (el que reciben todas las
    pantallas). `matriculas_abiertas` es otra cosa: la ventana en la que se
    admite gente nueva o renovaciones. La Casa de la Cultura no recibe
    matrículas todo el año, solo al principio y a mitad, así que el periodo
    puede estar en curso con las matrículas ya cerradas.
    """
    nombre = models.CharField(max_length=20, unique=True)
    fecha_inicio = models.DateField(verbose_name="fecha de inicio")
    fecha_fin = models.DateField(verbose_name="fecha de fin")
    activo = models.BooleanField(default=False)
    matriculas_abiertas = models.BooleanField(
        default=False, verbose_name="matrículas abiertas",
        help_text="Mientras esté cerrado, nadie puede inscribirse ni renovar en este periodo.",
    )

    class Meta:
        verbose_name = "Periodo"
        verbose_name_plural = "Periodos"
        constraints = [
            # Solo puede haber UN periodo en curso. Sin esto,
            # `filter(activo=True).first()` devolvería una fila arbitraria (no
            # hay ORDER BY), y de esa función cuelgan la ventana de matrículas,
            # el retiro y la renovación.
            models.UniqueConstraint(
                fields=["activo"],
                condition=Q(activo=True),
                name="un_solo_periodo_activo",
                violation_error_message=(
                    "Ya hay un periodo en curso. Cambia cuál es el periodo en curso desde "
                    "Gestión → Iniciar / finalizar matrículas."
                ),
            )
        ]

    def __str__(self):
        return self.nombre

    @classmethod
    def en_curso(cls):
        """El periodo activo, o None si el personal no ha marcado ninguno."""
        return cls.objects.filter(activo=True).first()

    @classmethod
    def poner_en_curso(cls, periodo):
        """Deja `periodo` como el único en curso, en una sola transacción.

        Al periodo que sale se le cierran también las matrículas: dejar el flag
        abierto en un periodo que ya no está en curso solo serviría para
        confundir a quien lo reactive meses después.
        """
        with transaction.atomic():
            cls.objects.filter(activo=True).exclude(pk=periodo.pk).update(
                activo=False, matriculas_abiertas=False
            )
            periodo.activo = True
            periodo.save(update_fields=["activo"])
        return periodo

    @property
    def admite_matriculas(self):
        return self.activo and self.matriculas_abiertas


# ---------------------------------------------------------------------------
# Usuarios: perfil común a TODOS los roles
# ---------------------------------------------------------------------------

FOTO_PERFIL_LADO_MAXIMO = 720
FOTO_PERFIL_CALIDAD_WEBP = 82


def _convertir_foto_a_webp(archivo):
    """Reescala (sin ampliar) y convierte una foto subida a WebP.

    Pensado para un sistema de +1800 personas subiendo fotos sobre todo desde
    el celular: WebP reduce el peso frente a JPEG/PNG a calidad similar, y
    limitar el lado más largo evita guardar fotos de cámara a resolución
    completa cuando la interfaz nunca las muestra a más de unos cientos de
    píxeles. `exif_transpose` corrige la rotación de cámara antes de reescalar.
    """
    imagen = Image.open(archivo)
    imagen = ImageOps.exif_transpose(imagen)
    if imagen.mode not in ("RGB", "RGBA"):
        imagen = imagen.convert("RGBA" if "A" in imagen.getbands() else "RGB")

    ancho, alto = imagen.size
    lado_mayor = max(ancho, alto)
    if lado_mayor > FOTO_PERFIL_LADO_MAXIMO:
        factor = FOTO_PERFIL_LADO_MAXIMO / lado_mayor
        imagen = imagen.resize((round(ancho * factor), round(alto * factor)), Image.LANCZOS)

    buffer = io.BytesIO()
    imagen.save(buffer, format="WEBP", quality=FOTO_PERFIL_CALIDAD_WEBP)
    nombre_base = os.path.splitext(os.path.basename(archivo.name))[0]
    return ContentFile(buffer.getvalue(), name=f"{nombre_base}.webp")


class Perfil(models.Model):
    """Extiende al usuario de Django. Uno por cada usuario, sin importar el rol."""

    ROLES = [
        ("administrador", "Administrador"),
        ("director", "Director de escuela"),
        ("profesor", "Profesor"),
        ("estudiante", "Estudiante"),
    ]

    usuario = models.OneToOneField(User, on_delete=models.CASCADE, related_name="perfil")
    rol = models.CharField(
        max_length=15, choices=ROLES, blank=True,
        help_text="En blanco = cuenta creada por autorregistro, pendiente de que un director/administrador le asigne rol.",
    )
    nombre_completo = models.CharField(max_length=90, verbose_name="nombre completo")
    fecha_nacimiento = models.DateField(verbose_name="fecha de nacimiento")  # se calcula la edad
    telefono = models.CharField(max_length=15, verbose_name="teléfono")
    # En blanco hasta que la persona la sube en "Mi perfil" (ver nota de diseño arriba).
    foto_perfil = models.ImageField(upload_to="fotos_perfil/", verbose_name="foto de perfil", blank=True)

    class Meta:
        verbose_name = "Perfil"
        verbose_name_plural = "Perfiles"

    def save(self, *args, **kwargs):
        # `_committed` es False solo para un archivo recién asignado desde un
        # formulario, nunca para uno ya guardado que se relee de la base de
        # datos — así la conversión corre una sola vez, en la subida real.
        if self.foto_perfil and not self.foto_perfil._committed:
            self.foto_perfil = _convertir_foto_a_webp(self.foto_perfil)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.nombre_completo} ({self.get_rol_display() or 'sin rol asignado'})"

    @property
    def edad(self):
        hoy = date.today()
        return (
            hoy.year - self.fecha_nacimiento.year
            - ((hoy.month, hoy.day) < (self.fecha_nacimiento.month, self.fecha_nacimiento.day))
        )

    @property
    def es_menor(self):
        return self.edad < 18


class EncuestaDemografica(models.Model):
    """Obligatoria para todos los usuarios. Los campos SENSIBLES quedan opcionales."""

    GENEROS = [
        ("f", "Femenino"),
        ("m", "Masculino"),
        ("o", "Otro"),
        ("ns", "Prefiero no responder"),
    ]
    ESTRATOS = [(i, str(i)) for i in range(1, 7)]

    perfil = models.OneToOneField(Perfil, on_delete=models.CASCADE, related_name="encuesta")
    genero = models.CharField(max_length=2, choices=GENEROS, verbose_name="género")
    barrio = models.CharField(max_length=60)
    estrato = models.PositiveSmallIntegerField(choices=ESTRATOS)
    nivel_educativo = models.CharField(max_length=40, verbose_name="nivel educativo")
    ocupacion = models.CharField(max_length=40, verbose_name="ocupación")

    # Datos sensibles (Ley 1581): opcionales aunque la encuesta sea obligatoria.
    grupo_etnico = models.CharField(max_length=40, blank=True, verbose_name="grupo étnico")
    discapacidad = models.CharField(max_length=80, blank=True)

    # Autorización de tratamiento de datos (para menores la otorga el acudiente).
    autoriza_tratamiento_datos = models.BooleanField(default=False, verbose_name="autoriza tratamiento de datos")
    fecha_autorizacion = models.DateTimeField(null=True, blank=True, verbose_name="fecha de autorización")

    class Meta:
        verbose_name = "Encuesta demográfica"
        verbose_name_plural = "Encuestas demográficas"

    def __str__(self):
        return f"Encuesta de {self.perfil.nombre_completo}"


class EncuestaSatisfaccion(models.Model):
    """Encuesta que llena un estudiante ANTIGUO al renovar, sobre el periodo que cursó.

    Es distinta de `EncuestaDemografica`: aquella describe a la persona y se
    llena una sola vez; esta evalúa un periodo concreto y se repite cada vez
    que el estudiante renueva. Por eso va atada a (perfil, periodo) y no es
    OneToOne con el perfil.

    Corta a propósito: es el trámite que acompaña al botón de renovar, no un
    estudio. El comentario es el único campo opcional.
    """

    ESCALA = [(i, str(i)) for i in range(1, 6)]

    perfil = models.ForeignKey(Perfil, on_delete=models.CASCADE, related_name="encuestas_satisfaccion")
    periodo = models.ForeignKey(
        Periodo, on_delete=models.PROTECT, related_name="encuestas_satisfaccion",
        help_text="El periodo que el estudiante evalúa, no aquel al que se renueva.",
    )
    satisfaccion_general = models.PositiveSmallIntegerField(
        choices=ESCALA, verbose_name="satisfacción general",
    )
    calificacion_profesor = models.PositiveSmallIntegerField(
        choices=ESCALA, verbose_name="acompañamiento del profesor",
    )
    horario_funciono = models.BooleanField(verbose_name="el horario le funcionó")
    recomendaria = models.BooleanField(verbose_name="recomendaría la promotoría")
    comentario = models.TextField(blank=True)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Encuesta de satisfacción"
        verbose_name_plural = "Encuestas de satisfacción"
        constraints = [
            models.UniqueConstraint(
                fields=["perfil", "periodo"],
                name="una_encuesta_satisfaccion_por_periodo",
                violation_error_message="Ya respondiste la encuesta de satisfacción de ese periodo.",
            )
        ]

    def __str__(self):
        return f"Satisfacción de {self.perfil.nombre_completo} en {self.periodo}"


class Acudiente(models.Model):
    """Responsable de un estudiante menor de edad."""
    nombre = models.CharField(max_length=90)
    telefono = models.CharField(max_length=15, verbose_name="teléfono")
    autoriza_tratamiento_datos = models.BooleanField(default=False, verbose_name="autoriza tratamiento de datos")
    fecha_autorizacion = models.DateTimeField(null=True, blank=True, verbose_name="fecha de autorización")

    class Meta:
        verbose_name = "Acudiente"
        verbose_name_plural = "Acudientes"

    def __str__(self):
        return self.nombre


class DatosEstudiante(models.Model):
    """Datos que solo tienen los usuarios con rol 'estudiante'."""
    perfil = models.OneToOneField(
        Perfil, on_delete=models.CASCADE, related_name="datos_estudiante"
    )
    documento_identidad = models.CharField(max_length=15, unique=True, verbose_name="documento de identidad")
    # La COPIA del documento solo la puede ver el administrador (control en las vistas).
    # En blanco tras la inscripción pública; se sube después en "Mi perfil" y NO
    # bloquea que el profesor/director confirme la matrícula mientras tanto.
    copia_documento = models.FileField(upload_to="documentos/", verbose_name="copia del documento", blank=True)
    acudiente = models.ForeignKey(
        Acudiente, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="estudiantes",
    )

    class Meta:
        verbose_name = "Datos del estudiante"
        verbose_name_plural = "Datos de estudiantes"

    def clean(self):
        # Regla de negocio: los menores de edad DEBEN tener acudiente.
        if self.perfil.es_menor and self.acudiente is None:
            raise ValidationError(
                "Los estudiantes menores de edad deben registrar un acudiente."
            )

    def __str__(self):
        return self.perfil.nombre_completo


# ---------------------------------------------------------------------------
# Promotorías, grupos y matrículas
# ---------------------------------------------------------------------------

class Promotoria(models.Model):
    """Una promotoría (ej. Violín). La dicta un solo profesor (puede quedar sin asignar)."""
    nombre = models.CharField(max_length=60)
    area = models.ForeignKey(Area, on_delete=models.PROTECT, related_name="promotorias")
    profesor = models.ForeignKey(
        Perfil, on_delete=models.PROTECT, related_name="promotorias_dictadas",
        limit_choices_to={"rol": "profesor"},
        null=True, blank=True,
    )

    class Meta:
        verbose_name = "Promotoría"
        verbose_name_plural = "Promotorías"

    def __str__(self):
        return f"{self.nombre} ({self.area})"

    def cupo_en(self, periodo):
        """Cupo máximo fijado para ese periodo, o None si la promotoría no tiene tope."""
        if periodo is None:
            return None
        cupo = self.cupos.filter(periodo=periodo).first()
        return cupo.cupo_maximo if cupo is not None else None

    def ocupados_en(self, periodo, excluir_matricula_pk=None):
        """Matrículas que ocupan cupo: pendientes y activas (las retiradas lo liberan)."""
        if periodo is None:
            return 0
        qs = self.matriculas.filter(periodo=periodo).exclude(estado="retirada")
        if excluir_matricula_pk is not None:
            qs = qs.exclude(pk=excluir_matricula_pk)
        return qs.count()

    def cupos_disponibles(self, periodo):
        """Cupos libres en el periodo, o None si no hay tope definido."""
        maximo = self.cupo_en(periodo)
        if maximo is None:
            return None
        return maximo - self.ocupados_en(periodo)


class CupoPromotoria(models.Model):
    """Cuántos estudiantes admite una promotoría en un periodo concreto.

    Va por periodo y no como campo de `Promotoria` a propósito: al abrir
    matrículas el profesor (o director/administrador) fija un cupo nuevo sin
    borrar el del periodo anterior, así el histórico queda reconstruible.

    Una promotoría SIN cupo definido para el periodo no tiene tope: es el
    estado por defecto y no bloquea a nadie.
    """

    promotoria = models.ForeignKey(Promotoria, on_delete=models.CASCADE, related_name="cupos")
    periodo = models.ForeignKey(Periodo, on_delete=models.CASCADE, related_name="cupos_promotoria")
    cupo_maximo = models.PositiveIntegerField(verbose_name="cupo máximo")

    class Meta:
        verbose_name = "Cupo de promotoría"
        verbose_name_plural = "Cupos de promotoría"
        constraints = [
            models.UniqueConstraint(
                fields=["promotoria", "periodo"],
                name="un_cupo_por_promotoria_y_periodo",
            )
        ]

    def __str__(self):
        return f"{self.promotoria} — {self.periodo}: {self.cupo_maximo}"


class Grupo(models.Model):
    """Promotoría + nivel: horario concreto creado por el profesor.

    El profesor lo crea según su disponibilidad y reparte ahí a los
    estudiantes que ya se matricularon en la promotoría.
    """

    NIVELES = [
        ("basico", "Básico"),
        ("intermedio", "Intermedio"),
        ("avanzado", "Avanzado"),
    ]

    promotoria = models.ForeignKey(Promotoria, on_delete=models.CASCADE, related_name="grupos")
    nivel = models.CharField(max_length=12, choices=NIVELES)
    horario = models.CharField(max_length=60)
    salon = models.CharField(max_length=40, verbose_name="salón")
    cupo_maximo = models.PositiveIntegerField(verbose_name="cupo máximo")

    class Meta:
        verbose_name = "Grupo"
        verbose_name_plural = "Grupos"
        constraints = [
            models.UniqueConstraint(fields=["promotoria", "nivel"], name="un_nivel_por_promotoria")
        ]

    def __str__(self):
        return f"{self.promotoria.nombre} - {self.get_nivel_display()}"

    def cupos_disponibles(self, periodo):
        ocupados = self.matriculas.filter(periodo=periodo, estado="activa").count()
        return self.cupo_maximo - ocupados


def limite_promotorias():
    """Cuántas promotorías puede cursar un estudiante en un mismo periodo.

    Sale de `ConfiguracionInstitucion` (Gestión → Configuración), no de una
    constante: el administrador lo cambia sin tocar código ni migrar. Cuentan
    las matrículas pendientes y activas — una solicitud pendiente ya ocupa
    cupo, para que nadie pida otra mientras espera confirmación —, y las
    retiradas (incluidas las rechazadas, que quedan retiradas) lo liberan.
    """
    return ConfiguracionInstitucion.actual().limite_promotorias_por_periodo


class Matricula(models.Model):
    """Inscripción de un estudiante en una PROMOTORÍA, para un periodo dado.

    El estudiante no elige grupo/horario al matricularse: `grupo` queda en
    blanco hasta que el profesor divide a los matriculados según su horario.

    Toda matrícula nueva nace "pendiente": el profesor (o director/admin) de
    la promotoría debe confirmarla antes de que cuente como activa, y solo
    entonces se le puede asignar un grupo.

    Un estudiante no puede acumular más promotorías sin retirar en el mismo
    periodo que las que permita la configuración de la institución (ver
    `limite_promotorias` y `clean`).
    """

    ESTADOS = [
        ("pendiente", "Pendiente de confirmación"),
        ("activa", "Activa"),
        ("retirada", "Retirada"),
    ]

    estudiante = models.ForeignKey(
        Perfil, on_delete=models.CASCADE, related_name="matriculas",
        limit_choices_to={"rol": "estudiante"},
    )
    promotoria = models.ForeignKey(Promotoria, on_delete=models.PROTECT, related_name="matriculas")
    grupo = models.ForeignKey(
        Grupo, on_delete=models.PROTECT, related_name="matriculas",
        null=True, blank=True,
        help_text="Lo asigna el profesor al dividir a los estudiantes matriculados.",
    )
    periodo = models.ForeignKey(Periodo, on_delete=models.PROTECT, related_name="matriculas")
    fecha = models.DateTimeField(auto_now_add=True)
    estado = models.CharField(max_length=10, choices=ESTADOS, default="pendiente")
    ranura = models.PositiveSmallIntegerField(
        default=1,
        help_text=(
            "Cuál de los cupos del estudiante ocupa esta matrícula en el periodo. "
            "La asigna el sistema; es lo que permite que la base de datos misma "
            "impida que dos matrículas compartan cupo."
        ),
    )

    class Meta:
        verbose_name = "Matrícula"
        verbose_name_plural = "Matrículas"
        constraints = [
            models.UniqueConstraint(
                fields=["estudiante", "promotoria", "periodo"],
                name="unica_matricula_por_periodo",
            ),
            # Techo absoluto, no la regla de negocio: el límite real es
            # configurable y siempre <= RANURA_MAXIMA_ABSOLUTA, así que este
            # CheckConstraint solo ataja valores imposibles.
            models.CheckConstraint(
                condition=Q(ranura__gte=1) & Q(ranura__lte=RANURA_MAXIMA_ABSOLUTA),
                name="ranura_valida",
            ),
            # Dos matrículas sin retirar del mismo estudiante en el mismo
            # periodo no pueden compartir ranura. Las retiradas quedan fuera del
            # índice, así que liberan el cupo.
            #
            # Esto ya NO es, por sí solo, el límite de promotorías por periodo:
            # desde que el límite es configurable hay RANURA_MAXIMA_ABSOLUTA
            # ranuras disponibles y el tope operativo puede ser menor, así que
            # quien lo impone es `clean()`. Este índice sigue siendo el que
            # impide duplicar una ranura en una carrera entre dos peticiones
            # simultáneas, y el que acota el daño a RANURA_MAXIMA_ABSOLUTA si
            # algo se salta la capa de aplicación.
            models.UniqueConstraint(
                fields=["estudiante", "periodo", "ranura"],
                condition=~Q(estado="retirada"),
                name="una_matricula_por_ranura_y_periodo",
                violation_error_message=(
                    "Este estudiante ya tiene ocupado su cupo de promotorías para el "
                    "periodo. Retira una matrícula antes de agregar otra."
                ),
            ),
        ]

    @classmethod
    def promotorias_ocupadas(cls, estudiante_id, periodo_id, excluir_pk=None):
        """Cuántos cupos de promotoría tiene ocupados el estudiante en el periodo."""
        qs = cls.objects.filter(
            estudiante_id=estudiante_id, periodo_id=periodo_id
        ).exclude(estado="retirada")
        if excluir_pk is not None:
            qs = qs.exclude(pk=excluir_pk)
        return qs.count()

    def _ranuras_ocupadas_por_otras(self):
        """Ranuras que ya usan las otras matrículas sin retirar del estudiante."""
        return set(
            Matricula.objects.filter(
                estudiante_id=self.estudiante_id, periodo_id=self.periodo_id
            ).exclude(estado="retirada").exclude(pk=self.pk).values_list("ranura", flat=True)
        )

    def _primera_ranura_libre(self, limite=None):
        """Primera ranura libre para el estudiante, o None si ya no tiene cupo.

        Sin cupo = tiene tantas matrículas sin retirar como permite el límite
        configurado. Se mira la CANTIDAD y no si quedan huecos en 1..límite,
        porque desde que el límite es configurable las dos cosas dejaron de ser
        equivalentes: si el administrador lo baja de 2 a 1, un estudiante con su
        única matrícula en la ranura 2 tiene libre la 1 y aun así está en el
        tope. Las ranuras se numeran hasta RANURA_MAXIMA_ABSOLUTA para poder
        colocar las que ya existan por encima del límite nuevo.
        """
        if limite is None:
            limite = limite_promotorias()
        ocupadas = self._ranuras_ocupadas_por_otras()
        if len(ocupadas) >= limite:
            return None
        for ranura in range(1, RANURA_MAXIMA_ABSOLUTA + 1):
            if ranura not in ocupadas:
                return ranura
        return None

    def aumenta_ocupacion(self):
        """True si guardar esta matrícula suma un sitio al cupo de la promotoría.

        Confirmar, rechazar, asignar grupo o mover de grupo NO cambian cuántos
        sitios se ocupan, así que no se les puede aplicar el tope: si no, bajar
        el cupo dejaría al personal sin poder tocar las matrículas que ya
        existen. Solo suman: crear una matrícula, reactivar una retirada, o
        moverla a otra promotoría/periodo.
        """
        if self.estado == "retirada":
            return False
        if self.pk is None:
            return True
        anterior = (
            type(self).objects.filter(pk=self.pk)
            .values("estado", "promotoria_id", "periodo_id").first()
        )
        if anterior is None:
            return True
        if anterior["estado"] == "retirada":
            return True
        return (
            anterior["promotoria_id"] != self.promotoria_id
            or anterior["periodo_id"] != self.periodo_id
        )

    def _colocar_en_ranura_libre(self, limite=None):
        """Mueve la matrícula a una ranura libre si otra ya ocupa la suya.

        Pasa al crear la segunda matrícula (ambas nacen con la ranura por
        defecto) y al reactivar una retirada desde el admin. Devuelve True si
        cambió el valor. Si no queda ninguna libre se deja como está a
        propósito: así el índice único de la base de datos rechaza el guardado.

        `limite` evita releer la configuración cuando quien llama ya la
        resolvió (lo hace `clean`); sin él se consulta aquí.

        Colocar bien la ranura ya NO basta para imponer el límite de
        promotorías: cuando la ranura por defecto está libre esto no hace nada,
        y el estudiante podría pasarse del tope configurado sin que ningún
        índice se queje. De eso se ocupa `clean()`.
        """
        if self.estado == "retirada" or not self.estudiante_id or not self.periodo_id:
            return False
        if self.ranura not in self._ranuras_ocupadas_por_otras():
            return False
        libre = self._primera_ranura_libre(limite)
        if libre is None:
            return False
        self.ranura = libre
        return True

    def save(self, *args, **kwargs):
        if self._colocar_en_ranura_libre():
            campos = kwargs.get("update_fields")
            if campos is not None and "ranura" not in campos:
                kwargs["update_fields"] = list(campos) + ["ranura"]
        super().save(*args, **kwargs)

    def clean(self):
        # Se resuelve una vez y se reparte: `ConfiguracionInstitucion.actual()`
        # es una consulta, y aquí hacen falta dos usos del mismo número.
        limite = limite_promotorias()

        # Colocar la ranura tiene que ir antes de que full_clean() valide las
        # constraints: si no, la segunda matrícula chocaría todavía con la
        # ranura por defecto.
        self._colocar_en_ranura_libre(limite)

        # El límite de promotorías por periodo se comprueba AQUÍ. Antes bastaba
        # el índice único parcial sobre `ranura`, porque había exactamente
        # tantas ranuras como permitía el límite; desde que el límite es
        # configurable el esquema solo conoce el techo absoluto
        # (RANURA_MAXIMA_ABSOLUTA) y no puede consultar la configuración, así
        # que la regla de negocio vive en la aplicación. El índice sigue detrás
        # como red: acota cualquier fuga a RANURA_MAXIMA_ABSOLUTA y cierra la
        # carrera entre dos peticiones simultáneas.
        #
        # Solo se comprueba cuando la operación suma un sitio, por lo mismo que
        # el cupo de la promotoría (ver `aumenta_ocupacion`): bajar el límite no
        # puede dejar al personal sin poder confirmar ni mover las matrículas
        # que ya existen.
        if self.estudiante_id and self.periodo_id and self.aumenta_ocupacion():
            ocupadas = self.promotorias_ocupadas(
                self.estudiante_id, self.periodo_id, excluir_pk=self.pk
            )
            if ocupadas >= limite:
                raise ValidationError(
                    f"Un estudiante puede estar en un máximo de {limite} "
                    f"{'promotoría' if limite == 1 else 'promotorías'} por periodo, y "
                    "este ya tiene ese cupo ocupado. Retira una matrícula antes de "
                    "agregar otra."
                )

        # Cupo de la promotoría en el periodo. Pendientes y activas ocupan cupo
        # por igual: una solicitud sin confirmar ya reserva el sitio, para que
        # el profesor no acabe rechazando una lista de espera entera. Sin cupo
        # definido no hay tope. Solo se comprueba cuando la operación suma un
        # sitio (ver `aumenta_ocupacion`). El mismo tope lo reaplica un trigger
        # de PostgreSQL, que además serializa las peticiones simultáneas.
        if self.promotoria_id and self.periodo_id and self.aumenta_ocupacion():
            maximo = self.promotoria.cupo_en(self.periodo)
            if maximo is not None:
                ocupados = self.promotoria.ocupados_en(self.periodo, excluir_matricula_pk=self.pk)
                if ocupados >= maximo:
                    raise ValidationError(
                        f"{self.promotoria} no tiene cupos disponibles para {self.periodo}: "
                        f"{ocupados} de {maximo} ocupados, contando las solicitudes pendientes."
                    )

        if self.grupo is not None:
            if self.grupo.promotoria_id != self.promotoria_id:
                raise ValidationError("El grupo elegido no pertenece a esta promotoría.")
            # Regla de cupo: no permitir asignar a un grupo lleno (se excluye a sí misma si ya estaba en él).
            ocupados = self.grupo.matriculas.filter(
                periodo=self.periodo, estado="activa"
            ).exclude(pk=self.pk).count()
            if ocupados >= self.grupo.cupo_maximo:
                raise ValidationError("El grupo no tiene cupos disponibles para este periodo.")

    def __str__(self):
        destino = self.grupo or self.promotoria
        return f"{self.estudiante.nombre_completo} -> {destino}"


def matriculas_renovables(perfil, periodo_actual):
    """Qué puede renovar un estudiante antiguo, y de qué periodo viene.

    Antiguo = tuvo al menos una matrícula ACTIVA en un periodo anterior. Se
    toma el último periodo que cursó (no todos), así que quien se saltó un
    semestre puede renovar igual desde el último en el que sí estuvo.

    Devuelve (periodo_anterior, [matrículas]). La lista excluye las promotorías
    en las que ya tiene matrícula viva en el periodo actual, para que renovar
    dos veces no sea posible. Un estudiante nuevo recibe (None, []).
    """
    if periodo_actual is None:
        return None, []

    anteriores = list(
        Matricula.objects.filter(estudiante=perfil, estado="activa")
        .filter(periodo__fecha_inicio__lt=periodo_actual.fecha_inicio)
        .select_related("periodo", "promotoria", "promotoria__area")
        .order_by("-periodo__fecha_inicio")
    )
    if not anteriores:
        return None, []

    periodo_anterior = anteriores[0].periodo
    del_ultimo_periodo = [m for m in anteriores if m.periodo_id == periodo_anterior.id]

    ya_tiene = set(
        Matricula.objects.filter(estudiante=perfil, periodo=periodo_actual)
        .exclude(estado="retirada").values_list("promotoria_id", flat=True)
    )
    return periodo_anterior, [m for m in del_ultimo_periodo if m.promotoria_id not in ya_tiene]


def historial_por_periodo(perfil):
    """Todas las matrículas de un estudiante, agrupadas por periodo, del más reciente al más antiguo.

    No hace falta ningún modelo de historial: cada `Matricula` ya guarda su
    periodo y nunca se borra al terminar (el estudiante que se va queda como
    "retirada", ver `retirar_matricula`), así que la trayectoria completa ya
    está en la tabla y esto solo la ordena.

    Incluye a propósito las retiradas y las rechazadas —que también quedan
    "retirada"—: un historial que solo enseña lo que prosperó no sirve para
    entender de dónde viene el estudiante, que es justo para lo que se
    consulta.

    Devuelve [{periodo, matriculas, en_curso}]. `en_curso` marca el periodo
    activo para que la plantilla separe lo vigente del pasado sin volver a
    consultarlo, y para que solo ahí se ofrezcan acciones: un periodo
    terminado es historial cerrado.
    """
    periodo_actual = Periodo.en_curso()
    matriculas = (
        Matricula.objects.filter(estudiante=perfil)
        .select_related(
            "periodo", "promotoria", "promotoria__area", "promotoria__profesor", "grupo",
        )
        # El id del periodo desempata para que las filas de un mismo periodo
        # queden contiguas aunque dos periodos compartan fecha de inicio; si se
        # intercalaran, el agrupado de abajo abriría dos bloques para uno solo.
        .order_by(
            "-periodo__fecha_inicio", "-periodo_id",
            "promotoria__area__nombre", "promotoria__nombre",
        )
    )

    bloques = []
    for matricula in matriculas:
        if not bloques or bloques[-1]["periodo"].id != matricula.periodo_id:
            bloques.append({
                "periodo": matricula.periodo,
                "matriculas": [],
                "en_curso": periodo_actual is not None and matricula.periodo_id == periodo_actual.id,
            })
        bloques[-1]["matriculas"].append(matricula)
    return bloques


def resumen_trayectoria(perfil):
    """Cifras de cabecera del historial: cuánto lleva el estudiante y cuánto ha cursado.

    Solo cuentan las matrículas ACTIVAS, es decir las que un profesor confirmó:
    eso es lo que el estudiante realmente cursó. Las pendientes y las retiradas
    siguen apareciendo en el detalle del historial, pero no inflan estas cifras
    —si contaran, quien pidió cinco promotorías y no entró a ninguna se leería
    como el estudiante más veterano de la casa.
    """
    activas = Matricula.objects.filter(estudiante=perfil, estado="activa")
    return {
        "periodos": activas.values("periodo_id").distinct().count(),
        "promotorias": activas.values("promotoria_id").distinct().count(),
        "desde": (
            Periodo.objects.filter(
                matriculas__estudiante=perfil, matriculas__estado="activa",
            ).order_by("fecha_inicio").first()
        ),
    }
