"""La encuesta demográfica pasa de texto libre a listas cerradas.

`nivel_educativo`, `ocupacion`, `grupo_etnico` y `discapacidad` eran CharField
libres; ahora tienen `choices`, y se suman tres campos nuevos (zona, víctima
del conflicto armado y afiliación a salud).

Qué se hace con lo ya escrito
-----------------------------
Se VACÍAN los cuatro campos convertidos, y la persona los vuelve a responder la
próxima vez que entre a "Mi perfil".

No se mapean a los códigos nuevos porque no hay mapeo fiable: había respuestas
que sí calzaban («Universitario», «Posgrado») junto a otras que exigían
interpretar («Bachillerato» ¿es secundaria completa?) y algunas sencillamente
no traducibles a la lista nueva («Docente», «Asesor de proyectos», que lo mismo
son empleados que independientes). Adivinar habría metido datos inventados
justo en las cifras que este cambio pretende volver fiables. Vaciar deja el
hueco a la vista, que es más honesto que rellenarlo mal.

Al revertir, los campos se quedan vacíos: el texto original no se guarda en
ninguna parte, así que no hay nada que devolver.
"""

from django.db import migrations, models


def limpiar_texto_libre(apps, schema_editor):
    EncuestaDemografica = apps.get_model("matriculas", "EncuestaDemografica")
    EncuestaDemografica.objects.update(
        nivel_educativo="", ocupacion="", grupo_etnico="", discapacidad="",
    )


class Migration(migrations.Migration):

    dependencies = [
        ('matriculas', '0015_limite_promotorias_configurable'),
    ]

    operations = [
        # Va PRIMERO, antes de los AlterField: los campos se estrechan de 40/80
        # a 20 caracteres, y una respuesta libre más larga que eso haría fallar
        # el ALTER. Limpiando antes, la columna que se estrecha ya está vacía.
        migrations.RunPython(limpiar_texto_libre, migrations.RunPython.noop),
        migrations.AddField(
            model_name='encuestademografica',
            name='afiliacion_salud',
            field=models.CharField(blank=True, choices=[('contributivo', 'Contributivo'), ('subsidiado', 'Subsidiado'), ('no_afiliado', 'No afiliado'), ('no_sabe', 'No sabe')], max_length=20, verbose_name='afiliación a salud'),
        ),
        migrations.AddField(
            model_name='encuestademografica',
            name='victima_conflicto_armado',
            field=models.CharField(blank=True, choices=[('si', 'Sí'), ('no', 'No'), ('ns', 'Prefiero no responder')], max_length=20, verbose_name='víctima del conflicto armado'),
        ),
        migrations.AddField(
            model_name='encuestademografica',
            name='zona',
            field=models.CharField(blank=True, choices=[('urbana', 'Urbana'), ('rural', 'Rural'), ('centro_poblado', 'Centro poblado')], max_length=20),
        ),
        migrations.AlterField(
            model_name='encuestademografica',
            name='discapacidad',
            field=models.CharField(blank=True, choices=[('ninguna', 'Ninguna'), ('fisica', 'Física/motora'), ('visual', 'Visual'), ('auditiva', 'Auditiva'), ('intelectual', 'Intelectual/cognitiva'), ('psicosocial', 'Psicosocial'), ('multiple', 'Múltiple'), ('ns', 'Prefiero no responder')], max_length=20),
        ),
        migrations.AlterField(
            model_name='encuestademografica',
            name='grupo_etnico',
            field=models.CharField(blank=True, choices=[('ninguno', 'Ninguno'), ('indigena', 'Indígena'), ('afro', 'Negro/Afrocolombiano'), ('raizal', 'Raizal'), ('palenquero', 'Palenquero'), ('rrom', 'Rrom/Gitano'), ('ns', 'Prefiero no responder')], max_length=20, verbose_name='grupo étnico'),
        ),
        migrations.AlterField(
            model_name='encuestademografica',
            name='nivel_educativo',
            field=models.CharField(choices=[('ninguno', 'Ninguno'), ('primaria_inc', 'Primaria incompleta'), ('primaria_com', 'Primaria completa'), ('secundaria_inc', 'Secundaria incompleta'), ('secundaria_com', 'Secundaria completa'), ('tecnico', 'Técnico'), ('tecnologo', 'Tecnólogo'), ('universitario', 'Universitario'), ('posgrado', 'Posgrado')], max_length=20, verbose_name='nivel educativo'),
        ),
        migrations.AlterField(
            model_name='encuestademografica',
            name='ocupacion',
            field=models.CharField(choices=[('estudiante', 'Estudiante'), ('empleado', 'Empleado'), ('independiente', 'Independiente'), ('desempleado', 'Desempleado'), ('hogar', 'Hogar'), ('pensionado', 'Pensionado'), ('otro', 'Otro')], max_length=20, verbose_name='ocupación'),
        ),
    ]
