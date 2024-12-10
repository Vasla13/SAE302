import socket
import threading
import subprocess
import os
import tempfile
import time
from queue import Queue

HOST = '127.0.0.1'
PORT = 5000

# Paramètres
MAX_TASKS_LOCAL = 2  # Au-delà de 2 tâches locales, on délègue aux esclaves.
SLAVES = [
    ('127.0.0.1', 6000)  # Liste des esclaves, vous pouvez en ajouter d'autres.
]

task_queue = Queue()

def handle_client(conn, addr):
    try:
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

        # Critère de délégation : si le nombre de tâches en cours est >= MAX_TASKS_LOCAL
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
        conn.close()

def delegate_to_slave(language, code):
    # Dans cet exemple, on choisit simplement le premier esclave de la liste.
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
            if c_out.strip():
                output = c_out
            else:
                output = run_command([exe_file])
        elif language in ("CPP", "C++"):
            exe_file = tmp_file_path + (".exe" if os.name == 'nt' else ".out")
            c_out = run_command(["g++", tmp_file_path, "-o", exe_file])
            if c_out.strip():
                output = c_out
            else:
                output = run_command([exe_file])
        elif language == "JAVA":
            dir_name = os.path.dirname(tmp_file_path)
            src_filename = os.path.join(dir_name, "Main.java")
            # S’assurer qu’un Main.java existant n’interfère pas
            if os.path.exists(src_filename):
                os.remove(src_filename)
            os.rename(tmp_file_path, src_filename)

            c_out = run_command(["javac", src_filename])
            if c_out.strip():
                output = c_out
            else:
                output = run_command(["java", "-cp", dir_name, "Main"])

            try:
                os.remove(src_filename)
            except:
                pass
            class_files = [f for f in os.listdir(dir_name) if f.endswith(".class")]
            for cf in class_files:
                try:
                    os.remove(os.path.join(dir_name, cf))
                except:
                    pass
            tmp_file_path = None
        else:
            output = f"Langage non supporté : {language}"
    except Exception as e:
        output = f"Erreur lors de l'exécution : {e}"
    finally:
        if tmp_file_path and os.path.exists(tmp_file_path):
            os.remove(tmp_file_path)
        if language in ("C", "CPP", "C++") and 'exe_file' in locals():
            try:
                os.remove(exe_file)
            except:
                pass

    return output

def run_command(cmd):
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = proc.communicate()
    return stdout.decode('utf-8') + stderr.decode('utf-8')

def get_extension(language):
    if language == "PYTHON":
        return ".py"
    elif language == "C":
        return ".c"
    elif language in ("CPP", "C++"):
        return ".cpp"
    elif language == "JAVA":
        return ".java"
    return ".txt"

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
    remaining = length
    while remaining > 0:
        chunk = conn.recv(remaining)
        if not chunk:
            return None
        data += chunk
        remaining -= len(chunk)
    return data.decode('utf-8')

def receive_all(sock):
    data = b""
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            break
        data += chunk
    return data.decode('utf-8')

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
    start_server()
