import socket
import threading
import subprocess
import os
import sys
import time
import uuid
import shutil
from contextlib import suppress

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

# Sécurisation ADMIN (optionnel) : définir ADMIN_TOKEN dans l'environnement
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "")

##########################################
# Helpers sécurité/ressources
##########################################

def safe_filename(filename: str, language: str) -> str:
    """Nettoie et force l'extension selon le langage."""
    base = os.path.basename(filename or "")
    if not base:
        base = f"main_{uuid.uuid4().hex}"
    base = "".join(c for c in base if c.isalnum() or c in ("-","_","."))[:64]
    lang = language.lower().lstrip(".")
    ext_map = {"python": ".py", "py": ".py", "c": ".c", "cpp": ".cpp", "c++": ".cpp", "java": ".java"}
    wanted = ext_map.get(lang, "")
    root, cur = os.path.splitext(base)
    if wanted and cur.lower() != wanted:
        base = root + wanted
    return base

def make_job_dir(root="temp_codes") -> str:
    d = os.path.join(root, "job_" + uuid.uuid4().hex)
    os.makedirs(d, exist_ok=True)
    return d

def _posix_limits():
    """Limites (CPU/Mémoire/Fichier) pour Unix uniquement."""
    if os.name != "nt":
        try:
            import resource
            resource.setrlimit(resource.RLIMIT_CPU, (5, 5))            # 5s CPU
            resource.setrlimit(resource.RLIMIT_AS, (256*1024**2,)*2)   # 256 MB
            resource.setrlimit(resource.RLIMIT_FSIZE, (10*1024**2,)*2) # 10 MB
        except Exception:
            pass

##########################################
# Réseau utilitaires
##########################################

def is_port_active(port, host="127.0.0.1"):
    """Vérifie si le port 'port' sur 'host' est connectable."""
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except Exception:
        return False

##########################################
# Handlers
##########################################

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
            response = handle_admin_command(decoded_data, client_address)
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
        with suppress(Exception):
            client_socket.sendall(error_msg.encode('utf-8', errors='replace'))

    finally:
        with tasks_lock:
            if current_tasks > 0:
                current_tasks -= 1
        with suppress(Exception):
            client_socket.close()

