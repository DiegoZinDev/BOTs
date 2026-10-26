import os
import re
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright

from database import (
    obter_proxima_oferta,
    marcar_como_postado,
    salvar_imagem_blob,
    obter_imagem_blob,
)

# Garante suporte a emojis no terminal Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

nome_grupo = "Loucos Por Perfume #1"
cookies = "./data/sessao"
INTERVALO_POSTAGEM_MINUTOS = 10
INTERVALO_POSTAGEM_SEGUNDOS = INTERVALO_POSTAGEM_MINUTOS * 60


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


def obter_url_alta_resolucao(url: str) -> str:
    """Remove modificadores de tamanho/miniatura da Amazon para obter a imagem em máxima resolução."""
    if not url:
        return ""
    return re.sub(r'\._[A-Za-z0-9_,-]+_\.', '.', url)


def buscar_imagem_lifestyle_amazon(asin: str, context=None) -> str | None:
    """
    Acessa a galeria da página do produto na Amazon para obter fotos de ambientação,
    notas olfativas ou marketing oficial (lifestyle).
    """
    if not context:
        return None
    page = None
    try:
        page = context.new_page()
        page.goto(f"https://www.amazon.com.br/dp/{asin}", timeout=8000)
        imgs = page.locator('#altImages ul li img').evaluate_all('els => els.map(e => e.src)')

        urls_validas = []
        for src in imgs:
            if not src or "mini-player" in src or "play-button" in src or "transparent-pixel" in src:
                continue
            alta_res = obter_url_alta_resolucao(src)
            urls_validas.append(alta_res)

        # Na Amazon:
        # A imagem no índice 0 costuma ser o frasco simples em fundo branco.
        # Os índices seguintes (1, 2, ...) trazem fotos temáticas, ingredientes e ambientação atraente.
        if len(urls_validas) > 2:
            return urls_validas[1]
        elif len(urls_validas) > 1:
            return urls_validas[1]
        elif urls_validas:
            return urls_validas[0]
    except Exception as e:
        print(f"⚠️ Erro ao buscar galeria na Amazon ({e}).")
    finally:
        if page:
            try:
                page.close()
            except Exception:
                pass
    return None


