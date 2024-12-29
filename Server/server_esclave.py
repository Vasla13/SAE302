#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import socket
import threading
import subprocess
import os
import sys

def handle_slave_client(client_socket, client_address):
    """
    Gère la requête envoyée par le serveur maître:
    'langage|nom_fichier|<code_source>'
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

        print(f"[RECEPTION] Langage: {language}, Fichier: {filename} de {client_address}")

        # Compiler / Exécuter
        output = compile_and_run(language, filename, code_source)
        client_socket.sendall(output.encode('utf-8', errors='replace'))

    except Exception as e:
        error_msg = f"Erreur (serveur esclave) : {str(e)}\n"
        client_socket.sendall(error_msg.encode('utf-8', errors='replace'))
        print(f"[ERREUR] Exception dans handle_slave_client: {e}")

    finally:
        client_socket.close()

def compile_and_run(language, filename, code):
    temp_dir = "temp_codes_slave"
    os.makedirs(temp_dir, exist_ok=True)

    filepath = os.path.join(temp_dir, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(code)

    try:
        if language.lower() in ["python", ".py"]:
            cmd = [sys.executable, filepath]
        elif language.lower() in ["c", ".c"]:
            exe_file = os.path.splitext(filepath)[0] + ".exe"
            compile_proc = subprocess.run(["gcc", filepath, "-o", exe_file],
                                          capture_output=True, text=True)
            if compile_proc.returncode != 0:
                print(f"[COMPILATION C] Erreur: {compile_proc.stderr}")
                return f"Erreur de compilation C:\n{compile_proc.stderr}"
            cmd = [exe_file]
        elif language.lower() in ["c++", "cpp", ".cpp"]:
            exe_file = os.path.splitext(filepath)[0] + ".exe"
            compile_proc = subprocess.run(["g++", filepath, "-o", exe_file],
                                          capture_output=True, text=True)
            if compile_proc.returncode != 0:
                print(f"[COMPILATION C++] Erreur: {compile_proc.stderr}")
                return f"Erreur de compilation C++:\n{compile_proc.stderr}"
            cmd = [exe_file]
        elif language.lower() in ["java", ".java"]:
            compile_proc = subprocess.run(["javac", filepath],
                                          capture_output=True, text=True)
            if compile_proc.returncode != 0:
                print(f"[COMPILATION Java] Erreur: {compile_proc.stderr}")
                return f"Erreur de compilation Java:\n{compile_proc.stderr}"
            class_file = os.path.splitext(os.path.basename(filepath))[0]
            cmd = ["java", "-cp", temp_dir, class_file]
        else:
            print(f"[COMPILATION] Langage non supporté: {language}")
            return "Langage non supporté ou inconnu.\n"

        print(f"[EXECUTION] Commande: {' '.join(cmd)}")
        exec_proc = subprocess.run(cmd, capture_output=True, text=True)
        output = f"Sortie:\n{exec_proc.stdout}\n"
        if exec_proc.stderr:
            output += f"Erreurs:\n{exec_proc.stderr}\n"
        return output

    except Exception as e:
        print(f"[EXECUTION] Erreur: {e}")
        return f"Erreur lors de l'execution : {str(e)}\n"

def start_slave_server(host="0.0.0.0", port=6001):
    try:
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
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
    except Exception as e:
        print(f"[ERREUR ESCLAVE] Problème lors du démarrage sur le port {port}: {e}")

if __name__ == "__main__":
    host = "0.0.0.0"
    port = 6001
    if len(sys.argv) > 1:
        port = int(sys.argv[1])
    start_slave_server(host, port)
