#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import socket
import threading
import subprocess
import os
import sys
import uuid
import shutil
from contextlib import suppress

##########################################
# Helpers sécurité/ressources (identiques maître)
##########################################

def safe_filename(filename: str, language: str) -> str:
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

def make_job_dir(root="temp_codes_slave") -> str:
    d = os.path.join(root, "job_" + uuid.uuid4().hex)
    os.makedirs(d, exist_ok=True)
    return d

def _posix_limits():
    if os.name != "nt":
        try:
            import resource
            resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
            resource.setrlimit(resource.RLIMIT_AS, (256*1024**2,)*2)
            resource.setrlimit(resource.RLIMIT_FSIZE, (10*1024**2,)*2)
        except Exception:
            pass

##########################################
# Exécution code
##########################################

def compile_and_run(language, filename, code):
    job_dir = make_job_dir("temp_codes_slave")
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
        with suppress(Exception):
            shutil.rmtree(job_dir)

##########################################
# Réseau
##########################################

def handle_slave_client(client_socket, client_address):
    """
    Gère la requête (code) envoyée par le serveur maître :
     - language|filename|code
     - Compile/exécute et renvoie le résultat
    """
    try:
        data = client_socket.recv(10_000_000)
        if not data:
            client_socket.close()
            return

        decoded_data = data.decode('utf-8', errors='replace')
        split_data = decoded_data.split('|', 2)
        if len(split_data) < 3:
            client_socket.sendall(b"Erreur : Donnees invalides.\n")
            client_socket.close()
            return

        language = split_data[0]
        filename = split_data[1]
        code_source = split_data[2]

        output = compile_and_run(language, filename, code_source)
        client_socket.sendall(output.encode('utf-8', errors='replace'))

    except Exception as e:
        error_msg = f"Erreur (serveur esclave) : {str(e)}\n"
        with suppress(Exception):
            client_socket.sendall(error_msg.encode('utf-8', errors='replace'))
    finally:
        with suppress(Exception):
            client_socket.close()

def start_slave_server(host="0.0.0.0", port=6001):
    """Lance le serveur esclave sur le port spécifié."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    server.listen(5)
    print(f"[SERVEUR ESCLAVE] En écoute sur {host}:{port} ...")

    while True:
        client_socket, client_address = server.accept()
        print(f"[CONNEXION ESCLAVE] Serveur maître connecté: {client_address}")
        slave_thread = threading.Thread(
            target=handle_slave_client,
            args=(client_socket, client_address),
            daemon=True
        )
        slave_thread.start()

if __name__ == "__main__":
    host = "0.0.0.0"
    port = 6001
    if len(sys.argv) > 1:
        port = int(sys.argv[1])
    start_slave_server(host, port)
