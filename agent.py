import os
import re
import json
from typing import List, Dict, Any, Optional, Tuple
from dotenv import load_dotenv
import database

load_dotenv()

# Word-to-number mapping for natural language quantity parsing (English & Roman Urdu)
NUMBER_WORDS = {
    # English
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "twenty": 20,
    # Roman Urdu
    "ek": 1, "aik": 1, "yak": 1,
    "do": 2,
    "teen": 3, "tin": 3,
    "char": 4, "chaar": 4,
    "panch": 5, "paanch": 5,
    "che": 6, "chay": 6, "chey": 6,
    "saat": 7, "sat": 7,
    "aath": 8, "ath": 8,
    "nau": 9, "nao": 9,
    "das": 10, "dus": 10
}

def extract_quantity(text: str) -> Optional[int]:
    """Extracts packet quantity from natural language reply (English or Roman Urdu)."""
    text_lower = text.lower().strip()
    
    # 1. Search for numeric digits (e.g. "5", "3 packets", "2pk")
    digit_match = re.search(r'\b(\d+)\b', text_lower)
    if digit_match:
        qty = int(digit_match.group(1))
        if qty > 0:
            return qty
            
    # 2. Search for Roman Urdu & English word numbers
    words = re.findall(r'[a-zA-Z]+', text_lower)
    for w in words:
        if w in NUMBER_WORDS:
            return NUMBER_WORDS[w]
            
    return None

def extract_contact_info(text: str, fallback_phone: str = "") -> Tuple[str, str]:
    """Extracts phone number and delivery address from customer's reply."""
    # Look for Pakistan mobile number patterns (03xx-xxxxxxx, +923xxxxxxxxx, 03xxxxxxxxx)
    phone_pattern = r'(?:(?:\+?92|0092|0)?\s*3\d{2}[-\s]?\d{7})'
    phone_match = re.search(phone_pattern, text)
    
    if phone_match:
        phone = phone_match.group(0).strip()
        # Remove phone from text to isolate address
        address = text.replace(phone_match.group(0), "").strip()
        # Clean up any leftover punctuation or labels
        address = re.sub(r'^(?:address|add|addr|phone|ph|cell|mobile|number|no|:|-)+\s*', '', address, flags=re.IGNORECASE).strip()
        return phone, address if address else "Address provided in message"
    else:
        # Fallback to customer's WhatsApp phone if not explicitly typed
        phone = fallback_phone
        address = text.strip()
        return phone, address

