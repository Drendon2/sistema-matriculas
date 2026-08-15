from datetime import date

from django import forms
from django.contrib.auth.models import User

from .models import (
    RANURA_MAXIMA_ABSOLUTA,
    ConfiguracionInstitucion, DatosEstudiante, DocumentoRequerido,
    EncuestaDemografica, EncuestaSatisfaccion, Grupo, Perfil, Promotoria,
    limite_promotorias,
)


class DocumentoRequeridoForm(forms.ModelForm):
    """Alta de un papel que la institución va a pedir.

    `activo` no está: un documento se crea pidiéndose. Dejar de pedirlo es una
    acción aparte en la lista, y no una casilla que se pueda desmarcar sin
    darse cuenta mientras se escribe el nombre.
    """

    class Meta:
        model = DocumentoRequerido
        fields = ["nombre", "descripcion", "obligatorio", "orden"]
        widgets = {
            "nombre": forms.TextInput(attrs={"placeholder": "Certificado de EPS"}),
            "descripcion": forms.TextInput(
                attrs={"placeholder": "Vigencia no mayor a 30 días (opcional)"}),
            "orden": forms.NumberInput(attrs={"min": 0, "step": 1, "style": "width:5rem;"}),
        }


class ConfiguracionInstitucionForm(forms.ModelForm):
    """Ajustes de la institución: la marca y el límite de promotorías.

    El color usa <input type="color"> del navegador; el límite, un <input
    type="number"> acotado al rango que admite el esquema, para que el
    navegador ayude antes de que responda el validador del modelo.
    """

    class Meta:
        model = ConfiguracionInstitucion
        fields = [
            "nombre_institucion", "logo", "color_acento",
            "limite_promotorias_por_periodo", "promotorias_visibles_para_estudiantes",
        ]
        widgets = {
            "color_acento": forms.TextInput(attrs={"type": "color"}),
            "limite_promotorias_por_periodo": forms.NumberInput(
                attrs={"min": 1, "max": RANURA_MAXIMA_ABSOLUTA, "step": 1}
            ),
        }


