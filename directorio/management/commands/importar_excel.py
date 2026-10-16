"""
Importa el Excel del Directorio Turístico de Tabasco.

Uso:
    python manage.py importar_excel "DIRECTORIO TURISTICO.xlsx" --dry-run
    python manage.py importar_excel "DIRECTORIO TURISTICO.xlsx"

Opciones:
    --dry-run    No escribe en DB, solo reporta qué haría
    --hoja N     Importar solo una hoja (1=Directorio, 2=Experiencias, 3=Ofertas, 4=Guías)

Lógica de duplicados:
    - Si encuentra una experiencia con el mismo nombre (normalizado),
      ACTUALIZA los campos vacíos + AGREGA redes y fuentes nuevas.
    - Igual para Negocios y Guías.
"""
import re
import unicodedata
from datetime import datetime, date
from pathlib import Path
from urllib.parse import urlparse

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

try:
    from openpyxl import load_workbook
except ImportError:
    raise CommandError('Falta openpyxl. Instala con: pip install openpyxl')

from directorio.models import (
    Municipio, Giro, Negocio, Experiencia, Guia,
    RedSocial, Fuente,
)


# ===============================================================
# NORMALIZACIÓN
# ===============================================================
def normalizar(texto) -> str:
    if not texto:
        return ''
    texto = unicodedata.normalize('NFKD', str(texto))
    texto = texto.encode('ascii', 'ignore').decode('ascii').lower()
    texto = re.sub(r'[^a-z0-9\s]', '', texto)
    return re.sub(r'\s+', ' ', texto).strip()


MUNICIPIOS_MAP = {
    'balancan': 'Balancán',
    'cardenas': 'Cárdenas',
    'centla': 'Centla',
    'centro': 'Centro',
    'comalcalco': 'Comalcalco',
    'cunduacan': 'Cunduacán',
    'emiliano zapata': 'Emiliano Zapata',
    'huimanguillo': 'Huimanguillo',
    'jalapa': 'Jalapa',
    'jalpa de mendez': 'Jalpa de Méndez',
    'jonuta': 'Jonuta',
    'macuspana': 'Macuspana',
    'nacajuca': 'Nacajuca',
    'paraiso': 'Paraíso',
    'tacotalpa': 'Tacotalpa',
    'teapa': 'Teapa',
    'tenosique': 'Tenosique',
    'vhsa': 'Centro',
    'villahermosa': 'Centro',
    'frontera': 'Centla',
    'central': 'Centro',
    'canducan': 'Cunduacán',
}


def parsear_municipio(valor):
    if not valor:
        return None, ''
    original = str(valor).strip()
    clave = normalizar(original)
    # Detectar el primer municipio mencionado
    for k, canonico in MUNICIPIOS_MAP.items():
        if k in clave:
            try:
                return Municipio.objects.get(nombre=canonico), original
            except Municipio.DoesNotExist:
                return None, original
    return None, original


def parsear_giro(valor):
    if not valor:
        return None, ''
    original = str(valor).strip()
    clave = normalizar(original)
    # Búsqueda exacta
    for g in Giro.objects.all():
        if normalizar(g.nombre) == clave:
            return g, original
    # Búsqueda parcial (primera palabra significativa)
    for g in Giro.objects.all():
        if normalizar(g.nombre) in clave:
            return g, original
    return None, original


# ===============================================================
# REDES SOCIALES
# ===============================================================
DOMINIOS_REDES = {
    'facebook.com': 'facebook',
    'fb.com': 'facebook',
    'instagram.com': 'instagram',
    'tiktok.com': 'tiktok',
    'wa.me': 'whatsapp',
    'whatsapp.com': 'whatsapp',
    'youtube.com': 'youtube',
    'youtu.be': 'youtube',
    'twitter.com': 'twitter',
    'x.com': 'twitter',
}


