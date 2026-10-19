
import random
import re
import time
from playwright.sync_api import sync_playwright


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
        
        print("abrindo whatsapp")
        page.goto("https://web.whatsapp.com")
        
        def type_in_chat():
            input_box = page.locator('#main [contenteditable="true"]')
            input_box.wait_for(state="visible", timeout=10000)
            input_box.press_sequentially("Bora começar", delay=random.randint(30, 100))
            input_box.press("Enter")

        print("abrindo primeira conversa")
        page.wait_for_selector('#pane-side [role="row"]', state="visible", timeout=20000)
        page.locator('#pane-side [role="row"]').first.click()
        type_in_chat()

        time.sleep(1000)

            
    
if __name__ == "__main__":
    iniciar_zap()
        



 