"""Puebla la base con una institución de mentira, para probar el sistema con volumen.

Con dieciséis usuarios no se ve si una pantalla aguanta, si una regla se
sostiene o si una cifra dice lo que uno cree. Este comando arma un escenario
completo —cien personas de los cuatro roles, con sus matrículas, sus clases y
su asistencia— y lo arma **a propósito**: no son cien filas aleatorias, son los
casos que el sistema tiene que saber manejar, cada uno colocado donde se pueda
ir a mirar (el comando imprime al final dónde está cada cual).

Todo lo que crea queda marcado:

- las cuentas, con el usuario `sim.algo`;
- el catálogo (departamentos, promotorías), con el sufijo ` (sim)`.

Por eso `--limpiar` puede borrarlo entero sin tocar nada tuyo, y por eso la
simulación **no altera tu configuración**: usa el periodo que ya esté en curso
en vez de crear uno y activarlo, que rompería el "un solo periodo activo", y se
inventa su propio catálogo en vez de meter gente en tus promotorías reales.

    python manage.py simular              # siembra ~100 usuarios
    python manage.py simular --limpiar    # borra TODO lo sembrado
    python manage.py simular --semilla 7  # otro reparto, igual de reproducible

Es una herramienta de desarrollo: se niega a correr con DEBUG=False salvo que
se insista con --forzar.
"""

import random
from datetime import date, timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from matriculas.models import (
    Acudiente, Area, Asistencia, Clase, ConfirmacionClase, CupoPromotoria,
    DatosEstudiante, EncuestaDemografica, EncuestaSatisfaccion, Grupo,
    Matricula, Perfil, Periodo, Promotoria, limite_promotorias,
)

# Las dos marcas que hacen reversible la simulación. Cambiarlas deja huérfano lo
# ya sembrado: `--limpiar` busca por ellas.
PREFIJO_USUARIO = "sim."
SUFIJO_CATALOGO = " (sim)"

NOMBRES = [
    "Ana", "Santiago", "Valentina", "Mateo", "Isabella", "Samuel", "Sofía",
    "Emiliano", "Camila", "Sebastián", "Mariana", "Nicolás", "Luciana", "Tomás",
    "Salomé", "Andrés", "Antonia", "Juan", "Gabriela", "Felipe", "Manuela",
    "Daniel", "Juliana", "Alejandro", "Paula", "Miguel", "Sara", "David",
    "Laura", "Esteban", "Catalina", "Ricardo", "Verónica", "Óscar", "Natalia",
]
APELLIDOS = [
    "Rendón", "Gómez", "Cardona", "Ospina", "Zapata", "Betancur", "Restrepo",
    "Arango", "Vélez", "Quintero", "Hoyos", "Marín", "Agudelo", "Muñoz",
    "Ramírez", "Pineda", "Loaiza", "Grisales", "Salazar", "Torres", "Bedoya",
]
BARRIOS = [
    "Centro", "La Playa", "San José", "El Carmen", "Vereda La Cristalina",
    "Los Naranjos", "Villa Nueva", "El Progreso", "La Floresta",
]
SALONES = ["Salón 1", "Salón 2", "Salón 3", "Aula múltiple", "Tarima"]
HORARIOS = [
    "Lunes 2:00-4:00 p.m.", "Martes 4:00-6:00 p.m.", "Miércoles 8:00-10:00 a.m.",
    "Jueves 3:00-5:00 p.m.", "Viernes 10:00 a.m.-12:00 m.", "Sábado 9:00-11:00 a.m.",
]