def build_menu_list_response(current_cart: List[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Builds WhatsApp Native List message displaying in-stock items with packet-based pricing."""
    if current_cart is None:
        current_cart = []
        
    cart_counts = {item["prod_id"]: item["qty"] for item in current_cart}
    
    # Only show items with stock > 0
    menu = database.get_menu(only_in_stock=True)
    rows = []
    text_lines = [
        "👋 *Salam & welcome to FC-Hut!* 🍗",
        "Here is our fresh frozen chicken menu. All items are in packets:",
        ""
    ]
    
    row_idx = 1
    for p in menu:
        remaining_stock = p["stock_qty"] - cart_counts.get(p["id"], 0)
        if remaining_stock <= 0:
            continue  # Skip items already depleted by current cart
            
        desc = f"Rs. {p['price_pkr']:,} per packet ({p['pack_size']})"
        text_lines.append(f"• *{p['name']}* - {desc}")
        
        rows.append({
            "id": f"prod_{p['id']}",
            "title": p["name"][:24],
            "description": f"Rs. {p['price_pkr']:,}/pkt | {p['pack_size']}"[:72]
        })
        row_idx += 1

    text_lines.append("\n👉 *Please select an item you would like to order:*")
    fallback_text = "\n".join(text_lines)
    
    return {
        "type": "interactive_list",
        "text": fallback_text,
        "list_data": {
            "header": "FC-Hut Menu & Live Stock",
            "body": "👋 Salam & welcome to *FC-Hut*! 🍗\nChoose an item below to order:",
            "footer": "Cash on Delivery | PKR",
            "button_label": "🍗 View Available Menu",
            "sections": [
                {
                    "title": "Frozen Chicken Items (Packets)",
                    "rows": rows
                }
            ]
        }
    }

class FCHutAgent:
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY", "").strip()
        self.use_gemini = bool(self.api_key and self.api_key != "your_gemini_api_key_here")

    def process_input(
        self,
        customer_phone: str,
        user_text: str = "",
        interactive_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Handles state-machine transitions according to the defined business rules:
        1. Select 1 item from in-stock menu.
        2. Ask quantity (open natural language, no buttons).
        3. Check stock:
           - If short: inform available packets, buttons [Yes, confirm X packets] [No, leave this product]
           - If enough: add to cart.
        4. Ask 'Do you want to order something else?' with buttons [Yes] [No].
        5. If No: Ask address & phone.
        6. Order summary with buttons [Yes, I confirm] [No, cancel].
        7. If Confirm: Announce delivery between 6-7 PM.
        """
        user_text = (user_text or "").strip()
        interactive_id = (interactive_id or "").strip()
        
        session = database.get_session(customer_phone)
        state = session.get("state", "IDLE")
        data = session.get("data", {})
        cart = data.get("cart", [])

        # -------------------------------------------------------------
        # GLOBAL RESET
        # -------------------------------------------------------------
        if user_text.lower() in ["/reset", "start over"]:
            database.clear_session(customer_phone)
            return build_menu_list_response()

        # -------------------------------------------------------------
        # 1. STATE: IDLE (Greeting / Start / Item Selection)
        # -------------------------------------------------------------
        if state == "IDLE":
            # Check if customer tapped an item from the menu list
            if interactive_id.startswith("prod_"):
                return self._handle_item_selected(customer_phone, data, interactive_id)

            # Check if customer typed a product name or alias directly (e.g. "samosas", "nuggets")
            matched_prod = database.match_product_by_text(user_text)
            if matched_prod and matched_prod["stock_qty"] > 0:
                data["selected_prod_id"] = matched_prod["id"]
                data["cart"] = cart
                database.set_session(customer_phone, "AWAITING_QTY", data)
                
                # Check if they also provided a quantity in the same message (e.g. "2 packets nuggets")
                qty = extract_quantity(user_text)
                if qty:
                    return self._process_quantity_input(customer_phone, data, matched_prod, qty)
                    
                return {
                    "type": "text",
                    "text": (
                        f"🍗 You selected *{matched_prod['name']}* - Rs. {matched_prod['price_pkr']:,} per packet ({matched_prod['pack_size']}).\n\n"
                        f"How many packets would you like to order? / Aap ko kitnay packets chahiyen?"
                    )
                }

            # Otherwise, show initial in-stock menu
            return build_menu_list_response(cart)

        # -------------------------------------------------------------
        # 2. STATE: AWAITING_QTY (Open Natural Language Quantity Input)
        # -------------------------------------------------------------
        if state == "AWAITING_QTY":
            prod_id = data.get("selected_prod_id")
            prod = database.get_product_by_id(prod_id)
            if not prod:
                database.clear_session(customer_phone)
                return build_menu_list_response()

            qty = extract_quantity(user_text)
            if not qty:
                return {
                    "type": "text",
                    "text": f"Please let us know how many packets of *{prod['name']}* you need (e.g., reply with 2, 3, or 'panch packet'):"
                }

            return self._process_quantity_input(customer_phone, data, prod, qty)

        # -------------------------------------------------------------
        # 3. STATE: AWAITING_PARTIAL_DECISION (Stock Shortage Branch)
        # -------------------------------------------------------------
        if state == "AWAITING_PARTIAL_DECISION":
            prod_id = data.get("selected_prod_id")
            prod = database.get_product_by_id(prod_id)
            avail = data.get("partial_offered_qty", 0)

            # Option A: Customer confirms available packets
            if interactive_id == "partial_confirm" or any(w in user_text.lower() for w in ["yes", "confirm", "theek", "haan", "le lo", "ok"]):
                if prod and avail > 0:
                    cart.append({
                        "prod_id": prod["id"],
                        "name": prod["name"],
                        "pack_size": prod["pack_size"],
                        "qty": avail,
                        "price_pkr": prod["price_pkr"],
                        "subtotal_pkr": prod["price_pkr"] * avail
                    })
                    data["cart"] = cart
                return self._ask_order_something_else(customer_phone, data, prod, avail)

            # Option B: Customer leaves this product
            elif interactive_id == "partial_leave" or any(w in user_text.lower() for w in ["no", "leave", "choro", "rehn do", "nahi"]):
                data["cart"] = cart
                if cart:
                    # Cart already has other items, ask if they want something else
                    return self._ask_order_something_else(customer_phone, data, None, 0)
                else:
                    # Cart empty, show menu again
                    database.set_session(customer_phone, "IDLE", {"cart": []})
                    resp = build_menu_list_response()
                    resp["text"] = "Item discarded. Please select another available item from the menu:\n\n" + resp["text"]
                    return resp
            else:
                return {
                    "type": "interactive_buttons",
                    "text": f"Please tap one of the buttons below to confirm or leave {prod['name']}:",
                    "buttons_data": {
                        "body": f"Currently only {avail} packets of {prod['name']} are available. Do you want these {avail} packets?",
                        "buttons": [
                            {"id": "partial_confirm", "title": f"Yes, confirm {avail} pkts"[:20]},
                            {"id": "partial_leave", "title": "No, leave product"}
                        ]
                    }
                }

        # -------------------------------------------------------------
        # 4. STATE: AWAITING_ADD_MORE ("Do you want to order something else?")
        # -------------------------------------------------------------
        if state == "AWAITING_ADD_MORE":
            if interactive_id == "more_yes" or any(w in user_text.lower() for w in ["yes", "haan", "aur", "more", "ji"]):
                # Customer wants to add more items -> show available menu
                database.set_session(customer_phone, "IDLE", data)
                return build_menu_list_response(cart)

            elif interactive_id == "more_no" or any(w in user_text.lower() for w in ["no", "nahi", "bas", "done", "complete", "bus"]):
                # Customer is done selecting items -> Ask address & phone
                database.set_session(customer_phone, "AWAITING_CONTACT", data)
                return {
                    "type": "text",
                    "text": (
                        "📍 *Delivery Details:*\n"
                        "Please provide your complete **Delivery Address** and **Contact Phone Number** to proceed with your order:"
                    )
                }
            else:
                return {
                    "type": "interactive_buttons",
                    "text": "Do you want to order something else? Please choose Yes or No:",
                    "buttons_data": {
                        "body": "Do you want to order something else? / Kya aap kuch aur order karna chahtay hain?",
                        "buttons": [
                            {"id": "more_yes", "title": "Yes"},
                            {"id": "more_no", "title": "No"}
                        ]
                    }
                }

        # -------------------------------------------------------------
        # 5. STATE: AWAITING_CONTACT (Multi-text Address & Phone Extraction)
        # -------------------------------------------------------------
        if state == "AWAITING_CONTACT":
            phone_pattern = r'(?:(?:\+?92|0092|0)?\s*3\d{2}[-\s]?\d{7})|(?:0\d{2,3}[-\s]?\d{7,8})'
            phone_match = re.search(phone_pattern, user_text)

            # Check if customer indicates using their current WhatsApp number
            if any(w in user_text.lower() for w in ["same number", "same", "yehi number", "isi number", "this number", "apna number"]):
                data["delivery_phone"] = customer_phone
                # Check if there's also address in the message
                clean_text = re.sub(r'\b(?:same number|same|yehi number|isi number|this number)\b', '', user_text, flags=re.IGNORECASE).strip()
                if len(clean_text) >= 4:
                    data["delivery_address"] = clean_text

            elif phone_match:
                # Phone number found in this message
                found_phone = phone_match.group(0).strip()
                data["delivery_phone"] = found_phone
                
                # Check if there is leftover text that serves as address
                leftover = user_text.replace(phone_match.group(0), "").strip()
                leftover = re.sub(r'^(?:address|add|addr|phone|ph|cell|mobile|number|no|:|-)+\s*', '', leftover, flags=re.IGNORECASE).strip()
                if len(leftover) >= 4:
                    data["delivery_address"] = leftover

            else:
                # No phone number in this text -> Treat as delivery address
                if len(user_text) >= 4:
                    data["delivery_address"] = user_text.strip()

            has_address = bool(data.get("delivery_address"))
            has_phone = bool(data.get("delivery_phone"))

            # Case A: Both address and phone are collected!
            if has_address and has_phone:
                database.set_session(customer_phone, "AWAITING_ORDER_CONFIRM", data)
                return self._build_order_summary_response(
                    cart,
                    data["delivery_address"],
                    data["delivery_phone"]
                )

            # Case B: Address provided, but phone is still missing
            elif has_address and not has_phone:
                database.set_session(customer_phone, "AWAITING_CONTACT", data)
                return {
                    "type": "text",
                    "text": (
                        f"📍 Address noted: *{data['delivery_address']}*\n\n"
                        f"📞 Now please provide your **Contact Phone Number** (or reply 'same number'):"
                    )
                }

            # Case C: Phone provided, but address is still missing
            elif has_phone and not has_address:
                database.set_session(customer_phone, "AWAITING_CONTACT", data)
                return {
                    "type": "text",
                    "text": (
                        f"📞 Phone number noted: *{data['delivery_phone']}*\n\n"
                        f"📍 Now please provide your complete **Delivery Address** (House #, Street, Area/City):"
                    )
                }

            else:
                return {
                    "type": "text",
                    "text": "📍 Please provide your Delivery Address and Contact Phone Number to finalize your order:"
                }

        # -------------------------------------------------------------
        # 6. STATE: AWAITING_ORDER_CONFIRM (Final Confirmation)
        # -------------------------------------------------------------
        if state == "AWAITING_ORDER_CONFIRM":
            if interactive_id == "final_confirm" or any(w in user_text.lower() for w in ["yes", "confirm", "haan", "ok", "done", "theek"]):
                return self._finalize_order(customer_phone, data)

            elif interactive_id == "final_cancel" or any(w in user_text.lower() for w in ["no", "cancel", "nahi", "rehn do", "abort"]):
                database.clear_session(customer_phone)
                return {
                    "type": "text",
                    "text": "No problem at all! Whenever you crave fresh frozen chicken items, FC-Hut is here for you. Have a wonderful day! 😊🍗"
                }
            else:
                return self._build_order_summary_response(cart, data.get("delivery_address", ""), data.get("delivery_phone", customer_phone))

        # Default fallback
        return build_menu_list_response(cart)

    # -------------------------------------------------------------
    # HELPER LOGIC METHODS
    # -------------------------------------------------------------
    def _handle_item_selected(self, customer_phone: str, data: Dict[str, Any], interactive_id: str) -> Dict[str, Any]:
        try:
            prod_id = int(interactive_id.replace("prod_", ""))
            prod = database.get_product_by_id(prod_id)
            if not prod:
                return {"type": "text", "text": "❌ Product not found in menu."}
                
            # Check remaining stock considering current cart
            cart = data.get("cart", [])
            in_cart = sum(it["qty"] for it in cart if it["prod_id"] == prod["id"])
            remaining = prod["stock_qty"] - in_cart
            
            if remaining <= 0:
                resp = build_menu_list_response(cart)
                resp["text"] = f"❌ *{prod['name']}* is currently sold out! Please select another item:\n\n" + resp["text"]
                return resp

            data["selected_prod_id"] = prod["id"]
            data["cart"] = cart
            database.set_session(customer_phone, "AWAITING_QTY", data)
            
            return {
                "type": "text",
                "text": (
                    f"🍗 You selected *{prod['name']}* - Rs. {prod['price_pkr']:,} per packet ({prod['pack_size']}).\n\n"
                    f"How many packets would you like to order? / Aap ko kitnay packets chahiyen?"
                )
            }
        except Exception as e:
            return {"type": "text", "text": f"Error selecting item: {e}"}

    def _process_quantity_input(self, customer_phone: str, data: Dict[str, Any], prod: Dict[str, Any], qty: int) -> Dict[str, Any]:
        cart = data.get("cart", [])
        in_cart = sum(it["qty"] for it in cart if it["prod_id"] == prod["id"])
        available = prod["stock_qty"] - in_cart

        if qty > available:
            # Shortage branch: Offer exact available packets
            data["partial_offered_qty"] = available
            database.set_session(customer_phone, "AWAITING_PARTIAL_DECISION", data)
            
            body_msg = (
                f"⚠️ Currently only *{available} packet(s)* of *{prod['name']}* are available right now in stock.\n\n"
                f"Would you like to confirm these {available} packet(s), or leave this product?"
            )
            return {
                "type": "interactive_buttons",
                "text": body_msg,
                "buttons_data": {
                    "body": body_msg,
                    "buttons": [
                        {"id": "partial_confirm", "title": f"Yes, confirm {available} pkts"[:20]},
                        {"id": "partial_leave", "title": "No, leave product"}
                    ]
                }
            }
        else:
            # Stock is sufficient: Add to cart
            cart.append({
                "prod_id": prod["id"],
                "name": prod["name"],
                "pack_size": prod["pack_size"],
                "qty": qty,
                "price_pkr": prod["price_pkr"],
                "subtotal_pkr": prod["price_pkr"] * qty
            })
            data["cart"] = cart
            return self._ask_order_something_else(customer_phone, data, prod, qty)

    def _ask_order_something_else(self, customer_phone: str, data: Dict[str, Any], prod: Optional[Dict[str, Any]], qty: int) -> Dict[str, Any]:
        database.set_session(customer_phone, "AWAITING_ADD_MORE", data)
        
        prefix = ""
        if prod and qty > 0:
            prefix = f"✅ Added *{qty} packet(s)* of *{prod['name']}* to your order.\n\n"
            
        body_text = prefix + "Do you want to order something else? / Kya aap kuch aur order karna chahtay hain?"
        return {
            "type": "interactive_buttons",
            "text": body_text + "\n(Tap Yes or No below):",
            "buttons_data": {
                "body": body_text,
                "buttons": [
                    {"id": "more_yes", "title": "Yes"},
                    {"id": "more_no", "title": "No"}
                ]
            }
        }

    def _build_order_summary_response(self, cart: List[Dict[str, Any]], address: str, phone: str) -> Dict[str, Any]:
        lines = ["📋 *ORDER SUMMARY:*"]
        total_pkr = 0
        for item in cart:
            lines.append(f"• {item['qty']}x {item['name']} ({item['pack_size']}) = Rs. {item['subtotal_pkr']:,}")
            total_pkr += item["subtotal_pkr"]
            
        lines.append(f"\n💰 *Total Amount: Rs. {total_pkr:,} (Cash on Delivery)*")
        lines.append(f"📍 *Delivery Address:* {address}")
        lines.append(f"📞 *Contact Number:* {phone}")
        lines.append("\nShould I confirm this order?")

        body_text = "\n".join(lines)
        return {
            "type": "interactive_buttons",
            "text": body_text,
            "buttons_data": {
                "body": body_text,
                "buttons": [
                    {"id": "final_confirm", "title": "Yes, I confirm"},
                    {"id": "final_cancel", "title": "No, cancel"}
                ]
            }
        }

    def _finalize_order(self, customer_phone: str, data: Dict[str, Any]) -> Dict[str, Any]:
        cart = data.get("cart", [])
        address = data.get("delivery_address", "")
        contact_phone = data.get("delivery_phone", customer_phone)
        
        if not cart:
            database.clear_session(customer_phone)
            return {"type": "text", "text": "Your cart was empty. Please choose an item from the menu."}

        order_items = [{"product_id": item["prod_id"], "quantity": item["qty"]} for item in cart]
        
        # Atomic deduction in database
        result = database.place_order_atomic(
            customer_phone=contact_phone,
            customer_name="Customer",
            delivery_address=address,
            items=order_items
        )
        
        # Clear session
        database.clear_session(customer_phone)
        
        if not result.get("success"):
            return {
                "type": "text",
                "text": f"❌ Could not confirm order: {result.get('error')}\nPlease start again by saying 'Hi'."
            }

        order_id = result["order_id"]
        total = result["total_pkr"]
        
        confirmation_msg = (
            f"🎉 *Your order has been confirmed! (Order #{order_id})*\n\n"
            f"💰 Total Amount: Rs. {total:,} (Cash on Delivery)\n"
            f"📍 Delivery Address: {address}\n"
            f"📞 Contact Number: {contact_phone}\n\n"
            f"🛵 *Your order will be delivered today in between 6-7 PM.* Thank you for choosing FC-Hut! 🍗"
        )
        return {"type": "text", "text": confirmation_msg}

    def handle_message(self, customer_phone: str, user_message: str) -> str:
        resp = self.process_input(customer_phone, user_text=user_message)
        return resp.get("text", "")
