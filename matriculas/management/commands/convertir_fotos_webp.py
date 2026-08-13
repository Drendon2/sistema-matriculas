from django.core.management.base import BaseCommand
from django.core.files.storage import default_storage

from matriculas.models import Perfil, _convertir_foto_a_webp


class Command(BaseCommand):
    """Convierte a WebP las fotos de perfil subidas ANTES de que la conversión
    automática existiera (ver Perfil.save() en matriculas/models.py). Corrida
    única, segura de repetir: cualquier foto que ya termine en .webp se salta.
    """

    help = "Convierte a WebP las fotos de perfil ya guardadas que quedaron en su formato original."

    def handle(self, *args, **options):
        convertidas = 0
        omitidas = 0
        for perfil in Perfil.objects.exclude(foto_perfil="").iterator():
            nombre_anterior = perfil.foto_perfil.name
            if nombre_anterior.lower().endswith(".webp"):
                omitidas += 1
                continue

            with perfil.foto_perfil.open("rb") as archivo_original:
                nuevo_archivo = _convertir_foto_a_webp(archivo_original)

            perfil.foto_perfil.save(nuevo_archivo.name, nuevo_archivo, save=True)
            default_storage.delete(nombre_anterior)
            convertidas += 1
            self.stdout.write(f"{perfil.nombre_completo}: {nombre_anterior} -> {perfil.foto_perfil.name}")

        self.stdout.write(self.style.SUCCESS(
            f"Listo: {convertidas} foto(s) convertida(s), {omitidas} ya estaban en WebP."
        ))