class Command(BaseCommand):
    help = "Siembra (o borra, con --limpiar) una institución de prueba con ~100 usuarios."

    def add_arguments(self, parser):
        parser.add_argument(
            "--estudiantes", type=int, default=88,
            help="Cuántos estudiantes sembrar. El resto hasta ~100 son personal (por defecto: 88).",
        )
        parser.add_argument(
            "--semilla", type=int, default=2026,
            help="Semilla del azar. La misma semilla da exactamente el mismo reparto.",
        )
        parser.add_argument(
            "--limpiar", action="store_true",
            help="Borra todo lo que sembró este comando y no siembra nada nuevo.",
        )
        parser.add_argument(
            "--forzar", action="store_true",
            help="Deja correr aunque DEBUG=False. Es una herramienta de desarrollo: piénsalo dos veces.",
        )

    def handle(self, *args, **opciones):
        if not settings.DEBUG and not opciones["forzar"]:
            raise CommandError(
                "DEBUG=False: esto parece un entorno real y el comando escribe cien usuarios "
                "de mentira en la base. Si de verdad es lo que quieres, repite con --forzar."
            )

        if opciones["limpiar"]:
            self._limpiar()
            return

        self.azar = random.Random(opciones["semilla"])
        self.documento = 1_000_000
        with transaction.atomic():
            self._sembrar(opciones["estudiantes"])

    # -- borrar -------------------------------------------------------------

    @transaction.atomic
    def _limpiar(self):
        """Borra en el orden que exigen las claves protegidas, que no es el obvio.

        Hay un cruce: las matrículas PROTEGEN a las promotorías, pero cuelgan de
        las cuentas; y las promotorías, a su vez, protegen la cuenta de su
        profesor (`Promotoria.profesor` es PROTECT). Así que ni "usuarios
        primero" ni "catálogo primero" funcionan solos — hay que romper el ciclo
        borrando las matrículas por su cuenta, y solo entonces catálogo y
        cuentas. Va en una transacción para que un fallo a mitad no deje la base
        medio limpia.

        El periodo NO se toca en ningún caso: es tuyo, no lo creó la simulación.
        """
        usuarios = User.objects.filter(username__startswith=PREFIJO_USUARIO)
        cuentas = usuarios.count()
        promotorias = Promotoria.objects.filter(nombre__endswith=SUFIJO_CATALOGO)
        areas = Area.objects.filter(nombre__endswith=SUFIJO_CATALOGO)
        cuantas_promotorias, cuantas_areas = promotorias.count(), areas.count()

        Matricula.objects.filter(
            estudiante__usuario__username__startswith=PREFIJO_USUARIO
        ).delete()
        # Los grupos se llevan por cascada las clases, la asistencia y las
        # confirmaciones.
        Grupo.objects.filter(promotoria__nombre__endswith=SUFIJO_CATALOGO).delete()

        try:
            promotorias.delete()
            areas.delete()
        except ProtectedError:
            # Pasa si matriculaste a alguien TUYO en una promotoría de la
            # simulación. Se para en seco y la transacción revierte: esa
            # matrícula es tuya y la decisión de qué hacer con ella también.
            raise CommandError(
                "Hay matrículas que no son de la simulación colgando de su catálogo, así "
                "que borrarlo se llevaría datos tuyos por delante. No se borró nada. "
                "Revisa qué matrículas propias apuntan a las promotorías terminadas en "
                "«(sim)», retíralas, y vuelve a intentarlo."
            )

        usuarios.delete()

        # Los acudientes no cuelgan del perfil (SET_NULL), así que sobreviven a
        # la cascada y hay que barrerlos aparte. Se reconocen por su nombre.
        Acudiente.objects.filter(
            nombre__endswith=SUFIJO_CATALOGO, estudiantes__isnull=True
        ).delete()

        self.stdout.write(self.style.SUCCESS(
            f"Borrado: {cuentas} cuentas, {cuantas_promotorias} promotorías, {cuantas_areas} departamentos."
        ))

    # -- sembrar ------------------------------------------------------------

    def _sembrar(self, cuantos_estudiantes):
        periodo = Periodo.en_curso()
        if periodo is None:
            raise CommandError(
                "No hay un periodo en curso. Márcalo en Gestión → Iniciar / finalizar "
                "matrículas: la simulación usa el tuyo en vez de crear uno, para no "
                "chocar con la regla de un solo periodo activo."
            )
        anterior = (
            Periodo.objects.filter(fecha_inicio__lt=periodo.fecha_inicio)
            .order_by("-fecha_inicio").first()
        )

        personal = self._sembrar_personal()
        promotorias = self._sembrar_catalogo(personal)
        grupos = self._sembrar_grupos(promotorias)
        estudiantes = self._sembrar_estudiantes(cuantos_estudiantes)
        self._sembrar_matriculas(estudiantes, promotorias, grupos, periodo)
        self._sembrar_historia(estudiantes, promotorias, anterior)
        self._sembrar_cupos(promotorias, periodo)
        self._sembrar_clases(grupos, periodo)

        self._resumen(periodo, anterior, personal, promotorias, grupos)

    # -- personal -----------------------------------------------------------

    def _sembrar_personal(self):
        """Los roles de arriba, cada uno con un caso que probar.

        Incluye a propósito un director que ADEMÁS dicta —el caso que obligó a
        que la asistencia mire el vínculo y no el rol—, un profesor sin ninguna
        promotoría asignada y dos cuentas sin rol todavía, que es como queda
        cualquiera que se autorregistre.
        """
        personal = {}
        personal["admin"] = self._crear_perfil(
            "admin", "Álvaro Mesa", "administrador", self._nacimiento(45),
        )
        personal["director"] = self._crear_perfil(
            "director", "Beatriz Londoño", "director", self._nacimiento(50),
        )
        personal["director_dicta"] = self._crear_perfil(
            "director.dicta", "Clara Jaramillo", "director", self._nacimiento(41),
        )
        personal["profesores"] = [
            self._crear_perfil(f"profe{i}", self._nombre(), "profesor", self._nacimiento(30 + i))
            for i in range(1, 6)
        ]
        # Este se queda sin promotoría: el panel de un profesor recién llegado.
        personal["profesor_sin_promotoria"] = personal["profesores"][-1]
        # Autorregistro pendiente de que le asignen rol.
        personal["sin_rol"] = [
            self._crear_perfil(f"pendiente{i}", self._nombre(), "", self._nacimiento(28))
            for i in range(1, 3)
        ]
        return personal

    # -- catálogo -----------------------------------------------------------

    def _sembrar_catalogo(self, personal):
        """Departamentos y promotorías propios, para no tocar los tuyos.

        La última promotoría queda SIN profesor asignado a propósito: es el caso
        en el que nadie puede registrar clases, y conviene poder verlo.
        """
        areas = [
            Area.objects.create(nombre=nombre + SUFIJO_CATALOGO)
            for nombre in ("Música", "Danza", "Teatro")
        ]
        profes = personal["profesores"]
        reparto = [
            ("Violín", areas[0], profes[0]),
            ("Guitarra", areas[0], profes[1]),
            ("Coro", areas[0], personal["director_dicta"]),  # el director que enseña
            ("Danza folclórica", areas[1], profes[2]),
            ("Ballet", areas[1], profes[2]),                 # dos promotorías, un profesor
            ("Teatro juvenil", areas[2], profes[3]),
            ("Títeres", areas[2], None),                     # sin profesor asignado
        ]
        return [
            Promotoria.objects.create(
                nombre=nombre + SUFIJO_CATALOGO, area=area, profesor=profesor,
            )
            for nombre, area, profesor in reparto
        ]

    def _sembrar_grupos(self, promotorias):
        """Uno o dos grupos por promotoría (el esquema admite un nivel por promotoría).

        La de Títeres se queda sin grupos: promotoría con matriculados y nada
        donde repartirlos, que es como empieza cualquiera.
        """
        grupos = {}
        for promotoria in promotorias[:-1]:
            niveles = ["basico"] if self.azar.random() < 0.4 else ["basico", "intermedio"]
            grupos[promotoria.id] = [
                Grupo.objects.create(
                    promotoria=promotoria, nivel=nivel,
                    horario=self.azar.choice(HORARIOS), salon=self.azar.choice(SALONES),
                    cupo_maximo=self.azar.choice([8, 10, 12, 15]),
                )
                for nivel in niveles
            ]
        return grupos

    # -- estudiantes --------------------------------------------------------

    def _sembrar_estudiantes(self, cuantos):
        """Estudiantes con la mezcla de casos que el sistema tiene que aguantar.

        Un tercio son menores de edad y llevan acudiente (sin él, `DatosEstudiante`
        no valida). La encuesta demográfica queda en tres estados —completa, a
        medias y sin empezar— porque las tres existen en la base real: la
        migración 0016 vació campos de las encuestas viejas, y las cifras tienen
        que saber contarlo.
        """
        estudiantes = []
        for i in range(1, cuantos + 1):
            menor = i % 3 == 0
            edad = self.azar.randint(7, 16) if menor else self.azar.randint(18, 67)
            perfil = self._crear_perfil(
                f"est{i:03d}", self._nombre(), "estudiante", self._nacimiento(edad),
            )

            acudiente = None
            if menor:
                acudiente = Acudiente.objects.create(
                    nombre=f"{self._nombre()}{SUFIJO_CATALOGO}",
                    telefono=self._telefono(),
                    autoriza_tratamiento_datos=True,
                    fecha_autorizacion=timezone.now(),
                )
            self.documento += 1
            DatosEstudiante.objects.create(
                perfil=perfil, documento_identidad=str(self.documento), acudiente=acudiente,
            )

            suerte = self.azar.random()
            if suerte < 0.7:
                self._encuesta(perfil, completa=True)
            elif suerte < 0.85:
                self._encuesta(perfil, completa=False)
            # el resto se queda sin encuesta: aparece como pendiente

            estudiantes.append(perfil)
        return estudiantes

    def _encuesta(self, perfil, completa):
        EncuestaDemografica.objects.create(
            perfil=perfil,
            genero=self.azar.choice([c for c, _ in EncuestaDemografica.GENEROS]),
            barrio=self.azar.choice(BARRIOS),
            estrato=self.azar.choice([1, 2, 3, 4, 5, 6]),
            # A medias = con los campos que la migración 0016 dejó vacíos.
            nivel_educativo=(
                self.azar.choice([c for c, _ in EncuestaDemografica.NIVELES_EDUCATIVOS])
                if completa else ""
            ),
            ocupacion=(
                self.azar.choice([c for c, _ in EncuestaDemografica.OCUPACIONES])
                if completa else ""
            ),
            zona=self.azar.choice(["urbana", "rural", "centro_poblado", ""]),
            afiliacion_salud=self.azar.choice(["contributivo", "subsidiado", ""]),
            grupo_etnico=self.azar.choice(["ninguno", "indigena", "afro", ""]),
            discapacidad=self.azar.choice(["ninguna", "ninguna", "visual", ""]),
            victima_conflicto_armado=self.azar.choice(["no", "si", "ns", ""]),
            autoriza_tratamiento_datos=True,
            fecha_autorizacion=timezone.now(),
        )

    # -- matrículas del periodo en curso ------------------------------------

    def _sembrar_matriculas(self, estudiantes, promotorias, grupos, periodo):
        """Los cuatro estados de una matrícula, y con/sin grupo asignado.

        Se respeta el límite de promotorías por periodo que tengas configurado
        (`limite_promotorias`), y cada matrícula pasa por `full_clean` igual que
        si la hubiera creado una persona: la simulación no se salta las reglas
        que después vas a probar.
        """
        limite = limite_promotorias()
        cuenta = 0

        for estudiante in estudiantes:
            cuantas = self.azar.choice([1, 1, 1, 2, min(3, limite)])
            elegidas = self.azar.sample(promotorias, min(cuantas, limite, len(promotorias)))
            for promotoria in elegidas:
                cuenta += 1
                # El estado se reparte por MATRÍCULA y no por estudiante: si no,
                # quien tuviera tres las tendría las tres retiradas, y el caso
                # normal —una activa y otra pendiente a la vez— no aparecería.
                estado = self._estado_de_matricula(cuenta)
                matricula = Matricula(
                    estudiante=estudiante, promotoria=promotoria,
                    periodo=periodo, estado=estado,
                )
                matricula.full_clean()
                matricula.save()

                # Solo se reparte en grupo lo que está inscrito, igual que en la
                # aplicación: una pendiente no tiene grupo todavía.
                candidatos = grupos.get(promotoria.id) or []
                if candidatos and estado in Matricula.ESTADOS_INSCRITO and self.azar.random() < 0.82:
                    grupo = self.azar.choice(candidatos)
                    if grupo.cupos_disponibles(periodo) > 0:
                        matricula.grupo = grupo
                        matricula.save(update_fields=["grupo"])

    def _estado_de_matricula(self, indice):
        """Reparto fijo por posición, no al azar: garantiza que los cuatro estados
        existan aunque la semilla cambie."""
        if indice % 11 == 0:
            return "pendiente"
        if indice % 17 == 0:
            return Matricula.ESTADO_CANCELACION
        if indice % 13 == 0:
            return "retirada"
        return "activa"

    # -- historia: periodo anterior -----------------------------------------

    def _sembrar_historia(self, estudiantes, promotorias, anterior):
        """Matrículas del periodo pasado, que es lo que hace existir tres cosas:

        el historial del estudiante, la renovación (que busca matrículas
        ACTIVAS de un periodo previo) y las cifras de deserción de Estadísticas,
        que comparan quién siguió y quién no volvió.
        """
        if anterior is None:
            return

        for estudiante in estudiantes[: len(estudiantes) // 3]:
            promotoria = self.azar.choice(promotorias)
            estado = "activa" if self.azar.random() < 0.75 else "retirada"
            matricula = Matricula(
                estudiante=estudiante, promotoria=promotoria,
                periodo=anterior, estado=estado,
            )
            matricula.full_clean()
            matricula.save()
            # La fecha es auto_now_add: se corrige a mano para que caiga dentro
            # del periodo que dice ser.
            Matricula.objects.filter(pk=matricula.pk).update(
                fecha=timezone.now() - timedelta(days=self.azar.randint(180, 320))
            )

            if estado == "activa" and self.azar.random() < 0.5:
                EncuestaSatisfaccion.objects.create(
                    perfil=estudiante, periodo=anterior,
                    satisfaccion_general=self.azar.randint(3, 5),
                    calificacion_profesor=self.azar.randint(3, 5),
                    horario_funciono=self.azar.random() < 0.8,
                    recomendaria=self.azar.random() < 0.9,
                    comentario=self.azar.choice(["", "", "Muy buena experiencia."]),
                )

    # -- cupos ---------------------------------------------------------------

    def _sembrar_cupos(self, promotorias, periodo):
        """Los cupos van DESPUÉS de matricular, y no es un detalle de orden.

        El tope lo impone un trigger de PostgreSQL sobre las altas: fijarlo
        antes habría hecho fallar la siembra al llegar al límite. Puestos
        después, dejan justo el escenario interesante —una promotoría llena y
        otra por llenarse—, que es legítimo en la aplicación: bajar el cupo no
        retira a nadie, solo cierra la puerta.
        """
        for indice, promotoria in enumerate(promotorias):
            ocupados = promotoria.ocupados_en(periodo)
            if indice % 3 == 0:
                continue  # sin tope: es el estado por defecto
            holgura = 0 if indice % 3 == 1 else self.azar.randint(2, 6)
            CupoPromotoria.objects.create(
                promotoria=promotoria, periodo=periodo, cupo_maximo=ocupados + holgura,
            )

    # -- clases y asistencia -------------------------------------------------

    def _sembrar_clases(self, grupos, periodo):
        """Un escenario de verificación distinto por grupo, no ruido repartido.

        Los cinco casos que el sistema distingue quedan sembrados a propósito, en
        este orden de grupos:

        0. al día: varias clases, todas verificadas;
        1. con faltas y excusas, verificadas;
        2. vencida SIN verificar (el plazo de 48 h se acabó con confirmaciones
           de menos);
        3. recién dictada, confirmaciones a medias y el plazo todavía abierto;
        4. sin ninguna clase registrada.

        Las confirmaciones se escriben directo, saltándose la ventana de 48
        horas que aplica la vista: es la única forma de fabricar una clase
        antigua ya verificada, que es justo lo que hay que poder mirar.
        """
        planos = [g for lista in grupos.values() for g in lista]
        if not planos:
            return

        escenarios = ["al_dia", "con_faltas", "vencida", "abierta", "sin_clases"]
        for indice, grupo in enumerate(planos):
            escenario = escenarios[indice % len(escenarios)]
            if escenario == "sin_clases":
                continue

            inscritos = list(
                Matricula.objects.filter(
                    grupo=grupo, periodo=periodo, estado__in=Matricula.ESTADOS_INSCRITO,
                )
            )
            if not inscritos:
                continue

            if escenario == "abierta":
                sesiones = [2]                      # horas atrás: dentro del plazo
            elif escenario == "vencida":
                sesiones = [24 * 5]
            else:
                sesiones = [24 * d for d in (21, 14, 7, 2)]

            for horas in sesiones:
                self._una_clase(grupo, periodo, inscritos, horas, escenario)

    def _una_clase(self, grupo, periodo, inscritos, horas_atras, escenario):
        clase = Clase.abrir(grupo, periodo, grupo.promotoria.profesor)
        cuando = timezone.now() - timedelta(hours=horas_atras)
        Clase.objects.filter(pk=clase.pk).update(fecha_hora=cuando)
        clase.refresh_from_db()

        for matricula in inscritos:
            if escenario == "con_faltas":
                estado = self.azar.choices(
                    ["asistio", "falto", "excusa"], weights=[70, 20, 10]
                )[0]
            else:
                estado = self.azar.choices(["asistio", "falto"], weights=[92, 8])[0]
            # En la clase recién dictada se deja gente sin marcar: es válido y
            # es el estado en el que de verdad se encuentra una lista a medias.
            if escenario == "abierta" and self.azar.random() < 0.3:
                continue
            Asistencia.objects.create(clase=clase, matricula=matricula, estado=estado)

        # Una menos de las que pide deja los dos escenarios incompletos; lo que
        # los separa es la fecha, no el conteo: la vieja ya no puede cambiar y la
        # de hace dos horas sí.
        if escenario in ("vencida", "abierta"):
            confirman = max(0, clase.confirmaciones_requeridas - 1)
        else:
            confirman = clase.confirmaciones_requeridas

        for matricula in inscritos[:confirman]:
            ConfirmacionClase.objects.create(clase=clase, matricula=matricula)

    # -- utilidades ----------------------------------------------------------

    def _crear_perfil(self, sufijo, nombre, rol, nacimiento):
        usuario = User.objects.create_user(
            username=f"{PREFIJO_USUARIO}{sufijo}", password="simulacion",
        )
        return Perfil.objects.create(
            usuario=usuario, rol=rol, nombre_completo=nombre,
            fecha_nacimiento=nacimiento, telefono=self._telefono(),
        )

    def _nombre(self):
        return f"{self.azar.choice(NOMBRES)} {self.azar.choice(APELLIDOS)}"

    def _telefono(self):
        return f"3{self.azar.randint(100000000, 199999999)}"

    def _nacimiento(self, edad):
        """Una fecha que da AL MENOS esa edad cumplida.

        Va por días y con 366 por año, no restando años al calendario: si el
        cumpleaños todavía no ha pasado este año, `hoy.year - 18` produce a
        alguien de diecisiete, y entonces `DatosEstudiante` exige acudiente
        justo donde la simulación creía estar sembrando a un adulto.
        """
        return date.today() - timedelta(days=366 * edad + self.azar.randint(0, 300))

    # -- resumen -------------------------------------------------------------

    def _resumen(self, periodo, anterior, personal, promotorias, grupos):
        escribir = self.stdout.write
        cuentas = User.objects.filter(username__startswith=PREFIJO_USUARIO).count()
        matriculas = Matricula.objects.filter(
            estudiante__usuario__username__startswith=PREFIJO_USUARIO
        )
        clases = Clase.objects.filter(grupo__promotoria__nombre__endswith=SUFIJO_CATALOGO)
        verificadas = sum(1 for c in clases if c.esta_confirmada())

        escribir(self.style.SUCCESS(f"\nSimulación lista: {cuentas} cuentas nuevas.\n"))
        escribir(f"  Periodo en curso ....... {periodo}")
        escribir(f"  Periodo anterior ....... {anterior or 'ninguno (sin historial que sembrar)'}")
        escribir(f"  Promotorías ............ {len(promotorias)}")
        escribir(f"  Grupos ................. {sum(len(g) for g in grupos.values())}")
        escribir(f"  Matrículas ............. {matriculas.count()}")
        for estado, etiqueta in Matricula.ESTADOS:
            escribir(f"      {etiqueta:<28} {matriculas.filter(estado=estado).count()}")
        escribir(f"  Clases dictadas ........ {clases.count()} ({verificadas} verificadas)")

        escribir(self.style.MIGRATE_HEADING("\nEntra con cualquiera de estas (contraseña: simulacion):"))
        escribir(f"  administrador .......... {PREFIJO_USUARIO}admin")
        escribir(f"  director ............... {PREFIJO_USUARIO}director")
        escribir(f"  director que DICTA ..... {PREFIJO_USUARIO}director.dicta  (mira Coro{SUFIJO_CATALOGO})")
        escribir(f"  profesor ............... {PREFIJO_USUARIO}profe1")
        escribir(f"  profesor sin promotoría  {PREFIJO_USUARIO}profe5")
        escribir(f"  cuenta sin rol ......... {PREFIJO_USUARIO}pendiente1")
        escribir(f"  estudiantes ............ {PREFIJO_USUARIO}est001 … {PREFIJO_USUARIO}est0NN")

        escribir(self.style.MIGRATE_HEADING("\nQué hay puesto para mirar:"))
        escribir("  · una promotoría sin profesor (Títeres): nadie puede registrarle clases")
        escribir("  · una promotoría sin grupos: matriculados sin dónde repartirlos")
        escribir("  · promotorías llenas, con holgura y sin tope de cupo")
        escribir("  · matrículas en los cuatro estados, con y sin grupo asignado")
        escribir("  · menores con acudiente; encuestas completas, a medias y sin empezar")
        escribir("  · clases verificadas, una vencida SIN verificar y una abierta a medias")
        escribir("  · historial y renovables del periodo anterior, con deserción para Estadísticas")
        escribir(self.style.WARNING(
            f"\nPara deshacerlo todo: python manage.py simular --limpiar\n"
        ))
