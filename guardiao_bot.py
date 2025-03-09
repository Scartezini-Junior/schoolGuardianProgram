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
from telegram import Update, CallbackQuery
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from flask import Flask
import threading
import time

# 🔹 Configuração de logs detalhados
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# 🔹 Criando um servidor Flask Fake para manter o Render "feliz"
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot está rodando!"

# 🔹 Função para iniciar o servidor Flask em uma thread separada
def iniciar_servidor():
    logging.info("🌐 Iniciando o servidor Flask...")
    app.run(host="0.0.0.0", port=8080, debug=False, use_reloader=False)

# 🔹 Ping para manter o Render ativo
RENDER_URL = "https://schoolguardianprogram.onrender.com"  # 🚀 ALTERE AQUI COM SUA URL REAL

def manter_online():
    while True:
        try:
            requests.get(RENDER_URL)
            logging.info("✅ Ping enviado para manter a instância ativa.")
        except Exception as e:
            logging.error(f"⚠️ Erro ao enviar ping: {e}")
        time.sleep(600)  # ⏳ Aguarda 10 minutos antes do próximo ping

# 🔹 Configuração de autenticação do Google Sheets
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# 🔹 Ler variáveis de ambiente
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_USER_IDS = os.getenv("ADMIN_USER_IDS", "").strip("[]").replace('"', '').split(",")
ADMIN_USER_IDS = [x.strip() for x in ADMIN_USER_IDS if x.strip()]
GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON")

# 🔹 Garantir que o JSON de credenciais seja interpretado corretamente
if GOOGLE_CREDENTIALS_JSON:
    GOOGLE_CREDENTIALS = json.loads(GOOGLE_CREDENTIALS_JSON)
else:
    GOOGLE_CREDENTIALS = None

CSV_URL = os.getenv("CSV_URL")


# 🔹 Adicionar um novo registro na planilha
def adicionar_escola(user_id, nome, funcao, escola, telefone, email, endereco, localizacao, nome_aba="Escolas"):
    try:
        planilha = conectar_planilha()
        aba = planilha.worksheet(nome_aba)

        # 🚨 Verifica se já existe esse User ID
        registros = aba.get_all_records()
        for registro in registros:
            if str(registro["User ID"]) == str(user_id):  # ✅ CORRETO
                print("⚠️ Escola já cadastrada.")
                return False

        nova_linha = [user_id, nome, funcao, escola, telefone, email, endereco, localizacao]
        linha_vazia = len(aba.get_all_values()) + 1
        aba.insert_row(nova_linha, linha_vazia)

        print(f"✅ Nova escola cadastrada: {escola}")
        return True
    except Exception as e:
        print(f"❌ Erro ao adicionar escola: {e}")
        return False

# 🔹 Atualizar dados de uma escola existente
async def atualizar_escola(update: Update, context, user_id, coluna, novo_valor, nome_aba="Escolas"):
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

        # 🚨 Atualiza os dados se encontrar o User ID correspondente
        for idx, registro in enumerate(registros, start=2):
            if str(registro.get("User ID", "")) == str(user_id):  # Usa .get() para evitar KeyError
                aba.update_cell(idx, colunas.index(coluna) + 1, novo_valor)
                await update.message.reply_text(f"✅ {coluna} atualizado para {novo_valor}.")
                print(f"✅ Atualização bem-sucedida: {coluna} do User ID {user_id} atualizado para {novo_valor}.")
                return True

        # 🚨 Se não encontrar o User ID
        await update.message.reply_text("⚠️ User ID não encontrado.")
        print(f"⚠️ Erro: User ID {user_id} não encontrado na planilha '{nome_aba}'.")
        return False

    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao atualizar a escola.")
        print(f"❌ Erro ao atualizar escola: {e}")
        return False

# 🔹 Remover uma escola da planilha
async def remover_escola(update: Update, context, user_id, nome_aba="Escolas"):
    try:
        planilha = conectar_planilha()
        aba = planilha.worksheet(nome_aba)
        
        registros = aba.get_all_records()
        for idx, registro in enumerate(registros, start=2):
            if str(registro["User ID"]) == str(user_id):
                aba.delete_rows(idx)
                await update.message.reply_text(f"✅ Escola com User ID {user_id} removida.")
                return True  # Sucesso

        await update.message.reply_text("⚠️ User ID não encontrado.")
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
def buscar_dados_escola(user_id):
    try:
        for linha in dados_planilha:
            if str(linha.get('User ID', '')) == str(user_id):  # Evita erro caso a chave 'User ID' não exista
                return linha
        print(f"⚠️ User ID {user_id} não encontrado.")
        return None
    except Exception as e:
        print(f"❌ Erro ao buscar dados da escola: {e}")  
        return None

