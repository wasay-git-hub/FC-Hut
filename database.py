import sqlite3
import json
import random
from typing import List, Dict, Any, Optional
from pathlib import Path

DB_PATH = Path(__file__).parent / "fchut.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes the database tables."""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Products table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                category TEXT NOT NULL,
                pack_size TEXT NOT NULL,
                price_pkr INTEGER NOT NULL,
                stock_qty INTEGER NOT NULL DEFAULT 0
            )
        """)
        
        # Orders table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_phone TEXT NOT NULL,
                customer_name TEXT,
                delivery_address TEXT NOT NULL,
                items_json TEXT NOT NULL,
                total_pkr INTEGER NOT NULL,
                status TEXT DEFAULT 'CONFIRMED',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Chat history table for conversation continuity
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_history (
                customer_phone TEXT PRIMARY KEY,
                history_json TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Customer session state for interactive buttons flow
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS customer_sessions (
                customer_phone TEXT PRIMARY KEY,
                state TEXT NOT NULL DEFAULT 'IDLE',
                pending_data_json TEXT NOT NULL DEFAULT '{}',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

def seed_products(force: bool = False):
    """Pre-seeds the inventory with realistic frozen chicken items and random stock quantities."""
    init_db()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM products")
        count = cursor.fetchone()[0]
        
        if count > 0 and not force:
            return  # Already seeded

        # Clear existing if force is True
        if force:
            cursor.execute("DELETE FROM products")
            cursor.execute("DELETE FROM sqlite_sequence WHERE name = 'products'")
            
        initial_items = [
            ("Crispy Chicken Nuggets", "Nuggets", "1 packet consists of 24 pieces", 1450, random.randint(10, 25)),
            ("Tempura Nuggets", "Nuggets", "1 packet consists of 12 pieces", 850, random.randint(6, 18)),
            ("Crispy Chicken Tenders", "Tenders", "1 packet consists of 10 tenders", 950, random.randint(8, 20)),
            ("Spicy Buffalo Wings", "Wings", "1 packet consists of 12 wings", 1150, random.randint(5, 16)),
            ("Chicken Cheese Balls", "Snacks", "1 packet consists of 12 cheese balls", 890, random.randint(5, 15)),
            ("Zinger Burger Fillets", "Patties", "1 packet consists of 4 fillets", 980, random.randint(10, 22)),
            ("Crispy Popcorn Chicken", "Snacks", "1 packet consists of 40 pieces", 920, random.randint(8, 20)),
            ("Chicken Chapli Kabab", "Kababs", "1 packet consists of 6 kababs", 780, random.randint(6, 16)),
            ("Chicken Seekh Kabab", "Kababs", "1 packet consists of 8 pieces", 850, random.randint(5, 15)),
            ("Crispy Chicken Samosas", "Snacks", "1 packet consists of 12 samosas", 650, random.randint(10, 30)),
        ]
        
        cursor.executemany("""
            INSERT OR REPLACE INTO products (name, category, pack_size, price_pkr, stock_qty)
            VALUES (?, ?, ?, ?, ?)
        """, initial_items)
        conn.commit()

def get_menu(only_in_stock: bool = False) -> List[Dict[str, Any]]:
    """Returns products with their current stock status and PKR pricing (can filter to in-stock only)."""
    with get_db() as conn:
        cursor = conn.cursor()
        if only_in_stock:
            cursor.execute("SELECT id, name, category, pack_size, price_pkr, stock_qty FROM products WHERE stock_qty > 0 ORDER BY category, name")
        else:
            cursor.execute("SELECT id, name, category, pack_size, price_pkr, stock_qty FROM products ORDER BY category, name")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

def check_stock(query: str = "") -> List[Dict[str, Any]]:
    """Checks stock for items matching a keyword (or returns all in-stock items if query is empty)."""
    with get_db() as conn:
        cursor = conn.cursor()
        if query.strip():
            wildcard = f"%{query.strip()}%"
            cursor.execute("""
                SELECT id, name, category, pack_size, price_pkr, stock_qty 
                FROM products 
                WHERE name LIKE ? OR category LIKE ?
                ORDER BY stock_qty DESC
            """, (wildcard, wildcard))
        else:
            cursor.execute("""
                SELECT id, name, category, pack_size, price_pkr, stock_qty 
                FROM products 
                WHERE stock_qty > 0
                ORDER BY category, name
            """)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

def place_order_atomic(
    customer_phone: str,
    customer_name: Optional[str],
    delivery_address: str,
    items: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Atomically places an order and deducts stock from inventory.
    Each item in `items` should be: {"product_id": int, "quantity": int} or {"name": str, "quantity": int}.
    
    If stock is insufficient for ANY item, transaction rolls back and returns an error dictionary.
    """
    if not items:
        return {"success": False, "error": "Order must contain at least one item."}
    
    if not delivery_address or not delivery_address.strip():
        return {"success": False, "error": "Delivery address is required to place an order."}

    conn = get_db()
    try:
        cursor = conn.cursor()
        
        # 1. Resolve and validate stock for all items
        resolved_items = []
        total_pkr = 0
        
        for item in items:
            qty = int(item.get("quantity", 1))
            if qty <= 0:
                return {"success": False, "error": "Quantity must be at least 1."}
                
            product_id = item.get("product_id")
            name = item.get("name")
            
            if product_id:
                cursor.execute("SELECT id, name, pack_size, price_pkr, stock_qty FROM products WHERE id = ?", (product_id,))
            elif name:
                cursor.execute("SELECT id, name, pack_size, price_pkr, stock_qty FROM products WHERE name LIKE ?", (f"%{name}%",))
            else:
                return {"success": False, "error": "Each item must have a product_id or name."}
                
            product = cursor.fetchone()
            if not product:
                return {"success": False, "error": f"Product '{name or product_id}' not found in catalog."}
                
            prod_id = product["id"]
            prod_name = product["name"]
            prod_price = product["price_pkr"]
            current_stock = product["stock_qty"]
            pack_size = product["pack_size"]
            
            if current_stock < qty:
                return {
                    "success": False,
                    "error": f"Insufficient stock for '{prod_name}'. Requested: {qty}, Available: {current_stock}."
                }
                
            line_total = prod_price * qty
            total_pkr += line_total
            resolved_items.append({
                "product_id": prod_id,
                "name": prod_name,
                "pack_size": pack_size,
                "price_pkr": prod_price,
                "quantity": qty,
                "subtotal_pkr": line_total
            })

        # 2. Deduct stock atomically
        for item in resolved_items:
            cursor.execute("""
                UPDATE products 
                SET stock_qty = stock_qty - ? 
                WHERE id = ? AND stock_qty >= ?
            """, (item["quantity"], item["product_id"], item["quantity"]))
            
            if cursor.rowcount == 0:
                conn.rollback()
                return {"success": False, "error": f"Stock conflict for '{item['name']}'. Please try again."}

        # 3. Create order record
        cursor.execute("""
            INSERT INTO orders (customer_phone, customer_name, delivery_address, items_json, total_pkr, status)
            VALUES (?, ?, ?, ?, ?, 'CONFIRMED')
        """, (
            customer_phone,
            customer_name or "Valued Customer",
            delivery_address.strip(),
            json.dumps(resolved_items),
            total_pkr
        ))
        order_id = cursor.lastrowid
        conn.commit()

        return {
            "success": True,
            "order_id": order_id,
            "customer_phone": customer_phone,
            "customer_name": customer_name or "Valued Customer",
            "delivery_address": delivery_address.strip(),
            "items": resolved_items,
            "total_pkr": total_pkr,
            "currency": "PKR",
            "status": "CONFIRMED"
        }

    except Exception as e:
        conn.rollback()
        return {"success": False, "error": str(e)}
    finally:
        conn.close()