def detectar_red(url):
    if not url:
        return None, None
    url = url.strip()
    if not url.startswith('http'):
        return None, None
    try:
        dominio = urlparse(url).netloc.lower().replace('www.', '')
        for d, tipo in DOMINIOS_REDES.items():
            if d in dominio:
                return tipo, url
    except Exception:
        pass
    return 'pagina', url


def parsear_redes(texto):
    """Extrae URLs del texto. Devuelve lista de (tipo, usuario)."""
    if not texto:
        return []
    texto = str(texto)
    urls = re.findall(r'https?://[^\s,;<>]+', texto)
    resultado = []
    for u in urls:
        tipo, usuario = detectar_red(u)
        if tipo and usuario:
            resultado.append((tipo, usuario))
    return resultado


def parsear_redes_por_columna(row, idx):
    """
    Para la hoja 3 y 4: cada columna trae una red.
    Devuelve lista de (tipo, usuario).
    """
    if idx >= len(row) or not row[idx]:
        return []
    texto = str(row[idx])
    urls = re.findall(r'https?://[^\s,;<>]+', texto)
    resultado = []
    if urls:
        for u in urls:
            tipo, usuario = detectar_red(u)
            if tipo and usuario:
                resultado.append((tipo, usuario))
    else:
        # Sin URL, guardar el texto como está
        linea = texto.strip().split('\n')[0][:300]
        if linea and linea.lower() not in ('x', 'no'):
            resultado.append((None, linea))
    return resultado


# ===============================================================
# HELPERS
# ===============================================================
def limpiar_telefono(txt):
    if not txt:
        return ''
    txt = str(txt)
    return re.sub(r'[^0-9+\-()\s/]', '', txt).strip()[:150]


def parsear_fecha(valor):
    if not valor:
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    try:
        return datetime.strptime(str(valor)[:10], '%Y-%m-%d').date()
    except Exception:
        return None


def excel_id_de_fila(hoja, fila):
    return hoja * 100000 + fila


def agregar_red_si_no_existe(content_obj, tipo, usuario):
    """
    Agrega una RedSocial solo si no existe ya con el mismo usuario.
    Devuelve True si la agregó.
    """
    usuario = (usuario or '').strip()
    if not usuario:
        return False
    # Buscar duplicado exacto
    existente = RedSocial.objects.filter(
        content_type__model=content_obj._meta.model_name,
        object_id=content_obj.pk,
        usuario=usuario,
    ).exists()
    if existente:
        return False
    RedSocial.objects.create(
        content_object=content_obj,
        tipo=tipo or 'otra',
        usuario=usuario,
    )
    return True


def agregar_fuente_si_no_existe(content_obj, url, descripcion, orden):
    if not url:
        return False
    existente = Fuente.objects.filter(
        content_type__model=content_obj._meta.model_name,
        object_id=content_obj.pk,
        url=url,
    ).exists()
    if existente:
        return False
    Fuente.objects.create(
        content_object=content_obj,
        url=url,
        descripcion=descripcion[:400],
        orden=orden,
    )
    return True


