import os
import csv
import requests
import logging
import asyncio
import unicodedata
import textwrap
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from flask import Flask
import threading
import time
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json

# 🔹 Configuração da autenticação com Google Sheets
# Configurações básicas
TELEGRAM_TOKEN = '8109000267:AAFDXVsitaFwPFLSPul3iyfimpVeBMJ-4No'
GOOGLE_CREDENTIALS_JSON = json.loads(os.getenv("GOOGLE_CREDENTIALS_JSON"))
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
CREDENTIALS = ServiceAccountCredentials.from_json_keyfile_dict(GOOGLE_CREDENTIALS_JSON, SCOPE)
gc = gspread.authorize(CREDENTIALS)

# 🔹 Função para salvar nova escola na planilha
def salvar_escola_na_planilha(chat_id, nome, funcao, escola, telefone, email, endereco, localizacao):
    try:
        planilha = gc.open_by_url("https://docs.google.com/spreadsheets/d/115SXqaQ2T0xPzVQ9enFt4C-Ns1QOFBJfDSqKi1YaPKM")
        aba = planilha.worksheet("Escolas")  # Certifique-se de que a aba se chama "Escolas"

        # Adicionar nova escola na planilha
        aba.append_row([chat_id, nome, funcao, escola, telefone, email, endereco, localizacao])

        logging.info(f"✅ Escola {escola} adicionada à planilha com sucesso.")
        return True
    except Exception as e:
        logging.error(f"❌ Erro ao salvar escola na planilha: {e}")
        return False

# Inicializando Flask
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot está ativo!"

# 🔹 Configuração de logs detalhados
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# 🔹 Função para iniciar o servidor Flask em uma thread separada
def iniciar_servidor():
    logging.info("🌐 Iniciando o servidor Flask...")
    app.run(host="0.0.0.0", port=8080, debug=False, use_reloader=False)

# Função para normalizar texto (remover acentos e deixar tudo maiúsculo)
def normalizar_texto(texto):
    return unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('utf-8').upper()

# Função para carregar os dados diretamente do Google Sheets
def carregar_dados_csv():
    global dados_planilha, administradores
    try:
        # Conectar à planilha do Google Sheets
        planilha = gc.open_by_url("https://docs.google.com/spreadsheets/d/115SXqaQ2T0xPzVQ9enFt4C-Ns1QOFBJfDSqKi1YaPKM")
        logging.info("✅ Conectado à planilha do Google Sheets")

        # Acessar as abas "Escolas" e "Administradores"
        aba_escolas = planilha.worksheet("Escolas")
        aba_admins = planilha.worksheet("Administradores")

        # Ler dados das escolas
        escolas = aba_escolas.get_all_values()
        cabecalho = escolas[0]  # Pega a primeira linha como referência
        dados_planilha = [dict(zip(cabecalho, linha)) for linha in escolas[1:]]

        # Ler administradores
        administradores = [linha[0] for linha in aba_admins.get_all_values()[1:]]  # Pega a primeira coluna (Chat ID)

        logging.info("✅ Dados da planilha carregados com sucesso.")

    except Exception as e:
        logging.error(f"❌ Erro ao carregar planilha: {e}")

# Função para manter a planilha sempre atualizada
def atualizar_planilha_periodicamente():
    while True:
        carregar_dados_csv()
        time.sleep(300)  # Atualiza a cada 5 minutos

# Função para buscar dados da escola pelo Chat ID
def buscar_dados_escola(chat_id):
    for linha in dados_planilha:
        if linha['Chat ID'] == str(chat_id):
            return linha
    return None

# Função para obter administradores (busca na lista carregada)
def obter_administradores():
    return administradores  # Lista já carregada no carregar_dados_csv()

