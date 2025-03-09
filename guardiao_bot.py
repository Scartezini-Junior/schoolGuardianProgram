import os
import requests
import csv
import threading
import time
import unicodedata
import socket
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackContext, filters
from flask import Flask

# Criar um servidor Flask para enganar o Render
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot do Telegram rodando!"

def iniciar_servidor():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))


# Configurações
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CSV_URL = os.getenv("CSV_URL")
ADMIN_CHAT_IDS = os.getenv("ADMIN_CHAT_IDS", "").split(",")

dados_planilha = []
emergencia_ativa = False

def normalizar_texto(texto):
    return unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('utf-8').upper()

def internet_disponivel():
    try:
        response = requests.get("https://www.google.com", timeout=3)
        return response.status_code == 200
    except requests.RequestException:
        return False

def carregar_dados_csv():
    global dados_planilha
    try:
        response = requests.get(CSV_URL)
        response.raise_for_status()
        decoded_content = response.content.decode('utf-8')
        reader = csv.DictReader(decoded_content.splitlines())
        dados_planilha = list(reader)
        print("✅ Planilha atualizada com sucesso!")
    except Exception as e:
        print(f"❌ Erro ao carregar a planilha: {e}")

def buscar_dados_escola(chat_id):
    try:
        for linha in dados_planilha:
            if str(linha['Chat ID']) == str(chat_id):
                return linha
        return None
    except Exception as e:
        print(f"❌ Erro ao buscar dados: {e}")

def exibir_erro(mensagem):
    """ Registra erros no log e notifica os administradores """
    print(f"❌ ERRO: {mensagem}")  # Exibe o erro no console

    for admin_id in ADMIN_CHAT_IDS:
        try:
            context.bot.send_message(chat_id=admin_id, text=f"⚠️ Erro detectado: {mensagem}")
        except Exception as e:
            print(f"❌ Falha ao notificar admin ({admin_id}): {e}")

# Função para exibir a mensagem de boas-vindas
def start(update: Update, context: CallbackContext):
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
        "- AGRESSOR\n- HOMICÍDIO\n- REFÉM\n- BOMBA\n- TESTE\n"
        "2️⃣ *Envie os detalhes do ocorrido*, incluindo:\n"
        "- Localização exata\n- Número de envolvidos\n- Estado das vítimas\n- Meios utilizados pelo agressor."
    )
    update.message.reply_text(mensagem_boas_vindas, parse_mode='Markdown')

# Função para exibir a ajuda
def ajuda(update: Update, context: CallbackContext):
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
    update.message.reply_text(mensagem_ajuda, parse_mode='Markdown')

# 🔹 Funções específicas para cada comando
def bomba(update: Update, context: CallbackContext):
    print("⚠️ Comando /bomba acionado")
    comando_emergencia(update, context, "bomba")

def ameaca(update: Update, context: CallbackContext):
    print("⚠️ Comando /ameaca acionado")
    comando_emergencia(update, context, "ameaça")

def refem(update: Update, context: CallbackContext):
    print("⚠️ Comando /refem acionado")
    comando_emergencia(update, context, "refém")

def agressor(update: Update, context: CallbackContext):
    print("⚠️ Comando /agressor acionado")
    comando_emergencia(update, context, "agressor")

def homicidio(update: Update, context: CallbackContext):
    print("⚠️ Comando /homicidio acionado")
    comando_emergencia(update, context, "homicídio")

def teste(update: Update, context: CallbackContext):
    print("⚠️ Comando /teste acionado")
    comando_emergencia(update, context, "teste")

def cadastro(update: Update, context: CallbackContext):
    chat_id = str(update.message.chat_id)
    nome = update.message.from_user.first_name or "Nome não informado"
    username = update.message.from_user.username or "Sem username"

    print(f"📌 Novo pedido de cadastro recebido: Nome={nome}, Username={username}, Chat ID={chat_id}")

    mensagem_confirmacao = (
        "📌 *Sua solicitação foi enviada para análise.*\n"
        "Aguarde o contato de um administrador."
    )
    update.message.reply_text(mensagem_confirmacao, parse_mode="Markdown")

    mensagem_admin = (
        f"📌 *Novo usuário solicitando cadastro!*\n\n"
        f"🔹 *Chat ID*: `{chat_id}`\n"
        f"👤 *Nome*: {nome}\n"
        f"🔹 *Username*: @{username}\n\n"
        f"Para cadastrá-lo, insira manualmente os dados na planilha."
    )

    for admin_id in ADMIN_CHAT_IDS:
        try:
            context.bot.send_message(chat_id=admin_id, text=mensagem_admin, parse_mode='Markdown')
            print(f"✅ Notificação de cadastro enviada para {admin_id}")
        except Exception as e:
            print(f"❌ Erro ao enviar notificação de cadastro para {admin_id}: {e}")