# ===============================================================
# IMPORTADOR
# ===============================================================
class Importador:
    def __init__(self, dry_run=False):
        self.dry_run = dry_run
        self.stdout_write = print
        self.stats = {
            'negocios_creados': 0,
            'negocios_actualizados': 0,
            'negocios_duplicados_saltados': 0,
            'experiencias_creadas': 0,
            'experiencias_actualizadas': 0,
            'experiencias_duplicadas_saltadas': 0,
            'guias_creados': 0,
            'guias_actualizados': 0,
            'guias_duplicados_saltados': 0,
            'redes_creadas': 0,
            'fuentes_creadas': 0,
        }

    def log(self, msg):
        self.stdout_write(msg)

    # ---------- HOJA 1: DIRECTORIO ----------
    def importar_hoja1(self, ws):
        print('\n=== HOJA 1: DIRECTORIO TURÍSTICO ===')
        for i, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            if not row or len(row) < 2:
                continue
            nombre = (row[1] or '').strip() if row[1] else ''
            if not nombre:
                continue

            giro_txt = row[2] or ''
            municipio_txt = row[3] or ''
            direccion = (row[4] or '').strip() if len(row) > 4 and row[4] else ''
            telefono = limpiar_telefono(row[5] if len(row) > 5 else '')
            redes_txt = row[6] if len(row) > 6 else ''
            descripcion = (row[7] or '').strip() if len(row) > 7 and row[7] else ''

            municipio, municipio_orig = parsear_municipio(municipio_txt)
            giro, giro_orig = parsear_giro(giro_txt)

            # Buscar existente por nombre
            clave = normalizar(nombre)
            existente = None
            for n in Negocio.objects.all():
                if normalizar(n.nombre) == clave:
                    existente = n
                    break

            if existente:
                # ACTUALIZAR campos vacíos
                cambio = False
                if not existente.direccion and direccion:
                    existente.direccion = direccion; cambio = True
                if not existente.telefono and telefono:
                    existente.telefono = telefono; cambio = True
                if not existente.descripcion and descripcion:
                    existente.descripcion = descripcion; cambio = True
                if not existente.municipio and municipio:
                    existente.municipio = municipio; cambio = True
                if not existente.giro and giro:
                    existente.giro = giro; cambio = True

                if not self.dry_run and cambio:
                    existente.save()
                    self.stats['negocios_actualizados'] += 1
                    self.log(f'  [update] {nombre}')

                # Agregar redes
                for tipo, usuario in parsear_redes(redes_txt):
                    if self.dry_run:
                        self.stats['redes_creadas'] += 1
                    else:
                        if agregar_red_si_no_existe(existente, tipo, usuario):
                            self.stats['redes_creadas'] += 1
                continue

            self.log(f'  [+] {nombre} | {giro_orig} | {municipio_orig}')
            if self.dry_run:
                self.stats['negocios_creados'] += 1
                continue

            with transaction.atomic():
                negocio = Negocio.objects.create(
                    excel_id=excel_id_de_fila(1, i),
                    nombre=nombre,
                    municipio=municipio,
                    municipio_original=municipio_orig if not municipio else '',
                    giro=giro,
                    giro_original=giro_orig if not giro else '',
                    direccion=direccion,
                    telefono=telefono,
                    descripcion=descripcion,
                )
                self.stats['negocios_creados'] += 1

                for tipo, usuario in parsear_redes(redes_txt):
                    if agregar_red_si_no_existe(negocio, tipo, usuario):
                        self.stats['redes_creadas'] += 1

    # ---------- HOJA 2: EXPERIENCIAS ----------
    def importar_hoja2(self, ws):
        print('\n=== HOJA 2: EXPERIENCIAS MEMORABLES ===')
        for i, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            if not row or len(row) < 1:
                continue
            nombre = (row[0] or '').strip() if row[0] else ''
            if not nombre:
                continue

            operador_txt = (row[1] or '').strip() if len(row) > 1 and row[1] else ''
            giro_txt = row[2] if len(row) > 2 else ''
            municipio_txt = row[3] if len(row) > 3 else ''
            direccion = (row[4] or '').strip() if len(row) > 4 and row[4] else ''
            telefono = limpiar_telefono(row[5] if len(row) > 5 else '')
            redes_txt = row[6] if len(row) > 6 else ''
            contacto = (row[7] or '').strip() if len(row) > 7 and row[7] else ''
            descripcion = (row[8] or '').strip() if len(row) > 8 and row[8] else ''

            municipio, municipio_orig = parsear_municipio(municipio_txt)
            giro, giro_orig = parsear_giro(giro_txt)

            # Buscar operador
            operador = None
            if operador_txt:
                clave_op = normalizar(operador_txt)
                for n in Negocio.objects.all():
                    if normalizar(n.nombre) == clave_op:
                        operador = n
                        break

            # Buscar existente
            clave = normalizar(nombre)
            existente = None
            for e in Experiencia.objects.all():
                if normalizar(e.nombre) == clave:
                    existente = e
                    break

            if existente:
                cambio = False
                if not existente.operador and operador:
                    existente.operador = operador; cambio = True
                if not existente.municipio and municipio:
                    existente.municipio = municipio; cambio = True
                if not existente.giro and giro:
                    existente.giro = giro; cambio = True
                if not existente.lugar_realizacion and direccion:
                    existente.lugar_realizacion = direccion; cambio = True
                if not existente.telefono and telefono:
                    existente.telefono = telefono; cambio = True
                if not existente.contacto_encargado and contacto:
                    existente.contacto_encargado = contacto; cambio = True
                if not existente.descripcion and descripcion:
                    existente.descripcion = descripcion; cambio = True

                if not self.dry_run and cambio:
                    existente.save()
                    self.stats['experiencias_actualizadas'] += 1
                    self.log(f'  [update] {nombre}')

                # Agregar redes
                for tipo, usuario in parsear_redes(redes_txt):
                    if self.dry_run:
                        self.stats['redes_creadas'] += 1
                    else:
                        if agregar_red_si_no_existe(existente, tipo, usuario):
                            self.stats['redes_creadas'] += 1
                continue

            self.log(f'  [+] {nombre}')
            if self.dry_run:
                self.stats['experiencias_creadas'] += 1
                continue

            with transaction.atomic():
                exp = Experiencia.objects.create(
                    excel_id=excel_id_de_fila(2, i),
                    nombre=nombre,
                    operador=operador,
                    operador_original=operador_txt if not operador else '',
                    municipio=municipio,
                    municipio_original=municipio_orig if not municipio else '',
                    giro=giro,
                    giro_original=giro_orig if not giro else '',
                    lugar_realizacion=direccion,
                    telefono=telefono,
                    contacto_encargado=contacto,
                    descripcion=descripcion,
                )
                self.stats['experiencias_creadas'] += 1

                # Redes del texto libre
                for tipo, usuario in parsear_redes(redes_txt):
                    if agregar_red_si_no_existe(exp, tipo, usuario):
                        self.stats['redes_creadas'] += 1

    # ---------- HOJA 3: 100 OFERTAS ----------
    def importar_hoja3(self, ws):
        print('\n=== HOJA 3: 100 OFERTAS TURÍSTICAS ===')
        # La hoja tiene encabezado en fila 2, datos desde fila 3
        for i, row in enumerate(ws.iter_rows(min_row=3, values_only=True), start=3):
            if not row or len(row) < 2:
                continue
            nombre = (row[1] or '').strip() if row[1] else ''
            if not nombre:
                continue

            operador_txt = (row[2] or '').strip() if len(row) > 2 and row[2] else ''
            lugar = (row[3] or '').strip() if len(row) > 3 and row[3] else ''
            direccion = (row[4] or '').strip() if len(row) > 4 and row[4] else ''
            telefono = limpiar_telefono(row[5] if len(row) > 5 else '')
            descripcion = (row[12] or '').strip() if len(row) > 12 and row[12] else ''
            estado_txt = (row[13] or '').strip() if len(row) > 13 and row[13] else ''
            actividad = (row[14] or '').strip() if len(row) > 14 and row[14] else ''
            fecha_rev = parsear_fecha(row[15] if len(row) > 15 else None)

            municipio, municipio_orig = parsear_municipio(lugar)

            # Buscar operador
            operador = None
            if operador_txt:
                clave_op = normalizar(operador_txt)
                for n in Negocio.objects.all():
                    if normalizar(n.nombre) == clave_op:
                        operador = n
                        break

            # Buscar existente por nombre
            clave = normalizar(nombre)
            existente = None
            for e in Experiencia.objects.all():
                if normalizar(e.nombre) == clave:
                    existente = e
                    break

            if existente:
                # ACTUALIZAR con datos más completos de la hoja 3
                cambio = False
                if not existente.operador and operador:
                    existente.operador = operador; cambio = True
                if not existente.municipio and municipio:
                    existente.municipio = municipio; cambio = True
                if not existente.lugar_realizacion and lugar:
                    existente.lugar_realizacion = lugar; cambio = True
                if not existente.direccion_referencia and direccion:
                    existente.direccion_referencia = direccion; cambio = True
                if not existente.telefono and telefono:
                    existente.telefono = telefono; cambio = True
                if not existente.descripcion and descripcion:
                    existente.descripcion = descripcion; cambio = True
                if not existente.estado_oferta and estado_txt:
                    existente.estado_oferta = self._mapear_estado(estado_txt); cambio = True
                if not existente.actividad_redes and actividad:
                    existente.actividad_redes = actividad; cambio = True
                if not existente.fecha_revision and fecha_rev:
                    existente.fecha_revision = fecha_rev; cambio = True

                if not self.dry_run and cambio:
                    existente.save()
                    self.stats['experiencias_actualizadas'] += 1
                    self.log(f'  [update] {nombre}')

                target = existente
            else:
                self.log(f'  [+] {nombre}')
                if self.dry_run:
                    self.stats['experiencias_creadas'] += 1
                    continue

                with transaction.atomic():
                    target = Experiencia.objects.create(
                        excel_id=excel_id_de_fila(3, i),
                        nombre=nombre,
                        operador=operador,
                        operador_original=operador_txt if not operador else '',
                        municipio=municipio,
                        municipio_original=municipio_orig if not municipio else '',
                        lugar_realizacion=lugar,
                        direccion_referencia=direccion,
                        telefono=telefono,
                        descripcion=descripcion,
                        estado_oferta=self._mapear_estado(estado_txt),
                        actividad_redes=actividad,
                        fecha_revision=fecha_rev,
                    )
                    self.stats['experiencias_creadas'] += 1

            # === Redes por columna (7=FB, 8=IG, 9=X, 10=TikTok, 11=Otra) ===
            for col_idx, tipo_default in [(6, 'facebook'), (7, 'instagram'),
                                          (8, 'twitter'), (9, 'tiktok'), (10, 'otra')]:
                if col_idx >= len(row):
                    continue
                for tipo, usuario in parsear_redes_por_columna(row, col_idx):
                    if self.dry_run:
                        self.stats['redes_creadas'] += 1
                    else:
                        if agregar_red_si_no_existe(target, tipo or tipo_default, usuario):
                            self.stats['redes_creadas'] += 1

            # === Fuentes (16-20) ===
            for j, idx in enumerate([16, 17, 18, 19, 20], start=1):
                if idx >= len(row) or not row[idx]:
                    continue
                urls = re.findall(r'https?://[^\s,;<>]+', str(row[idx]))
                desc = str(row[idx]).split('http')[0].strip()[:200]
                for u in urls:
                    if self.dry_run:
                        self.stats['fuentes_creadas'] += 1
                    else:
                        if agregar_fuente_si_no_existe(target, u, f'Fuente {j}: {desc}', j):
                            self.stats['fuentes_creadas'] += 1

    def _mapear_estado(self, texto):
        if not texto:
            return ''
        t = normalizar(texto)
        if 'disponible' in t: return 'disponible'
        if 'publicad' in t: return 'publicada'
        if 'descontinu' in t: return 'descontinuada'
        if 'pendiente' in t or 'confirmar' in t: return 'pendiente'
        return ''

    # ---------- HOJA 4: GUÍAS ----------
    def importar_hoja4(self, ws):
        print('\n=== HOJA 4: 90 GUÍAS ===')
        # Encabezados en fila 2, datos desde fila 3
        for i, row in enumerate(ws.iter_rows(min_row=3, values_only=True), start=3):
            if not row or len(row) < 2:
                continue
            nombre = (row[1] or '').strip() if row[1] else ''
            if not nombre or normalizar(nombre) in ('guia', 'nombre'):
                continue

            credencial = (row[2] or '').strip() if len(row) > 2 and row[2] else ''
            idiomas = (row[3] or '').strip() if len(row) > 3 and row[3] else ''
            acreditacion = (row[4] or '').strip() if len(row) > 4 and row[4] else ''
            ubicacion = (row[5] or '').strip() if len(row) > 5 and row[5] else ''
            direccion = (row[6] or '').strip() if len(row) > 6 and row[6] else ''
            telefono = limpiar_telefono(row[7] if len(row) > 7 else '')
            servicio_txt = (row[8] or '').strip() if len(row) > 8 and row[8] else ''
            referencia_redes_txt = (row[14] or '').strip() if len(row) > 14 and row[14] else ''
            actividad = (row[15] or '').strip() if len(row) > 15 and row[15] else ''
            vinculacion = (row[16] or '').strip() if len(row) > 16 and row[16] else ''
            observacion = (row[17] or '').strip() if len(row) > 17 and row[17] else ''
            tipo_fuente = (row[18] or '').strip() if len(row) > 18 and row[18] else ''
            fecha_rev = parsear_fecha(row[19] if len(row) > 19 else None)

            municipio, municipio_orig = parsear_municipio(ubicacion)

            # Servicio vinculado
            servicio = None
            if servicio_txt:
                clave_sv = normalizar(servicio_txt)
                for n in Negocio.objects.all():
                    if normalizar(n.nombre) == clave_sv:
                        servicio = n
                        break

            # Buscar existente
            clave = normalizar(nombre)
            existente = None
            for g in Guia.objects.all():
                if normalizar(g.nombre) == clave:
                    existente = g
                    break

            if existente:
                cambio = False
                if not existente.credencial and credencial:
                    existente.credencial = credencial; cambio = True
                if not existente.idiomas and idiomas:
                    existente.idiomas = idiomas; cambio = True
                if not existente.acreditacion_vigencia and acreditacion:
                    existente.acreditacion_vigencia = acreditacion; cambio = True
                if not existente.municipio and municipio:
                    existente.municipio = municipio; cambio = True
                if not existente.direccion_comercial and direccion:
                    existente.direccion_comercial = direccion; cambio = True
                if not existente.telefono and telefono:
                    existente.telefono = telefono; cambio = True
                if not existente.servicio_vinculado and servicio:
                    existente.servicio_vinculado = servicio; cambio = True
                if not existente.referencia_redes and referencia_redes_txt:
                    existente.referencia_redes = referencia_redes_txt; cambio = True
                if not existente.actividad_redes and actividad:
                    existente.actividad_redes = actividad; cambio = True
                if not existente.vinculacion_contacto and vinculacion:
                    existente.vinculacion_contacto = vinculacion; cambio = True
                if not existente.observacion_ubicacion and observacion:
                    existente.observacion_ubicacion = observacion; cambio = True
                if not existente.tipo_fuente and tipo_fuente:
                    existente.tipo_fuente = tipo_fuente; cambio = True
                if not existente.fecha_revision and fecha_rev:
                    existente.fecha_revision = fecha_rev; cambio = True

                if not self.dry_run and cambio:
                    existente.save()
                    self.stats['guias_actualizados'] += 1
                    self.log(f'  [update] {nombre}')

                target = existente
            else:
                self.log(f'  [+] {nombre} ({credencial})')
                if self.dry_run:
                    self.stats['guias_creados'] += 1
                    continue

                with transaction.atomic():
                    target = Guia.objects.create(
                        excel_id=excel_id_de_fila(4, i),
                        nombre=nombre,
                        credencial=credencial,
                        idiomas=idiomas,
                        acreditacion_vigencia=acreditacion,
                        ubicacion_base=ubicacion,
                        municipio=municipio,
                        municipio_original=municipio_orig if not municipio else '',
                        direccion_comercial=direccion,
                        telefono=telefono,
                        servicio_vinculado=servicio,
                        servicio_vinculado_texto=servicio_txt if not servicio else '',
                        referencia_redes=referencia_redes_txt,
                        actividad_redes=actividad,
                        vinculacion_contacto=vinculacion,
                        observacion_ubicacion=observacion,
                        tipo_fuente=tipo_fuente,
                        fecha_revision=fecha_rev,
                    )
                    self.stats['guias_creados'] += 1

            # === Redes por columna (9=FB, 10=IG, 11=X, 12=TikTok, 13=Otra) ===
            for col_idx, tipo_default in [(9, 'facebook'), (10, 'instagram'),
                                          (11, 'twitter'), (12, 'tiktok'), (13, 'otra')]:
                if col_idx >= len(row):
                    continue
                for tipo, usuario in parsear_redes_por_columna(row, col_idx):
                    if self.dry_run:
                        self.stats['redes_creadas'] += 1
                    else:
                        if agregar_red_si_no_existe(target, tipo or tipo_default, usuario):
                            self.stats['redes_creadas'] += 1

            # === Fuentes (20-23) ===
            for j, idx in enumerate([20, 21, 22, 23], start=1):
                if idx >= len(row) or not row[idx]:
                    continue
                urls = re.findall(r'https?://[^\s,;<>]+', str(row[idx]))
                desc = str(row[idx]).split('http')[0].strip()[:200]
                for u in urls:
                    if self.dry_run:
                        self.stats['fuentes_creadas'] += 1
                    else:
                        if agregar_fuente_si_no_existe(target, u, f'Fuente {j}: {desc}', j):
                            self.stats['fuentes_creadas'] += 1


