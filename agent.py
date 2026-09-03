import os
import re
import json
from typing import List, Dict, Any, Optional, Tuple
from dotenv import load_dotenv
import database

load_dotenv()

# Universal exit / main menu keywords recognized at ANY step
UNIVERSAL_EXIT_KEYWORDS = {
    "menu", "main menu", "exit", "cancel", "stop", "wapas",
    "restart", "shuru", "shuru se", "start over", "khatam",
    "batao menu", "back"
}

NAVIGATION_FOOTER = "\n\n💡 *Tip: Reply 'menu' anytime to return to Main Menu, or 'cancel' to exit.*"

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
    
    # Differentiate English auxiliary verb ("do you", "do u", "do we") from Roman Urdu number "do" (2)
    cleaned_text = re.sub(r'\bdo\s+(?:you|u|we|they|i)\b', 'inquiry', text_lower)

    # 1. Search for numeric digits (e.g. "5", "3 packets", "2pk")
    digit_match = re.search(r'\b(\d+)\b', cleaned_text)
    if digit_match:
        qty = int(digit_match.group(1))
        if qty > 0:
            return qty
            
    # 2. Search for Roman Urdu & English word numbers
    words = re.findall(r'[a-zA-Z]+', cleaned_text)
    for w in words:
        if w in NUMBER_WORDS:
            return NUMBER_WORDS[w]
            
    return None

