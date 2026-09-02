import os
import sys
import requests
from fastapi import FastAPI, Request, Query, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import database
from agent import FCHutAgent

load_dotenv()

app = FastAPI(
    title="FC-Hut WhatsApp AI Agent",
    description="Automated AI Sales & Stock Management Agent for Frozen Chicken Items (PKR) with Native Buttons & Lists"
)

# Initialize database on startup
database.init_db()
database.seed_products()

agent = FCHutAgent()

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "fchut_secret_verify_token_123")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "").strip()
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "").strip()

@app.get("/")
def home():
    return {
        "business": "FC-Hut (Frozen Chicken Hut)",
        "status": "online",
        "currency": "PKR",
        "interactive_features": ["Native WhatsApp List Menus", "Quick Reply Buttons", "Atomic Stock Deduction"],
        "endpoints": {
            "products": "/products",
            "orders": "/orders",
            "meta_webhook": "/webhook",
            "test_chat": "/test-chat"
        }
    }

@app.get("/products")
def list_products():
    """Returns all frozen chicken items, pack sizes, PKR prices, and current live stock."""
    return {"products": database.get_menu()}

@app.get("/orders")
def list_orders():
    """Returns all recorded customer orders."""
    return {"orders": database.get_orders()}

# -------------------------------------------------------------
# 1. META WHATSAPP CLOUD API WEBHOOK VERIFICATION (GET)
# -------------------------------------------------------------
@app.get("/webhook")
def verify_webhook(
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
):
    """
    Endpoint required by Meta to verify webhook ownership.
    When configuring Webhook in Meta Developer Portal, Meta sends a GET request here.
    """
    if hub_mode == "subscribe" and hub_verify_token == VERIFY_TOKEN:
        print(f"[Meta Webhook] Successfully verified with challenge: {hub_challenge}")
        return PlainTextResponse(content=hub_challenge, status_code=200)
    
    print("[Meta Webhook] Verification failed: Token mismatch")
    raise HTTPException(status_code=403, detail="Verification token mismatch")

# -------------------------------------------------------------
# 2. META WHATSAPP SENDER (TEXT, NATIVE LISTS & BUTTONS)
# -------------------------------------------------------------
def send_whatsapp_payload(payload: Dict[str, Any]) -> bool:
    """Sends any compliant WhatsApp Cloud API JSON payload to Meta."""
    if not WHATSAPP_TOKEN or not WHATSAPP_PHONE_NUMBER_ID:
        print(f"[Notice] WhatsApp token not configured in .env. Payload preview:\n{payload}")
        return False
        
    url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
        print(f"[WhatsApp Sent] Successfully delivered message to {payload.get('to')}")
        return True
    except Exception as e:
        print(f"[WhatsApp Send Error]: {e}")
        return False

def send_whatsapp_response(to_phone: str, resp_dict: Dict[str, Any]):
    """Dispatches the structured agent response to the customer via Meta WhatsApp Cloud API."""
    msg_type = resp_dict.get("type", "text")
    
    if msg_type == "interactive_list" and "list_data" in resp_dict:
        ld = resp_dict["list_data"]
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_phone,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "header": {"type": "text", "text": ld.get("header", "FC-Hut Menu")},
                "body": {"text": ld.get("body", "Please select an item:")},
                "footer": {"text": ld.get("footer", "")},
                "action": {
                    "button": ld.get("button_label", "View Menu"),
                    "sections": ld.get("sections", [])
                }
            }
        }
    elif msg_type == "interactive_buttons" and "buttons_data" in resp_dict:
        bd = resp_dict["buttons_data"]
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_phone,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": bd.get("body", "Please choose an option:")},
                "action": {
                    "buttons": [
                        {"type": "reply", "reply": {"id": b["id"], "title": b["title"]}}
                        for b in bd.get("buttons", [])
                    ]
                }
            }
        }
    else:
        # Standard text message
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_phone,
            "type": "text",
            "text": {"body": resp_dict.get("text", "")}
        }
        
    return send_whatsapp_payload(payload)

# -------------------------------------------------------------
# 3. META WHATSAPP CLOUD API INCOMING MESSAGES (POST)
# -------------------------------------------------------------
@app.post("/webhook")
async def receive_webhook(request: Request):
    """
    Receives incoming WhatsApp webhook payloads from Meta.
    Handles standard text messages as well as interactive button & list clicks.
    """
    body = await request.json()
    
    # 1. Handle Meta WhatsApp Cloud API payload
    if "entry" in body:
        for entry in body.get("entry", []):
            for change in entry.get("changes", []):
                val = change.get("value", {})
                messages = val.get("messages", [])
                for msg in messages:
                    sender_phone = msg.get("from")
                    msg_type = msg.get("type")
                    
                    if msg_type == "text":
                        user_text = msg.get("text", {}).get("body", "")
                        print(f"\n[Incoming Text] From: {sender_phone} | Text: {user_text}")
                        reply_dict = agent.process_input(sender_phone, user_text=user_text)
                        send_whatsapp_response(sender_phone, reply_dict)
                        
                    elif msg_type == "interactive":
                        interactive = msg.get("interactive", {})
                        itype = interactive.get("type")  # "list_reply" or "button_reply"
                        reply_obj = interactive.get(itype, {})
                        item_id = reply_obj.get("id")
                        item_title = reply_obj.get("title", "")
                        
                        print(f"\n[Incoming Click] From: {sender_phone} | Type: {itype} | ID: {item_id} | Title: {item_title}")
                        reply_dict = agent.process_input(sender_phone, interactive_id=item_id)
                        send_whatsapp_response(sender_phone, reply_dict)
                        
        return JSONResponse(content={"status": "received"}, status_code=200)

    # 2. Simplified fallback for direct testing (e.g. Postman or cURL)
    sender = body.get("phone", "+923001234567")
    user_text = body.get("message")
    interactive_id = body.get("interactive_id")
    
    reply_dict = agent.process_input(sender, user_text=user_text, interactive_id=interactive_id)
    return {"sender": sender, "response": reply_dict}

# -------------------------------------------------------------
# 4. DIRECT TEST CHAT ENDPOINT
# -------------------------------------------------------------
class TestChatRequest(BaseModel):
    phone: str = "+923001234567"
    message: Optional[str] = None
    interactive_id: Optional[str] = None

@app.post("/test-chat")
def test_chat(req: TestChatRequest):
    """Direct endpoint to test the agent with text or button clicks."""
    resp = agent.process_input(req.phone, user_text=req.message, interactive_id=req.interactive_id)
    return {
        "customer_phone": req.phone,
        "input_message": req.message,
        "input_interactive_id": req.interactive_id,
        "reply": resp.get("text", ""),
        "response": resp
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
