from _datetime import datetime
import os
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Request, Depends, status, BackgroundTasks
from pydantic import BaseModel, Field
from bson import ObjectId
from typing import Optional, List
from pydantic.functional_validators import BeforeValidator
import shutil
from typing_extensions import Annotated
from fastapi.staticfiles import StaticFiles
from pymongo import MongoClient
import cloudinary
import cloudinary.uploader
import cloudinary.api
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
# from twilio.rest import Client

load_dotenv()

# Setup tags
tags_metadata = [
    {
        "name": "Manage Users",
        "description": "Operations with users. The **login** logic is also here.",
    },
    {
        "name": "Books",
        "description": "Manage items. So _fancy_ they have their own docs.",
    },
{
        "name": "Users",
        "description": "Manage items. So _fancy_ they have their own docs.",
    },
{
        "name": "Borrowing",
        "description": "Manage items. So _fancy_ they have their own docs.",
    },
{
        "name": "Borrow Request",
        "description": "Manage items. So _fancy_ they have their own docs.",
    },
]

# Configure your Cloudinary credentials
cloudinary.config(
    cloud_name=os.getenv("CLOUD_NAME"),
    api_key=os.getenv("API_KEY"),
    api_secret=os.getenv("API_SECRET")
)

# DB Config

client = MongoClient(os.getenv("MONGO_URL"))
db = client.ekeukwu

user_collection = db.user
shops_collection = db.shops
order_collection = db.orders
payment_collection = db.payments
payment_history_collection = db.payment_history

# Convert ObjectId to string
PyObjectId = Annotated[str, BeforeValidator(str)]

# Security Setup
SECRET_KEY = "1234567890"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Models

class GetUser(BaseModel):
    id: Optional[PyObjectId] = Field(alias="_id", default=None)
    name: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None

