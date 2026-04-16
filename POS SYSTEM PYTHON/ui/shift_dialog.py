import os
from PyQt5 import uic
from PyQt5.QtWidgets import QDialog, QMessageBox
from database import get_connection
from services.shift_service import (
    get_open_session, start_shift, end_shift,
    add_cash_adjustment, get_shift_report,
)

UI_FILE = os.path.join(os.path.dirname(__file__), "shift_dialog.ui")


class ShiftDialog(QDialog):
    """
    Single dialog that handles the full shift lifecycle:
      Page 0 — Start Shift   (no open session)
      Page 1 — Active Shift  (session open: cash adjustments)
      Page 2 — End Shift     (confirm closing cash + summary)
    """

    def __init__(self, parent=None, user: dict = None):
        super().__init__(parent)
        uic.loadUi(UI_FILE, self)
        self.user    = user
        self.session = None          # current open session dict

        self._connect_signals()
        self._refresh()

    # ── Signals ────────────────────────────────────────────────────────────────

    def _connect_signals(self):
        self.btnStartShift.clicked.connect(self._start_shift)
        self.btnAddAdjustment.clicked.connect(self._add_adjustment)
        self.btnGoEndShift.clicked.connect(self._go_end_page)
        self.btnBackToActive.clicked.connect(lambda: self.stackedWidget.setCurrentIndex(1))
        self.btnConfirmEnd.clicked.connect(self._confirm_end_shift)
        self.btnClose.clicked.connect(self.accept)

    # ── State refresh ──────────────────────────────────────────────────────────

    def _refresh(self):
        """Reload session state and update UI accordingly."""
        self.session = get_open_session(self.user["id"]) if self.user else None

        if self.session:
            self._show_active_page()
        else:
            self.stackedWidget.setCurrentIndex(0)
            self.lblStatus.setText("⚪  No active shift — open one to start selling.")
            self.lblStatus.setStyleSheet(
                "background:#fff3e0;color:#e65100;border-radius:5px;"
                "padding:8px;font-weight:bold;font-size:12px;"
            )

    def _show_active_page(self):
        self.stackedWidget.setCurrentIndex(1)
        s = self.session

        # Status banner
        self.lblStatus.setText(
            f"🟢  Shift #{s['id']} open since {s['opened_at'][:16].replace('T', ' ')}"
        )
        self.lblStatus.setStyleSheet(
            "background:#e8f5e9;color:#2e7d32;border-radius:5px;"
            "padding:8px;font-weight:bold;font-size:12px;"
        )

        # Session info
        self.lblSessionInfo.setText(
            f"Session #{s['id']}  |  Opening cash: ₱{s['opening_cash']:,.2f}"
        )

        # Live sales total for this session
        with get_connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as cnt, COALESCE(SUM(total),0) as tot"
                " FROM sales WHERE session_id=?",
                (s["id"],),
            ).fetchone()
        self.lblSessionSales.setText(
            f"Sales this shift: ₱{row['tot']:,.2f}  ({row['cnt']} transaction(s))"
        )

    # ── Start Shift ────────────────────────────────────────────────────────────

    def _start_shift(self):
        opening_cash = self.spinOpeningCash.value()
        notes        = self.txtStartNotes.toPlainText().strip()
        try:
            self.session = start_shift(self.user["id"], opening_cash, notes)
            self._refresh()
        except ValueError as e:
            QMessageBox.warning(self, "Cannot Open Shift", str(e))

    # ── Cash Adjustment ────────────────────────────────────────────────────────

    def _add_adjustment(self):
        if not self.session:
            QMessageBox.warning(self, "No Active Shift", "Open a shift first.")
            return

        adj_type = "cash_in" if self.cmbAdjType.currentIndex() == 0 else "cash_out"
        amount   = self.spinAdjAmount.value()
        reason   = self.txtAdjReason.text().strip()

        try:
            add_cash_adjustment(self.session["id"], adj_type, amount, reason)
            self.spinAdjAmount.setValue(0.00)
            self.txtAdjReason.clear()
            self._show_active_page()   # refresh sales total
            QMessageBox.information(
                self, "Adjustment Recorded",
                f"{'Cash In' if adj_type == 'cash_in' else 'Cash Out'} "
                f"₱{amount:,.2f} recorded."
            )
        except ValueError as e:
            QMessageBox.warning(self, "Adjustment Error", str(e))

    # ── End Shift — page navigation ────────────────────────────────────────────

    def _go_end_page(self):
        if not self.session:
            return
        s = self.session

        # Build summary text before user enters closing cash
        with get_connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as cnt, COALESCE(SUM(total),0) as tot"
                " FROM sales WHERE session_id=?",
                (s["id"],),
            ).fetchone()
            cash_in = conn.execute(
                "SELECT COALESCE(SUM(amount),0) FROM cash_adjustments"
                " WHERE session_id=? AND type='cash_in'", (s["id"],)
            ).fetchone()[0]
            cash_out = conn.execute(
                "SELECT COALESCE(SUM(amount),0) FROM cash_adjustments"
                " WHERE session_id=? AND type='cash_out'", (s["id"],)
            ).fetchone()[0]

        expected = round(s["opening_cash"] + row["tot"] + cash_in - cash_out, 2)

        self.lblEndDetails.setText(
            f"Opening Cash :  ₱{s['opening_cash']:>10,.2f}\n"
            f"Sales Total  :  ₱{row['tot']:>10,.2f}  ({row['cnt']} txn)\n"
            f"Cash In      :  ₱{cash_in:>10,.2f}\n"
            f"Cash Out     :  ₱{cash_out:>10,.2f}\n"
            f"─────────────────────────────\n"
            f"Expected Cash:  ₱{expected:>10,.2f}"
        )
        self.spinClosingCash.setValue(expected)   # pre-fill as convenience
        self.stackedWidget.setCurrentIndex(2)

    # ── End Shift — confirm ────────────────────────────────────────────────────

    def _confirm_end_shift(self):
        if not self.session:
            return

        closing_cash = self.spinClosingCash.value()
        notes        = self.txtEndNotes.toPlainText().strip()

        confirm = QMessageBox.question(
            self, "Confirm End Shift",
            f"Close shift with ₱{closing_cash:,.2f} actual cash?\n"
            "This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return

        try:
            closed = end_shift(self.session["id"], closing_cash, notes)
            self.session = None
            self._show_report_summary(closed)
            self._refresh()
        except ValueError as e:
            QMessageBox.warning(self, "End Shift Error", str(e))

    def _show_report_summary(self, closed: dict):
        disc = closed["discrepancy"]
        sign = "+" if disc >= 0 else ""
        color = "#2e7d32" if disc == 0 else ("#e65100" if abs(disc) > 0 else "#1565c0")

        msg = (
            f"✅  Shift #{closed['id']} Closed\n\n"
            f"Opening Cash :  ₱{closed['opening_cash']:,.2f}\n"
            f"Expected Cash:  ₱{closed['expected_cash']:,.2f}\n"
            f"Actual Cash  :  ₱{closed['closing_cash']:,.2f}\n"
            f"Discrepancy  :  {sign}₱{abs(disc):,.2f}"
        )
        QMessageBox.information(self, "Shift Closed", msg)