# 🔹 Função principal de emergência e notificações
def comando_emergencia(update: Update, context: CallbackContext, tipo: str):
    global emergencia_ativa
    chat_id = str(update.message.chat_id)
    texto = update.message.text
    dados_escola = buscar_dados_escola(chat_id)

    # ✅ Se o usuário NÃO estiver cadastrado, notifica os administradores automaticamente
    if not dados_escola:
        mensagem_nao_autorizada = (
            "⚠️ *Canal exclusivo para as Instituições de Ensino cadastradas.*\n"
            "Favor entrar em contato com o 190 em caso de emergência.\n\n"
            "Caso tenha interesse em se cadastrar, envie a mensagem \"CADASTRO\"."
        )
        update.message.reply_text(mensagem_nao_autorizada, parse_mode='Markdown')

        # ✅ Enviar notificação para os administradores com os dados do novo usuário
        mensagem_admin = (
            f"📌 *Novo usuário tentando interagir com o bot!*\n\n"
            f"🔹 *Chat ID*: `{chat_id}`\n"
            f"👤 *Nome*: {update.message.from_user.first_name or 'Nome não informado'}\n"
            f"🔹 *Username*: @{update.message.from_user.username or 'Sem username'}\n\n"
            f"Para cadastrá-lo, insira manualmente os dados na planilha."
        )

        for admin_id in ADMIN_CHAT_IDS:
            try:
                context.bot.send_message(chat_id=admin_id, text=mensagem_admin, parse_mode='Markdown')
                print(f"📌 Notificação de novo usuário enviada para {admin_id}")
            except Exception as e:
                print(f"❌ Erro ao enviar notificação de cadastro para {admin_id}: {e}")

        return  # Bloqueia qualquer outra ação para usuários não cadastrados.

    # ✅ Usuário cadastrado - processamento normal
    texto_normalizado = normalizar_texto(texto)
    emergencia_ativa = True  # Ativando emergência
    print(f"⚠️ Emergência ativada: {tipo.upper()} para {dados_escola['Escola']}")

    # ✅ Confirmação para o usuário
    update.message.reply_text(
        f"Mensagem Recebida. Identificamos que vocês estão em situação de emergência envolvendo {tipo.lower()}, o Guardião Escolar foi ativado e em breve uma equipe chegará ao seu local. "
        "Mantenha-se em segurança e, se possível, envie uma nova mensagem com mais detalhes sobre o que está acontecendo, quantos envolvidos, meios utilizados e se há alguém necessitando de suporte médico."
    )

    # ✅ Alerta detalhado para os administradores
    mensagem_para_admins = (
        f"⚠️ *Mensagem de emergência recebida:*\n\n"
        f"🏫 *Escola*: {dados_escola['Escola']}\n"
        f"👤 *Servidor*: {dados_escola['Nome']}\n"
        f"👤 *Função*: {dados_escola['Função']}\n"
        f"📞 *Telefone*: {dados_escola['Telefone']}\n"
        f"✉️ *Email*: {dados_escola['Email']}\n"
        f"📍 *Endereço*: {dados_escola['Endereço']}\n"
        f"🌐 *Localização*: {dados_escola['Localização']}\n\n"
        f"📩 *Mensagem original*: {texto.upper()}\n"
        f"👤 *Usuário*: @{update.message.from_user.username or 'Sem username'} "
        f"(Nome: {update.message.from_user.first_name}, Chat ID: {chat_id})"
    )

    for admin_id in ADMIN_CHAT_IDS:
        try:
            context.bot.send_message(chat_id=admin_id, text=mensagem_para_admins, parse_mode='Markdown')
            print(f"✅ Notificação de emergência enviada para {admin_id}")
        except Exception as e:
            print(f"❌ Erro ao enviar alerta para {admin_id}: {e}")

    emergencia_ativa = False  # Finaliza a emergência

