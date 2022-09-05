import cv2
import pickle

from flask_cors import CORS
import random
import cvzone
import numpy as np
from flask import Flask, render_template, request, redirect, url_for, session, Response,jsonify,send_file
from datetime import datetime,timedelta
from flask_mysqldb import MySQL
from flask_mail import Mail, Message
from flask_qrcode import QRcode
import io
import os
import json
from PIL import Image, ImageDraw
from base64 import b64encode

app=Flask(__name__)
CORS(app)
app.secret_key = 'your secret key'
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = ''
app.config['MYSQL_DB'] = 'smartiotparking'
app.config['MAIL_SERVER']='mail.hieroglyphs.pk'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USERNAME'] = 'smartiot@hieroglyphs.pk'
app.config['MAIL_PASSWORD'] = 'checkiot123'
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USE_SSL'] = True

mysql = MySQL(app)
mail = Mail(app)
qrcode = QRcode(app)



# Video feed
cap = cv2.VideoCapture('carPark.mp4')

with open('CarParkPos', 'rb') as f:
    posList = pickle.load(f)

width, height = 107, 48

freeSpaceList=[]
bookedSpace = []

def generate_frames():
    def checkParkingSpace(imgPro):
        spaceCounter = 0
        temp = 0
        tempFree = []
        for pos in posList:

            x, y = pos

            imgCrop = imgPro[y:y + height, x:x + width]
            # cv2.imshow(str(x * y), imgCrop)
            count = cv2.countNonZero(imgCrop)

            if count < 900 and temp not in bookedSpace:
                color = (0, 255, 0)
                thickness = 2
                spaceCounter += 1
                tempFree.append(temp)

            elif temp in bookedSpace:
                color = (255, 0, 0)
                thickness = 2
                cvzone.putTextRect(img, "Booked", (x +10, y + 30), scale=1.5,
                                   thickness=2, offset=0, colorR=(255, 0, 0))

                if temp in tempFree:
                    tempFree.remove(temp)

            else:
                color = (0, 0, 255)
                thickness = 2
                if temp in tempFree:
                    tempFree.remove(temp)

            cv2.rectangle(img, pos, (pos[0] + width, pos[1] + height), color, thickness)

            cvzone.putTextRect(img, str(count), (x, y + height - 3), scale=1,
                               thickness=2, offset=0, colorR=color)

            cvzone.putTextRect(img, str(temp), (x + width - 30, y + 20), scale=1.5,
                               thickness=2, offset=0, colorB=(0, 0, 255))


            global freeSpaceList
            freeSpaceList = tempFree

            temp = temp + 1
        cvzone.putTextRect(img, f'Free: {spaceCounter}/{len(posList)}', (100, 50), scale=3,
                           thickness=5, offset=20, colorR=(0, 200, 0))

    while True:
        if cap.get(cv2.CAP_PROP_POS_FRAMES) == cap.get(cv2.CAP_PROP_FRAME_COUNT):
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        success, img = cap.read()
        imgGray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        imgBlur = cv2.GaussianBlur(imgGray, (3, 3), 1)
        imgThreshold = cv2.adaptiveThreshold(imgBlur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                             cv2.THRESH_BINARY_INV, 25, 16)
        imgMedian = cv2.medianBlur(imgThreshold, 5)
        kernel = np.ones((3, 3), np.uint8)
        imgDilate = cv2.dilate(imgMedian, kernel, iterations=1)

        checkParkingSpace(imgDilate)
        #cv2.imshow("Image", img)
        # cv2.imshow("ImageBlur", imgBlur)
        # cv2.imshow("ImageThres", imgMedian)
        cv2.waitKey(15)

        ret, buffer = cv2.imencode('.jpg', img)
        img = buffer.tobytes()
        # print(b'--img\r\n'
        #                    b'Content-Type: image/jpeg\r\n\r\n' + img + b'\r\n')
        # yield (b'--img\r\n'b'Content-Type: image/jpg\r\n\r\n' + img + b' \r\n')
        yield(b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + img + b'\r\n')
# print(generate_frames())

@app.route('/',methods=['POST', 'GET'])
def index():
    global freeSpaceList,bookedSpace
    usableSpaceList=[]
    for i in freeSpaceList:
        if i not in bookedSpace:
            usableSpaceList.append(i)

    return usableSpaceList


@app.route('/allslots',methods=['POST', 'GET'])
def allSlots():
    if request.method == 'GET':
        data = {
            "total": len(posList),
        }
        return jsonify(data)


