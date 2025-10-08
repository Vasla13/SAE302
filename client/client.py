import sys
import socket
import os

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QLineEdit, QPushButton,
    QVBoxLayout, QHBoxLayout, QTextEdit, QComboBox, QFileDialog, QMenuBar, QMenu,
    QMessageBox, QGroupBox, QGridLayout, QSplitter
)
from PyQt6.QtCore import Qt, QRegularExpression
from PyQt6.QtGui import QFont, QTextCharFormat, QColor, QSyntaxHighlighter

# =========================
# Simple highlighter Python
# =========================
class PythonSyntaxHighlighter(QSyntaxHighlighter):
    """
      Un simple QSyntaxHighlighter pour le code Python.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._rules = []

        # Format pour les mots-clés
        keyword_format = QTextCharFormat()
        keyword_format.setForeground(QColor("#0000FF"))  # Bleu
        keyword_words = [
            "def", "class", "import", "from", "as", "if", "elif", "else", 
            "for", "while", "return", "in", "and", "or", "not", "print"
        ]
        for word in keyword_words:
            pattern = QRegularExpression(r"\b" + word + r"\b")
            self._rules.append((pattern, keyword_format))

        # Format pour les chaînes de caractères (simple / double quotes)
        string_format = QTextCharFormat()
        string_format.setForeground(QColor("#008000"))  # Vert
        # Simple quotes
        pattern_single = QRegularExpression(r"'[^'\\]*(\\.[^'\\]*)*'")
        self._rules.append((pattern_single, string_format))
        # Double quotes
        pattern_double = QRegularExpression(r"\"[^\"\\]*(\\.[^\"\\]*)*\"")
        self._rules.append((pattern_double, string_format))

        # Format pour les commentaires (# ...)
        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor("#999999"))  # Gris
        pattern_comment = QRegularExpression(r"#.*")
        self._rules.append((pattern_comment, comment_format))

    def highlightBlock(self, text):
        for pattern, fmt in self._rules:
            matcher = pattern.globalMatch(text)
            while matcher.hasNext():
                match = matcher.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), fmt)

class ClientGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Client")
        self.resize(1200, 800)

        # =========================
        #  Barre de menu 
        # =========================
        menubar = QMenuBar(self)
        file_menu = QMenu("Fichier", self)
        menubar.addMenu(file_menu)
        self.setMenuBar(menubar)

        # =========================
        #  Paramètres de connexion et compilation
        # =========================
        self.ip_label = QLabel("IP du serveur :")
        self.ip_edit = QLineEdit("127.0.0.1")  # Valeur par défaut

        self.port_label = QLabel("Port :")
        self.port_edit = QLineEdit("5000")     # Valeur par défaut

        self.lang_label = QLabel("Langage :")
        self.lang_combo = QComboBox()
        self.lang_combo.addItems(["Python", "C", "C++", "Java"])

        self.file_label = QLabel("Nom du fichier :")
        self.file_edit = QLineEdit("exemple.py")

        self.import_code_button = QPushButton("Importer un fichier")
        self.import_code_button.clicked.connect(self.open_file_dialog)

        self.save_code_button = QPushButton("Enregistrer le code")
        self.save_code_button.clicked.connect(self.save_file_dialog)

        # Indicateur de connexion
        self.connection_status_label = QLabel("Statut :")
        self.connection_status_indicator = QLabel()
        self.connection_status_indicator.setFixedSize(20, 20)
        self.connection_status_indicator.setStyleSheet("background-color: red; border-radius: 10px;")

        self.test_connection_button = QPushButton("Tester la connexion")
        self.test_connection_button.clicked.connect(self.test_connection)

        # GroupBox Paramètres
        top_groupbox = QGroupBox("Paramètres de connexion et compilation")
        top_layout = QGridLayout()

        top_layout.addWidget(self.ip_label, 0, 0)
        top_layout.addWidget(self.ip_edit, 0, 1)
        top_layout.addWidget(self.port_label, 0, 2)
        top_layout.addWidget(self.port_edit, 0, 3)

        top_layout.addWidget(self.lang_label, 1, 0)
        top_layout.addWidget(self.lang_combo, 1, 1)
        top_layout.addWidget(self.file_label, 1, 2)
        top_layout.addWidget(self.file_edit, 1, 3)

        top_layout.addWidget(self.import_code_button, 2, 0, 1, 2)
        top_layout.addWidget(self.save_code_button,    2, 2, 1, 2)

        top_layout.addWidget(self.connection_status_label, 3, 0)
        top_layout.addWidget(self.connection_status_indicator, 3, 1)
        top_layout.addWidget(self.test_connection_button, 3, 2, 1, 2)

        top_groupbox.setLayout(top_layout)

        # =========================
        #  Éditeur de code
        # =========================
        self.code_edit = QTextEdit()
        font = QFont("Courier New", 11)
        self.code_edit.setFont(font)
        self.syntax_highlighter = PythonSyntaxHighlighter(self.code_edit.document())

        # =========================
        #  Résultats
        # =========================
        self.result_edit = QTextEdit()
        self.result_edit.setReadOnly(True)
        self.result_edit.setFont(font)

        self.run_button = QPushButton("Exécuter le code")
        self.run_button.clicked.connect(self.run_code)

        self.clear_result_button = QPushButton("Vider la sortie")
        self.clear_result_button.clicked.connect(self.clear_result)

        # =========================
        #  Section Administration
        # =========================
        self.admin_groupbox = QGroupBox("Administration du Serveur")
        self.admin_layout = QVBoxLayout()

        # Champ MAX_TASKS
        self.new_max_label = QLabel("Nouvelle valeur de MAX_TASKS :")
        self.new_max_edit = QLineEdit("5")
        self.btn_set_max_tasks = QPushButton("Mettre à jour MAX_TASKS")
        self.btn_set_max_tasks.clicked.connect(self.update_max_tasks)

        # Champ MAX_SLAVES
        self.new_max_slaves_label = QLabel("Nouvelle valeur de MAX_SLAVES :")
        self.new_max_slaves_edit = QLineEdit("5")
        self.btn_set_max_slaves = QPushButton("Mettre à jour MAX_SLAVES")
        self.btn_set_max_slaves.clicked.connect(self.update_max_slaves)

        # Bouton pour récupérer les infos
        self.btn_get_info = QPushButton("Obtenir info du serveur (Tâches, MAX_TASKS, MAX_SLAVES, etc.)")
        self.btn_get_info.clicked.connect(self.get_server_info)

        self.admin_layout.addWidget(self.new_max_label)
        self.admin_layout.addWidget(self.new_max_edit)
        self.admin_layout.addWidget(self.btn_set_max_tasks)
        self.admin_layout.addSpacing(10)

        self.admin_layout.addWidget(self.new_max_slaves_label)
        self.admin_layout.addWidget(self.new_max_slaves_edit)
        self.admin_layout.addWidget(self.btn_set_max_slaves)
        self.admin_layout.addSpacing(10)

        self.admin_layout.addWidget(self.btn_get_info)

        self.admin_groupbox.setLayout(self.admin_layout)

        # =========================
        #  Splitter (code / résultats)
        # =========================
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(5)

        code_groupbox = QGroupBox("Éditeur de code")
        code_layout = QVBoxLayout()
        code_layout.addWidget(self.code_edit)
        code_groupbox.setLayout(code_layout)

        result_groupbox = QGroupBox("Résultats d'exécution")
        result_layout = QVBoxLayout()

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.run_button)
        button_layout.addWidget(self.clear_result_button)

        result_layout.addLayout(button_layout)
        result_layout.addWidget(self.result_edit)
        result_groupbox.setLayout(result_layout)

        splitter.addWidget(code_groupbox)
        splitter.addWidget(result_groupbox)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        # =========================
        #  Layout principal
        # =========================
        main_layout = QVBoxLayout()
        main_layout.addWidget(top_groupbox)

        # Admin + splitter côte à côte
        middle_layout = QHBoxLayout()
        middle_layout.addWidget(self.admin_groupbox, stretch=0)
        middle_layout.addWidget(splitter, stretch=1)

        main_layout.addLayout(middle_layout)

        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

        # Code par défaut
        self.code_edit.setPlainText("# Écrivez votre code Python ici...\nprint('Hello World!')")

    # ======================================================
    #   Méthodes : Tester la connexion
    # ======================================================
    def test_connection(self):
        """Tester la connexion au serveur et mettre à jour l'indicateur de statut."""
        server_ip = self.ip_edit.text().strip()
        server_port = int(self.port_edit.text().strip())

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(5)  # Timeout de 5 secondes
                s.connect((server_ip, server_port))
                self.connection_status_indicator.setStyleSheet("background-color: green; border-radius: 10px;")
                QMessageBox.information(self, "Connexion réussie", "La connexion au serveur a été établie avec succès.")
        except Exception as e:
            self.connection_status_indicator.setStyleSheet("background-color: red; border-radius: 10px;")
            QMessageBox.critical(self, "Erreur de connexion", f"Impossible de se connecter au serveur :\n{str(e)}")

    # ======================================================
    #   Méthodes : Exécuter code
    # ======================================================
    def run_code(self):
        """
        Envoie le code au serveur maître pour compilation/exécution.
        Affiche la sortie ou l'erreur dans la zone de résultats.
        """
        server_ip = self.ip_edit.text().strip()
        server_port = int(self.port_edit.text().strip())

        language = self.lang_combo.currentText()
        filename = self.file_edit.text().strip()
        code_source = self.code_edit.toPlainText()

        payload = f"{language}|{filename}|{code_source}"

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(10)  # évite de se bloquer
                s.connect((server_ip, server_port))
                s.sendall(payload.encode('utf-8'))

                response = []
                while True:
                    chunk = s.recv(4096)
                    if not chunk:
                        break
                    response.append(chunk.decode('utf-8', errors='replace'))
            result = "".join(response)
            self.result_edit.setPlainText(result)

        except Exception as e:
            self.result_edit.setPlainText(f"Erreur (exécution) : {str(e)}")

    # ======================================================
    #   Méthodes : Administration (GET_INFO, SET_MAX_TASKS, SET_MAX_SLAVES)
    # ======================================================
    def get_server_info(self):
        """
        Envoie ADMIN|GET_INFO (avec TOKEN si présent en variable d'env) pour connaître la charge
        """
        resp = self.send_admin_command("GET_INFO")
        self.result_edit.setPlainText(resp)

    def update_max_tasks(self):
        """
        Envoie ADMIN|SET_MAX_TASKS|<valeur> pour mettre à jour MAX_TASKS sur le maître.
        """
        new_max = self.new_max_edit.text().strip()
        if not new_max.isdigit():
            QMessageBox.warning(self, "Attention", "La valeur de MAX_TASKS doit être un entier.")
            return

        command = f"SET_MAX_TASKS|{new_max}"
        resp = self.send_admin_command(command)
        self.result_edit.setPlainText(resp)

    def update_max_slaves(self):
        """
        Envoie ADMIN|SET_MAX_SLAVES|<valeur> pour mettre à jour MAX_SLAVES sur le maître.
        """
        new_max_slaves = self.new_max_slaves_edit.text().strip()
        if not new_max_slaves.isdigit():
            QMessageBox.warning(self, "Attention", "La valeur de MAX_SLAVES doit être un entier.")
            return

        command = f"SET_MAX_SLAVES|{new_max_slaves}"
        resp = self.send_admin_command(command)
        self.result_edit.setPlainText(resp)

    def send_admin_command(self, subcommand):
        """
        Envoie une commande ADMIN : ADMIN|[TOKEN=xxx|]<subcommand>[|param...]
        - Si la variable d'env ADMIN_TOKEN est définie côté client, on l'ajoute automatiquement.
        """
        server_ip = self.ip_edit.text().strip()
        server_port = int(self.port_edit.text().strip())

        token = os.environ.get("ADMIN_TOKEN", "").strip()
        if token:
            payload = f"ADMIN|TOKEN={token}|{subcommand}"
        else:
            payload = f"ADMIN|{subcommand}"

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(10)
                s.connect((server_ip, server_port))
                s.sendall(payload.encode('utf-8'))

                response = []
                while True:
                    chunk = s.recv(4096)
                    if not chunk:
                        break
                    response.append(chunk.decode('utf-8', errors='replace'))
            return "".join(response)
        except Exception as e:
            return f"Erreur (admin) : {str(e)}"

    # ======================================================
    #   Méthodes : Importer/Enregistrer le code
    # ======================================================
    def open_file_dialog(self):
        """
        Ouvrir un fichier existant sur le disque et charger son contenu dans l'éditeur.
        """
        file_dialog = QFileDialog(self, "Importer un fichier")
        file_dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        if file_dialog.exec():
            selected_files = file_dialog.selectedFiles()
            if selected_files:
                file_path = selected_files[0]
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    self.code_edit.setPlainText(content)
                    self.file_edit.setText(os.path.basename(file_path))
                except Exception as e:
                    QMessageBox.critical(self, "Erreur", f"Impossible de lire le fichier:\n{str(e)}")

    def save_file_dialog(self):
        """
        Enregistrer le code courant dans un fichier sur le disque.
        """
        file_dialog = QFileDialog(self, "Enregistrer le code")
        file_dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        if file_dialog.exec():
            selected_files = file_dialog.selectedFiles()
            if selected_files:
                file_path = selected_files[0]
                try:
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(self.code_edit.toPlainText())
                    QMessageBox.information(self, "Succès", "Fichier enregistré avec succès.")
                except Exception as e:
                    QMessageBox.critical(self, "Erreur", f"Impossible d'enregistrer le fichier:\n{str(e)}")

    def clear_result(self):
        """Vider la zone de sortie."""
        self.result_edit.clear()

def main():
    app = QApplication(sys.argv)
    gui = ClientGUI()
    gui.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
