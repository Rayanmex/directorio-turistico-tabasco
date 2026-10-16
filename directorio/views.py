import os
import re
import subprocess
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Count
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST

from .models import (
    Municipio, Giro, Negocio, Experiencia, Guia,
    FotoNegocio, RedSocial, Fuente,
)


# ===============================================================
# HELPERS
# ===============================================================
def _volver(request, fallback='directorio:panel'):
    """Redirige a la página anterior, o al panel si no hay referer."""
    return redirect(request.META.get('HTTP_REFERER', fallback))


def _limpiar_telefono(txt: str) -> str:
    """Deja solo dígitos, +, -, (, ), espacios, /. Máx 30 chars."""
    if not txt:
        return ''
    return re.sub(r'[^0-9+\-()\s/]', '', txt).strip()[:30]


# ===============================================================
# LOGIN / LOGOUT (públicas)
# ===============================================================
@csrf_protect
def login_view(request):
    """Pantalla de login."""
    # Si ya está logueado, redirigir al index
    if request.user.is_authenticated:
        return redirect('directorio:index')

    error = None

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        next_url = request.POST.get('next', request.GET.get('next', '/'))

        user = authenticate(request, username=username, password=password)
        if user is not None and user.is_active:
            login(request, user)
            # Evitar open redirect: solo URLs relativas
            if not next_url or not next_url.startswith('/'):
                next_url = '/'
            return redirect(next_url)
        else:
            error = 'Usuario o contraseña incorrectos.'

    return render(request, 'directorio/login.html', {
        'error': error,
        'next': request.GET.get('next', '/'),
    })


def logout_view(request):
    """Cerrar sesión."""
    logout(request)
    return redirect('directorio:login')


# ===============================================================
# ZONA PÚBLICA (protegida con login)
# ===============================================================
@login_required
def index(request):
    """Catálogo público de prestadores con filtros."""
    q = request.GET.get('q', '').strip()
    municipio_slug = request.GET.get('municipio', '').strip()
    giro_slug = request.GET.get('giro', '').strip()
    solo_con_foto = request.GET.get('con_foto') == '1'
    orden = request.GET.get('orden', 'relevancia')

    # Query base
    negocios = Negocio.objects.filter(activo=True).select_related(
        'municipio', 'giro'
    ).prefetch_related('fotos')

    # Aplicar filtros
    if q:
        negocios = negocios.filter(
            Q(nombre__icontains=q) |
            Q(descripcion__icontains=q) |
            Q(direccion__icontains=q) |
            Q(municipio__nombre__icontains=q) |
            Q(giro__nombre__icontains=q)
        )

    if municipio_slug:
        negocios = negocios.filter(municipio__slug=municipio_slug)

    if giro_slug:
        negocios = negocios.filter(giro__slug=giro_slug)

    if solo_con_foto:
        negocios = negocios.filter(fotos__isnull=False).distinct()

    # Orden
    if orden == 'nombre':
        negocios = negocios.order_by('nombre')
    elif orden == 'municipio':
        negocios = negocios.order_by('municipio__orden', 'nombre')
    else:
        negocios = negocios.order_by('-destacado', 'municipio__orden', 'nombre')

    negocios = negocios[:300]

    # Datos para los selects de filtros
    municipios = Municipio.objects.annotate(
        total=Count('negocios', filter=Q(negocios__activo=True))
    ).order_by('orden', 'nombre')

    giros = Giro.objects.annotate(
        total=Count('negocios', filter=Q(negocios__activo=True))
    ).order_by('orden', 'nombre')

    total_resultados = len(negocios)
    total_general = Negocio.objects.filter(activo=True).count()

    return render(request, 'directorio/index.html', {
        'negocios': negocios,
        'municipios': municipios,
        'giros': giros,
        'q': q,
        'municipio_sel': municipio_slug,
        'giro_sel': giro_slug,
        'solo_con_foto': solo_con_foto,
        'orden': orden,
        'total_resultados': total_resultados,
        'total_general': total_general,
        'seccion': 'inicio',
    })