class AddUser(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None


class User(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None

class UserInDB(User):
    hashed_password: Optional[str] = None

class Token(BaseModel):
    access_token: Optional[str] = None
    token_type: Optional[str] = None

class TokenData(BaseModel):
    email: Optional[str] = None

class LoginUser(BaseModel):
    email: Optional[str] = None
    password: Optional[str] = None


class GetShops(BaseModel):
    id: Optional[PyObjectId] = Field(alias="_id", default=None)
    title: Optional[str] = None
    description: Optional[str] = None
    address: Optional[str] = None
    price: Optional[str] = None
    images: Optional[List[Optional[str]]] = None
    availability: Optional[str] = None


class AddShops(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    address: Optional[str] = None
    price: Optional[str] = None
    images: Optional[List[Optional[str]]] = None
    availability: Optional[str] = None

class AddOrder(BaseModel):
    user_id: Optional[str] = None
    products: Optional[List[Optional[str]]] = None
    payment_method: Optional[str] = None
    status: Optional[str] = None

class GetOrder(BaseModel):
    id: Optional[PyObjectId] = Field(alias="_id", default=None)
    user_id: Optional[str] = None
    products: Optional[List[Optional[str]]] = None
    payment_method: Optional[str] = None #staggered, rent-to-own, outright
    status: Optional[str] = None

class AddPayment(BaseModel):
    order_id: Optional[str] = None
    user_id: Optional[str] = None
    amount: Optional[float] = None
    payment_method: Optional[str] = None  # staggered, rent-to-own, outright
    # payment_date: Optional[datetime] = None
    # next_payment_date: Optional[datetime] = None
    due_date: Optional[datetime] = None

class GetPayment(BaseModel):
    id: Optional[PyObjectId] = Field(alias="_id", default=None)
    order_id: Optional[str] = None
    user_id: Optional[str] = None
    amount: Optional[float] = None
    payment_method: Optional[str] = None  # staggered, rent-to-own, outright
    # payment_date: Optional[datetime] = None
    # next_payment_date: Optional[datetime] = None
    due_date: Optional[datetime] = None

app = FastAPI()

# set up cors
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Function to send email reminders
def send_email_reminder(email: str, message: str):
    msg = MIMEText(message)
    msg["Subject"] = "Payment Reminder"
    msg["From"] = "ahuekweprinceugo@gmail.com"
    msg["To"] = email

    # Connect to the Gmail SMTP server
    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.ehlo()  # Identify ourselves to the server
        server.starttls()  # Secure the connection
        server.ehlo()  # Re-identify ourselves as an encrypted connection
        # Login with the correct environment variable
        server.login("ahuekweprinceugo@gmail.com", os.getenv("GMAIL_PASS"))
        # Send the email
        server.sendmail(msg["From"], [msg["To"]], msg.as_string())

# Function to get user email by user_id
def get_user_email(user_id: str) -> str:
    user = user_collection.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user["email"]

# AUTH Functions
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def get_user(db, email: str):
    user = db.find_one({"email": email})
    if user:
        return UserInDB(**user)

def authenticate_user(db, email: str, password: str):
    user = get_user(db, email)
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user


async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
        token_data = TokenData(email=email)
    except JWTError:
        raise credentials_exception

    user = get_user(user_collection, email=token_data.email)
    if user is None:
        raise credentials_exception
    return user

# Routes

# Auth Routes
@app.post("/register", response_model=User, tags=["Auth"])
async def register_user(user: UserInDB):
    user.hashed_password = get_password_hash(user.hashed_password)
    user_collection.insert_one(user.dict())
    return user

@app.post("/token", response_model=Token, tags=["Auth"])
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(user_collection, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


@app.get("/users/me", response_model=User, tags=["Auth"])
async def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user

# Manage Users
@app.get("/users", tags=["Manage Users"])
def Get_Users(current_user: User = Depends(get_current_user)):
    usersQuery = user_collection.find({})

    rep = []

    for user in usersQuery:
        rep.append(GetUser(**user))

    return rep

@app.post("/users", tags=["Manage Users"])
def Add_Users(body: AddUser, current_user: User = Depends(get_current_user)):
    usersQuery = user_collection.insert_one(body.dict())

    # Get Added User
    getUser = user_collection.find_one({"_id": ObjectId(usersQuery.inserted_id)})

    getUser["_id"] = str(getUser["_id"])

    return getUser

@app.get("/users/{id}", tags=["Manage Users"])
def Get_User_By_Id(id:str, current_user: User = Depends(get_current_user)):
    userQuery = user_collection.find_one({"_id": ObjectId(id)})

    if userQuery:
        userQuery["_id"] = str(userQuery["_id"])
        return userQuery
    else:
        raise HTTPException(status_code=404, detail="User not found")

@app.get("/users/", tags=["Auth"])
def Login_Users(email=str, password=str, current_user: User = Depends(get_current_user)):
    userQuery = user_collection.find_one({"email": email, "password": password})

    if userQuery:
        userQuery["_id"] = str(userQuery["_id"])
        return userQuery
    else:
        raise HTTPException(status_code=404, detail="Incorrect email or password")

@app.patch("/users/{id}", tags=["Manage Users"])
def Update_Users(id:str, body: AddUser, current_user: User = Depends(get_current_user)):
    update_data = {k: v for k, v in body.dict().items() if v is not None}
    findUser = user_collection.find_one({"_id": ObjectId(id)})

    if findUser:
        updateQuery = user_collection.update_one({"_id": ObjectId(id)}, {"$set": update_data})
        findUser["_id"] = str(findUser["_id"])
        return findUser
    else:
        raise HTTPException(status_code=404, detail="User not found")

@app.delete("/users/{id}", tags=["Manage Users"])
def Delete_User(id:str, current_user: User = Depends(get_current_user)):
    deleteQuery = user_collection.delete_one({"_id": ObjectId(id)})

    if deleteQuery:
        return f"Successfully Deleted {id}"
    else:
        raise HTTPException(status_code=400, detail="Something went wrong")


# Manage Shops
@app.get("/shops", tags=["Manage Shops"])
def Get_Shops():
    shopsQuery = shops_collection.find({})
    allShops = []

    for shop in shopsQuery:
        allShops.append(GetShops(**shop))

    return allShops

@app.post("/shops", tags=["Manage Shops"])
def Add_Shop(request: Request, title: str = Form(...), description: str = Form(...),
    address: str = Form(...),
    price: str = Form(...),
    images: List[UploadFile] = File(None),
    availability: str = Form(...), current_user: User = Depends(get_current_user)):
    image_urls = []

    # Upload images to Cloudinary
    if images:
        for image in images:
            try:
                upload_result = cloudinary.uploader.upload(image.file, folder="shops")
                image_url = upload_result.get("url")
                image_urls.append(image_url)
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Image upload failed: {str(e)}")

    # Create shop data to insert into MongoDB
    shop_data = {
        "title": title,
        "description": description,
        "address": address,
        "price": price,
        "images": image_urls,  # Store URLs of uploaded images
        "availability": availability
    }

    # Insert the shop data into MongoDB
    try:
        result = shops_collection.insert_one(shop_data)
        shop_data["_id"] = str(result.inserted_id)  # Convert ObjectId to string
        return {"message": "Shop added successfully", "shop": shop_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to add shop: {str(e)}")

@app.get("/shops/{id}", tags=["Manage Shops"])
def Get_Shops_By_Id(id:str):
    shopQuery = shops_collection.find_one({"_id": ObjectId(id)})

    if shopQuery:
        shopQuery["_id"] = str(shopQuery["_id"])
        return shopQuery
    else:
        raise HTTPException(status_code=404, detail="Shop not found")

@app.patch("/shops/{id}", tags=["Manage Shops"])
def Edit_Shop(id:str, body:AddShops, current_user: User = Depends(get_current_user)):
    update_data = {k: v for k, v in body.dict().items() if v is not None}
    getShopToUpdate = shops_collection.find_one({"_id": ObjectId(id)})

    if getShopToUpdate:
        editShop = shops_collection.update_one({"_id": ObjectId(id)}, {"$set": update_data})
        getShopToUpdate["_id"] = str(getShopToUpdate["_id"])
        return getShopToUpdate
    else:
        raise HTTPException(status_code=404, detail=f"Shop with ID {id} not found")

@app.delete("/shops/{id}", tags=["Manage Shops"])
def Delete_Shop(id:str, current_user: User = Depends(get_current_user)):
    delQuery = shops_collection.delete_one({"_id": ObjectId(id)})

    if delQuery:
        return f"Shop with ID: {id} was deleted successfully"
    else:
        return "Something went wrong"

# Manage Order

@app.get("/order", tags=["Manage Order"])
def Get_Orders(current_user: User = Depends(get_current_user)):
    order_query = order_collection.find({})
    orderList = []

    for order in order_query:
        orderList.append(GetOrder(**order))

    return orderList

@app.post("/order", tags=["Manage Order"])
def Add_Order(body:AddOrder, current_user: User = Depends(get_current_user)):
    addOrder = order_collection.insert_one(body.dict())
    getAddedOrder = order_collection.find_one({"_id": ObjectId(addOrder.inserted_id)})
    getAddedOrder["_id"] = str(getAddedOrder["_id"])
    return getAddedOrder

@app.get("/order/{id}", tags=["Manage Order"])
def Get_Order_By_Id(id:str, current_user: User = Depends(get_current_user)):
    getOrderQuery = order_collection.find_one({"_id": ObjectId(id)})

    if getOrderQuery:
        getOrderQuery["_id"] = str(getOrderQuery["_id"])
        return getOrderQuery
    else:
        raise HTTPException(status_code=404, detail="Order not found")

@app.get("/orders/{order_id}/payments", tags=["Manage Order Payments"])
def Get_Order_Payments(order_id:str, current_user: User = Depends(get_current_user)):
    orderQuery = order_collection.find_one({"_id": order_id})

    if not orderQuery:
        raise HTTPException(status_code=404,detail="Order not found")

    paymentQuery = payment_collection.find({"order_id": order_id})

    return list(paymentQuery)

@app.patch("/order/{id}", tags=["Manage Order"])
def Edit_Order(id:str, body:Add_Order, current_user: User = Depends(get_current_user)):
    update_data = {k: v for k, v in body.dict().items() if v is not None}
    getOrderToUpdate = order_collection.find_one({"_id": ObjectId(id)})

    if getOrderToUpdate:
        editOrder = order_collection.update_one({"_id": ObjectId(id)}, {"$set": update_data})
        getOrderToUpdate["_id"] = str(getOrderToUpdate["_id"])
        return getOrderToUpdate
    else:
        raise HTTPException(status_code=404, detail=f"Order with ID {id} not found")

@app.delete("/order/{id}", tags=["Manage Order"])
def Delete_Order(id:str, current_user: User=Depends(get_current_user)):
    delQuery = order_collection.delete_one({"_id": ObjectId(id)})

    if delQuery:
        return f"Order with ID: {id} was deleted successfully"
    else:
        return "Something went wrong"




# Manage Payments

# Endpoint to process a payment
@app.post("/payments", tags=["Manage Payments"])
def process_payment(payment: AddPayment, background_tasks: BackgroundTasks, current_user: User = Depends(get_current_user)):
    payment_data = payment.dict()
    payment_data["created_at"] = datetime.utcnow()
    result = payment_collection.insert_one(payment_data)

    # Add to payment history
    payment_history_collection.insert_one(payment_data)

    # Schedule reminder if due_date is set
    if payment.due_date:
        user_email = get_user_email(payment_data["user_id"])  # Assuming order_id is the same as user_id
        background_tasks.add_task(send_email_reminder, user_email, f"Your next payment is due on {payment.due_date}")

    return {"payment_id": str(result.inserted_id)}

# Endpoint to retrieve payment details
@app.get("/payments/{order_id}", tags=["Manage Payments"])
def get_payment(order_id: str, current_user: User = Depends(get_current_user)):
    payment = payment_collection.find_one({"order_id": order_id})
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    payment["_id"] = str(payment["_id"])
    return payment

# Endpoint to process staggered payments
@app.post("/payments/staggered", tags=["Manage Payments"])
def process_staggered_payment(payment: AddPayment, background_tasks: BackgroundTasks, current_user: User = Depends(get_current_user)):
    payment.due_date = datetime.utcnow() + timedelta(minutes=5)  # Example: next payment due in 30 days
    return process_payment(payment, background_tasks)

# Endpoint to process rent-to-own payments
@app.post("/payments/rent-to-own", tags=["Manage Payments"])
def process_rent_to_own_payment(payment: AddPayment, background_tasks: BackgroundTasks, current_user: User = Depends(get_current_user)):
    payment.due_date = datetime.utcnow() + timedelta(minutes=5)  # Example: next payment due in 30 days
    return process_payment(payment, background_tasks)

# Endpoint to process outright purchase payments
@app.post("/payments/outright", tags=["Manage Payments"])
def process_outright_payment(payment: AddPayment, background_tasks: BackgroundTasks, current_user: User = Depends(get_current_user)):
    return process_payment(payment, background_tasks)

# Function to check for renewals
@app.get("/payments/renewals", tags=["Manage Payments"])
def check_renewals(current_user: User = Depends(get_current_user)):
    now = datetime.utcnow()
    renewals = payment_collection.find({"due_date": {"$lte": now}})
    return list(renewals)

# Endpoint to retrieve payment history
@app.get("/payments/history/{order_id}", tags=["Manage Payments"])
def get_payment_history(order_id: str, current_user: User = Depends(get_current_user)):
    history = payment_history_collection.find({"order_id": order_id})
    historyList = []

    for histor in history:
        historyList.append(GetPayment(**histor))
    return historyList




# @app.get("/payments/{date}", tags=["Manage Payments"])
# def Get_Payments_Due_Today(date:datetime):
#     due_payments = payment_collection.find({"next_payment_date":{"$lte": date.da}})