import os
import re
import unicodedata

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.db import models


# ===============================================================
# UTILIDADES
# ===============================================================
def slugify_texto(texto: str) -> str:
    """'Casa Castillo Cabañas' -> 'casa-castillo-cabanas'"""
    if not texto:
        return ""
    texto = unicodedata.normalize('NFKD', texto)
    texto = texto.encode('ascii', 'ignore').decode('ascii')
    texto = texto.lower()
    texto = re.sub(r'[^a-z0-9\s_-]', '', texto)
    texto = re.sub(r'[\s\-_]+', '-', texto.strip())
    return texto.strip('-')


def _slug_unico(Modelo, base: str, pk=None) -> str:
    """Genera slug único para un modelo."""
    slug = base or 'sin-nombre'
    contador = 1
    qs = Modelo.objects.exclude(pk=pk)
    while qs.filter(slug=slug).exists():
        slug = f'{base}-{contador}'
        contador += 1
    return slug


# ===============================================================
# TAXONOMÍAS
# ===============================================================
class Municipio(models.Model):
    nombre = models.CharField(max_length=150, unique=True)
    slug = models.SlugField(max_length=180, unique=True, blank=True)
    orden = models.PositiveIntegerField(default=0)
    descripcion = models.TextField(blank=True)
    imagen = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ['orden', 'nombre']
        verbose_name = 'Municipio'
        verbose_name_plural = 'Municipios'

    def __str__(self):
        return self.nombre

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify_texto(self.nombre)
        super().save(*args, **kwargs)


class Giro(models.Model):
    nombre = models.CharField(max_length=150, unique=True)
    slug = models.SlugField(max_length=180, unique=True, blank=True)
    orden = models.PositiveIntegerField(default=0)
    icono = models.CharField(max_length=100, blank=True)
    descripcion = models.TextField(blank=True)

    class Meta:
        ordering = ['orden', 'nombre']
        verbose_name = 'Giro'
        verbose_name_plural = 'Giros'

    def __str__(self):
        return self.nombre

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify_texto(self.nombre)
        super().save(*args, **kwargs)


# ===============================================================
# REDES SOCIALES (genéricas)
# ===============================================================
class RedSocial(models.Model):
    """
    Red social asociada a Negocio, Experiencia o Guia.
    Usa GenericForeignKey para servir a los 3 modelos.
    """
    REDES = [
        ('facebook', 'Facebook'),
        ('instagram', 'Instagram'),
        ('tiktok', 'TikTok'),
        ('whatsapp', 'WhatsApp'),
        ('youtube', 'YouTube'),
        ('twitter', 'Twitter / X'),
        ('pagina', 'Página web'),
        ('otra', 'Otra'),
    ]

    # Generic FK
    content_type = models.ForeignKey(
        ContentType, on_delete=models.CASCADE
    )
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')

    tipo = models.CharField(max_length=20, choices=REDES)
    usuario = models.CharField(max_length=300, help_text='@handle, usuario o URL')
    referencia = models.CharField(max_length=300, blank=True,
        help_text='Referencia de redes (fuente)')
    actividad = models.TextField(blank=True,
        help_text='Notas sobre actividad reciente en redes')
    orden = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['orden', 'tipo']
        verbose_name = 'Red social'
        verbose_name_plural = 'Redes sociales'
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
        ]

    def __str__(self):
        return f'{self.get_tipo_display()}: {self.usuario}'

    @property
    def url(self):
        u = (self.usuario or '').strip()
        if not u:
            return '#'
        if u.startswith('http'):
            return u
        u = u.lstrip('@')
        base = {
            'facebook':  f'https://facebook.com/{u}',
            'instagram': f'https://instagram.com/{u}',
            'tiktok':    f'https://tiktok.com/@{u}',
            'whatsapp':  f'https://wa.me/{u}',
            'youtube':   f'https://youtube.com/@{u}',
            'twitter':   f'https://twitter.com/{u}',
            'pagina':    f'https://{u}',
        }
        return base.get(self.tipo, u)


