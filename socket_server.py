import json
import socket
import tempfile
import threading
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime


# TODO LIST:
#
# - Make a more user friendly sending/listening port selection. Make an "available" chat room system where you are
#   given a list of chat rooms to join, not just selecting each listening/sending port
#   - It could be where each chat room is created by scanning for two available ports automatically that are free
#   - If one person joins the chat room, they're automatically given those ports. If another person joins, it checks
#     to see if those ports are used. If yes, it swaps the send/listen ports for that person
# - Need to figure out how to have one person connect to a "room", and then another person would be able to see
#   that room. Basically the listening port would be taken up, but the next port is open
#   - One idea is to make it so rooms can only have an even listening port, i + 1 sending port (odd). Then during
#     a port sweep, if someone sees that a listening port is being used, they'll check if the i + 1 port is either
#     pending a connection. If it's pending, that means someone is waiting on the other end to chat
#   - The weird thing is how to tell if a port is actually being used. Right now I'm looking into using a lock
#     file, which will say which ports are being used by instances of this script
# - Make a username system (maybe)


LOCK_FILE = os.path.join(tempfile.gettempdir(), "my_script.lock")
PENDING_CONNECTION_PID = -1
LOCAL_HOST_NAME = "localhost"

stop_event = threading.Event()

def load_lock_file():
    if os.path.exists(LOCK_FILE):
        with open(LOCK_FILE) as f:
            return json.load(f)
    return {}

def save_lock_file(data):
    with open(LOCK_FILE, "w") as f:
        json.dump(data, f)

def is_pid_alive_or_pending(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False

def start_listener(locks, listen_port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((LOCAL_HOST_NAME, int(listen_port)))
    s.listen()
    print(f"Listening on port {listen_port}")
    locks[listen_port] = os.getpid()
    locks[listen_port + 1] = PENDING_CONNECTION_PID
    save_lock_file(locks)
    return s

def receive_messages(server_socket):
    while not stop_event.is_set():
        try:
            connection, address = server_socket.accept()
            with connection:
                while not stop_event.is_set():
                    buf = connection.recv(1024)
                    if not buf:
                        break
                    formatted_datestring = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    print(f"\n[Received at {formatted_datestring}]: {buf.decode()}")
        except ConnectionError as e:
            print(f"Receive error: {e}")

def send_messages(sending_port):
    while not stop_event.is_set():
        message = input("Enter your message (or /quit to exit): ")
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect(('localhost', int(sending_port)))
                s.sendall(message.encode())
                if message == "/quit":
                    print("Exiting...")
                    stop_event.set()
                    break
        except ConnectionError as e:
            print(f"Send error: {e}")

def is_port_free(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("localhost", port))
            return True
        except OSError:
            return False

def find_required_ports(host, ports, required_port_count=10):
    open_ports = []
    ports_found = 0

    for port in ports:
        if is_port_free(port):
            open_ports.append(port)
            ports_found += 1
        if ports_found >= required_port_count:
            break

    if len(open_ports) > 0 and len(open_ports) % 2 != 0:
        open_ports.pop()

    return open_ports

def create_chat_room_list(open_ports):
    open_ports.sort()
    room_map = dict()
    room_count = 0

    for i in range(0, len(open_ports), 2):
        room_map[room_count] = {open_ports[i], open_ports[i+1]}
        room_count += 1

    return room_map

if __name__ == '__main__':
    locks = load_lock_file()
    locks = {p: pid for p, pid in locks.items() if is_pid_alive_or_pending(pid) or pid < 0}

    port_range = range(8061, 8099)
    open_ports = find_required_ports("localhost", port_range, 10)
    chat_rooms = create_chat_room_list(open_ports)
    print(chat_rooms)

    listen_port = input("Enter the port you want to listen on: ")
    sending_port = input("Enter the port you want to send to: ")

    server_socket = start_listener(locks, listen_port)

    with ThreadPoolExecutor(max_workers=2) as executor:
        executor.submit(receive_messages, server_socket)
        executor.submit(send_messages, sending_port)
