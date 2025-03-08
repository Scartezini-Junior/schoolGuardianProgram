import os
import csv
import json
import logging
import asyncio
import textwrap
import unicodedata
import gspread
import aiohttp
import requests
from google.oauth2.service_account import Credentials
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from telegram.ext import Application, CommandHandler, MessageHandler, filters

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# 🔹 Carregar credenciais do JSON armazenado no Render
GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON")

try:
    GOOGLE_CREDENTIALS = json.loads(GOOGLE_CREDENTIALS_JSON)
    creds = Credentials.from_service_account_info(GOOGLE_CREDENTIALS, scopes=SCOPES)
except json.JSONDecodeError:
    raise ValueError("❌ Erro: JSON de credenciais malformado.")

# 🔹 Adicionar um novo registro na planilha
def adicionar_escola(chat_id, nome, funcao, escola, telefone, email, endereco, localizacao, nome_aba="Escolas"):
    try:
        planilha = conectar_planilha()
        aba = planilha.worksheet(nome_aba)

        # 🚨 Verifica se já existe esse Chat ID
        registros = aba.get_all_records()
        for registro in registros:
            if str(registro["Chat ID"]) == str(chat_id):
                print("⚠️ Escola já cadastrada.")
                return False

        nova_linha = [chat_id, nome, funcao, escola, telefone, email, endereco, localizacao]
        linha_vazia = len(aba.get_all_values()) + 1
        aba.insert_row(nova_linha, linha_vazia)

        print(f"✅ Nova escola cadastrada: {escola}")
        return True
    except Exception as e:
        print(f"❌ Erro ao adicionar escola: {e}")
        return False

# 🔹 Atualizar dados de uma escola existente
async def atualizar_escola(update: Update, context, chat_id, coluna, novo_valor, nome_aba="Escolas"):
    try:
        planilha = conectar_planilha()
        aba = planilha.worksheet(nome_aba)
        
        registros = aba.get_all_records()
        colunas = [c.upper() for c in aba.row_values(1)]  # Converte colunas para maiúsculas
        coluna = coluna.upper()  # Evita erro por capitalização

        # 🚨 Verifica se a coluna existe
        if coluna not in colunas:
            await update.message.reply_text("⚠️ Coluna informada não existe.")
            print(f"⚠️ Erro: Coluna '{coluna}' não encontrada na planilha '{nome_aba}'.")
            return False

        # 🚨 Atualiza os dados se encontrar o Chat ID correspondente
        for idx, registro in enumerate(registros, start=2):
            if str(registro.get("Chat ID", "")) == str(chat_id):  # Usa .get() para evitar KeyError
                aba.update_cell(idx, colunas.index(coluna) + 1, novo_valor)
                await update.message.reply_text(f"✅ {coluna} atualizado para {novo_valor}.")
                print(f"✅ Atualização bem-sucedida: {coluna} do Chat ID {chat_id} atualizado para {novo_valor}.")
                return True

        # 🚨 Se não encontrar o Chat ID
        await update.message.reply_text("⚠️ Chat ID não encontrado.")
        print(f"⚠️ Erro: Chat ID {chat_id} não encontrado na planilha '{nome_aba}'.")
        return False

    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao atualizar a escola.")
        print(f"❌ Erro ao atualizar escola: {e}")
        return False

# 🔹 Remover uma escola da planilha
async def remover_escola(update: Update, context, chat_id, nome_aba="Escolas"):
    try:
        planilha = conectar_planilha()
        aba = planilha.worksheet(nome_aba)
        
        registros = aba.get_all_records()
        for idx, registro in enumerate(registros, start=2):
            if str(registro["Chat ID"]) == str(chat_id):
                aba.delete_rows(idx)
                await update.message.reply_text(f"✅ Escola com Chat ID {chat_id} removida.")
                return True  # Sucesso

        await update.message.reply_text("⚠️ Chat ID não encontrado.")
        return False  # Falha
    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao remover escola: {e}")
        return False  # Falha devido a erro

# 🔹 Lista temporária para armazenar novos cadastros pendentes
cadastros_pendentes = {}

# 🔹 Função para remover acentos e normalizar o texto
def normalizar_texto(texto):
    return unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('utf-8').upper()

