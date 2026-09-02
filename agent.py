import os
import json
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
import database

load_dotenv()

SYSTEM_INSTRUCTION = """
You are 'Hutty', the helpful and friendly WhatsApp sales assistant for 'FC-Hut' (Frozen Chicken Hut), 
a premium frozen chicken fried food business based in Pakistan.

Your Core Rules:
1. CURRENCY: All prices are strictly in Pakistani Rupees (PKR / Rs.).
2. STOCK & INVENTORY INTEGRITY:
   - NEVER make up or hallucinate stock quantities or prices.
   - Use the `check_stock` or `get_menu` tools to verify availability before answering questions about products.
   - If an item is out of stock or low in stock, politely inform the customer and suggest available alternatives.
3. ORDER PLACEMENT FLOW:
   - When a customer wants to buy items, check availability first.
   - Before placing the order, you MUST collect:
     a) Exact items and quantities
     b) Customer name (or nickname)
     c) Complete delivery address
   - Once all details are known, provide a clear order summary with line items, quantities, subtotal, and delivery address.
   - Ask for confirmation ("Should I confirm this order for you?").
   - Once the customer says yes/confirms, call `place_order`.
   - Never call `place_order` until the customer explicitly agrees to the summary and you have their delivery address.
4. TONE & STYLE:
   - Warm, welcoming, respectful, and concise (ideal for WhatsApp chats).
   - Reply in the language the customer speaks (English or Roman Urdu).
"""

# Tool functions exposed to the AI model
def get_available_menu() -> str:
    """Returns the current menu of all frozen chicken items with pack sizes, prices in PKR, and stock."""
    menu = database.get_menu()
    lines = ["📋 *FC-HUT MENU & LIVE STOCK:*"]
    for item in menu:
        status = f"✅ In Stock ({item['stock_qty']} packs)" if item['stock_qty'] > 0 else "❌ Out of Stock"
        lines.append(f"• *{item['name']}* ({item['pack_size']}) - Rs. {item['price_pkr']:,} [{status}]")
    return "\n".join(lines)

def check_item_stock(query: str = "") -> str:
    """Checks inventory count and price for specific items or categories (e.g. 'nuggets', 'wings', 'tenders')."""
    items = database.check_stock(query)
    if not items:
        return f"No items found matching '{query}'. Try asking for nuggets, wings, tenders, kababs, or fillets."
    lines = [f"🔍 *Stock check for '{query}':*"]
    for item in items:
        status = f"✅ {item['stock_qty']} packs available" if item['stock_qty'] > 0 else "❌ Sold out"
        lines.append(f"• *{item['name']}* - Rs. {item['price_pkr']:,} ({status})")
    return "\n".join(lines)

def execute_order(
    customer_phone: str,
    customer_name: str,
    delivery_address: str,
    items: List[Dict[str, Any]]
) -> str:
    """
    Places an order atomically and deducts inventory.
    Each item must have 'product_id' (int) or 'name' (str), and 'quantity' (int).
    """
    result = database.place_order_atomic(
        customer_phone=customer_phone,
        customer_name=customer_name,
        delivery_address=delivery_address,
        items=items
    )
    if not result.get("success"):
        return f"❌ Order failed: {result.get('error')}"
    
    order_id = result["order_id"]
    total = result["total_pkr"]
    lines = [
        f"🎉 *ORDER CONFIRMED! (Order #{order_id})*",
        f"👤 Customer: {result['customer_name']}",
        f"📍 Address: {result['delivery_address']}",
        "📦 *Items:*",
    ]
    for item in result["items"]:
        lines.append(f"  • {item['quantity']}x {item['name']} ({item['pack_size']}) = Rs. {item['subtotal_pkr']:,}")
    lines.append(f"\n💰 *Total Amount: Rs. {total:,} (Cash on Delivery)*")
    lines.append("🛵 Your frozen chicken items will be dispatched shortly in insulated cold bags. Thank you for choosing FC-Hut! 🍗")
    return "\n".join(lines)