# ===============================================================
# FUENTES (genéricas)
# ===============================================================
class Fuente(models.Model):
    """
    Fuente de un dato (URL + descripción).
    Puede pertenecer a Negocio, Experiencia o Guia.
    """
    content_type = models.ForeignKey(
        ContentType, on_delete=models.CASCADE
    )
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')

    url = models.URLField(max_length=500)
    descripcion = models.CharField(max_length=400, blank=True,
        help_text='Ej: "Catálogo estatal, página 6"')
    orden = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['orden']
        verbose_name = 'Fuente'
        verbose_name_plural = 'Fuentes'
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
        ]

    def __str__(self):
        return self.descripcion or self.url


# ===============================================================
# NEGOCIO (Hoja 1: Directorio Turístico)
# ===============================================================
class Negocio(models.Model):
    """Negocio físico / lugar turístico."""
    excel_id = models.PositiveIntegerField(unique=True, null=True, blank=True)

    # Clasificación
    municipio = models.ForeignKey(
        Municipio, on_delete=models.PROTECT,
        related_name='negocios', null=True, blank=True
    )
    municipio_original = models.CharField(
        max_length=200, blank=True,
        help_text='Valor tal como venía en el Excel (si no era un municipio válido)'
    )
    giro = models.ForeignKey(
        Giro, on_delete=models.PROTECT,
        related_name='negocios', null=True, blank=True
    )
    giro_original = models.CharField(
        max_length=200, blank=True,
        help_text='Valor tal como venía en el Excel'
    )

    # Datos básicos
    nombre = models.CharField(max_length=250)
    slug = models.SlugField(max_length=250, unique=True, blank=True)
    direccion = models.CharField(max_length=500, blank=True)
    telefono = models.CharField(max_length=150, blank=True,
        help_text='Puede contener varios números separados por /')
    email = models.EmailField(blank=True)
    sitio_web = models.URLField(blank=True)

    # Descripción (antes se llamaba "experiencia")
    descripcion = models.TextField(blank=True,
        help_text='Descripción / qué ofrece el negocio')

    # Geolocalización
    latitud = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitud = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    # Presentación
    orden = models.PositiveIntegerField(default=0)
    destacado = models.BooleanField(default=False)
    activo = models.BooleanField(default=True)

    # Metadata de investigación
    actividad_redes = models.TextField(blank=True)
    fecha_revision = models.DateField(null=True, blank=True)

    # Auditoría
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    # Relations (GenericRelation)
    redes = GenericRelation(RedSocial, related_query_name='negocios')
    fuentes = GenericRelation(Fuente, related_query_name='negocios')

    class Meta:
        ordering = ['municipio__orden', 'giro__orden', 'orden', 'nombre']
        verbose_name = 'Negocio'
        verbose_name_plural = 'Negocios'
        indexes = [
            models.Index(fields=['municipio', 'giro']),
            models.Index(fields=['slug']),
        ]

    def __str__(self):
        return f'{self.nombre} ({self.municipio or self.municipio_original})'

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = _slug_unico(Negocio, slugify_texto(self.nombre), self.pk)
        super().save(*args, **kwargs)

    # ---- Fotos ----
    @property
    def logo_url(self):
        logo = self.fotos.filter(tipo='logo').first()
        if logo:
            return logo.url
        portada = self.fotos.filter(tipo='portada').first()
        if portada:
            return portada.url
        primera = self.fotos.first()
        if primera:
            return primera.url
        carpeta = getattr(settings, 'FOTOS_ACTIVAS', 'negocios')
        for ext in ('.png', '.jpg', '.jpeg', '.webp'):
            rel = f'img/{carpeta}/{self.slug}{ext}'
            if os.path.exists(settings.BASE_DIR / 'static' / rel):
                return f'{settings.STATIC_URL}{rel}'
        return None

    

    @property
    def galeria(self):
        return self.fotos.filter(tipo='galeria').order_by('-fecha_subida')

    @property
    def foto_url(self):
        return self.logo_url

    @property
    def todas_las_fotos(self):
        return self.fotos.all().order_by('tipo', '-fecha_subida')

    @property
    def telefono_limpio(self):
        return re.sub(r'\D', '', self.telefono or '')


