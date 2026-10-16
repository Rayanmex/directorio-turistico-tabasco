"""
Scraper que se conecta al Chrome ya abierto vía CDP.
Usa la sesión de Facebook que ya tienes activa.

Requisitos:
    1. Chrome abierto con:
       "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\directorio_turistico\chrome_debug"
    2. Facebook logueado en ese Chrome

Uso:
    python scraper_cdp.py --limite 6
    python scraper_cdp.py --todos
"""
import os
os.environ['DJANGO_ALLOW_ASYNC_UNSAFE'] = 'true'

import time
import random
import asyncio
import argparse
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'directorio_turistico.settings')
django.setup()

from playwright.async_api import async_playwright

from directorio.models import Negocio, FotoNegocio
from django.conf import settings
from asgiref.sync import sync_to_async


# ============================================================
# CONFIGURACIÓN
# ============================================================
CDP_URL = 'http://localhost:9222'

CARPETA_FOTOS = settings.BASE_DIR / 'static' / 'img' / 'negocios'
CARPETA_FOTOS.mkdir(parents=True, exist_ok=True)

DELAY_MIN = 3
DELAY_MAX = 6
MAX_GALERIA = 6


# ============================================================
# HELPERS
# ============================================================
def extraer_username_fb(url):
    if not url:
        return None
    try:
        p = urlparse(url)
        path = p.path.strip('/')
        if path.startswith('profile.php'):
            return parse_qs(p.query).get('id', [None])[0]
        partes = [x for x in path.split('/') if x and x not in ('pages', 'people', 'p')]
        for parte in partes:
            if not parte.isdigit():
                return parte
        return partes[0] if partes else None
    except Exception:
        return None


