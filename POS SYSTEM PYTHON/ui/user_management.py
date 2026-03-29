import os
from PyQt5 import uic
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QDialog, QMessageBox, QTableWidgetItem
from services.user_service import get_all_users, toggle_user_active, add_user, update_user

UI_FILE = os.path.join(os.path.dirname(__file__), "user_management.ui")
USER_DLG = os.path.join(os.path.dirname(__file__), "user_dialog.ui")


class UserDialog(QDialog):
    def __init__(self, parent=None, user=None):
        super().__init__(parent)
        uic.loadUi(USER_DLG, self)
        self.user = user

        if user:
            self.lblTitle.setText("Edit User")
            self.txtUsername.setText(user["username"])
            self.txtPassword.setPlaceholderText("Leave blank to keep current password")
            idx = self.cmbRole.findText(user["role"])
            if idx >= 0:
                self.cmbRole.setCurrentIndex(idx)

        self.btnSave.clicked.connect(self._save)
        self.btnCancel.clicked.connect(self.reject)

    def _save(self):
        username = self.txtUsername.text().strip()
        password = self.txtPassword.text().strip()
        role     = self.cmbRole.currentText()

        if not username:
            QMessageBox.warning(self, "Validation", "Username is required.")
            return
        if not self.user and not password:
            QMessageBox.warning(self, "Validation", "Password is required for new users.")
            return

        try:
            if self.user:
                update_user(self.user["id"], username, password or None, role)
            else:
                add_user(username, password, role)
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))


class UserManagement(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        uic.loadUi(UI_FILE, self)
        self._setup_table()
        self._load_users()
        self.btnAddUser.clicked.connect(self._add_user)
        self.btnEditUser.clicked.connect(self._edit_user)
        self.btnToggleActive.clicked.connect(self._toggle_active)
        self.btnClose.clicked.connect(self.accept)

    def _setup_table(self):
        self.tblUsers.verticalHeader().setVisible(False)
        self.tblUsers.horizontalHeader().setStretchLastSection(True)
        for i, w in enumerate([40, 160, 100, 80]):
            self.tblUsers.setColumnWidth(i, w)

    def _load_users(self):
        users = get_all_users()
        self.tblUsers.setRowCount(0)
        role_colors = {"admin": "#e8f5e9", "it": "#e3f2fd", "cashier": "#fff8e1"}
        for row, u in enumerate(users):
            self.tblUsers.insertRow(row)
            values = [
                str(u["id"]), u["username"], u["role"].upper(),
                "Active" if u["is_active"] else "Inactive",
                u["created_at"][:10],
            ]
            for col, val in enumerate(values):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
                if col == 0:
                    item.setData(Qt.UserRole, u["id"])
                bg = role_colors.get(u["role"], "#ffffff")
                item.setBackground(QColor(bg))
                if not u["is_active"]:
                    item.setForeground(QColor("#aaa"))
                self.tblUsers.setItem(row, col, item)

    def _get_selected_user_id(self):
        row = self.tblUsers.currentRow()
        if row < 0:
            QMessageBox.information(self, "Select User", "Please select a user.")
            return None
        return self.tblUsers.item(row, 0).data(Qt.UserRole)

    def _get_selected_user_row(self):
        row = self.tblUsers.currentRow()
        if row < 0:
            return None
        return {
            "id":        self.tblUsers.item(row, 0).data(Qt.UserRole),
            "username":  self.tblUsers.item(row, 1).text(),
            "role":      self.tblUsers.item(row, 2).text().lower(),
            "is_active": self.tblUsers.item(row, 3).text() == "Active",
        }

    def _add_user(self):
        dlg = UserDialog(self)
        if dlg.exec_():
            self._load_users()

    def _edit_user(self):
        user = self._get_selected_user_row()
        if not user:
            return
        dlg = UserDialog(self, user=user)
        if dlg.exec_():
            self._load_users()

    def _toggle_active(self):
        user = self._get_selected_user_row()
        if not user:
            return
        new_state = not user["is_active"]
        action = "enable" if new_state else "disable"
        if QMessageBox.question(
            self, "Confirm", f"{action.capitalize()} user '{user['username']}'?",
            QMessageBox.Yes | QMessageBox.No
        ) == QMessageBox.Yes:
            try:
                toggle_user_active(user["id"], new_state)
                self._load_users()
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))