@login_required
def municipio_detalle(request, slug):
    """Negocios de un municipio, agrupados por giro."""
    municipio = get_object_or_404(Municipio, slug=slug)

    negocios = Negocio.objects.filter(
        municipio=municipio, activo=True
    ).select_related('giro').prefetch_related('fotos', 'redes')

    por_giro = {}
    for n in negocios:
        por_giro.setdefault(n.giro, []).append(n)

    return render(request, 'directorio/municipio_detalle.html', {
        'municipio': municipio,
        'por_giro': por_giro,
    })


@login_required
def giro_detalle(request, slug):
    """Negocios de un giro, agrupados por municipio."""
    giro = get_object_or_404(Giro, slug=slug)

    negocios = Negocio.objects.filter(
        giro=giro, activo=True
    ).select_related('municipio').prefetch_related('fotos', 'redes')

    por_municipio = {}
    for n in negocios:
        por_municipio.setdefault(n.municipio, []).append(n)

    return render(request, 'directorio/giro_detalle.html', {
        'giro': giro,
        'por_municipio': por_municipio,
    })


@login_required
def negocio_detalle(request, slug):
    """Ficha pública de un negocio."""
    negocio = get_object_or_404(
        Negocio.objects.select_related('municipio', 'giro')
                       .prefetch_related('fotos', 'redes'),
        slug=slug, activo=True
    )
    return render(request, 'directorio/negocio_detalle.html', {
        'negocio': negocio,
    })


@login_required
def buscar(request):
    """Búsqueda pública por nombre, giro, municipio o descripción."""
    q = request.GET.get('q', '').strip()
    resultados = []
    if q:
        resultados = Negocio.objects.filter(activo=True).filter(
            Q(nombre__icontains=q) |
            Q(direccion__icontains=q) |
            Q(descripcion__icontains=q) |
            Q(municipio__nombre__icontains=q) |
            Q(giro__nombre__icontains=q)
        ).select_related('municipio', 'giro').prefetch_related('fotos')[:200]

    return render(request, 'directorio/buscar.html', {
        'q': q,
        'resultados': resultados,
    })


# ===============================================================
# PANEL (protegido con login)
# ===============================================================
@login_required
def panel(request):
    """Dashboard del panel administrativo."""
    municipios = Municipio.objects.prefetch_related(
        'negocios__fotos', 'negocios__giro'
    ).annotate(total=Count('negocios'))
    giros = Giro.objects.annotate(total=Count('negocios'))

    q = request.GET.get('q', '').strip()
    resultados = []
    if q:
        resultados = Negocio.objects.filter(
            Q(nombre__icontains=q) |
            Q(direccion__icontains=q) |
            Q(descripcion__icontains=q) |
            Q(municipio__nombre__icontains=q) |
            Q(giro__nombre__icontains=q)
        ).select_related('municipio', 'giro').prefetch_related('fotos')[:100]

    total_negocios = Negocio.objects.count()
    total_activos = Negocio.objects.filter(activo=True).count()
    total_con_foto = sum(1 for n in Negocio.objects.all() if n.logo_url)
    total_sin_foto = total_negocios - total_con_foto

    return render(request, 'directorio/panel.html', {
        'municipios': municipios,
        'giros': giros,
        'q': q,
        'resultados': resultados,
        'total_negocios': total_negocios,
        'total_activos': total_activos,
        'total_con_foto': total_con_foto,
        'total_sin_foto': total_sin_foto,
        'seccion': 'panel',
    })


@login_required
def panel_municipio(request, pk):
    """Negocios de un municipio, agrupados por giro."""
    municipio = get_object_or_404(Municipio, pk=pk)
    negocios = Negocio.objects.filter(
        municipio=municipio
    ).select_related('giro').prefetch_related('fotos', 'redes')

    por_giro = {}
    for n in negocios:
        por_giro.setdefault(n.giro, []).append(n)

    return render(request, 'directorio/panel_municipio.html', {
        'municipio': municipio,
        'por_giro': por_giro,
        'giros': Giro.objects.all().order_by('orden', 'nombre'),
    })


