import sys
import socket
import threading
import subprocess
import os
import tempfile
from queue import Queue


# --------------------
# Paramètres généraux
# --------------------
HOST = '127.0.0.1'
PORT = 5000

# Pour limiter le nombre de tâches locales
# Si vous voulez le rendre paramétrable : MAX_TASKS_LOCAL = int(sys.argv[1]) if len(sys.argv) > 1 else 2
MAX_TASKS_LOCAL = 2

# Liste de serveurs esclaves (IP, PORT)
SLAVES = [
    ('127.0.0.1', 6000)  # Ajouter d'autres esclaves si nécessaire
]

# File d'attente pour gérer les tâches locales
task_queue = Queue()

# Pour suivi basique du nombre de clients connectés
clients_connected = 0


def start_server():
    """Démarre le serveur maître en écoute."""
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind((HOST, PORT))
    server_socket.listen(5)
    print(f"[INFO] Serveur maître en écoute sur {HOST}:{PORT}")

    while True:
        conn, addr = server_socket.accept()
        thread = threading.Thread(target=handle_client, args=(conn, addr))
        thread.start()


def handle_client(conn, addr):
    """Gère la connexion client et traite la requête."""
    global clients_connected
    try:
        clients_connected += 1
        print(f"[INFO] Connexion établie avec {addr}")
        print(f"[INFO] Clients connectés : {clients_connected}")

        language_line = read_line(conn)
        if not language_line:
            return
        language = language_line.strip()

        length_line = read_line(conn)
        if not length_line:
            return
        code_length = int(length_line.strip())

        code = receive_fixed_length(conn, code_length)
        if code is None:
            return

        # Si la file locale est pleine, déléguer à un esclave
        if task_queue.qsize() >= MAX_TASKS_LOCAL and SLAVES:
            result = delegate_to_slave(language, code)
        else:
            # Exécution locale
            task_queue.put(1)
            try:
                result = execute_code(language, code)
            finally:
                task_queue.get()

        conn.sendall(result.encode('utf-8'))

    except Exception as e:
        print(f"[ERREUR maître] {e}")
    finally:
        clients_connected -= 1
        print(f"[INFO] Connexion fermée avec {addr}. Clients connectés : {clients_connected}")
        conn.close()


def delegate_to_slave(language, code):
    """Délègue l'exécution du code au premier esclave de la liste."""
    if not SLAVES:
        return "Aucun serveur esclave disponible."

    ip, port = SLAVES[0]
    print(f"[INFO] Délégation au serveur esclave : {ip}:{port}")
    result = run_on_slave(ip, port, language, code)
    print(f"[INFO] Réponse reçue de l'esclave : {result}")
    return result


def run_on_slave(ip, port, language, code):
    """Envoie le code à un serveur esclave et récupère la réponse."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((ip, port))
        header = f"{language}\n{len(code)}\n"
        s.sendall(header.encode('utf-8'))
        s.sendall(code.encode('utf-8'))

        result = receive_all(s)
        s.close()
        return result
    except Exception as e:
        print(f"[ERREUR] Impossible de communiquer avec l'esclave : {e}")
        return f"Erreur de communication avec l'esclave : {e}"


def execute_code(language, code):
    """Compile/Exécute le code localement selon le langage."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=get_extension(language)) as tmp_file:
        tmp_file.write(code.encode('utf-8'))
        tmp_file_path = tmp_file.name

    output = ""
    try:
        if language == "PYTHON":
            cmd = ["python", tmp_file_path]
            output = run_command(cmd)
        elif language == "C":
            exe_file = tmp_file_path + (".exe" if os.name == 'nt' else ".out")
            c_out = run_command(["gcc", tmp_file_path, "-o", exe_file])
            output = c_out if c_out.strip() else run_command([exe_file])
        elif language in ("CPP", "C++"):
            exe_file = tmp_file_path + (".exe" if os.name == 'nt' else ".out")
            c_out = run_command(["g++", tmp_file_path, "-o", exe_file])
            output = c_out if c_out.strip() else run_command([exe_file])
        elif language == "JAVA":
            dir_name = os.path.dirname(tmp_file_path)
            src_filename = os.path.join(dir_name, "Main.java")
            if os.path.exists(src_filename):
                os.remove(src_filename)
            os.rename(tmp_file_path, src_filename)

            c_out = run_command(["javac", src_filename])
            output = c_out if c_out.strip() else run_command(["java", "-cp", dir_name, "Main"])

            # Nettoyage classes Java
            if os.path.exists(src_filename):
                os.remove(src_filename)
            for cf in os.listdir(dir_name):
                if cf.endswith(".class"):
                    os.remove(os.path.join(dir_name, cf))
        else:
            output = f"Langage non supporté : {language}"
    except Exception as e:
        output = f"Erreur lors de l'exécution : {e}"
    finally:
        if tmp_file_path and os.path.exists(tmp_file_path):
            os.remove(tmp_file_path)

    return output


def run_command(cmd):
    """Exécute une commande et retourne la sortie standard + erreur standard."""
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = proc.communicate()
    return stdout.decode('utf-8') + stderr.decode('utf-8')


def get_extension(language):
    """Retourne l'extension de fichier selon le langage."""
    return {
        "PYTHON": ".py",
        "C": ".c",
        "CPP": ".cpp",
        "C++": ".cpp",
        "JAVA": ".java"
    }.get(language, ".txt")


def read_line(conn):
    """Lit une ligne (terminée par \n) depuis la socket."""
    data = b""
    while True:
        chunk = conn.recv(1)
        if not chunk:
            return None
        if chunk == b"\n":
            break
        data += chunk
    return data.decode('utf-8')


def receive_fixed_length(conn, length):
    """Reçoit un message d'une longueur fixe."""
    data = b""
    remaining = length
    while remaining > 0:
        chunk = conn.recv(remaining)
        if not chunk:
            return None
        data += chunk
        remaining -= len(chunk)
    return data.decode('utf-8')


def receive_all(sock):
    """Lit tous les octets disponibles depuis la socket."""
    data = b""
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            break
        data += chunk
    return data.decode('utf-8')


if __name__ == "__main__":
    start_server()
