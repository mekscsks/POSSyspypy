from services.inventory_service import get_product_by_barcode, get_product_by_id


class Cart:
    def __init__(self):
        self._items = {}  # product_id -> item dict

    def add_item(self, product_id, quantity=1.0):
        product = get_product_by_id(product_id)
        if not product or not product["is_active"]:
            raise ValueError("Product not found or inactive.")
        qty = float(quantity)
        if qty <= 0:
            raise ValueError("Quantity must be greater than zero.")
        current = self._items.get(product_id, {}).get("quantity", 0.0)
        if current + qty > product["stock"]:
            raise ValueError(f"Insufficient stock. Available: {product['stock']} {product['unit']}")
        if product_id in self._items:
            self._items[product_id]["quantity"] = current + qty
            self._items[product_id]["subtotal"] = round((current + qty) * product["price"], 2)
        else:
            self._items[product_id] = {
                "product_id": product_id,
                "name": product["name"],
                "barcode": product["barcode"],
                "quantity": qty,
                "price": product["price"],
                "unit": product["unit"],
                "subtotal": round(qty * product["price"], 2),
            }

    def add_by_barcode(self, barcode, quantity=1.0):
        product = get_product_by_barcode(barcode)
        if not product:
            raise ValueError(f"No product found for barcode: {barcode}")
        self.add_item(product["id"], quantity)
        return product

    def remove_item(self, product_id):
        self._items.pop(product_id, None)

    def update_quantity(self, product_id, quantity):
        qty = float(quantity)
        if qty <= 0:
            self.remove_item(product_id)
            return
        product = get_product_by_id(product_id)
        if product and qty > product["stock"]:
            raise ValueError(f"Insufficient stock. Available: {product['stock']} {product['unit']}")
        if product_id in self._items:
            self._items[product_id]["quantity"] = qty
            self._items[product_id]["subtotal"] = round(qty * self._items[product_id]["price"], 2)

    def clear(self):
        self._items.clear()

    def get_items(self):
        return list(self._items.values())

    def get_total(self):
        return round(sum(i["subtotal"] for i in self._items.values()), 2)

    def is_empty(self):
        return not self._items
