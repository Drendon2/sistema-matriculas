---
name: Casa de la Cultura — Matrículas
description: La cartelera del estudio — sistema de inscripción a promotorías artísticas de una entidad cultural pública, mostrado como el tablón de anuncios real de un estudio comunitario.
colors:
  bg:
    value: "#f2f5f3"
  surface:
    value: "#ffffff"
  surface-alt:
    value: "#eaf1ec"
  border:
    value: "#dce4df"
  border-strong:
    value: "#c3cfc7"
  ink:
    value: "#182420"
  ink-soft:
    value: "#55645c"
  ink-faint:
    value: "#56655d"
  accent:
    value: "#0a7a59"
  accent-dark:
    value: "#065a41"
  accent-soft:
    value: "#dbf2e7"
  activa:
    value: "#2458d6"
  activa-bg:
    value: "#e3ebfc"
  danger:
    value: "#b22e22"
  danger-bg:
    value: "#fbe4e1"
  tag-0-amber:
    value: "#8f5e10"
  tag-1-violeta:
    value: "#7c4fce"
  tag-2-rosa:
    value: "#c4447b"
  tag-3-verdeazulado:
    value: "#12676a"
  tag-4-indigo:
    value: "#5b57c9"
  tag-5-naranja:
    value: "#c1571f"
  tag-6-magenta:
    value: "#a83cae"
  tag-7-ocre:
    value: "#766a19"
  chart-1-azul:
    value: "#2a78d6"
  chart-2-naranja:
    value: "#eb6834"
  chart-3-aqua:
    value: "#1baf7a"
  chart-4-violeta:
    value: "#4a3aa7"
typography:
  headline:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
    fontSize: "1.75rem"
    fontWeight: 800
    lineHeight: 1.25
    letterSpacing: "-0.02em"
  title:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
    fontSize: "1.2rem"
    fontWeight: 700
    lineHeight: 1.3
    letterSpacing: "normal"
  label:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
    fontSize: "0.78rem"
    fontWeight: 700
    lineHeight: 1.3
    letterSpacing: "0.05em"
  chrome-mono:
    fontFamily: "ui-monospace, 'SF Mono', 'Cascadia Code', 'Segoe UI Mono', Consolas, 'Liberation Mono', monospace"
    fontSize: "0.7rem"
    fontWeight: 700
    lineHeight: 1.3
    letterSpacing: "0.045em"
  body:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "normal"
rounded:
  sm: "8px"
  md: "12px"
  lg: "18px"
  circle: "50%"
spacing:
  xs: "0.4rem"
  sm: "0.65rem"
  md: "1.1rem"
  lg: "1.75rem"
  xl: "2rem"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.surface}"
    rounded: "{rounded.sm}"
    padding: "0.6rem 1.15rem"
  button-primary-hover:
    backgroundColor: "{colors.accent-dark}"
  button-destructive:
    backgroundColor: "transparent"
    textColor: "{colors.ink-soft}"
    rounded: "{rounded.sm}"
    padding: "0.6rem 1.15rem"
  card:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.md}"
    padding: "1.6rem 1.85rem"
  carne:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.md}"
    padding: "0.9rem 1.15rem"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "0.6rem 0.7rem"
---

# Design System: Casa de la Cultura — Matrículas

## Overview

**Creative North Star: "La Cartelera del Estudio"**

Este sistema es la cartelera de anuncios real de un estudio comunitario de artes — el tablón donde se pega el horario de clases, quién ya confirmó cupo y quién todavía espera — no una carpeta de archivo ni un portal gubernamental frío. El fondo es blanco de pizarra, la tinta es un carbón fresco, y un único verde esmeralda hace todo el trabajo de marca y acción. Cada Área artística (Música, Danza, Teatro, Pintura...) recibe su propio color de marcador — como un rotulador de color distinto por disciplina — y el estado de una matrícula se lee por FORMA de marcador (pin sólido con punto / contorno punteado / tachado), nunca solo por color.

