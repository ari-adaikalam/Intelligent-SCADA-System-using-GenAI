"""
SWAT Chatbot Diagnostic Script
===============================
Tests all endpoints to identify issues
"""

import requests
import json

def test_endpoint(name, url, method="GET", data=None):
    """Test an endpoint and print results"""
    print(f"\n{'='*60}")
    print(f"Testing: {name}")
    print(f"URL: {url}")
    print(f"Method: {method}")
    
    try:
        if method == "GET":
            response = requests.get(url, timeout=5)
        else:
            response = requests.post(url, json=data, timeout=5)
        
        print(f"✅ Status Code: {response.status_code}")
        
        try:
            result = response.json()
            print(f"Response: {json.dumps(result, indent=2)}")
        except:
            print(f"Response (text): {response.text[:200]}")
        
        return True
        
    except requests.exceptions.ConnectionError:
        print(f"❌ CONNECTION ERROR - Service not running")
        return False
    except requests.exceptions.Timeout:
        print(f"❌ TIMEOUT - Service too slow")
        return False
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False


def main():
    print("="*60)
    print("SWAT AI CHATBOT DIAGNOSTIC")
    print("="*60)
    
    results = {}
    
    # Test 1: Ollama
    results['ollama'] = test_endpoint(
        "Ollama API",
        "http://127.0.0.1:11434/api/tags",
        "GET"
    )
    
    # Test 2: ML API
    results['ml_api'] = test_endpoint(
        "ML API Health",
        "http://127.0.0.1:5000/health",
        "GET"
    )
    
    # Test 3: RAG API
    results['rag_api'] = test_endpoint(
        "RAG API Health",
        "http://127.0.0.1:5001/health",
        "GET"
    )
    
    # Test 4: C# Backend
    results['backend'] = test_endpoint(
        "C# Backend Chat Status",
        "http://localhost:65040/api/chat/status",
        "GET"
    )
    
    # Test 5: RAG Chat Endpoint
    if results['rag_api']:
        results['rag_chat'] = test_endpoint(
            "RAG API Chat",
            "http://127.0.0.1:5001/api/chat",
            "POST",
            {
                "sessionId": "diagnostic_test",
                "message": "Hello, this is a test",
                "conversationHistory": [],
                "realtimeData": None,
                "databaseConnection": {
                    "server": "localhost",
                    "database": "swat",
                    "username": "test",
                    "password": "test"
                }
            }
        )
    
    # Summary
    print("\n" + "="*60)
    print("DIAGNOSTIC SUMMARY")
    print("="*60)
    
    for service, status in results.items():
        icon = "✅" if status else "❌"
        print(f"{icon} {service.upper()}: {'ONLINE' if status else 'OFFLINE'}")
    
    print("\n" + "="*60)
    
    # Recommendations
    print("\nRECOMMENDATIONS:")
    
    if not results.get('ollama'):
        print("❌ Start Ollama: ollama serve")
    
    if not results.get('ml_api'):
        print("❌ Start ML API: dotnet run (in SwatDashboard folder)")
    
    if not results.get('rag_api'):
        print("❌ Start RAG API: python rag_api.py (in PythonRagService folder)")
    
    if not results.get('backend'):
        print("❌ Start C# Backend: dotnet run (in SwatDashboard folder)")
        print("   Or check port - may not be 65040")
    
    if all([results.get('ollama'), results.get('ml_api'), results.get('rag_api')]):
        print("✅ All services running! Check browser console (F12) for frontend errors.")


if __name__ == "__main__":
    main()
