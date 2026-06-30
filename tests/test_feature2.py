import requests

base_url = 'http://localhost:5000/api'

# The payload for your NEW MT5 demo account
payload = {
    "user_id": 1,
    "account_no": "109043772",
    "broker_name": "MetaQuotes-Demo"
}

print("=== 1. Registering New Account ===")
response1 = requests.post(f"{base_url}/accounts", json=payload)
print(f"HTTP Status: {response1.status_code}")
print(f"Response: {response1.json()}\n")

print("=== 2. Testing Duplicate Protection (Adding same account again) ===")
response2 = requests.post(f"{base_url}/accounts", json=payload)
print(f"HTTP Status: {response2.status_code} (Expected: 409)")
print(f"Response: {response2.json()}\n")
