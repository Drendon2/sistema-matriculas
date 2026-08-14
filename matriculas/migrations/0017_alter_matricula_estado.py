"""Un estado más: la cancelación pedida por el estudiante y aún sin resolver.

Retirarse dejó de ser inmediato. El estudiante SOLICITA la cancelación y un
director o administrador la resuelve; mientras tanto la matrícula vive en
`cancelacion_solicitada`.

No hace falta tocar ninguna restricción, y no es casualidad: tanto el índice
único de ranura (`una_matricula_por_ranura_y_periodo`) como el trigger de cupo
(`cupo_promotoria_disponible`) están escritos excluyendo el valor "retirada" en
concreto, no "cualquier cosa que no sea activa". Un estado nuevo cae por
omisión del lado que ocupa sitio, que es justo lo que debe pasar: hasta que
alguien apruebe la salida, el estudiante sigue contando para el cupo de la
promotoría y para su propio límite de promotorías por periodo.

`max_length` sube de 10 a 24 porque el código nuevo no cabía en el anterior.
Ninguna fila existente cambia de valor: las que ya estaban retiradas siguen
retiradas.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('matriculas', '0016_encuestademografica_afiliacion_salud_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='matricula',
            name='estado',
            field=models.CharField(choices=[('pendiente', 'Pendiente de confirmación'), ('activa', 'Activa'), ('cancelacion_solicitada', 'Cancelación solicitada'), ('retirada', 'Retirada')], default='pendiente', max_length=24),
        ),
    ]
