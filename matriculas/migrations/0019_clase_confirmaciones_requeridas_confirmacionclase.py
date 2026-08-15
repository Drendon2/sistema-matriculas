"""Las clases las verifican los estudiantes.

Registrar una clase deja de bastar para darla por dictada: ahora hace falta que
la confirmen suficientes estudiantes desde su propia sesión
(`ConfirmacionClase`), y cada clase guarda cuántas necesita.

El default de 3 solo sirve para poder añadir la columna. Las clases que ya
existían se recalculan enseguida con la regla real —una si el grupo tenía uno o
dos inscritos, tres si tenía más— porque un grupo de dos con el requisito en
tres se quedaría sin poder confirmar nunca, que es justo lo contrario de lo que
este cambio busca. Al revertir se pierden las confirmaciones dadas.
"""

import django.db.models.deletion
from django.db import migrations, models


def fijar_requisito_de_las_clases_existentes(apps, schema_editor):
    Clase = apps.get_model("matriculas", "Clase")
    Matricula = apps.get_model("matriculas", "Matricula")
    # Los estados van escritos aquí y no importados del modelo: una migración
    # tiene que seguir dando el mismo resultado aunque el código de hoy cambie.
    inscritos_estados = ("activa", "cancelacion_solicitada")

    for clase in Clase.objects.all():
        inscritos = Matricula.objects.filter(
            grupo_id=clase.grupo_id, periodo_id=clase.periodo_id,
            estado__in=inscritos_estados,
        ).count()
        if inscritos <= 0:
            requeridas = 0
        elif inscritos <= 2:
            requeridas = 1
        else:
            requeridas = 3
        Clase.objects.filter(pk=clase.pk).update(confirmaciones_requeridas=requeridas)


class Migration(migrations.Migration):

    dependencies = [
        ('matriculas', '0018_clase_asistencia'),
    ]

    operations = [
        migrations.AddField(
            model_name='clase',
            name='confirmaciones_requeridas',
            field=models.PositiveSmallIntegerField(default=3, help_text='Cuántos estudiantes tienen que confirmar esta clase. Lo fija el sistema al abrirla, según cuánta gente había inscrita en el grupo en ese momento.', verbose_name='confirmaciones requeridas'),
        ),
        migrations.RunPython(
            fijar_requisito_de_las_clases_existentes,
            # Al revertir, la columna entera se va con el AddField: no hay nada
            # que devolver a su sitio.
            migrations.RunPython.noop,
        ),
        migrations.CreateModel(
            name='ConfirmacionClase',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fecha', models.DateTimeField(auto_now_add=True)),
                ('clase', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='confirmaciones', to='matriculas.clase')),
                ('matricula', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='confirmaciones_clase', to='matriculas.matricula')),
            ],
            options={
                'verbose_name': 'Confirmación de clase',
                'verbose_name_plural': 'Confirmaciones de clase',
                'constraints': [models.UniqueConstraint(fields=('clase', 'matricula'), name='una_confirmacion_por_clase_y_estudiante', violation_error_message='Ya confirmaste esta clase.')],
            },
        ),
    ]
