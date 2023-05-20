import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
from firebase_admin import auth

import os

print (os.environ["FIREBASE_TYPE"])

cert = {
    "type": os.environ["FIREBASE_TYPE"],
    "project_id": os.environ["FIREBASE_PROJECT_ID"],
    "private_key_id": os.environ["FIREBASE_PRIVATE_KEY_ID"],
    "private_key": os.environ["FIREBASE_PRIVATE_KEY"].replace("\\n", "\n"),
    "client_email": os.environ["FIREBASE_CLIENT_EMAIL"],
    "client_id": os.environ["FIREBASE_CLIENT_ID"],
    "auth_uri": os.environ["FIREBASE_AUTH_URI"],
    "token_uri": os.environ["FIREBASE_TOKEN_URI"],
    "auth_provider_x509_cert_url": os.environ["FIREBASE_AUTH_PROVIDER_X509_CERT_URL"],
    "client_x509_cert_url": os.environ["FIREBASE_CLIENT_X509_CERT_URL"],
}

cred = credentials.Certificate(cert)
firebase_admin.initialize_app(cred)
db = firestore.client()


def verify_id_token(id_token):
    """
    Veryifies the id token and make email ends with @upstage.ai
    """
    decoded_token = auth.verify_id_token(id_token)
    if not decoded_token:
        return False
    
    if 'email_verified' not in decoded_token or not decoded_token['email_verified']:
        return False
    
    if 'email' not in decoded_token:
        return False
    
    email = decoded_token["email"]
    if not email.endswith("@upstage.ai"):
        return False
    
    return decoded_token

def read_collection(path):
    """
    Reads a collection and returns a list of documents.
    """
    docs = db.collection(path).stream()
    return [doc for doc in docs]


def add_doc(path, data):
    doc_ref = db.collection(path).add(data)
    return doc_ref[1].get().id


def set_doc(path, doc_id, data):
    doc_ref = db.collection(path).document(doc_id).set(data)