def handle_admin_command(decoded_data, client_address):
    """Gère les commandes ADMIN (GET_INFO, SET_MAX_TASKS, SET_MAX_SLAVES) avec contrôle d'accès."""
    global current_tasks, MAX_TASKS, MAX_SLAVES

    parts = decoded_data.split('|')
    if len(parts) < 2:
        return "Erreur : commande ADMIN invalide."

    # Format supporté : ADMIN|TOKEN=xxx|SUBCMD|...
    token = ""
    idx = 1
    if len(parts) > 1 and parts[1].startswith("TOKEN="):
        token = parts[1][6:]
        idx = 2

    # Autorisation : local OU token valide si défini
    is_local = client_address[0] in ("127.0.0.1", "::1")
    if not is_local and (not ADMIN_TOKEN or token != ADMIN_TOKEN):
        return "Erreur : ADMIN non autorisée."

    if len(parts) <= idx:
        return "Erreur : sous-commande ADMIN manquante."
    subcommand = parts[idx].upper()

    if subcommand == "GET_INFO":
        return (
            "INFO:\n"
            f" - Tâches en cours: {current_tasks}\n"
            f" - MAX_TASKS: {MAX_TASKS}\n"
            f" - MAX_SLAVES: {MAX_SLAVES}\n"
            f" - Nombre d'esclaves actifs: {len(SLAVE_SERVERS)}\n"
        )

    elif subcommand == "SET_MAX_TASKS":
        if len(parts) <= idx + 1:
            return "Erreur : valeur SET_MAX_TASKS manquante."
        try:
            new_max = int(parts[idx + 1])
            if new_max < 1:
                return "Erreur : la valeur de MAX_TASKS doit être >= 1."
            MAX_TASKS = new_max
            return f"OK: MAX_TASKS est maintenant {MAX_TASKS}."
        except ValueError:
            return "Erreur : valeur SET_MAX_TASKS invalide (entier attendu)."

    elif subcommand == "SET_MAX_SLAVES":
        if len(parts) <= idx + 1:
            return "Erreur : valeur SET_MAX_SLAVES manquante."
        try:
            new_max_slaves = int(parts[idx + 1])
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

    print(f"[DEBUG] Lancement d'un esclave sur le port {new_port} -> {slave_script_path}")
    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.Popen(
        [sys.executable, slave_script_path, str(new_port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags
    )
    time.sleep(2)  # Laisser l'esclave démarrer

    # Vérifier si le port est actif
    if is_port_active(new_port, "127.0.0.1"):
        SLAVE_PROCESSES.append(proc)
        SLAVE_SERVERS.append(("127.0.0.1", new_port))
        print(f"[LANCEMENT ESCLAVE] Nouveau serveur esclave lancé sur le port {new_port}.")
    else:
        print(f"[ERREUR ESCLAVE] Le port {new_port} n'est pas actif après démarrage.")
        with suppress(Exception):
            proc.terminate()
            time.sleep(1)
            if proc.poll() is None:
                proc.kill()

def delegate_to_slave(language, filename, code_source):
    """Essaye de déléguer la tâche au premier esclave actif avec timeout réseau."""
    if not SLAVE_SERVERS:
        return "Erreur : aucun serveur esclave disponible.\n"

    payload = f"{language}|{safe_filename(filename, language)}|{code_source}"

    for i, (slave_ip, slave_port) in enumerate(SLAVE_SERVERS):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(10)
                s.connect((slave_ip, slave_port))
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
            # On pourrait retirer l'esclave défectueux ici si nécessaire
            pass

    return "Erreur : aucun esclave actif disponible.\n"

def compile_and_run(language, filename, code):
    """Exécution locale : compile/interprète le code selon le langage avec timeouts et limites."""
    job_dir = make_job_dir("temp_codes")
    filepath = os.path.join(job_dir, safe_filename(filename, language))

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(code)

    try:
        lang = language.lower().lstrip('.')
        preexec = _posix_limits if os.name != "nt" else None

        if lang in ["python", "py"]:
            cmd = [sys.executable, filepath]
            exec_proc = subprocess.run(cmd, capture_output=True, text=True, timeout=5, preexec_fn=preexec)
            out = f"Sortie:\n{exec_proc.stdout}\n"
            if exec_proc.stderr:
                out += f"Erreurs:\n{exec_proc.stderr}\n"
            return out

        elif lang in ["c"]:
            exe = os.path.join(job_dir, "a.exe" if os.name == "nt" else "a.out")
            comp = subprocess.run(["gcc", filepath, "-O2", "-s", "-o", exe],
                                  capture_output=True, text=True, timeout=15)
            if comp.returncode != 0:
                return f"Erreur de compilation C:\n{comp.stderr}"
            exec_proc = subprocess.run([exe], capture_output=True, text=True, timeout=5, preexec_fn=preexec)
            out = f"Sortie:\n{exec_proc.stdout}\n"
            if exec_proc.stderr:
                out += f"Erreurs:\n{exec_proc.stderr}\n"
            return out

        elif lang in ["c++", "cpp"]:
            exe = os.path.join(job_dir, "a.exe" if os.name == "nt" else "a.out")
            comp = subprocess.run(["g++", filepath, "-O2", "-s", "-o", exe],
                                  capture_output=True, text=True, timeout=15)
            if comp.returncode != 0:
                return f"Erreur de compilation C++:\n{comp.stderr}"
            exec_proc = subprocess.run([exe], capture_output=True, text=True, timeout=5, preexec_fn=preexec)
            out = f"Sortie:\n{exec_proc.stdout}\n"
            if exec_proc.stderr:
                out += f"Erreurs:\n{exec_proc.stderr}\n"
            return out

        elif lang in ["java"]:
            comp = subprocess.run(["javac", filepath, "-d", job_dir],
                                  capture_output=True, text=True, timeout=20)
            if comp.returncode != 0:
                return f"Erreur de compilation Java:\n{comp.stderr}"
            class_name = os.path.splitext(os.path.basename(filepath))[0]
            exec_proc = subprocess.run(["java", "-cp", job_dir, class_name],
                                       capture_output=True, text=True, timeout=5, preexec_fn=preexec)
            out = f"Sortie:\n{exec_proc.stdout}\n"
            if exec_proc.stderr:
                out += f"Erreurs:\n{exec_proc.stderr}\n"
            return out

        else:
            return "Langage non supporté ou inconnu.\n"

    except subprocess.TimeoutExpired:
        return "Erreur : exécution dépassé le délai (timeout).\n"
    except Exception as e:
        return f"Erreur lors de l'execution : {str(e)}\n"
    finally:
        # Nettoyage (best-effort)
        with suppress(Exception):
            shutil.rmtree(job_dir)

def load_monitor_thread():
    """Thread de monitoring de la charge : tue 1 esclave si charge basse prolongée."""
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
    """Tue le dernier esclave de la liste (libération de ressources)."""
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
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
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
