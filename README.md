# Sistema de Matrículas

Plataforma de autoservicio para inscripción, confirmación y asignación de grupos en una escuela de artes (casas de cultura) — reemplaza el proceso manual en papel/hojas de cálculo por un flujo digital organizado por roles.

## Qué resuelve

El público en general (incluyendo menores de edad) se inscribe desde su casa o celular en una **promotoría** artística (música, danza, teatro, pintura, etc.), sin elegir horario. El profesor de esa promotoría confirma la matrícula y luego crea **grupos** según su propia disponibilidad, repartiendo ahí a los ya matriculados.

El personal de la institución (profesores, directores, administradores) gestiona el catálogo académico (departamentos, promotorías, grupos, periodos, cupos), confirma o rechaza matrículas, y administra usuarios — todo desde una interfaz web, sin depender de planillas sueltas.

## Características principales

- **Roles**: estudiante, profesor, director y administrador, cada uno con su propia vista y permisos.
- **Autorregistro público**: tanto para profesores nuevos (queda pendiente de que se le asigne rol) como para estudiantes (queda inscrito de una vez, pendiente de confirmación).
- **Renovación de matrícula**: un estudiante antiguo no vuelve a inscribirse desde cero — renueva marcando en qué promotorías sigue y respondiendo una encuesta de satisfacción corta.
- **Historial por estudiante**: la trayectoria completa de cada quien —en qué promotorías estuvo, en qué periodo, con qué grupo y en qué estado—, incluidas las matrículas retiradas. No hay tabla de historial aparte: se reconstruye de las matrículas mismas, que conservan su periodo y no se borran al terminar. El estudiante ve la suya agrupada por periodo; el personal la consulta desde el panel, y el profesor ve la trayectoria completa aunque sea de otras áreas, porque es lo que permite ubicar en un nivel a quien llega de otra disciplina.
- **Asistencia por clase**: el profesor oprime "Iniciar clase" en su grupo cuando la clase empieza —queda registrada la hora real— y marca ahí mismo quién asistió, quién faltó y quién faltó con excusa. Solo quien dicta la promotoría la escribe —incluido un director que además enseña—; el resto ve el registro sin poder modificarlo. Cada grupo tiene su propia pantalla de clases dictadas, con el conteo de cada sesión y el porcentaje de asistencia de cada estudiante.
- **La clase la verifican los estudiantes**: como quien la registra es parte interesada, la clase queda sin verificar hasta que la confirmen tres estudiantes desde su sesión (uno solo si el grupo tiene uno o dos), y hay 48 horas de plazo para hacerlo. El profesor ve cuántas confirmaciones lleva, no quiénes la dieron.
- **Panel de asistencia en cada ficha**: cifras de cabecera y un calendario del periodo, en la ficha de la persona. Al estudiante le dice cuánto asistió, faltó o justificó y con qué racha; a quien dicta, cuántas clases dio y cuántas se le verificaron. Son dos preguntas distintas y por eso se ven distintas: la celda del estudiante codifica un **estado** y la de quien dicta una **magnitud**.
- **Documentos configurables por institución**: qué papeles hacen falta para dar una matrícula por válida cambia de una entidad a otra, así que la lista se edita en Gestión → Institución. El estudiante los sube desde Mi perfil, de a uno según los consiga, y a quien le falte alguno obligatorio le sale una etiqueta en el panel del profesor y en su ficha. Un documento se **desactiva**, nunca se borra: los archivos entregados cuelgan de él.
- **Reparto de estudiantes en bloque**: al principio de periodo casi todos van al mismo horario, así que se marcan varios y se asignan de un clic. El lote es todo o nada — si no caben, no entra ninguno y se dice cuántos cupos quedaban.
- **Catálogo jerárquico navegable**: Departamentos → Promotorías → Grupos → Estudiantes inscritos, con migas de pan y creación en contexto.
- **Cupos por periodo**: cada promotoría tiene un cupo configurable por periodo (no fijo), garantizado a nivel de base de datos (no solo de la aplicación) para evitar condiciones de carrera.
- **Privacidad diferenciada por rol**: quién ve nombre/foto, quién ve edad/teléfono/acudiente, quién ve la encuesta demográfica y quién ve la copia del documento de identidad están definidos de forma estricta (pensado para cumplir la Ley 1581 de Colombia / habeas data).
- **Marca y reglas configurables**: nombre, logo, color de acento, cuántas promotorías puede cursar alguien por periodo y si los estudiantes pueden matricularse por su cuenta se editan desde la propia interfaz (Gestión → Institución), no están quemados en el código — pensado para poder reinstalar el sistema en otra institución sin tocar plantillas.
- **Las acciones no recargan la página**: confirmar una matrícula, aprobar una cancelación o asignar un grupo repintan solo el contenido y dejan al usuario donde estaba, con el scroll y los desplegables intactos. Las vistas siguen siendo Django de toda la vida —guardan, encolan su mensaje y redirigen—; sin JavaScript todo funciona igual.