@login_required
def panel_giro(request, pk):
    """Negocios de un giro, agrupados por municipio."""
    giro = get_object_or_404(Giro, pk=pk)
    negocios = Negocio.objects.filter(
        giro=giro
    ).select_related('municipio').prefetch_related('fotos', 'redes')

    por_municipio = {}
    for n in negocios:
        por_municipio.setdefault(n.municipio, []).append(n)

    return render(request, 'directorio/panel_giro.html', {
        'giro': giro,
        'por_municipio': por_municipio,
        'municipios': Municipio.objects.all().order_by('orden', 'nombre'),
    })


# ===============================================================
# ACCIONES SOBRE NEGOCIOS (protegidas)
# ===============================================================
@login_required
@require_POST
def actualizar_nombre_view(request, pk):
    negocio = get_object_or_404(Negocio, pk=pk)
    nuevo = request.POST.get('nombre', '').strip()
    if nuevo:
        negocio.nombre = nuevo
        negocio.slug = ''
        negocio.save()
        messages.success(request, f'Nombre actualizado a "{nuevo}".')
    else:
        messages.error(request, 'El nombre no puede estar vacío.')
    return _volver(request)


@login_required
@require_POST
def actualizar_direccion_view(request, pk):
    negocio = get_object_or_404(Negocio, pk=pk)
    negocio.direccion = request.POST.get('direccion', '').strip()
    negocio.save()
    messages.success(request, f'Dirección actualizada para {negocio.nombre}.')
    return _volver(request)


@login_required
@require_POST
def actualizar_telefono_view(request, pk):
    negocio = get_object_or_404(Negocio, pk=pk)
    negocio.telefono = _limpiar_telefono(request.POST.get('telefono', ''))
    negocio.save()
    messages.success(request, f'Teléfono actualizado para {negocio.nombre}.')
    return _volver(request)


@login_required
@require_POST
def actualizar_descripcion_view(request, pk):
    negocio = get_object_or_404(Negocio, pk=pk)
    negocio.descripcion = request.POST.get('descripcion', '').strip()
    negocio.save()
    messages.success(request, f'Descripción actualizada para {negocio.nombre}.')
    return _volver(request)


@login_required
@require_POST
def actualizar_municipio_view(request, pk):
    negocio = get_object_or_404(Negocio, pk=pk)
    mun_id = request.POST.get('municipio_id')
    if mun_id:
        negocio.municipio = get_object_or_404(Municipio, pk=mun_id)
        negocio.save()
        messages.success(request, f'Municipio actualizado para {negocio.nombre}.')
    return _volver(request)


@login_required
@require_POST
def actualizar_giro_view(request, pk):
    negocio = get_object_or_404(Negocio, pk=pk)
    giro_id = request.POST.get('giro_id')
    if giro_id:
        negocio.giro = get_object_or_404(Giro, pk=giro_id)
        negocio.save()
        messages.success(request, f'Giro actualizado para {negocio.nombre}.')
    return _volver(request)


# ===============================================================
# REDES SOCIALES (protegidas)
# ===============================================================
@login_required
@require_POST
def agregar_red_view(request, pk):
    negocio = get_object_or_404(Negocio, pk=pk)
    tipo = request.POST.get('tipo')
    usuario = request.POST.get('usuario', '').strip()
    if tipo and usuario:
        RedSocial.objects.create(
            content_object=negocio,
            tipo=tipo,
            usuario=usuario,
        )
        messages.success(request, f'Red {tipo} agregada a {negocio.nombre}.')
    else:
        messages.error(request, 'Faltan datos de la red social.')
    return _volver(request)


@login_required
@require_POST
def eliminar_red_view(request, pk):
    red = get_object_or_404(RedSocial, pk=pk)
    nombre = red.content_object.nombre if red.content_object else '—'
    red.delete()
    messages.success(request, f'Red eliminada de {nombre}.')
    return _volver(request)