def obter_ou_baixar_imagem_blob(asin: str, imagem_url_padrao: str, context=None) -> bytes | None:
    """
    Recupera a imagem do produto salva no banco de dados SQLite (MEDIUMBLOB).
    Caso ainda não esteja no banco, faz a busca na galeria da Amazon ou na URL oficial,
    baixa diretamente para a memória e salva no banco de dados SQLite.
    """
    # 1. Verifica se já está guardada no banco de dados SQLite
    blob = obter_imagem_blob(asin)
    if blob and len(blob) > 1000:
        print(f"📦 Imagem do produto {asin} recuperada diretamente do banco SQLite ({len(blob)} bytes).")
        return blob

    # 2. Se não estiver no banco, busca fotos de ambientação/lifestyle na Amazon
    url_final = None
    if context:
        print(f"🔍 Buscando foto de ambientação/lifestyle na Amazon para {asin}...")
        url_final = buscar_imagem_lifestyle_amazon(asin, context)

    # 3. Fallback para a imagem principal em ultra alta resolução
    if not url_final and imagem_url_padrao:
        url_final = obter_url_alta_resolucao(imagem_url_padrao)

    if not url_final:
        return None

    try:
        req = urllib.request.Request(
            url_final,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()

        if data and len(data) > 1000:
            # Salva os bytes diretamente no banco de dados SQLite (MEDIUMBLOB)
            salvar_imagem_blob(asin, data)
            print(f"💾 Foto salva no banco de dados SQLite (MEDIUMBLOB, {len(data)} bytes) para {asin}!")
            return data
    except Exception as e:
        print(f"⚠️ Falha no download da imagem ({e}).")
        if imagem_url_padrao and url_final != imagem_url_padrao:
            try:
                with urllib.request.urlopen(imagem_url_padrao, timeout=15) as resp:
                    data = resp.read()
                if data and len(data) > 1000:
                    salvar_imagem_blob(asin, data)
                    return data
            except Exception:
                pass
    return None


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
        
        def type_in_chat() -> bool:
            try:
                # Busca a melhor oferta que nunca foi postada OU postada há mais de 2 dias
                oferta = obter_proxima_oferta(filtro_ouro=True, intervalo_dias=2)
                if not oferta:
                    print("⚠️ Nenhuma oferta disponível no momento. Todas já foram postadas nos últimos 2 dias!")
                    return False

                print(f"\n[OFERTA SELECIONADA]: {oferta['titulo']}")
                texto_mensagem = formatar_mensagem_oferta(oferta)

                enviou_com_imagem = False

                # 1. Obtém os bytes da imagem do produto (do banco SQLite ou baixa e salva no banco)
                imagem_bytes = obter_ou_baixar_imagem_blob(
                    asin=oferta["asin"],
                    imagem_url_padrao=oferta.get("imagem_url"),
                    context=context
                )

                # 2. Se temos a imagem em bytes, envia como FOTO com o texto na LEGENDA (mensagem única)
                if imagem_bytes:
                    caminho_temp = None
                    try:
                        print("📤 Anexando foto do produto com o texto da oferta na legenda...")
                        
                        if not page.locator('#main').is_visible():
                            page.locator('#pane-side [role="row"]').first.click()
                            time.sleep(1)

                        # Cria um arquivo temporário descartável apenas para upload via navegador
                        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                            tmp.write(imagem_bytes)
                            caminho_temp = tmp.name

                        # 1. Abre o menu de anexos (+) se necessário
                        btn_anexar = page.locator('#main footer button[aria-label*="Anexar"], #main footer button[title*="Anexar"], #main footer span[data-icon="plus"]').first
                        if btn_anexar.is_visible():
                            btn_anexar.click()
                            time.sleep(1)

                        # 2. Localiza o botão "Fotos e vídeos" no menu
                        item_fotos = page.locator('button').filter(has_text=re.compile(r"Fotos e v[ií]deos|Photos & videos", re.I)).first
                        item_fotos.wait_for(state="visible", timeout=8000)

                        # 3. Dispara o seletor de arquivos de forma assíncrona/direta via Playwright (sem abrir janela do Windows)
                        with page.expect_file_chooser(timeout=10000) as fc_info:
                            item_fotos.click()
                        file_chooser = fc_info.value
                        file_chooser.set_files(caminho_temp)

                        # 4. Aguarda a tela de prévia da foto abrir
                        time.sleep(2.5)

                        # 5. Localiza a caixa de legenda específica da mídia (media-caption-input-container)
                        caption_box = page.locator('[data-testid="media-caption-input-container"] [contenteditable="true"]').first
                        if caption_box.count() == 0:
                            for ed in page.locator('div[contenteditable="true"]').all():
                                if ed.get_attribute("data-testid") != "conversation-compose-box-input":
                                    caption_box = ed
                                    break

                        if not caption_box or caption_box.count() == 0:
                            caption_box = page.locator('div[contenteditable="true"][aria-label="Digite uma mensagem"]').first

                        caption_box.wait_for(state="visible", timeout=10000)
                        caption_box.focus()
                        caption_box.click(force=True)
                        time.sleep(0.5)

                        # 6. Insere a mensagem completa da oferta NA LEGENDA DA FOTO
                        page.keyboard.insert_text(texto_mensagem)
                        time.sleep(1.5)

                        # 7. Envia a foto COM a legenda junta (mensagem única)
                        btn_enviar = page.locator('span[data-icon="send"], [data-testid="send"], button[aria-label="Enviar"]').last
                        if btn_enviar.is_visible():
                            btn_enviar.click(force=True)
                        else:
                            page.keyboard.press("Enter")

                        time.sleep(2)
                        # Se por ventura a tela de prévia ainda estiver aberta, envia com Enter
                        if page.locator('button[aria-label="Fechar"], span[data-icon="x"]').is_visible():
                            page.keyboard.press("Enter")
                            time.sleep(2)

                        print("✅ Foto do produto postada com a mensagem completa na legenda (mensagem única)!")
                        enviou_com_imagem = True
                        time.sleep(3)

                    except Exception as e_img:
                        print(f"⚠️ Não foi possível enviar a foto com legenda ({e_img}). Tentando fallback em texto...")
                        try:
                            btn_fechar = page.locator('[aria-label="Fechar"], span[data-icon="x"]').first
                            if btn_fechar.is_visible():
                                btn_fechar.click(force=True)
                                time.sleep(1)
                        except Exception:
                            pass
                    finally:
                        # Deleta o arquivo temporário imediatamente
                        if caminho_temp and os.path.exists(caminho_temp):
                            try:
                                os.remove(caminho_temp)
                            except Exception:
                                pass

                # 3. Fallback: se o envio da foto falhou, posta a mensagem em texto normal
                if not enviou_com_imagem:
                    input_box = page.locator('#main [contenteditable="true"]')
                    if not input_box.is_visible():
                        page.locator('#pane-side [role="row"]').first.click()
                        time.sleep(1)

                    input_box.wait_for(state="visible", timeout=30000)
                    input_box.click()
                    time.sleep(2)
                    
                    page.keyboard.insert_text(texto_mensagem)
                    time.sleep(8)
                    input_box.press("Enter")
                    print("✅ Mensagem enviada com sucesso no grupo!")

                # Registra no banco de dados para bloquear repetição por 2 dias
                marcar_como_postado(oferta["asin"])
                print(f"🔒 Produto {oferta['asin']} bloqueado para repostagem pelos próximos 2 dias.")
                return True
            except Exception as e:
                print(f"❌ Erro ao enviar oferta: {e}")
                return False

        print("Aguardando carregamento das conversas...")
        page.wait_for_selector('#pane-side [role="row"]', state="visible", timeout=30000)
        
        print("Abrindo a conversa...")
        page.locator('#pane-side [role="row"]').first.click()
        time.sleep(2)

        print(f"\n🚀 Bot de postagens iniciado! Ofertas serão postadas a cada {INTERVALO_POSTAGEM_MINUTOS} minutos.")
        print("Pressione Ctrl + C no terminal para encerrar o bot a qualquer momento.\n")

        try:
            while True:
                if page.is_closed():
                    print("Navegador fechado. Finalizando bot.")
                    break

                sucesso = type_in_chat()
                
                proximo_envio = (datetime.now() + timedelta(seconds=INTERVALO_POSTAGEM_SEGUNDOS)).strftime("%H:%M:%S")
                if sucesso:
                    print(f"⏳ Próxima oferta agendada para: {proximo_envio} (daqui a {INTERVALO_POSTAGEM_MINUTOS} minutos).")
                else:
                    print(f"⏳ Nova tentativa agendada para: {proximo_envio} (daqui a {INTERVALO_POSTAGEM_MINUTOS} minutos).")
                
                time.sleep(INTERVALO_POSTAGEM_SEGUNDOS)
        except KeyboardInterrupt:
            print("\n🛑 Bot interrompido pelo usuário.")


if __name__ == "__main__":
    iniciar_zap()