Es un mundo moderno pero deliberadamente legible: tipografía de sistema en pesos confiados, con una monoespaciada reservada a IDs, cifras y estados de tabla. Las tarjetas SÍ flotan esta vez — a diferencia del mundo anterior de este mismo proyecto ("El Carné y la Carpeta de Matrícula", que rechazaba toda sombra) — porque en esta metáfora las fichas están literalmente pineadas sobre la pared, y una ficha pineada proyecta sombra. Rechaza tres extremos por igual: el portal gubernamental frío de azul corporativo, el dashboard SaaS genérico morado-degradado, y el archivo de carpeta manila que este mismo producto usaba antes.

**Key Characteristics:**
- Fondo blanco-pizarra; un único verde esmeralda como acento de marca/acción — nunca decorativo, nunca reutilizado para estado de datos.
- Colores de etiqueta por Área (8 tonos rotando por id) — el marcador de color que identifica de un vistazo a qué disciplina pertenece una promotoría.
- El estado de una matrícula se lee por FORMA (pin sólido con punto / contorno punteado / tachado), no solo por color — accesible sin depender del matiz.
- Sombra real y con intención: las tarjetas son fichas pineadas en una pared, no hojas planas de carpeta.
- Radios de esquina suaves (8–18px), como una ficha o nota de verdad, no esquinas duras de spec-sheet ni el recorte de pestaña de carpeta del mundo anterior.

## Colors

Paleta de cartelera de estudio: blanco-pizarra y tinta carbón, con un único verde esmeralda de marca/acción, un azul reservado exclusivamente al estado "activa", rojo para "retirada"/error, y ocho colores de etiqueta para Área.

### Primary
- **Accent / Esmeralda** (`#0a7a59`): color de acción y marca — botones primarios, enlaces, borde de foco, mensajes de éxito. Es el color que dice "esto se puede hacer". Nunca se usa para el estado "activa" de una matrícula.
- **Accent Dark** (`#065a41`): estado hover/activo del acento.
- **Accent Soft** (`#dbf2e7`): anillo de foco, fondo de mensajes de éxito, fondo de campo condicional activo.

### Neutral
- **Blanco-pizarra / bg** (`#f2f5f3`): fondo de página en toda la aplicación.
- **Surface** (`#ffffff`): fondo de tarjetas, fichas, tablas, campos, la tarjeta pública flotante — blanco limpio, nunca cream.
- **Surface Alt** (`#eaf1ec`): superficie secundaria — cabecera de tabla, fondo de campo de archivo, fila de tabla al pasar el cursor.
- **Border** (`#dce4df`) / **Border Strong** (`#c3cfc7`): bordes por defecto y separadores.
- **Ink** (`#182420`): texto principal. Carbón frío, nunca negro puro ni el marrón-tinta del mundo anterior.
- **Ink Soft** (`#55645c`): texto secundario.
- **Ink Faint** (`#56655d`): texto terciario — estados vacíos, separadores de migas. Verificado en ≥4.5:1 sobre `bg` y sobre `surface`, las dos superficies donde aparece.

### Semantic (estado de matrícula)
- **Activa** (`#2458d6` sobre `#e3ebfc`): pin sólido con un punto — matrícula confirmada, "ya está pineada". Azul, deliberadamente distinto del verde de marca.
- **Retirada** (`#b22e22` sobre `#fbe4e1`): mismo tratamiento pero con el texto tachado; también el color de mensajes de error.
- **Pendiente**: sin color de marca propio — contorno punteado en tinta suave/borde fuerte, sin relleno. "Todavía no se ha pineado" es la metáfora.

### Área (colores de etiqueta)
Ocho colores rotan por `Area.id` (ver `matriculas/templatetags/matriculas_extras.py::tag_color`), como marcadores de color distintos por disciplina: ámbar, violeta, rosa, verde azulado, índigo, naranja, magenta, ocre. Todos verificados en ≥4.5:1 sobre blanco. Un color de etiqueta identifica una disciplina — nunca comunica una acción ni un estado.