Para el detalle completo de reglas de negocio y decisiones de producto, ver [`PRODUCT.md`](PRODUCT.md). Para el sistema de diseño visual, ver [`DESIGN.md`](DESIGN.md).

## Stack

- [Django](https://www.djangoproject.com/) 5.x
- PostgreSQL
- [django-environ](https://github.com/joke2k/django-environ) (configuración vía `.env`)
- Pillow (procesamiento de fotos de perfil)

## Puesta en marcha local

### Requisitos previos

- Python 3.10 o superior
- PostgreSQL corriendo localmente (o accesible por red)

### 1. Clonar e instalar dependencias

```bash
git clone https://github.com/Drendon2/sistema-matriculas.git
cd sistema-matriculas
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configurar variables de entorno

Copia `.env.example` como `.env` y completa los valores reales (clave secreta de Django, credenciales de tu base de datos PostgreSQL):

```bash
copy .env.example .env
```

### 3. Crear la base de datos y aplicar migraciones

Crea la base de datos en PostgreSQL con el nombre que pusiste en `DATABASE_URL` dentro de `.env`, y luego:

```bash
python manage.py migrate
```

### 4. Crear una cuenta de administrador

```bash
python manage.py createsuperuser
```

### 5. Levantar el servidor

```bash
python manage.py runserver
```

Abre `http://127.0.0.1:8000/` en el navegador. Inicia sesión con la cuenta creada en el paso 4 y ve a **Gestión** para empezar a cargar departamentos, promotorías y periodos.

### Adaptarlo a otra institución

Casi todo lo que cambia de una entidad a otra se configura desde la interfaz, en **Gestión → Institución** (solo administrador):

| Ajuste | Qué hace |
|---|---|
| Nombre, logo, color de acento | La marca. De un solo color se derivan el tono de hover y el de fondo. |
| Promotorías por estudiante y periodo | Cuántas puede cursar alguien a la vez. |
| Los estudiantes ven el catálogo | Apágalo si la institución matricula en ventanilla. |
| Documentos para matricularse | Qué papeles se exigen. Se agregan y se dejan de pedir sin tocar código. |

No hace falta editar plantillas ni migrar el esquema para ninguno de los cuatro.

## Datos de prueba

Para probar el sistema con volumen real hay un sembrador:

```bash
python manage.py simular              # ~100 usuarios de los cuatro roles
python manage.py simular --limpiar    # borra todo lo que sembró
```

No son cien filas aleatorias: siembra a propósito los casos que el sistema tiene que saber manejar —promotoría sin profesor, promotoría sin grupos, matrículas en los cuatro estados, menores con acudiente, encuestas completas / a medias / sin empezar, clases verificadas, una vencida sin verificar y una a medias con el plazo abierto, más historial y deserción del periodo anterior— y al terminar imprime dónde está cada uno y con qué cuenta entrar (la contraseña de todas es `simulacion`).

El sembrador **no configura documentos requeridos** —esa lista es de cada institución y se
arma desde Gestión → Institución—, así que en una base recién sembrada la etiqueta de «faltan
papeles» no aparece hasta que agregues alguno.

Todo queda marcado: las cuentas con el usuario `sim.…` y el catálogo con el sufijo ` (sim)`, así que `--limpiar` lo borra entero sin tocar tus datos. Usa el periodo que ya esté en curso en vez de crear uno, y se niega a correr con `DEBUG=False`.

## Pruebas

```bash
python manage.py test matriculas
```

Son ~260 y corren contra PostgreSQL, así que necesitan la misma base configurada en `.env` (Django crea y destruye una `test_…` aparte). Cubren sobre todo las reglas que no se ven en la pantalla: cupos y sus condiciones de carrera, la matriz de visibilidad por rol, los plazos de confirmación, y qué se puede borrar y qué no.

## Estado del proyecto

En desarrollo activo. Proyecto privado.