# 🔹 Função para lidar com mensagens de emergência enviadas como texto livre
def mensagem_recebida(update: Update, context: CallbackContext):
    global emergencia_ativa  # Controle de emergência
    try:
        chat_id = str(update.message.chat_id)
        texto = update.message.text
        dados_escola = buscar_dados_escola(chat_id)

        # ✅ Se o usuário NÃO estiver cadastrado, notifica os administradores automaticamente
        if not dados_escola:
            mensagem_nao_autorizada = (
                "⚠️ *Canal exclusivo para as Instituições de Ensino cadastradas.*\n"
                "Favor entrar em contato com o 190 em caso de emergência.\n\n"
                "Caso tenha interesse em se cadastrar, envie a mensagem \"CADASTRO\"."
            )
            update.message.reply_text(mensagem_nao_autorizada, parse_mode='Markdown')

            # ✅ Enviar notificação para os administradores com os dados do novo usuário
            mensagem_admin = (
                f"📌 *Novo usuário tentando interagir com o bot!*\n\n"
                f"🔹 *Chat ID*: `{chat_id}`\n"
                f"👤 *Nome*: {update.message.from_user.first_name or 'Nome não informado'}\n"
                f"🔹 *Username*: @{update.message.from_user.username or 'Sem username'}\n\n"
                f"Para cadastrá-lo, insira manualmente os dados na planilha."
            )

            for admin_id in ADMIN_CHAT_IDS:
                try:
                    context.bot.send_message(chat_id=admin_id, text=mensagem_admin, parse_mode='Markdown')
                    print(f"📌 Notificação de novo usuário enviada para {admin_id}")
                except Exception as e:
                    print(f"❌ Erro ao notificar administradores sobre novo usuário ({admin_id}): {e}")

            return  # Bloqueia qualquer outra ação para usuários não cadastrados.

        # ✅ Se o usuário está cadastrado, continua normalmente.
        texto_normalizado = normalizar_texto(texto)
        palavra_chave_encontrada = False

        for palavra in ["AGRESSOR", "HOMICIDIO", "REFEM", "BOMBA", "SOCORRO", "TESTE"]:
            if palavra in texto_normalizado:
                palavra_chave_encontrada = True
                emergencia_ativa = True  # Ativando emergência
                print(f"⚠️ Emergência ativada: {palavra.upper()} para {dados_escola['Escola']}")

                # ✅ Confirmação para o usuário
                update.message.reply_text(
                    f"Mensagem Recebida. Identificamos que vocês estão em situação de emergência envolvendo {palavra.lower()}, o Guardião Escolar foi ativado e em breve uma equipe chegará ao seu local. "
                    "Mantenha-se em segurança e, se possível, envie uma nova mensagem com mais detalhes sobre o que está acontecendo, quantos envolvidos, meios utilizados e se há alguém necessitando de suporte médico."
                )

                # ✅ Alerta detalhado para os administradores
                mensagem_para_admins = (
                    f"⚠️ *Mensagem de emergência recebida:*\n\n"
                    f"🏫 *Escola*: {dados_escola['Escola']}\n"
                    f"👤 *Servidor*: {dados_escola['Nome']}\n"
                    f"👤 *Função*: {dados_escola['Função']}\n"
                    f"📞 *Telefone*: {dados_escola['Telefone']}\n"
                    f"✉️ *Email*: {dados_escola['Email']}\n"
                    f"📍 *Endereço*: {dados_escola['Endereço']}\n"
                    f"🌐 *Localização*: {dados_escola['Localização']}\n\n"
                    f"📩 *Mensagem original*: {texto.upper()}\n"
                    f"👤 *Usuário*: @{update.message.from_user.username or 'Sem username'} "
                    f"(Nome: {update.message.from_user.first_name}, Chat ID: {chat_id})"
                )

                for admin_id in ADMIN_CHAT_IDS:
                    try:
                        context.bot.send_message(
                            chat_id=admin_id,
                            text=mensagem_para_admins,
                            parse_mode='Markdown'
                        )
                        print(f"✅ Notificação de emergência enviada para {admin_id}")
                    except Exception as e:
                        print(f"❌ Erro ao enviar alerta para {admin_id}: {e}")

                emergencia_ativa = False  # Finaliza a emergência
                break

        if not palavra_chave_encontrada:
            mensagem_erro = (
                "⚠️ Este canal é exclusivo para comunicação de emergências.\n\n"
                "Siga as orientações do menu /ajuda. Se você estiver em uma situação de emergência, "
                "lembre-se de inserir a palavra-chave correspondente e incluir o máximo de detalhes possível.\n"
                "📞 Inclua também um número de contato para que possamos falar com você."
            )
            update.message.reply_text(mensagem_erro)

    except Exception as e:
        emergencia_ativa = False
        print(f"❌ Erro ao processar mensagem: {e}")
        try:
            for admin_id in ADMIN_CHAT_IDS:
                context.bot.send_message(chat_id=admin_id, text=f"⚠️ Erro detectado ao processar uma mensagem: {e}")
        except Exception as admin_error:
            print(f"❌ Falha ao notificar administradores sobre erro: {admin_error}")

