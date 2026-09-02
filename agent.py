import os
import re
import json
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
import database

load_dotenv()

def build_menu_list_response() -> Dict[str, Any]:
    """Builds a WhatsApp Native Interactive List message containing all menu items and live stock."""
    menu = database.get_menu()
    rows = []
    text_lines = ["📋 *FC-HUT MENU & LIVE STOCK:*"]
    
    for p in menu:
        status_desc = f"Rs. {p['price_pkr']:,} | In Stock ({p['stock_qty']} pk)" if p['stock_qty'] > 0 else f"Rs. {p['price_pkr']:,} | Out of stock"
        text_lines.append(f"• *{p['name']}* ({p['pack_size']}) - Rs. {p['price_pkr']:,} [{'✅ In Stock' if p['stock_qty'] > 0 else '❌ Out of stock'}]")
        
        # Meta limits: title <= 24 chars, description <= 72 chars
        short_title = p['name'][:24]
        rows.append({
            "id": f"prod_{p['id']}",
            "title": short_title,
            "description": status_desc[:72]
        })
        
    fallback_text = "\n".join(text_lines) + "\n\n👉 *Reply with an item name or number to order!*"
    
    return {
        "type": "interactive_list",
        "text": fallback_text,
        "list_data": {
            "header": "FC-Hut Menu & Stock",
            "body": "👋 Salam & welcome to *FC-Hut*! 🍗\nAll items are blast-frozen & fresh. Tap below to choose your item:",
            "footer": "Prices in PKR | Cash on Delivery",
            "button_label": "🍗 View Menu & Stock",
            "sections": [
                {
                    "title": "Frozen Fried Chicken",
                    "rows": rows
                }
            ]
        }
    }

def build_quantity_buttons_response(prod: Dict[str, Any]) -> Dict[str, Any]:
    """Builds WhatsApp Native Quick Reply buttons for quantity selection."""
    body_text = (
        f"🍗 *{prod['name']}* ({prod['pack_size']})\n"
        f"💰 Price: Rs. {prod['price_pkr']:,} per pack\n"
        f"📦 Available: {prod['stock_qty']} packs in stock\n\n"
        f"How many packs would you like to order?"
    )
    return {
        "type": "interactive_buttons",
        "text": body_text + "\n(Tap a button below or type a number like 4):",
        "buttons_data": {
            "body": body_text,
            "buttons": [
                {"id": "qty_1", "title": "1 Pack"},
                {"id": "qty_2", "title": "2 Packs"},
                {"id": "qty_3", "title": "3 Packs"}
            ]
        }
    }

