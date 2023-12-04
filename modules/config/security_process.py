import socket
import time

import socket
import time

def process_function():
    timeout = 2*60
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind(('127.0.0.1', 61313))
    server_socket.listen(1)
    server_socket.settimeout(2*60)

    pin = "not entered"
    sec = 0

    try:
        print("Waiting for connection...")
        connection, address = server_socket.accept()
        print(f"Connected by {address}")
        while True:
            print(f"pin received: {pin}")
            received_data = connection.recv(1024).decode()
            print(f"Child process received: {received_data}")
            if "put" in received_data:
                pin = received_data.split("_")[1]
            if "get" in received_data:
                connection.send(pin.encode())
            if "close" in received_data:
                break
            time.sleep(1)
            sec += 1
            if sec > timeout:
                break

    except socket.timeout:
        print("Timeout reached. Closing connection and exiting.")

    finally:
        try:
            connection.close()
        except:
            print("no connection found.")
        server_socket.close()
        print("socket closed")

if __name__ == "__main__":
    process_function()




