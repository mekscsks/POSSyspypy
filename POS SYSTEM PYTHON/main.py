import sys
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QFont
from database import initialize_db


def show_login(app: QApplication):
    from ui.login_dialog import LoginDialog
    from ui.main_window import MainWindow

    login = LoginDialog()
    if login.exec_():
        window = MainWindow(user=login.current_user, app=app)
        window.showMaximized()
        app._main_window = window   # prevent GC
    else:
        app.quit()


def main():
    initialize_db()
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))
    app.setStyle("Fusion")
    show_login(app)
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