# ===============================================================
# FOTOS (protegidas)
# ===============================================================
@login_required
@require_POST
def subir_foto(request, pk):
    negocio = get_object_or_404(Negocio, pk=pk)
    archivo = request.FILES.get('foto')
    tipo = request.POST.get('tipo', 'galeria')

    if tipo not in ('logo', 'galeria'):
        tipo = 'galeria'

    if not archivo:
        messages.error(request, 'No enviaste archivo.')
        return _volver(request)

    ext = Path(archivo.name).suffix.lower()
    if ext not in ('.png', '.jpg', '.jpeg', '.webp', '.gif'):
        messages.error(request, 'Formato no permitido. Usa JPG, PNG, WEBP o GIF.')
        return _volver(request)

    carpeta = settings.BASE_DIR / 'static' / 'img' / 'negocios'
    carpeta.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    nombre_archivo = f'{negocio.slug}_{tipo}_{ts}{ext}'

    with open(carpeta / nombre_archivo, 'wb+') as f:
        for chunk in archivo.chunks():
            f.write(chunk)

    FotoNegocio.objects.create(
        negocio=negocio,
        archivo=nombre_archivo,
        carpeta='negocios',
        tipo=tipo,
    )
    messages.success(request, f'{tipo.capitalize()} agregada a {negocio.nombre}.')
    return _volver(request)


@login_required
@require_POST
def eliminar_foto_view(request, pk):
    foto = get_object_or_404(FotoNegocio, pk=pk)
    negocio = foto.negocio
    foto.eliminar_de_disco()
    foto.delete()
    messages.success(request, f'Foto eliminada de {negocio.nombre}.')
    return _volver(request)


@login_required
@require_POST
def marcar_principal_view(request, pk):
    """Convierte esta foto en el LOGO del negocio."""
    foto = get_object_or_404(FotoNegocio, pk=pk)
    foto.tipo = 'logo'
    foto.save()
    messages.success(request, f'{foto.negocio.nombre}: nuevo logo.')
    return _volver(request)


# ===============================================================
# MOVER ORDEN (protegidas)
# ===============================================================
@login_required
@require_POST
def mover_municipio(request, pk):
    return _mover(Municipio, pk, request)


@login_required
@require_POST
def mover_giro(request, pk):
    return _mover(Giro, pk, request)


@login_required
@require_POST
def mover_negocio(request, pk):
    return _mover(Negocio, pk, request)


def _mover(Modelo, pk, request):
    obj = get_object_or_404(Modelo, pk=pk)
    direccion = request.POST.get('direccion')
    hermanos = list(Modelo.objects.all().order_by('orden', 'nombre'))
    idx = next((i for i, x in enumerate(hermanos) if x.pk == obj.pk), None)
    if idx is None:
        return _volver(request)

    if direccion == 'arriba' and idx > 0:
        otro = hermanos[idx - 1]
    elif direccion == 'abajo' and idx < len(hermanos) - 1:
        otro = hermanos[idx + 1]
    else:
        return _volver(request)

    obj.orden, otro.orden = otro.orden, obj.orden
    obj.save()
    otro.save()
    return _volver(request)


# ===============================================================
# TOGGLE ACTIVO / DESTACADO / ELIMINAR (protegidas)
# ===============================================================
@login_required
@require_POST
def toggle_activo_view(request, pk):
    negocio = get_object_or_404(Negocio, pk=pk)
    negocio.activo = not negocio.activo
    negocio.save()
    messages.success(
        request,
        f'{negocio.nombre} ahora está {"activo" if negocio.activo else "oculto"}.'
    )
    return _volver(request)


@login_required
@require_POST
def toggle_destacado_view(request, pk):
    negocio = get_object_or_404(Negocio, pk=pk)
    negocio.destacado = not negocio.destacado
    negocio.save()
    messages.success(
        request,
        f'{negocio.nombre} {"es" if negocio.destacado else "ya no es"} destacado.'
    )
    return _volver(request)


