import sys
import database
from agent import FCHutAgent

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

def print_stock_summary():
    menu = database.get_menu()
    print("\n" + "="*60)
    print("🍗 CURRENT FC-HUT INVENTORY (LIVE DATABASE):")
    print("="*60)
    for p in menu:
        status = f"{p['stock_qty']} packs" if p['stock_qty'] > 0 else "OUT OF STOCK"
        print(f" • [ID {p['id']:2d}] {p['name']:<35} | Rs. {p['price_pkr']:>5,}/pack | Stock: {status}")
    print("="*60 + "\n")

def run_simulator():
    database.init_db()
    database.seed_products()
    agent = FCHutAgent()
    customer_phone = "+923001234567"
    
    print("\n" + "#"*60)
    print("  FC-HUT WHATSAPP AI AGENT SIMULATOR (PKR)")
    print("  Engine: " + ("Gemini Flash (API Connected)" if agent.use_gemini else "Standalone Smart Fallback (No Key Needed)"))
    print("#"*60)
    print("Commands:")
    print(" • Type any message as a customer (e.g. 'hi', 'show menu', 'do you have nuggets?')")
    print(" • Type '/stock' to view the live database inventory")
    print(" • Type '/orders' to view all orders placed so far")
    print(" • Type '/reset' to re-seed initial random stock")
    print(" • Type 'exit' or 'quit' to quit")
    print("-"*60)
    
    print_stock_summary()
    
    while True:
        try:
            user_input = input("\n📱 Customer (+923001234567): ").strip()
            if not user_input:
                continue
                
            if user_input.lower() in ["exit", "quit", "q"]:
                print("Exiting simulator. Bye!")
                break
                
            if user_input.lower() == "/stock":
                print_stock_summary()
                continue
                
            if user_input.lower() == "/orders":
                orders = database.get_orders()
                print(f"\n📦 Total Orders Placed: {len(orders)}")
                for o in orders:
                    print(f"  • Order #{o['id']} | {o['customer_name']} ({o['customer_phone']}) | Total: Rs. {o['total_pkr']:,} | Status: {o['status']}")
                    print(f"    Address: {o['delivery_address']}")
                    for it in o['items']:
                        print(f"      - {it['quantity']}x {it['name']} = Rs. {it['subtotal_pkr']:,}")
                continue

            if user_input.lower() == "/reset":
                database.seed_products(force=True)
                print("Inventory re-seeded with fresh random stock!")
                print_stock_summary()
                continue
            
            # Send message to AI Agent
            print("\n🤖 FC-Hut Agent is typing...")
            reply = agent.handle_message(customer_phone, user_input)
            print("-" * 50)
            print(reply)
            print("-" * 50)
            
        except (KeyboardInterrupt, EOFError):
            print("\nExiting simulator.")
            break

if __name__ == "__main__":
    run_simulator()
