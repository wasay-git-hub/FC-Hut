import sys
import database
from agent import FCHutAgent

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

def test_brain_features():
    print("--- 1. Initialize Database ---")
    database.init_db()
    database.seed_products(force=True)
    
    agent = FCHutAgent()
    phone = "+923001239988"
    database.clear_session(phone)

    # -------------------------------------------------------------
    # Test 1: Ghosting & Returning with Greeting
    # -------------------------------------------------------------
    print("\n--- 2. Test Ghosting & Return with Greeting ---")
    # Customer asks for nuggets
    agent.process_input(phone, user_text="I want Crispy Chicken Nuggets")
    session = database.get_session(phone)
    assert session["state"] == "AWAITING_QTY"
    print("Customer was at AWAITING_QTY for nuggets.")
    
    # Customer ghosts for 3 days and returns with a greeting
    ghost_reply = agent.process_input(phone, user_text="Assalam o alaikum")
    assert ghost_reply["type"] == "interactive_list"
    assert "welcome back" in ghost_reply["text"].lower() or "salam" in ghost_reply["text"].lower()
    # Ensure state was cleanly reset and menu is shown
    new_session = database.get_session(phone)
    assert new_session["state"] == "IDLE"
    print("[Brain Verified] Agent detected greeting after ghosting, reset stale state, and presented fresh menu!")

    # -------------------------------------------------------------
    # Test 2: Ghosting & Returning with a New Product Inquiry
    # -------------------------------------------------------------
    print("\n--- 3. Test Ghosting & Return with New Product Inquiry ---")
    phone2 = "+923005556677"
    database.clear_session(phone2)
    # Customer asks for Samosas
    agent.process_input(phone2, interactive_id="prod_10")
    assert database.get_session(phone2)["state"] == "AWAITING_QTY"
    print("Customer was at AWAITING_QTY for Samosas.")
    
    # Customer returns later and asks: "Do you have Chicken Seekh Kababs?"
    switch_reply = agent.process_input(phone2, user_text="Do you have Chicken Seekh Kabab?")
    assert "Chicken Seekh Kabab" in switch_reply["text"]
    assert "How many packets would you like" in switch_reply["text"]
    assert database.get_session(phone2)["data"]["selected_prod_id"] == 9
    print("[Brain Verified] Agent detected product switch, abandoned stale samosa state, and switched to Seekh Kabab!")

    # -------------------------------------------------------------
    # Test 3: Universal Exit at Every Single Step
    # -------------------------------------------------------------
    print("\n--- 4. Test Universal Exit ('menu', 'cancel', 'wapas', 'exit') at ALL Steps ---")
    
    # Step A: At AWAITING_QTY, customer types "menu"
    phone_u = "+923008881122"
    database.clear_session(phone_u)
    agent.process_input(phone_u, interactive_id="prod_1") # nuggets
    assert database.get_session(phone_u)["state"] == "AWAITING_QTY"
    resp_menu = agent.process_input(phone_u, user_text="menu")
    assert "Returned to Main Menu" in resp_menu["text"]
    assert database.get_session(phone_u)["state"] == "IDLE"
    print("  ✓ Universal 'menu' at AWAITING_QTY -> Main Menu!")

    # Step B: At AWAITING_ADD_MORE, customer types "wapas"
    database.clear_session(phone_u)
    agent.process_input(phone_u, interactive_id="prod_1")
    agent.process_input(phone_u, user_text="2 packets")
    assert database.get_session(phone_u)["state"] == "AWAITING_ADD_MORE"
    resp_wapas = agent.process_input(phone_u, user_text="wapas")
    assert "Returned to Main Menu" in resp_wapas["text"]
    assert database.get_session(phone_u)["state"] == "IDLE"
    print("  ✓ Universal 'wapas' at AWAITING_ADD_MORE -> Main Menu!")

    # Step C: At AWAITING_CONTACT, customer types "cancel"
    database.clear_session(phone_u)
    agent.process_input(phone_u, interactive_id="prod_1")
    agent.process_input(phone_u, user_text="1 packet")
    agent.process_input(phone_u, interactive_id="more_no")
    assert database.get_session(phone_u)["state"] == "AWAITING_CONTACT"
    resp_cancel = agent.process_input(phone_u, user_text="cancel")
    assert "Returned to Main Menu" in resp_cancel["text"]
    assert database.get_session(phone_u)["state"] == "IDLE"
    print("  ✓ Universal 'cancel' at AWAITING_CONTACT -> Main Menu!")

    # Step D: At AWAITING_ORDER_CONFIRM, customer types "exit"
    database.clear_session(phone_u)
    agent.process_input(phone_u, interactive_id="prod_1")
    agent.process_input(phone_u, user_text="1 packet")
    agent.process_input(phone_u, interactive_id="more_no")
    agent.process_input(phone_u, user_text="House 1, Islamabad 03001234567")
    assert database.get_session(phone_u)["state"] == "AWAITING_ORDER_CONFIRM"
    resp_exit = agent.process_input(phone_u, user_text="exit")
    assert "Returned to Main Menu" in resp_exit["text"]
    assert database.get_session(phone_u)["state"] == "IDLE"
    print("  ✓ Universal 'exit' at AWAITING_ORDER_CONFIRM -> Main Menu!")

    # -------------------------------------------------------------
    # Test 4: Navigation Footers
    # -------------------------------------------------------------
    print("\n--- 5. Verify Navigation Footers on Outbound Messages ---")
    msg = agent.process_input("+923000000000", user_text="hi")
    assert "Reply 'menu' anytime" in msg["text"]
    print("[Footer Verified] Escape prompt present on messages!")

    print("\n[SUCCESS] All LLM Brain Cognitive & Universal Exit tests PASSED! 🎉")

if __name__ == "__main__":
    test_brain_features()
