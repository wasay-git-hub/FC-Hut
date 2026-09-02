import os
import requests
from fastapi import FastAPI, Request, Response, Query, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv

import database
from agent import FCHutAgent

load_dotenv()

app = FastAPI(
    title="FC-Hut WhatsApp AI Agent",
    description="Automated AI Sales & Stock Management Agent for Frozen Chicken Items (PKR)"
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
# 2. META WHATSAPP CLOUD API INCOMING MESSAGES (POST)
# -------------------------------------------------------------
def send_whatsapp_message(to_phone: str, message_text: str):
    """Sends a message back to the customer using Meta's WhatsApp Cloud API."""
    if not WHATSAPP_TOKEN or not WHATSAPP_PHONE_NUMBER_ID:
        print(f"[Notice] WhatsApp token not configured in .env. Reply output:\n{message_text}")
        return False
        
    url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "text",
        "text": {"body": message_text}
    }
    
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
        print(f"[WhatsApp Sent] Successfully sent reply to {to_phone}")
        return True
    except Exception as e:
        print(f"[WhatsApp Send Error]: {e}")
        return False

@app.post("/webhook")
async def receive_webhook(request: Request):
    """
    Receives incoming WhatsApp webhook payloads.
    Supports standard Meta WhatsApp Cloud API format and custom JSON payloads for testing.
    """
    body = await request.json()
    
    # 1. Handle Meta WhatsApp Cloud API structure
    if "entry" in body:
        for entry in body.get("entry", []):
            for change in entry.get("changes", []):
                val = change.get("value", {})
                messages = val.get("messages", [])
                for msg in messages:
                    if msg.get("type") == "text":
                        sender_phone = msg.get("from")
                        text = msg.get("text", {}).get("body", "")
                        
                        print(f"\n[Incoming WhatsApp] From: {sender_phone} | Message: {text}")
                        reply = agent.handle_message(sender_phone, text)
                        print(f"[Agent Reply]:\n{reply}\n")
                        
                        send_whatsapp_message(sender_phone, reply)
                        
        return JSONResponse(content={"status": "received"}, status_code=200)

    # 2. Simplified fallback for direct testing (e.g. Postman or cURL)
    sender = body.get("phone", "+923001234567")
    text = body.get("message", "")
    if text:
        reply = agent.handle_message(sender, text)
        return {"sender": sender, "reply": reply}
        
    return JSONResponse(content={"status": "ignored"}, status_code=200)

# -------------------------------------------------------------
# 3. DIRECT TEST CHAT ENDPOINT (FOR CONVENIENT TESTING)
# -------------------------------------------------------------
class TestChatRequest(BaseModel):
    phone: str = "+923001234567"
    message: str

@app.post("/test-chat")
def test_chat(req: TestChatRequest):
    """Direct endpoint to test the agent without needing WhatsApp configured."""
    reply = agent.handle_message(req.phone, req.message)
    return {
        "customer_phone": req.phone,
        "message": req.message,
        "reply": reply
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
