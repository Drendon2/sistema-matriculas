"""Registro de clases dictadas y asistencia por estudiante.

Dos tablas nuevas, sin tocar nada de lo que ya existía: `Clase` (una sesión
concreta de un grupo, con la hora real en que el profesor oprimió el botón) y
`Asistencia` (cómo le fue a cada estudiante en esa clase).

No hay datos que migrar hacia atrás: la asistencia empieza a existir desde la
primera clase que se registre. Revertir borra las dos tablas y con ellas todo
lo pasado hasta ese momento.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('matriculas', '0017_alter_matricula_estado'),
    ]

    operations = [
        migrations.CreateModel(
            name='Clase',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fecha_hora', models.DateTimeField(auto_now_add=True, verbose_name='fecha y hora')),
                ('grupo', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='clases', to='matriculas.grupo')),
                ('periodo', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='clases', to='matriculas.periodo')),
                ('registrada_por', models.ForeignKey(blank=True, help_text='Quién oprimió el botón. Queda en blanco si esa cuenta se elimina.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='clases_registradas', to='matriculas.perfil', verbose_name='registrada por')),
            ],
            options={
                'verbose_name': 'Clase',
                'verbose_name_plural': 'Clases',
                'ordering': ['-fecha_hora'],
            },
        ),
        migrations.CreateModel(
            name='Asistencia',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('estado', models.CharField(choices=[('asistio', 'Asistió'), ('falto', 'Faltó'), ('excusa', 'Faltó con excusa')], max_length=10)),
                ('fecha_registro', models.DateTimeField(auto_now=True, verbose_name='fecha de registro')),
                ('matricula', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='asistencias', to='matriculas.matricula')),
                ('clase', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='asistencias', to='matriculas.clase')),
            ],
            options={
                'verbose_name': 'Asistencia',
                'verbose_name_plural': 'Asistencias',
                'constraints': [models.UniqueConstraint(fields=('clase', 'matricula'), name='una_asistencia_por_clase_y_matricula')],
            },
        ),
    ]
