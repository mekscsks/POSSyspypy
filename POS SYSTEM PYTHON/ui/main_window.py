import os
import csv
from datetime import datetime

from PyQt5 import uic
from PyQt5.QtCore import Qt, QTimer, QDate
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QMainWindow, QMessageBox, QTableWidgetItem,
    QFileDialog, QApplication
)

from pos_logic import Cart
from services.inventory_service import (
    get_all_products, get_available_products, get_low_stock_products,
    deactivate_product, get_product_by_id
)
from services.sales_service import (
    checkout, get_sales_history, get_sale_items, get_daily_summary
)
from services.user_service import has_permission
from services.shift_service import get_open_session
from ui.product_dialog import ProductDialog
from ui.restock_dialog import RestockDialog
from ui.user_management import UserManagement
from ui.shift_dialog import ShiftDialog
from utils import format_currency

UI_FILE = os.path.join(os.path.dirname(__file__), "main_window.ui")


class MainWindow(QMainWindow):
    def __init__(self, user: dict, app=None):
        super().__init__()
        uic.loadUi(UI_FILE, self)
        self.user = user  # dict: id, username, role
        self._app  = app
        self.cart  = Cart()

        self._setup_tables()
        self._connect_signals()
        self._apply_permissions()
        self._start_clock()
        self._load_products()
        self._load_inventory()
        self._load_sales()
        self._update_today_summary()
        self._init_date_filters()
        self._refresh_shift_state()

        role_label = self.user["role"].upper()
        self.lblLoggedIn.setText(f"👤  {self.user['username']}  [{role_label}]")

    # ── Setup ──────────────────────────────────────────────────────────────

    def _setup_tables(self):
        for tbl, cols in [
            (self.tblProducts,  [180, 130, 80, 70, 60]),
            (self.tblCart,      [160, 60, 80, 80]),
            (self.tblInventory, [40, 180, 130, 80, 70, 60, 70]),
            (self.tblSales,     [110, 90, 90, 90, 160]),
            (self.tblSaleItems, [180, 70, 90, 90]),
        ]:
            tbl.horizontalHeader().setStretchLastSection(True)
            tbl.verticalHeader().setVisible(False)
            tbl.setShowGrid(True)
            for i, w in enumerate(cols[:-1]):
                tbl.setColumnWidth(i, w)

    def _connect_signals(self):
        # POS
        self.txtSearch.textChanged.connect(self._load_products)
        self.btnClearSearch.clicked.connect(self.txtSearch.clear)
        self.txtBarcode.returnPressed.connect(self._barcode_add)
        self.btnAddToCart.clicked.connect(self._add_selected_to_cart)
        self.tblProducts.doubleClicked.connect(self._add_selected_to_cart)
        self.btnRemoveItem.clicked.connect(self._remove_cart_item)
        self.btnClearCart.clicked.connect(self._clear_cart)
        self.txtPayment.textChanged.connect(self._update_change)
        self.btnCheckout.clicked.connect(self._checkout)
        self.btnLowStock.clicked.connect(self._show_low_stock)
        # Inventory
        self.txtInvSearch.textChanged.connect(self._load_inventory)
        self.btnAddProduct.clicked.connect(self._add_product)
        self.btnEditProduct.clicked.connect(self._edit_product)
        self.btnRestock.clicked.connect(self._restock_product)
        self.btnDeactivate.clicked.connect(self._deactivate_product)
        # Reports
        self.btnFilterSales.clicked.connect(self._load_sales)
        self.btnExportCSV.clicked.connect(self._export_csv)
        self.tblSales.itemSelectionChanged.connect(self._load_sale_items)
        # Top bar
        self.btnUsers.clicked.connect(self._open_user_management)
        self.btnLogout.clicked.connect(self._logout)
        self.btnShift.clicked.connect(self._open_shift_dialog)

    def _apply_permissions(self):
        role = self.user["role"]

        # Inventory manage buttons — cashier cannot use
        can_manage = has_permission(role, "inventory_manage")
        for btn in [self.btnAddProduct, self.btnEditProduct,
                    self.btnRestock, self.btnDeactivate]:
            btn.setVisible(can_manage)

        # Reports tab — cashier cannot see
        can_reports = has_permission(role, "reports")
        self.tabWidget.setTabVisible(2, can_reports)

        # Export CSV
        self.btnExportCSV.setVisible(has_permission(role, "export"))

        # Users button
        self.btnUsers.setVisible(has_permission(role, "users"))

    def _start_clock(self):
        self._tick()
        timer = QTimer(self)
        timer.timeout.connect(self._tick)
        timer.start(1000)

    def _tick(self):
        self.lblDateTime.setText(
            datetime.now().strftime("%A, %B %d %Y   %I:%M:%S %p")
        )

    def _init_date_filters(self):
        today = QDate.currentDate()
        self.dateFrom.setDate(today.addDays(-30))
        self.dateTo.setDate(today)

    # ── Products ───────────────────────────────────────────────────────────

    def _load_products(self):
        products = get_available_products(self.txtSearch.text().strip())
        self.tblProducts.setRowCount(0)
        for row, p in enumerate(products):
            self.tblProducts.insertRow(row)
            self._set_row(self.tblProducts, row, [
                p["name"], p["barcode"],
                f"₱{p['price']:,.2f}", f"{p['stock']}", p["unit"],
            ], data=p["id"])
            if p["stock"] <= 10:
                self._highlight_row(self.tblProducts, row, "#fff3e0")

    # ── Cart ───────────────────────────────────────────────────────────────

    def _barcode_add(self):
        barcode = self.txtBarcode.text().strip()
        if not barcode:
            self._add_selected_to_cart()
            return
        try:
            self.cart.add_by_barcode(barcode, self.spinQty.value())
            self.txtBarcode.clear()
            self._refresh_cart()
        except ValueError as e:
            QMessageBox.warning(self, "Cannot Add", str(e))
        self.txtBarcode.setFocus()

    def _add_selected_to_cart(self):
        row = self.tblProducts.currentRow()
        if row < 0:
            QMessageBox.information(self, "Select Product", "Please select a product first.")
            return
        product_id = self.tblProducts.item(row, 0).data(Qt.UserRole)
        try:
            self.cart.add_item(product_id, self.spinQty.value())
            self._refresh_cart()
        except ValueError as e:
            QMessageBox.warning(self, "Cannot Add", str(e))
        self.txtBarcode.setFocus()

    def _refresh_cart(self):
        self.tblCart.setRowCount(0)
        for row, item in enumerate(self.cart.get_items()):
            self.tblCart.insertRow(row)
            qty_str = f"{item['quantity']:.3f}".rstrip("0").rstrip(".")
            self._set_row(self.tblCart, row, [
                item["name"],
                f"{qty_str} {item['unit']}",
                f"₱{item['price']:,.2f}",
                f"₱{item['subtotal']:,.2f}",
            ], data=item["product_id"])
        self.lblTotal.setText(format_currency(self.cart.get_total()))
        self._update_change()

    def _remove_cart_item(self):
        row = self.tblCart.currentRow()
        if row < 0:
            return
        self.cart.remove_item(self.tblCart.item(row, 0).data(Qt.UserRole))
        self._refresh_cart()

    def _clear_cart(self):
        if self.cart.is_empty():
            return
        if QMessageBox.question(self, "Clear Cart", "Clear all items?",
                                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self.cart.clear()
            self._refresh_cart()

    def _update_change(self):
        try:
            payment = float(self.txtPayment.text() or 0)
            change  = payment - self.cart.get_total()
            self.lblChange.setText(format_currency(max(change, 0)))
            color = "#1565c0" if change >= 0 else "#c62828"
            self.lblChange.setStyleSheet(
                f"font-size:16px;font-weight:bold;color:{color};"
            )
        except ValueError:
            self.lblChange.setText("₱0.00")

    # ── Checkout ───────────────────────────────────────────────────────────

    def _checkout(self):
        if self.cart.is_empty():
            QMessageBox.warning(self, "Empty Cart", "Add items to cart first.")
            return

        # Enforce active shift before any transaction
        session = get_open_session(self.user["id"])
        if not session:
            QMessageBox.warning(
                self, "No Active Shift",
                "You must open a shift before processing transactions.\n"
                "Click the 'Shift' button in the top bar."
            )
            return

        try:
            payment = float(self.txtPayment.text())
        except ValueError:
            QMessageBox.warning(self, "Invalid Payment", "Enter a valid payment amount.")
            return
        try:
            result = checkout(
                self.cart.get_items(), payment,
                self.user["id"], session["id"]
            )
            self.cart.clear()
            self._refresh_cart()
            self.txtPayment.clear()
            self._load_products()
            self._load_inventory()
            self._update_today_summary()
            self._refresh_shift_state()
            QMessageBox.information(
                self, "✔ Checkout Complete",
                f"Receipt No : {result['receipt_no']}\n"
                f"Total      : {format_currency(result['total'])}\n"
                f"Payment    : {format_currency(result['payment'])}\n"
                f"Change     : {format_currency(result['change'])}\n\n"
                f"Receipt saved:\n{result['receipt_path']}"
            )
            self.txtBarcode.setFocus()
        except ValueError as e:
            QMessageBox.warning(self, "Checkout Error", str(e))
        except Exception as e:
            QMessageBox.critical(self, "Transaction Failed", f"Rolled back.\n{e}")

    def _update_today_summary(self):
        s = get_daily_summary()
        self.lblTodaySummary.setText(
            f"Today: {s['txn_count']} transaction(s)  |  {format_currency(s['total_sales'])}"
        )

    # ── Low Stock ──────────────────────────────────────────────────────────

    def _show_low_stock(self):
        items = get_low_stock_products()
        if not items:
            QMessageBox.information(self, "Low Stock", "All products have sufficient stock.")
            return
        msg = "\n".join(f"• {p['name']} — {p['stock']} {p['unit']}" for p in items)
        QMessageBox.warning(self, f"⚠ Low Stock ({len(items)} items)", msg)

    # ── Inventory ──────────────────────────────────────────────────────────

    def _load_inventory(self):
        search = self.txtInvSearch.text().strip()
        self.tblInventory.setRowCount(0)
        for row, p in enumerate(get_all_products(search)):
            self.tblInventory.insertRow(row)
            self._set_row(self.tblInventory, row, [
                str(p["id"]), p["name"], p["barcode"],
                f"₱{p['price']:,.2f}", f"{p['stock']}", p["unit"],
                "Active" if p["is_active"] else "Inactive",
            ], data=p["id"])
            if p["stock"] <= 10:
                self._highlight_row(self.tblInventory, row, "#fff3e0")

    def _get_selected_inv_id(self):
        row = self.tblInventory.currentRow()
        if row < 0:
            QMessageBox.information(self, "Select Product", "Please select a product.")
            return None
        return self.tblInventory.item(row, 0).data(Qt.UserRole)

    def _add_product(self):
        if dlg := ProductDialog(self):
            if dlg.exec_():
                self._load_inventory()
                self._load_products()

    def _edit_product(self):
        pid = self._get_selected_inv_id()
        if pid is None:
            return
        dlg = ProductDialog(self, product=get_product_by_id(pid))
        if dlg.exec_():
            self._load_inventory()
            self._load_products()

    def _restock_product(self):
        pid = self._get_selected_inv_id()
        if pid is None:
            return
        dlg = RestockDialog(self, product=get_product_by_id(pid))
        if dlg.exec_():
            self._load_inventory()
            self._load_products()

    def _deactivate_product(self):
        pid = self._get_selected_inv_id()
        if pid is None:
            return
        row  = self.tblInventory.currentRow()
        name = self.tblInventory.item(row, 1).text()
        if QMessageBox.question(
            self, "Deactivate", f"Deactivate '{name}'?",
            QMessageBox.Yes | QMessageBox.No
        ) == QMessageBox.Yes:
            try:
                deactivate_product(pid)
                self._load_inventory()
                self._load_products()
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    # ── Reports ────────────────────────────────────────────────────────────

    def _load_sales(self):
        date_from = self.dateFrom.date().toString("yyyy-MM-dd")
        date_to   = self.dateTo.date().toString("yyyy-MM-dd")
        sales     = get_sales_history(date_from, date_to)
        self.tblSales.setRowCount(0)
        total_sum = 0.0
        for row, s in enumerate(sales):
            self.tblSales.insertRow(row)
            self._set_row(self.tblSales, row, [
                s["receipt_no"],
                f"₱{s['total']:,.2f}",
                f"₱{s['payment']:,.2f}",
                f"₱{s['change']:,.2f}",
                s["created_at"][:19].replace("T", " "),
            ], data=s["id"])
            total_sum += s["total"]
        self.lblReportSummary.setText(
            f"{len(sales)} transaction(s)  |  Total: {format_currency(total_sum)}"
        )
        self.tblSaleItems.setRowCount(0)
        self.lblSaleDetail.setText("Click a sale to view items.")

    def _load_sale_items(self):
        row = self.tblSales.currentRow()
        if row < 0:
            return
        sale_id = self.tblSales.item(row, 0).data(Qt.UserRole)
        self.tblSaleItems.setRowCount(0)
        for r, item in enumerate(get_sale_items(sale_id)):
            self.tblSaleItems.insertRow(r)
            qty_str = f"{item['quantity']:.3f}".rstrip("0").rstrip(".")
            self._set_row(self.tblSaleItems, r, [
                item["name"],
                f"{qty_str} {item['unit']}",
                f"₱{item['price']:,.2f}",
                f"₱{round(item['quantity'] * item['price'], 2):,.2f}",
            ])
        self.lblSaleDetail.setText(
            f"Items for Receipt: {self.tblSales.item(row, 0).text()}"
        )

    def _export_csv(self):
        date_from = self.dateFrom.date().toString("yyyy-MM-dd")
        date_to   = self.dateTo.date().toString("yyyy-MM-dd")
        sales     = get_sales_history(date_from, date_to)
        if not sales:
            QMessageBox.information(self, "Export", "No sales data to export.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save CSV", f"sales_{date_from}_{date_to}.csv", "CSV Files (*.csv)"
        )
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Receipt No", "Total", "Payment", "Change", "Date"])
                for s in sales:
                    writer.writerow([
                        s["receipt_no"], s["total"], s["payment"],
                        s["change"], s["created_at"][:19].replace("T", " ")
                    ])
            QMessageBox.information(self, "Export", f"Exported to:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", str(e))

    # ── Shift ──────────────────────────────────────────────────────────────

    def _open_shift_dialog(self):
        dlg = ShiftDialog(self, user=self.user)
        dlg.exec_()
        self._refresh_shift_state()

    def _refresh_shift_state(self):
        """Update top-bar shift button and block checkout when no shift is open."""
        session = get_open_session(self.user["id"])
        if session:
            self.btnShift.setText("🟢 Shift Open")
            self.btnShift.setStyleSheet(
                "QPushButton{background:#2e7d32;color:white;border:none;"
                "padding:6px 14px;border-radius:4px;font-weight:bold;}"
                "QPushButton:hover{background:#1b5e20;}"
            )
            self.btnCheckout.setEnabled(True)
        else:
            self.btnShift.setText("⚪ Open Shift")
            self.btnShift.setStyleSheet(
                "QPushButton{background:#f57f17;color:white;border:none;"
                "padding:6px 14px;border-radius:4px;font-weight:bold;}"
                "QPushButton:hover{background:#e65100;}"
            )
            self.btnCheckout.setEnabled(False)

    # ── User Management ────────────────────────────────────────────────────

    def _open_user_management(self):
        UserManagement(self).exec_()

    # ── Logout ─────────────────────────────────────────────────────────────

    def _logout(self):
        if QMessageBox.question(
            self, "Logout", f"Logout as '{self.user['username']}'?",
            QMessageBox.Yes | QMessageBox.No
        ) == QMessageBox.Yes:
            self.close()
            from main import show_login
            show_login(self._app or QApplication.instance())

    # ── Helpers ────────────────────────────────────────────────────────────

    def _set_row(self, table, row, values, data=None):
        for col, val in enumerate(values):
            item = QTableWidgetItem(str(val))
            item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
            if col == 0 and data is not None:
                item.setData(Qt.UserRole, data)
            table.setItem(row, col, item)

    def _highlight_row(self, table, row, color):
        for col in range(table.columnCount()):
            item = table.item(row, col)
            if item:
                item.setBackground(QColor(color))