@login_required
@require_POST
def eliminar_negocio_view(request, pk):
    negocio = get_object_or_404(Negocio, pk=pk)
    nombre = negocio.nombre
    negocio.delete()
    messages.success(request, f'Negocio "{nombre}" eliminado.')
    return redirect('directorio:panel')


# ===============================================================
# CREAR NEGOCIO (protegida)
# ===============================================================
@login_required
@require_POST
def crear_negocio(request):
    nombre = request.POST.get('nombre', '').strip()
    municipio_id = request.POST.get('municipio_id')
    giro_id = request.POST.get('giro_id')

    if not (nombre and municipio_id and giro_id):
        messages.error(request, 'Faltan datos: nombre, municipio y giro son obligatorios.')
        return _volver(request)

    municipio = get_object_or_404(Municipio, pk=municipio_id)
    giro = get_object_or_404(Giro, pk=giro_id)

    descripcion = (
        request.POST.get('descripcion') or
        request.POST.get('experiencia') or
        ''
    ).strip()

    negocio = Negocio.objects.create(
        nombre=nombre,
        municipio=municipio,
        giro=giro,
        direccion=request.POST.get('direccion', '').strip(),
        telefono=_limpiar_telefono(request.POST.get('telefono', '')),
        descripcion=descripcion,
    )

    # Redes sociales
    tipos = request.POST.getlist('red_tipo')
    usuarios = request.POST.getlist('red_usuario')
    tipos_vistos = set()
    for tipo, usuario in zip(tipos, usuarios):
        tipo = (tipo or '').strip()
        usuario = (usuario or '').strip()
        if tipo and usuario and tipo not in tipos_vistos:
            RedSocial.objects.create(
                content_object=negocio,
                tipo=tipo,
                usuario=usuario,
            )
            tipos_vistos.add(tipo)

    # Fotos
    carpeta = settings.BASE_DIR / 'static' / 'img' / 'negocios'
    carpeta.mkdir(parents=True, exist_ok=True)

    EXTENSIONES_OK = ('.png', '.jpg', '.jpeg', '.webp', '.gif')

    def _guardar(archivo, tipo):
        ext = Path(archivo.name).suffix.lower()
        if ext not in EXTENSIONES_OK:
            return False
        ts = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        nombre_archivo = f'{negocio.slug}_{tipo}_{ts}{ext}'
        with open(carpeta / nombre_archivo, 'wb+') as f:
            for chunk in archivo.chunks():
                f.write(chunk)
        FotoNegocio.objects.create(
            negocio=negocio,
            archivo=nombre_archivo,
            carpeta='negocios',
            tipo=tipo,
        )
        return True

    logo = request.FILES.get('logo')
    if logo:
        _guardar(logo, 'logo')

    for archivo in request.FILES.getlist('fotos') or []:
        _guardar(archivo, 'galeria')

    total_fotos = negocio.fotos.count()
    messages.success(
        request,
        f'Negocio "{negocio.nombre}" creado con '
        f'{negocio.redes.count()} red(es) y {total_fotos} foto(s).'
    )
    return redirect('directorio:panel_municipio', pk=municipio.pk)


# ===============================================================
# LISTADOS GENERALES DEL PANEL (protegidas)
# ===============================================================
@login_required
def panel_giro_lista(request):
    giros = Giro.objects.annotate(total=Count('negocios'))
    return render(request, 'directorio/panel_giro_lista.html', {
        'giros': giros,
        'seccion': 'giros',
    })


@login_required
def panel_experiencia_lista(request):
    q = request.GET.get('q', '').strip()
    experiencias = Experiencia.objects.select_related('operador', 'municipio', 'giro')
    if q:
        experiencias = experiencias.filter(
            Q(nombre__icontains=q) |
            Q(descripcion__icontains=q) |
            Q(operador_original__icontains=q)
        )
    experiencias = experiencias[:500]
    return render(request, 'directorio/panel_experiencia_lista.html', {
        'experiencias': experiencias,
        'q': q,
        'seccion': 'experiencias',
    })