def get_orders() -> List[Dict[str, Any]]:
    """Returns all recorded orders."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM orders ORDER BY id DESC")
        rows = cursor.fetchall()
        orders = []
        for r in rows:
            order = dict(r)
            order["items"] = json.loads(order["items_json"])
            orders.append(order)
        return orders

def get_chat_history(customer_phone: str) -> List[Dict[str, str]]:
    """Retrieves previous chat messages for this customer."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT history_json FROM chat_history WHERE customer_phone = ?", (customer_phone,))
        row = cursor.fetchone()
        if row:
            try:
                return json.loads(row["history_json"])
            except Exception:
                return []
        return []

def save_chat_history(customer_phone: str, history: List[Dict[str, str]]):
    """Saves updated conversation history for a customer (keeps last 20 messages)."""
    with get_db() as conn:
        cursor = conn.cursor()
        # Keep only the last 20 messages to avoid token blowup
        trimmed = history[-20:]
        cursor.execute("""
            INSERT INTO chat_history (customer_phone, history_json, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(customer_phone) DO UPDATE SET 
                history_json = excluded.history_json,
                updated_at = CURRENT_TIMESTAMP
        """, (customer_phone, json.dumps(trimmed)))
        conn.commit()

def get_product_by_id(product_id: int) -> Optional[Dict[str, Any]]:
    """Retrieves a single product by its database ID."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM products WHERE id = ?", (product_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

# Product aliases for typo and Roman Urdu tolerance
PRODUCT_KEYWORD_MAP = [
    ("%Samosa%", ["samosa", "samosay", "samose", "samosiyan", "samosi", "somosa"]),
    ("%Crispy Chicken Nuggets%", ["crispy nugget", "nugget", "nuggets", "nagats", "nagat", "nugets"]),
    ("%Tempura Nuggets%", ["tempura", "tempura nugget", "tempura nuggets"]),
    ("%Tenders%", ["tender", "tenders", "crispy tender", "tandar", "tandars"]),
    ("%Wings%", ["wing", "wings", "buffalo", "buffalo wing", "buffalo wings", "spicy wing"]),
    ("%Cheese Balls%", ["cheese ball", "cheese balls", "ball", "balls"]),
    ("%Fillets%", ["fillet", "fillets", "zinger", "zinger fillet", "burger patty", "patty"]),
    ("%Popcorn%", ["popcorn", "popcorn chicken", "chicken popcorn"]),
    ("%Chapli%", ["chapli", "chapli kabab", "chapli kababs", "kababain"]),
    ("%Seekh%", ["seekh", "seekh kabab", "seekh kababs", "sikh kabab"])
]

def match_product_by_text(user_text: str) -> Optional[Dict[str, Any]]:
    """Matches text against product IDs, names, or Roman Urdu/spelling aliases."""
    text = user_text.lower().strip()
    
    # 1. Explicit ID match (e.g. "prod_10", "#10", "item 10", or just "10")
    import re
    explicit_id = re.match(r'^(?:prod_|^#|^item\s*)?(\d{1,2})$', text)
    if explicit_id:
        pid = int(explicit_id.group(1))
        prod = get_product_by_id(pid)
        if prod:
            return prod
            
    # 2. Match against Roman Urdu & typo aliases
    with get_db() as conn:
        cursor = conn.cursor()
        for name_pattern, aliases in PRODUCT_KEYWORD_MAP:
            for alias in aliases:
                # check as whole word or substring
                if re.search(r'\b' + re.escape(alias) + r'\b', text) or alias in text:
                    cursor.execute("SELECT * FROM products WHERE name LIKE ? LIMIT 1", (name_pattern,))
                    row = cursor.fetchone()
                    if row:
                        return dict(row)
                
    # 3. Direct database substring match
    matches = check_stock(text)
    if matches:
        return matches[0]
        
    return None

def get_session(customer_phone: str) -> Dict[str, Any]:
    """Gets the interactive ordering session for a customer."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT state, pending_data_json FROM customer_sessions WHERE customer_phone = ?", (customer_phone,))
        row = cursor.fetchone()
        if row:
            try:
                data = json.loads(row["pending_data_json"])
            except Exception:
                data = {}
            return {"state": row["state"], "data": data}
        return {"state": "IDLE", "data": {}}

def set_session(customer_phone: str, state: str, data: Dict[str, Any] = None):
    """Sets the current state and pending order data for a customer."""
    if data is None:
        data = {}
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO customer_sessions (customer_phone, state, pending_data_json, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(customer_phone) DO UPDATE SET 
                state = excluded.state,
                pending_data_json = excluded.pending_data_json,
                updated_at = CURRENT_TIMESTAMP
        """, (customer_phone, state, json.dumps(data)))
        conn.commit()

def clear_session(customer_phone: str):
    """Resets the customer session back to IDLE."""
    set_session(customer_phone, "IDLE", {})

if __name__ == "__main__":
    init_db()
    seed_products(force=True)
    print("Database initialized and seeded successfully!")
    for item in get_menu():
        print(f"[{item['id']}] {item['name']} | PKR {item['price_pkr']} | Stock: {item['stock_qty']} packs")
