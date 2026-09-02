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

    print("\n--- 3. Customer: Ask Menu ---")
    resp = agent.handle_message(phone, "Please show me the menu and prices")
    print(f"Agent:\n{resp}")
    assert "Rs." in resp, "Menu should show prices in PKR"

    print("\n--- 4. Customer: Check Stock for Wings ---")
    resp = agent.handle_message(phone, "Do you have wings in stock?")
    print(f"Agent:\n{resp}")
    assert "Wings" in resp or "wings" in resp, "Stock check should find wings"

    print("\n--- 5. Customer: Place Order with Delivery Address ---")
    # Check initial nuggets stock
    initial_nuggets = database.check_stock("Nuggets")[0]
    initial_stock = initial_nuggets["stock_qty"]
    print(f"Pre-order stock for {initial_nuggets['name']}: {initial_stock}")
    
    order_msg = f"I want 2 {initial_nuggets['name']} to House 15, Street 4, Sector F-7/2, Islamabad"
    resp = agent.handle_message(phone, order_msg)
    print(f"Agent Summary:\n{resp}")
    assert "ORDER SUMMARY" in resp or "Selected:" in resp
    
    # Customer confirms
    confirm_resp = agent.handle_message(phone, "Yes please confirm")
    print(f"Agent Confirmation:\n{confirm_resp}")
    assert "ORDER CONFIRMED" in confirm_resp, "Should confirm order"
    
    # Check updated stock of the exact item ordered
    with database.get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name, stock_qty FROM products WHERE id = ?", (initial_nuggets["id"],))
        updated_row = cursor.fetchone()
        updated_stock = updated_row["stock_qty"]
        print(f"Post-order stock for {updated_row['name']}: {updated_stock}")
        assert updated_stock == initial_stock - 2, f"Expected {initial_stock - 2}, got {updated_stock}"

    # Check orders table
    orders = database.get_orders()
    assert len(orders) >= 1, "Order should be stored in orders table"
    latest = orders[0]
    print(f"\nStored Order in DB: Order #{latest['id']} | Total: Rs. {latest['total_pkr']:,} | Address: {latest['delivery_address']}")

    print("\n[SUCCESS] All E2E WhatsApp Agent flow tests passed successfully!")

if __name__ == "__main__":
    run_e2e_test()