@login_required
def panel_guia_lista(request):
    q = request.GET.get('q', '').strip()
    guias = Guia.objects.select_related('municipio', 'servicio_vinculado')
    if q:
        guias = guias.filter(
            Q(nombre__icontains=q) |
            Q(credencial__icontains=q) |
            Q(idiomas__icontains=q)
        )
    guias = guias[:500]
    return render(request, 'directorio/panel_guia_lista.html', {
        'guias': guias,
        'q': q,
        'seccion': 'guias',
    })


# ===============================================================
# DOCUMENTO HTML (protegidas)
# ===============================================================
def _construir_paginas(negocios, modo):
    agrupado = {}
    for n in negocios:
        if modo == 'municipio':
            g1, g2 = n.municipio, n.giro
        elif modo == 'giro':
            g1, g2 = n.giro, n.municipio
        else:
            g1, g2 = n.municipio, n.giro

        agrupado.setdefault(g1, {}).setdefault(g2, []).append(n)

    paginas = []
    for g1, subgrupos in agrupado.items():
        for g2, lista in subgrupos.items():
            for i in range(0, len(lista), 3):
                bloque = lista[i:i+3]
                paginas.append({
                    'grupo_principal': g1,
                    'subgrupo': g2,
                    'negocios': bloque,
                    'es_continuacion': i > 0,
                })
    return paginas


@login_required
def documento(request, pk=None, tipo=None):
    """Documento completo o filtrado."""
    tipo = tipo or request.resolver_match.url_name

    if 'municipio' in tipo and pk:
        municipio = get_object_or_404(Municipio, pk=pk)
        negocios = Negocio.objects.filter(
            municipio=municipio, activo=True
        ).select_related('giro').prefetch_related('fotos', 'redes')
        titulo = f'Municipio: {municipio.nombre}'
        modo = 'municipio'
    elif 'giro' in tipo and pk:
        giro = get_object_or_404(Giro, pk=pk)
        negocios = Negocio.objects.filter(
            giro=giro, activo=True
        ).select_related('municipio').prefetch_related('fotos', 'redes')
        titulo = f'Giro: {giro.nombre}'
        modo = 'giro'
    else:
        negocios = Negocio.objects.filter(
            activo=True
        ).select_related('municipio', 'giro').prefetch_related('fotos', 'redes')
        titulo = 'Directorio Turístico'
        modo = 'completo'

    paginas = _construir_paginas(negocios, modo)
    return render(request, 'directorio/documento.html', {
        'paginas': paginas,
        'titulo': titulo,
        'modo': modo,
        'mostrar_portada': modo == 'completo',
    })


@login_required
def documento_pdf_html(request, pk=None):
    """Versión silenciosa para generar el PDF."""
    if pk:
        if 'municipio' in request.resolver_match.url_name:
            municipio = get_object_or_404(Municipio, pk=pk)
            negocios = Negocio.objects.filter(
                municipio=municipio, activo=True
            ).select_related('giro').prefetch_related('fotos', 'redes')
            modo = 'municipio'
        else:
            giro = get_object_or_404(Giro, pk=pk)
            negocios = Negocio.objects.filter(
                giro=giro, activo=True
            ).select_related('municipio').prefetch_related('fotos', 'redes')
            modo = 'giro'
    else:
        negocios = Negocio.objects.filter(
            activo=True
        ).select_related('municipio', 'giro').prefetch_related('fotos', 'redes')
        modo = 'completo'

    paginas = _construir_paginas(negocios, modo)
    return render(request, 'directorio/documento.html', {
        'paginas': paginas,
        'modo': modo,
        'pdf_mode': True,
        'mostrar_portada': modo == 'completo',
    })


