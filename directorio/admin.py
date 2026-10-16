from django.contrib import admin
from django.contrib.contenttypes.admin import GenericTabularInline
from .models import (
    Municipio, Giro, Negocio, Experiencia, Guia,
    FotoNegocio, RedSocial, Fuente,
)


# ===============================================================
# INLINES GENÉRICOS (Redes y Fuentes)
# ===============================================================
class RedSocialInline(GenericTabularInline):
    model = RedSocial
    extra = 1
    fields = ('tipo', 'usuario', 'referencia', 'actividad', 'orden')
    ct_field = 'content_type'
    ct_fk_field = 'object_id'


class FuenteInline(GenericTabularInline):
    model = Fuente
    extra = 1
    fields = ('url', 'descripcion', 'orden')
    ct_field = 'content_type'
    ct_fk_field = 'object_id'


class FotoNegocioInline(admin.TabularInline):
    model = FotoNegocio
    extra = 1
    fields = ('archivo', 'carpeta', 'tipo', 'descripcion')


# ===============================================================
# ADMIN: MUNICIPIO
# ===============================================================
@admin.register(Municipio)
class MunicipioAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'slug', 'orden')
    list_editable = ('orden',)
    prepopulated_fields = {'slug': ('nombre',)}
    search_fields = ('nombre',)


# ===============================================================
# ADMIN: GIRO
# ===============================================================
@admin.register(Giro)
class GiroAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'slug', 'orden', 'icono')
    list_editable = ('orden',)
    prepopulated_fields = {'slug': ('nombre',)}
    search_fields = ('nombre',)


# ===============================================================
# ADMIN: NEGOCIO
# ===============================================================
@admin.register(Negocio)
class NegocioAdmin(admin.ModelAdmin):
    list_display = (
        'nombre', 'municipio', 'giro', 'telefono',
        'activo', 'destacado'
    )
    list_filter = ('municipio', 'giro', 'activo', 'destacado')
    search_fields = ('nombre', 'direccion', 'descripcion',
                     'municipio_original', 'giro_original')
    list_editable = ('activo', 'destacado')
    prepopulated_fields = {'slug': ('nombre',)}
    inlines = [RedSocialInline, FuenteInline, FotoNegocioInline]
    fieldsets = (
        ('Clasificación', {
            'fields': ('municipio', 'municipio_original',
                       'giro', 'giro_original',
                       'orden', 'destacado', 'activo')
        }),
        ('Datos', {
            'fields': ('nombre', 'slug', 'direccion', 'telefono',
                       'email', 'sitio_web', 'descripcion')
        }),
        ('Ubicación geográfica', {
            'fields': ('latitud', 'longitud'),
            'classes': ('collapse',)
        }),
        ('Metadata de investigación', {
            'fields': ('actividad_redes', 'fecha_revision', 'excel_id'),
            'classes': ('collapse',)
        }),
    )


# ===============================================================
# ADMIN: EXPERIENCIA
# ===============================================================
@admin.register(Experiencia)
class ExperienciaAdmin(admin.ModelAdmin):
    list_display = (
        'nombre', 'operador', 'municipio', 'giro',
        'estado_oferta', 'activo', 'destacado'
    )
    list_filter = ('municipio', 'giro', 'estado_oferta', 'activo', 'destacado')
    search_fields = ('nombre', 'descripcion', 'operador_original',
                     'lugar_realizacion', 'contacto_encargado')
    list_editable = ('activo', 'destacado')
    prepopulated_fields = {'slug': ('nombre',)}
    inlines = [RedSocialInline, FuenteInline]
    fieldsets = (
        ('Identificación', {
            'fields': ('nombre', 'slug', 'excel_id')
        }),
        ('Operador y clasificación', {
            'fields': ('operador', 'operador_original',
                       'municipio', 'municipio_original',
                       'giro', 'giro_original')
        }),
        ('Ubicación', {
            'fields': ('lugar_realizacion', 'direccion_referencia')
        }),
        ('Contacto', {
            'fields': ('telefono', 'contacto_encargado')
        }),
        ('Contenido', {
            'fields': ('descripcion', 'duracion')
        }),
        ('Estado y metadata', {
            'fields': ('estado_oferta', 'referencia_redes',
                       'actividad_redes', 'fecha_revision',
                       'orden', 'destacado', 'activo')
        }),
    )


# ===============================================================
# ADMIN: GUIA
# ===============================================================
@admin.register(Guia)
class GuiaAdmin(admin.ModelAdmin):
    list_display = (
        'nombre', 'credencial', 'idiomas',
        'municipio', 'telefono', 'activo'
    )
    list_filter = ('municipio', 'activo')
    search_fields = ('nombre', 'credencial', 'idiomas',
                     'telefono', 'servicio_vinculado_texto',
                     'municipio_original')
    list_editable = ('activo',)
    prepopulated_fields = {'slug': ('nombre',)}
    inlines = [RedSocialInline, FuenteInline]
    fieldsets = (
        ('Identificación', {
            'fields': ('nombre', 'slug', 'excel_id')
        }),
        ('Credencial', {
            'fields': ('credencial', 'idiomas', 'acreditacion_vigencia')
        }),
        ('Ubicación', {
            'fields': ('municipio', 'municipio_original',
                       'ubicacion_base', 'direccion_comercial')
        }),
        ('Contacto', {
            'fields': ('telefono',)
        }),
        ('Servicio vinculado', {
            'fields': ('servicio_vinculado', 'servicio_vinculado_texto')
        }),
        ('Metadata de investigación', {
            'fields': ('referencia_redes', 'actividad_redes',
                       'vinculacion_contacto', 'observacion_ubicacion',
                       'tipo_fuente', 'fecha_revision'),
            'classes': ('collapse',)
        }),
    )


# ===============================================================
# ADMIN: RED SOCIAL (genérica)
# ===============================================================
@admin.register(RedSocial)
class RedSocialAdmin(admin.ModelAdmin):
    list_display = ('tipo', 'usuario', 'content_object', 'orden')
    list_filter = ('tipo',)
    search_fields = ('usuario', 'referencia', 'actividad')


# ===============================================================
# ADMIN: FUENTE (genérica)
# ===============================================================
@admin.register(Fuente)
class FuenteAdmin(admin.ModelAdmin):
    list_display = ('descripcion', 'url', 'content_object', 'orden')
    search_fields = ('descripcion', 'url')


# ===============================================================
# ADMIN: FOTO NEGOCIO
# ===============================================================
@admin.register(FotoNegocio)
class FotoNegocioAdmin(admin.ModelAdmin):
    list_display = ('negocio', 'archivo', 'tipo', 'fecha_subida')
    list_filter = ('tipo',)
    search_fields = ('negocio__nombre', 'archivo')