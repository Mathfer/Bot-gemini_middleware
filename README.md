# Bot Middleware Gemini

Middleware para integração entre Freshchat e Google Gemini AI, desenvolvido em FastAPI.

## 🚀 URL Pública

https://bot-gemini-152892554473.southamerica-east1.run.app/

## Funcionalidades

- Recebe dados do Freshchat via webhook
- Processa consultas usando a API do Google Gemini
- Envia respostas de volta para o Freshchat
- Armazena histórico de conversas por solicitante
- Sistema de logging completo com rotação
- Autenticação via Bearer Token
- Rate limiting para proteção contra spam
- Sanitização de dados de entrada
- CORS configurado para integração com frontend
- Endpoints de monitoramento e manutenção

## Configuração

### Variáveis de Ambiente

Copie o arquivo `env.example` para `.env` e configure as variáveis:

```bash
cp env.example .env
```

Ou crie um arquivo `.env` na raiz do projeto com as seguintes variáveis:

```env
# Token de autorização para a API (obrigatório)
TOKEN_ESPERADO=RLjUoIUiajoI8Ss33WATbH3-KDhIkpAlNUmPjDIhQ7k

# Configurações do Freshchat (obrigatório)
FRESHCHAT_API_TOKEN=seu_token_do_freshchat_aqui
FRESHCHAT_BASE_URL=https://api.freshchat.com/v2

# Configurações do Gemini (obrigatório)
GEMINI_API_KEY=sua_api_key_do_gemini_aqui

# Configurações de Rate Limiting (opcional)
MAX_REQUESTS_PER_MINUTE=60
```

### Instalação

1. Instale as dependências:
```bash
pip install -r requirements.txt
```

2. Configure as variáveis de ambiente no arquivo `.env`

3. Execute o servidor:
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## Endpoints

### PUT /webhook/freshbot
Recebe dados do Freshchat e inicia processamento em background.

**Headers necessários:**
- `Authorization: Bearer <TOKEN_ESPERADO>`

**Body (JSON):**
```json
{
    "solicitante": "TESTE",
    "contexto": "teste",
    "pergunta": "isso é um teste"
}
```

### GET /webhook/freshbot/search_id
Pega a resposta do Gemini e envia para o Freshchat.


### GET /health
Verificação de saúde da aplicação.

### GET /config
Verifica configurações (sem expor tokens sensíveis).

### POST /cleanup
Executa limpeza de arquivos temporários e logs antigos.

### GET /stats
Obtém estatísticas da aplicação (requisições, arquivos, etc.).

### POST /test/gemini
Testa a conexão com o Gemini para verificar se está funcionando.

### POST /test/integration
Testa a integração completa (Gemini + Freshchat) e retorna o status de ambos os serviços.

### GET /logs
Consulta logs em tempo real. Parâmetros: `lines` (número de linhas) e `file` (arquivo de log).

### GET /metrics
Obtém métricas de performance da aplicação (tempos de resposta, taxa de sucesso, etc.).

## Estrutura de Arquivos

```
Bot_Middleware_Gemini/
├── main.py                 # Arquivo principal da aplicação
├── requirements.txt        # Dependências do projeto
├── README.md              # Documentação principal
├── DEPLOY.md              # Guia completo de deploy
├── QUICK-START.md         # Início rápido
├── OPCOES_LOCAIS.md       # Opções locais de deploy
├── env.example            # Exemplo de configuração
├── .env                   # Variáveis de ambiente (criar)
├── .gitignore             # Arquivos ignorados pelo Git
├── Dockerfile             # Configuração Docker
├── docker-compose.yml     # Compose para desenvolvimento
├── start.sh               # Script de inicialização
├── railway.json           # Configuração Railway
├── test-public-url.py     # Script de teste de URL pública
├── dados_recebidos.txt    # Log de todos os dados recebidos
├── log_entradas.txt       # Log geral de entradas
├── ids_salvos.txt         # IDs extraídos das conversas
├── app.log                # Log da aplicação
└── historicos/            # Histórico por solicitante
    ├── historico_*.json   # Arquivos de histórico individuais
```

## Funcionalidades de Logging

- **Log Geral**: Todos os dados recebidos são logados em `log_entradas.txt`
- **Dados Recebidos**: Dados em formato JSON são salvos em `dados_recebidos.txt`
- **Histórico por Solicitante**: Cada solicitante tem seu próprio arquivo JSON em `historicos/`
- **IDs Extraídos**: IDs numéricos são extraídos e salvos em `ids_salvos.txt`

## Tratamento de Erros

- Validação de dados de entrada com limites de tamanho
- Sanitização automática de strings (remove HTML e caracteres perigosos)
- Tratamento de timeouts nas APIs
- Logging detalhado de erros com rotação de arquivos
- Respostas de erro padronizadas
- Verificação de configurações obrigatórias
- Rate limiting para proteção contra spam

## Segurança

- Autenticação via Bearer Token
- Validação de dados de entrada com Pydantic
- Sanitização automática de dados de entrada
- Rate limiting por IP para prevenir spam
- Uso de FileLock para operações concorrentes em arquivos
- Não exposição de tokens sensíveis em endpoints de configuração
- CORS configurado para controle de acesso

## Desenvolvimento

Para desenvolvimento local:

```bash
# Instalar dependências
pip install -r requirements.txt

# Executar com reload automático
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Acessar documentação da API
# http://localhost:8000/docs

## 🧪 Testando URL Pública

Após fazer o deploy, você pode testar se a URL pública está funcionando:

```bash
# Teste básico
python test-public-url.py https://sua-url.onrender.com

# Ou usando curl
curl https://sua-url.onrender.com/health
curl https://sua-url.onrender.com/config
```

## 📋 Configuração do Webhook

Após obter a URL pública, configure o webhook no Freshchat:

- **URL**: `https://sua-url.onrender.com/webhook/freshbot`
- **Método**: `PUT`
- **Headers**: `Authorization: Bearer RLjUoIUiajoI8Ss33WATbH3-KDhIkpAlNUmPjDIhQ7k` 