# 🔹 Configurações (Pegando do ambiente para segurança e flexibilidade)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")  # 🔒 Pegando o token do ambiente
CSV_URL = os.getenv("CSV_URL")  # 🔄 Permite mudar a planilha sem editar o código

# 🔹 Função para obter administradores
def obter_administradores():
    try:
        planilha = conectar_planilha()
        aba = planilha.worksheet("Administradores")  
        return [linha[0] for linha in aba.get_all_values()[1:]]  # Pula a linha do cabeçalho
    except Exception as e:
        print(f"❌ Erro ao obter administradores: {e}")
        return []

# 🔹 Função para adicionar um administrador
def adicionar_admin(chat_id):
    try:
        planilha = conectar_planilha()
        aba = planilha.worksheet("Administradores")

        admins = obter_administradores()
        if str(chat_id) in admins:
            print(f"⚠️ Administrador {chat_id} já está cadastrado.")
            return False

        aba.append_row([chat_id])
        print(f"✅ Novo administrador adicionado: {chat_id}")
        return True
    except Exception as e:
        print(f"❌ Erro ao adicionar administrador: {e}")
        return False

# 🔹 Função para remover um administrador
def remover_admin(chat_id):
    try:
        planilha = conectar_planilha()
        aba = planilha.worksheet("Administradores")
        registros = aba.get_all_values()

        for idx, linha in enumerate(registros, start=1):
            if str(linha[0]) == str(chat_id):
                aba.delete_rows(idx)
                print(f"✅ Administrador {chat_id} removido.")
                return True

        print("⚠️ Administrador não encontrado.")
        return False
    except Exception as e:
        print(f"❌ Erro ao remover administrador: {e}")
        return False

# 🔹 Variáveis globais
dados_planilha = []
emergencia_ativa = False  # Controle de emergência

# 🔹 Função para exibir a mensagem de boas-vindas
async def start(update: Update, context):
    mensagem_boas_vindas = (
        "👋 *Bem-vindo ao Guardião Escolar!*\n\n"
        "Este Canal é utilizado para comunicação rápida e eficaz em situações de emergência.\n\n"
        "⚠️ *Quando acionar?*\n"
        "- *Agressor Ativo*: Atos de violência contínuos e deliberados contra a escola.\n"
        "- *Homicídio ou Tentativa de Homicídio*: Atos contra a vida.\n"
        "- *Tomada de Refém*: Manter alguém sob ameaça para alcançar algum objetivo.\n"
        "- *Ameaça de Explosivos*: Suspeita ou evidência de explosivo no perímetro escolar.\n\n"
        "📋 *Como enviar uma mensagem de emergência?*\n"
        "1️⃣ *Inclua uma palavra-chave* na mensagem:\n"
        "- AGRESSOR\n- HOMICÍDIO\n- REFÉM\n- BOMBA\n- TESTE DE ATIVAÇÃO\n"
        "2️⃣ *Envie os detalhes do ocorrido*, incluindo:\n"
        "- Localização exata\n- Número de envolvidos\n- Estado das vítimas\n- Meios utilizados pelo agressor."
    )
    await update.message.reply_text(mensagem_boas_vindas, parse_mode='Markdown')

# 🔹 Função para exibir a ajuda
async def ajuda(update: Update, context):
    mensagem_ajuda = (
        "📋 *Como usar o Guardião Escolar:*\n\n"
        "1️⃣ *Envie uma mensagem contendo a palavra-chave*, seguida dos detalhes do ocorrido.\n"
        "2️⃣ *Inclua informações importantes*, como:\n"
        "- Localização exata\n"
        "- Número de envolvidos\n"
        "- Estado das vítimas\n"
        "- Meios utilizados pelo agressor\n\n"
        "⚠️ *Importante*: Mantenha-se seguro e envie as informações apenas se isso não colocar sua segurança em risco."
    )
    await update.message.reply_text(mensagem_ajuda, parse_mode='Markdown')

# 🔹 Função para carregar os dados da planilha (agora assíncrona)
async def carregar_dados_csv():
    global dados_planilha
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(CSV_URL) as response:
                response.raise_for_status()
                decoded_content = await response.text()
                reader = csv.DictReader(decoded_content.splitlines())
                dados_planilha = list(reader) if decoded_content else []
                print("📌 Dados da planilha atualizados com sucesso.")
    except Exception as e:
        print(f"❌ Erro ao carregar a planilha: {e}") 

