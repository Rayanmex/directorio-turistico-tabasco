from django.urls import path
from . import views

app_name = 'directorio'

urlpatterns = [
    # =========================================================
    # LOGIN / LOGOUT (públicas)
    # =========================================================
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # =========================================================
    # ZONA PÚBLICA (requiere login)
    # =========================================================
    path('', views.index, name='index'),
    path('buscar/', views.buscar, name='buscar'),
    path('municipio/<slug:slug>/', views.municipio_detalle, name='municipio_detalle'),
    path('giro/<slug:slug>/', views.giro_detalle, name='giro_detalle'),
    path('negocio/<slug:slug>/', views.negocio_detalle, name='negocio_detalle'),

    # =========================================================
    # DOCUMENTO HTML (público)
    # =========================================================
    path('documento/', views.documento, name='documento'),
    path('documento/municipio/<int:pk>/', views.documento, name='documento_municipio'),
    path('documento/giro/<int:pk>/', views.documento, name='documento_giro'),

    # =========================================================
    # HTML SILENCIOSO PARA PDF (Playwright)
    # =========================================================
    path('pdf-html/', views.documento_pdf_html, name='pdf_html'),
    path('pdf-html/municipio/<int:pk>/', views.documento_pdf_html, name='pdf_html_municipio'),
    path('pdf-html/giro/<int:pk>/', views.documento_pdf_html, name='pdf_html_giro'),

    # =========================================================
    # DESCARGA PDF
    # =========================================================
    path('pdf/', views.documento_pdf, name='pdf_completo'),
    path('pdf/municipio/<int:pk>/', views.documento_pdf, name='pdf_municipio'),
    path('pdf/giro/<int:pk>/', views.documento_pdf, name='pdf_giro'),

    # =========================================================
    # PANEL — Dashboard y listados
    # =========================================================
    path('panel/', views.panel, name='panel'),
    path('panel/giros/', views.panel_giro_lista, name='panel_giro_lista'),
    path('panel/experiencias/', views.panel_experiencia_lista, name='panel_experiencia_lista'),
    path('panel/guias/', views.panel_guia_lista, name='panel_guia_lista'),
    path('panel/imagenes/', views.panel_imagenes, name='panel_imagenes'),

    # Panel por municipio y por giro
    path('panel/municipio/<int:pk>/', views.panel_municipio, name='panel_municipio'),
    path('panel/giro/<int:pk>/', views.panel_giro, name='panel_giro'),

    # =========================================================
    # CREAR NEGOCIO
    # =========================================================
    path('panel/negocio/crear/', views.crear_negocio, name='crear_negocio'),

    # =========================================================
    # ACCIONES SOBRE NEGOCIOS
    # =========================================================
    path('panel/negocio/<int:pk>/subir-foto/', views.subir_foto, name='subir_foto'),
    path('panel/negocio/<int:pk>/nombre/', views.actualizar_nombre_view, name='actualizar_nombre'),
    path('panel/negocio/<int:pk>/direccion/', views.actualizar_direccion_view, name='actualizar_direccion'),
    path('panel/negocio/<int:pk>/telefono/', views.actualizar_telefono_view, name='actualizar_telefono'),
    path('panel/negocio/<int:pk>/descripcion/', views.actualizar_descripcion_view, name='actualizar_descripcion'),
    path('panel/negocio/<int:pk>/municipio/', views.actualizar_municipio_view, name='actualizar_municipio'),
    path('panel/negocio/<int:pk>/giro/', views.actualizar_giro_view, name='actualizar_giro'),
    path('panel/negocio/<int:pk>/toggle-activo/', views.toggle_activo_view, name='toggle_activo'),
    path('panel/negocio/<int:pk>/toggle-destacado/', views.toggle_destacado_view, name='toggle_destacado'),
    path('panel/negocio/<int:pk>/eliminar/', views.eliminar_negocio_view, name='eliminar_negocio'),
    path('panel/negocio/<int:pk>/mover/', views.mover_negocio, name='mover_negocio'),

    # =========================================================
    # REDES SOCIALES
    # =========================================================
    path('panel/negocio/<int:pk>/redes/agregar/', views.agregar_red_view, name='agregar_red'),
    path('panel/red/<int:pk>/eliminar/', views.eliminar_red_view, name='eliminar_red'),

    # =========================================================
    # FOTOS
    # =========================================================
    path('panel/foto/<int:pk>/eliminar/', views.eliminar_foto_view, name='eliminar_foto'),
    path('panel/foto/<int:pk>/principal/', views.marcar_principal_view, name='marcar_principal'),

    # =========================================================
    # MOVER ORDEN (municipio, giro)
    # =========================================================
    path('panel/municipio/<int:pk>/mover/', views.mover_municipio, name='mover_municipio'),
    path('panel/giro/<int:pk>/mover/', views.mover_giro, name='mover_giro'),

    # =========================================================
    # GENERAR PDF RÁPIDO (guarda en disco)
    # =========================================================
    path('panel/generar-pdf/', views.generar_pdf_rapido, name='generar_pdf_rapido'),
    path('panel/generar-pdf/municipio/<int:pk>/', views.generar_pdf_rapido, name='generar_pdf_rapido_municipio'),
    path('panel/generar-pdf/giro/<int:pk>/', views.generar_pdf_rapido, name='generar_pdf_rapido_giro'),

    # =========================================================
    # EDITOR DE IMÁGENES DEL DOCUMENTO
    # =========================================================
    path('panel/imagenes/<str:clave>/subir/', views.subir_imagen_documento, name='subir_imagen_documento'),
    path('panel/imagenes/<str:clave>/restaurar/', views.restaurar_imagen_documento, name='restaurar_imagen_documento'),

    # =========================================================
    # EJECUTAR SCRAPERS
    # =========================================================
    path('panel/scraper/<str:tipo>/', views.ejecutar_scraper, name='ejecutar_scraper'),
]