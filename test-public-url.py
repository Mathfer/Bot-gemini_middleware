#!/usr/bin/env python3
"""
Script para testar a URL pública do Bot Middleware Gemini
"""

import requests
import json
import sys
from datetime import datetime

def test_endpoint(url, endpoint, method="GET", data=None, headers=None):
    """Testa um endpoint específico"""
    try:
        full_url = f"{url.rstrip('/')}/{endpoint.lstrip('/')}"
        print(f"🔍 Testando: {method} {full_url}")
        
        if method.upper() == "GET":
            response = requests.get(full_url, headers=headers, timeout=10)
        elif method.upper() == "POST":
            response = requests.post(full_url, json=data, headers=headers, timeout=10)
        elif method.upper() == "PUT":
            response = requests.put(full_url, json=data, headers=headers, timeout=10)
        else:
            print(f"❌ Método {method} não suportado")
            return False
        
        print(f"📊 Status: {response.status_code}")
        
        if response.status_code == 200:
            print(f"✅ Sucesso!")
            try:
                result = response.json()
                print(f"📄 Resposta: {json.dumps(result, indent=2, ensure_ascii=False)}")
            except:
                print(f"📄 Resposta: {response.text[:200]}...")
            return True
        else:
            print(f"❌ Erro: {response.status_code}")
            print(f"📄 Resposta: {response.text}")
            return False
            
    except requests.exceptions.Timeout:
        print(f"⏰ Timeout ao acessar {endpoint}")
        return False
    except requests.exceptions.ConnectionError:
        print(f"🔌 Erro de conexão ao acessar {endpoint}")
        return False
    except Exception as e:
        print(f"💥 Erro inesperado: {e}")
        return False

def main():
    if len(sys.argv) < 2:
        print("🚀 Uso: python test-public-url.py <URL_PUBLICA>")
        print("📝 Exemplo: python test-public-url.py https://seu-bot-production.up.railway.app")
        sys.exit(1)
    
    url = sys.argv[1]
    print(f"🌐 Testando URL pública: {url}")
    print(f"⏰ Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # Teste básico de conectividade
    print("🔗 Teste de conectividade básica...")
    try:
        response = requests.get(url, timeout=5)
        print(f"✅ Conectividade OK - Status: {response.status_code}")
    except Exception as e:
        print(f"❌ Erro de conectividade: {e}")
        sys.exit(1)
    
    print("\n" + "=" * 60)
    
    # Testar endpoints
    tests = [
        ("health", "GET"),
        ("config", "GET"),
        ("stats", "GET"),
        ("metrics", "GET"),
    ]
    
    success_count = 0
    total_tests = len(tests)
    
    for endpoint, method in tests:
        print(f"\n🧪 Teste {tests.index((endpoint, method)) + 1}/{total_tests}")
        if test_endpoint(url, endpoint, method):
            success_count += 1
        print("-" * 40)
    
    # Teste com autenticação
    print(f"\n🔐 Teste com autenticação...")
    headers = {"Authorization": "Bearer RLjUoIUiajoI8Ss33WATbH3-KDhIkpAlNUmPjDIhQ7k"}
    test_data = {
        "solicitante": "teste",
        "contexto": "Teste de conectividade",
        "pergunta": "Olá, isso é um teste",
        "user_id": "123456",
        "id_usuario": "123456",
        "id_conversa": "teste-123"
    }
    
    if test_endpoint(url, "webhook/freshbot", "PUT", test_data, headers):
        success_count += 1
    
    print("\n" + "=" * 60)
    print(f"📊 Resultado Final: {success_count}/{total_tests + 1} testes passaram")
    
    if success_count == total_tests + 1:
        print("🎉 Todos os testes passaram! Sua aplicação está funcionando perfeitamente.")
        print(f"🔗 URL pública: {url}")
        print(f"📋 Webhook URL: {url}/webhook/freshbot")
        print(f"🔑 Token: RLjUoIUiajoI8Ss33WATbH3-KDhIkpAlNUmPjDIhQ7k")
    else:
        print("⚠️ Alguns testes falharam. Verifique a configuração da aplicação.")
        sys.exit(1)

if __name__ == "__main__":
    main()
