"""Trigger que hace cumplir el cupo de promotoría dentro de la propia base de datos.

`Matricula.clean()` ya comprueba el cupo, pero entre esa comprobación y el
INSERT hay una ventana: dos solicitudes simultáneas para el último sitio pasan
las dos. Un CHECK no sirve (solo ve su propia fila) y un índice único tampoco
(el máximo es un dato variable, no una forma fija de la tabla), así que la
única garantía real es un trigger.

La clave para que sea a prueba de carreras es el `FOR UPDATE` sobre la fila de
`matriculas_cupopromotoria`: esa fila es el cerrojo natural de la promotoría en
ese periodo. Dos transacciones que intenten matricular a la vez se serializan
ahí, y la segunda ya cuenta a la primera. Sin cupo definido no hay fila, no hay
cerrojo y no hay tope: el camino sin límite no paga nada.
"""

from django.db import migrations

CREAR = r"""
CREATE OR REPLACE FUNCTION matriculas_cupo_promotoria_disponible()
RETURNS trigger AS $$
DECLARE
    maximo integer;
    ocupados integer;
    nombre_promotoria text;
    nombre_periodo text;
BEGIN
    -- Una matrícula retirada no ocupa sitio: nunca hay nada que comprobar.
    IF NEW.estado = 'retirada' THEN
        RETURN NEW;
    END IF;

    -- Solo se comprueba cuando la operación SUMA un sitio. Confirmar, rechazar
    -- o asignar grupo no cambian la ocupación, y bloquearlos dejaría al
    -- personal sin poder tocar las matrículas que ya existen tras bajar el cupo.
    IF TG_OP = 'UPDATE'
       AND OLD.estado <> 'retirada'
       AND OLD.promotoria_id = NEW.promotoria_id
       AND OLD.periodo_id = NEW.periodo_id THEN
        RETURN NEW;
    END IF;

    -- El FOR UPDATE es lo que cierra la carrera: bloquea la fila del cupo hasta
    -- el fin de la transacción, así dos matrículas simultáneas se serializan.
    SELECT cupo_maximo INTO maximo
    FROM matriculas_cupopromotoria
    WHERE promotoria_id = NEW.promotoria_id
      AND periodo_id = NEW.periodo_id
    FOR UPDATE;

    -- Sin cupo definido para ese periodo, la promotoría no tiene tope.
    IF NOT FOUND THEN
        RETURN NEW;
    END IF;

    SELECT count(*) INTO ocupados
    FROM matriculas_matricula
    WHERE promotoria_id = NEW.promotoria_id
      AND periodo_id = NEW.periodo_id
      AND estado <> 'retirada'
      AND id IS DISTINCT FROM NEW.id;

    IF ocupados >= maximo THEN
        SELECT nombre INTO nombre_promotoria FROM matriculas_promotoria WHERE id = NEW.promotoria_id;
        SELECT nombre INTO nombre_periodo FROM matriculas_periodo WHERE id = NEW.periodo_id;
        RAISE EXCEPTION
            'La promotoría % no tiene cupos disponibles para %: % de % ocupados, contando las solicitudes pendientes.',
            nombre_promotoria, nombre_periodo, ocupados, maximo
            USING ERRCODE = 'check_violation',
                  CONSTRAINT = 'cupo_promotoria_disponible';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS cupo_promotoria_disponible ON matriculas_matricula;

CREATE TRIGGER cupo_promotoria_disponible
    BEFORE INSERT OR UPDATE ON matriculas_matricula
    FOR EACH ROW EXECUTE FUNCTION matriculas_cupo_promotoria_disponible();
"""

DESHACER = r"""
DROP TRIGGER IF EXISTS cupo_promotoria_disponible ON matriculas_matricula;
DROP FUNCTION IF EXISTS matriculas_cupo_promotoria_disponible();
"""


class Migration(migrations.Migration):

    dependencies = [
        ("matriculas", "0010_cupo_por_promotoria_y_periodo"),
    ]

    operations = [
        migrations.RunSQL(sql=CREAR, reverse_sql=DESHACER),
    ]
