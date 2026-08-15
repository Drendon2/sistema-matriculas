"""Una promotoría la puede dictar cualquiera del personal, no solo el rol "profesor".

Un director de escuela que además da su propia promotoría es un caso real, y
con `limit_choices_to={"rol": "profesor"}` no podía ni aparecer en el
desplegable que la asigna. Ahora entran los tres roles del personal
(`Perfil.ROLES_PERSONAL`); los estudiantes siguen fuera.

`limit_choices_to` no toca el esquema —solo acota lo que ofrecen los
formularios y el admin—, así que esta migración no cambia ni un dato. Nada que
revertir salvo volver a estrechar la lista.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('matriculas', '0019_clase_confirmaciones_requeridas_confirmacionclase'),
    ]

    operations = [
        migrations.AlterField(
            model_name='promotoria',
            name='profesor',
            field=models.ForeignKey(blank=True, help_text='Quien la dicta y pasa lista en sus grupos. Puede ser un director que también enseña.', limit_choices_to={'rol__in': ('administrador', 'director', 'profesor')}, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='promotorias_dictadas', to='matriculas.perfil'),
        ),
    ]