class FCHutAgent:
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY", "").strip()
        self.use_gemini = bool(self.api_key and self.api_key != "your_gemini_api_key_here")
        self.model = None

        if self.use_gemini:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                
                # Register tools
                tools = [
                    get_available_menu,
                    check_item_stock,
                    execute_order
                ]
                
                self.model = genai.GenerativeModel(
                    model_name="gemini-1.5-flash",
                    system_instruction=SYSTEM_INSTRUCTION,
                    tools=tools
                )
            except Exception as e:
                print(f"[Agent Warning] Failed to initialize Gemini model: {e}. Running in standalone mode.")
                self.use_gemini = False

    def handle_message(self, customer_phone: str, user_message: str) -> str:
        """Processes an incoming customer message and generates an agent response."""
        # Retrieve previous chat history
        history = database.get_chat_history(customer_phone)
        
        if self.use_gemini and self.model:
            response_text = self._handle_with_gemini(customer_phone, user_message, history)
        else:
            response_text = self._handle_standalone(customer_phone, user_message, history)
            
        # Update and save chat history
        history.append({"role": "user", "parts": [user_message]})
        history.append({"role": "model", "parts": [response_text]})
        database.save_chat_history(customer_phone, history)
        
        return response_text

    def _handle_with_gemini(self, customer_phone: str, user_message: str, history: List[Dict[str, Any]]) -> str:
        """Handles chat using Gemini's native multi-turn chat and function calling."""
        import google.generativeai as genai
        
        try:
            # Reconstruct chat session with tool handling
            # Inject phone context into user message so tool can access it
            chat = self.model.start_chat(enable_automatic_function_calling=True)
            
            # Replay history
            context_prompt = f"[Customer Phone: {customer_phone}]\nCustomer message: {user_message}"
            response = chat.send_message(context_prompt)
            return response.text
        except Exception as e:
            print(f"[Gemini Error]: {e}, falling back to standalone handler.")
            return self._handle_standalone(customer_phone, user_message, history)

    def _handle_standalone(self, customer_phone: str, user_message: str, history: List[Dict[str, Any]]) -> str:
        """
        Standalone rule-based assistant when Gemini API key is not yet configured.
        Allows instant testing of menu, stock checking, and ordering.
        """
        msg = user_message.lower().strip()
        
        # 1. Greetings
        if any(w in msg for w in ["hi", "hello", "hey", "salam", "assalam"]):
            return (
                "👋 Salam & welcome to *FC-Hut (Frozen Chicken Hut)*! 🍗\n"
                "We provide premium frozen fried chicken items (Nuggets, Wings, Tenders, Patties, Kababs).\n\n"
                "How can I help you today?\n"
                "• Type *'menu'* to see all items & prices\n"
                "• Type *'stock nuggets'* to check availability\n"
                "• Or tell me what you'd like to order!"
            )
            
        # 2. Menu inquiry
        if any(w in msg for w in ["menu", "list", "items", "kya hai", "rate", "price"]):
            return get_available_menu()
            
        # 3. Stock inquiry
        if any(w in msg for w in ["stock", "available", "have", "hai", "hoga"]):
            # Extract possible product keywords
            keywords = ["nugget", "wing", "tender", "fillet", "ball", "popcorn", "kabab", "samosa"]
            matched = [k for k in keywords if k in msg]
            query = matched[0] if matched else ""
            return check_item_stock(query)

        # 4. Ordering / confirmation
        # Check if customer provides address or order
        all_prods = database.get_menu()
        ordered_items = []
        for prod in all_prods:
            short_name = prod["name"].lower().split()[1] if len(prod["name"].split()) > 1 else prod["name"].lower()
            if short_name in msg:
                # Find quantity
                import re
                qty_match = re.search(r'(\d+)\s*(?:pack|box|kg|piece|x)?\s*' + re.escape(short_name), msg)
                qty = int(qty_match.group(1)) if qty_match else 1
                ordered_items.append({"product_id": prod["id"], "quantity": qty})

        if ordered_items:
            # Check if address is mentioned
            if any(w in msg for w in ["street", "house", "sector", "road", "f-", "g-", "i-", "lahore", "islamabad", "karachi", "block"]):
                # Customer included address! Place order directly
                return execute_order(
                    customer_phone=customer_phone,
                    customer_name="Customer",
                    delivery_address=user_message,
                    items=ordered_items
                )
            else:
                # Ask for address
                lines = ["📝 *Order Details Recorded:*"]
                total = 0
                for item in ordered_items:
                    p = next(p for p in all_prods if p["id"] == item["product_id"])
                    sub = p["price_pkr"] * item["quantity"]
                    total += sub
                    lines.append(f"• {item['quantity']}x {p['name']} = Rs. {sub:,}")
                lines.append(f"\n💰 *Subtotal: Rs. {total:,}*")
                lines.append("\n📍 *Please reply with your Delivery Address* to confirm and dispatch your order!")
                return "\n".join(lines)

        return (
            "🍗 *FC-Hut Assistant:*\n"
            "I can help you check stock and place orders for frozen chicken items.\n"
            "• Ask me: *'What are the prices of nuggets?'*\n"
            "• Or say: *'I want 2 packs of Crispy Tenders to House 5, Street 2, Islamabad'*"
        )
