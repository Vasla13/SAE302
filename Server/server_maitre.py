import socket
import threading
import subprocess
import os
import sys
import time

##########################################
# Paramètres de charge et de scaling
##########################################
MAX_TASKS = 3           # Limite de tâches en local avant délégation
MAX_SLAVES = 5          # Nombre maximum d'esclaves que le maître peut lancer
SLAVE_PORTS = [6001, 6002, 6003, 6004, 6005, 6006]

SLAVE_SERVERS = []      # Liste dynamique (ip, port) des esclaves
SLAVE_PROCESSES = []    # Liste des processus (Popen) esclaves lancés

current_tasks = 0       # Nombre de tâches en cours d'exécution locale
tasks_lock = threading.Lock()

##########################################
# Paramètres pour le kill d'esclaves
##########################################
KILL_THRESHOLD = 0         # Si current_tasks <= 0, on considère la charge "très basse"
KILL_GRACE_PERIOD = 30     # Temps (secondes) pendant lequel la charge doit rester <= KILL_THRESHOLD
last_time_low_load = None  # Timestamp quand on est passé en charge basse

def handle_client(client_socket, client_address):
    global current_tasks
    
    try:
        data = client_socket.recv(10_000_000)
        if not data:
            client_socket.close()
            return

        decoded_data = data.decode('utf-8', errors='replace')

        # Vérifier si c’est une commande ADMIN
        if decoded_data.startswith("ADMIN|"):
            response = handle_admin_command(decoded_data)
            client_socket.sendall(response.encode('utf-8', errors='replace'))
            client_socket.close()
            return

        # Sinon, c’est un code "langage|nom_fichier|<code_source>"
        split_data = decoded_data.split('|', 2)
        if len(split_data) < 3:
            client_socket.sendall(b"Erreur : Donnees invalides.\n")
            client_socket.close()
            return

        language = split_data[0]
        filename = split_data[1]
        code_source = split_data[2]

        # Vérifier la charge
        with tasks_lock:
            if current_tasks >= MAX_TASKS:
                # Tenter de lancer un nouvel esclave si possible
                maybe_launch_new_slave()
                
                # On délègue la tâche à un esclave s'il y en a
                if SLAVE_SERVERS:
                    result = delegate_to_slave(language, filename, code_source)
                    client_socket.sendall(result.encode('utf-8', errors='replace'))
                    client_socket.close()
                    return
                else:
                    # Pas d'esclave dispo -> exécution locale malgré tout
                    current_tasks += 1
            else:
                current_tasks += 1

        # Compiler / exécuter localement
        output = compile_and_run(language, filename, code_source)
        client_socket.sendall(output.encode('utf-8', errors='replace'))

    except Exception as e:
        error_msg = f"Erreur (serveur maître) : {str(e)}\n"
        client_socket.sendall(error_msg.encode('utf-8', errors='replace'))

    finally:
        # Libérer la ressource
        with tasks_lock:
            if current_tasks > 0:
                current_tasks -= 1

        client_socket.close()

def handle_admin_command(decoded_data):
    """
    Gère les commandes ADMIN, ex:
      - ADMIN|GET_INFO
      - ADMIN|SET_MAX_TASKS|<valeur>
      - ADMIN|SET_MAX_SLAVES|<valeur>
    """
    global current_tasks, MAX_TASKS, MAX_SLAVES

    parts = decoded_data.split('|')
    if len(parts) < 2:
        return "Erreur : commande ADMIN invalide."

    subcommand = parts[1].upper()

    if subcommand == "GET_INFO":
        info = (
            f"INFO:\n"
            f" - Tâches en cours: {current_tasks}\n"
            f" - MAX_TASKS: {MAX_TASKS}\n"
            f" - MAX_SLAVES: {MAX_SLAVES}\n"
            f" - Nombre d'esclaves actifs: {len(SLAVE_SERVERS)}\n"
        )
        return info

    elif subcommand == "SET_MAX_TASKS":
        if len(parts) < 3:
            return "Erreur : valeur SET_MAX_TASKS manquante."
        try:
            new_max = int(parts[2])
            if new_max < 1:
                return "Erreur : la valeur de MAX_TASKS doit être >= 1."
            MAX_TASKS = new_max
            return f"OK: MAX_TASKS est maintenant {MAX_TASKS}."
        except ValueError:
            return "Erreur : valeur SET_MAX_TASKS invalide (entier attendu)."

    elif subcommand == "SET_MAX_SLAVES":
        if len(parts) < 3:
            return "Erreur : valeur SET_MAX_SLAVES manquante."
        try:
            new_max_slaves = int(parts[2])
            if new_max_slaves < 0:
                return "Erreur : la valeur de MAX_SLAVES doit être >= 0."
            MAX_SLAVES = new_max_slaves
            return f"OK: MAX_SLAVES est maintenant {MAX_SLAVES}."
        except ValueError:
            return "Erreur : valeur SET_MAX_SLAVES invalide (entier attendu)."

    else:
        return f"Erreur : sous-commande ADMIN inconnue : {subcommand}"

