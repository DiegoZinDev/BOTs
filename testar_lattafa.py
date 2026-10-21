import time
import sys

# Garante suporte a emojis no console Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from playwright.sync_api import sync_playwright
from web_scrap import extrair_dados_card
from database import init_db, salvar_produto, obter_proxima_oferta
from whatsBots import formatar_mensagem_oferta

def testar():
    init_db()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = context.new_page()
        
        url_busca = "https://www.amazon.com.br/s?k=Lattafa+Asad+Eau+de+Parfum+100ml"
        print(f"Buscando: {url_busca}")
        page.goto(url_busca, wait_until="domcontentloaded", timeout=30000)
        
        # Espera carregar os cards de busca
        page.wait_for_selector('div[data-component-type="s-search-result"]', timeout=15000)
        
        cards = page.locator('div[data-component-type="s-search-result"]')
        total = cards.count()
        print(f"Cards encontrados: {total}")
        
        encontrado = None
        for i in range(total):
            card = cards.nth(i)
            dados = extrair_dados_card(card)
            if dados and "asad" in dados["titulo"].lower():
                encontrado = dados
                salvar_produto(dados)
                break
                
        if not encontrado:
            # Pega o primeiro que tiver dados válidos
            for i in range(total):
                card = cards.nth(i)
                dados = extrair_dados_card(card)
                if dados:
                    encontrado = dados
                    salvar_produto(dados)
                    break

        if encontrado:
            print("\n" + "="*50)
            print("DADOS EXTRAÍDOS DO PRODUTO:")
            print("="*50)
            for k, v in encontrado.items():
                print(f"  {k}: {v}")
                
            print("\n" + "="*50)
            print("MENSAGEM FORMATADA PARA O WHATSAPP:")
            print("="*50)
            msg = formatar_mensagem_oferta(encontrado)
            print(msg)
            print("="*50)
            print(f"\nLINK DE AFILIADO GERADO: {encontrado['link_afiliado']}")
        else:
            print("Nenhum card com dados válidos encontrado.")
            
        browser.close()

if __name__ == "__main__":
    testar()