### Gráfica (rampa categórica)
Cuatro tonos exclusivos de las gráficas de sectores, en orden de asignación fijo: **azul** (`#2a78d6`), **naranja** (`#eb6834`), **aqua** (`#1baf7a`) y **violeta** (`#4a3aa7`). No son los colores de Área, y esa separación es deliberada por dos motivos.

El primero es semántico: en la pantalla de Estadísticas los `tag-*` ya significan "Área" en el árbol de departamentos, y reutilizarlos abajo para género o zona haría que el mismo violeta dijera dos cosas distintas en una sola página.

El segundo es de accesibilidad, y es el que cierra la puerta: la rampa de Área **no pasa** la comprobación para una torta. Su verde azulado y su rosa (`#12676a` / `#c4447b`) quedan en ΔE 2.8 bajo daltonismo protán, muy por debajo del umbral de 8 — para bastante gente serían el mismo sector. Los cuatro de arriba están validados comparando **todos los pares entre sí**, no solo los contiguos, porque en una torta cualquier sector se compara con cualquier otro. El aqua queda por debajo de 3:1 contra el fondo, y su compensación obligatoria son las cifras visibles de la leyenda.

El "sin responder" no pertenece a esta rampa: usa el gris de **Border Strong** (`#c3cfc7`) precisamente porque no es una categoría, es la ausencia de respuesta, y debe leerse como tal sin competir con las opciones reales.

### Named Rules
**La Regla del Marcador, no del Matiz.** Ningún estado de matrícula se comunica solo por color: activa es sólida con punto, pendiente es punteada sin relleno, retirada es tachada. Cualquier pantalla nueva que muestre estado reproduce la forma completa.

**La Regla de la Rampa de Gráfica.** Los cuatro tonos de gráfica son exclusivos de visualizaciones y se asignan **en el orden de la lista, por opción, nunca por ranking** — la opción conserva su color aunque caiga a cero, para que filtrar no repinte a las demás. Nunca se mezclan con los `tag-*` de Área ni con el esmeralda de marca. Una gráfica nueva que necesite colores parte de esta rampa; si necesita otros, se validan antes de usarlos, nunca se eligen a ojo.

**La Regla del Esmeralda Único.** El acento verde es la marca y solo la marca — botones, enlaces, foco, éxito. Nunca se usa para "activa" (eso es azul) ni para error (eso es rojo); mezclarlos rompe la distinción entre "esto es la app" y "esto es un dato".

**La Regla de la Etiqueta de Área.** El color de Área es metadata de categoría, nunca una acción ni un estado — vive como un punto pequeño junto al nombre, nunca como fondo de un botón o de un `.estado`.

## Typography

**Body/Display Font:** -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif
**Chrome/Mono Font:** ui-monospace, "SF Mono", "Cascadia Code", "Segoe UI Mono", Consolas, "Liberation Mono", monospace

**Character:** Una sola familia sans de sistema — rápida de cargar, legible en el celular más viejo del público — haciendo la jerarquía por peso y escala, más una monoespaciada reservada a cifras, IDs y estados. Nada de mayúsculas trazadas en botones ni navegación: eso pertenecía al mundo anterior y se sentía "de oficina antigua"; este mundo habla en frase normal, en negrita segura.

### Hierarchy
- **Headline** (800, 1.75rem, tracking -0.02em, sans): título de página (`h2`).
- **Title** (700, 1.2rem, sans): título de sección (`h3`), sin regla divisoria — el espacio hace la separación.
- **Label** (700, 0.78rem, mayúsculas, tracking 0.05em, sans): eyebrows de subsección (`h4`).
- **Chrome/Mono** (600–700, 0.62–0.72rem, mayúsculas, tracking 0.045em, **monoespaciada**): encabezados de tabla, estado de matrícula, cifras de "Mi perfil".
- **Body** (400–700, 0.85–1rem, sans): párrafos, campos de tabla, texto de apoyo.

