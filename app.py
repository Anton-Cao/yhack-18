import time
import datetime
import json
import requests
from threading import Thread

import smartcar
from flask import Flask, redirect, request, jsonify, send_from_directory, session
from flask_cors import CORS
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse
from pymongo import MongoClient

from config import *

app = Flask(__name__, static_folder="client")
app.secret_key = "not secret"
CORS(app)

# global variable to save our access_token
access = {}

# data about each vehicle
data_readings = {}

# list of phone numbers of potential victims
victims = []

smartcar_client = smartcar.AuthClient(
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    redirect_uri=REDIRECT_URI,
    scope=["read_vehicle_info", "read_odometer", 'read_location'],
    test_mode=TEST_MODE,
)

twilio_client = Client(TWILIO_SID, TWILIO_AUTH_TOKEN)

mongo_client = MongoClient(MONGO_URI)
db = mongo_client.get_database()

@app.route("/", methods=["GET"])
def home():
    return app.send_static_file("Yhacks.html")

@app.route("/<path:path>", methods=["GET"])
def serve_file(path):
    return send_from_directory("client", path)

@app.route("/register", methods=["GET"])
def register():

    email = request.args.get("email")
    psw = request.args.get("psw")
    psw_repeat = request.args.get("psw-repeat")
    phone = request.args.get("phone")

    user = db.users.find_one({"email": email})
    if user:
        return "user with email already exists", 500
    if psw != psw_repeat:
        return "passwords do not match", 500

    db.users.insert_one({
        "email": email,
        "psw": psw,
        "phone": phone,
        "uids": []
    })

    session["email"] = email
    session["phone"] = phone

    return redirect("/")

@app.route("/login", methods=["GET"])
def login():

    email = request.args.get("email")
    psw = request.args.get("psw")

    user = db.users.find_one({"email" : email})
    if not user or user.get("psw") != psw:
        return "incorrect password"
    else:
        session["email"] = email
        session["phone"] = user.get("phone")
        return redirect("/")

@app.route("/logout", methods=["GET"])
def logout():
    session.clear()
    return redirect("/")

@app.route("/whoami", methods=["GET"])
def whoami():
    if "email" not in session:
        return "not logged in"
    user = db.users.find_one({"email": session.get("email")})
    if not user:
        return "not logged in"
    result = "<h1>Email</h1>"
    result += f"<p>{session.get('email')}</p>"
    result += "<h1>Phone number</h1>"
    result += f"<p>{session.get('phone')}</p>"
    result += "<h1>UIDs</h1>"
    result += "<ul>" 
    for user_id in user.get('uids'):
        result += f"<li>{user_id}</li>"
        token = access[user_id]["access_token"]
        vehicle_ids = smartcar.get_vehicle_ids(
            token)["vehicles"]
        result += "<ul>"
        for vehicle_id in vehicle_ids:
            result += f"<li>{vehicle_id}</li>"
        result += "</ul>"
    result += "</ul>"
    return result

@app.route("/register_vehicle", methods=["GET"])
def register_vehicle():
    if "email" in session:
        auth_url = smartcar_client.get_auth_url()
        return redirect(auth_url)
    else:
        return redirect("/signin.html")

@app.route("/exchange", methods=["GET"])
def exchange():
    global access

    email = session.get("email")
    if not email:
        return "not logged in"

    code = request.args.get("code")

    user_access = smartcar_client.exchange_code(code)
    user_id = smartcar.get_user_id(user_access["access_token"])
    user_access["uid"] = user_id
    db.access.insert_one(user_access)
    access[user_id] = user_access

    user = db.users.find_one({"email": email})
    uids = user.get("uids")
    uids.append(user_id)
    db.users.update_one({"email": email}, {"$set": {"uids" : uids}})
    return "", 200


@app.route("/vehicles", methods=["GET"])
def vehicles():
    global access
    
    if "email" not in session:
        return "not logged in"
    email = session.get("email")
    user = db.users.find_one({"email" : email})
    uids = user.get("uids")

    vehicles = []

    for user_id in uids:
        token = access[user_id]["access_token"]
        vehicle_ids = smartcar.get_vehicle_ids(
            token)["vehicles"]
    
        for vehicle in [smartcar.Vehicle(vehicle_id, token) for vehicle_id in vehicle_ids]:
            vehicle_info = vehicle.info()
            print(vehicle_info)
            vehicles.append(f"{vehicle_info['make']} {vehicle_info['model']}")
    return vehicles

#@app.route("/vehicles", methods=["GET"])
#def vehicles():
#    global access
#
#    result = "<ul>"
#    for user_id in access:
#        result += f"<li>user: {user_id}</li>"
#        token = access[user_id]["access_token"]
#        vehicle_ids = smartcar.get_vehicle_ids(
#            token)["vehicles"]
#    
#        result += "<ul>"
#        for vehicle in [smartcar.Vehicle(vehicle_id, token) for vehicle_id in vehicle_ids]:
#            result += f"<li>{vehicle.info()}</li>"
#        result += "</ul>"
#    result += "</ul>"
#    return result


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
    for phone, time in victims:
        result += f"<li>{phone} {time}</li>"
    result += "</ul>"
    return result


@app.route("/sms", methods=["GET","POST"])    
def handle_sms():
    global victims

    ans = request.values.get("Body", None)
    number = request.values.get("From", None)
    resp = MessagingResponse()
    if ans.lower() in ["yes", "yep", "ye", "y"]:
        victims = [victim for victim in victims if victim["phone"] != number] # remove from victims list
        resp.message("Okay Cool!")
    else:
        resp.message("Help is on the way.")
    return str(resp)


def check_on_driver(number='+12039182330'):
    """Send text to phone number to check if driver is ok"""
    global victims

    # add victim to watch list
    victims.append({
        "phone": number,
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
                vehicle_type = vehicle.info()['make']
                print(resp_location)
                print(vehicle_type)
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
                    alert_weather_changes(vehicle_type)

def alert_weather_changes(vehicle_type, number='+12039182330'):
    """Send text to phone number about the weather"""
    global weatherDescription

    weathermessage = twilio_client.messages \
        .create(
        body="weather condition alert: your {} is under {}".format(vehicle_type, weatherDescription),
        from_='+14752758132',
        to=number
    )
    print(weathermessage.sid)

if __name__ == '__main__':
    # check_on_driver()
    # t1 = Thread(target=detect_accidents)
    # t1.start()
    # t2 = Thread(target=detect_weather)
    # t2.start()
    app.run(port=8000)
    # t1.join()
    # t2.join()