# 🔹 Função para enviar alerta e áudio no Telegram
def exibir_alerta(dados_escola, tipo, detalhes, tipo_mensagem="livre", context=None):
    """
    Envia um alerta de emergência para os administradores do bot no Telegram.
    Inclui um áudio de alerta se disponível no servidor.
    """

    # Verifica o tipo de mensagem e ajusta o conteúdo exibido
    if tipo_mensagem == "comando":
        mensagem_ajustada = (
            f"⚠️ *Usuário acionou o botão de emergência: {tipo.upper()}*.\n"
            f"O solicitante pode estar em perigo. Prossiga com brevidade e cautela.⚠️"
        )
    else:
        mensagem_ajustada = (
            f"⚠️ *Mensagem de emergência recebida:*\n"
            f"\"{detalhes.upper()}\"\n"
            f"Usuário pode estar em perigo. Prossiga com brevidade e cautela.⚠️"
        )

    # Formata a mensagem completa do alerta
    mensagem = (
        f"🚨 *ALERTA DE EMERGÊNCIA* 🚨\n\n"
        f"🏫 *Escola*: {dados_escola['Escola']}\n"
        f"👤 *Servidor*: {dados_escola['Nome']}\n"
        f"👤 *Função*: {dados_escola['Função']}\n"
        f"📞 *Telefone*: {dados_escola['Telefone']}\n"
        f"📩 *Email*: {dados_escola['Email']}\n"
        f"📍 *Endereço*: {dados_escola['Endereço']}\n"
        f"🌍 *Localização*: {dados_escola['Localização']}\n\n"
        f"🔔 *Tipo de Emergência*: {tipo.upper()}\n"
        f"{mensagem_ajustada}\n\n"
        f"🆘 *Atenção*: Contatar imediatamente o solicitante!"
    )

    # Caminho do arquivo de áudio (deve estar no servidor)
    caminho_audio = "alerta.mp3" if tipo.lower() != "teste" else "teste.mp3"

    # ✅ Enviar mensagem e áudio para os administradores no Telegram
    for admin_id in ADMIN_CHAT_IDS:
        try:
            context.bot.send_message(chat_id=admin_id, text=mensagem, parse_mode="Markdown")
            print(f"✅ Alerta de emergência enviado para {admin_id}")

            # Enviar áudio se disponível
            with open(caminho_audio, "rb") as audio:
                context.bot.send_audio(chat_id=admin_id, audio=audio, caption="🔊 *Alerta Sonoro*")
                print(f"✅ Áudio de alerta enviado para {admin_id}")

        except Exception as e:
            print(f"❌ Erro ao enviar alerta para {admin_id}: {e}")

