FROM python:3.11-slim

WORKDIR /app

# Instalar dependências do sistema
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copiar arquivos de dependências
COPY requirements.txt .

# Instalar dependências Python
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código da aplicação
COPY main.py .
COPY start.sh .

# Criar diretórios necessários
RUN mkdir -p historicos logs

# Tornar o script executável
RUN chmod +x start.sh

# Expor porta
EXPOSE 8000

# Comando para executar a aplicação
CMD ["./start.sh"] 