import sys
import database
from agent import FCHutAgent

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

def run_e2e_test():
    print("--- 1. Initializing & Re-seeding DB ---")
    database.init_db()
    database.seed_products(force=True)
    
    agent = FCHutAgent()
    phone = "+923009876543"
    database.clear_session(phone)
    
    print("\n--- 2. Customer: Greeting ---")
    resp = agent.handle_message(phone, "Assalam o alaikum")
    print(f"Agent:\n{resp}")
    assert "fc-hut" in resp.lower(), "Greeting should mention FC-Hut"
    assert "packet" in resp.lower(), "Menu should show prices per packet"

    print("\n--- 3. Customer: Selects Nuggets ---")
    resp = agent.handle_message(phone, "I want Crispy Chicken Nuggets")
    print(f"Agent:\n{resp}")
    assert "How many packets" in resp, "Should ask for packet quantity"

    print("\n--- 4. Customer: Provides Quantity in Roman Urdu ---")
    resp = agent.handle_message(phone, "mujhe 2 packets chahiyen")
    print(f"Agent:\n{resp}")
    assert "Do you want to order something else?" in resp

    print("\n--- 5. Customer: No more items ---")
    resp = agent.handle_message(phone, "no, that's all")
    print(f"Agent:\n{resp}")
    assert "Delivery Address" in resp and "Phone Number" in resp

    print("\n--- 6. Customer: Provides Address & Phone ---")
    resp = agent.handle_message(phone, "House 15, Street 4, Sector F-7/2, Islamabad. 03009876543")
    print(f"Agent Summary:\n{resp}")
    assert "ORDER SUMMARY" in resp
    assert "03009876543" in resp

    print("\n--- 7. Customer: Confirms Order ---")
    confirm_resp = agent.handle_message(phone, "Yes I confirm")
    print(f"Agent Confirmation:\n{confirm_resp}")
    assert "confirmed" in confirm_resp.lower()
    assert "6-7 PM" in confirm_resp or "6-7 pm" in confirm_resp.lower(), "Must mention delivery 6-7 PM"

    # Check orders table
    orders = database.get_orders()
    assert len(orders) >= 1, "Order should be stored in orders table"
    latest = orders[0]
    print(f"\nStored Order in DB: Order #{latest['id']} | Total: Rs. {latest['total_pkr']:,} | Address: {latest['delivery_address']}")

    print("\n[SUCCESS] All E2E WhatsApp Agent flow tests passed successfully!")

if __name__ == "__main__":
    run_e2e_test()
