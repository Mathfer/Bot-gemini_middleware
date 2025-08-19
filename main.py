# =====================
# IMPORTS E CONFIGURAÇÕES
# =====================
import os
import json
import re
import asyncio
import logging
import httpx
import datetime
from typing import Optional
from fastapi import FastAPI, BackgroundTasks, Request, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ValidationError, Field, field_validator
from filelock import FileLock
from dotenv import load_dotenv
from google import genai

# Teste de import mais robusto
try:
    from google.genai import GenerativeModel
    HAS_GENERATIVE_MODEL = True
except ImportError as e:
    HAS_GENERATIVE_MODEL = False

try:
    from google.genai import Client
    HAS_CLIENT = True
except ImportError as e:
    HAS_CLIENT = False

# =====================
# LOGGING E VARIÁVEIS DE AMBIENTE
# =====================
load_dotenv()
logging.basicConfig(
    level=logging.INFO, 
    format='[%(asctime)s][%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('app.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# =====================
# CONFIGURAÇÕES GERAIS
# =====================
pasta_historicos = "historicos"
if not os.path.exists(pasta_historicos):
    os.makedirs(pasta_historicos)
    logger.info("[SETUP] Pasta 'historicos' criada com sucesso!")
else:
    logger.info("[SETUP] Pasta 'historicos' já existe.")

# Validação das variáveis de ambiente
TOKEN_ESPERADO = os.environ.get("TOKEN_ESPERADO", "RLjUoIUiajoI8Ss33WATbH3-KDhIkpAlNUmPjDIhQ7k")
FRESHCHAT_API_TOKEN = os.environ.get("FRESHCHAT_API_TOKEN", "")
FRESHCHAT_BASE_URL = os.environ.get("FRESHCHAT_BASE_URL", "https://api.freshchat.com/v2")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# Configurações de rate limiting
MAX_REQUESTS_PER_MINUTE = int(os.environ.get("MAX_REQUESTS_PER_MINUTE", "60"))
request_counts = {}

# Log de configuração (sem expor tokens)
logger.info(f"[SETUP] FRESHCHAT_BASE_URL: {FRESHCHAT_BASE_URL}")
logger.info(f"[SETUP] MAX_REQUESTS_PER_MINUTE: {MAX_REQUESTS_PER_MINUTE}")
logger.info(f"[SETUP] TOKEN_ESPERADO: {'***CONFIGURADO***' if TOKEN_ESPERADO else 'NÃO CONFIGURADO'}")
logger.info(f"[SETUP] FRESHCHAT_API_TOKEN: {'***CONFIGURADO***' if FRESHCHAT_API_TOKEN else 'NÃO CONFIGURADO'}")
logger.info(f"[SETUP] GEMINI_API_KEY: {'***CONFIGURADO***' if GEMINI_API_KEY else 'NÃO CONFIGURADO'}")

app = FastAPI(
    title="Bot Middleware Gemini",
    description="Middleware para integração entre Freshchat e Google Gemini AI",
    version="1.0.0"
)

# Configuração CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Em produção, especifique os domínios permitidos
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()

# Métricas de performance
performance_metrics = {
    "gemini_response_times": [],
    "freshchat_response_times": [],
    "total_requests": 0,
    "successful_requests": 0,
    "failed_requests": 0
}

# Configuração do cliente Gemini
if GEMINI_API_KEY:
    if HAS_GENERATIVE_MODEL:
        client = GenerativeModel("gemini-2.5-flash", api_key=GEMINI_API_KEY)
        logger.info("[SETUP] Cliente Gemini configurado com GenerativeModel!")
    elif HAS_CLIENT:
        client = Client(api_key=GEMINI_API_KEY)
        logger.info("[SETUP] Cliente Gemini configurado com Client!")
    else:
        client = None
        logger.error("[SETUP] Nenhuma classe compatível encontrada para o Gemini!")
else:
    client = None
    logger.warning("[SETUP] GEMINI_API_KEY não definida. A integração com Gemini não funcionará.")

# Verificação de variáveis críticas
if not FRESHCHAT_API_TOKEN:
    logger.warning("[SETUP] FRESHCHAT_API_TOKEN não definida. A integração com Freshchat não funcionará.")

# =====================
# MODELOS
# =====================
class DadosRecebidos(BaseModel):
    solicitante: str = Field(default="desconhecido", max_length=100)
    contexto: str = Field(default="", max_length=2000)
    pergunta: str = Field(default="", max_length=1000)
    user_id: str = Field(default="", max_length=50)
    id_usuario: str = Field(default="", max_length=50)
    id_conversa: str = Field(default="", max_length=50)
    resposta_gemini: str = Field(default="", max_length=4000)
    url: str = Field(default="", max_length=500)
    
    @field_validator('solicitante', 'contexto', 'pergunta', 'user_id', 'id_usuario', 'id_conversa', 'resposta_gemini', 'url')
    @classmethod
    def sanitize_strings(cls, v):
        """Sanitiza strings removendo caracteres perigosos"""
        if isinstance(v, str):
            # Remove caracteres de controle e HTML
            v = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', v)
            v = re.sub(r'<[^>]*>', '', v)
            return v.strip()
        return v

# =====================
# UTILITÁRIOS
# =====================
def verificar_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Verifica se o token de autorização é válido.
    
    Args:
        credentials: Credenciais HTTP Bearer
        
    Raises:
        HTTPException: Se o token for inválido
    """
    logger.info("[AUTH] Verificando token...")
    if credentials.credentials != TOKEN_ESPERADO:
        logger.error("[AUTH] Token inválido ou ausente!")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido ou ausente",
        )
    logger.info("[AUTH] Token válido.")

def verificar_rate_limit(request: Request):
    """
    Verifica se o cliente não excedeu o limite de requisições.
    
    Args:
        request: Objeto Request do FastAPI
        
    Raises:
        HTTPException: Se o limite for excedido
    """
    client_ip = request.client.host
    current_time = datetime.datetime.now()
    
    # Limpa registros antigos (mais de 1 minuto)
    if client_ip in request_counts:
        request_counts[client_ip] = [
            req_time for req_time in request_counts[client_ip]
            if (current_time - req_time).seconds < 60
        ]
    
    # Verifica se excedeu o limite
    if client_ip in request_counts and len(request_counts[client_ip]) >= MAX_REQUESTS_PER_MINUTE:
        logger.warning(f"[RATE_LIMIT] Cliente {client_ip} excedeu limite de requisições")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Limite de requisições excedido. Tente novamente em 1 minuto."
        )
    
    # Adiciona requisição atual
    if client_ip not in request_counts:
        request_counts[client_ip] = []
    request_counts[client_ip].append(current_time)

def limpar_arquivos_antigos():
    """
    Remove arquivos de log antigos para evitar acúmulo excessivo.
    """
    try:
        current_time = datetime.datetime.now()
        files_removed = 0
        files_cleaned = 0
        
        # Remove arquivos de lock antigos (mais de 1 hora)
        for filename in os.listdir('.'):
            if filename.endswith('.lock'):
                file_path = os.path.join('.', filename)
                try:
                    file_time = datetime.datetime.fromtimestamp(os.path.getmtime(file_path))
                    if (current_time - file_time).seconds > 3600:
                        os.remove(file_path)
                        logger.info(f"[CLEANUP] Arquivo de lock removido: {filename}")
                        files_removed += 1
                except (OSError, FileNotFoundError):
                    pass  # Arquivo já foi removido ou não existe
        
        # Limpeza de logs antigos (mais de 7 dias)
        log_files = ["app.log", "log_entradas.txt", "dados_recebidos.txt"]
        for log_file in log_files:
            if os.path.exists(log_file):
                try:
                    file_time = datetime.datetime.fromtimestamp(os.path.getmtime(log_file))
                    if (current_time - file_time).days > 7:
                        # Criar backup antes de limpar
                        backup_name = f"{log_file}.backup.{current_time.strftime('%Y%m%d')}"
                        try:
                            with open(log_file, 'r', encoding='utf-8') as f:
                                content = f.read()
                            with open(backup_name, 'w', encoding='utf-8') as f:
                                f.write(content)
                            
                            # Limpar arquivo (manter apenas últimas 1000 linhas)
                            with open(log_file, 'r', encoding='utf-8') as f:
                                lines = f.readlines()
                            if len(lines) > 1000:
                                with open(log_file, 'w', encoding='utf-8') as f:
                                    f.writelines(lines[-1000:])
                                logger.info(f"[CLEANUP] Log {log_file} limpo, mantidas últimas 1000 linhas")
                                files_cleaned += 1
                        except Exception as e:
                            logger.error(f"[CLEANUP] Erro ao processar log {log_file}: {e}")
                except (OSError, FileNotFoundError):
                    pass
        
        # Limpeza de backups antigos (mais de 30 dias)
        for filename in os.listdir('.'):
            if filename.endswith('.backup.'):
                file_path = os.path.join('.', filename)
                try:
                    file_time = datetime.datetime.fromtimestamp(os.path.getmtime(file_path))
                    if (current_time - file_time).days > 30:
                        os.remove(file_path)
                        logger.info(f"[CLEANUP] Backup antigo removido: {filename}")
                        files_removed += 1
                except (OSError, FileNotFoundError):
                    pass
        
        logger.info(f"[CLEANUP] Limpeza concluída: {files_removed} arquivos removidos, {files_cleaned} logs limpos")
                        
    except Exception as e:
        logger.error(f"[CLEANUP] Erro ao limpar arquivos: {e}")

# =====================
# FUNÇÕES DE INTEGRAÇÃO
# =====================
async def consultar_gemini(dados):
    """
    Realiza consulta real à API do Gemini usando a biblioteca oficial.
    
    Args:
        dados: Dados da consulta contendo contexto e pergunta
        
    Returns:
        str: Resposta do Gemini ou mensagem de erro
    """
    if not client:
        logger.error("[GEMINI] Cliente Gemini não configurado")
        return "Erro: Cliente Gemini não configurado"
    
    if not GEMINI_API_KEY:
        logger.error("[GEMINI] GEMINI_API_KEY não configurada")
        return "Erro: GEMINI_API_KEY não configurada"
    
    try:
        logger.info("[GEMINI] Iniciando consulta ao Gemini...")
        
        # Preparar o prompt para o Gemini
        contexto = dados.get('contexto', '')
        pergunta = dados.get('pergunta', '')
        
        if not pergunta:
            logger.warning("[GEMINI] Nenhuma pergunta fornecida")
            return "Erro: Nenhuma pergunta fornecida"
        
        # Preparar o conteúdo com o template específico
        system_instruction = """Você é um atendente de primeira linha da Multiclara, especialista em SaaS, IaaS e PaaS. Seu objetivo principal é ser resolutivo. Ao invés de apenas descrever um serviço, foque em solucionar o problema do usuário.

// MÉTODO DE AÇÃO OBRIGATÓRIO:
Se a pergunta do usuário for um pedido de ajuda (ex: 'algo não funciona', 'estou com um erro', 'não consigo fazer X'), sua primeira ação deve ser sempre sugerir passos práticos ou fazer perguntas claras para diagnosticar o problema. Nunca dê uma resposta genérica que apenas descreve um produto ou tecnologia.

// EXEMPLO DE COMPORTAMENTO:
- Se o usuário diz 'Meu app está lento', pergunte: 'Claro, vamos investigar! Você notou se a lentidão ocorre em horários específicos ou após alguma ação?'
- Se o usuário diz 'Não consigo conectar ao banco de dados', sugira: 'Ok, vamos verificar alguns pontos. Você pode confirmar se as credenciais estão corretas e se o IP da aplicação tem permissão de acesso?'

Recuse educadamente perguntas fora do escopo de SaaS, IaaS ou PaaS. Presuma que as permissões necessárias já foram concedidas. Mantenha a linguagem simples e amigável e não utilise este caracter '*' para deixar em negrito, utilize '<b> texto em negrito </b>'. Use este contexto: ${{custom::2375366}}"""
        
        user_content = f"Contexto: {contexto}\n\nPergunta: {pergunta}"
        
        # Fazer a chamada usando a biblioteca oficial
        start_time = datetime.datetime.now()
        
        try:
            if hasattr(client, 'generate_content'):
                # Para GenerativeModel
                response = client.generate_content(
                    f"{system_instruction}\n\n{user_content}",
                    generation_config={
                        "temperature": 0.4,
                        "top_k": 20,
                        "top_p": 0.8,
                        "max_output_tokens": 2048
                    }
                )
            else:
                # Para Client (versão antiga)
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=[
                        {
                            "role": "user",
                            "parts": [{"text": f"{system_instruction}\n\n{user_content}"}]
                        }
                    ],
                    generation_config={
                        "temperature": 0.4,
                        "top_k": 20,
                        "top_p": 0.8,
                        "max_output_tokens": 2048
                    }
                )
        except Exception as api_error:
            logger.error(f"[GEMINI] Erro na API do Gemini: {api_error}")
            if "quota" in str(api_error).lower():
                return "Erro: Limite de quota do Gemini excedido"
            elif "invalid" in str(api_error).lower() or "authentication" in str(api_error).lower():
                return "Erro: Configuração inválida do Gemini"
            elif "network" in str(api_error).lower() or "timeout" in str(api_error).lower():
                return "Erro: Problema de conectividade com o Gemini"
            else:
                return f"Erro na API do Gemini: {str(api_error)}"
        
        end_time = datetime.datetime.now()
        
        # Registrar métrica de performance
        response_time = (end_time - start_time).total_seconds()
        performance_metrics["gemini_response_times"].append(response_time)
        if len(performance_metrics["gemini_response_times"]) > 100:
            performance_metrics["gemini_response_times"] = performance_metrics["gemini_response_times"][-100:]
        
        # Verificar se a resposta é válida
        if not hasattr(response, 'text') or not response.text:
            logger.error("[GEMINI] Resposta vazia ou inválida do Gemini")
            return "Erro: Resposta vazia do Gemini"
        
        # Validar tamanho da resposta
        if len(response.text) > 4000:
            logger.warning("[GEMINI] Resposta muito longa, truncando...")
            resposta_truncada = response.text[:4000] + "..."
            logger.info(f"[GEMINI] Resposta truncada obtida com sucesso")
            return resposta_truncada
        else:
            logger.info(f"[GEMINI] Resposta obtida com sucesso ({len(response.text)} caracteres)")
            return response.text
            
    except Exception as e:
        logger.error(f"[GEMINI] Erro inesperado: {e}")
        return f"Erro inesperado: {str(e)}"

async def enviar_mensagem_freshchat(conversation_id: str, mensagem: str):
    """
    Envia mensagem para o Freshchat.
    
    Args:
        conversation_id: ID da conversa no Freshchat
        mensagem: Mensagem a ser enviada
        
    Returns:
        dict: Resposta da API do Freshchat
        
    Raises:
        Exception: Se houver erro na comunicação com o Freshchat
    """
    if not FRESHCHAT_API_TOKEN:
        logger.error("[FRESHCHAT] Token não configurado")
        raise Exception("Token do Freshchat não configurado")
    
    if not conversation_id:
        logger.error("[FRESHCHAT] conversation_id não fornecido")
        raise Exception("conversation_id é obrigatório")
    
    if not mensagem:
        logger.error("[FRESHCHAT] Mensagem vazia")
        raise Exception("Mensagem não pode estar vazia")
    
    logger.info(f"[FRESHCHAT] Enviando mensagem para conversa {conversation_id}...")
    url = f"{FRESHCHAT_BASE_URL}/conversations/{conversation_id}/messages"
    headers = {
        "Authorization": f"Bearer {FRESHCHAT_API_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "message_parts": [
            {"text": mensagem, "content_type": "text"}
        ],
        "actor_type": "Agent"
    }
    
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, headers=headers, json=payload)
            logger.info(f"[FRESHCHAT] Resposta da API: {response.status_code}")
            
            if response.status_code == 200:
                logger.info("[FRESHCHAT] Mensagem enviada com sucesso")
                return response.json()
            elif response.status_code == 401:
                logger.error("[FRESHCHAT] Token inválido ou expirado")
                raise Exception("Token do Freshchat inválido ou expirado")
            elif response.status_code == 403:
                logger.error("[FRESHCHAT] Sem permissão para enviar mensagem")
                raise Exception("Sem permissão para enviar mensagem no Freshchat")
            elif response.status_code == 404:
                logger.error("[FRESHCHAT] Conversa não encontrada")
                raise Exception("Conversa não encontrada no Freshchat")
            else:
                logger.error(f"[FRESHCHAT] Erro HTTP: {response.status_code}")
                response.raise_for_status()
                
    except httpx.TimeoutException:
        logger.error("[FRESHCHAT] Timeout ao enviar mensagem")
        raise Exception("Timeout ao enviar mensagem para Freshchat")
    except httpx.HTTPStatusError as e:
        logger.error(f"[FRESHCHAT] Erro HTTP: {e.response.status_code}")
        raise Exception(f"Erro HTTP do Freshchat: {e.response.status_code}")
    except httpx.ConnectError:
        logger.error("[FRESHCHAT] Erro de conexão")
        raise Exception("Erro de conexão com o Freshchat")
    except Exception as e:
        logger.error(f"[FRESHCHAT] Erro inesperado: {e}")
        raise Exception(f"Erro inesperado ao enviar mensagem: {str(e)}")

# =====================
# ENDPOINTS
# =====================
@app.put("/webhook/freshbot")
async def receber_freshbot(
    request: Request,
    background_tasks: BackgroundTasks,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Endpoint PUT para receber dados do Freshbot.
    Processa os dados recebidos e inicia consulta ao Gemini em background.
    """
    try:
        logger.info("[PUT] Recebendo solicitação em /webhook/freshbot")
        verificar_token(credentials)
        verificar_rate_limit(request)
        
        dados_json = await request.json()
        try:
            dados = DadosRecebidos(**dados_json)
        except ValidationError as ve:
            logger.error(f"[PUT] Dados inválidos recebidos: {ve}")
            return JSONResponse(status_code=400, content={"erro": "Dados inválidos", "detalhes": ve.errors()})
        
        logger.info(f"[PUT] Dados recebidos: {dados}")
        logger.info(f"[PUT] id_usuario: {dados.id_usuario}")
        logger.info(f"[PUT] id_conversa: {dados.id_conversa}")
        logger.info(f"[PUT] solicitante: {dados.solicitante}")
        logger.info(f"[PUT] contexto: {dados.contexto}")
        logger.info(f"[PUT] pergunta: {dados.pergunta}")
        
        # Loga todos os dados recebidos (log geral)
        try:
            with FileLock("log_entradas.txt.lock"):
                with open("log_entradas.txt", "a", encoding="utf-8") as log_file:
                    log_file.write(f"[{datetime.datetime.now()}] {dados_json}\n")
            logger.info("[PUT] Dados logados em log_entradas.txt")
        except Exception as e:
            logger.error(f"[PUT] Erro ao logar dados: {e}")
        
        # Salva todos os dados recebidos em um arquivo separado, em formato JSON
        try:
            with FileLock("dados_recebidos.txt.lock"):
                with open("dados_recebidos.txt", "a", encoding="utf-8") as dados_file:
                    dados_file.write(json.dumps(dados_json, ensure_ascii=False) + "\n")
            logger.info("[PUT] Dados salvos em dados_recebidos.txt: %s", dados_json)
        except Exception as e:
            logger.error("[PUT][ERRO] Erro ao salvar dados: %s", e)
            raise
        
        # Salva o histórico separado por solicitante em formato JSON válido, dentro da pasta 'historicos'
        solicitante = dados.solicitante or "desconhecido"
        nome_arquivo = os.path.join(pasta_historicos, f"historico_{solicitante}.json")
        try:
            with FileLock(nome_arquivo + ".lock"):
                historico = []
                if os.path.exists(nome_arquivo):
                    with open(nome_arquivo, "r", encoding="utf-8") as hist_file:
                        try:
                            historico = json.load(hist_file)
                        except Exception:
                            historico = []
                historico.append(dados_json)
                with open(nome_arquivo, "w", encoding="utf-8") as hist_file:
                    json.dump(historico, hist_file, ensure_ascii=False, indent=2)
            logger.info(f"[PUT] Histórico salvo em {nome_arquivo}: %s", dados_json)
        except Exception as e:
            logger.error("[PUT][ERRO] Erro ao salvar histórico do solicitante: %s", e)
            raise
        
        # Extrai e salva IDs (prioriza id_usuario, depois user_id)
        user_id_to_process = dados.id_usuario or dados.user_id
        ids = re.findall(r"\d{7,}", user_id_to_process) if user_id_to_process else []
        try:
            with FileLock("ids_salvos.txt.lock"):
                with open("ids_salvos.txt", "a") as f:
                    for user_id in ids:
                        f.write(user_id + "\n")
            logger.info(f"[PUT] IDs extraídos e salvos: {ids}")
        except Exception as e:
            logger.error(f"[PUT] Erro ao salvar IDs: {e}")
        
        # Atualizar métricas
        performance_metrics["total_requests"] += 1
        
        # Processar consulta ao Gemini em background
        async def processar_gemini():
            try:
                resposta = await consultar_gemini(dados_json)
                if resposta and not resposta.startswith("Erro:"):
                    performance_metrics["successful_requests"] += 1
                    logger.info("[PUT] Consulta ao Gemini processada com sucesso")
                else:
                    performance_metrics["failed_requests"] += 1
                    logger.error(f"[PUT] Erro na consulta ao Gemini: {resposta}")
            except Exception as e:
                performance_metrics["failed_requests"] += 1
                logger.error(f"[PUT] Erro inesperado na consulta ao Gemini: {e}")
        
        background_tasks.add_task(processar_gemini)
        logger.info("[PUT] Tarefa de consulta ao Gemini adicionada ao background.")
        
        return JSONResponse(content={
            "message": "Sua solicitação está sendo analisada. Aguarde a resposta.",
            "ids_extraidos": ids,
            "contexto_recebido": dados.contexto,
            "pergunta_recebida": dados.pergunta,
            "id_usuario": dados.id_usuario,
            "conversation_id": dados.id_conversa,
            "solicitante": dados.solicitante
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[PUT][ERRO] Erro inesperado: {e}")
        return JSONResponse(status_code=500, content={"erro": "Erro interno do servidor"})

@app.post("/webhook/freshbot")
async def enviar_freshbot(request: Request, background_tasks: BackgroundTasks):
    """
    Endpoint POST para enviar dados processados para o Freshbot.
    Processa a resposta do Gemini e envia para o Freshchat.
    """
    try:
        logger.info("[POST] Recebendo solicitação em /webhook/freshbot")
        verificar_rate_limit(request)
        
        dados_json = await request.json()
        try:
            dados = DadosRecebidos(**dados_json)
        except ValidationError as ve:
            logger.error(f"[POST] Dados inválidos recebidos: {ve}")
            return JSONResponse(status_code=400, content={"erro": "Dados inválidos", "detalhes": ve.errors()})
        
        logger.info(f"[POST] Dados recebidos: {dados}")
        
        # Validar dados obrigatórios
        if not dados.resposta_gemini:
            logger.warning("[POST] resposta_gemini não fornecida")
            return JSONResponse(status_code=400, content={"erro": "resposta_gemini é obrigatória"})
        
        if not dados.user_id and not dados.id_usuario:
            logger.warning("[POST] user_id ou id_usuario não fornecidos")
            return JSONResponse(status_code=400, content={"erro": "user_id ou id_usuario é obrigatório"})
        
        # Usar user_id ou id_usuario como conversation_id
        conversation_id = dados.user_id or dados.id_usuario
        
        async def tarefa_envio_freshchat():
            try:
                start_time = datetime.datetime.now()
                await enviar_mensagem_freshchat(conversation_id, dados.resposta_gemini)
                end_time = datetime.datetime.now()
                
                # Registrar métrica de performance
                response_time = (end_time - start_time).total_seconds()
                performance_metrics["freshchat_response_times"].append(response_time)
                if len(performance_metrics["freshchat_response_times"]) > 100:
                    performance_metrics["freshchat_response_times"] = performance_metrics["freshchat_response_times"][-100:]
                
                logger.info("[POST] Mensagem enviada para Freshchat com sucesso.")
            except Exception as e:
                logger.error(f"[POST][ERRO] Erro ao enviar mensagem para Freshchat: {e}")
        
        background_tasks.add_task(tarefa_envio_freshchat)
        return JSONResponse(content={"message": "Mensagem enviada para Freshchat com sucesso."})
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[POST][ERRO] Erro inesperado: {e}")
        return JSONResponse(status_code=500, content={"erro": "Erro interno do servidor"})

# =====================
# ENDPOINTS ADICIONAIS
# =====================
@app.get("/health")
async def health_check():
    """
    Endpoint de verificação de saúde da aplicação.
    Verifica apenas se a aplicação está rodando, sem fazer requisições externas.
    """
    return {
        "status": "healthy",
        "timestamp": datetime.datetime.now().isoformat(),
        "uptime": "running",
        "message": "Aplicação está funcionando"
    }

@app.get("/config")
async def get_config():
    """
    Endpoint para verificar configurações (sem expor tokens sensíveis).
    """
    return {
        "gemini_configured": bool(GEMINI_API_KEY),
        "freshchat_configured": bool(FRESHCHAT_API_TOKEN),
        "freshchat_base_url": FRESHCHAT_BASE_URL,
        "gemini_model": "gemini-2.5-flash",
        "rate_limit": MAX_REQUESTS_PER_MINUTE
    }

@app.get("/health/full")
async def health_check_full():
    """
    Endpoint de verificação completa de saúde da aplicação.
    Verifica todos os serviços e configurações (chamado manualmente).
    """
    health_status = {
        "status": "healthy",
        "timestamp": datetime.datetime.now().isoformat(),
        "uptime": "running",
        "services": {}
    }
    
    # Verificar Gemini (apenas verificação básica sem fazer requisições)
    try:
        if client and GEMINI_API_KEY:
            # Verificação básica sem fazer requisições HTTP
            if len(GEMINI_API_KEY) > 10:  # Token parece válido
                health_status["services"]["gemini"] = "configured"
            else:
                health_status["services"]["gemini"] = "invalid_token"
                health_status["status"] = "degraded"
        else:
            health_status["services"]["gemini"] = "not_configured"
    except Exception as e:
        health_status["services"]["gemini"] = f"error: {str(e)}"
        health_status["status"] = "degraded"
    
    # Verificar Freshchat (apenas verificação básica sem fazer requisições)
    try:
        if FRESHCHAT_API_TOKEN:
            # Verificação básica sem fazer requisições HTTP
            if len(FRESHCHAT_API_TOKEN) > 10:  # Token parece válido
                health_status["services"]["freshchat"] = "configured"
            else:
                health_status["services"]["freshchat"] = "invalid_token"
                health_status["status"] = "degraded"
        else:
            health_status["services"]["freshchat"] = "not_configured"
    except Exception as e:
        health_status["services"]["freshchat"] = f"error: {str(e)}"
        health_status["status"] = "degraded"
    
    # Verificar sistema de arquivos
    try:
        required_files = ["app.log"]
        for file in required_files:
            if not os.path.exists(file):
                health_status["services"]["filesystem"] = f"error: {file} not found"
                health_status["status"] = "degraded"
                break
        else:
            health_status["services"]["filesystem"] = "healthy"
    except Exception as e:
        health_status["services"]["filesystem"] = f"error: {str(e)}"
        health_status["status"] = "degraded"
    
    return health_status

@app.get("/test/freshchat")
async def test_freshchat_connection():
    """
    Endpoint para testar a conectividade com o Freshchat.
    """
    try:
        if not FRESHCHAT_API_TOKEN:
            return {"status": "error", "message": "Token do Freshchat não configurado"}
        
        # Teste de conectividade com Freshchat
        async with httpx.AsyncClient(timeout=10) as http_client:
            response = await http_client.get(FRESHCHAT_BASE_URL, headers={
                "Authorization": f"Bearer {FRESHCHAT_API_TOKEN}"
            })
            
            if response.status_code in [200, 401, 403]:  # 401/403 significa que o token é válido mas sem permissão
                return {"status": "success", "message": "Conexão com Freshchat funcionando", "status_code": response.status_code}
            else:
                return {"status": "error", "message": f"Erro na conexão com Freshchat: {response.status_code}", "status_code": response.status_code}
                
    except Exception as e:
        logger.error(f"[TEST] Erro ao testar Freshchat: {e}")
        return {"status": "error", "message": f"Erro ao conectar com Freshchat: {str(e)}"}

@app.post("/test/payload")
async def test_payload(request: Request):
    """
    Endpoint para testar o processamento do payload.
    """
    try:
        logger.info("[TEST] Testando processamento de payload...")
        
        dados_json = await request.json()
        logger.info(f"[TEST] Payload recebido: {dados_json}")
        
        try:
            dados = DadosRecebidos(**dados_json)
            logger.info(f"[TEST] Payload validado com sucesso: {dados}")
            
            return {
                "status": "success",
                "message": "Payload processado com sucesso",
                "dados_processados": {
                    "id_usuario": dados.id_usuario,
                    "conversation_id": dados.id_conversa,
                    "solicitante": dados.solicitante,
                    "contexto": dados.contexto,
                    "pergunta": dados.pergunta,
                    "user_id": dados.user_id
                }
            }
        except ValidationError as ve:
            logger.error(f"[TEST] Erro de validação: {ve}")
            return {
                "status": "error",
                "message": "Erro de validação",
                "erros": ve.errors()
            }
            
    except Exception as e:
        logger.error(f"[TEST] Erro inesperado: {e}")
        return {"status": "error", "message": f"Erro: {str(e)}"}

@app.post("/test/gemini")
async def test_gemini():
    """
    Endpoint para testar a conexão com o Gemini.
    """
    try:
        if not client:
            return JSONResponse(status_code=500, content={"status": "error", "message": "Cliente Gemini não configurado"})
        
        if not GEMINI_API_KEY:
            return JSONResponse(status_code=500, content={"status": "error", "message": "GEMINI_API_KEY não configurada"})
        
        # Teste simples com o Gemini
        try:
            if hasattr(client, 'generate_content'):
                response = client.generate_content(
                    "Responda apenas 'OK' se você está funcionando.",
                    generation_config={
                        "temperature": 0.1,
                        "max_output_tokens": 10
                    }
                )
            else:
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents="Responda apenas 'OK' se você está funcionando.",
                    generation_config={
                        "temperature": 0.1,
                        "max_output_tokens": 10
                    }
                )
            
            if response.text and "ok" in response.text.lower():
                return JSONResponse(content={"status": "success", "message": "Conexão com Gemini funcionando"})
            else:
                return JSONResponse(content={"status": "warning", "message": "Conexão com Gemini funcionando, mas resposta inesperada"})
                
        except Exception as api_error:
            logger.error(f"[TEST] Erro na API do Gemini: {api_error}")
            return JSONResponse(status_code=500, content={"status": "error", "message": f"Erro na API do Gemini: {str(api_error)}"})
            
    except Exception as e:
        logger.error(f"[TEST] Erro ao testar Gemini: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": f"Erro ao conectar com Gemini: {str(e)}"})

@app.post("/test/integration")
async def test_integration():
    """
    Endpoint para testar a integração completa (Gemini + Freshchat).
    """
    try:
        test_results = {
            "gemini": {"status": "unknown", "message": ""},
            "freshchat": {"status": "unknown", "message": ""},
            "overall": "unknown"
        }
        
        # Teste Gemini
        if client and GEMINI_API_KEY:
            try:
                if hasattr(client, 'generate_content'):
                    response = client.generate_content(
                        "Responda apenas 'OK' se você está funcionando.",
                        generation_config={"temperature": 0.1, "max_output_tokens": 10}
                    )
                else:
                    response = client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents="Responda apenas 'OK' se você está funcionando.",
                        generation_config={"temperature": 0.1, "max_output_tokens": 10}
                    )
                
                if response.text and "ok" in response.text.lower():
                    test_results["gemini"] = {"status": "success", "message": "Gemini funcionando"}
                else:
                    test_results["gemini"] = {"status": "warning", "message": "Gemini respondeu, mas de forma inesperada"}
            except Exception as e:
                test_results["gemini"] = {"status": "error", "message": f"Erro no Gemini: {str(e)}"}
        else:
            test_results["gemini"] = {"status": "error", "message": "Gemini não configurado"}
        
        # Teste Freshchat
        if FRESHCHAT_API_TOKEN:
            try:
                async with httpx.AsyncClient(timeout=10) as http_client:
                    response = await http_client.get(FRESHCHAT_BASE_URL, headers={
                        "Authorization": f"Bearer {FRESHCHAT_API_TOKEN}"
                    })
                    
                    if response.status_code in [200, 401, 403]:
                        test_results["freshchat"] = {"status": "success", "message": "Freshchat acessível"}
                    else:
                        test_results["freshchat"] = {"status": "error", "message": f"Erro no Freshchat: {response.status_code}"}
            except Exception as e:
                test_results["freshchat"] = {"status": "error", "message": f"Erro ao conectar com Freshchat: {str(e)}"}
        else:
            test_results["freshchat"] = {"status": "error", "message": "Freshchat não configurado"}
        
        # Determinar status geral
        gemini_ok = test_results["gemini"]["status"] in ["success", "warning"]
        freshchat_ok = test_results["freshchat"]["status"] in ["success", "warning"]
        
        if gemini_ok and freshchat_ok:
            test_results["overall"] = "success"
        elif gemini_ok or freshchat_ok:
            test_results["overall"] = "partial"
        else:
            test_results["overall"] = "error"
        
        return JSONResponse(content=test_results)
        
    except Exception as e:
        logger.error(f"[TEST] Erro no teste de integração: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": f"Erro no teste de integração: {str(e)}"})

