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
- **Catálogo jerárquico navegable**: Departamentos → Promotorías → Grupos → Estudiantes inscritos, con migas de pan y creación en contexto.
- **Cupos por periodo**: cada promotoría tiene un cupo configurable por periodo (no fijo), garantizado a nivel de base de datos (no solo de la aplicación) para evitar condiciones de carrera.
- **Privacidad diferenciada por rol**: quién ve nombre/foto, quién ve edad/teléfono/acudiente, quién ve la encuesta demográfica y quién ve la copia del documento de identidad están definidos de forma estricta (pensado para cumplir la Ley 1581 de Colombia / habeas data).
- **Marca configurable**: nombre, logo y color de acento de la institución se editan desde la propia interfaz (Gestión → Institución), no están quemados en el código — pensado para poder reinstalar el sistema en otra institución sin tocar plantillas.

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

## Estado del proyecto

En desarrollo activo. Proyecto privado.