# ===============================================================
# COMANDO
# ===============================================================
class Command(BaseCommand):
    help = 'Importa las 4 hojas del Excel del Directorio Turístico de Tabasco'

    def add_arguments(self, parser):
        parser.add_argument('archivo', type=str, help='Ruta al .xlsx')
        parser.add_argument('--dry-run', action='store_true',
            help='Solo reporta, no escribe en DB')
        parser.add_argument('--hoja', type=int, default=0,
            help='Importar solo una hoja (1-4). Por defecto todas.')

    def handle(self, *args, **options):
        ruta = Path(options['archivo'])
        if not ruta.exists():
            raise CommandError(f'Archivo no encontrado: {ruta}')

        dry = options['dry_run']
        hoja = options['hoja']

        if dry:
            self.stdout.write(self.style.WARNING(
                '\n*** MODO DRY-RUN: no se escribirá en la base de datos ***\n'
            ))

        wb = load_workbook(ruta, read_only=True, data_only=True)
        self.stdout.write(f'Hojas disponibles: {wb.sheetnames}')

        imp = Importador(dry_run=dry)
        imp.stdout_write = self.stdout.write

        if hoja == 0 or hoja == 1:
            imp.importar_hoja1(wb[wb.sheetnames[0]])
        if hoja == 0 or hoja == 2:
            imp.importar_hoja2(wb[wb.sheetnames[1]])
        if hoja == 0 or hoja == 3:
            imp.importar_hoja3(wb[wb.sheetnames[2]])
        if hoja == 0 or hoja == 4:
            imp.importar_hoja4(wb[wb.sheetnames[3]])

        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(self.style.SUCCESS('RESUMEN'))
        self.stdout.write('=' * 60)
        for k, v in imp.stats.items():
            self.stdout.write(f'  {k}: {v}')
        if dry:
            self.stdout.write(self.style.WARNING('\n(DRY-RUN: nada guardado)'))