# 🔹 Função para exibir erro (sem interface gráfica)
def exibir_erro(mensagem):
    if emergencia_ativa:
        print("Erro suprimido durante emergência.")
        return
    print(f"❌ ERRO: {mensagem}")  

# 🔹 Função para buscar dados da escola pelo ID do chat
def buscar_dados_escola(chat_id):
    try:
        for linha in dados_planilha:
            if str(linha.get('Chat ID', '')) == str(chat_id):  # Evita erro caso a chave 'Chat ID' não exista
                return linha
        print(f"⚠️ Chat ID {chat_id} não encontrado.")
        return None
    except Exception as e:
        print(f"❌ Erro ao buscar dados da escola: {e}")  
        return None

async def mensagem_recebida(update: Update, context):
    """Processa mensagens recebidas e identifica emergências."""
    global emergencia_ativa  
    try:
        chat_id = str(update.message.chat_id)
        texto = update.message.text.strip()  # Remove espaços extras
        dados_escola = buscar_dados_escola(chat_id)

        # 🔹 Verifica se o Chat ID está cadastrado
        if not dados_escola:
            await processar_novo_usuario(update, context)
            return  # Finaliza para evitar processamento extra

        # 🔹 Normaliza o texto recebido
        texto_normalizado = normalizar_texto(texto)

        # 🔹 Lista de palavras-chave para emergência (usando conjunto para busca otimizada)
        palavras_chave = {"AGRESSOR", "AGRESSORES", "HOMICIDIO", "REFEM", "REFENS",
                          "BOMBA", "BOMBAS", "ATAQUE", "EXPLOSÃO", "TESTE"}

        if any(palavra in texto_normalizado for palavra in palavras_chave):
            emergencia_ativa = True  # Ativando emergência

            # 🔹 Enviar confirmação ao usuário
            await update.message.reply_text(
                "🚨 Mensagem Recebida! A Equipe do Guardião Escolar está a Caminho."
            )

            # 🔹 Criar mensagem detalhada para os administradores
            mensagem_para_admins = (
                f"⚠️ *Mensagem de emergência recebida:*\n\n"
                f"🏫 *Escola*: {dados_escola.get('Escola', 'Não informado')}\n"
                f"👤 *Servidor*: {dados_escola.get('Nome', 'Não informado')}\n"
                f"👤 *Função*: {dados_escola.get('Função', 'Não informado')}\n"
                f"📞 *Telefone*: {dados_escola.get('Telefone', 'Não informado')}\n"
                f"✉️ *Email*: {dados_escola.get('Email', 'Não informado')}\n"
                f"📍 *Endereço*: {dados_escola.get('Endereço', 'Não informado')}\n"
                f"🌐 *Localização*: {dados_escola.get('Localização', 'Não informado')}\n\n"
                f"📩 *Mensagem original*: {texto}\n"
                f"👤 *Usuário*: @{update.message.from_user.username or 'Sem username'} "
                f"(Nome: {update.message.from_user.first_name}, Chat ID: {chat_id})"
            )

            # 🔹 Enviar mensagem detalhada para todos os administradores
            await asyncio.gather(*[
                context.bot.send_message(chat_id=admin_id, text=mensagem_para_admins, parse_mode='Markdown')
                for admin_id in ADMIN_CHAT_IDS
            ])

            emergencia_ativa = False  # Finaliza a emergência
            return  # Sai da função após enviar o alerta

        # 🔹 Se não for uma emergência, responde com instruções
        await update.message.reply_text(
            "⚠️ *Este canal é exclusivo para comunicação de emergências.*\n\n"
            "Siga as orientações do menu /ajuda. Se você estiver em uma situação de emergência, "
            "lembre-se de inserir a palavra-chave correspondente e incluir o máximo de detalhes possível.\n"
            "📞 Inclua também um número de contato para que possamos falar com você.",
            parse_mode='Markdown'
        )

    except Exception as e:
        emergencia_ativa = False  # Garante que o estado não fique preso em True
        logging.exception(f"❌ Erro ao processar a mensagem recebida (Chat ID: {chat_id}): {e}")

