import sys
import socket
import os
import re
from PyQt6 import QtWidgets, QtGui, QtCore


def receive_all(sock):
    """Lit tous les octets disponibles depuis la socket."""
    data = b""
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            break
        data += chunk
    return data.decode('utf-8')


# ---- Coloration syntaxique Python (exemple) ----
class PythonHighlighter(QtGui.QSyntaxHighlighter):
    """Highlighter simple pour le Python."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.rules = []

        keyword_format = QtGui.QTextCharFormat()
        keyword_format.setForeground(QtGui.QColor("blue"))
        keywords = ["def", "class", "import", "from", "if", "else", "elif", "for", "while", "return", "print"]
        for kw in keywords:
            pattern = r"\b" + kw + r"\b"
            self.rules.append((re.compile(pattern), keyword_format))

        string_format = QtGui.QTextCharFormat()
        string_format.setForeground(QtGui.QColor("darkred"))
        self.rules.append((re.compile(r'".*?"'), string_format))
        self.rules.append((re.compile(r"'.*?'"), string_format))

    def highlightBlock(self, text):
        for pattern, fmt in self.rules:
            for m in pattern.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)


# ---- Zone de numérotation des lignes ----
class LineNumberArea(QtWidgets.QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QtCore.QSize(self.editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.editor.lineNumberAreaPaintEvent(event)


class CodeEditor(QtWidgets.QPlainTextEdit):
    """Éditeur de code avec numérotation de lignes et highlight des parenthèses."""
    def __init__(self):
        super().__init__()
        self.lineNumberArea = LineNumberArea(self)
        self.blockCountChanged.connect(self.updateLineNumberAreaWidth)
        self.updateRequest.connect(self.updateLineNumberArea)
        self.cursorPositionChanged.connect(self.highlightCurrentLine)
        self.updateLineNumberAreaWidth(0)
        self.parenthesis_highlight_format = QtGui.QTextCharFormat()
        self.parenthesis_highlight_format.setBackground(QtGui.QColor("#d0d0ff"))

    def line_number_area_width(self):
        digits = len(str(self.blockCount()))
        return 3 + self.fontMetrics().horizontalAdvance('9') * digits

    def updateLineNumberAreaWidth(self, _):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def updateLineNumberArea(self, rect, dy):
        if dy:
            self.lineNumberArea.scroll(0, dy)
        else:
            self.lineNumberArea.update(0, rect.y(), self.lineNumberArea.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self.updateLineNumberAreaWidth(0)

    def lineNumberAreaPaintEvent(self, event):
        painter = QtGui.QPainter(self.lineNumberArea)
        painter.fillRect(event.rect(), QtGui.QColor("#f0f0f0"))

        block = self.firstVisibleBlock()
        blockNumber = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(blockNumber + 1)
                painter.setPen(QtGui.QColor("black"))
                painter.drawText(0, top, self.lineNumberArea.width(),
                                 self.fontMetrics().height(),
                                 QtCore.Qt.AlignmentFlag.AlignRight, number)
            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            blockNumber += 1

    def highlightCurrentLine(self):
        """Surligne la ligne courante et les parenthèses correspondantes."""
        extraSelections = []
        selection = QtWidgets.QTextEdit.ExtraSelection()
        lineColor = QtGui.QColor("#e0f0ff")
        selection.format.setBackground(lineColor)
        selection.format.setProperty(QtGui.QTextFormat.Property.FullWidthSelection, True)
        selection.cursor = self.textCursor()
        selection.cursor.clearSelection()
        extraSelections.append(selection)

        self.highlightMatchingParentheses(extraSelections)
        self.setExtraSelections(extraSelections)

    def highlightMatchingParentheses(self, extraSelections):
        """Recherche les parenthèses correspondantes."""
        cursor = self.textCursor()
        block = cursor.block()
        text = block.text()
        pos = cursor.positionInBlock()

        if pos > 0 <= len(text):
            char = text[pos - 1]
            if char in ")]":
                match_char = "(" if char == ")" else "["
                direction = -1
                balance = 0
                index = pos - 1
                while 0 <= index < len(text):
                    c = text[index]
                    if c == char:
                        balance += 1
                    elif c == match_char:
                        balance -= 1
                    if balance == 0 and c == match_char:
                        sel = QtWidgets.QTextEdit.ExtraSelection()
                        sel.format = self.parenthesis_highlight_format
                        sel.cursor = self.textCursor()
                        sel.cursor.setPosition(cursor.block().position() + index)
                        sel.cursor.movePosition(QtGui.QTextCursor.MoveOperation.NextCharacter,
                                                QtGui.QTextCursor.MoveMode.KeepAnchor)
                        extraSelections.append(sel)

                        sel2 = QtWidgets.QTextEdit.ExtraSelection()
                        sel2.format = self.parenthesis_highlight_format
                        sel2.cursor = self.textCursor()
                        sel2.cursor.setPosition(cursor.position() - 1)
                        sel2.cursor.movePosition(QtGui.QTextCursor.MoveOperation.NextCharacter,
                                                 QtGui.QTextCursor.MoveMode.KeepAnchor)
                        extraSelections.append(sel2)
                        break
                    index += (direction * -1)


class ClientWindow(QtWidgets.QMainWindow):
    """Fenêtre principale du client IDE."""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Client IDE")
        self.setGeometry(100, 100, 1000, 700)

        # Variables internes
        self.code_history = []
        self.current_file = None
        self.is_dark_theme = False

        # Adresse des esclaves (à adapter si besoin)
        self.slaves = [
            ('127.0.0.1', 6000)
        ]

        # Widgets (zone de configuration)
        ip_label = QtWidgets.QLabel("IP du serveur :")
        self.ip_edit = QtWidgets.QLineEdit("127.0.0.1")

        port_label = QtWidgets.QLabel("Port :")
        self.port_edit = QtWidgets.QLineEdit("5000")

        language_label = QtWidgets.QLabel("Langage :")
        self.language_combo = QtWidgets.QComboBox()
        self.language_combo.addItems(["PYTHON", "C", "C++", "JAVA"])

        # Éditeur de code
        self.code_editor = CodeEditor()
        self.highlighter = PythonHighlighter(self.code_editor.document())

        # Boutons
        self.send_button = QtWidgets.QPushButton("Envoyer")
        self.send_button.clicked.connect(self.send_code)

        self.import_button = QtWidgets.QPushButton("Importer un fichier")
        self.import_button.clicked.connect(self.import_file)

        # Zone de résultats
        self.results_display = QtWidgets.QPlainTextEdit()
        self.results_display.setReadOnly(True)

        # Barre de statut + barre de progression
        self.status_bar = QtWidgets.QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Prêt")

        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setMaximum(0)
        self.progress_bar.setVisible(False)

        # Label pour afficher la charge (optionnel, ici fictif)
        self.charge_label = QtWidgets.QLabel("Charge: Inconnue")
        self.status_bar.addPermanentWidget(self.charge_label)

        # Layouts
        top_layout = QtWidgets.QHBoxLayout()
        top_layout.addWidget(ip_label)
        top_layout.addWidget(self.ip_edit)
        top_layout.addWidget(port_label)
        top_layout.addWidget(self.port_edit)
        top_layout.addWidget(language_label)
        top_layout.addWidget(self.language_combo)
        top_layout.addWidget(self.send_button)
        top_layout.addWidget(self.import_button)

        main_layout = QtWidgets.QVBoxLayout()
        main_layout.addLayout(top_layout)
        main_layout.addWidget(QtWidgets.QLabel("Code source :"))
        main_layout.addWidget(self.code_editor)
        main_layout.addWidget(QtWidgets.QLabel("Résultats :"))
        main_layout.addWidget(self.results_display)
        main_layout.addWidget(self.progress_bar)

        container = QtWidgets.QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

        self.create_menus_and_toolbars()

    def create_menus_and_toolbars(self):
        menubar = self.menuBar()
        
        # Menu Fichier
        file_menu = menubar.addMenu("Fichier")
        open_action = QtGui.QAction("Ouvrir...", self)
        open_action.triggered.connect(self.import_file)
        file_menu.addAction(open_action)

        save_action = QtGui.QAction("Enregistrer...", self)
        save_action.triggered.connect(self.save_file)
        file_menu.addAction(save_action)

        exit_action = QtGui.QAction("Quitter", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Menu Edition
        edit_menu = menubar.addMenu("Edition")
        history_action = QtGui.QAction("Historique", self)
        history_action.triggered.connect(self.show_history)
        edit_menu.addAction(history_action)

        # Menu Affichage (Thème)
        view_menu = menubar.addMenu("Affichage")
        theme_action = QtGui.QAction("Basculer thème clair/sombre", self)
        theme_action.setCheckable(True)
        theme_action.triggered.connect(self.toggle_theme)
        view_menu.addAction(theme_action)

        # Résultats dans une fenêtre séparée
        results_action = QtGui.QAction("Ouvrir résultats dans une fenêtre", self)
        results_action.triggered.connect(self.open_results_in_window)
        view_menu.addAction(results_action)

        # Menu Réseau
        network_menu = menubar.addMenu("Réseau")
        check_conn_action = QtGui.QAction("Vérifier les connexions", self)
        check_conn_action.triggered.connect(self.check_connections)
        network_menu.addAction(check_conn_action)

        # Toolbar
        toolbar = self.addToolBar("Outils")
        toolbar.addAction(open_action)
        toolbar.addAction(save_action)
        toolbar.addAction(history_action)
        toolbar.addAction(check_conn_action)

    def check_connections(self):
        """Vérifie la connexion au serveur maître et aux esclaves."""
        server_ip = self.ip_edit.text().strip()
        server_port_str = self.port_edit.text().strip()
        try:
            server_port = int(server_port_str)
        except ValueError:
            QtWidgets.QMessageBox.warning(self, "Erreur", "Le port du serveur maître n'est pas valide.")
            return

        master_status = self.test_connection(server_ip, server_port)
        slaves_status = []
        for ip, port in self.slaves:
            status = self.test_connection(ip, port)
            slaves_status.append((ip, port, status))

        msg = f"Serveur maître ({server_ip}:{server_port}) : {'Connecté' if master_status else 'Non accessible'}\n\n"
        for (ip, port, st) in slaves_status:
            msg += f"Esclave ({ip}:{port}) : {'Connecté' if st else 'Non accessible'}\n"

        QtWidgets.QMessageBox.information(self, "Etat des connexions", msg)

    def test_connection(self, ip, port):
        """Teste la connexion à l'adresse IP et au port spécifiés."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1.0)
            s.connect((ip, port))
            s.close()
            return True
        except:
            return False

    def toggle_theme(self, checked):
        """Bascule le thème de l'interface (clair/sombre)."""
        self.is_dark_theme = checked
        if checked:
            palette = QtGui.QPalette()
            palette.setColor(QtGui.QPalette.ColorRole.Window, QtGui.QColor(53, 53, 53))
            palette.setColor(QtGui.QPalette.ColorRole.WindowText, QtCore.Qt.GlobalColor.white)
            palette.setColor(QtGui.QPalette.ColorRole.Base, QtGui.QColor(25, 25, 25))
            palette.setColor(QtGui.QPalette.ColorRole.AlternateBase, QtGui.QColor(53, 53, 53))
            palette.setColor(QtGui.QPalette.ColorRole.ToolTipBase, QtCore.Qt.GlobalColor.white)
            palette.setColor(QtGui.QPalette.ColorRole.ToolTipText, QtCore.Qt.GlobalColor.white)
            palette.setColor(QtGui.QPalette.ColorRole.Text, QtCore.Qt.GlobalColor.white)
            palette.setColor(QtGui.QPalette.ColorRole.Button, QtGui.QColor(53, 53, 53))
            palette.setColor(QtGui.QPalette.ColorRole.ButtonText, QtCore.Qt.GlobalColor.white)
            palette.setColor(QtGui.QPalette.ColorRole.BrightText, QtCore.Qt.GlobalColor.red)
            palette.setColor(QtGui.QPalette.ColorRole.Highlight, QtGui.QColor(142, 45, 197).lighter())
            palette.setColor(QtGui.QPalette.ColorRole.HighlightedText, QtCore.Qt.GlobalColor.black)
            self.setPalette(palette)
        else:
            self.setPalette(self.style().standardPalette())

    def show_history(self):
        """Affiche l'historique des codes envoyés."""
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Historique")
        layout = QtWidgets.QVBoxLayout(dialog)

        list_widget = QtWidgets.QListWidget(dialog)
        for i, code in enumerate(self.code_history):
            processed_code = code[:30].replace('\n', ' ')
            list_widget.addItem(f"Code #{i + 1} : {processed_code}...")
        layout.addWidget(list_widget)

        buttonBox = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        layout.addWidget(buttonBox)
        buttonBox.accepted.connect(dialog.accept)
        buttonBox.rejected.connect(dialog.reject)

        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            if list_widget.currentRow() >= 0:
                self.code_editor.setPlainText(self.code_history[list_widget.currentRow()])

    def open_results_in_window(self):
        """Ouvre les résultats dans une fenêtre séparée."""
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Résultats")
        layout = QtWidgets.QVBoxLayout(dialog)
        results_view = QtWidgets.QPlainTextEdit(dialog)
        results_view.setReadOnly(True)
        results_view.setPlainText(self.results_display.toPlainText())
        layout.addWidget(results_view)
        dialog.exec()

    def send_code(self):
        """Envoie le code au serveur maître pour exécution."""
        ip = self.ip_edit.text().strip()
        port_str = self.port_edit.text().strip()
        language = self.language_combo.currentText()
        code = self.code_editor.toPlainText()

        if not ip or not port_str or not code:
            self.results_display.setPlainText("Veuillez remplir tous les champs et fournir du code.")
            return

        try:
            port = int(port_str)
        except ValueError:
            self.results_display.setPlainText("Le port doit être un entier.")
            return

        self.status_bar.showMessage("Exécution en cours...")
        self.send_button.setEnabled(False)
        self.progress_bar.setVisible(True)
        QtWidgets.QApplication.processEvents()  # Mise à jour de l'UI

        # Historique
        self.code_history.append(code)

        # Connexion au serveur
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((ip, port))
        except Exception as e:
            self.results_display.setPlainText(f"Impossible de se connecter au serveur : {e}")
            self.status_bar.showMessage("Erreur")
            self.send_button.setEnabled(True)
            self.progress_bar.setVisible(False)
            return

        # Envoi des données
        try:
            header = language + "\n" + str(len(code)) + "\n"
            s.sendall(header.encode('utf-8'))
            s.sendall(code.encode('utf-8'))
        except Exception as e:
            self.results_display.setPlainText(f"Erreur lors de l'envoi des données : {e}")
            s.close()
            self.status_bar.showMessage("Erreur")
            self.send_button.setEnabled(True)
            self.progress_bar.setVisible(False)
            return

        # Réception du résultat
        try:
            result = receive_all(s)
            self.results_display.setPlainText(result)
        except Exception as e:
            self.results_display.setPlainText(f"Erreur lors de la réception des données : {e}")
        finally:
            s.close()

        self.status_bar.showMessage("Terminé")
        self.send_button.setEnabled(True)
        self.progress_bar.setVisible(False)

    def import_file(self):
        """Importe un fichier dans l'éditeur (détection automatique du langage)."""
        selected_file, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Ouvrir un fichier", "", "Tous les fichiers (*)"
        )
        if selected_file:
            try:
                with open(selected_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                self.code_editor.setPlainText(content)
                self.current_file = selected_file

                # Ajuster la combo en fonction de l'extension
                ext = os.path.splitext(selected_file)[1].lower()
                if ext == ".py":
                    self.language_combo.setCurrentText("PYTHON")
                elif ext == ".c":
                    self.language_combo.setCurrentText("C")
                elif ext == ".cpp":
                    self.language_combo.setCurrentText("C++")
                elif ext == ".java":
                    self.language_combo.setCurrentText("JAVA")

            except Exception as e:
                self.results_display.setPlainText(f"Erreur lors de la lecture du fichier : {e}")

    def save_file(self):
        """Enregistre le contenu de l'éditeur dans un fichier."""
        if not self.current_file:
            save_path, _ = QtWidgets.QFileDialog.getSaveFileName(
                self, "Enregistrer sous", "", "Tous les fichiers (*)"
            )
            if not save_path:
                return
            self.current_file = save_path

        try:
            with open(self.current_file, 'w', encoding='utf-8') as f:
                f.write(self.code_editor.toPlainText())
            self.status_bar.showMessage(f"Fichier enregistré: {self.current_file}")
        except Exception as e:
            self.results_display.setPlainText(f"Erreur lors de l'enregistrement : {e}")


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = ClientWindow()
    window.show()
    sys.exit(app.exec())