# ===============================================================
# EXPERIENCIA (Hojas 2 y 3)
# ===============================================================
class Experiencia(models.Model):
    """Experiencia / oferta turística."""
    excel_id = models.PositiveIntegerField(unique=True, null=True, blank=True)

    nombre = models.CharField(max_length=300)
    slug = models.SlugField(max_length=300, unique=True, blank=True)

    # Operador
    operador = models.ForeignKey(
        Negocio, on_delete=models.SET_NULL,
        related_name='experiencias', null=True, blank=True
    )
    operador_original = models.CharField(max_length=250, blank=True,
        help_text='Nombre tal como venía en el Excel')

    # Clasificación
    municipio = models.ForeignKey(
        Municipio, on_delete=models.PROTECT,
        related_name='experiencias', null=True, blank=True
    )
    municipio_original = models.CharField(max_length=200, blank=True)


    referencia_redes = models.TextField(
    blank=True,
    help_text='Notas sobre las redes del operador'
    )

    giro = models.ForeignKey(
        Giro, on_delete=models.PROTECT,
        related_name='experiencias', null=True, blank=True
    )
    giro_original = models.CharField(max_length=200, blank=True)

    # Ubicación específica de la experiencia
    lugar_realizacion = models.CharField(max_length=400, blank=True,
        help_text='Dónde se realiza la experiencia')
    direccion_referencia = models.CharField(max_length=500, blank=True)

    # Contacto
    telefono = models.CharField(max_length=150, blank=True)
    contacto_encargado = models.CharField(max_length=250, blank=True)

    duracion = models.CharField(
    max_length=100, blank=True,
    help_text='Ej: 6D/5N, 3 horas, medio día'
    )

    # Contenido
    descripcion = models.TextField(blank=True,
        help_text='Qué ofrece la experiencia')

    # Estado de la oferta
    ESTADOS = [
        ('publicada', 'Publicada en catálogo'),
        ('disponible', 'Disponible'),
        ('pendiente', 'Pendiente de confirmar'),
        ('descontinuada', 'Descontinuada'),
    ]
    estado_oferta = models.CharField(
        max_length=30, choices=ESTADOS, blank=True,
        help_text='Estado de la oferta'
    )

    # Metadata de investigación
    actividad_redes = models.TextField(blank=True)
    fecha_revision = models.DateField(null=True, blank=True)

    # Presentación
    orden = models.PositiveIntegerField(default=0)
    destacado = models.BooleanField(default=False)
    activo = models.BooleanField(default=True)

    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    redes = GenericRelation(RedSocial, related_query_name='experiencias')
    fuentes = GenericRelation(Fuente, related_query_name='experiencias')

    class Meta:
        ordering = ['municipio__orden', 'orden', 'nombre']
        verbose_name = 'Experiencia'
        verbose_name_plural = 'Experiencias'
        indexes = [
            models.Index(fields=['municipio']),
            models.Index(fields=['slug']),
        ]

    def __str__(self):
        return self.nombre

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = _slug_unico(Experiencia, slugify_texto(self.nombre), self.pk)
        super().save(*args, **kwargs)