### Named Rules
**La Regla Mono-Para-Datos.** La monoespaciada aparece únicamente donde hay un dato tabular, un ID, una cifra o un estado — nunca en un título ni en prosa.

**La Regla de la Frase Normal.** Botones y navegación van en frase normal, negrita, sin mayúsculas trazadas — la voz de este mundo es directa, no de sello administrativo.

## Layout

Contenedor único de contenido: `max-width: 960px`, centrado, `padding: 0 1.25rem`. La pantalla pública de autenticación usa una tarjeta centrada sobre viewport completo. Responsive: bajo 640px, `main` reduce sus márgenes, los inputs se fijan en 16px (evita el zoom automático de iOS), los botones ganan padding vertical para el tamaño de toque, y las tablas se vuelven contenedores con scroll horizontal.

### Named Rules
**La Regla de los 16px.** Ningún campo de formulario baja de `1rem` (16px) en ningún breakpoint — el piso de legibilidad para el público de alfabetización digital variable que este producto sirve.

## Elevation & Depth

Sombra real, con intención — una ficha pineada en la pared proyecta sombra; esto es una ruptura deliberada y coherente con el mundo anterior ("El Carné y la Carpeta"), que rechazaba toda sombra porque nada flotaba en un archivador. Aquí todo SÍ flota, porque todo está pineado.

### Shadow Vocabulary
- **Ficha pineada** (`--shadow`: `0 1px 2px rgba(24,36,32,0.05), 0 6px 16px rgba(24,36,32,0.08)`): `.card`, `.form-card`, `.carne`, `table`, `.tarjeta-enlace` en reposo — la sombra por defecto de toda superficie de contenido.
- **Ficha levantada** (`--shadow-lift`: `0 4px 10px rgba(24,36,32,0.10), 0 12px 28px rgba(24,36,32,0.12)`): `.tarjeta-enlace:hover`, la tarjeta pública flotante (`.caja`), la foto grande de "Mi perfil" — el momento en que algo se levanta de la pared.

### Named Rules
**La Regla de la Ficha Pineada.** Toda superficie de contenido usa `--shadow` en reposo como mínimo; nada queda plano contra el fondo, porque en esta metáfora todo está pineado, no guardado en una carpeta.

## Shapes

Radios suaves y consistentes: `8px` en controles (botones, inputs, chips de estado), `12px` en tarjetas/fichas/tablas, `18px` en la foto grande de "Mi perfil" y la tarjeta pública flotante. La esquina suave imita una ficha o nota real — más generosa que el mundo anterior, que reservaba radios grandes solo a la tarjeta pública.

**El pin de esquina** (un punto circular de 10px en el acento, con sombra propia, en la esquina superior izquierda de `.tarjeta-enlace`): la firma geométrica de este mundo — literalmente el push-pin que sostiene la ficha en la pared. Es la única figura de este tipo del sistema.

El estado "activa" (`.estado-activa`) lleva un punto (`::before`) del color del estado antes del texto, como la cabeza de un pin — pendiente y retirada no lo llevan.

**Excepción intencional — barras de dato:** las pistas y rellenos de las barras de estadísticas (`.stat-bar-pista`/`.stat-bar-relleno`, `.dash-split`) usan radio = mitad de su propia altura (`5px` sobre `10px`, `7px` sobre `14px`), no la escala `8/12/18px` de tarjetas y controles. Una barra de dato es una pista delgada con extremos en píldora — su propia categoría de forma, igual que el punto del pin no sigue la escala de radios tampoco.

## Components

### Buttons
- **Shape:** radio pequeño (`8px`).
- **Primary (`.btn`):** fondo esmeralda, texto blanco, frase normal en negrita — directo, sin mayúsculas trazadas.
- **Hover:** esmeralda oscuro. **Active:** escala a 0.97.
- **Secondary (`.btn-secundario`):** transparente, texto esmeralda, borde neutro.
- **Destructive (`.btn-retirar`):** sin relleno rojo — borde punteado en tinta suave con el texto tachado, que se vuelve rojo sólo al pasar el cursor.
- **Text-only (`.btn-texto`):** frase normal, negrita, tinta suave, subrayado.

