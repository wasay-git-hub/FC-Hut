import database
from agent import FCHutAgent
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_interactive_flow():
    print("--- 1. Reset Database ---")
    database.init_db()
    database.seed_products(force=True)
    
    agent = FCHutAgent()
    phone = "+923005554433"
    database.clear_session(phone)
    
    # Step 1: Greeting -> Native List Menu returned
    print("\n--- 2. Customer: Greeting ---")
    resp = agent.process_input(phone, user_text="Salam")
    assert resp["type"] == "interactive_list", f"Expected interactive_list, got {resp['type']}"
    assert len(resp["list_data"]["sections"][0]["rows"]) >= 10
    print("Agent returned WhatsApp Native List Menu with all items!")

    # Step 2: Customer taps an item from the list (e.g. "prod_10" -> Samosas)
    print("\n--- 3. Customer taps 'prod_10' (Crispy Chicken Samosas) ---")
    samosa_initial = database.get_product_by_id(10)
    initial_stock = samosa_initial["stock_qty"]
    print(f"Initial stock for {samosa_initial['name']}: {initial_stock}")
    
    resp = agent.process_input(phone, interactive_id="prod_10")
    assert resp["type"] == "interactive_buttons", f"Expected interactive_buttons, got {resp['type']}"
    buttons = resp["buttons_data"]["buttons"]
    assert len(buttons) == 3
    assert buttons[0]["id"] == "qty_1"
    assert buttons[1]["id"] == "qty_2"
    print("Agent returned Quantity Quick Reply buttons: [ 1 Pack ] [ 2 Packs ] [ 3 Packs ]")

    # Step 3: Customer taps quantity button [ 2 Packs ] ("qty_2")
    print("\n--- 4. Customer taps [ 2 Packs ] (qty_2) ---")
    resp = agent.process_input(phone, interactive_id="qty_2")
    assert "Please reply with your complete Delivery Address" in resp["text"]
    session = database.get_session(phone)
    assert session["state"] == "AWAITING_ADDRESS"
    assert session["data"]["qty"] == 2
    print("Session moved to AWAITING_ADDRESS, quantity 2 recorded!")

    # Step 4: Customer sends delivery address
    print("\n--- 5. Customer sends delivery address ---")
    address = "Flat 4B, Silver Heights, Sector E-11/2, Islamabad"
    resp = agent.process_input(phone, user_text=address)
    assert resp["type"] == "interactive_buttons"
    assert resp["buttons_data"]["buttons"][0]["id"] == "order_confirm"
    assert resp["buttons_data"]["buttons"][1]["id"] == "order_cancel"
    print("Agent returned Confirmation buttons: [ Confirm Order ] [ Cancel ]")

    # Step 5: Customer taps [ Confirm Order ] ("order_confirm")
    print("\n--- 6. Customer taps [ Confirm Order ] ---")
    resp = agent.process_input(phone, interactive_id="order_confirm")
    assert "ORDER CONFIRMED" in resp["text"]
    
    # Verify stock decremented in SQLite
    updated_stock = database.get_product_by_id(10)["stock_qty"]
    print(f"Updated stock for Samosas: {updated_stock} (Decreased from {initial_stock})")
    assert updated_stock == initial_stock - 2

    # Verify session cleared
    session = database.get_session(phone)
    assert session["state"] == "IDLE"
    print("Session state reset to IDLE after confirmation!")

    # Step 6: Test Roman Urdu / Typo tolerance: "bhai 2 samosiyan bhej do"
    print("\n--- 7. Test Roman Urdu 'samosiyan' direct order ---")
    phone2 = "+923009998877"
    database.clear_session(phone2)
    resp = agent.process_input(phone2, user_text="bhai 2 samosiyan bhej do")
    assert "Selected: *2x Crispy Chicken Samosas" in resp["text"]
    assert "Please reply with your complete Delivery Address" in resp["text"]
    print("Correctly recognized 'samosiyan' and quantity 2!")

    # Step 7: Test Meta Webhook HTTP payload with interactive list and button replies
    print("\n--- 8. Test Meta Webhook HTTP endpoints with interactive events ---")
    phone3 = "+923001112233"
    
    # Webhook list_reply payload
    meta_list_payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "123",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"display_phone_number": "123", "phone_number_id": "123"},
                    "messages": [{
                        "from": phone3,
                        "id": "wamid.123",
                        "timestamp": "1234567890",
                        "type": "interactive",
                        "interactive": {
                            "type": "list_reply",
                            "list_reply": {"id": "prod_1", "title": "Crispy Chicken Nuggets"}
                        }
                    }]
                },
                "field": "messages"
            }]
        }]
    }
    r = client.post("/webhook", json=meta_list_payload)
    assert r.status_code == 200
    assert database.get_session(phone3)["state"] == "AWAITING_QTY"
    print("POST /webhook successfully processed native list_reply event!")

    print("\n[PASSED] All WhatsApp Native Interactive Buttons & Lists tests succeeded! 🎉")

if __name__ == "__main__":
    test_interactive_flow()
