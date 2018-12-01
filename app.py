import time
import datetime
import os
from threading import Thread

import smartcar
from flask import Flask, redirect, request, jsonify
from flask_cors import CORS
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse

from config import *

app = Flask(__name__)
CORS(app)

# global variable to save our access_token
access = {}

# data about each vehicle
data_readings = {}

# list of phone numbers of potential victims
victims = []

client = smartcar.AuthClient(
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    redirect_uri=REDIRECT_URI,
    scope=["read_vehicle_info", "read_odometer"],
    test_mode=TEST_MODE
)

twilio_client = Client(TWILIO_SID, TWILIO_AUTH_TOKEN)

@app.route("/", methods=["GET"])
def home():
    return redirect("/login")


@app.route("/login", methods=["GET"])
def login():
    auth_url = client.get_auth_url()
    return redirect(auth_url)


@app.route("/exchange", methods=["GET"])
def exchange():
    global access

    code = request.args.get("code")

    user_access = client.exchange_code(code)
    user_id = smartcar.get_user_id(user_access["access_token"])
    access[user_id] = user_access

    return "", 200


@app.route("/vehicles", methods=["GET"])
def vehicles():
    global access

    result = "<ul>"
    for user_id in access:
        result += f"<li>user: {user_id}</li>"
        token = access[user_id]["access_token"]
        vehicle_ids = smartcar.get_vehicle_ids(
            token)["vehicles"]
    
        result += "<ul>"
        for vehicle in [smartcar.Vehicle(vehicle_id, token) for vehicle_id in vehicle_ids]:
            result += f"<li>{vehicle.info()}</li>"
        result += "</ul>"
    result += "</ul>"
    return result


@app.route("/data", methods=["GET"])
def data():
    global access
    global data_readings

    result = "<ul>"
    for vehicle_id, data in data_readings.items():
        result += f"<li>vehicle: {vehicle_id}, data: {data}</li>"
    result += "</ul>"
    return result


@app.route("/victims", methods=["GET"])
def show_victims():
    global victims

    result = "<ul>"
    for number, time in victims:
        result += f"<li>{number} {time}</li>"
    result += "</ul>"
    return result


@app.route("/sms", methods=["GET","POST"])    
def handle_sms():
    global victims

    ans = request.values.get("Body", None)
    number = request.values.get("From", None)
    resp = MessagingResponse()
    if ans == "yes":
        victims = [pair for pair in victims if victims[0] != number] # remove from victims list
        resp.message("Okay Cool!")
    else:
        resp.message("Help is on the way.")
    return resp


def check_on_driver(number='+12039182330'):
    """Send text to phone number to check if driver is ok"""
    global victims

    victims.append((number, datetime.datetime.now())) # add victim to watch list

    message = twilio_client.messages \
        .create(
            body="Are you okay?",
            from_='+14752758132',
            to=number
        )
    print(message.sid)


def detect_accidents():
    global access
    global data_readings

    print("detecting accidents")
    while True:
        if len(access) == 0: # no cars
            time.sleep(1)
            continue

        for user_id in access:
            token = access[user_id]["access_token"]
            vehicle_ids = smartcar.get_vehicle_ids(
                token)["vehicles"]
            for vehicle_id in vehicle_ids:
                print(f"vehicle id: {vehicle_id}")
                vehicle = smartcar.Vehicle(vehicle_id, token)
                odometer_data = vehicle.odometer()
                odometer_reading = odometer_data["data"]["distance"]
                measurement_time = odometer_data["age"]
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
                        print(f"cur speed: {speed}, prev speed: {prev_speed}")
                        if prev_speed != None:
                            if min(prev_speed, speed) < 0 or max(prev_speed, speed) > 200: # not real data
                                print("test car, fake data")
                            elif prev_speed >= 80 and speed <= 10: # if decelerated from > 80km/h to < 10km/h, check if accident
                                print("accident warning")
                                check_on_driver()
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
    app.run(port=8000, debug=True)
    t.join()
