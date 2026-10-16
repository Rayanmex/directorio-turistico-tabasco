from django.core.management.base import BaseCommand
from directorio.models import Giro


# (nombre, icono, descripcion)
GIROS_TABASCO = [
    ('Cabaña',              '🏕️', 'Cabañas y alojamiento rústico'),
    ('Hospedaje',           '🛏️', 'Alojamiento en general'),
    ('Hotel',               '🏨', 'Hoteles y moteles'),
    ('Restaurante',         '🍽️', 'Restaurantes y fondas'),
    ('Cafetería',           '☕', 'Cafeterías y panaderías'),
    ('Bar',                 '🍺', 'Bares y cantinas'),
    ('Cocina tradicional',  '🌮', 'Cocina típica tabasqueña'),
    ('Recorrido',           '🚶', 'Tours y recorridos guiados'),
    ('Centro Ecoturístico', '🌿', 'Parques y centros de naturaleza'),
    ('Agencia de viajes',   '🧭', 'Agencias y operadores turísticos'),
    ('Balneario',           '💦', 'Balnearios y spas'),
    ('Artesanías',          '🎨', 'Tiendas de artesanías'),
    ('Museo',               '🏛️', 'Museos y galerías'),
    ('Sitio arqueológico',  '🗿', 'Zonas arqueológicas'),
    ('Parque',              '🌳', 'Parques y plazas'),
    ('Productor local',     '🌾', 'Productores y agroindustria'),
    ('Otro',                '📍', 'Otros giros'),
]


class Command(BaseCommand):
    help = 'Carga los giros sugeridos para el directorio turístico'

    def handle(self, *args, **options):
        creados = 0
        actualizados = 0

        for i, (nombre, icono, descripcion) in enumerate(GIROS_TABASCO):
            obj, created = Giro.objects.get_or_create(
                nombre=nombre,
                defaults={
                    'orden': i * 10,
                    'icono': icono,
                    'descripcion': descripcion,
                },
            )
            if created:
                creados += 1
                self.stdout.write(self.style.SUCCESS(
                    f'✓ {icono} {nombre}'
                ))
            else:
                # Si ya existía pero sin icono, actualizarlo
                if not obj.icono:
                    obj.icono = icono
                    obj.save()
                    actualizados += 1
                self.stdout.write(f'· {icono} {nombre} (ya existía)')

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Listo. {creados} creados, {actualizados} actualizados, '
            f'{len(GIROS_TABASCO) - creados - actualizados} sin cambios.'
        ))