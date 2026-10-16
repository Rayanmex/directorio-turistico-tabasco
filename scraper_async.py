"""
Scraper con asyncio + 3 pestañas paralelas usando un PERFIL DEDICADO de Chrome.

El perfil dedicado YA tiene la sesión de Facebook copiada de tu Chrome personal.

Uso:
    python scraper_async.py                 # 6 negocios
    python scraper_async.py --todos         # Todos los sin foto
    python scraper_async.py --tabs 5        # 5 pestañas
    python scraper_async.py --headless      # Sin ventana
"""
import os
os.environ['DJANGO_ALLOW_ASYNC_UNSAFE'] = 'true'

import sys
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
# Perfil DEDICADO (aislado de tu Chrome personal)
PERFIL_CHROME = Path(r'C:\directorio_turistico\chrome_scraper')

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


def verificar_chrome_cerrado():
    import subprocess
    try:
        result = subprocess.run(
            ['tasklist', '/FI', 'IMAGENAME eq chrome.exe'],
            capture_output=True, text=True, timeout=5
        )
        if 'chrome.exe' in result.stdout.lower():
            return False
    except Exception:
        pass
    return True


# ============================================================
# SCRAPER (async)
# ============================================================
async def scrape_facebook_page(page, username):
    url = f'https://www.facebook.com/{username}'
    resultado = {'username': username, 'fotos': []}

    try:
        await page.goto(url, wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(random.uniform(2, 4))

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
    print(f'Modo:                {"HEADLESS" if args.headless else "VISIBLE"}\n')

    from queue import Queue
    cola = Queue()
    for n in qs:
        cola.put(n.pk)

    stats = {'exitos': 0, 'fallos': 0, 'fotos': 0}
    lock = asyncio.Lock()

    inicio = time.time()

    async with async_playwright() as p:
        print(f'Perfil dedicado: {PERFIL_CHROME}')
        print()

        if not PERFIL_CHROME.exists():
            print(f'❌ Perfil no encontrado: {PERFIL_CHROME}')
            print()
            print('   Copia tu perfil de Chrome con este comando:')
            print(f'   xcopy "%LOCALAPPDATA%\\Google\\Chrome\\User Data\\Default" "{PERFIL_CHROME}" /E /I /H /Y')
            return

        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(PERFIL_CHROME),
            headless=args.headless,
            channel='chrome',
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-first-run',
                '--no-default-browser-check',
                '--disable-infobars',
                '--disable-session-crashed-bubble',
            ],
            viewport={'width': 1366, 'height': 768},
            locale='es-MX',
            timezone_id='America/Mexico_City',
        )

        # Verificar login
        first_page = context.pages[0] if context.pages else await context.new_page()
        await first_page.goto('https://www.facebook.com/', wait_until='domcontentloaded', timeout=20000)
        await first_page.wait_for_timeout(2500)

        url = first_page.url.lower()

        # PAUSA PARA LOGIN MANUAL (solo si no está logueado)
        if 'login' in url or 'checkpoint' in url:
            print()
            print('=' * 70)
            print('  LOGIN REQUERIDO')
            print('=' * 70)
            print('  El navegador está abierto con el PERFIL DEDICADO.')
            print()
            print('  1. Ve a la ventana de Chrome')
            print('  2. Inicia sesión en Facebook')
            print('  3. Vuelve a esta terminal y presiona ENTER')
            print()
            print('  La sesión se guardará en el perfil dedicado.')
            print('  Las próximas veces no tendrás que loguearte.')
            print()
            input('  ➤ Presiona ENTER cuando estés logueado... ')

            await first_page.goto('https://www.facebook.com/', wait_until='domcontentloaded', timeout=20000)
            await first_page.wait_for_timeout(2000)

            url = first_page.url.lower()
            if 'login' in url or 'checkpoint' in url:
                print()
                print('❌ Aún no estás logueado. Abortando.')
                try:
                    await context.close()
                except Exception:
                    pass
                return

        print('✓ Sesión de Facebook activa\n')

        # Cerrar pestañas extra
        if len(context.pages) > 1:
            for pg in context.pages[1:]:
                try:
                    await pg.close()
                except Exception:
                    pass

        # Lanzar N workers
        tasks = []
        for i in range(args.tabs):
            tasks.append(worker(i + 1, context, cola, stats, lock, f'[T{i+1}]'))

        await asyncio.gather(*tasks)

        try:
            await context.close()
        except Exception:
            pass

    duracion = time.time() - inicio

    print('\n' + '=' * 70)
    print('RESUMEN')
    print('=' * 70)
    print(f'  Tiempo total:       {duracion:.0f} segundos ({duracion/60:.1f} min)')
    print(f'  Negocios exitosos:  {stats["exitos"]}')
    print(f'  Negocios fallidos:  {stats["fallos"]}')
    print(f'  Total negocios:     {total}')
    print(f'  Fotos descargadas:  {stats["fotos"]}')
    if total:
        print(f'  Promedio:           {duracion/total:.1f}s por negocio')
    print(f'  Carpeta:            {CARPETA_FOTOS.resolve()}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--todos', action='store_true')
    parser.add_argument('--tabs', type=int, default=3)
    parser.add_argument('--limite', type=int, default=6)
    parser.add_argument('--headless', action='store_true')
    args = parser.parse_args()

    print('=' * 70)
    print('SCRAPER CHROME + PERFIL DEDICADO')
    print('=' * 70)
    print(f'Perfil: {PERFIL_CHROME}')
    print()

    if not verificar_chrome_cerrado():
        print('❌ Chrome está abierto. Ciérralo completamente antes de correr.')
        print('   (El script necesita abrir Chrome con el perfil dedicado)')
        input('   ➤ Presiona ENTER cuando lo hayas cerrado... ')
        if not verificar_chrome_cerrado():
            print('❌ Chrome sigue abierto. Abortando.')
            return

    print('✓ Chrome cerrado\n')

    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        print('\n⚠ Interrumpido')


if __name__ == '__main__':
    main()