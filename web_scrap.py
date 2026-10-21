import re
import random
import time
from playwright.sync_api import sync_playwright
from database import init_db, salvar_produto, total_produtos

# Configurações do Afiliado e Busca
TAG_AFILIADO = "diego07306-20"  # Sua tag oficial de associado Amazon
COOKIES_AMAZON = "./data/sessaoAmazon"
TERMOS_BUSCA = [
    "perfumes masculinos importados",
    "perfumes femininos importados",
]


def limpar_preco(texto: str) -> float | None:
    """Converte 'R$ 189,90' ou '1.250,00' em float (ex: 189.90)."""
    if not texto:
        return None
    limpo = re.sub(r"[^\d,\.]", "", texto)
    if "," in limpo:
        limpo = limpo.replace(".", "").replace(",", ".")
    try:
        return float(limpo)
    except ValueError:
        return None


def limpar_nota(texto: str) -> float | None:
    """Extrai '4,6' de '4,6 de 5 estrelas' e converte para float 4.6."""
    if not texto:
        return None
    match = re.search(r"(\d+[.,]\d+)", texto)
    if match:
        return float(match.group(1).replace(",", "."))
    return None


def limpar_qtd_avaliacoes(texto: str) -> int | None:
    """Extrai quantidade de avaliações, tratando formatos como '29,8 mil' ou '1.450'."""
    if not texto:
        return None
    texto_lower = texto.lower()
    if "mil" in texto_lower:
        match = re.search(r"([\d,\.]+)", texto_lower)
        if match:
            num = float(match.group(1).replace(",", "."))
            return int(num * 1000)
    digitos = re.sub(r"\D", "", texto)
    return int(digitos) if digitos else None



def extrair_dados_card(card) -> dict | None:
    """Extrai todas as informações de um card de produto no resultado de busca."""
    try:
        asin = card.get_attribute("data-asin")
        if not asin or len(asin.strip()) == 0:
            return None  # Não é um produto real (espaçador publicitário)

        # 1. Título
        titulo_el = card.locator("h2 a span, h2 span, h2").first
        titulo = titulo_el.inner_text().strip() if titulo_el.count() > 0 else "Sem título"

        # 2. Link canônico com tag de afiliado (limpo e sem parâmetros de rastreamento da busca)
        link_afiliado = f"https://www.amazon.com.br/dp/{asin}?tag={TAG_AFILIADO}"

        # 3. Imagem
        img_el = card.locator("img.s-image").first
        imagem_url = img_el.get_attribute("src") if img_el.count() > 0 else None

        # 4. Preço Atual ("Por")
        preco_atual = None
        preco_atual_el = card.locator("span.a-price:not(.a-text-price) span.a-offscreen").first
        if preco_atual_el.count() > 0:
            preco_atual = limpar_preco(preco_atual_el.inner_text())

        if not preco_atual:
            # Sem preço disponível (esgotado ou formato diferente)
            return None

        # 5. Preço Original Riscado ("De")
        preco_original = None
        preco_orig_el = card.locator("span.a-price.a-text-price span.a-offscreen").first
        if preco_orig_el.count() > 0:
            preco_original = limpar_preco(preco_orig_el.inner_text())

        # 6. Cálculo de Desconto (% OFF)
        desconto_pct = 0
        if preco_original and preco_original > preco_atual:
            desconto_pct = round(((preco_original - preco_atual) / preco_original) * 100)

        # 7. Nota Média (Estrelas)
        nota = None
        nota_el = card.locator("i.a-icon-star-small span.a-icon-alt, span.a-icon-alt").first
        if nota_el.count() > 0:
            nota = limpar_nota(nota_el.inner_text())

        # 8. Qtd de Avaliações
        qtd_avaliacoes = None
        qtd_el = card.locator("span.a-size-base.s-underline-text, a[href*='#customerReviews'] span").first
        if qtd_el.count() > 0:
            qtd_avaliacoes = limpar_qtd_avaliacoes(qtd_el.inner_text())

        # 9. Vendas Recentes ("Mais de X compras no mês passado")
        vendas_mes = None
        card_text = card.inner_text()
        vendas_match = re.search(r"(Mais de [\d\w\s]+ compras no m[êe]s passado)", card_text, re.IGNORECASE)
        if vendas_match:
            vendas_mes = vendas_match.group(1).strip()

        # 10. Selo Amazon Prime
        is_prime = 1 if card.locator("i.a-icon-prime, span[aria-label*='Prime']").count() > 0 else 0

        # 11. Selos / Badges Oficiais
        badge = None
        badge_el = card.locator("span.a-badge-text, span.a-badge-label").first
        if badge_el.count() > 0:
            badge = badge_el.inner_text().strip()
        elif "mais vendido" in card_text.lower():
            badge = "1º Mais Vendido"
        elif "escolha da amazon" in card_text.lower():
            badge = "Escolha da Amazon"

        return {
            "asin": asin,
            "titulo": titulo,
            "link_afiliado": link_afiliado,
            "imagem_url": imagem_url,
            "preco_atual": preco_atual,
            "preco_original": preco_original,
            "desconto_pct": desconto_pct,
            "avaliacao_nota": nota,
            "avaliacao_qtd": qtd_avaliacoes,
            "vendas_mes": vendas_mes,
            "is_prime": is_prime,
            "badge": badge,
        }
    except Exception as e:
        print(f"Erro ao processar card: {e}")
        return None


