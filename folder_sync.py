import socket
import os
import sys

sys.setrecursionlimit(1000)

EXCLUDED = {"desktop.ini"}

class File():
    def __init__(self, name, location):
        location = location.strip()
        if not location[-1] == "/":
            location += "/"
        self.name = name
        self.location = location
        self.path = location + name
        self.children = []

        if (os.path.isdir(self.path)):
            for child_name in os.listdir(self.path):
                if child_name in EXCLUDED:
                    continue
                self.children.append(File(child_name, self.path))
            self.children.sort(key = lambda child: (len(child.children) > 0, child.name))

    def file_from_path(path):
        name = path.split("/")[-1]
        location = "/".join(path.split("/")[:-1])
        return File(name, location)

    def path_from_root(self, root):
        return self.path[len(root.path):]

    def to_string(self):
        output = self.name + "\n"
        for i, child in enumerate(self.children):
            first_line = True
            for line in child.to_string().split("\n"):
                prefix = [["|   ", "    "],
                          ["|-- ", "`-- "],][first_line][i == len(self.children) - 1]
                output += prefix + line + "\n"
                first_line = False
        return output.strip()
    
    def join(*paths):
        output = ""
        for i, path in enumerate(paths[:-1]):
            if path == "":
                continue
            if i != 0:
                if path[0] == "/":
                    path = path[1:]
            path = path.replace("\\", "/")
            if not path[-1] == "/":
                path += "/"
            output += path
        return output + paths[-1].replace("/", "")

    
    __repr__ = to_string
    __str__ = to_string

a = lambda a, b: bytes([a[i] & b[i] for i in range(len(a))])
o = lambda a, b: bytes([a[i] | b[i] for i in range(len(a))])
pack = lambda buffer, length: b"\00" * (length - len(buffer)) + buffer

class SyncSocket():
    port = 3012
    def __init__(self, root, is_server = True, ip = ""):
        self.root = root
        os.chdir(self.root.path)
        self.is_server = is_server
        self.connection = socket.socket()
        if is_server:
            self.connection.bind(("0.0.0.0", SyncSocket.port))
            self.connection.listen(1)
            self.connection, address = self.connection.accept()
            print("Connected to " + str(address))
        else:
            self.connection.connect((ip, SyncSocket.port))
            self.listen_loop()
    
    def listen_loop(self):
        while True:
            method = ""
            while method == "":
                method, header, buffer = self.receive()
            SyncSocket.commands[method](self, header, buffer)

    def receive_packet(self, packet_size):
        packet = b''
        while len(packet) < packet_size:
            packet += self.connection.recv(packet_size - len(packet))
        return packet

    def receive_buffer(self, buffer_length):
        buffer = b''
        for i in range(buffer_length // 1024):
            buffer += self.receive_packet(1024)
        buffer += self.receive_packet(buffer_length % 1024)
        return buffer

    def receive(self):
        header_length = int.from_bytes(self.receive_packet(8))
        buffer_length = int.from_bytes(self.receive_packet(8))
        header = self.receive_packet(header_length).decode()
        buffer = self.receive_buffer(buffer_length)
        if " " in header:
            i = header.index(" ") 
            return header[:i], header[i + 1:], buffer
        return header, "", buffer

    def file(self, header, buffer):
        if not os.path.exists(File.join(self.root.path, *header.split("/")[:-1])):
            os.makedirs(File.join(self.root.path, *header.split("/")[:-1]))
        with open(File.join(self.root.path, *header.split("/")), "wb") as file:
            file.write(buffer)
        self.send("RESPONSE", "", b't')

    def close(self, header, buffer):
        self.connection.close()
        print("Folder sync complete.")
        quit()

    def get(self, header, buffer):
        self.send_file(File.file_from_path(File.join(self.root.path, *header.split("/"))))

    def peek(self, header, buffer):
        output = False
        server_m_time = float(buffer.decode())
        path = File.join(self.root.path, header[1:])
        if os.path.exists(path):
            m_time = os.path.getmtime(path)
            output = m_time > server_m_time

        self.send("RESPONSE", "", b't' if output else b'f')

    def send(self, command, header, buffer):
        header = (command + " " + header).encode()

        self.connection.send(int.to_bytes(len(header), length = 8))
        self.connection.send(int.to_bytes(len(buffer), length = 8))
        self.connection.send(header)
        self.connection.send(buffer)

    def send_file(self, file):
        relative_path, file = file.path_from_root(self.root), open(file.path, "rb")
        self.send("FILE", relative_path, file.read())

    def send_close(self):
        self.send("CLOSE", "", b"")
        self.connection.close()
        print("Folder sync complete.")
        quit()

    def sync(self):
        self.sync_folder(self.root)
        self.send_close()

    def sync_folder(self, folder):
        for child in folder.children:
            if os.path.isdir(child.path):
                self.sync_folder(child)
            else:
                self.sync_file(child)

    def sync_file(self, file):
        relative_path = file.path_from_root(self.root)
        m_time = os.path.getmtime(file.path)
        self.send("PEEK", relative_path, str(m_time).encode())
        response = self.receive()
        if response[2] == b't':
            self.send("GET", relative_path, b'')
            self.file(*self.receive()[1:])
        else:
            self.send_file(file)
            self.receive()

    commands = {"FILE": file, "GET": get, "CLOSE": close, "PEEK": peek}

if __name__ == "__main__":
    is_server = "n" not in input("Is server? (Y/n): ").strip().lower()
    path = input("Folder path: ")
    ip = ""
    if not is_server:
        ip = input("Server IP: ")
    sync_socket = SyncSocket(File.file_from_path(path), is_server, ip)
    if is_server:
        sync_socket.sync()