### Cards / Carné
- **Corner Style:** `12px`.
- **`.card`/`.form-card`:** superficie blanca sobre fondo blanco-pizarra, con `--shadow`.
- **`.carne`:** foto cuadrada de `56px` a la izquierda, nombre en negrita y un renglón de detalle en monoespaciada tenue a la derecha.

### Status Marker (`.estado`) — Signature Component
Tres tratamientos, diferenciados por FORMA: **Activa** = sólido azul con punto; **Pendiente** = contorno punteado neutro; **Retirada** = borde y texto rojo con tachado. Tipografía monoespaciada, mayúsculas, `0.68rem`.

### Area Tag (`.tag-dot`) — Signature Component
Un punto de 8px del color de Área (`tag-0`…`tag-7`, ver `tag_color`), antes del nombre de la Promotoría o del Área — el marcador de color que identifica la disciplina de un vistazo, en las tablas de "Promotorías disponibles", "Panel" y "Gestión → Departamentos".

### Data Bar (`.stat-bar-fila`) — Estadísticas
Fila horizontal etiqueta + pista + relleno + cifra, para cualquier magnitud por categoría (estudiantes por promotoría, grupos por nivel, respuestas de encuesta). El relleno usa `--accent` por defecto (una sola magnitud, sin identidad que distinguir); cuando la categoría YA tiene un color propio en el sistema (Área → `tag_color`), el relleno reutiliza ese mismo color en vez de inventar uno nuevo — nunca un color distinto por barra sin motivo. El árbol Departamento → Promotoría (`.dash-departamento`/`.dash-promotorias`) anida las promotorías bajo su Área en vez de repetir la cifra en dos listas planas separadas. Ver la excepción de radio en Shapes.

**Una tanda de barras de encuesta dibuja siempre a toda la población.** Quien no cae en ninguna opción entra como una fila final de **"Sin responder"**, en el mismo gris de `--border-strong` que el sector gris de la torta y bajo una línea fina, porque no pertenece a la escala de la pregunta. Es la misma regla del todo que ya cumplía la torta, y su ausencia era un fallo real: una pregunta contestada por dos de cinco personas se dibujaba entera y nada avisaba de las otras tres.

Cada departamento es un `<details>` nativo, sin JavaScript, con el renglón como `<summary>`: con 26 promotorías la lista completa obligaba a bajar mucho para comparar dos áreas. **Plegado no esconde el dato, solo el desglose** — el renglón cerrado conserva su barra, su cifra y sus micro-columnas. El departamento que pierde la mitad o más de su gente **arranca abierto**: acortar la página no puede costar esconder justo la fila que hay que mirar.

### Micro-columnas de permanencia (`.perm`) — Estadísticas
Tres columnas verticales de `8px` sobre una línea base, al final de una fila del árbol de departamentos: **sigue**, **deja** y **no volvió**. Es la única gráfica vertical del sistema, y esa orientación es el punto — la fila ya tiene una barra horizontal de magnitud, y una segunda barra horizontal al lado obligaría a leer dos escalas en la misma dirección. Girada 90°, la micro-gráfica se lee como otra cosa y deja de competir.

Sustituye a las tres cifras en monoespaciada que ocupaban media fila: en texto no se alineaban entre renglones, así que la pregunta real —en qué promotoría se está yendo la gente— había que responderla número por número en vez de de un vistazo.

Cada columna se distingue por **forma antes que por color**, igual que el marcador de estado: *sigue* sólida (color de Área en el departamento, tinta suave en la promotoría), *deja* sólida con **trama diagonal**, *no volvió* **hueca** con contorno. La trama no es decorativa y no se quita: la columna roja queda pegada al ámbar o al naranja de un Área, y bajo daltonismo protán ese borde desaparece si la única diferencia es el matiz. El hueco de *no volvió* dice además que mide otra población — la del periodo anterior.