def maybe_launch_new_slave():
    global MAX_SLAVES

    if len(SLAVE_PROCESSES) >= MAX_SLAVES:
        return

    used_ports = {p for (_, p) in SLAVE_SERVERS}
    free_ports = [p for p in SLAVE_PORTS if p not in used_ports]
    if not free_ports:
        return

    new_port = free_ports[0]

    proc = subprocess.Popen(
        [sys.executable, "server_esclave.py", str(new_port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    time.sleep(1)

    SLAVE_PROCESSES.append(proc)
    SLAVE_SERVERS.append(("127.0.0.1", new_port))

    print(f"[LANCEMENT ESCLAVE] Nouveau serveur esclave lancé sur le port {new_port}.")

def delegate_to_slave(language, filename, code_source):
    if not SLAVE_SERVERS:
        return "Erreur : aucun serveur esclave disponible.\n"

    slave_ip, slave_port = SLAVE_SERVERS[0]

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((slave_ip, slave_port))
            payload = f"{language}|{filename}|{code_source}"
            s.sendall(payload.encode('utf-8', errors='replace'))

            result = []
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    break
                result.append(chunk.decode('utf-8', errors='replace'))
            return "".join(result)
    except Exception as e:
        return f"Erreur : impossible de contacter l'esclave {slave_ip}:{slave_port}. {str(e)}\n"

def compile_and_run(language, filename, code):
    temp_dir = "temp_codes"
    os.makedirs(temp_dir, exist_ok=True)

    filepath = os.path.join(temp_dir, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(code)

    try:
        if language.lower() in ["python", ".py"]:
            cmd = [sys.executable, filepath]
        elif language.lower() in ["c", ".c"]:
            exe_file = os.path.splitext(filepath)[0]
            compile_proc = subprocess.run(["gcc", filepath, "-o", exe_file],
                                          capture_output=True, text=True)
            if compile_proc.returncode != 0:
                return f"Erreur de compilation C:\n{compile_proc.stderr}"
            cmd = [exe_file]
        elif language.lower() in ["c++", "cpp", ".cpp"]:
            exe_file = os.path.splitext(filepath)[0]
            compile_proc = subprocess.run(["g++", filepath, "-o", exe_file],
                                          capture_output=True, text=True)
            if compile_proc.returncode != 0:
                return f"Erreur de compilation C++:\n{compile_proc.stderr}"
            cmd = [exe_file]
        elif language.lower() in ["java", ".java"]:
            compile_proc = subprocess.run(["javac", filepath],
                                          capture_output=True, text=True)
            if compile_proc.returncode != 0:
                return f"Erreur de compilation Java:\n{compile_proc.stderr}"
            class_file = os.path.splitext(os.path.basename(filepath))[0]
            cmd = ["java", "-cp", temp_dir, class_file]
        else:
            return "Langage non supporté ou inconnu.\n"

        exec_proc = subprocess.run(cmd, capture_output=True, text=True)
        output = f"Sortie:\n{exec_proc.stdout}\n"
        if exec_proc.stderr:
            output += f"Erreurs:\n{exec_proc.stderr}\n"
        return output

    except Exception as e:
        return f"Erreur lors de l'execution : {str(e)}\n"

def load_monitor_thread():
    global last_time_low_load

    while True:
        time.sleep(5)
        with tasks_lock:
            if current_tasks <= KILL_THRESHOLD:
                if last_time_low_load is None:
                    last_time_low_load = time.time()
                else:
                    elapsed = time.time() - last_time_low_load
                    if elapsed >= KILL_GRACE_PERIOD:
                        maybe_kill_one_slave()
                        last_time_low_load = time.time()
            else:
                last_time_low_load = None

def maybe_kill_one_slave():
    if not SLAVE_PROCESSES or not SLAVE_SERVERS:
        return

    proc = SLAVE_PROCESSES.pop()  # process
    ip, port = SLAVE_SERVERS.pop()

    try:
        proc.terminate()
        time.sleep(1)
        if proc.poll() is None:
            proc.kill()

        print(f"[KILL ESCLAVE] Esclave sur port {port} tué pour libérer des ressources.")
    except Exception as e:
        print(f"[ERREUR KILL ESCLAVE] Impossible de tuer l'esclave port {port}. {e}")

def start_server(host="0.0.0.0", port=5000):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((host, port))
    server.listen(5)
    print(f"[SERVEUR MAÎTRE] En écoute sur {host}:{port} ...")

    monitor_thread = threading.Thread(target=load_monitor_thread, daemon=True)
    monitor_thread.start()

    while True:
        client_socket, client_address = server.accept()
        print(f"[CONNEXION] Client connecté: {client_address}")
        client_thread = threading.Thread(
            target=handle_client,
            args=(client_socket, client_address),
            daemon=True
        )
        client_thread.start()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        port = int(sys.argv[1])
    else:
        port = 5000

    start_server("0.0.0.0", port)