# 🔹 Função para enviar alerta e tocar áudio no Telegram
async def enviar_alerta(context, dados_escola, tipo, detalhes):
    detalhes_quebrados = textwrap.fill(detalhes, width=80)

    mensagem = (
        f"🚨 *ALERTA DE EMERGÊNCIA*\n\n"
        f"⚠️ *Tipo*: {tipo}\n"
        f"🏫 *Escola*: {dados_escola.get('Escola', 'Não informado')}\n"
        f"👤 *Servidor*: {dados_escola.get('Nome', 'Não informado')}\n"
        f"📞 *Telefone*: {dados_escola.get('Telefone', 'Não informado')}\n"
        f"📍 *Localização*: {dados_escola.get('Localização', 'Não informado')}\n\n"
        f"📝 *Detalhes*: {detalhes_quebrados}"
    )

    arquivo_audio = "teste.mp3" if tipo == "TESTE" else "alerta.mp3"

    async def enviar_para_admin(admin_id):
        try:
            await context.bot.send_message(chat_id=admin_id, text=mensagem, parse_mode='Markdown')

            with open(arquivo_audio, "rb") as audio:
                await context.bot.send_audio(chat_id=admin_id, audio=audio)

            print(f"🚨 Alerta ({tipo}) enviado para {admin_id} com áudio.")
        except Exception as e:
            logging.error(f"❌ Erro ao enviar alerta para {admin_id}: {e}")

    await asyncio.gather(*[enviar_para_admin(admin_id) for admin_id in ADMIN_CHAT_IDS])

# 🔹 Função para processar novos usuários e enviar para os administradores com botões interativos
async def enviar_alerta(context, dados_escola, tipo, detalhes):
    detalhes_quebrados = textwrap.fill(detalhes, width=80)

    mensagem = (
        f"🚨 *ALERTA DE EMERGÊNCIA*\n\n"
        f"⚠️ *Tipo*: {tipo}\n"
        f"🏫 *Escola*: {dados_escola.get('Escola', 'Não informado')}\n"
        f"👤 *Servidor*: {dados_escola.get('Nome', 'Não informado')}\n"
        f"📞 *Telefone*: {dados_escola.get('Telefone', 'Não informado')}\n"
        f"📍 *Localização*: {dados_escola.get('Localização', 'Não informado')}\n\n"
        f"📝 *Detalhes*: {detalhes_quebrados}"
    )

    arquivo_audio = "teste.mp3" if tipo == "TESTE" else "alerta.mp3"

    async def enviar_para_admin(admin_id):
        try:
            await context.bot.send_message(chat_id=admin_id, text=mensagem, parse_mode='Markdown')

            with open(arquivo_audio, "rb") as audio:
                await context.bot.send_audio(chat_id=admin_id, audio=audio)

            print(f"🚨 Alerta ({tipo}) enviado para {admin_id} com áudio.")
        except Exception as e:
            logging.error(f"❌ Erro ao enviar alerta para {admin_id}: {e}")

    await asyncio.gather(*[enviar_para_admin(admin_id) for admin_id in ADMIN_CHAT_IDS])

# 🔹 Função para lidar com a escolha do administrador
async def callback_handler(update: Update, context):
    query: CallbackQuery = update.callback_query
    query_data = query.data
    chat_id = query.message.chat_id

    if str(chat_id) not in ADMIN_CHAT_IDS:
        await query.answer("⚠️ Você não tem permissão para executar esta ação.", show_alert=True)
        return

    if query_data.startswith("aprovar_"):
        chat_id = query_data.split("_")[1]
        usuario = cadastros_pendentes.pop(chat_id, None)

        if usuario:
            await query.edit_message_text(
                text=f"✅ *Usuário {usuario['Nome']} aprovado!* Agora, envie os dados adicionais no formato:\n\n"
                     "`/cadastrar <ChatID>;<Nome>;<Função>;<Escola>;<Telefone>;<Email>;<Endereço>;<Localização Google Maps>`",
                parse_mode="Markdown"
            )
        else:
            await query.edit_message_text("⚠️ Usuário já foi processado ou não encontrado.")

    elif query_data.startswith("rejeitar_"):
        chat_id = query_data.split("_")[1]
        usuario = cadastros_pendentes.pop(chat_id, None)

        if usuario:
            await query.edit_message_text(f"❌ *Usuário {usuario['Nome']} foi rejeitado e não será cadastrado.*")
        else:
            await query.edit_message_text("⚠️ Usuário já foi rejeitado ou não encontrado.")