def build_menu_list_response(
    current_cart: List[Dict[str, Any]] = None,
    greeting_prefix: str = ""
) -> Dict[str, Any]:
    """Builds WhatsApp Native List message displaying in-stock items with packet-based pricing."""
    if current_cart is None:
        current_cart = []
        
    cart_counts = {item["prod_id"]: item["qty"] for item in current_cart}
    
    # Only show items with stock > 0
    menu = database.get_menu(only_in_stock=True)
    rows = []
    
    if greeting_prefix:
        text_lines = [greeting_prefix]
    else:
        text_lines = [
            "👋 *Salam & welcome to FC-Hut!* 🍗",
            "Here is our fresh frozen chicken menu. All items are in packets:\n"
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
    text_lines.append(NAVIGATION_FOOTER.strip())
    fallback_text = "\n".join(text_lines)
    
    return {
        "type": "interactive_list",
        "text": fallback_text,
        "list_data": {
            "header": "FC-Hut Menu & Live Stock",
            "body": "👋 Salam & welcome to *FC-Hut*! 🍗\nChoose an item below to order:\n(Reply 'menu' anytime to return here)",
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
        self.model = None

        if self.use_gemini:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                self.model = genai.GenerativeModel("gemini-1.5-flash")
            except Exception as e:
                print(f"[Agent Warning] Failed to initialize Gemini model: {e}")
                self.use_gemini = False

    def _analyze_with_llm_brain(
        self,
        customer_message: str,
        session_state: str,
        current_prod_name: Optional[str],
        cart: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Cognitive Brain: Uses Gemini Flash to analyze the customer's message in context.
        Determines if they are continuing the flow, greeting anew after ghosting, switching products,
        asking a general question, or requesting exit/main menu.
        """
        if not self.use_gemini or not self.model:
            return self._heuristic_brain_fallback(customer_message, session_state, current_prod_name)

        prompt = f"""
You are the cognitive NLP brain for 'FC-Hut', a Pakistani frozen chicken food delivery bot on WhatsApp.
Current Session State: "{session_state}"
Active Product Being Ordered (if any): "{current_prod_name or 'None'}"
Items in Cart: {json.dumps(cart)}
Customer Message: "{customer_message}"

Analyze the customer's message in this exact context.
Categorize the intent into ONE of:
- "CANCEL_EXIT": Customer says menu, main menu, cancel, exit, stop, wapas, restart, shuru se.
- "NEW_START": Customer sends a greeting (hi, salam, hello, hey, aalam), or returns after ghosting asking a new general greeting.
- "TOPIC_SWITCH": Customer was ordering an active product, but explicitly asks about a DIFFERENT product (e.g. asking "are kababs available?" or "show me wings").
- "ANSWER_STEP": Customer is answering the question for the current step (giving quantity e.g. "3 packets" or "do packet", giving address/phone, or answering yes/no).
- "GENERAL_QUESTION": Customer asks about store location, delivery areas, cooking instructions.

Extract entities if present:
- "quantity": integer or null
- "product_query": string or null
- "decision": "yes" | "no" | "confirm" | "cancel" | null

Return ONLY valid JSON matching this schema:
{{
  "intent": "CANCEL_EXIT" | "NEW_START" | "TOPIC_SWITCH" | "ANSWER_STEP" | "GENERAL_QUESTION",
  "quantity": null,
  "product_query": null,
  "decision": null,
  "reasoning": "brief explanation"
}}
"""
        try:
            resp = self.model.generate_content(
                prompt,
                generation_config={"response_mime_type": "application/json"}
            )
            data = json.loads(resp.text)
            return data
        except Exception as e:
            print(f"[LLM Brain Warning]: {e}. Using heuristic brain.")
            return self._heuristic_brain_fallback(customer_message, session_state, current_prod_name)

    def _heuristic_brain_fallback(
        self,
        customer_message: str,
        session_state: str,
        current_prod_name: Optional[str]
    ) -> Dict[str, Any]:
        """Intelligent heuristic fallback when LLM API key is not active."""
        msg = customer_message.lower().strip()

        # 1. Universal exit / menu keywords
        if any(w == msg or f" {w} " in f" {msg} " for w in UNIVERSAL_EXIT_KEYWORDS):
            return {"intent": "CANCEL_EXIT", "quantity": None, "product_query": None, "decision": "cancel"}

        # 2. Greetings / New conversation trigger (use word boundaries to avoid matching 'hai' as 'hi')
        is_greeting = bool(re.search(r'\b(salam|assalam|hello|hi|hey|aalam)\b', msg))
        
        # 3. Product match check
        matched_prod = database.match_product_by_text(msg)
        
        # If in an active step (e.g. AWAITING_QTY), but customer asks about a different product
        if matched_prod and current_prod_name and matched_prod["name"] != current_prod_name:
            return {"intent": "TOPIC_SWITCH", "quantity": extract_quantity(msg), "product_query": matched_prod["name"], "decision": None}

        # If customer sends a pure greeting while in an active state (returning after ghosting)
        if is_greeting and not extract_quantity(msg) and len(msg.split()) <= 4:
            return {"intent": "NEW_START", "quantity": None, "product_query": None, "decision": None}

        # If customer sends a fresh product query from IDLE
        if session_state == "IDLE" and matched_prod:
            return {"intent": "TOPIC_SWITCH", "quantity": extract_quantity(msg), "product_query": matched_prod["name"], "decision": None}

        # Decision keywords
        decision = None
        if any(w in msg for w in ["yes", "haan", "confirm", "theek", "ok"]):
            decision = "yes"
        elif any(w in msg for w in ["no", "nahi", "cancel", "leave", "choro"]):
            decision = "no"

        return {
            "intent": "ANSWER_STEP",
            "quantity": extract_quantity(msg),
            "product_query": matched_prod["name"] if matched_prod else None,
            "decision": decision
        }

    def process_input(
        self,
        customer_phone: str,
        user_text: str = "",
        interactive_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Cognitive Brain Decision Loop:
        1. Checks for universal exit / return to main menu.
        2. Consults LLM Brain on intent and context switches.
        3. Routes to state handlers seamlessly.
        """
        user_text = (user_text or "").strip()
        interactive_id = (interactive_id or "").strip()
        
        session = database.get_session(customer_phone)
        state = session.get("state", "IDLE")
        data = session.get("data", {})
        cart = data.get("cart", [])
        active_prod_id = data.get("selected_prod_id")
        active_prod = database.get_product_by_id(active_prod_id) if active_prod_id else None
        active_prod_name = active_prod["name"] if active_prod else None

        # -------------------------------------------------------------
        # STEP A: UNIVERSAL EXIT & RETURN TO MAIN MENU CHECK
        # -------------------------------------------------------------
        clean_text = user_text.lower().strip()
        is_universal_exit = (
            interactive_id in ["final_cancel", "leave_product", "menu_exit"] or
            any(clean_text == kw or f" {kw} " in f" {clean_text} " for kw in UNIVERSAL_EXIT_KEYWORDS)
        )

        if is_universal_exit:
            database.clear_session(customer_phone)
            prefix = "🏠 *Returned to Main Menu.* What would you like to order today?\n\n"
            return build_menu_list_response(greeting_prefix=prefix)

        # -------------------------------------------------------------
        # STEP B: COGNITIVE BRAIN INTENT ANALYSIS
        # -------------------------------------------------------------
        # Consult brain if message is text (interactive clicks are deterministic)
        brain_analysis = {}
        if user_text:
            brain_analysis = self._analyze_with_llm_brain(user_text, state, active_prod_name, cart)
            intent = brain_analysis.get("intent", "ANSWER_STEP")

            # 1. CANCEL / EXIT DETECTED BY BRAIN
            if intent == "CANCEL_EXIT":
                database.clear_session(customer_phone)
                prefix = "🏠 *Returned to Main Menu.* What would you like to order today?\n\n"
                return build_menu_list_response(greeting_prefix=prefix)

            # 2. GHOSTING RETURN / NEW CONVERSATION DETECTED BY BRAIN
            # If customer was previously mid-flow, but returns with greeting or new conversation:
            if intent == "NEW_START" and state != "IDLE":
                print(f"[Brain Insight] Customer returning after ghosting/new start. Resetting state from {state} -> IDLE")
                database.clear_session(customer_phone)
                prefix = "👋 *Salam & welcome back to FC-Hut!* 🍗\nHere is our fresh frozen chicken menu. All items are in packets:\n\n"
                return build_menu_list_response(greeting_prefix=prefix)

            # 3. TOPIC SWITCH DETECTED BY BRAIN
            # If customer pivots to a different product while we were asking for quantity/details:
            if intent == "TOPIC_SWITCH":
                matched_prod = database.match_product_by_text(user_text)
                if matched_prod and matched_prod["stock_qty"] > 0:
                    print(f"[Brain Insight] Topic switch detected! Switching from {active_prod_name} -> {matched_prod['name']}")
                    data["selected_prod_id"] = matched_prod["id"]
                    data["cart"] = cart
                    database.set_session(customer_phone, "AWAITING_QTY", data)
                    
                    qty = brain_analysis.get("quantity") or extract_quantity(user_text)
                    if qty:
                        return self._process_quantity_input(customer_phone, data, matched_prod, qty)
                        
                    return {
                        "type": "text",
                        "text": (
                            f"🍗 Switched to *{matched_prod['name']}* - Rs. {matched_prod['price_pkr']:,} per packet ({matched_prod['pack_size']}).\n\n"
                            f"How many packets would you like to order? / Aap ko kitnay packets chahiyen?"
                            f"{NAVIGATION_FOOTER}"
                        )
                    }

        # -------------------------------------------------------------
        # STEP C: STATE MACHINE EXECUTION
        # -------------------------------------------------------------
        # 1. STATE: IDLE
        if state == "IDLE":
            if interactive_id.startswith("prod_"):
                return self._handle_item_selected(customer_phone, data, interactive_id)

            matched_prod = database.match_product_by_text(user_text)
            if matched_prod and matched_prod["stock_qty"] > 0:
                data["selected_prod_id"] = matched_prod["id"]
                data["cart"] = cart
                database.set_session(customer_phone, "AWAITING_QTY", data)
                
                qty = brain_analysis.get("quantity") or extract_quantity(user_text)
                if qty:
                    return self._process_quantity_input(customer_phone, data, matched_prod, qty)
                    
                return {
                    "type": "text",
                    "text": (
                        f"🍗 You selected *{matched_prod['name']}* - Rs. {matched_prod['price_pkr']:,} per packet ({matched_prod['pack_size']}).\n\n"
                        f"How many packets would you like to order? / Aap ko kitnay packets chahiyen?"
                        f"{NAVIGATION_FOOTER}"
                    )
                }

            return build_menu_list_response(cart)

        # 2. STATE: AWAITING_QTY
        if state == "AWAITING_QTY":
            prod_id = data.get("selected_prod_id")
            prod = database.get_product_by_id(prod_id)
            if not prod:
                database.clear_session(customer_phone)
                return build_menu_list_response()

            qty = brain_analysis.get("quantity") or extract_quantity(user_text)
            if not qty:
                return {
                    "type": "text",
                    "text": (
                        f"Please let us know how many packets of *{prod['name']}* you need (e.g., reply with 2, 3, or 'panch packet'):"
                        f"{NAVIGATION_FOOTER}"
                    )
                }

            return self._process_quantity_input(customer_phone, data, prod, qty)

        # 3. STATE: AWAITING_PARTIAL_DECISION
        if state == "AWAITING_PARTIAL_DECISION":
            prod_id = data.get("selected_prod_id")
            prod = database.get_product_by_id(prod_id)
            avail = data.get("partial_offered_qty", 0)

            decision = brain_analysis.get("decision")
            if interactive_id == "partial_confirm" or decision == "yes" or any(w in user_text.lower() for w in ["yes", "confirm", "theek", "haan", "le lo", "ok"]):
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

            elif interactive_id == "partial_leave" or decision == "no" or any(w in user_text.lower() for w in ["no", "leave", "choro", "rehn do", "nahi"]):
                data["cart"] = cart
                if cart:
                    return self._ask_order_something_else(customer_phone, data, None, 0)
                else:
                    database.set_session(customer_phone, "IDLE", {"cart": []})
                    prefix = "Item discarded. Please select another available item from the menu:\n\n"
                    return build_menu_list_response(greeting_prefix=prefix)
            else:
                return {
                    "type": "interactive_buttons",
                    "text": f"Please choose whether to take {avail} packet(s) of {prod['name']}:{NAVIGATION_FOOTER}",
                    "buttons_data": {
                        "body": f"Currently only {avail} packets of {prod['name']} are available. Do you want these {avail} packets?",
                        "buttons": [
                            {"id": "partial_confirm", "title": f"Yes, confirm {avail} pkts"[:20]},
                            {"id": "partial_leave", "title": "No, leave product"}
                        ]
                    }
                }

        # 4. STATE: AWAITING_ADD_MORE
        if state == "AWAITING_ADD_MORE":
            decision = brain_analysis.get("decision")
            if interactive_id == "more_yes" or decision == "yes" or any(w in user_text.lower() for w in ["yes", "haan", "aur", "more", "ji"]):
                database.set_session(customer_phone, "IDLE", data)
                return build_menu_list_response(cart)

            elif interactive_id == "more_no" or decision == "no" or any(w in user_text.lower() for w in ["no", "nahi", "bas", "done", "complete", "bus"]):
                database.set_session(customer_phone, "AWAITING_CONTACT", data)
                return {
                    "type": "text",
                    "text": (
                        "📍 *Delivery Details:*\n"
                        "Please provide your complete **Delivery Address** and **Contact Phone Number** to proceed with your order:"
                        f"{NAVIGATION_FOOTER}"
                    )
                }
            else:
                return {
                    "type": "interactive_buttons",
                    "text": f"Do you want to order something else? Please choose Yes or No:{NAVIGATION_FOOTER}",
                    "buttons_data": {
                        "body": "Do you want to order something else? / Kya aap kuch aur order karna chahtay hain?",
                        "buttons": [
                            {"id": "more_yes", "title": "Yes"},
                            {"id": "more_no", "title": "No"}
                        ]
                    }
                }

        # 5. STATE: AWAITING_CONTACT (Multi-text Address & Phone)
        if state == "AWAITING_CONTACT":
            phone_pattern = r'(?:(?:\+?92|0092|0)?\s*3\d{2}[-\s]?\d{7})|(?:0\d{2,3}[-\s]?\d{7,8})'
            phone_match = re.search(phone_pattern, user_text)

            if any(w in user_text.lower() for w in ["same number", "same", "yehi number", "isi number", "this number", "apna number"]):
                data["delivery_phone"] = customer_phone
                clean_t = re.sub(r'\b(?:same number|same|yehi number|isi number|this number)\b', '', user_text, flags=re.IGNORECASE).strip()
                if len(clean_t) >= 4:
                    data["delivery_address"] = clean_t

            elif phone_match:
                found_phone = phone_match.group(0).strip()
                data["delivery_phone"] = found_phone
                leftover = user_text.replace(phone_match.group(0), "").strip()
                leftover = re.sub(r'^(?:address|add|addr|phone|ph|cell|mobile|number|no|:|-)+\s*', '', leftover, flags=re.IGNORECASE).strip()
                if len(leftover) >= 4:
                    data["delivery_address"] = leftover

            else:
                if len(user_text) >= 4:
                    data["delivery_address"] = user_text.strip()

            has_address = bool(data.get("delivery_address"))
            has_phone = bool(data.get("delivery_phone"))

            if has_address and has_phone:
                database.set_session(customer_phone, "AWAITING_ORDER_CONFIRM", data)
                return self._build_order_summary_response(
                    cart,
                    data["delivery_address"],
                    data["delivery_phone"]
                )
            elif has_address and not has_phone:
                database.set_session(customer_phone, "AWAITING_CONTACT", data)
                return {
                    "type": "text",
                    "text": (
                        f"📍 Address noted: *{data['delivery_address']}*\n\n"
                        f"📞 Now please provide your **Contact Phone Number** (or reply 'same number'):"
                        f"{NAVIGATION_FOOTER}"
                    )
                }
            elif has_phone and not has_address:
                database.set_session(customer_phone, "AWAITING_CONTACT", data)
                return {
                    "type": "text",
                    "text": (
                        f"📞 Phone number noted: *{data['delivery_phone']}*\n\n"
                        f"📍 Now please provide your complete **Delivery Address** (House #, Street, Area/City):"
                        f"{NAVIGATION_FOOTER}"
                    )
                }
            else:
                return {
                    "type": "text",
                    "text": f"📍 Please provide your Delivery Address and Contact Phone Number to finalize your order:{NAVIGATION_FOOTER}"
                }

        # 6. STATE: AWAITING_ORDER_CONFIRM
        if state == "AWAITING_ORDER_CONFIRM":
            decision = brain_analysis.get("decision")
            if interactive_id == "final_confirm" or decision in ["yes", "confirm"] or any(w in user_text.lower() for w in ["yes", "confirm", "haan", "ok", "done", "theek"]):
                return self._finalize_order(customer_phone, data)

            elif interactive_id == "final_cancel" or decision in ["no", "cancel"] or any(w in user_text.lower() for w in ["no", "cancel", "nahi", "rehn do", "abort"]):
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
                return {"type": "text", "text": f"❌ Product not found in menu.{NAVIGATION_FOOTER}"}
                
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
                    f"{NAVIGATION_FOOTER}"
                )
            }
        except Exception as e:
            return {"type": "text", "text": f"Error selecting item: {e}"}

    def _process_quantity_input(self, customer_phone: str, data: Dict[str, Any], prod: Dict[str, Any], qty: int) -> Dict[str, Any]:
        cart = data.get("cart", [])
        in_cart = sum(it["qty"] for it in cart if it["prod_id"] == prod["id"])
        available = prod["stock_qty"] - in_cart

        if qty > available:
            data["partial_offered_qty"] = available
            database.set_session(customer_phone, "AWAITING_PARTIAL_DECISION", data)
            
            body_msg = (
                f"⚠️ Currently only *{available} packet(s)* of *{prod['name']}* are available right now in stock.\n\n"
                f"Would you like to confirm these {available} packet(s), or leave this product?"
            )
            return {
                "type": "interactive_buttons",
                "text": body_msg + NAVIGATION_FOOTER,
                "buttons_data": {
                    "body": body_msg,
                    "buttons": [
                        {"id": "partial_confirm", "title": f"Yes, confirm {available} pkts"[:20]},
                        {"id": "partial_leave", "title": "No, leave product"}
                    ]
                }
            }
        else:
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
            "text": body_text + "\n(Tap Yes or No below):" + NAVIGATION_FOOTER,
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
        lines.append(NAVIGATION_FOOTER.strip())

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
            return {"type": "text", "text": f"Your cart was empty. Please choose an item from the menu.{NAVIGATION_FOOTER}"}

        order_items = [{"product_id": item["prod_id"], "quantity": item["qty"]} for item in cart]
        
        # Atomic deduction in database
        result = database.place_order_atomic(
            customer_phone=contact_phone,
            customer_name="Customer",
            delivery_address=address,
            items=order_items
        )
        
        database.clear_session(customer_phone)
        
        if not result.get("success"):
            return {
                "type": "text",
                "text": f"❌ Could not confirm order: {result.get('error')}\nPlease start again by saying 'Hi'.{NAVIGATION_FOOTER}"
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