# ===============================================================
# DESCARGA PDF (protegidas)
# ===============================================================
@login_required
def documento_pdf(request, pk=None):
    """Genera el PDF visitando la URL real de Django (Playwright)."""
    from .services.pdf import pdf_desde_url

    url_name = request.resolver_match.url_name
    if 'municipio' in url_name and pk:
        path = reverse('directorio:pdf_html_municipio', args=[pk])
        nombre = f'directorio_municipio_{pk}.pdf'
    elif 'giro' in url_name and pk:
        path = reverse('directorio:pdf_html_giro', args=[pk])
        nombre = f'directorio_giro_{pk}.pdf'
    else:
        path = reverse('directorio:pdf_html')
        nombre = 'directorio_completo.pdf'

    url_pdf = request.build_absolute_uri(path)
    pdf_bytes = pdf_desde_url(url_pdf)

    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="{nombre}"'
    return response


@login_required
@require_POST
def generar_pdf_rapido(request, pk=None):
    """Genera el PDF y lo guarda en disco."""
    from .services.pdf import pdf_desde_url

    BASE_URL = 'http://127.0.0.1:8000'
    url_name = request.resolver_match.url_name

    if 'municipio' in url_name and pk:
        municipio = get_object_or_404(Municipio, pk=pk)
        path = reverse('directorio:pdf_html_municipio', args=[pk])
        salida = Path(settings.BASE_DIR) / f'directorio_{municipio.slug}.pdf'
        volver_a = reverse('directorio:panel_municipio', args=[pk])
    elif 'giro' in url_name and pk:
        giro = get_object_or_404(Giro, pk=pk)
        path = reverse('directorio:pdf_html_giro', args=[pk])
        salida = Path(settings.BASE_DIR) / f'directorio_{giro.slug}.pdf'
        volver_a = reverse('directorio:panel_giro', args=[pk])
    else:
        path = reverse('directorio:pdf_html')
        salida = Path(settings.BASE_DIR) / 'directorio_completo.pdf'
        volver_a = reverse('directorio:panel')

    url_pdf = f'{BASE_URL}{path}'

    try:
        pdf_bytes = pdf_desde_url(url_pdf)
        salida.write_bytes(pdf_bytes)
        messages.success(
            request,
            f'PDF generado: {salida.name} ({len(pdf_bytes)/1024:.0f} KB)'
        )
    except Exception as e:
        messages.error(request, f'Error al generar el PDF: {e}')

    return redirect(volver_a)


# ===============================================================
# EDITOR DE IMÁGENES DEL DOCUMENTO (protegidas)
# ===============================================================
IMAGENES_EDITABLES = {
    'portada': {
        'nombre': 'Portada',
        'descripcion': 'Primera hoja del PDF',
        'archivo': 'portada.jpg',
        'preview': 'img/portada.jpg',
    },
    'plantilla': {
        'nombre': 'Plantilla',
        'descripcion': 'Header y footer de cada hoja',
        'archivo': 'plantilla.png',
        'preview': 'img/plantilla.png',
    },
    'textura': {
        'nombre': 'Textura de fondo',
        'descripcion': 'Textura detrás de cada hoja',
        'archivo': 'textura.jpg',
        'preview': 'img/textura.jpg',
    },
    'cuadrito': {
        'nombre': 'Cuadrito',
        'descripcion': 'Marco alrededor de cada foto',
        'archivo': 'cuadrito.png',
        'preview': 'img/cuadrito.png',
    },
}


@login_required
def panel_imagenes(request):
    imagenes = []
    for clave, info in IMAGENES_EDITABLES.items():
        ruta = settings.BASE_DIR / 'static' / 'img' / info['archivo']
        imagenes.append({
            'clave': clave,
            'info': info,
            'existe': ruta.exists(),
            'url': f'{settings.STATIC_URL}{info["preview"]}',
            'peso_kb': round(ruta.stat().st_size / 1024, 1) if ruta.exists() else 0,
        })
    return render(request, 'directorio/panel_imagenes.html', {'imagenes': imagenes})