@app.post("/cleanup")
async def cleanup_files():
    """
    Endpoint para limpeza de arquivos temporários e logs antigos.
    """
    try:
        limpar_arquivos_antigos()
        return {"message": "Limpeza concluída com sucesso"}
    except Exception as e:
        logger.error(f"[CLEANUP] Erro na limpeza: {e}")
        return {"erro": "Erro durante a limpeza"}

@app.get("/stats")
async def get_stats():
    """
    Endpoint para obter estatísticas da aplicação.
    """
    try:
        stats = {
            "total_requests": len(request_counts),
            "active_clients": len([ip for ip, times in request_counts.items() if times]),
            "rate_limit": MAX_REQUESTS_PER_MINUTE,
            "files": {}
        }
        
        # Conta arquivos de log
        for filename in ["log_entradas.txt", "dados_recebidos.txt", "ids_salvos.txt"]:
            if os.path.exists(filename):
                stats["files"][filename] = os.path.getsize(filename)
        
        # Conta arquivos de histórico
        if os.path.exists(pasta_historicos):
            historico_files = [f for f in os.listdir(pasta_historicos) if f.endswith('.json')]
            stats["files"]["historicos"] = len(historico_files)
        
        return stats
    except Exception as e:
        logger.error(f"[STATS] Erro ao obter estatísticas: {e}")
        return {"erro": "Erro ao obter estatísticas"}

