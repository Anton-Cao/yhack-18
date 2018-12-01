import time
import datetime
from threading import Thread

import smartcar
from flask import Flask, redirect, request, jsonify
from flask_cors import CORS
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse
from config import *
import json

import requests

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
    scope=["read_vehicle_info", "read_odometer", 'read_location'],
    test_mode=TEST_MODE,
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
    if ans.lower() in ["yes", "yep", "ye", "y"]:
        victims = [victim for victim in victims if victim["number"] != number] # remove from victims list
        resp.message("Okay Cool!")
    else:
        resp.message("Help is on the way.")
    return str(resp)


def check_on_driver(number='+12039182330'):
    """Send text to phone number to check if driver is ok"""
    global victims

    # add victim to watch list
    victims.append({
        "number": number,
        "time": datetime.datetime.now()
    })

    message = twilio_client.messages \
        .create(
            body="Are you okay? Please respond with yes or no.",
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

def detect_weather():
    global access
    global APIKEY
    APIKEY = 'ad40ed71bf39847adcd100c62e212a68'
    global weatherDescription
    while True:
        for user_id in list(access):
            token = access[user_id]["access_token"]
            vehicle_ids = smartcar.get_vehicle_ids(token)['vehicles']

            for id in vehicle_ids:
                vehicle = smartcar.Vehicle(id, token)
                resp_location = vehicle.location()
                print(resp_location)
                #resp_location = vehicle.location()
                lat = resp_location['data']['latitude']
                print(lat, flush=True)
                lon = resp_location['data']['longitude']
                print(lon, flush=True)

                resp_weather = requests.get('https://api.openweathermap.org/data/2.5/weather?lat={}&lon={}&APPID={}'.format(lat, lon, APIKEY))
                # if resp.status_code != 200:
                #     # This means something went wrong.
                #     raise ApiErro
                #r('GET /tasks/ {}'.format(resp.status_code))
                weather = resp_weather.json()
                weatherDescription = weather['weather'][0]['description']
                weatherId = weather['weather'][0]['id']
                print(weatherDescription)
                if weatherId >= 200 and weatherId < 300 or weatherId >= 500 and weatherId < 800 :
                    alert_weather_changes()

def alert_weather_changes(number='+12039182330'):
    """Send text to phone number about the weather"""
    global weatherDescription

    weathermessage = twilio_client.messages \
        .create(
        body="weather condition alert: {}".format(weatherDescription),
        from_='+14752758132',
        to=number
    )
    print(weathermessage.sid)

if __name__ == '__main__':
    # check_on_driver()
    t1 = Thread(target=detect_accidents)
    t1.start()
    t2 = Thread(target=detect_weather)
    t2.start()
    app.run(port=8000)
    t1.join()
    t2.join()