class EncuestaSatisfaccionForm(forms.ModelForm):
    """Las cinco preguntas que acompañan al botón de renovar."""

    class Meta:
        model = EncuestaSatisfaccion
        fields = [
            "satisfaccion_general", "calificacion_profesor",
            "horario_funciono", "recomendaria", "comentario",
        ]
        labels = {
            "satisfaccion_general": "¿Qué tan satisfecho quedaste con el proceso?",
            "calificacion_profesor": "¿Cómo calificas el acompañamiento del profesor?",
            "horario_funciono": "¿El horario te funcionó?",
            "recomendaria": "¿Recomendarías tu promotoría a alguien más?",
            "comentario": "¿Algo que quieras contarnos? (opcional)",
        }
        widgets = {
            "satisfaccion_general": forms.RadioSelect,
            "calificacion_profesor": forms.RadioSelect,
            "horario_funciono": forms.RadioSelect(choices=[(True, "Sí"), (False, "No")]),
            "recomendaria": forms.RadioSelect(choices=[(True, "Sí"), (False, "No")]),
            "comentario": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # RadioSelect de un campo con choices mete una opción vacía "---------";
        # sobra, porque las cuatro primeras preguntas son obligatorias.
        for nombre in ("satisfaccion_general", "calificacion_profesor"):
            self.fields[nombre].widget.choices = EncuestaSatisfaccion.ESCALA
        for nombre in ("horario_funciono", "recomendaria"):
            self.fields[nombre].required = True


def campo_fecha_nacimiento(label="Fecha de nacimiento"):
    """DateField con formato ISO fijo.

    Con LANGUAGE_CODE en español, Django formatea la fecha inicial como
    dd/mm/aaaa, pero el <input type="date"> del navegador solo entiende
    aaaa-mm-dd — si no coinciden, el navegador simplemente lo muestra vacío.
    Fijar el formato evita eso tanto al mostrar como al leer el valor.
    """
    return forms.DateField(
        label=label,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        input_formats=["%Y-%m-%d"],
    )


class EncuestaDemograficaForm(forms.ModelForm):
    class Meta:
        model = EncuestaDemografica
        exclude = ["perfil", "fecha_autorizacion"]
        widgets = {
            "autoriza_tratamiento_datos": forms.CheckboxInput(),
        }


class FotoPerfilForm(forms.ModelForm):
    """Subida de foto en "Mi perfil", ya logueado (ver RegistroForm/InscripcionEstudianteForm).

    Widget plano (no ClearableFileInput): la plantilla dibuja su propia
    tarjeta clicable alrededor del input, así que no queremos el texto
    "Currently / Clear" que agrega el widget por defecto de Django.
    """

    class Meta:
        model = Perfil
        fields = ["foto_perfil"]
        labels = {"foto_perfil": "Foto de perfil"}
        widgets = {
            "foto_perfil": forms.FileInput(attrs={"accept": "image/*", "class": "perfil-avatar-input"}),
        }


class CopiaDocumentoForm(forms.ModelForm):
    """Subida de la copia del documento en "Mi perfil" (solo estudiantes)."""

    class Meta:
        model = DatosEstudiante
        fields = ["copia_documento"]


class DatosContactoForm(forms.ModelForm):
    """Edición del teléfono en "Mi perfil" (la edad no se edita: sale de la fecha de nacimiento)."""

    class Meta:
        model = Perfil
        fields = ["telefono"]
        labels = {"copia_documento": "Copia del documento"}


class GrupoForm(forms.ModelForm):
    """Grupo dentro de una promotoría ya conocida (la fija la vista, no el form)."""

    class Meta:
        model = Grupo
        fields = ["nivel", "horario", "salon", "cupo_maximo"]


class UsuarioForm(forms.Form):
    """Combina User + Perfil (+ DatosEstudiante/Acudiente si el rol es estudiante).

    No es un ModelForm porque abarca varios modelos a la vez; la vista se
    encarga de guardar cada pieza.
    """

    username = forms.CharField(max_length=150, label="Usuario")
    password = forms.CharField(
        label="Contraseña temporal", widget=forms.PasswordInput, required=False,
        help_text="Al editar, déjalo en blanco para no cambiar la contraseña.",
    )
    rol = forms.ChoiceField(choices=Perfil.ROLES, label="Rol")
    nombre_completo = forms.CharField(max_length=90, label="Nombre completo")
    fecha_nacimiento = campo_fecha_nacimiento()
    telefono = forms.CharField(max_length=15, label="Teléfono")
    foto_perfil = forms.ImageField(label="Foto de perfil", required=False)

    documento_identidad = forms.CharField(max_length=15, label="Documento de identidad (solo estudiante)", required=False)
    copia_documento = forms.FileField(label="Copia del documento (solo estudiante)", required=False)
    acudiente_nombre = forms.CharField(max_length=90, label="Nombre del acudiente (solo estudiante)", required=False)
    acudiente_telefono = forms.CharField(max_length=15, label="Teléfono del acudiente", required=False)

    def __init__(self, *args, es_creacion=True, **kwargs):
        self.es_creacion = es_creacion
        super().__init__(*args, **kwargs)
        self.fields["password"].required = es_creacion
        self.fields["foto_perfil"].required = es_creacion

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("rol") == "estudiante":
            if not cleaned.get("documento_identidad"):
                self.add_error("documento_identidad", "Obligatorio para estudiantes.")
            if self.es_creacion and not cleaned.get("copia_documento"):
                self.add_error("copia_documento", "Obligatorio para estudiantes.")
        return cleaned


class RegistroForm(forms.Form):
    """Autorregistro público: crea la cuenta y el perfil básico, SIN rol.

    No pide foto de perfil: por seguridad, los archivos no se suben desde un
    formulario público sin autenticar. La persona la sube después, ya
    logueada, en "Mi perfil".

    Un director/administrador le asigna el rol después desde Gestión de
    usuarios (ver UsuarioForm/usuario_editar).
    """

    username = forms.CharField(max_length=150, label="Usuario")
    password = forms.CharField(label="Contraseña", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Confirmar contraseña", widget=forms.PasswordInput)
    nombre_completo = forms.CharField(max_length=90, label="Nombre completo")
    fecha_nacimiento = campo_fecha_nacimiento()
    telefono = forms.CharField(max_length=15, label="Teléfono")

    def clean_username(self):
        username = self.cleaned_data["username"]
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("Ya existe una cuenta con ese nombre de usuario.")
        return username

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("password") and cleaned.get("password2") and cleaned["password"] != cleaned["password2"]:
            self.add_error("password2", "Las contraseñas no coinciden.")
        return cleaned


class InscripcionEstudianteForm(forms.Form):
    """Autorregistro de estudiante: crea la cuenta Y la inscribe a una promotoría.

    No pide foto de perfil ni copia del documento: por seguridad, los
    archivos no se suben desde un formulario público sin autenticar. El
    estudiante los sube después, ya logueado, en "Mi perfil"; eso NO bloquea
    que el profesor confirme la matrícula mientras tanto.

    La matrícula queda "pendiente" hasta que el profesor la confirme.
    """

    username = forms.CharField(max_length=150, label="Usuario")
    password = forms.CharField(label="Contraseña", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Confirmar contraseña", widget=forms.PasswordInput)
    nombre_completo = forms.CharField(max_length=90, label="Nombre completo")
    fecha_nacimiento = campo_fecha_nacimiento()
    telefono = forms.CharField(max_length=15, label="Teléfono")

    documento_identidad = forms.CharField(max_length=15, label="Documento de identidad")
    acudiente_nombre = forms.CharField(max_length=90, label="Nombre del acudiente", required=False)
    acudiente_telefono = forms.CharField(max_length=15, label="Teléfono del acudiente", required=False)

    # Solo el primer cupo es fijo: el resto se construyen en __init__ según el
    # límite configurado, así que subirlo añade selectores sin tocar el código.
    promotoria = forms.ModelChoiceField(
        queryset=Promotoria.objects.none(), label="Promotoría principal",
        empty_label="-- elegir --",
    )

    def __init__(self, *args, periodo_activo=None, limite=None, **kwargs):
        self.periodo_activo = periodo_activo
        self.limite = limite if limite is not None else limite_promotorias()
        super().__init__(*args, **kwargs)

        for numero in range(2, self.limite + 1):
            self.fields[f"promotoria_{numero}"] = forms.ModelChoiceField(
                queryset=Promotoria.objects.none(),
                label=f"Promotoría {numero}",
                empty_label="-- elegir --",
                required=False,
            )

        promotorias = Promotoria.objects.select_related("area").order_by("area__nombre", "nombre")
        for nombre_campo in self.nombres_campos_promotoria:
            self.fields[nombre_campo].queryset = promotorias
            self.fields[nombre_campo].label_from_instance = lambda p: f"{p.nombre} ({p.area})"

    @property
    def nombres_campos_promotoria(self):
        return ["promotoria"] + [f"promotoria_{n}" for n in range(2, self.limite + 1)]

    @property
    def campos_promotoria(self):
        """Los cupos como BoundField, en orden, para que la plantilla los recorra."""
        return [self[nombre] for nombre in self.nombres_campos_promotoria]

    @property
    def campos_promotoria_extra(self):
        """Los cupos opcionales: todos menos el primero, que es obligatorio."""
        return self.campos_promotoria[1:]

    def promotorias_elegidas(self):
        """Las promotorías escogidas, en orden de cupo y sin repetir."""
        elegidas = []
        for nombre in self.nombres_campos_promotoria:
            elegida = self.cleaned_data.get(nombre)
            if elegida is not None and elegida not in elegidas:
                elegidas.append(elegida)
        return elegidas

    def clean_username(self):
        username = self.cleaned_data["username"]
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("Ya existe una cuenta con ese nombre de usuario.")
        return username

    def clean_documento_identidad(self):
        documento_identidad = self.cleaned_data["documento_identidad"]
        if DatosEstudiante.objects.filter(documento_identidad=documento_identidad).exists():
            raise forms.ValidationError("Ya existe un estudiante registrado con ese documento de identidad.")
        return documento_identidad

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("password") and cleaned.get("password2") and cleaned["password"] != cleaned["password2"]:
            self.add_error("password2", "Las contraseñas no coinciden.")

        fecha_nacimiento = cleaned.get("fecha_nacimiento")
        if fecha_nacimiento:
            hoy = date.today()
            edad = hoy.year - fecha_nacimiento.year - (
                (hoy.month, hoy.day) < (fecha_nacimiento.month, fecha_nacimiento.day)
            )
            if edad < 18 and not cleaned.get("acudiente_nombre"):
                self.add_error(
                    "acudiente_nombre",
                    "Eres menor de edad: necesitas registrar el nombre de tu acudiente.",
                )

        # Ninguna promotoría puede repetirse entre cupos. Se recorren todos los
        # que existan, no solo dos: el error se marca en el cupo repetido, que
        # es el que la persona tiene que corregir.
        vistas = set()
        for nombre in self.nombres_campos_promotoria:
            elegida = cleaned.get(nombre)
            if elegida is None:
                continue
            if elegida.pk in vistas:
                self.add_error(
                    nombre,
                    f"Ya elegiste {elegida} en otro cupo. Escoge una distinta o deja este vacío.",
                )
            vistas.add(elegida.pk)

        if self.periodo_activo is None:
            raise forms.ValidationError(
                "No hay un periodo de matrícula activo en este momento. Intenta más tarde."
            )

        return cleaned