# ============================================================
# SCRAPER
# ============================================================
async def scrape_facebook_page(page, username):
    url = f'https://www.facebook.com/{username}'
    resultado = {'username': username, 'fotos': []}

    try:
        await page.goto(url, wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(random.uniform(2, 4))

        # Cerrar diálogos emergentes
        for label in ['Cerrar', 'Close', 'Ahora no', 'Not now',
                      'Permitir todas', 'Allow all']:
            try:
                btn = page.locator(f'div[aria-label="{label}"], button:has-text("{label}")')
                count = await btn.count()
                if count > 0:
                    await btn.first.click()
                    await asyncio.sleep(0.5)
            except Exception:
                pass

        await page.wait_for_timeout(2000)

        # FOTO DE PERFIL
        try:
            selectores_perfil = [
                'svg image[*|href*="scontent"]',
                'img[src*="scontent"][alt*="perfil"]',
                'img[src*="scontent"][alt*="profile"]',
                'div[role="img"] img[src*="scontent"]',
            ]
            for sel in selectores_perfil:
                fotos = page.locator(sel)
                count = await fotos.count()
                if count > 0:
                    first = fotos.first
                    src = (await first.get_attribute('xlink:href') or
                           await first.get_attribute('href') or
                           await first.get_attribute('src'))
                    if src and 'scontent' in src:
                        resultado['fotos'].append({'tipo': 'logo', 'url': src})
                        break
        except Exception:
            pass

        # SCROLL
        try:
            for _ in range(5):
                await page.mouse.wheel(0, random.randint(800, 1500))
                await asyncio.sleep(random.uniform(1.0, 1.8))
        except Exception:
            pass

        await page.wait_for_timeout(2000)

        # FOTOS DE POSTS
        try:
            selectores_galeria = [
                'div[role="article"] img[src*="scontent"]',
                'div[role="article"] svg image[*|href*="scontent"]',
                'a[href*="/photo"] img[src*="scontent"]',
                'a[href*="/photos"] img[src*="scontent"]',
            ]

            urls_vistas = {f['url'] for f in resultado['fotos']}
            galeria_actual = 0

            for sel in selectores_galeria:
                if galeria_actual >= MAX_GALERIA:
                    break
                try:
                    imgs = page.locator(sel)
                    count = await imgs.count()
                    for i in range(min(count, 40)):
                        if galeria_actual >= MAX_GALERIA:
                            break
                        try:
                            img = imgs.nth(i)
                            src = (await img.get_attribute('src') or
                                   await img.get_attribute('xlink:href') or
                                   await img.get_attribute('href'))
                            if src and 'scontent' in src and src not in urls_vistas:
                                if any(x in src for x in ['_s.', '_t.', '_q.']):
                                    continue
                                resultado['fotos'].append({'tipo': 'galeria', 'url': src})
                                urls_vistas.add(src)
                                galeria_actual += 1
                        except Exception:
                            continue
                except Exception:
                    continue
        except Exception:
            pass

    except Exception as e:
        resultado['error'] = str(e)[:200]

    return resultado


async def descargar_foto(page, url, destino):
    try:
        response = await page.request.get(url, timeout=20000)
        if response.ok:
            body = await response.body()
            with open(destino, 'wb') as f:
                f.write(body)
            return True, len(body)
    except Exception:
        pass
    return False, 0


# ============================================================
# WORKER
# ============================================================
async def worker(tab_id, context, cola, stats, lock, etiqueta):
    page = await context.new_page()
    print(f'{etiqueta} Pestaña lista')

    while True:
        try:
            negocio_id = cola.get_nowait()
        except Exception:
            break

        try:
            negocio = await sync_to_async(Negocio.objects.get)(pk=negocio_id)
        except Negocio.DoesNotExist:
            continue

        red = await sync_to_async(
            lambda n: n.redes.filter(tipo='facebook').first()
        )(negocio)

        if not red:
            continue

        username = extraer_username_fb(red.usuario)
        if not username:
            async with lock:
                stats['fallos'] += 1
            continue

        print(f'{etiqueta} [{negocio.nombre[:45]}]')

        resultado = await scrape_facebook_page(page, username)

        if 'error' in resultado or not resultado['fotos']:
            async with lock:
                stats['fallos'] += 1
            print(f'{etiqueta}   ✗')
        else:
            fotos_viejas = await sync_to_async(
                lambda n: list(FotoNegocio.objects.filter(negocio=n))
            )(negocio)

            for vieja in fotos_viejas:
                try:
                    await sync_to_async(vieja.eliminar_de_disco)()
                except Exception:
                    pass
                await sync_to_async(vieja.delete)()

            descargadas = 0
            for j, foto in enumerate(resultado['fotos'], 1):
                nombre = f'{negocio.slug}_{foto["tipo"]}_{j}.jpg'
                destino = CARPETA_FOTOS / nombre

                ok, _ = await descargar_foto(page, foto['url'], destino)
                if ok:
                    await sync_to_async(FotoNegocio.objects.create)(
                        negocio=negocio,
                        archivo=nombre,
                        carpeta='negocios',
                        tipo=foto['tipo'],
                    )
                    descargadas += 1

            async with lock:
                if descargadas > 0:
                    stats['exitos'] += 1
                    stats['fotos'] += descargadas
                    print(f'{etiqueta}   ✓ {descargadas} fotos')
                else:
                    stats['fallos'] += 1
                    print(f'{etiqueta}   ✗')

        await asyncio.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    try:
        await page.close()
    except Exception:
        pass

    print(f'{etiqueta} Terminado')


# ============================================================
# MAIN
# ============================================================
async def main_async(args):
    qs = await sync_to_async(
        lambda: list(
            Negocio.objects.filter(
                redes__tipo='facebook',
                fotos__isnull=True
            ).distinct().order_by('pk')
        )
    )()

    if not args.todos:
        qs = qs[:args.limite]

    total = len(qs)
    print(f'Negocios a procesar: {total}')
    print(f'Pestañas paralelas:  {args.tabs}')
    print(f'Delays:              {DELAY_MIN}-{DELAY_MAX}s')
    print()

    from queue import Queue
    cola = Queue()
    for n in qs:
        cola.put(n.pk)

    stats = {'exitos': 0, 'fallos': 0, 'fotos': 0}
    lock = asyncio.Lock()

    inicio = time.time()

    async with async_playwright() as p:
        print(f'Conectando a Chrome en {CDP_URL}...')

        try:
            # Conectar al Chrome ya abierto
            browser = await p.chromium.connect_over_cdp(CDP_URL)
            print('✓ Conectado a Chrome')
        except Exception as e:
            print(f'❌ Error: No se pudo conectar a Chrome')
            print(f'   {e}')
            print()
            print('   Asegúrate de haber iniciado Chrome con:')
            print()
            print('   "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\\directorio_turistico\\chrome_debug"')
            print()
            print('   Y de estar logueado en Facebook en ese Chrome.')
            return

        # IMPORTANTE: usar el contexto existente (donde tienes la sesión de Facebook)
        context = browser.contexts[0] if browser.contexts else await browser.new_context()

        print('✓ Usando contexto existente con tu sesión de Facebook\n')

        # Lanzar workers
        tasks = []
        for i in range(args.tabs):
            tasks.append(worker(i + 1, context, cola, stats, lock, f'[T{i+1}]'))

        await asyncio.gather(*tasks)

    duracion = time.time() - inicio

    print('\n' + '=' * 70)
    print('RESUMEN')
    print('=' * 70)
    print(f'  Tiempo total:       {duracion:.0f} segundos')
    print(f'  Negocios exitosos:  {stats["exitos"]}')
    print(f'  Negocios fallidos:  {stats["fallos"]}')
    print(f'  Fotos descargadas:  {stats["fotos"]}')
    print(f'  Carpeta:            {CARPETA_FOTOS.resolve()}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--todos', action='store_true')
    parser.add_argument('--tabs', type=int, default=3)
    parser.add_argument('--limite', type=int, default=6)
    args = parser.parse_args()

    print('=' * 70)
    print('SCRAPER CONECTADO A CHROME EXISTENTE')
    print('=' * 70)

    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        print('\n⚠ Interrumpido')


if __name__ == '__main__':
    main()