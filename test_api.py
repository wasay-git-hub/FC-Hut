from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_api_endpoints():
    # 1. Test Root
    res = client.get("/")
    assert res.status_code == 200
    assert res.json()["business"] == "FC-Hut (Frozen Chicken Hut)"
    print("GET / passed!")

    # 2. Test Products
    res = client.get("/products")
    assert res.status_code == 200
    products = res.json()["products"]
    assert len(products) >= 10
    print(f"GET /products passed! Found {len(products)} products.")

    # 3. Test Orders
    res = client.get("/orders")
    assert res.status_code == 200
    print("GET /orders passed!")

    # 4. Test Webhook Verification (Success)
    res = client.get("/webhook?hub.mode=subscribe&hub.verify_token=fchut_secret_verify_token_123&hub.challenge=115599")
    assert res.status_code == 200
    assert res.text == "115599"
    print("GET /webhook (Meta verification success) passed!")

    # 5. Test Webhook Verification (Failure)
    res = client.get("/webhook?hub.mode=subscribe&hub.verify_token=wrong_token&hub.challenge=115599")
    assert res.status_code == 403
    print("GET /webhook (Security rejection on wrong token) passed!")

    # 6. Test direct chat endpoint
    res = client.post("/test-chat", json={"phone": "+923001234567", "message": "What do you have in stock?"})
    assert res.status_code == 200
    reply = res.json()["reply"]
    assert len(reply) > 0
    print("POST /test-chat passed!")

    print("\nAll FastAPI Webhook endpoints verified successfully!")

if __name__ == "__main__":
    test_api_endpoints()
