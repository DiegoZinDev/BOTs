import random
from playwright.sync_api import sync_playwright 
import time

nome_grupo = "Loucos Por Perfume #1"
cookies = "./data/sessao"
link_grupo = "L7F2OedGjnJ9Z675wQ6UWX"

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
        
        print("abrindo convite")
        page.goto(f"https://chat.whatsapp.com/{link_grupo}")



        botão_entrar = page.get_by_role("link", name=re.compile(r"Continua para o WhatsApp Web", re.IGNORECASE))
        button_entar.wait_for(timeout=10000)
        buttonm_entrar.click()
        print("clicando no botao de convite!")

        time.sleep(100)

if __name__ == "__main__":
    iniciar_zap()
        



 