def raspar_busca(termo_busca: str):
    """Abre a busca na Amazon, coleta os produtos e insere no banco de dados."""
    init_db()

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            COOKIES_AMAZON,
            headless=False,
            slow_mo=200
        )

        page = context.pages[0] if context.pages else context.new_page()

        print("Acessando Amazon Brasil...")
        page.goto("https://www.amazon.com.br")

        # Localiza a barra de pesquisa
        barra_pesquisa = page.locator("#twotabsearchtextbox")
        barra_pesquisa.wait_for(state="visible", timeout=15000)

        print(f"Pesquisando por: '{termo_busca}'")
        barra_pesquisa.fill("")
        barra_pesquisa.press_sequentially(termo_busca, delay=random.randint(20, 60))
        barra_pesquisa.press("Enter")

        # Aguarda os resultados
        selector_card = 'div[data-component-type="s-search-result"]'
        page.wait_for_selector(selector_card, state="visible", timeout=15000)

        # Rola a página suavemente para forçar o carregamento de imagens (lazy load)
        page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
        time.sleep(1)
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(1)

        cards = page.locator(selector_card)
        total_cards = cards.count()
        print(f"Encontrados {total_cards} produtos na página!")

        inseridos = 0
        for i in range(total_cards):
            card = cards.nth(i)
            dados = extrair_dados_card(card)

            if dados:
                sucesso = salvar_produto(dados)
                if sucesso:
                    inseridos += 1
                    desconto_str = f"({dados['desconto_pct']}% OFF)" if dados['desconto_pct'] > 0 else ""
                    nota_str = f"⭐ {dados['avaliacao_nota']}" if dados['avaliacao_nota'] else "S/Nota"
                    badge_str = f"[{dados['badge']}]" if dados['badge'] else ""
                    print(f"[{inseridos}] Salvo: {dados['titulo'][:40]}... | R$ {dados['preco_atual']} {desconto_str} | {nota_str} {badge_str}")

        print(f"\nColeta concluída para '{termo_busca}': {inseridos} produtos salvos/atualizados.")
        stats = total_produtos()
        print(f"Estatísticas atuais do Banco de Dados: {stats}\n")

        context.close()


if __name__ == "__main__":
    # Executa a busca para o primeiro termo configurado
    raspar_busca("perfumes masculinos importados")