Dos ausencias que se ven distinto porque significan lo contrario: un **0% real** deja una marca de `2px` sobre la base, y **sin referencia** es la ranura completa en punteado. Un dato en cero que no dibujara nada sería indistinguible de un dato que no existe. La leyenda va **una sola vez** por sección, nunca por fila; el porcentaje exacto vive en `title` y la fila entera lleva `aria-label`.

Los remates son planos: la píldora pertenece a la pista horizontal, no a una columna de `8px`.

### Torta (`.torta`) — Estadísticas
Disco de `116px` con su leyenda al lado, para las preguntas donde lo que importa es **qué parte del total** es cada opción y las opciones son pocas (género, zona). Las escalas con orden propio —estrato, nivel educativo— se quedan en barra de dato: una torta las obligaría a comparar ángulos parecidos.

Cada sector es un `<circle>` con el trazo tan grueso como el diámetro y `stroke-dasharray` recortando su arco; el grupo va rotado `-90°` para empezar a las 12. Sin JavaScript ni librerías: la geometría se calcula en la vista.

**El SVG va dentro de `{% localize off %}`, y no es opcional.** La interfaz está en `es-co`, que escribe los decimales con coma, y en SVG la coma no es un decimal sino el separador entre valores: `stroke-dasharray="73,4 188,5"` deja de ser un arco y pasa a ser un patrón de cuatro tramos que rellena casi el disco. La torta salió mal en producción con la aritmética perfectamente correcta y todos sus tests en verde, porque los tests miraban los números y no el marcado. Cualquier gráfica nueva que escriba un número decimal en un atributo SVG hereda esta regla, y se prueba sobre el HTML renderizado. Entre sectores va un hueco de `2px` del color del fondo — **separación, nunca un borde dibujado alrededor**; un sector único no lo lleva, porque solo dejaría una muesca contra sí mismo.

La leyenda no es un pie de foto, es la mitad de la gráfica: lleva el punto de color, la etiqueta, la cifra y el porcentaje. Es lo que permite leerla sin depender del matiz, y la compensación obligatoria del tono que no alcanza 3:1. Lista **todas** las opciones, incluidas las que están en cero —que por definición no dibujan sector— atenuadas en tinta tenue: si desaparecieran, nadie sabría que la opción existe.

**El todo de la torta es el total de encuestas, no la suma de respuestas.** En una pregunta opcional esa distinción lo cambia todo: con una sola respuesta de dieciséis, una torta de solo respondientes afirmaría que el 100% de la gente vive en zona rural. El resto entra como sector gris de "sin responder".

### Barra de filtros (`.filtros`)
Tira de controles sobre una tabla, en tarjeta propia con `--shadow` — etiqueta pequeña en monoespaciada arriba, control debajo, como los rótulos de una carpeta de archivador. Se reparte en varias líneas cuando la pantalla no da, y bajo 640px cada control pasa a ancho completo: media fila es demasiado estrecho para leer el nombre de una promotoría.

El botón de acción **sigue al último control** en vez de irse al extremo derecho: en una sola fila la diferencia no se nota, pero en cuanto la barra se parte en dos líneas un `margin-left: auto` lo deja descolgado al otro lado de un hueco vacío. Los desplegables jerárquicos usan `<optgroup>` (Promotoría agrupada por Área, Grupo por Promotoría), así la jerarquía del catálogo se ve sin recargar la página al elegir el nivel de arriba. "Limpiar" solo aparece cuando hay algún filtro puesto.

### Navigation
- **Barra superior:** riel claro (blanco, borde inferior fino), título en negrita frase normal, enlaces en frase normal con fondo suave al pasar el cursor.
- **Pestañas de sección (`.tarjeta-enlace`):** ficha pineada con el pin de esquina (ver Shapes) — el vocabulario de navegación del hub de Gestión.
- **Migas de pan (`.migas`):** sin cambios estructurales, recoloreadas al nuevo sistema.

