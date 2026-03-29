import os
from PyQt5 import uic
from PyQt5.QtWidgets import QDialog, QMessageBox
from services.inventory_service import add_product, update_product

UI_FILE = os.path.join(os.path.dirname(__file__), "product_dialog.ui")


class ProductDialog(QDialog):
    def __init__(self, parent=None, product=None):
        super().__init__(parent)
        uic.loadUi(UI_FILE, self)
        self.product = product

        if product:
            self.lblTitle.setText("Edit Product")
            self.txtName.setText(product["name"])
            self.txtBarcode.setText(product["barcode"])
            self.spinPrice.setValue(product["price"])
            self.spinStock.setValue(product["stock"])
            idx = self.cmbUnit.findText(product["unit"])
            if idx >= 0:
                self.cmbUnit.setCurrentIndex(idx)

        self.btnSave.clicked.connect(self._save)
        self.btnCancel.clicked.connect(self.reject)

    def _save(self):
        name    = self.txtName.text().strip()
        barcode = self.txtBarcode.text().strip()
        price   = self.spinPrice.value()
        stock   = self.spinStock.value()
        unit    = self.cmbUnit.currentText()

        if not name or not barcode:
            QMessageBox.warning(self, "Validation", "Name and Barcode are required.")
            return

        try:
            if self.product:
                update_product(self.product["id"], name, barcode, price, stock, unit)
            else:
                add_product(name, barcode, price, stock, unit)
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
