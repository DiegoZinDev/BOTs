
import random
import re
import time
from playwright.sync_api import sync_playwright


from database import obter_proxima_oferta, marcar_como_postado

nome_grupo = "Loucos Por Perfume #1"
cookies = "./data/sessao"


def formatar_mensagem_oferta(p: dict) -> str:
    """Monta uma mensagem de alta conversão usando os gatilhos e critérios extraídos."""
    linhas = []

    # 1. Headline de destaque
    if p.get("badge"):
        linhas.append(f"🏆 *DESTAQUE: {p['badge'].upper()}!*")
    elif p.get("desconto_pct") and p["desconto_pct"] >= 15:
        linhas.append(f"🔥 *QUEDA DE PREÇO: {p['desconto_pct']}% OFF!*")
    else:
        linhas.append("🚨 *SUPER OFERTA NA AMAZON!*")

    linhas.append("")
    linhas.append(f"✨ *{p['titulo']}*")
    linhas.append("")

    # 2. Preço De / Por
    if p.get("preco_original") and p["preco_original"] > p["preco_atual"]:
        linhas.append(f"❌ De: ~R$ {p['preco_original']:.2f}~")
        linhas.append(f"✅ *Por: R$ {p['preco_atual']:.2f}* ({p['desconto_pct']}% de desconto)")
    else:
        linhas.append(f"💰 *Preço: R$ {p['preco_atual']:.2f}*")

    linhas.append("")

    # 3. Gatilhos de Prova Social e Segurança (Critérios de Perfumaria)
    if p.get("avaliacao_nota") and p.get("avaliacao_qtd"):
        linhas.append(f"⭐ Nota {p['avaliacao_nota']:.1f} ({p['avaliacao_qtd']} avaliações)")
    if p.get("vendas_mes"):
        linhas.append(f"🔥 {p['vendas_mes']}")
    if p.get("is_prime"):
        linhas.append("🚚 Frete Grátis com Amazon Prime")

    linhas.append("")
    linhas.append("🛒 *Garanta o seu no link oficial:*")
    linhas.append(p["link_afiliado"])

    return "\n".join(linhas)






import sys

# Garante suporte a emojis no terminal Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")


def iniciar_zap():
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=cookies,
            headless=False,
            slow_mo=300
        )
        
        page = context.pages[0] if context.pages else context.new_page()
        
        print("Abrindo WhatsApp Web...")
        page.goto("https://web.whatsapp.com")
        
        def type_in_chat():
            # Busca a melhor oferta que nunca foi postada OU postada há mais de 2 dias
            oferta = obter_proxima_oferta(filtro_ouro=True, intervalo_dias=2)
            if not oferta:
                print("Nenhuma oferta disponível no momento. Todas já foram postadas nos últimos 2 dias!")
                return

            print(f"\n[OFERTA SELECIONADA]: {oferta['titulo']}")
            texto_mensagem = formatar_mensagem_oferta(oferta)

            input_box = page.locator('#main [contenteditable="true"]')
            input_box.wait_for(state="visible", timeout=15000)
            input_box.click()
            time.sleep(1)

            # Insere o texto completo instantaneamente (como Ctrl+V humano)
            page.keyboard.insert_text(texto_mensagem)
            
            # Aguarda 2 segundos para o WhatsApp carregar a prévia do link da Amazon
            time.sleep(2)

            # Envia a mensagem
            input_box.press("Enter")
            print("Mensagem enviada com sucesso no grupo!")

            # Registra no banco de dados para bloquear repetição por 2 dias
            marcar_como_postado(oferta["asin"])
            print(f"Produto {oferta['asin']} bloqueado para repostagem pelos próximos 2 dias.")

        print("Aguardando carregamento das conversas...")
        page.wait_for_selector('#pane-side [role="row"]', state="visible", timeout=30000)
        
        print("Abrindo a conversa...")
        page.locator('#pane-side [role="row"]').first.click()
        time.sleep(1)
        type_in_chat()

        print("\nProcesso finalizado. Aguardando...")
        time.sleep(1000)

            
    
if __name__ == "__main__":
    iniciar_zap()
        



 