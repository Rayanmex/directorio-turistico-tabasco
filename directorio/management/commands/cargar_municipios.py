from django.core.management.base import BaseCommand
from directorio.models import Municipio


MUNICIPIOS_TABASCO = [
    'Balancán',
    'Cárdenas',
    'Centla',
    'Centro',
    'Comalcalco',
    'Cunduacán',
    'Emiliano Zapata',
    'Huimanguillo',
    'Jalapa',
    'Jalpa de Méndez',
    'Jonuta',
    'Macuspana',
    'Nacajuca',
    'Paraíso',
    'Tacotalpa',
    'Teapa',
    'Tenosique',
]


class Command(BaseCommand):
    help = 'Carga los 17 municipios de Tabasco si no existen'

    def handle(self, *args, **options):
        creados = 0
        for i, nombre in enumerate(MUNICIPIOS_TABASCO):
            obj, created = Municipio.objects.get_or_create(
                nombre=nombre,
                defaults={'orden': i * 10},
            )
            if created:
                creados += 1
                self.stdout.write(self.style.SUCCESS(f'✓ {nombre}'))
            else:
                self.stdout.write(f'· {nombre} (ya existía)')

        self.stdout.write(self.style.SUCCESS(
            f'\nListo. {creados} municipios creados, {len(MUNICIPIOS_TABASCO) - creados} ya existían.'
        ))