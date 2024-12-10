import socket
import threading
import subprocess
import os
import tempfile

HOST = '127.0.0.1'
PORT = 6000

def handle_task(conn, addr):
    try:
        language = read_line(conn).strip()
        length_line = read_line(conn)
        code_length = int(length_line.strip())
        code = receive_fixed_length(conn, code_length)

        result = execute_code(language, code)
        conn.sendall(result.encode('utf-8'))
    except Exception as e:
        conn.sendall(f"Erreur interne esclave: {e}".encode('utf-8'))
    finally:
        conn.close()

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

def start_slave():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind((HOST, PORT))
    server_socket.listen(5)
    print(f"[INFO] Serveur esclave en écoute sur {HOST}:{PORT}")

    while True:
        conn, addr = server_socket.accept()
        thread = threading.Thread(target=handle_task, args=(conn, addr))
        thread.start()

if __name__ == "__main__":
    start_slave()
