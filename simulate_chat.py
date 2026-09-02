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
    print("\n" + "="*65)
    print("🍗 CURRENT FC-HUT INVENTORY (LIVE DATABASE):")
    print("="*65)
    for p in menu:
        status = f"{p['stock_qty']} packs" if p['stock_qty'] > 0 else "OUT OF STOCK"
        print(f" • [ID {p['id']:2d}] {p['name']:<35} | Rs. {p['price_pkr']:>5,}/pack | Stock: {status}")
    print("="*65 + "\n")

def run_simulator():
    database.init_db()
    database.seed_products()
    agent = FCHutAgent()
    customer_phone = "+923001234567"
    
    print("\n" + "#"*65)
    print("  🍗 FC-HUT WHATSAPP NATIVE BUTTONS & LIST SIMULATOR (PKR)")
    print("  Simulating: WhatsApp Cloud API Interactive UI (Mobile UX)")
    print("#"*65)
    print("Controls:")
    print(" • Type button letter [A], [B] or number [1-10] to simulate screen taps")
    print(" • Or type freely (e.g. 'samosiyan', 'cancel', delivery addresses)")
    print(" • Type '/stock' to view live inventory")
    print(" • Type '/orders' to view all placed orders in database")
    print(" • Type '/reset' to re-seed stock")
    print(" • Type 'exit' to quit")
    print("-"*65)

    print_stock_summary()

    # Active choices mapping for current step
    active_choices = {}

    # Start with initial menu list
    initial_resp = agent.process_input(customer_phone, user_text="hi")
    active_choices = display_agent_response(initial_resp)

    while True:
        try:
            prompt = "\n📱 Customer (+923001234567): "
            user_input = input(prompt).strip()
            if not user_input:
                continue
                
            if user_input.lower() in ["exit", "quit", "q"]:
                print("Exiting simulator. Goodbye!")
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
                database.clear_session(customer_phone)
                print("Inventory re-seeded with fresh random stock and session cleared!")
                print_stock_summary()
                resp = agent.process_input(customer_phone, user_text="hi")
                active_choices = display_agent_response(resp)
                continue

            # Check if input matches an active interactive button/list choice
            key = user_input.upper()
            interactive_id = None
            text_val = None

            if key in active_choices:
                interactive_id = active_choices[key]
                print(f"👆 [Simulated Tap]: Selected {key} -> (ID: {interactive_id})")
            elif user_input in active_choices:
                interactive_id = active_choices[user_input]
                print(f"👆 [Simulated Tap]: Selected {user_input} -> (ID: {interactive_id})")
            else:
                text_val = user_input

            # Send to agent
            print("\n🤖 FC-Hut Agent is processing...")
            resp = agent.process_input(
                customer_phone,
                user_text=text_val or "",
                interactive_id=interactive_id
            )
            
            # Display formatted response and update active choices
            active_choices = display_agent_response(resp)
            
        except (KeyboardInterrupt, EOFError):
            print("\nExiting simulator.")
            break

def display_agent_response(resp: dict) -> dict:
    """Renders the agent's response and returns a dictionary of valid shortcuts."""
    msg_type = resp.get("type", "text")
    choices = {}
    
    print("\n" + "─"*55)
    
    if msg_type == "interactive_list" and "list_data" in resp:
        ld = resp["list_data"]
        print(f"📲 *{ld.get('header', 'FC-Hut')}*")
        print(ld.get("body", ""))
        print(f"\n🔘 Button: [{ld.get('button_label', 'View Menu')}]")
        print("┌" + "─"*53 + "┐")
        print("│ 📋 POPUP LIST MENU ON CUSTOMER PHONE:             │")
        print("├" + "─"*53 + "┤")
        
        row_idx = 1
        for section in ld.get("sections", []):
            for row in section.get("rows", []):
                print(f"│  [{row_idx:2d}] {row['title']:<24} | {row['description']:<20} │")
                choices[str(row_idx)] = row["id"]
                row_idx += 1
                
        print("└" + "─"*53 + "┘")
        print(f"💡 {ld.get('footer', '')}")
        print("👉 Tap any option (1-10) or type an item name like 'samosiyan':")

    elif msg_type == "interactive_buttons" and "buttons_data" in resp:
        bd = resp["buttons_data"]
        print(bd.get("body", ""))
        print("\n🔘 QUICK REPLY BUTTONS ON CUSTOMER PHONE:")
        letters = ["A", "B", "C"]
        for idx, btn in enumerate(bd.get("buttons", [])):
            letter = letters[idx] if idx < len(letters) else str(idx+1)
            print(f"   [{letter}] {btn['title']}")
            choices[letter] = btn["id"]
            # Also allow numeric shortcut
            choices[str(idx+1)] = btn["id"]
        print("👉 Tap button (A / B / C):")

    else:
        # Standard text message
        print(resp.get("text", ""))

    print("─"*55)
    return choices

if __name__ == "__main__":
    run_simulator()
