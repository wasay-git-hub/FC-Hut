import database

def test_atomic_order():
    database.init_db()
    database.seed_products(force=True)
    
    # 1. Test check_stock
    nuggets = database.check_stock("Nuggets")
    assert len(nuggets) >= 2, "Should find at least 2 nugget products"
    item1 = nuggets[0]
    initial_stock = item1["stock_qty"]
    print(f"Initial stock for {item1['name']}: {initial_stock}")
    
    # 2. Test valid order
    order_result = database.place_order_atomic(
        customer_phone="+923001234567",
        customer_name="Ali Khan",
        delivery_address="House 42, Street 7, F-8/2, Islamabad",
        items=[{"product_id": item1["id"], "quantity": 2}]
    )
    assert order_result["success"] is True, f"Order failed: {order_result}"
    print(f"Order #{order_result['order_id']} placed successfully! Total: PKR {order_result['total_pkr']}")
    
    # Check that stock decreased by exactly 2
    updated_items = database.check_stock(item1["name"])
    new_stock = updated_items[0]["stock_qty"]
    assert new_stock == initial_stock - 2, f"Expected {initial_stock - 2}, got {new_stock}"
    print(f"Stock correctly decremented from {initial_stock} -> {new_stock}")
    
    # 3. Test out-of-stock over-ordering
    excessive_qty = new_stock + 10
    fail_result = database.place_order_atomic(
        customer_phone="+923001234567",
        customer_name="Ali Khan",
        delivery_address="House 42, Street 7, Islamabad",
        items=[{"product_id": item1["id"], "quantity": excessive_qty}]
    )
    assert fail_result["success"] is False, "Order should have failed due to insufficient stock"
    print(f"Properly rejected over-order: {fail_result['error']}")
    
    # Verify stock remained untouched after failed order
    verify_stock = database.check_stock(item1["name"])[0]["stock_qty"]
    assert verify_stock == new_stock, "Stock should NOT change after a failed order"
    print("Database stock verification tests PASSED!")

if __name__ == "__main__":
    test_atomic_order()