# Função para exibir a mensagem de boas-vindas
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mensagem_boas_vindas = (
        "👋 *Bem-vindo ao Guardião Escolar!*\n\n"
        "Este Canal é utilizado para comunicação rápida e eficaz em situações de emergência. "
        "Siga as instruções abaixo para enviar alertas corretamente.\n\n"
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


# Função para exibir a ajuda
async def ajuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

emergencia_ativa = False  # Controle de emergência

# Função para lidar com mensagens recebidas
async def mensagem_recebida(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global emergencia_ativa  # Controle de emergência
    try:
        chat_id = str(update.message.chat_id)
        texto = update.message.text
        dados_escola = buscar_dados_escola(chat_id)

        # Verifica se o Chat ID está cadastrado na planilha
        if not dados_escola:
            # Enviar dados do usuário para os administradores automaticamente
            mensagem_admin = (
                f"⚠️ *Novo usuário tentando interagir com o bot!*\n\n"
                f"📌 *Chat ID*: `{chat_id}`\n"
                f"👤 *Nome*: {update.message.from_user.first_name}\n"
                f"🔹 *Username*: @{update.message.from_user.username or 'Sem username'}\n\n"
                f"Para cadastrá-lo, utilize:\n"
                f"`/cadastrar {chat_id};<Nome>;<Função>;<Escola>;<Telefone>;<Email>;<Endereço>;<Localização>`"
            )

            for admin_id in obter_administradores():
                await context.bot.send_message(chat_id=admin_id, text=mensagem_admin, parse_mode='Markdown')

            # Se o usuário digitou "CADASTRO", ele recebe uma mensagem informativa
            if texto.upper() == "CADASTRO":
                await update.message.reply_text(
                    "📌 Sua solicitação foi enviada para análise. Um administrador entrará em contato em breve.",
                    parse_mode='Markdown'
                )
            else:
                # Resposta padrão para usuários não cadastrados
                await update.message.reply_text(
                    "⚠️ *Canal exclusivo para as Instituições de Ensino cadastradas.*\n"
                    "*Favor entrar em contato com o 190 em caso de emergência.*\n"
                    "*Caso tenha interesse em se cadastrar, envie a mensagem \"CADASTRO\".*",
                    parse_mode='Markdown'
                )
            return  # Finaliza aqui para evitar processamento extra

        # 🔹 Normaliza o texto recebido
        texto_normalizado = normalizar_texto(texto)

        palavra_chave_encontrada = False
        for palavra in ["AGRESSOR", "AGRESSORES", "HOMICIDIO", "REFEM", "REFENS", "BOMBA", "BOMBAS", "ATAQUE", "EXPLOSÃO", "TESTE"]:
            if palavra in texto_normalizado:
                palavra_chave_encontrada = True
                global emergencia_ativa
                emergencia_ativa = True  # Ativando emergência

                # Enviar confirmação para a escola que enviou a mensagem
                await update.message.reply_text(
                    "Mensagem Recebida, A Equipe do Guardião Escolar está a Caminho."
                )

                # Preparar mensagem detalhada para os administradores
                mensagem_para_admins = (
                    f"⚠️ *Mensagem de emergência recebida:*\n\n"
                    f"🏫 *Escola*: {dados_escola['Escola']}\n"
                    f"👤 *Servidor*: {dados_escola['Nome']}\n"
                    f"👤 *Função*: {dados_escola['Função']}\n"
                    f"📞 *Telefone*: {dados_escola['Telefone']}\n"
                    f"✉️ *Email*: {dados_escola['Email']}\n"
                    f"📍 *Endereço*: {dados_escola['Endereço']}\n"
                    f"🌐 *Localização*: {dados_escola['Localização']}\n\n"
                    f"📩 *Mensagem original*: {texto}\n"
                    f"👤 *Usuário*: @{update.message.from_user.username or 'Sem username'} "
                    f"(Nome: {update.message.from_user.first_name}, Chat ID: {chat_id})"
                )

                # Enviar mensagem detalhada para cada administrador
                for admin_id in obter_administradores():
                    await context.bot.send_message(
                        chat_id=admin_id,
                        text=mensagem_para_admins,
                        parse_mode='Markdown'
                    )

                emergencia_ativa = False  # Finaliza a emergência
                break

        if not palavra_chave_encontrada:
            mensagem_erro = (
                "⚠️ Este canal é exclusivo para comunicação de emergências.\n\n"
                "Siga as orientações do menu /ajuda. Se você estiver em uma situação de emergência, "
                "lembre-se de inserir a palavra-chave correspondente e incluir o máximo de detalhes possível.\n"
                "📞 Inclua também um número de contato para que possamos falar com você."
            )
            await update.message.reply_text(mensagem_erro)

    except Exception:
        emergencia_ativa = False
        exibir_erro("Erro ao processar a mensagem recebida.")

# 🔹 Função para notificar administradores sobre um pedido de cadastro
async def notificar_admin_solicitacao_cadastro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.from_user.id)
    first_name = update.message.from_user.first_name or "Não informado"
    username = f"@{update.message.from_user.username}" if update.message.from_user.username else "Sem username"

    mensagem = (
        f"👤 *Novo pedido de cadastro*\n\n"
        f"📌 *Chat ID*: `{chat_id}`\n"
        f"👤 *Nome*: {first_name}\n"
        f"🔹 *Username*: {username}\n\n"
        f"Para aprovar este usuário, utilize o comando:\n"
        f"`/cadastrar {chat_id};<Nome>;<Função>;<Escola>;<Telefone>;<Email>;<Endereço>;<Localização>`"
    )

    # 🔹 Enviar para todos os administradores
    for admin_id in obter_administradores():
        await context.bot.send_message(chat_id=admin_id, text=mensagem, parse_mode='Markdown')

    # Confirmação para o usuário
    await update.message.reply_text("📌 Sua solicitação foi enviada para análise.")

# 🔹 Função para cadastrar um novo usuário na planilha
async def cadastrar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    administradores = obter_administradores()

    # 🔹 Verifica se quem está cadastrando é um administrador
    if str(update.message.chat_id) not in administradores:
        await update.message.reply_text("⚠️ Apenas administradores podem cadastrar novas escolas.")
        return

    # 🔹 Captura e valida os dados enviados no comando
    dados = " ".join(context.args)
    campos = dados.split(";")

    if len(campos) != 8:
        await update.message.reply_text(
            "⚠️ *Formato inválido!*\n\n"
            "Use o seguinte formato:\n"
            "`/cadastrar <ChatID>;<Nome>;<Função>;<Escola>;<Telefone>;<Email>;<Endereço>;<Localização>`",
            parse_mode="Markdown"
        )
        return

    chat_id, nome, funcao, escola, telefone, email, endereco, localizacao = campos

    # 🚨 Bloquear cadastro duplicado
    if buscar_dados_escola(chat_id):
        await update.message.reply_text("⚠️ Esta escola já está cadastrada!")
        return

    # 🔹 Adicionar a nova escola na planilha
    sucesso = adicionar_escola(chat_id, nome, funcao, escola, telefone, email, endereco, localizacao)

    if sucesso:
        await update.message.reply_text(f"✅ *Escola {escola} cadastrada com sucesso!*", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Erro ao salvar os dados na planilha.")

# 🔹 Função para adicionar uma nova escola à memória e salvar na planilha
def adicionar_escola(chat_id, nome, funcao, escola, telefone, email, endereco, localizacao):
    global dados_planilha
    try:
        nova_escola = {
            "Chat ID": chat_id,
            "Nome": nome,
            "Função": funcao,
            "Escola": escola,
            "Telefone": telefone,
            "Email": email,
            "Endereço": endereco,
            "Localização": localizacao
        }
        dados_planilha.append(nova_escola)  # Adiciona localmente
        sucesso = salvar_escola_na_planilha(chat_id, nome, funcao, escola, telefone, email, endereco, localizacao)

        if sucesso:
            logging.info(f"✅ Nova escola cadastrada e salva na planilha: {escola}")
            return True
        else:
            logging.error(f"❌ Erro ao salvar escola {escola} na planilha.")
            return False
    except Exception as e:
        logging.error(f"❌ Erro ao adicionar escola: {e}")
        return False

# 🔹 Função para listar todas as escolas cadastradas (apenas para administradores)
async def listar_escolas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)

    # 🚨 Verifica se o usuário é um administrador
    if chat_id not in obter_administradores():
        await update.message.reply_text("⚠️ Apenas administradores podem visualizar a lista de escolas cadastradas.")
        return

    # Verifica se há escolas cadastradas
    if not dados_planilha:
        await update.message.reply_text("📌 Nenhuma escola cadastrada ainda.")
        return

    # 🔹 Monta a lista de escolas formatada
    mensagem = "🏫 *Lista de Escolas Cadastradas:*\n\n"
    for idx, escola in enumerate(dados_planilha, start=1):
        mensagem += f"{idx}. *{escola['Escola']}* - {escola['Nome']} ({escola['Função']})\n"

    await update.message.reply_text(mensagem, parse_mode='Markdown')


# 🔹 Função para enviar alerta e tocar áudio no Telegram
async def enviar_alerta(context: ContextTypes.DEFAULT_TYPE, dados_escola, tipo, detalhes):
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

    arquivo_audio = "/mnt/data/teste.mp3" if tipo == "TESTE" else "/mnt/data/alerta.mp3"

    for admin_id in obter_administradores():
        try:
            await context.bot.send_message(chat_id=admin_id, text=mensagem, parse_mode='Markdown')

            with open(arquivo_audio, "rb") as audio:
                await context.bot.send_audio(chat_id=admin_id, audio=audio)

            logging.info(f"🚨 Alerta ({tipo}) enviado para {admin_id} com áudio.")
        except Exception as e:
            logging.error(f"❌ Erro ao enviar alerta para {admin_id}: {e}")

# 🔹 Função para rodar o Bot do Telegram corretamente (Assíncrono)
async def iniciar_bot():
    logging.info("🤖 Iniciando o bot do Telegram...")
    
    app_telegram = Application.builder().token(TELEGRAM_TOKEN).build()

    # 🔹 Adicionar comandos ao bot
    app_telegram.add_handler(CommandHandler("start", start))
    app_telegram.add_handler(CommandHandler("ajuda", ajuda))
    app_telegram.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mensagem_recebida))
    app_telegram.add_handler(CommandHandler("listarescolas", listar_escolas))

    # 🔹 Iniciar atualização automática da planilha
    threading.Thread(target=atualizar_planilha_periodicamente, daemon=True).start()

    # 🔹 Iniciar o bot
    await app_telegram.run_polling()

# 🔹 Configuração principal do programa
async def main():
    # 🔹 Carregar os dados da planilha antes de iniciar o bot
    carregar_dados_csv()

    # 🔹 Iniciar o bot do Telegram
    await iniciar_bot()

if __name__ == "__main__":
    # 🔹 Iniciar o servidor Flask em uma thread separada
    threading.Thread(target=iniciar_servidor, daemon=True).start()

    # 🔹 Capturar o loop de eventos existente no Render
    loop = asyncio.get_event_loop()

    # 🔹 Se o loop já estiver rodando (como no Render), cria uma task para rodar o bot sem travar
    if loop.is_running():
        logging.info("🔄 Loop de eventos já está rodando, iniciando o bot como uma tarefa assíncrona...")
        loop.create_task(main())  # Usa `create_task()` para rodar sem conflitos
    else:
        logging.info("▶️ Iniciando novo loop de eventos para o bot...")
        loop.run_until_complete(main())  # Para ambientes locais onde o loop não está rodando
