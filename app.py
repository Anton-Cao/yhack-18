import time
import datetime
import os
from threading import Thread

import smartcar
from flask import Flask, redirect, request, jsonify
from flask_cors import CORS

from config import *
from send_sms import writeMess


app = Flask(__name__)
CORS(app)

# global variable to save our access_token
access = {}

# data about each vehicle
data_readings = {}

client = smartcar.AuthClient(
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    redirect_uri=REDIRECT_URI,
    scope=["read_vehicle_info", "read_odometer"],
    test_mode=True
)


@app.route("/login", methods=["GET"])
def login():
    auth_url = client.get_auth_url()
    return redirect(auth_url)


@app.route("/exchange", methods=["GET"])
def exchange():
    code = request.args.get("code")

    # access our global variable and store our access tokens
    global access
    # in a production app you"ll want to store this in some kind of
    # persistent storage

    user_access = client.exchange_code(code)
    user_id = smartcar.get_user_id(user_access["access_token"])
    access[user_id] = user_access

    return "", 200


@app.route("/vehicles", methods=["GET"])
def vehicles():
    global access

    result = ""
    for user_id in access:
        result += f"user: {user_id}\n"
        token = access[user_id]["access_token"]
        vehicle_ids = smartcar.get_vehicle_ids(
            token)["vehicles"]
    
        for vehicle in [smartcar.Vehicle(vehicle_id, token) for vehicle_id in vehicle_ids]:
            result += f"{vehicle.info()}\n"
    return result


@app.route("/data", methods=["GET"])
def data():
    global access
    global data_readings

    return str(access) + str(data_readings)

    print(data_readings)

    result = ""
    for vehicle_id, data in data_readings.items():
        result += f"vehicle: {vehicle_id}, data: {data}"
    return result


def detect_accidents():
    global access
    global data_readings

    print("detecting accidents")
    while True:
        time.sleep(1)

        for user_id in access:
            token = access[user_id]["access_token"]
            vehicle_ids = smartcar.get_vehicle_ids(
                token)["vehicles"]
            for vehicle_id in vehicle_ids:
                print(f"vehicle id: {vehicle_id}")
                vehicle = smartcar.Vehicle(vehicle_id, token)
                odometer_data = vehicle.odometer()
                odometer_reading = odometer_data['data']['distance']
                measurement_time = odometer_data['age']
                print(f"odometer: {odometer_reading}, time: {measurement_time}")

                if vehicle_id in data_readings and "time" in data_readings[vehicle_id]:
                    # time since last measurement in seconds
                    time_elapsed = (measurement_time - data_readings[vehicle_id]["time"]) / datetime.timedelta(seconds=1)
                    if time_elapsed >= 10: # if measurement was a long time ago (> 10 seconds), reset
                        data_readings[vehicle_id] = {
                            "odometer": odometer_reading,
                            "time": measurement_time,
                            "speed": None,
                        }
                    else: # calculate the speed
                        distance = odometer_reading - data_readings[vehicle_id]["odometer"] # kilometers
                        speed = (distance / time_elapsed) * 60 * 60 # kilometers per hour
                        prev_speed = data_readings[vehicle_id].get("speed")
                        if prev_speed != None:
                            print(f"cur speed: {speed}, prev speed: {prev_speed}")
                            if min(prev_speed, speed) < 0 or max(prev_speed, speed) > 200: # not real data
                                print("test car, fake data")
                            elif prev_speed >= 80 and speed <= 10: # if decelerated from > 80km/h to < 10km/h, check if accident
                                print("accident warning")
                                writeMess()
                        data_readings[vehicle_id] = {
                            "odometer": odometer_reading,
                            "time": measurement_time,
                            "speed": speed,
                        }
                else: # no recorded data yet for this vehicle
                    data_readings[vehicle_id] = {
                        "odometer": odometer_reading,
                        "time": measurement_time,
                        "speed": None,
                    }
                print("\n")


if __name__ == "__main__":
    t = Thread(target=detect_accidents)
    t.start()
    app.run(port=8000, debug=True, use_reloader=False)
    t.join()
