# Exemplos de chamadas para telas de consulta/configuração Freshchat

import httpx

# Todas as funções agora recebem freshchat_base_url e freshchat_api_token como argumento,
# e usam filtros/paginação para garantir dados sempre atualizados e evitar conversas erradas/antigas.

import datetime

async def listar_agentes(freshchat_base_url, freshchat_api_token, page=1, items_per_page=50):
    url = f"{freshchat_base_url}/agents"
    params = {"page": page, "items_per_page": items_per_page, "sort_order": "desc", "sort_by": "updated_time"}
    headers = {
        "Authorization": f"Bearer {freshchat_api_token}",
        "Accept": "application/json"
    }
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()

async def listar_usuarios(freshchat_base_url, freshchat_api_token, filtro=None, page=1, items_per_page=50):
    url = f"{freshchat_base_url}/users"
    params = filtro or {}
    params.update({"page": page, "items_per_page": items_per_page, "sort_order": "desc", "sort_by": "updated_time"})
    headers = {
        "Authorization": f"Bearer {freshchat_api_token}",
        "Accept": "application/json"
    }
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()

async def listar_conversas_usuario(freshchat_base_url, freshchat_api_token, user_id, from_time=None):
    url = f"{freshchat_base_url}/users/{user_id}/conversations"
    params = {}
    if from_time:
        params["from_time"] = from_time
    headers = {
        "Authorization": f"Bearer {freshchat_api_token}",
        "Accept": "application/json"
    }
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()

async def listar_canais(freshchat_base_url, freshchat_api_token, page=1, items_per_page=50):
    url = f"{freshchat_base_url}/channels"
    params = {"page": page, "items_per_page": items_per_page, "sort_order": "desc", "sort_by": "updated_time"}
    headers = {
        "Authorization": f"Bearer {freshchat_api_token}",
        "Accept": "application/json"
    }
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()

async def listar_grupos(freshchat_base_url, freshchat_api_token, page=1, items_per_page=50):
    url = f"{freshchat_base_url}/groups"
    params = {"page": page, "items_per_page": items_per_page, "sort_order": "desc", "sort_by": "updated_time"}
    headers = {
        "Authorization": f"Bearer {freshchat_api_token}",
        "Accept": "application/json"
    }
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()

def ler_log(file_path, linhas=50):
    with open(file_path, 'r', encoding='utf-8') as f:
        all_lines = f.readlines()
    return all_lines[-linhas:] if len(all_lines) > linhas else all_lines

async def validar_token(freshchat_base_url, freshchat_api_token):
    url = f"{freshchat_base_url}/accounts/configuration"
    headers = {
        "Authorization": f"Bearer {freshchat_api_token}",
        "Accept": "application/json"
    }
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(url, headers=headers)
        return response.status_code == 200

# Exemplo de uso para buscar apenas dados recentes:
# from_time = datetime.datetime.utcnow().isoformat()  # para buscar conversas a partir de agora
# await listar_conversas_usuario(base_url, token, user_id, from_time=from_time)