# ===============================================================
# GUIA (Hoja 4)
# ===============================================================
class Guia(models.Model):
    """Guía turístico (persona física con credencial)."""
    excel_id = models.PositiveIntegerField(unique=True, null=True, blank=True)

    nombre = models.CharField(max_length=250)
    slug = models.SlugField(max_length=250, unique=True, blank=True)

    # Credencial
    credencial = models.CharField(max_length=200, blank=True,
        help_text='Número(s) de credencial SECTUR')
    idiomas = models.CharField(max_length=200, blank=True)
    acreditacion_vigencia = models.TextField(blank=True,
        help_text='Estado de acreditación y vigencia')

    # Ubicación
    ubicacion_base = models.CharField(max_length=300, blank=True,
        help_text='Base geográfica reportada')
    municipio = models.ForeignKey(
        Municipio, on_delete=models.PROTECT,
        related_name='guias', null=True, blank=True
    )
    municipio_original = models.CharField(max_length=200, blank=True)
    direccion_comercial = models.CharField(max_length=500, blank=True)

    # Contacto
    telefono = models.CharField(max_length=150, blank=True)

    referencia_redes = models.TextField(
    blank=True,
    help_text='Referencia de las redes sociales del guía'
    )

    # Servicio vinculado
    servicio_vinculado = models.ForeignKey(
        Negocio, on_delete=models.SET_NULL,
        related_name='guias', null=True, blank=True
    )
    servicio_vinculado_texto = models.CharField(max_length=250, blank=True)

    # Metadata de investigación
    actividad_redes = models.TextField(blank=True)
    vinculacion_contacto = models.TextField(blank=True)
    observacion_ubicacion = models.TextField(blank=True)
    tipo_fuente = models.CharField(max_length=200, blank=True)
    fecha_revision = models.DateField(null=True, blank=True)

    orden = models.PositiveIntegerField(default=0)
    activo = models.BooleanField(default=True)

    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    redes = GenericRelation(RedSocial, related_query_name='guias')
    fuentes = GenericRelation(Fuente, related_query_name='guias')

    class Meta:
        ordering = ['nombre']
        verbose_name = 'Guía'
        verbose_name_plural = 'Guías'
        indexes = [
            models.Index(fields=['municipio']),
            models.Index(fields=['credencial']),
            models.Index(fields=['slug']),
        ]

    def __str__(self):
        return self.nombre

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = _slug_unico(Guia, slugify_texto(self.nombre), self.pk)
        super().save(*args, **kwargs)

    @property
    def credenciales(self):
        """Devuelve lista de credenciales si hay varias separadas por coma."""
        if not self.credencial:
            return []
        return [c.strip() for c in self.credencial.split(',') if c.strip()]


# ===============================================================
# FOTO DE NEGOCIO
# ===============================================================
class FotoNegocio(models.Model):
    """Foto de un Negocio. Tipos: logo (1), portada (1), galeria (N)."""
    TIPOS = [
        ('logo', 'Logo / Perfil'),
        ('galeria', 'Galería'),
    ]

    negocio = models.ForeignKey(
        Negocio, on_delete=models.CASCADE, related_name='fotos'
    )
    archivo = models.CharField(max_length=300)
    carpeta = models.CharField(max_length=100, default='negocios')
    tipo = models.CharField(max_length=20, choices=TIPOS, default='galeria')
    descripcion = models.CharField(max_length=150, blank=True)
    fecha_subida = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['tipo', '-fecha_subida']
        verbose_name = 'Foto de negocio'
        verbose_name_plural = 'Fotos de negocios'

    def __str__(self):
        return f'{self.get_tipo_display()} · {self.negocio.nombre} — {self.archivo}'

    @property
    def url(self):
        return f'{settings.STATIC_URL}img/{self.carpeta}/{self.archivo}'

    @property
    def existe_en_disco(self):
        ruta = settings.BASE_DIR / 'static' / 'img' / self.carpeta / self.archivo
        return os.path.exists(ruta)

    def eliminar_de_disco(self):
        ruta = settings.BASE_DIR / 'static' / 'img' / self.carpeta / self.archivo
        if ruta.exists():
            try:
                ruta.unlink()
            except Exception:
                pass

    def save(self, *args, **kwargs):
        if self.tipo in ('logo', 'portada'):
            FotoNegocio.objects.filter(
                negocio=self.negocio, tipo=self.tipo
            ).exclude(pk=self.pk).delete()
        super().save(*args, **kwargs)