def build_confirmation_buttons_response(
    prod: Dict[str, Any],
    qty: int,
    subtotal: int,
    address: str
) -> Dict[str, Any]:
    """Builds WhatsApp Native Quick Reply buttons for final order confirmation."""
    body_text = (
        f"📋 *ORDER SUMMARY:*\n"
        f"• Item: {qty}x {prod['name']} ({prod['pack_size']})\n"
        f"• Subtotal: Rs. {subtotal:,}\n"
        f"📍 Delivery Address: {address}\n"
        f"💰 Total: Rs. {subtotal:,} (Cash on Delivery)\n\n"
        f"Should I confirm and dispatch this order?"
    )
    return {
        "type": "interactive_buttons",
        "text": body_text,
        "buttons_data": {
            "body": body_text,
            "buttons": [
                {"id": "order_confirm", "title": "✅ Confirm Order"},
                {"id": "order_cancel", "title": "❌ Cancel"}
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
        Main entry point for processing customer input.
        Handles both text messages and native interactive button/list clicks.
        Returns a structured dictionary with 'type', 'text', and optional 'list_data' / 'buttons_data'.
        """
        user_text = (user_text or "").strip()
        interactive_id = (interactive_id or "").strip()
        
        session = database.get_session(customer_phone)
        current_state = session.get("state", "IDLE")
        pending_data = session.get("data", {})
        
        # -------------------------------------------------------------
        # GLOBAL RESET / CANCEL
        # -------------------------------------------------------------
        if interactive_id == "order_cancel" or user_text.lower() in ["cancel", "reset", "stop", "abort", "wapas"]:
            database.clear_session(customer_phone)
            resp = build_menu_list_response()
            resp["text"] = "❌ Order cancelled.\n\n" + resp["text"]
            resp["list_data"]["body"] = "Order cancelled. Tap below to start a new order anytime:"
            return resp

        # -------------------------------------------------------------
        # 1. BUTTON / LIST SELECTION HANDLING
        # -------------------------------------------------------------
        # Case A: Product selected from list menu (e.g. "prod_1", "prod_10")
        if interactive_id.startswith("prod_"):
            try:
                prod_id = int(interactive_id.replace("prod_", ""))
                prod = database.get_product_by_id(prod_id)
                if not prod:
                    return {"type": "text", "text": "❌ Product not found. Please choose an item from the menu."}
                if prod["stock_qty"] <= 0:
                    resp = build_menu_list_response()
                    resp["text"] = f"❌ Sorry, *{prod['name']}* is currently sold out! Please choose another item:\n\n" + resp["text"]
                    return resp
                    
                # Transition to AWAITING_QTY
                database.set_session(customer_phone, "AWAITING_QTY", {"prod_id": prod["id"]})
                return build_quantity_buttons_response(prod)
            except Exception as e:
                return {"type": "text", "text": f"Error selecting product: {e}"}

        # Case B: Quantity button tapped (e.g. "qty_1", "qty_2", "qty_3")
        if interactive_id.startswith("qty_"):
            try:
                qty = int(interactive_id.replace("qty_", ""))
                return self._handle_quantity_selected(customer_phone, pending_data, qty)
            except Exception as e:
                return {"type": "text", "text": f"Error selecting quantity: {e}"}

        # Case C: Order Confirmation button tapped ("order_confirm")
        if interactive_id == "order_confirm":
            return self._handle_order_confirmed(customer_phone, pending_data)

        # -------------------------------------------------------------
        # 2. STATE MACHINE HANDLING FOR TEXT INPUT
        # -------------------------------------------------------------
        # Check if customer changed their mind and mentioned a different product
        new_prod_match = database.match_product_by_text(user_text) if current_state != "AWAITING_CONFIRM" else None

        if current_state == "AWAITING_QTY":
            # If user mentioned a different product entirely, switch to it!
            if new_prod_match and new_prod_match["id"] != pending_data.get("prod_id"):
                database.clear_session(customer_phone)
                # re-process as fresh product request
                return self.process_input(customer_phone, user_text=user_text)

            # Extract quantity from text (e.g. "2", "3 packs", "two")
            qty_match = re.search(r'\b(\d+)\b', user_text)
            if qty_match:
                qty = int(qty_match.group(1))
                return self._handle_quantity_selected(customer_phone, pending_data, qty)
            else:
                prod = database.get_product_by_id(pending_data.get("prod_id"))
                if prod:
                    return {
                        "type": "text",
                        "text": f"Please specify how many packs of *{prod['name']}* you want (e.g., tap a button or type 1, 2, 3):"
                    }

        elif current_state == "AWAITING_ADDRESS":
            # Customer sent address text
            if len(user_text) < 5:
                return {
                    "type": "text",
                    "text": "📍 Please provide a complete delivery address (House #, Street, Area/City) so our rider can deliver your order."
                }
                
            pending_data["address"] = user_text
            database.set_session(customer_phone, "AWAITING_CONFIRM", pending_data)
            
            prod = database.get_product_by_id(pending_data["prod_id"])
            qty = pending_data["qty"]
            subtotal = pending_data["subtotal"]
            return build_confirmation_buttons_response(prod, qty, subtotal, user_text)

        elif current_state == "AWAITING_CONFIRM":
            if any(w in user_text.lower() for w in ["yes", "confirm", "haan", "ok", "done", "theek", "bhej do"]):
                return self._handle_order_confirmed(customer_phone, pending_data)
            elif any(w in user_text.lower() for w in ["no", "cancel", "nahi", "change"]):
                database.clear_session(customer_phone)
                resp = build_menu_list_response()
                resp["text"] = "❌ Order cancelled. Tap below to start over:\n\n" + resp["text"]
                return resp
            else:
                prod = database.get_product_by_id(pending_data["prod_id"])
                return build_confirmation_buttons_response(
                    prod,
                    pending_data["qty"],
                    pending_data["subtotal"],
                    pending_data["address"]
                )

        # -------------------------------------------------------------
        # 3. IDLE / GENERAL CHAT (Fuzzy product matching & greetings)
        # -------------------------------------------------------------
        # Check if customer mentions a product directly (e.g., "samosiyan", "nuggets", "2 tenders")
        matched_product = database.match_product_by_text(user_text)
        if matched_product:
            if matched_product["stock_qty"] <= 0:
                resp = build_menu_list_response()
                resp["text"] = f"❌ *{matched_product['name']}* is currently out of stock. Please check other items:\n\n" + resp["text"]
                return resp
                
            # Check if quantity was also mentioned (e.g. "2 samosiyan")
            qty_match = re.search(r'\b(\d+)\b', user_text)
            if qty_match:
                qty = int(qty_match.group(1))
                if 1 <= qty <= matched_product["stock_qty"]:
                    pending_data = {
                        "prod_id": matched_product["id"],
                        "qty": qty,
                        "subtotal": matched_product["price_pkr"] * qty
                    }
                    # Check if address was also provided in the same message
                    if any(w in user_text.lower() for w in ["house", "street", "sector", "road", "block", "phase", "flat", "islamabad", "lahore", "karachi", "rawalpindi"]):
                        pending_data["address"] = user_text
                        database.set_session(customer_phone, "AWAITING_CONFIRM", pending_data)
                        return build_confirmation_buttons_response(
                            matched_product,
                            qty,
                            pending_data["subtotal"],
                            user_text
                        )

                    database.set_session(customer_phone, "AWAITING_ADDRESS", pending_data)
                    return {
                        "type": "text",
                        "text": (
                            f"✅ Selected: *{qty}x {matched_product['name']}* = Rs. {pending_data['subtotal']:,}\n\n"
                            f"📍 *Please reply with your complete Delivery Address* (House #, Street, City) to finalize your order:"
                        )
                    }

            # Otherwise, ask for quantity with buttons
            database.set_session(customer_phone, "AWAITING_QTY", {"prod_id": matched_product["id"]})
            return build_quantity_buttons_response(matched_product)

        # Greetings or general inquiry -> Show interactive menu list
        return build_menu_list_response()

    def _handle_quantity_selected(
        self,
        customer_phone: str,
        pending_data: Dict[str, Any],
        qty: int
    ) -> Dict[str, Any]:
        prod_id = pending_data.get("prod_id")
        prod = database.get_product_by_id(prod_id)
        if not prod:
            database.clear_session(customer_phone)
            return build_menu_list_response()
            
        if qty <= 0:
            return {"type": "text", "text": "Please enter a valid quantity of at least 1."}
            
        if qty > prod["stock_qty"]:
            return {
                "type": "text",
                "text": f"⚠️ Sorry, only *{prod['stock_qty']} packs* of *{prod['name']}* are available right now. Please choose a quantity up to {prod['stock_qty']}."
            }

        subtotal = prod["price_pkr"] * qty
        pending_data["qty"] = qty
        pending_data["subtotal"] = subtotal
        
        database.set_session(customer_phone, "AWAITING_ADDRESS", pending_data)
        
        return {
            "type": "text",
            "text": (
                f"✅ Selected: *{qty}x {prod['name']}* = Rs. {subtotal:,}\n\n"
                f"📍 *Please reply with your complete Delivery Address* (House #, Street, City) to finalize your order:"
            )
        }

    def _handle_order_confirmed(
        self,
        customer_phone: str,
        pending_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        prod_id = pending_data.get("prod_id")
        qty = pending_data.get("qty", 1)
        address = pending_data.get("address", "")
        
        prod = database.get_product_by_id(prod_id)
        if not prod:
            database.clear_session(customer_phone)
            return {"type": "text", "text": "❌ Order session expired. Please start again by typing 'menu'."}
            
        # Atomic order placement & stock deduction
        result = database.place_order_atomic(
            customer_phone=customer_phone,
            customer_name="Valued Customer",
            delivery_address=address,
            items=[{"product_id": prod_id, "quantity": qty}]
        )
        
        # Clear session after order attempt
        database.clear_session(customer_phone)
        
        if not result.get("success"):
            return {
                "type": "text",
                "text": f"❌ Could not confirm order: {result.get('error')}\nPlease tap below to choose another item."
            }
            
        order_id = result["order_id"]
        total = result["total_pkr"]
        receipt_text = (
            f"🎉 *ORDER CONFIRMED! (Order #{order_id})*\n\n"
            f"📦 *Item:* {qty}x {prod['name']} ({prod['pack_size']})\n"
            f"💰 *Total:* Rs. {total:,} (Cash on Delivery)\n"
            f"📍 *Delivery To:* {address}\n\n"
            f"🛵 Your frozen chicken items will be dispatched shortly. Thank you for choosing FC-Hut! 🍗"
        )
        return {"type": "text", "text": receipt_text}

    # Backward compatibility method for string text responses
    def handle_message(self, customer_phone: str, user_message: str) -> str:
        resp = self.process_input(customer_phone, user_text=user_message)
        return resp.get("text", "")
