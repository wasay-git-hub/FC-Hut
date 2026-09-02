# 🍗 FC-Hut — WhatsApp AI Agent (Frozen Chicken Items)

An automated WhatsApp AI Sales & Stock Management Agent for **FC-Hut**, a small business selling frozen chicken fried items.

All pricing is in **PKR (Rs.)**, inventory is pre-seeded in SQLite with atomic stock deductions, and customer orders are automatically logged with receipts.

---

## 🚀 Quick Start (Test Native Buttons in 10 Seconds)

You can interact with the agent right now in your terminal. It visually simulates WhatsApp's native interactive buttons and list menus:

```bash
python simulate_chat.py
```

### Try this in the simulator:
1. **Browse List Menu**: Type `10` or tap any option (1-10) to choose an item (e.g. Samosas).
2. **Select Quantity**: Type `B` or `2` to tap the `[ 2 Packs ]` button.
3. **Enter Address**: Type `House 12, Street 4, Islamabad`.
4. **Confirm Order**: Type `A` or `1` to tap `[ ✅ Confirm Order ]`.
5. **Inspect Live Stock**: Type `/stock` to see that stock was automatically decremented in the SQLite database!

---

## 💡 Typo & Roman Urdu Tolerance

Customers rarely write exact dictionary spellings on WhatsApp. The agent automatically handles:
- **Samosas**: `samosiyan`, `samose`, `samosay`, `samosi`
- **Nuggets**: `nagats`, `nagat`, `nugets`, `nagits`
- **Tenders**: `tandar`, `tandars`
- **Kababs**: `kababain`, `chapli kabab`, `seekh`

Even if a customer types *"bhai 2 packet samosiyan bhej do"*, the agent seamlessly maps it to **Crispy Chicken Samosas** and asks for their address!

---

## 📱 WhatsApp Native Interactive Features

- **Native List Menu (`list`)**:
  - Pops up a native scrollable list of all frozen items with live pack sizes and PKR prices.
  - Zero spelling errors possible — customer simply taps their choice.
- **Quick Reply Buttons (`button`)**:
  - `[ 1 Pack ]` `[ 2 Packs ]` `[ 3 Packs ]` for instant quantity selection.
  - `[ ✅ Confirm Order ]` `[ ❌ Cancel ]` for final confirmation.

---

## 📂 Project Structure

```
FC-Hut/
├── database.py       # SQLite database, pre-seeded products, atomic stock deduction & order history
├── agent.py          # AI agent with Tool/Function Calling (Gemini Flash + Smart Standalone Fallback)
├── main.py           # FastAPI Webhook server (Meta WhatsApp Cloud API compliant)
├── simulate_chat.py  # Interactive terminal WhatsApp simulator
├── test_stock.py     # Unit tests verifying atomic stock deduction & negative stock prevention
├── test_e2e.py       # Full conversational flow test
├── test_api.py       # FastAPI endpoint tests
├── requirements.txt  # Project dependencies
├── .env.example      # Environment variables template
└── fchut.db          # Live SQLite database (auto-created)
```

---

## 🍗 Pre-seeded Products (PKR)

| Product | Pack Size | Price (PKR) | Initial Stock |
| :--- | :--- | :--- | :--- |
| **Crispy Chicken Nuggets** | 1kg pack | Rs. 1,450 | 10 – 25 packs |
| **Tempura Nuggets** | 500g pack | Rs. 850 | 6 – 18 packs |
| **Crispy Chicken Tenders** | 500g pack | Rs. 950 | 8 – 20 packs |
| **Spicy Buffalo Wings** | 750g pack | Rs. 1,150 | 5 – 16 packs |
| **Chicken Cheese Balls** | 12 pcs (400g) | Rs. 890 | 5 – 15 packs |
| **Zinger Burger Fillets** | 4 fillets | Rs. 980 | 10 – 22 packs |
| **Crispy Popcorn Chicken** | 500g pack | Rs. 920 | 8 – 20 packs |
| **Chicken Chapli Kabab** | 6 kababs | Rs. 780 | 6 – 16 packs |
| **Chicken Seekh Kabab** | 6 seekh | Rs. 820 | 5 – 15 packs |
| **Crispy Chicken Samosas** | 12 samosas | Rs. 650 | 10 – 30 packs |

---

## ⚡ Running the FastAPI Webhook Server

Start the server:
```bash
python main.py
```
*(Or `uvicorn main:app --reload`)*

The server will be available at `http://localhost:8000`:
- **Live Inventory (JSON)**: `http://localhost:8000/products`
- **Orders Placed (JSON)**: `http://localhost:8000/orders`
- **Interactive API Docs (Swagger)**: `http://localhost:8000/docs`
- **Direct Test Chat**: `POST http://localhost:8000/test-chat`

---

## 🔑 Activating Google Gemini (Optional)

The agent runs with an intelligent fallback out-of-the-box. To enable full generative conversational AI with Gemini:

1. Get a free API key from [Google AI Studio](https://aistudio.google.com/).
2. Create a `.env` file from `.env.example`:
   ```bash
   cp .env.example .env
   ```
3. Add your key:
   ```env
   GEMINI_API_KEY=your_actual_key_here
   ```

---

## 📲 Connecting to Real WhatsApp (Meta Cloud API)

When you're ready to connect to a real WhatsApp number:

1. In your Meta Developer App, select **WhatsApp > Configuration**.
2. Expose your local server to the internet using **ngrok**:
   ```bash
   ngrok http 8000
   ```
3. Set your Callback URL in Meta:
   - **Callback URL**: `https://your-ngrok-url.ngrok-free.app/webhook`
   - **Verify Token**: `fchut_secret_verify_token_123` (configured in `.env`)
4. Copy your **Access Token** and **Phone Number ID** into your `.env` file:
   ```env
   WHATSAPP_TOKEN=EAAG...
   WHATSAPP_PHONE_NUMBER_ID=1092384729...
   ```
5. When customers send a WhatsApp message, Meta forwards it to your webhook, the agent checks stock, deducts inventory, and sends the reply back automatically!