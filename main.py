from _datetime import datetime
import os
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Request
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

# Convert ObjectId to string
PyObjectId = Annotated[str, BeforeValidator(str)]

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

app = FastAPI()

# set up cors
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes

# Manage Users
@app.get("/users", tags=["Manage Users"])
def Get_Users():
    usersQuery = user_collection.find({})

    rep = []

    for user in usersQuery:
        rep.append(GetUser(**user))

    return rep

@app.post("/users", tags=["Manage Users"])
def Add_Users(body:AddUser):
    usersQuery = user_collection.insert_one(body.dict())

    # Get Added User
    getUser = user_collection.find_one({"_id":ObjectId(usersQuery.inserted_id)})

    getUser["_id"] = str(getUser["_id"])

    return getUser

@app.get("/users/{id}", tags=["Manage Users"])
def Get_User_By_Id(id:str):
    userQuery = user_collection.find_one({"_id": ObjectId(id)})

    if userQuery:
        userQuery["_id"] = str(userQuery["_id"])
        return userQuery
    else:
        raise HTTPException(status_code=404, detail="User not found")

@app.get("/users/", tags=["Auth"])
def Login_Users(email=str, password=str):
    userQuery = user_collection.find_one({"email": email, "password": password})

    if userQuery:
        userQuery["_id"] = str(userQuery["_id"])
        return userQuery
    else:
        raise HTTPException(status_code=404, detail="Incorrect email or password")

@app.patch("/users/{id}", tags=["Manage Users"])
def Update_Users(id:str, body: AddUser):
    update_data = {k: v for k, v in body.dict().items() if v is not None}
    findUser = user_collection.find_one({"_id": ObjectId(id)})

    if findUser:
        updateQuery = user_collection.update_one({"_id": ObjectId(id)}, {"$set": update_data})
        findUser["_id"] = str(findUser["_id"])
        return findUser
    else:
        raise HTTPException(status_code=404, detail="User not found")

@app.delete("/users/{id}", tags=["Manage Users"])
def Delete_User(id:str):
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
    availability: str = Form(...)):
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
def Edit_Shop(id:str, body:AddShops):
    update_data = {k: v for k, v in body.dict().items() if v is not None}
    getShopToUpdate = shops_collection.find_one({"_id": ObjectId(id)})

    if getShopToUpdate:
        editShop = shops_collection.update_one({"_id": ObjectId(id)}, {"$set": update_data})
        getShopToUpdate["_id"] = str(getShopToUpdate["_id"])
        return getShopToUpdate
    else:
        raise HTTPException(status_code=404, detail=f"Shop with ID {id} not found")

@app.delete("/shops/{id}", tags=["Manage Shops"])
def Delete_Shop(id:str):
    delQuery = shops_collection.delete_one({"_id": ObjectId(id)})

    if delQuery:
        return f"Shop with ID: {id} was deleted successfully"
    else:
        return "Something went wrong"