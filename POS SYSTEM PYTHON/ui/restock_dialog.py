import os
from PyQt5 import uic
from PyQt5.QtWidgets import QDialog, QMessageBox
from services.inventory_service import restock_product

UI_FILE = os.path.join(os.path.dirname(__file__), "restock_dialog.ui")


class RestockDialog(QDialog):
    def __init__(self, parent=None, product=None):
        super().__init__(parent)
        uic.loadUi(UI_FILE, self)
        self.product = product

        if product:
            self.lblProductName.setText(product["name"])
            self.lblCurrentStock.setText(f"{product['stock']} {product['unit']}")

        self.btnConfirm.clicked.connect(self._confirm)
        self.btnCancel.clicked.connect(self.reject)

    def _confirm(self):
        qty = self.spinQty.value()
        if qty <= 0:
            QMessageBox.warning(self, "Validation", "Quantity must be greater than zero.")
            return
        try:
            restock_product(self.product["id"], qty)
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
