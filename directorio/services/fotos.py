"""
Servicio para gestionar las fotos de las personas.
Ahora trabaja con el modelo FotoPersona (N fotos por persona).
"""
from datetime import datetime
from pathlib import Path

from django.conf import settings

from directorio.models import FotoPersona


EXTENSIONES = ('.png', '.jpg', '.jpeg', '.webp')


def carpeta_activa() -> str:
    """Carpeta donde se guardan las fotos activas."""
    return getattr(settings, 'FOTOS_ACTIVAS', 'personas_gemini')


def carpeta_fotos(nombre: str = None) -> Path:
    """Devuelve la ruta absoluta de la carpeta de fotos."""
    if nombre is None:
        nombre = carpeta_activa()
    return Path(settings.BASE_DIR) / 'static' / 'img' / nombre


def carpeta_respaldo() -> Path:
    return Path(settings.BASE_DIR) / 'static' / 'img' / '_respaldo'


def guardar_foto(persona, archivo) -> FotoPersona:
    """
    Guarda `archivo` como una nueva FotoPersona.
    Si la persona no tenía fotos, la marca como principal.
    """
    ext = Path(archivo.name).suffix.lower()
    if ext not in EXTENSIONES:
        raise ValueError(f'Extensión no permitida: {ext}')

    carpeta_nombre = carpeta_activa()
    carpeta = carpeta_fotos(carpeta_nombre)
    carpeta.mkdir(parents=True, exist_ok=True)

    # Nombre único: slug + timestamp para no chocar con otras fotos
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    nombre_archivo = f'{persona.slug}_{ts}{ext}'
    destino = carpeta / nombre_archivo

    with open(destino, 'wb+') as f:
        for chunk in archivo.chunks():
            f.write(chunk)

    # ¿Es la primera foto?
    es_primera = not persona.fotos.exists()

    foto = FotoPersona.objects.create(
        persona=persona,
        archivo=nombre_archivo,
        carpeta=carpeta_nombre,
        es_principal=es_primera,
    )
    return foto


def eliminar_foto_persona(foto: FotoPersona, respaldar=True) -> bool:
    """
    Elimina una FotoPersona. Mueve el archivo a _respaldo/ si respaldar=True.
    Si era la principal, marca otra como principal (si existe).
    """
    archivo_fisico = settings.BASE_DIR / 'static' / 'img' / foto.carpeta / foto.archivo

    era_principal = foto.es_principal
    persona = foto.persona

    if archivo_fisico.exists():
        if respaldar:
            respaldo = carpeta_respaldo()
            respaldo.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            destino = respaldo / f'{archivo_fisico.stem}_{ts}{archivo_fisico.suffix}'
            archivo_fisico.rename(destino)
        else:
            archivo_fisico.unlink()

    foto.delete()

    # Si era la principal, promover otra
    if era_principal:
        siguiente = persona.fotos.first()
        if siguiente:
            siguiente.es_principal = True
            siguiente.save()

    return True


def marcar_como_principal(foto: FotoPersona):
    """Marca una foto como principal y desmarca las demás de la persona."""
    foto.marcar_como_principal()


def actualizar_nombre(persona, nuevo_nombre: str):
    """Actualiza el nombre de la persona."""
    persona.nombre = nuevo_nombre.strip()
    persona.save()
    return persona