# 🔹 Função para alertar administradores sobre perda de conexão
def exibir_alerta_conexao(context=None):
    """
    Envia um alerta para os administradores informando que o bot perdeu a conexão com a internet.
    """

    mensagem = (
        "⚠️ *Guardião Escolar Inoperante!*\n\n"
        "🚨 *Motivo*: Falta de Conexão com a Internet.\n"
        "🔄 O sistema tentará reconectar automaticamente.\n\n"
        "⚙️ *Ação necessária*: Verifique a conexão do servidor!"
    )

    # ✅ Enviar mensagem para os administradores no Telegram
    for admin_id in ADMIN_CHAT_IDS:
        try:
            context.bot.send_message(chat_id=admin_id, text=mensagem, parse_mode="Markdown")
            print(f"❌ ALERTA: Guardião Escolar sem conexão! Notificação enviada para {admin_id}")
        except Exception as e:
            print(f"❌ Erro ao enviar alerta de conexão para {admin_id}: {e}")


# 🔹 Função para enviar o alerta sonoro no Telegram (substitui tocar_som)
def tocar_som(tipo, context=None):
    """
    Envia um áudio de alerta para os administradores via Telegram em vez de reproduzi-lo no servidor.
    """

    # Define o caminho do arquivo de som
    caminho_audio = "teste.mp3" if tipo.lower() == "teste" else "alerta.mp3"

    # ✅ Envia o áudio para os administradores
    for admin_id in ADMIN_CHAT_IDS:
        try:
            with open(caminho_audio, "rb") as audio:
                context.bot.send_audio(chat_id=admin_id, audio=audio, caption="🔊 *Alerta Sonoro!*")
                print(f"✅ Áudio de alerta enviado para {admin_id}")
        except Exception as e:
            print(f"❌ Erro ao enviar áudio para {admin_id}: {e}")

# 🔹 Função para atualizar a planilha a cada 5 minutos em uma thread separada
def atualizar_planilha_periodicamente():
    """
    Atualiza os dados da planilha online a cada 5 minutos, rodando como uma thread separada.
    """
    while True:
        try:
            carregar_dados_csv()
            print("✅ Guardião Escolar - Planilha atualizada com sucesso!")
        except Exception as e:
            print(f"❌ Erro ao atualizar a planilha: {e}")
        time.sleep(300)  # 300 segundos = 5 minutos

# 🔹 Função para monitorar a conexão com a internet e alertar os administradores
def monitorar_conexao(context=None):
    """
    Verifica a conexão com a internet a cada 60 segundos.
    Se a conexão cair, alerta os administradores no Telegram.
    """
    while True:
        try:
            if not internet_disponivel():
                print("❌ Conexão perdida! Enviando alerta...")
                exibir_alerta_conexao(context)
            else:
                print("✅ Conexão com a internet verificada. Status: Conectado.")
        except Exception as e:
            print(f"❌ Erro no monitoramento da conexão: {e}")
        time.sleep(60)  # Verifica a cada 60 segundos

# 🔹 Função para iniciar o bot no servidor
def iniciar_bot():
    """
    Inicializa o bot do Telegram, configura os handlers e inicia threads essenciais.
    """
    print("🚀 Iniciando Guardião Escolar...")

    application = Application.builder().token(TELEGRAM_TOKEN).build()


    # ✅ Adicionando handlers para comandos de emergência
    application.add_handler(CommandHandler('bomba', bomba))
    application.add_handler(CommandHandler('ameaca', ameaca))
    application.add_handler(CommandHandler('refem', refem))
    application.add_handler(CommandHandler('agressor', agressor))
    application.add_handler(CommandHandler('homicidio', homicidio))
    application.add_handler(CommandHandler('teste', teste))

    # ✅ Handler para cadastro
    application.add_handler(CommandHandler('cadastro', cadastro))

    # ✅ Handlers para comandos básicos
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('ajuda', ajuda))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mensagem_recebida))

    # ✅ Iniciar a atualização da planilha em segundo plano
    threading.Thread(target=atualizar_planilha_periodicamente, daemon=True).start()

    # Iniciar o monitoramento da conexão usando application.bot
    threading.Thread(target=monitorar_conexao, args=(application.bot,), daemon=True).start()

    print("✅ Guardião Escolar está rodando! Aguardando mensagens...")
    
    # Iniciar o bot
    application.run_polling()


if __name__ == "__main__":
    threading.Thread(target=iniciar_servidor, daemon=True).start()  # Iniciar o servidor Flask
    iniciar_bot()  # Iniciar o bot normalmente
