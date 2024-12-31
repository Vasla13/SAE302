import socket
import threading
import subprocess
import os
import sys
import time

##########################################
# Paramètres de charge et de scaling
##########################################
MAX_TASKS = 5
MAX_SLAVES = 5

# Ports disponibles pour lancer des esclaves (adapter si conflit)
SLAVE_PORTS = [6001, 6002, 6003, 6004, 6005]

# Listes dynamiques
SLAVE_SERVERS = []     # (ip, port) des esclaves
SLAVE_PROCESSES = []   # Objet subprocess.Popen pour chaque esclave lancé

# Compteur de tâches locales
current_tasks = 0
tasks_lock = threading.Lock()

##########################################
# Paramètres pour le kill d'esclaves
##########################################
KILL_THRESHOLD = 0
KILL_GRACE_PERIOD = 30
last_time_low_load = None

def is_port_active(port, host="127.0.0.1"):
    """
    Vérifie si le port 'port' sur 'host' est actif (connectable).
    """
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except (socket.timeout, ConnectionRefusedError):
        return False
    except Exception as e:
        print(f"[DEBUG] is_port_active({port}) => Erreur inattendue: {e}")
        return False

def handle_client(client_socket, client_address):
    global current_tasks
    
    try:
        data = client_socket.recv(10_000_000)
        if not data:
            client_socket.close()
            return

        decoded_data = data.decode('utf-8', errors='replace')

        # Commande d'administration 
        if decoded_data.startswith("ADMIN|"):
            response = handle_admin_command(decoded_data)
            client_socket.sendall(response.encode('utf-8', errors='replace'))
            client_socket.close()
            return

        # Sinon, exécution de code
        split_data = decoded_data.split('|', 2)
        if len(split_data) < 3:
            client_socket.sendall(b"Erreur : Donnees invalides.\n")
            client_socket.close()
            return

        language = split_data[0]
        filename = split_data[1]
        code_source = split_data[2]

        with tasks_lock:
            if current_tasks >= MAX_TASKS:
                # Tenter de lancer un nouvel esclave si pas au max
                maybe_launch_new_slave()
                
                # Déléguer à un esclave s’il y en a de dispo
                if SLAVE_SERVERS:
                    result = delegate_to_slave(language, filename, code_source)
                    client_socket.sendall(result.encode('utf-8', errors='replace'))
                    client_socket.close()
                    return
                else:
                    # Sinon, exécution locale par dépit
                    current_tasks += 1
            else:
                current_tasks += 1

        # Exécution locale
        output = compile_and_run(language, filename, code_source)
        client_socket.sendall(output.encode('utf-8', errors='replace'))

    except Exception as e:
        error_msg = f"Erreur (serveur maître) : {str(e)}\n"
        client_socket.sendall(error_msg.encode('utf-8', errors='replace'))

    finally:
        with tasks_lock:
            if current_tasks > 0:
                current_tasks -= 1

        client_socket.close()

def handle_admin_command(decoded_data):
    """
    Gère les commandes ADMIN (GET_INFO, SET_MAX_TASKS, SET_MAX_SLAVES).
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
        print("[INFO] Nombre max d'esclaves déjà atteint.")
        return

    used_ports = {p for (_, p) in SLAVE_SERVERS}
    free_ports = [p for p in SLAVE_PORTS if p not in used_ports]
    if not free_ports:
        print("[INFO] Plus de ports esclaves disponibles.")
        return

    new_port = free_ports[0]

    # Construction du chemin absolu pour server_esclave.py
    slave_script_path = os.path.join(os.path.dirname(__file__), "server_esclave.py")

    print(f"[DEBUG] Tentative de lancement d'un esclave sur le port {new_port} avec {slave_script_path}")
    proc = subprocess.Popen(
        [sys.executable, slave_script_path, str(new_port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    time.sleep(2)  # Laisser l'esclave démarrer

    # Vérifier si le port est actif
    if is_port_active(new_port, "127.0.0.1"):
        SLAVE_PROCESSES.append(proc)
        SLAVE_SERVERS.append(("127.0.0.1", new_port))
        print(f"[LANCEMENT ESCLAVE] Nouveau serveur esclave lancé sur le port {new_port}.")
    else:
        stderr = proc.stderr.read().decode('utf-8')
        print(f"[ERREUR ESCLAVE] Impossible de lancer un esclave sur le port {new_port}. "
              f"Le port n'est pas actif après démarrage. Erreur: {stderr}")
        proc.terminate()

def delegate_to_slave(language, filename, code_source):
    """
    Essaye de déléguer la tâche au premier esclave actif.
    """
    if not SLAVE_SERVERS:
        return "Erreur : aucun serveur esclave disponible.\n"

    # On peut faire un loop pour tester plusieurs esclaves
    for i, (slave_ip, slave_port) in enumerate(SLAVE_SERVERS):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((slave_ip, slave_port))
                payload = f"{language}|{filename}|{code_source}"
                s.sendall(payload.encode('utf-8'))

                result = []
                while True:
                    chunk = s.recv(4096)
                    if not chunk:
                        break
                    result.append(chunk.decode('utf-8', errors='replace'))
                return "".join(result)

        except Exception as e:
            print(f"[ERREUR] Impossible de contacter l'esclave {slave_ip}:{slave_port}. {e}")
            # On peut décider de retirer cet esclave s'il est défectueux
            # SLAVE_SERVERS.pop(i)
            pass

    return "Erreur : aucun esclave actif disponible.\n"

def compile_and_run(language, filename, code):
    """
    Exécution locale : compile/interprète le code selon le langage.
    """
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
    """
    Thread de monitoring qui vérifie la charge toutes les 5s
    et tue un esclave si la charge reste trop basse trop longtemps.
    """
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
    """
    Tue le dernier esclave de la liste.
    """
    if not SLAVE_PROCESSES or not SLAVE_SERVERS:
        return

    proc = SLAVE_PROCESSES.pop()
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

    # Thread de monitoring
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
