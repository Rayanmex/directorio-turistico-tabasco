"""
Scraper de Instagram con Playwright + asyncio.
Usa tu perfil de Chrome (Default) para tener sesión activa.

Uso:
    python scraper_ig.py                    # 6 negocios (2 por pestaña)
    python scraper_ig.py --todos            # Todos los que tengan IG
    python scraper_ig.py --tabs 5           # 5 pestañas
    python scraper_ig.py --headless         # Sin ventana
"""
import os
os.environ['DJANGO_ALLOW_ASYNC_UNSAFE'] = 'true'

import time
import random
import asyncio
import argparse
from pathlib import Path
from urllib.parse import urlparse

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
PERFIL_CHROME = Path(os.environ['LOCALAPPDATA']) / 'Google' / 'Chrome' / 'User Data' / 'Default'

CARPETA_FOTOS = settings.BASE_DIR / 'static' / 'img' / 'negocios'
CARPETA_FOTOS.mkdir(parents=True, exist_ok=True)

# Instagram es más estricto que Facebook
DELAY_MIN = 8
DELAY_MAX = 15
MAX_GALERIA = 3


# ============================================================
# HELPERS
# ============================================================
def extraer_username_ig(url):
    """Extrae username de una URL de Instagram."""
    if not url:
        return None
    try:
        p = urlparse(url)
        path = p.path.strip('/')
        partes = [x for x in path.split('/') if x]
        for parte in partes:
            if parte not in ('p', 'reel', 'tv', 'stories'):
                # Limpiar query params residuales
                return parte.split('?')[0]
        return None
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
# SCRAPER
# ============================================================
async def scrape_instagram(page, username):
    """
    Navega al perfil de IG y extrae:
    - Foto de perfil (logo)
    - Fotos de los primeros posts (galería)
    """
    url = f'https://www.instagram.com/{username}/'
    resultado = {'username': username, 'fotos': []}

    try:
        await page.goto(url, wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(random.uniform(3, 5))

        # Cerrar modal de "Regístrate para ver más" si aparece
        try:
            # El botón "Ahora no" del modal
            for label in ['Ahora no', 'Not now', 'Cerrar', 'Close']:
                btn = page.locator(f'button:has-text("{label}")')
                if await btn.count() > 0:
                    await btn.first.click()
                    await asyncio.sleep(0.8)
                    break
        except Exception:
            pass

        # Foto de perfil
        try:
            # Instagram usa <img alt="Foto del perfil de ..."> o clase _aa8j
            selectores_perfil = [
                'header img[alt*="perfil"]',
                'header img[alt*="profile picture"]',
                'img[alt*="profile picture"]',
                'img[alt*="Foto del perfil"]',
                'header img[src*="scontent"][style*="object-fit"]',
                'header img[src*="scontent"]',
            ]
            for sel in selectores_perfil:
                loc = page.locator(sel)
                count = await loc.count()
                if count > 0:
                    src = await loc.first.get_attribute('src')
                    if src and 'cdninstagram' in src or 'fbcdn' in src:
                        resultado['fotos'].append({'tipo': 'logo', 'url': src})
                        print(f'    OK Foto de perfil')
                        break
        except Exception:
            pass

        # Scroll para cargar posts
        try:
            for _ in range(2):
                await page.mouse.wheel(0, random.randint(400, 800))
                await asyncio.sleep(random.uniform(1, 2))
        except Exception:
            pass

        await page.wait_for_timeout(1000)

        # Fotos de posts
        try:
            # Selector principal: imágenes en el grid de posts
            selectores_galeria = [
                'article img[src*="cdninstagram"]',
                'article img[src*="fbcdn"]',
                'main img[src*="cdninstagram"]',
                'div[role="main"] img[src*="cdninstagram"]',
                'a[href*="/p/"] img',
                'a[href*="/reel/"] img',
            ]

            urls_vistas = {f['url'] for f in resultado['fotos']}
            galeria_actual = 0

            for sel in selectores_galeria:
                if galeria_actual >= MAX_GALERIA:
                    break
                loc = page.locator(sel)
                count = await loc.count()
                if count == 0:
                    continue
                for i in range(min(count, 10)):
                    if galeria_actual >= MAX_GALERIA:
                        break
                    try:
                        src = await loc.nth(i).get_attribute('src')
                        if src and ('cdninstagram' in src or 'fbcdn' in src) and src not in urls_vistas:
                            resultado['fotos'].append({'tipo': 'galeria', 'url': src})
                            urls_vistas.add(src)
                            galeria_actual += 1
                    except Exception:
                        continue

            print(f'    OK {galeria_actual} fotos de galeria')

        except Exception:
            pass

    except Exception as e:
        resultado['error'] = str(e)[:200]

    return resultado


async def descargar_foto(page, url, destino):
    """Descarga una imagen usando el contexto del navegador (con cookies)."""
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
async def worker(tab_id, context, cola, stats, lock):
    etiqueta = f'[IG{tab_id}]'

    try:
        page = await context.new_page()
        print(f'{etiqueta} Pestaña lista')
    except Exception as e:
        print(f'{etiqueta} Error creando pestaña: {e}')
        return

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
            lambda n: n.redes.filter(tipo='instagram').first()
        )(negocio)

        if not red:
            continue

        username = extraer_username_ig(red.usuario)
        if not username:
            async with lock:
                stats['fallos'] += 1
            continue

        print(f'{etiqueta} [{negocio.nombre[:40]}] @{username}')

        resultado = await scrape_instagram(page, username)

        if 'error' in resultado or not resultado['fotos']:
            async with lock:
                stats['fallos'] += 1
            print(f'{etiqueta}   ✗')
        else:
            # Borrar SOLO fotos viejas de Instagram (las que empiezan con {slug}_ig_)
            # Las de Facebook (sin _ig_) se conservan
            prefijo_ig = f'{negocio.slug}_ig_'

            fotos_viejas_ig = await sync_to_async(
                lambda n, p: list(
                    FotoNegocio.objects.filter(negocio=n, archivo__startswith=p)
                )
            )(negocio, prefijo_ig)

            for vieja in fotos_viejas_ig:
                try:
                    await sync_to_async(vieja.eliminar_de_disco)()
                except Exception:
                    pass
                await sync_to_async(vieja.delete)()

            # Verificar si ya existe un logo (de FB por ejemplo)
            tiene_logo = await sync_to_async(
                lambda n: n.fotos.filter(tipo='logo').exists()
            )(negocio)

            descargadas = 0
            for j, foto in enumerate(resultado['fotos'], 1):
                # Si ya hay logo, forzar tipo='galeria' para no pisarlo
                tipo_final = foto['tipo']
                if foto['tipo'] == 'logo' and tiene_logo:
                    tipo_final = 'galeria'

                nombre = f'{negocio.slug}_ig_{tipo_final}_{j}.jpg'
                destino = CARPETA_FOTOS / nombre

                ok, _ = await descargar_foto(page, foto['url'], destino)
                if ok:
                    await sync_to_async(FotoNegocio.objects.create)(
                        negocio=negocio,
                        archivo=nombre,
                        carpeta='negocios',
                        tipo=tipo_final,
                    )
                    descargadas += 1
                    # Marcar que ya hay logo si se acaba de crear
                    if tipo_final == 'logo':
                        tiene_logo = True

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
            Negocio.objects.filter(redes__tipo='instagram')
            .distinct()
            .order_by('pk')
        )
    )()

    if not args.todos:
        qs = qs[:args.limite]

    total = len(qs)
    print(f'Negocios con Instagram: {total}')
    print(f'Pestañas paralelas:     {args.tabs}')
    print(f'Delays:                 {DELAY_MIN}-{DELAY_MAX}s')
    print(f'Modo:                   {"HEADLESS" if args.headless else "VISIBLE"}\n')

    from queue import Queue
    cola = Queue()
    for n in qs:
        cola.put(n.pk)

    stats = {'exitos': 0, 'fallos': 0, 'fotos': 0}
    lock = asyncio.Lock()

    inicio = time.time()

    async with async_playwright() as p:
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

        # Verificar login en Instagram
        first_page = context.pages[0] if context.pages else await context.new_page()
        await first_page.goto('https://www.instagram.com/', wait_until='domcontentloaded', timeout=20000)
        await first_page.wait_for_timeout(2000)

        url = first_page.url.lower()
        if '/accounts/login' in url:
            print('❌ No estás logueado en Instagram.')
            print('   Abre Chrome, ve a instagram.com, loguéate, y vuelve a correr el script.')
            try:
                await context.close()
            except Exception:
                pass
            return

        print('✓ Sesión de Instagram activa\n')

        # Lanzar N workers en paralelo
        tasks = []
        for i in range(args.tabs):
            tasks.append(worker(i + 1, context, cola, stats, lock))

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
    print('SCRAPER INSTAGRAM (Playwright + ASYNC)')
    print('=' * 70)

    if not verificar_chrome_cerrado():
        print('❌ Chrome está abierto. Ciérralo completamente antes de correr.')
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