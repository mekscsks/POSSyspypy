import os
from PyQt5 import uic
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDialog
from services.user_service import login

UI_FILE = os.path.join(os.path.dirname(__file__), "login_dialog.ui")


class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        uic.loadUi(UI_FILE, self)
        self.setWindowFlags(Qt.Window | Qt.WindowCloseButtonHint)
        self.current_user = None
        self.btnLogin.clicked.connect(self._login)
        self.txtPassword.returnPressed.connect(self._login)
        self.txtUsername.returnPressed.connect(lambda: self.txtPassword.setFocus())

    def _login(self):
        username = self.txtUsername.text().strip()
        password = self.txtPassword.text()

        if not username or not password:
            self.lblError.setText("Please enter username and password.")
            return

        user = login(username, password)
        if user:
            self.current_user = dict(user)
            self.accept()
        else:
            self.lblError.setText("Invalid username or password.")
            self.txtPassword.clear()
            self.txtPassword.setFocus()