### Inputs / Fields
- Borde `1px` en borde-fuerte, fondo blanco, radio `8px`, `font-size: 1rem` (nunca menos, ver Layout).
- Foco: borde esmeralda + anillo de `3px` en esmeralda-tenue.
- Archivo: fondo `surface-alt` para distinguirlo de un campo de texto.

### Banners
- **Mensajes de sesión (`.messages`):** variantes éxito (esmeralda) / error (rojo) únicamente.
- **Aviso contextual (`.aviso`):** fondo `surface-alt`, borde punteado — nota persistente, disponible en el shell autenticado y en el público.

### Perfil Hero (Mi Perfil) — Signature Component
La foto de perfil es una ficha grande (`aspect-ratio: 3/4`, radio `18px`, `--shadow-lift`), clicable de punta a punta para cambiarla al instante; el nombre y un chip con el rol se estampan sobre un degradado de tinta al pie. Cifras reales (matrículas activas/compañeros para estudiante; promotorías/grupos para profesor; promotorías/usuarios para director-administrador) debajo, nunca "seguidores/seguidos" inventados.

### Public Auth Shell (marca provisional)
El sello circular `.escudo` (52px, fondo blanco, borde esmeralda de 2px, iniciales "CC" en monoespaciada) sigue siendo la única marca del sistema, ahora sin rotación — más quieto, más "producto", menos "sello de tinta". Sigue provisional: PRODUCT.md registra que no existe todavía una identidad de marca oficial.

## Do's and Don'ts

### Do:
- **Do** reproducir el marcador de estado completo (forma + color) — nunca solo recolorear una píldora genérica.
- **Do** dar a cada Área nueva su color de etiqueta vía `tag_color`, nunca un color inventado a mano.
- **Do** mantener la monoespaciada exclusiva a IDs, cifras y estados — nunca en prosa ni títulos.
- **Do** mantener cada campo de formulario en `1rem` mínimo en cualquier breakpoint.
- **Do** usar `--shadow` como mínimo en toda superficie de contenido nueva — en este mundo, todo está pineado.
- **Do** validar cualquier paleta de gráfica antes de usarla, comparando todos los pares entre sí — la rampa de Área ya falló esa prueba una vez.
- **Do** contar el total de la población como el todo de una gráfica de partes, y mostrar lo que falta como "sin responder" en gris.

### Don't:
- **Don't** usar el esmeralda de marca para un estado de datos (activa/error) — es exclusivamente el color de marca/acción.
- **Don't** reutilizar un color de etiqueta de Área como fondo de botón o de `.estado` — es metadata de categoría, no una acción.
- **Don't** volver a las mayúsculas trazadas en botones o navegación — ese vocabulario pertenece al mundo anterior de este producto.
- **Don't** inventar cifras sociales (seguidores, likes) en "Mi perfil" — solo cifras reales derivadas de los datos del usuario.
- **Don't** aplanar una tarjeta quitándole `--shadow` "para simplificar" — en este mundo nada descansa plano, todo está pineado.
- **Don't** usar los colores de Área (`tag-*`) en una gráfica de sectores — además de chocar semánticamente con el árbol de departamentos, su verde azulado y su rosa son indistinguibles bajo daltonismo protán.
- **Don't** asignar el color de una gráfica por ranking — sigue a la opción, para que filtrar o cambiar los conteos no repinte a las demás.
- **Don't** separar sectores ni barras con un borde dibujado alrededor — la separación es un hueco del color del fondo.
- **Don't** dejar que un decimal llegue localizado a un atributo SVG — la coma de `es-co` parte el valor en dos y rompe la geometría en silencio.
- **Don't** dibujar solo a quien respondió — la gráfica cuenta la población entera, y lo que falta se ve, en gris, tanto en torta como en barras.