async def mensagem_recebida(update: Update, context):
    """Processa mensagens recebidas e identifica emergências."""
    global emergencia_ativa  
    try:
        user_id = str(update.effective_user.id)
        texto = update.message.text.strip()  # Remove espaços extras
        dados_escola = buscar_dados_escola(user_id)

        # 🔹 Verifica se o User ID está cadastrado
        if not dados_escola:
                if texto.upper() == "CADASTRO":
                    await notificar_admin_solicitacao_cadastro(update)
                else:
                    await update.message.reply_text(
                        "⚠️ *Canal exclusivo para as Instituições de Ensino cadastradas.*\n"
                        "*Favor entrar em contato com o 190 em caso de emergência.*\n"
                        "*Caso tenha interesse em se cadastrar, envie a mensagem \"CADASTRO\".*",
                        parse_mode='Markdown'
                    )
                return  # Bloqueia qualquer outra ação para usuários não cadastrados

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
                f"(Nome: {update.message.from_user.first_name}, User ID: {user_id})"
            )

            # 🔹 Enviar mensagem detalhada para todos os administradores
            await asyncio.gather(*[
                context.bot.send_message(chat_id=admin_id, text=mensagem_para_admins, parse_mode='Markdown')
                for admin_id in ADMIN_USER_IDS
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
        logging.exception(f"❌ Erro ao processar a mensagem recebida (User ID: {user_id}): {e}")

async def notificar_admin_solicitacao_cadastro(update: Update):
    user_id = str(update.message.from_user.id)
    first_name = update.message.from_user.first_name or "Não informado"
    last_name = update.message.from_user.last_name or "Não informado"
    telefone = update.message.contact.phone_number if update.message.contact else "Não informado"

    mensagem = (
        f"👤 *Novo pedido de cadastro*\n"
        f"📌 *ID*: {user_id}\n"
        f"👤 *Nome*: {first_name} {last_name}\n"
        f"📞 *Telefone*: {telefone}\n\n"
        f"Para aprovar este usuário, utilize o comando:\n"
        f"`/cadastrar {user_id};<Nome>;<Função>;<Escola>;<Telefone>;<Email>;<Endereço>;<Localização>`"
    )

    # 🔹 Enviar para todos os administradores
    await asyncio.gather(*[
        update.get_bot().send_message(chat_id=admin_id, text=mensagem, parse_mode='Markdown')
        for admin_id in obter_administradores()
    ])

    await update.message.reply_text("📌 Sua solicitação foi enviada para análise.")


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

    await asyncio.gather(*[enviar_para_admin(admin_id) for admin_id in ADMIN_USER_IDS])

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

    await asyncio.gather(*[enviar_para_admin(admin_id) for admin_id in ADMIN_USER_IDS])

# 🔹 Função para lidar com a escolha do administrador
async def callback_handler(update: Update, context):
    query: CallbackQuery = update.callback_query
    query_data = query.data
    user_id = str(query.from_user.id)  # ✅ Pegando corretamente o ID do usuário

    # 🚨 Verifica se o usuário tem permissão (se é administrador)
    if user_id not in ADMIN_USER_IDS:
        await query.answer("⚠️ Você não tem permissão para executar esta ação.", show_alert=True)
        return

    if query_data.startswith("aprovar_"):
        user_id_aprovado = query_data.split("_")[1]  # Pegando o ID do usuário a ser aprovado
        usuario = cadastros_pendentes.pop(user_id_aprovado, None)

        if usuario:
            await query.edit_message_text(
                text=f"✅ *Usuário {usuario['Nome']} aprovado!* Agora, envie os dados adicionais no formato:\n\n"
                     "`/cadastrar <UserID>;<Nome>;<Função>;<Escola>;<Telefone>;<Email>;<Endereço>;<Localização Google Maps>`",
                parse_mode="Markdown"
            )
        else:
            await query.edit_message_text("⚠️ Usuário já foi processado ou não encontrado.")

    elif query_data.startswith("rejeitar_"):
        user_id_rejeitado = query_data.split("_")[1]  # Pegando o ID do usuário a ser rejeitado
        usuario = cadastros_pendentes.pop(user_id_rejeitado, None)

        if usuario:
            await query.edit_message_text(f"❌ *Usuário {usuario['Nome']} foi rejeitado e não será cadastrado.*")
        else:
            await query.edit_message_text("⚠️ Usuário já foi rejeitado ou não encontrado.")

# 🔹 Função para cadastrar um novo usuário na planilha
async def cadastrar(update: Update, context):
    administradores = obter_administradores()
    
    # 🔹 Verifica se quem está cadastrando é um administrador
    if str(update.message.from_user.id) not in administradores:
        await update.message.reply_text("⚠️ Apenas administradores podem cadastrar novas escolas.")
        return

    dados = " ".join(context.args)
    campos = dados.split(";")

    if len(campos) != 8:
        await update.message.reply_text("⚠️ Formato inválido! Use:\n"
                                        "`/cadastrar <UserID>;<Nome>;<Função>;<Escola>;<Telefone>;<Email>;<Endereço>;<Localização>`",
                                        parse_mode="Markdown")
        return

    user_id, nome, funcao, escola, telefone, email, endereco, localizacao = campos

    # 🚨 Bloquear cadastro duplicado
    if buscar_dados_escola(user_id):
        await update.message.reply_text("⚠️ Esta escola já está cadastrada!")
        return

    sucesso = adicionar_escola(user_id, nome, funcao, escola, telefone, email, endereco, localizacao)

    if sucesso:
        await update.message.reply_text(f"✅ *Usuário {nome} cadastrado com sucesso!*", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Erro ao salvar os dados na planilha.")

# 🔹 Função para atualizar a planilha periodicamente (agora assíncrona)
async def atualizar_planilha_periodicamente():
    while True:
        try:
            print("🔄 Atualizando planilha...")
            await carregar_dados_csv()
            print("✅ Planilha atualizada com sucesso!")
        except Exception as e:
            logging.error(f"❌ Erro ao atualizar a planilha: {e}", exc_info=True)

        await asyncio.sleep(300)  # 🔄 Aguarda 5 minutos antes da próxima atualização

async def listar_escolas(update: Update, context):
    user_id = str(update.effective_user.id)
    
    # 🚨 Verifica se o usuário é um administrador
    administradores = obter_administradores()
    if user_id not in administradores:
        await update.message.reply_text("⚠️ Apenas administradores podem visualizar a lista de escolas cadastradas.")
        return

    try:
        planilha = conectar_planilha()
        aba = planilha.worksheet("Escolas")
        registros = aba.get_all_values()

        if len(registros) <= 1:
            await update.message.reply_text("📌 Nenhuma escola cadastrada ainda.")
            return

        # 🔹 Monta a lista de escolas
        mensagem = "🏫 *Lista de Escolas Cadastradas:*\n\n"
        for idx, linha in enumerate(registros[1:], start=1):  # Pula o cabeçalho
            mensagem += f"{idx}. {linha[3]} - {linha[1]} ({linha[2]})\n"

        await update.message.reply_text(mensagem, parse_mode='Markdown')

    except Exception as e:
        await update.message.reply_text("❌ Erro ao buscar lista de escolas.")

# 🔹 Função para rodar o Bot do Telegram corretamente
# 🔹 Função para rodar o Bot do Telegram corretamente
async def iniciar_bot():
    logging.info("🤖 Iniciando o bot do Telegram...")
    
    app_telegram = Application.builder().token(TELEGRAM_TOKEN).build()

    # 🔹 Adicionar comandos ao bot
    app_telegram.add_handler(CommandHandler("start", start))
    app_telegram.add_handler(CommandHandler("ajuda", ajuda))
    app_telegram.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mensagem_recebida))
    app_telegram.add_handler(CommandHandler("listarescolas", listar_escolas))

    # 🔹 Iniciar atualização da planilha em segundo plano
    asyncio.create_task(atualizar_planilha_periodicamente())

    logging.info("✅ Bot do Telegram iniciado com sucesso!")
    await app_telegram.run_polling()

# 🔹 Inicialização segura do Flask e do Bot
if __name__ == "__main__":
    # 🔹 Iniciar o servidor Flask em uma thread separada
    threading.Thread(target=iniciar_servidor, daemon=True).start()

    # 🔹 Rodar o ping para manter o Render online
    threading.Thread(target=manter_online, daemon=True).start()

    # 🔹 Criar o loop de eventos do asyncio e rodar o bot corretamente
    asyncio.run(iniciar_bot())