# 🔹 Função para cadastrar um novo usuário na planilha
async def cadastrar(update: Update, context):
    try:
        dados = " ".join(context.args)
        campos = dados.split(";")

        if len(campos) != 8:
            await update.message.reply_text("⚠️ Formato inválido! Use `/cadastrar <ChatID>;<Nome>;<Função>;<Escola>;<Telefone>;<Email>;<Endereço>;<Link Google Maps>`")
            return

        chat_id, nome, funcao, escola, telefone, email, endereco, localizacao = campos

        # 🔹 Agora usamos a função correta para adicionar à planilha
        sucesso = adicionar_escola(chat_id, nome, funcao, escola, telefone, email, endereco, localizacao)

        if sucesso:
            await update.message.reply_text(f"✅ *Usuário {nome} cadastrado com sucesso!*", parse_mode="Markdown")
            print(f"✅ Novo cadastro adicionado: {nome}")
        else:
            await update.message.reply_text("❌ Erro ao salvar os dados na planilha.")
            print(f"❌ Erro ao salvar o usuário {nome} na planilha.")

    except Exception as e:
        await update.message.reply_text("❌ Erro ao processar o cadastro.")
        logging.error(f"❌ Erro ao cadastrar novo usuário: {e}")

# 🔹 Função para adicionar um novo administrador
async def add_admin(update: Update, context):
    if len(context.args) != 1:
        await update.message.reply_text("⚠️ Uso correto: `/addadmin <ChatID>`")
        return

    novo_admin = context.args[0]

    # Verifica se já está cadastrado
    administradores = obter_administradores()
    if novo_admin in administradores:
        await update.message.reply_text("⚠️ Este usuário já é um administrador.")
        return

    # Adiciona na planilha
    sucesso = adicionar_admin(novo_admin)
    if sucesso:
        await update.message.reply_text(f"✅ *Usuário {novo_admin} agora é um administrador!*")
        print(f"✅ Novo administrador adicionado: {novo_admin}")
    else:
        await update.message.reply_text("❌ Erro ao adicionar administrador.")

# 🔹 Função para remover um administrador
async def remove_admin(update: Update, context):
    if len(context.args) != 1:
        await update.message.reply_text("⚠️ Uso correto: `/removeadmin <ChatID>`")
        return

    admin_remover = context.args[0]

    administradores = obter_administradores()
    if admin_remover not in administradores:
        await update.message.reply_text("⚠️ Este usuário não é um administrador.")
        return

    # Remove da planilha
    sucesso = remover_admin(admin_remover)
    if sucesso:
        await update.message.reply_text(f"❌ *Usuário {admin_remover} foi removido dos administradores.*")
        print(f"❌ Administrador removido: {admin_remover}")
    else:
        await update.message.reply_text("❌ Erro ao remover administrador.")

# 🔹 Função para atualizar a planilha periodicamente (agora assíncrona)
async def atualizar_planilha_periodicamente():
    while True:
        try:
            await carregar_dados_csv()
            print("📌 Planilha atualizada.")
        except Exception as e:
            logging.error(f"❌ Erro ao atualizar a planilha: {e}")
        await asyncio.sleep(300)  # Aguarda 5 minutos antes de atualizar novamente


# 🔹 Função para iniciar o bot
async def iniciar_bot():
    try:
        app = Application.builder().token(TELEGRAM_TOKEN).build()

        # 🔹 Adicionar comandos ao bot
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("ajuda", ajuda))
        app.add_handler(CommandHandler("addadmin", add_admin))
        app.add_handler(CommandHandler("removeadmin", remove_admin))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mensagem_recebida))

        # 🔹 Iniciar a atualização da planilha em segundo plano
        asyncio.create_task(atualizar_planilha_periodicamente())

        print("✅ Bot iniciado!")
        await app.run_polling()

    except Exception as e:
        logging.error(f"❌ Erro ao iniciar o bot: {e}")
