"""Payment business logic separated from HTTP layer."""

from typing import List, Tuple

from sqlalchemy.orm import Session

from app.models import (
    CashDesk,
    CashDeskProduct,
    Product,
)


class PaymentError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def calculate_order_total(
    db: Session, cash_desk_login: str, items: List[dict]
) -> Tuple[int, list]:
    desk = db.query(CashDesk).filter(CashDesk.login == cash_desk_login).first()
    if not desk:
        raise PaymentError("Касса не найдена")
    total_kop = 0
    detailed_items = []
    for item in items:
        mapping = db.query(CashDeskProduct).filter(
            CashDeskProduct.product_id == item["product_id"],
            CashDeskProduct.cash_desk_id == desk.id,
        ).first()
        product = db.query(Product).filter(Product.id == item["product_id"]).first()
        if not product:
            continue
        price = mapping.price if mapping else product.price
        total_kop += price * item["quantity"] * 100
        detailed_items.append({"name": product.name, "price": price, "qty": item["quantity"]})
    return int(total_kop), detailed_items