@app.get("/logs")
async def get_logs(lines: int = 50, file: str = "app.log"):
    """
    Endpoint para consultar logs em tempo real.
    
    Args:
        lines: Número de linhas a retornar (padrão: 50)
        file: Arquivo de log a consultar (padrão: app.log)
    """
    try:
        allowed_files = ["app.log", "log_entradas.txt", "dados_recebidos.txt"]
        if file not in allowed_files:
            return {"erro": "Arquivo de log não permitido"}
        
        if not os.path.exists(file):
            return {"erro": "Arquivo de log não encontrado"}
        
        with open(file, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
        
        # Retorna as últimas N linhas
        last_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
        
        return {
            "file": file,
            "total_lines": len(all_lines),
            "returned_lines": len(last_lines),
            "lines": last_lines
        }
    except Exception as e:
        logger.error(f"[LOGS] Erro ao consultar logs: {e}")
        return {"erro": "Erro ao consultar logs"}

@app.get("/metrics")
async def get_metrics():
    """
    Endpoint para obter métricas de performance da aplicação.
    """
    try:
        # Calcular estatísticas das métricas
        gemini_times = performance_metrics["gemini_response_times"]
        freshchat_times = performance_metrics["freshchat_response_times"]
        
        metrics = {
            "total_requests": performance_metrics["total_requests"],
            "successful_requests": performance_metrics["successful_requests"],
            "failed_requests": performance_metrics["failed_requests"],
            "success_rate": (performance_metrics["successful_requests"] / max(performance_metrics["total_requests"], 1)) * 100,
            "gemini": {
                "total_requests": len(gemini_times),
                "avg_response_time": sum(gemini_times) / len(gemini_times) if gemini_times else 0,
                "min_response_time": min(gemini_times) if gemini_times else 0,
                "max_response_time": max(gemini_times) if gemini_times else 0
            },
            "freshchat": {
                "total_requests": len(freshchat_times),
                "avg_response_time": sum(freshchat_times) / len(freshchat_times) if freshchat_times else 0,
                "min_response_time": min(freshchat_times) if freshchat_times else 0,
                "max_response_time": max(freshchat_times) if freshchat_times else 0
            }
        }
        
        return metrics
    except Exception as e:
        logger.error(f"[METRICS] Erro ao obter métricas: {e}")
        return {"erro": "Erro ao obter métricas"}
