from twilio.rest import Client


# Your Account Sid and Auth Token from twilio.com/console
account_sid = 'AC8490bbaabe460d921d30c8017aef4de2'
auth_token = '655c18d7ec1eed26b6c8b115ccbc53c1'
client = Client(account_sid, auth_token)

def writeMess():
    try:
        message = client.messages \
                        .create(
                             body="Are you okay?",
                             # We have to buy a number to use it for the project
                             from_='+15017122661',
                             to='+12039182330'
                         )
        print(message.sid)
    except Exception as e:
        print(e)
    