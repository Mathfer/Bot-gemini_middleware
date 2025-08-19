#!/bin/bash

# Script de inicialização para o Bot Middleware Gemini

echo "Iniciando Bot Middleware Gemini..."

# Verificar se as variáveis de ambiente estão definidas
if [ -z "$GEMINI_API_KEY" ]; then
    echo "WARNING: GEMINI_API_KEY não está definida"
else
    echo "GEMINI_API_KEY configurada"
fi

if [ -z "$FRESHCHAT_API_TOKEN" ]; then
    echo "WARNING: FRESHCHAT_API_TOKEN não está definida"
else
    echo "FRESHCHAT_API_TOKEN configurada"
fi

if [ -z "$TOKEN_ESPERADO" ]; then
    echo "WARNING: TOKEN_ESPERADO não está definida"
else
    echo "TOKEN_ESPERADO configurada"
fi

# Criar diretórios necessários
mkdir -p historicos logs

# Iniciar a aplicação
exec uvicorn main:app --host 0.0.0.0 --port 8000 --reload
