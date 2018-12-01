import smartcar
from flask import Flask, redirect, request, jsonify
from flask_cors import CORS
from config import *

import time

import os

app = Flask(__name__)
CORS(app)

# global variable to save our access_token
access = {}

client = smartcar.AuthClient(
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    redirect_uri=REDIRECT_URI,
    scope=['read_vehicle_info'],
    test_mode=True
)


@app.route('/login', methods=['GET'])
def login():
    auth_url = client.get_auth_url()
    return redirect(auth_url)


@app.route('/exchange', methods=['GET'])
def exchange():
    code = request.args.get('code')

    # access our global variable and store our access tokens
    global access
    # in a production app you'll want to store this in some kind of
    # persistent storage

    user_access = client.exchange_code(code)
    user_id = smartcar.get_user_id(user_access["access_token"])
    access[user_id] = user_access

    return '', 200

@app.route('/vehicles', methods=['GET'])
def vehicles():
    global access

    result = ""
    for user_id in access:
        result += f"user: {user_id}\n"
        token = access[user_id]["access_token"]
        vehicle_ids = smartcar.get_vehicle_ids(
            token)['vehicles']
    
        for vehicle in [smartcar.Vehicle(id, token) for id in vehicle_ids]:
            result += f"{vehicle.info()}\n"
    return result

def detect_accidents():
    # access our global variable to retrieve our access tokens
    global access

    while True:
        for user_id in access:
            token = access[user_id]["access_token"]
            vehicle_ids = smartcar.get_vehicle_ids(
                token)['vehicles']
            for vehicle in [smartcar.Vehicle(id, token) for id in vehicle_ids]:
                response_1= vehicle.odometer()
                time.sleep(5)
                response_2= vehicle.odometer()
                time.sleep(5)
                response_3= vehicle.odometer()
                v1=(response_2-response_1)/0.05
                v2=(response_3-response_2)/0.05
                if(v2-v1>50):
                    pass #I want to send the client a message to se if he is okay

if __name__ == '__main__':
    app.run(port=8000)
<<<<<<< HEAD
    detect_accidents()
=======
    detect_accidents()
>>>>>>> 0bb527e5a6b851a288156b1928f0448a0cdaf9b2
