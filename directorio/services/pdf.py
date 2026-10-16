"""
Convierte una URL servida por Django a PDF usando Playwright.
"""
from playwright.sync_api import sync_playwright


def pdf_desde_url(url: str) -> bytes:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        page.goto(url, wait_until='networkidle')
        page.wait_for_timeout(500)

        pdf_bytes = page.pdf(
            format='Letter',
            print_background=True,
            prefer_css_page_size=True,
            margin={'top': '0', 'right': '0', 'bottom': '0', 'left': '0'},
        )

        browser.close()
        return pdf_bytes