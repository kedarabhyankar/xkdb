import socket
import netifaces
import collections
import sys


BACKEND_PORT = 2025
BackendServer = collections.namedtuple('BackendServer', ['name', 'addr', 'backends'])
Backend = collections.namedtuple('Backend', ['name', 'type', 'user', 'time'])


def get_udp_broadcast_interfaces():
    broadcast_addresses = []

    for interface in netifaces.interfaces():
        addrs = netifaces.ifaddresses(interface)
        if socket.SOCK_DGRAM in addrs:
            addrs = addrs[socket.SOCK_DGRAM]
            for addr in addrs:
                if 'broadcast' in addr:
                    broadcast_addresses.append(addr['broadcast'])

    return broadcast_addresses

def get_connection_string(username, command, server="", backend_class=""):
    string = bytearray(b"\0" * 50)

    string[0] = b"C"
    if command == "list":
        string[1] = chr(4)
    elif command == "connect":
        string[1] = chr(9)
    else:
        raise ValueError("invalid command")

    string[2:2 + len(username)] = username.encode('utf8')
    string[18:18 + len(server)] = server.encode('utf8')
    string[34:34 + len(backend_class)] = backend_class.encode('utf8')

    return bytes(string) 

# Gets a string up to a null terminator, returning the length advanced
def get_string(s):
    string = b""
    count = 0
    for char in s:
        count += 1
        if char == b"\0":
            break
        string += char

    string = string.decode('utf8')
    return string, count

def parse_backend_response(response):
    if len(response) < 76:
        raise ValueError("Invalid response size")
    if response[0] != b"C":
        raise ValueError("Invalid response version")
    backends = []
    
    server_name = response[2:65].replace(b"\0", b"").decode('utf8')

    num_backends = response[66:75].replace(b"\0", b"").decode('utf8')
    num_backends = int(num_backends)

    read_cursor = 76
    for i in range(num_backends):
        backend_name, length = get_string(response[read_cursor:]) 
        read_cursor += length
        backend_type, length = get_string(response[read_cursor:])
        read_cursor += length

        # if the backend has a user connected
        if response[read_cursor] != b"\0":
            read_cursor += 1
            user, length = get_string(response[read_cursor:])
            read_cursor += length
            time, length = get_string(response[read_cursor:])
            read_cursor += length
        else:
            read_cursor += 1
            user = None
            time = None

        b = Backend(backend_name, backend_type, user, time)
        backends.append(b)

    return server_name, backends

def parse_port(response):
    if response[0] != b"C":
        raise ValueError("Invalid response version")

    server_name = response[2:65].replace(b"\0", b"").decode('utf8')
    port = response[76:]
    print(port)
    port = port.split()
    port = int(port[0])

    return port

def get_free_backend(backend_servers):
    for server in backend_servers:
        for backend in server.backends:
            if backend.user is None:
                return server, backend

def get_backend_servers(s, backend_class="cortex"):
    addresses = get_udp_broadcast_interfaces()
    backend_servers = []

    connection_string = get_connection_string("test", command="list", backend_class=backend_class)
    for address in addresses:
        s.sendto(connection_string, (address, BACKEND_PORT))
        response, addr = s.recvfrom(125004)
        server_name, backends = parse_backend_response(response)

        backend_server = BackendServer(server_name, addr[0], backends)
        backend_servers.append(backend_server)

    return backend_servers


def main():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    s.bind(("0.0.0.0", 0))
    s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 40000)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    backend_servers = get_backend_servers(s, backend_class="quark")
    print("Available servers: {}".format(backend_servers))

    server, backend = get_free_backend(backend_servers)
    connection_string = get_connection_string("test", command="connect", server=backend.name, backend_class=backend.type)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", 0))
    sock.sendto(connection_string, (server.addr, BACKEND_PORT))

    response, addr = sock.recvfrom(125004)
    addr = addr[0]

    sock.close()

    try:
        port = parse_port(response)
    except ValueError:
        print("Unable to connect")
        raise ValueError()

    print("Connecting to {}, backend: {}, address: {}:{}".format(server.name, backend.name, addr, port))

    # Close the udp socket
    s.close()
    # Establish a tcp connection on the provided port
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((addr, port))

    data = s.recv(1024)
    while data is not None:
        sys.stdout.write(data)

if __name__ == "__main__":
    main()