@app.route('/book',methods=['POST', 'GET'])
def book():
    if request.method == 'GET':
        args = request.args
        print(args)
        id = args.get('id')
        cursor = mysql.connection.cursor()
        cursor.execute('SELECT * FROM `bookings`  INNER JOIN `user` on bookings.user_id = user.id where user_id = %s',(id,))
        # Fetch one record and return result
        bookings = cursor.fetchall()
        bookingdata = []
        for row in bookings:
            print(row)
            with open(("qrcodes/code" + str(row[0]) + ".png"), "rb") as f:
                content = f.read()
            my_list = list(row)
            print(content)
            my_list.append((b64encode(content)).decode('utf-8'))
            row = tuple(my_list)
            bookingdata.append(row)

        data = {
            "bookings": bookingdata,
        }
        return jsonify(data)

    if request.method == 'POST':
        req = request.get_json()
        print(req)
        parking_no = req['parking_no']
        car_number = req['car_number']
        user_id = req['user_id']
        amount = req['amount']
        expiryTimeDate = datetime.now() + timedelta(days=1)
        status="booked"

        cursor = mysql.connection.cursor()
        record = [parking_no, car_number, user_id, expiryTimeDate, status, amount]
        cursor.execute(" INSERT INTO bookings (parking_no,car_number,user_id,expiry,status,amount) values(%s,%s,%s,%s,%s,%s)",
                       record)

        id = cursor.lastrowid
        mysql.connection.commit()
        cursor.close()
        data="Parking No: "+parking_no+", Car Number: "+car_number+",user id: "+user_id+",expiry date: "+str(expiryTimeDate)+",status: "+status+",amount: "+amount
        img = qrcode((data), mode="raw")
      #  image = Image.new("RGB", (300, 50))
        with open(("qrcodes/code"+str(id)+".png"), "wb") as f:
            f.write(img.getbuffer())
        print(img)
        return send_file(img, mimetype="image/png")


@app.route('/video')
def video():
    global bookedSpace
    cursor = mysql.connection.cursor()
    booked = 'booked'
    cursor.execute('SELECT * FROM bookings WHERE status = %s ', (booked,))
    bookings = cursor.fetchall()


    for row in bookings:
       bookedSpace.append(row[1])

    print(bookedSpace)

    cursor.close()
    return Response(generate_frames(),mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/signup', methods=['POST', 'GET'])
def signup():
    if request.method == 'GET':
        return "signup via the signup Form"

    if request.method == 'POST':
        req = request.get_json()
        fname = req['first_name']
        lname = req['last_name']
        phone = req['phone_number']
        email = req['email']
        password = random.randint(1000, 9999)
        print(password)
        cursor = mysql.connection.cursor()
        record = [fname,lname,phone,email,password]
        cursor.execute(" INSERT INTO user (first_name,last_name,phone_number,email,password) values(%s,%s,%s,%s,%s)",record)
        mysql.connection.commit()
        cursor.close()
        if(email):
            msg = Message(
                'Welocome to SMART CAR PARKING IOT, Your generated otp is:'+ str(password),
                sender='smartiot@hieroglyphs.pk ',
                recipients=[email]
            )
            msg.body = 'Hello Flask message sent from Flask-Mail'
            mail.send(msg)
        return f"Done!!"



@app.route('/login', methods=['POST', 'GET'])
def login():
    # Output message if something goes wrong...
    msg = ''
    # Check if "username" and "password" POST requests exist (user submitted form)
    req = request.get_json()
    if request.method == 'POST':
        # Create variables for easy access
        email = req['email']
        password = req['password']
        #print(email)
        #print(password)
        # Check if account exists using MySQL
        cursor = mysql.connection.cursor()
        cursor.execute('SELECT * FROM user WHERE email = %s AND password = %s', (email, password,))
        # Fetch one record and return result
        account = cursor.fetchone()
        #print(account)
        # If account exists in accounts table in out database
        if account:
            # Create session data, we can access this data in other routes
          #  session['loggedin'] = True
            #session['id'] = account['id']
            #session['email'] = account['email']
            # Redirect to home page
            data = {
                "id": account[0],
            }
            print(data)
            return jsonify(data)
        else:
            # Account doesnt exist or username/password incorrect
            msg = 'Incorrect username/password!'
            # Show the login form with message (if any)
            data = {
                "message": "invalid credentials",
            }
            return jsonify(data)

@app.route('/user',methods=['POST', 'GET'])
def user():
    if request.method == 'GET':
        args = request.args
        id = args.get('id')
        cursor = mysql.connection.cursor()
        cursor.execute('SELECT * FROM `user` where id = %s', (id,))
        # Fetch one record and return result
        user = cursor.fetchone()
        data = {
            "user": user,
        }
        return jsonify(data)

@app.route('/home', methods=['GET', 'POST'])
def home():
   return render_template('index.html')


if __name__=="__main__":
    app.run(host='0.0.0.0', debug=True)