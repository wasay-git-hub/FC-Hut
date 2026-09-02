import sys
import database
from agent import FCHutAgent
from fastapi.testclient import TestClient
from main import app

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

client = TestClient(app)

def test_business_rules_flow():
    print("--- 1. Reset Database & Pre-seed with Packets ---")
    database.init_db()
    database.seed_products(force=True)
    
    agent = FCHutAgent()
    phone = "+923007778899"
    database.clear_session(phone)

    # -------------------------------------------------------------
    # Step 1: Greeting / In-stock menu in packets
    # -------------------------------------------------------------
    print("\n--- 2. Customer: Greeting ---")
    resp = agent.process_input(phone, user_text="salam")
    assert resp["type"] == "interactive_list"
    text = resp["text"]
    assert "packet" in text.lower(), "Menu must specify prices in packets"
    assert "Chicken Seekh Kabab" in text
    assert "consists of" in text
    print("Agent sent in-stock menu with prices per packet & piece counts!")

    # -------------------------------------------------------------
    # Step 2: Customer selects 1 item (Seekh Kabab)
    # -------------------------------------------------------------
    print("\n--- 3. Customer selects 'prod_9' (Chicken Seekh Kabab) ---")
    resp = agent.process_input(phone, interactive_id="prod_9")
    assert resp["type"] == "text"
    assert "How many packets would you like to order?" in resp["text"]
    print("Agent asked for quantity with NO buttons (open natural language)!")

    # -------------------------------------------------------------
    # Step 3: Customer replies in Roman Urdu ("mujhe 2 packets chahiyen")
    # -------------------------------------------------------------
    print("\n--- 4. Customer replies: 'mujhe 2 packets chahiyen' ---")
    resp = agent.process_input(phone, user_text="mujhe 2 packets chahiyen")
    assert resp["type"] == "interactive_buttons"
    assert "Do you want to order something else?" in resp["buttons_data"]["body"]
    buttons = resp["buttons_data"]["buttons"]
    assert buttons[0]["title"] == "Yes" and buttons[0]["id"] == "more_yes"
    assert buttons[1]["title"] == "No" and buttons[1]["id"] == "more_no"
    print("Agent added 2 packets to cart & asked 'Do you want to order something else?' with [Yes] / [No]!")

    # -------------------------------------------------------------
    # Step 4: Customer taps [Yes] to order something else
    # -------------------------------------------------------------
    print("\n--- 5. Customer taps [Yes] to add more items ---")
    resp = agent.process_input(phone, interactive_id="more_yes")
    assert resp["type"] == "interactive_list"
    print("Agent showed available menu again!")

    # -------------------------------------------------------------
    # Step 5: Customer selects Samosas (prod_10)
    # -------------------------------------------------------------
    print("\n--- 6. Customer selects 'prod_10' (Crispy Chicken Samosas) ---")
    samosa_initial = database.get_product_by_id(10)
    samosa_stock = samosa_initial["stock_qty"]
    resp = agent.process_input(phone, interactive_id="prod_10")
    assert resp["type"] == "text"
    
    # -------------------------------------------------------------
    # Step 6: Customer asks for quantity exceeding stock (e.g. 500 packets)
    # -------------------------------------------------------------
    print(f"\n--- 7. Customer asks for 500 packets (Available: {samosa_stock}) ---")
    resp = agent.process_input(phone, user_text="give me 500 packets please")
    assert resp["type"] == "interactive_buttons"
    assert f"{samosa_stock} packet" in resp["text"]
    shortage_buttons = resp["buttons_data"]["buttons"]
    assert shortage_buttons[0]["id"] == "partial_confirm"
    assert f"Yes, confirm {samosa_stock}" in shortage_buttons[0]["title"]
    assert shortage_buttons[1]["id"] == "partial_leave"
    assert shortage_buttons[1]["title"] == "No, leave product"
    print(f"Agent informed exact {samosa_stock} packets available and provided 2 buttons: [Yes, confirm X pkts] & [No, leave product]!")

    # -------------------------------------------------------------
    # Step 7: Customer taps [Yes, confirm X packets]
    # -------------------------------------------------------------
    print(f"\n--- 8. Customer taps [Yes, confirm {samosa_stock} pkts] ---")
    resp = agent.process_input(phone, interactive_id="partial_confirm")
    assert resp["type"] == "interactive_buttons"
    assert "Do you want to order something else?" in resp["buttons_data"]["body"]
    print("Agent added partial available packets to cart and asked 'Do you want to order something else?'!")

    # -------------------------------------------------------------
    # Step 8: Customer taps [No] (Done selecting items)
    # -------------------------------------------------------------
    print("\n--- 9. Customer taps [No] ---")
    resp = agent.process_input(phone, interactive_id="more_no")
    assert resp["type"] == "text"
    assert "Delivery Address" in resp["text"] and "Phone Number" in resp["text"]
    print("Agent prompted customer for Delivery Address and Phone Number!")

    # -------------------------------------------------------------
    # Step 9: Customer types address & phone in natural language
    # -------------------------------------------------------------
    print("\n--- 10. Customer sends address & contact number ---")
    resp = agent.process_input(phone, user_text="House 15, Street 4, Sector F-7/2, Islamabad. 03001234567")
    assert resp["type"] == "interactive_buttons"
    assert "ORDER SUMMARY" in resp["text"]
    assert "03001234567" in resp["text"]
    assert "House 15" in resp["text"]
    confirm_buttons = resp["buttons_data"]["buttons"]
    assert confirm_buttons[0]["id"] == "final_confirm"
    assert confirm_buttons[0]["title"] == "Yes, I confirm"
    assert confirm_buttons[1]["id"] == "final_cancel"
    assert confirm_buttons[1]["title"] == "No, cancel"
    print("Agent sent Order Summary with [Yes, I confirm] and [No, cancel] buttons!")

    # -------------------------------------------------------------
    # Step 10: Customer taps [Yes, I confirm]
    # -------------------------------------------------------------
    print("\n--- 11. Customer taps [Yes, I confirm] ---")
    resp = agent.process_input(phone, interactive_id="final_confirm")
    assert resp["type"] == "text"
    assert "Your order has been confirmed!" in resp["text"]
    assert "6-7 PM" in resp["text"] or "6-7 pm" in resp["text"].lower()
    print("Agent confirmed order and warmly announced delivery in between 6-7 PM! 🛵🍗")

    # Verify inventory was deducted in SQLite
    updated_samosas = database.get_product_by_id(10)["stock_qty"]
    assert updated_samosas == 0, f"Expected 0 samosas left, got {updated_samosas}"
    print(f"Verified Samosas stock decremented from {samosa_stock} -> {updated_samosas}!")

    # -------------------------------------------------------------
    # Step 11: Cancellation Test (Customer taps [No, cancel])
    # -------------------------------------------------------------
    print("\n--- 12. Test Cancellation Branch ---")
    phone2 = "+923008889900"
    database.clear_session(phone2)
    agent.process_input(phone2, user_text="salam")
    agent.process_input(phone2, interactive_id="prod_1") # nuggets
    agent.process_input(phone2, user_text="1 packet")
    agent.process_input(phone2, interactive_id="more_no")
    agent.process_input(phone2, user_text="Flat 2B, Islamabad 03009999999")
    cancel_resp = agent.process_input(phone2, interactive_id="final_cancel")
    # -------------------------------------------------------------
    # Step 12: Multi-Text Address & Phone Test
    # -------------------------------------------------------------
    print("\n--- 13. Test Separate Address & Phone Messages ---")
    phone3 = "+923004443322"
    database.clear_session(phone3)
    agent.process_input(phone3, user_text="salam")
    agent.process_input(phone3, interactive_id="prod_1") # nuggets
    agent.process_input(phone3, user_text="1 packet")
    agent.process_input(phone3, interactive_id="more_no")
    
    # Customer sends address only in Text 1
    resp_addr = agent.process_input(phone3, user_text="House 22, Street 8, F-11/1, Islamabad")
    assert "Address noted" in resp_addr["text"]
    assert "Contact Phone Number" in resp_addr["text"]
    print("Agent received address only, acknowledged it, and asked for phone number!")

    # Customer sends phone only in Text 2
    resp_phone = agent.process_input(phone3, user_text="03001234567")
    assert resp_phone["type"] == "interactive_buttons"
    assert "ORDER SUMMARY" in resp_phone["text"]
    assert "03001234567" in resp_phone["text"]
    assert "House 22" in resp_phone["text"]
    print("Agent combined address and phone across multiple messages and sent Order Summary!")

    # Customer confirms
    conf = agent.process_input(phone3, interactive_id="final_confirm")
    assert "Your order has been confirmed!" in conf["text"]
    assert "6-7 PM" in conf["text"] or "6-7 pm" in conf["text"].lower()

    # -------------------------------------------------------------
    # Step 13: Test 'same number' shortcut
    # -------------------------------------------------------------
    print("\n--- 14. Test 'Same Number' Shortcut ---")
    phone4 = "+923009990011"
    database.clear_session(phone4)
    agent.process_input(phone4, user_text="salam")
    agent.process_input(phone4, interactive_id="prod_2") # tempura nuggets
    agent.process_input(phone4, user_text="2 packets")
    agent.process_input(phone4, interactive_id="more_no")
    
    # Text 1: Address
    agent.process_input(phone4, user_text="Sector I-8/2, Islamabad")
    # Text 2: "same number"
    resp_same = agent.process_input(phone4, user_text="yehi number hai")
    assert resp_same["type"] == "interactive_buttons"
    assert "ORDER SUMMARY" in resp_same["text"]
    assert phone4 in resp_same["text"]
    print("Agent correctly used customer's WhatsApp phone number when customer said 'yehi number hai'!")

    print("\n[SUCCESS] All Defined Business Rules & Flows verified successfully! 🎉")

if __name__ == "__main__":
    test_business_rules_flow()
