import random
from playwright.sync_api import sync_playwright 
import time
import re


nome_grupo = "Loucos Por Perfume #1"
cookies = "./data/sessao"

links_promo = [

]

def iniciar_zap():
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=cookies,
            headless=False,
            slow_mo=500
        )
        
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(f"https://web.whatsapp.com/")
        # espera a lista de conversas carregar (tempo longo caso precise escanear o QR Code)
        page.wait_for_selector("#pane-side", timeout=60000)

        primeira_conversa = page.locator(
            '#pane-side [role="listitem"], #pane-side [role="row"]'
        ).first
        
        primeira_conversa.click()
        print("primeira conversa aberta!")

        

        time.sleep(100)

if __name__ == "__main__":
    iniciar_zap()
        



 