import random
import time
from playwright.sync_api import sync_playwright

cookiesAmazon = "./data/sessaoAmazon"

links_lojas = [


]

def abrir_amazon():
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            cookiesAmazon,
            headless=False,
            slow_mo=500)

        # Reutiliza a aba que o launch_persistent_context já abre por padrão
        page = context.pages[0] if context.pages else context.new_page()
        
        print("abrindo amazon")
        page.goto("https://www.amazon.com.br")

        # Localiza a barra de pesquisa pelo ID mostrado no DevTools (#twotabsearchtextbox)
        termo_busca = "perfumes masculinos importados"
        barra_pesquisa = page.locator("#twotabsearchtextbox")
        barra_pesquisa.wait_for(state="visible", timeout=15000)

        print(f"Pesquisando por: {termo_busca}")
        barra_pesquisa.press_sequentially(termo_busca, delay=random.randint(30, 100))
        barra_pesquisa.press("Enter")

        # Aguarda os resultados carregarem
        page.wait_for_selector('div[data-component-type="s-search-result"]', state="visible", timeout=15000)
        print("Resultados carregados!")

        time.sleep(600)
    
        context.close()
        
if __name__ == "__main__":
    abrir_amazon()        