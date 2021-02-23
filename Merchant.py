import socket
import json
import bson
from AESFunctions import *
from Shared import *

private_key = RSA.generate(2048)
public_key = generate_to_file(private_key, 'keys/pubk_m')

if __name__ == "__main__":
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        print("Starting Merchant")
        server.bind(('127.0.0.1', M_PORT))
        server.listen()
        print('Server listening on', ('127.0.0.1', M_PORT))
        while True:
            client_conn, address = server.accept()

            # receive PKC
            data = client_conn.recv(4096)
            data = bson.BSON.decode(data)

            
            # create & send signature to client_conn
            data = hybrid_decrypt_msg(data, private_key)
            client_pubk = data["dec_text"]

            session_id = get_random_bytes(16)
            client_conn_signature = compute_signature(session_id, private_key)

            k = get_random_bytes(16)
            encrypted_session_id = aes_encrypt_msg(k, session_id)
            encrypted_client_conn_signature = aes_encrypt_msg(k, client_conn_signature)
            encrypted_k = rsa_encrypt_msg(k, RSA.importKey(client_pubk)) # Rename this to rsa_client_key

            client_conn.send(bson.BSON.encode(
                {
                    "session_id": encrypted_session_id,
                    "sid_signature": encrypted_client_conn_signature,
                    "enc_key": encrypted_k
                }
            ))
            
            #Exchange subprotocol
            #3 receive PM, PO 
            data = client_conn.recv(4096)
            data = bson.decode(data)

            #decrypt msg
            pm_po_key = rsa_decrypt_msg(data["pm_po_key"], private_key)
            pm_po = aes_decrypt_msg(pm_po_key, data["pm_po"])

            #load using bson
            loaded_pm_po = bson.decode(pm_po)
            pm = loaded_pm_po["pm"]
            po = PaymentOrder()
            po.body = loaded_pm_po["po"]

            order_info = {k:po.body[k] for k in po.body if k!='sigc'}
            
            if verify_signature(bson.encode(order_info), RSA.import_key(client_pubk), po.body["sigc"]):
                print("Order signature OK!")

            #4 send PM, SigM(Sid, PubKC, Amount)
            pg_conn = socket.socket()
            pg_conn.connect(('127.0.0.1', PG_PORT))
            sig_m = bson.BSON.encode(
                {
                    "session_id": encrypted_session_id,
                    "client_pubk": encrypted_k,
                    "amount":  po.body["amount"]
                }
            )
            pg_conn_signature = compute_signature(sig_m, private_key)
            encrypted_pg_conn_signature = aes_encrypt_msg(k, pg_conn_signature)

            pubk_pg = get_pubkey_pg()
            pubk_pg = rsa_encrypt_msg(k, pubk_pg)

            info = bson.BSON.encode(
                {
                    "payment_message": pm,
                    "sigm": sig_m,
                    "enc_k": pubk_pg
                }
            )

            encrypted_info = hybrid_encrypt_msg(info, pubk_pg)

            pg_conn.send(encrypted_info)
            print('Succesfully sent payment message to PG')