@login_required
@require_POST
def subir_imagen_documento(request, clave):
    import shutil
    if clave not in IMAGENES_EDITABLES:
        messages.error(request, f'Imagen no válida: {clave}')
        return redirect('directorio:panel_imagenes')

    info = IMAGENES_EDITABLES[clave]
    archivo = request.FILES.get('imagen')
    if not archivo:
        messages.error(request, 'No enviaste archivo.')
        return redirect('directorio:panel_imagenes')

    destino = settings.BASE_DIR / 'static' / 'img' / info['archivo']
    if destino.exists():
        respaldo_dir = settings.BASE_DIR / 'static' / 'img' / '_respaldo_imagenes'
        respaldo_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        shutil.copy2(destino, respaldo_dir / f'{destino.stem}_{ts}{destino.suffix}')

    with open(destino, 'wb+') as f:
        for chunk in archivo.chunks():
            f.write(chunk)

    messages.success(request, f'Imagen "{info["nombre"]}" actualizada.')
    return redirect('directorio:panel_imagenes')


@login_required
@require_POST
def restaurar_imagen_documento(request, clave):
    import shutil
    if clave not in IMAGENES_EDITABLES:
        messages.error(request, f'Imagen no válida: {clave}')
        return redirect('directorio:panel_imagenes')

    info = IMAGENES_EDITABLES[clave]
    destino = settings.BASE_DIR / 'static' / 'img' / info['archivo']
    respaldo_dir = settings.BASE_DIR / 'static' / 'img' / '_respaldo_imagenes'

    if not respaldo_dir.exists():
        messages.warning(request, 'No hay respaldos disponibles.')
        return redirect('directorio:panel_imagenes')

    respaldos = sorted(respaldo_dir.glob(f'{destino.stem}_*{destino.suffix}'), reverse=True)
    if not respaldos:
        messages.warning(request, 'No hay respaldos de esta imagen.')
        return redirect('directorio:panel_imagenes')

    shutil.copy2(respaldos[0], destino)
    messages.success(request, f'Imagen "{info["nombre"]}" restaurada.')
    return redirect('directorio:panel_imagenes')


# ===============================================================
# EJECUTAR SCRAPERS (protegida)
# ===============================================================
SCRIPTS_DISPONIBLES = {
    'facebook': {
        'nombre': 'Facebook',
        'script': 'scraper_async.py',
        'args': ['--todos', '--headless'],
    },
    'instagram': {
        'nombre': 'Instagram',
        'script': 'scraper_ig.py',
        'args': ['--todos', '--headless'],
    },
}


@login_required
@require_POST
def ejecutar_scraper(request, tipo):
    """Ejecuta el scraper de Facebook o Instagram en background."""
    if tipo not in SCRIPTS_DISPONIBLES:
        messages.error(request, f'Scraper no válido: {tipo}')
        return _volver(request)

    info = SCRIPTS_DISPONIBLES[tipo]
    script_path = settings.BASE_DIR / info['script']

    if not script_path.exists():
        messages.error(request, f'No se encontró el script: {info["script"]}')
        return _volver(request)

    # Verificar Chrome cerrado antes de lanzar
    try:
        result = subprocess.run(
            ['tasklist', '/FI', 'IMAGENAME eq chrome.exe'],
            capture_output=True, text=True, timeout=5
        )
        if 'chrome.exe' in result.stdout.lower():
            messages.error(
                request,
                'Chrome está abierto. Ciérralo completamente antes de ejecutar el scraper.'
            )
            return _volver(request)
    except Exception:
        pass

    try:
        python_exe = settings.BASE_DIR / 'venv' / 'Scripts' / 'python.exe'
        if not python_exe.exists():
            python_exe = 'python'

        cmd = [str(python_exe), str(script_path)] + info['args']

        subprocess.Popen(
            cmd,
            cwd=str(settings.BASE_DIR),
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )

        messages.success(
            request,
            f'Scraper de {info["nombre"]} iniciado en una nueva ventana. '
            f'Puede tardar varios minutos. Revisa la ventana negra para ver el progreso.'
        )
    except Exception as e:
        messages.error(request, f'Error al ejecutar scraper: {e}')

    return _volver(request)