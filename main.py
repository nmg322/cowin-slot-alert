#!/usr/bin/env python
# Author: NMG (20210522)
# Script to check & inform (in telegram chat) about vaccine availability


# import libraries
import sys, os, logging, time, datetime, json, requests, threading

import telegram # $ pip install -U python-telegram-bot


# CONSTANTS & Setup
# enable logging - required for telegram package
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)

START_TIME = datetime.datetime.utcnow()
DISTRICT_ID = 316 # ID of district you want to check, default is Rewa, Madhya Pradesh

CHECK_AFTER = 5 # check for vaccine slot after every this many seconds (shouldn't be less than 5)
REFOUND_AFTER = 6 # to update the info about already found slot (and re-send alert) if not filled after this many hours

# To find chat_id:
# 1. Post one message (eg. /start) from User to the Bot (user shoud have already used /start on BOT)
# 2. Open this page - https://api.telegram.org/bot<BOT_TOKEN>/getUpdates
# 3. Find this message and navigate to the result->message->chat->id key.
BOT_TOKEN = os.getenv('BOT_TOKEN', None) # token to access telegram bot HTTP API
ALERT_CHAT_ID = os.getenv('ALERT_CHAT_ID', None) # ID of telegram chat to send the alert
ERROR_CHAT_ID = os.getenv('ERROR_CHAT_ID', None) # ID of telegram chat to send error message
if any(list(map(lambda x: x is None, [BOT_TOKEN, ALERT_CHAT_ID, ERROR_CHAT_ID]))):
    print(f"ERROR> BOT_TOKEN/ALERT_CHAT_ID/ERROR_CHAT_ID environment variables not set correctly. Exiting...")
    sys.exit(1)

FOUND_SLOTS_SAVEPATH = "previouslyFoundSlots.json" # load/save previously found slots from/to this file
# load/initialize dict of previously found slots: {session_id of found slots: their found time in UTC}
if os.path.isfile(FOUND_SLOTS_SAVEPATH):
    with open(FOUND_SLOTS_SAVEPATH, 'r') as fp:
        FOUND_SLOTS = json.load(fp)
else:
    FOUND_SLOTS = dict()


def main_loop(telegram_bot):
    # HTTP GET request details to get vaccination sessions by district for 7 days
    # source: Cowin API - https://apisetu.gov.in/public/marketplace/api/cowin
    url = f"https://cdn-api.co-vin.in/api/v2/appointment/sessions/public/calendarByDistrict"
    params = {
                "district_id": DISTRICT_ID,
                "date": (START_TIME + datetime.timedelta(hours=5, minutes=30)).strftime("%d-%m-%Y") # date (IST) to check from for vaccine
            }
    headers = {
        "Host": "cdn-api.co-vin.in",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:88.0) Gecko/20100101 Firefox/88.0",
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.5",
        "Origin": "https://www.cowin.gov.in",
        "Referer": "https://www.cowin.gov.in/",
    }

    days_passed = datetime.timedelta(days=0) # used to update date parameter of HTTP request
    request_no = 0 # initialize request # to 0
    while True:
        # update start date to check from for vaccine after one day
        if (datetime.datetime.utcnow() - START_TIME  - days_passed > datetime.timedelta(days=1)):
            days_passed += datetime.timedelta(days=1)
            params['date'] = (START_TIME + datetime.timedelta(hours=5, minutes=30) + days_passed).strftime("%d-%m-%Y")
            print('\n' + '*'*100)
            print(f"Updated date (IST) to check from for vaccine to {params['date']} at {datetime.datetime.utcnow()}")
            print('*'*100 + '\n')

        request_no += 1
        try:
            response = None
            message_string = ""
            # start a session
            with requests.session() as session:
                response = session.get(url=url, params=params, headers=headers)
                response_json = response.json()
                # parse response_json to generate message
                msg_bullet_no = 0 # initialize session # to 0
                for center in response_json['centers']:
                    for session in center['sessions']:
                        if (session['min_age_limit'] < 45) and (session['available_capacity'] > 0):
                            if (session['session_id'] in FOUND_SLOTS) and (datetime.datetime.utcnow() - datetime.datetime.strptime(FOUND_SLOTS[session['session_id']], "%Y-%m-%d %H:%M:%S.%f") < datetime.timedelta(hours=REFOUND_AFTER)):
                                continue

                            FOUND_SLOTS[session['session_id']] = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")
                            msg_bullet_no += 1
                            message_string += '\n'
                            message_string += f"{msg_bullet_no}) Center Name: {center['name']}\n"
                            message_string += f"Address: {center['address']}\n"
                            message_string += f"Pincode (Block): {center['pincode']} ({center['block_name']})\n"
                            message_string += f"Vaccine Name: {session['vaccine']}\n"
                            message_string += f"Total {session['available_capacity']} slots on {session['date']} for {session['min_age_limit']}+\n"
                            message_string += f"(Dose1: {session['available_capacity_dose1']}, Dose2: {session['available_capacity_dose2']})\n"
            # send message to telegram chat
            if len(message_string)>0:
                message_string += "\nCoWIN: https://selfregistration.cowin.gov.in\n"
                telegram_bot.sendMessage(chat_id=ALERT_CHAT_ID, text=message_string)
        except Exception as err:
            message_string = f"\nERROR (in request #{request_no}) >\n{err}\n"
            if response is not None:
                message_string += f"\nRESPONSE >\n{response.text}\n"
            # noify admin about error
            try:
                telegram_bot.sendMessage(chat_id=ERROR_CHAT_ID, text=message_string)
            except:
                message_string += f"\nCan't notify about this in telegram!\n"

        # print message on terminal
        print('\n' + '*'*100)
        print(f"Sending request #{request_no} at {datetime.datetime.utcnow()} to check slot availability:-")
        print(message_string)
        print('*'*100 + '\n')

        time.sleep(CHECK_AFTER)

if __name__ == "__main__":
    # creat telegram bot object
    leviLeft_1Bot = telegram.Bot(token=BOT_TOKEN)

    try:
        main_loop(leviLeft_1Bot)
    except Exception as err:
        print(f"Exception: {err}")
    finally:
        with open(FOUND_SLOTS_SAVEPATH, 'w') as fp:
            json.dump(FOUND_SLOTS, fp, indent=4)
