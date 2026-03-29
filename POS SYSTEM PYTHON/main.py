import sys
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QFont
from database import initialize_db

app = None


def show_login():
    from ui.login_dialog import LoginDialog
    from ui.main_window import MainWindow

    login = LoginDialog()
    if login.exec_():
        window = MainWindow(user=login.current_user)
        window.showMaximized()
        # keep reference so it doesn't get garbage collected
        show_login._window = window
    else:
        # user closed login dialog — exit app
        QApplication.quit()


def main():
    global app
    initialize_db()
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))
    app.setStyle("Fusion")
    show_login()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
