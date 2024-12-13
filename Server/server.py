import socket
import threading
import subprocess
import os
import tempfile
from queue import Queue
from flask import Flask, render_template
import psutil  # Pour surveiller la charge CPU et mémoire

# Configuration du serveur
HOST = '127.0.0.1'
PORT = 5000
MAX_TASKS_LOCAL = 2
SLAVES = [
    ('127.0.0.1', 6000)
]

task_queue = Queue()

# Flask App pour le monitoring
app = Flask(__name__)

server_status = {
    "clients_connected": 0,
    "tasks_in_queue": 0,
    "cpu_usage": 0.0,
    "memory_usage": 0.0,
    "slaves": [{"ip": slave[0], "port": slave[1], "status": "Unknown"} for slave in SLAVES]
}

@app.route("/")
def monitoring_dashboard():
    """Affiche le tableau de bord du monitoring."""
    return render_template("dashboard.html", status=server_status)

def update_server_status():
    """Met à jour périodiquement l'état des ressources."""
    while True:
        server_status["cpu_usage"] = psutil.cpu_percent(interval=1)
        server_status["memory_usage"] = psutil.virtual_memory().percent
        server_status["tasks_in_queue"] = task_queue.qsize()

        # Vérification de l'état des esclaves
        for slave in server_status["slaves"]:
            slave["status"] = "Connected" if test_connection(slave["ip"], slave["port"]) else "Disconnected"

def start_monitoring_interface():
    """Démarre l'interface Flask."""
    app.run(host="0.0.0.0", port=8080)

def handle_client(conn, addr):
    """Gère les connexions clients et les tâches."""
    try:
        server_status["clients_connected"] += 1

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

        # Critère de délégation
        if task_queue.qsize() >= MAX_TASKS_LOCAL and SLAVES:
            result = delegate_to_slave(language, code)
        else:
            task_queue.put(1)
            try:
                result = execute_code(language, code)
            finally:
                task_queue.get()

        conn.sendall(result.encode('utf-8'))
    except Exception as e:
        print(f"[ERREUR maître] {e}")
    finally:
        server_status["clients_connected"] -= 1
        conn.close()

def delegate_to_slave(language, code):
    ip, port = SLAVES[0]
    return run_on_slave(ip, port, language, code)

def run_on_slave(ip, port, language, code):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((ip, port))
    header = language + "\n" + str(len(code)) + "\n"
    s.sendall(header.encode('utf-8'))
    s.sendall(code.encode('utf-8'))
    result = receive_all(s)
    s.close()
    return result

def execute_code(language, code):
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
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = proc.communicate()
    return stdout.decode('utf-8') + stderr.decode('utf-8')

def get_extension(language):
    return {
        "PYTHON": ".py",
        "C": ".c",
        "CPP": ".cpp",
        "C++": ".cpp",
        "JAVA": ".java"
    }.get(language, ".txt")

def read_line(conn):
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
    data = b""
    while length > 0:
        chunk = conn.recv(length)
        if not chunk:
            return None
        data += chunk
        length -= len(chunk)
    return data.decode('utf-8')

def receive_all(sock):
    data = b""
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            break
        data += chunk
    return data.decode('utf-8')

def test_connection(ip, port):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        s.connect((ip, port))
        s.close()
        return True
    except:
        return False

def start_server():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind((HOST, PORT))
    server_socket.listen(5)
    print(f"[INFO] Serveur maître en écoute sur {HOST}:{PORT}")

    while True:
        conn, addr = server_socket.accept()
        client_thread = threading.Thread(target=handle_client, args=(conn, addr))
        client_thread.start()

if __name__ == "__main__":
    monitoring_thread = threading.Thread(target=start_monitoring_interface, daemon=True)
    monitoring_thread.start()

    resource_thread = threading.Thread(target=update_server_status, daemon=True)
    resource_thread.start()

    start_server()
