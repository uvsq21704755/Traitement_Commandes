#!/usr/bin/env python
# coding: utf-8

# In[7]:


from fastapi import FastAPI, BackgroundTasks, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, String, Integer, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import asyncio
import random
import os

DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(DATABASE_URL)
Base = declarative_base()

class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    email = Column(String)
    validated = Column(Boolean, default=False)  # Ajout de la colonne pour suivre l'état de la validation de la commande
    validated_quote_supplier = Column(Boolean, default=False) # Ajout de la colonne pour suivre l'état de la validation du devis par le fournisseur
    validated_quote_client = Column(Boolean, default=False) # Ajout de la colonne pour suivre l'état de la validation du devis par le client
    service_realization = Column(Boolean, default=False) # Ajout de la colonne pour suivre l'état de la réalisation du service
    quote_file_name = Column(String, default="None")

Base.metadata.create_all(bind=engine)

class OrderCreate(BaseModel):
    name: str
    email: str

app = FastAPI()

@app.post("/place_order")
async def place_order(order: OrderCreate, background_tasks: BackgroundTasks):
    db_order = Order(name=order.name, email=order.email)
    db = sessionmaker(autocommit=False, autoflush=True, bind=engine)
    with db() as session:
        session.add(db_order)
        session.commit()
        session.refresh(db_order)

    background_tasks.add_task(validate_order, db_order.id, background_tasks)

    return {"order_id": db_order.id, "message": "Commande reçue, en attente de validation"}

async def validate_order(order_id: int, background_tasks: BackgroundTasks):
    await asyncio.sleep(5)

    while True:
        await asyncio.sleep(1)
        validation_result = check_validation(order_id)
        if validation_result is True:
            db = sessionmaker(autocommit=False, autoflush=True, bind=engine)
            with db() as session:
                order = session.query(Order).filter(Order.id == order_id).first()
                order.validated = True
                session.commit()
                session.refresh(order)
            print(f"Commande {order_id} validée. Notification envoyée au client.")
            background_tasks.add_task(process_and_validate_quote, order_id, order.name, order.email, background_tasks)
            break
        elif validation_result is False:
            db = sessionmaker(autocommit=False, autoflush=True, bind=engine)
            with db() as session:
                order = session.query(Order).filter(Order.id == order_id).first()
                session.delete(order)  # Supprimer l'ordre de la base de données
                session.commit()
            print(f"Commande {order_id} invalidée. Notification envoyée au client.")
            break
            
@app.get("/check_order/{order_id}")
async def check_order(order_id: int):
    db = sessionmaker(autocommit=False, autoflush=True, bind=engine)
    with db() as session:
        order = session.query(Order).filter(Order.id == order_id).first()
        if order and order.validated:
            return {"message": "Votre commande a été vérifiée"}
        elif order:
            return {"message": "Votre commande est en attente de validation"}
        else :
            return {"message": "Votre commande a été invalidée, veuillez replacer votre commande"}

def check_validation(order_id: int):
    # Simuler ici une vérification humaine, par exemple, à partir de la console
    validation_input = input(f"Vérifier la commande {order_id}. Tapez 'ok' pour valider, 'non' pour invalider: ")
    if validation_input.lower() == "ok":
        return True
    elif validation_input.lower() == "non":
        return False
    else :
        return None

def generate_quote(order_id: int, name: str, email: str):
    cost = random.randint(0, 400)
    quote = f"id: {order_id}\nname: {name}\nemail: {email}\ncost: {cost}"
    
    # Enregistrez le devis dans un fichier texte
    filename = f"quote_{order_id}.txt"
    with open(filename, "w") as file:
        file.write(quote)
    
    return filename

def process_and_validate_quote(order_id: int, name: str, email: str, background_tasks: BackgroundTasks):
    quote_filename = generate_quote(order_id, name, email)
    print(f"Devis généré : {quote_filename}")
    # Simuler ici une vérification humaine du devis
    validation_quote_input = input(f"Vérifier le devis {order_id}. Tapez 'ok' pour valider, 'non' pour invalider: ")
    if validation_quote_input.lower() == "ok":
        print(f"Devis {order_id} validé.")
        db = sessionmaker(autocommit=False, autoflush=True, bind=engine)
        with db() as session:
            order = session.query(Order).filter(Order.id == order_id).first()
            order.validated_quote_supplier = True
            order.quote_file_name = quote_filename
            session.commit()
            session.refresh(order)
            background_tasks.add_task(evaluate_quote, order_id, background_tasks)
    elif validation_quote_input.lower() == "non":
        db = sessionmaker(autocommit=False, autoflush=True, bind=engine)
        with db() as session:
            order = session.query(Order).filter(Order.id == order_id).first()
            session.delete(order)  # Supprimer l'ordre de la base de données
            session.commit()
        print(f"Devis {order_id} non validé.")
    else:
        print(f"Choix non valide pour la vérification du devis {order_id}.")

async def evaluate_quote(order_id: int, background_tasks: BackgroundTasks):
    await asyncio.sleep(5)
    db = sessionmaker(autocommit=False, autoflush=True, bind=engine)
    with db() as session:
        order = session.query(Order).filter(Order.id == order_id).first()
        response = None
        if order and order.validated and order.validated_quote_supplier:
            print(f"Le devis associé à la commande {order_id} a été généré et validé, veuillez le consulter et tapez 'ok' pour le valider, 'non' pour invalider: ")
            while(response == None):
                evaluation_quote_input = input(f"Réponse: ")
                if evaluation_quote_input.lower() == "ok":
                    order.validated_quote_client = True
                    session.commit()
                    session.refresh(order)
                    response = True
                    print(f"Devis {order_id} accepté.")
                    background_tasks.add_task(realization_service, order_id, background_tasks)
                elif evaluation_quote_input.lower() == "non":
                    response = True
                    session.delete(order)  # Supprimer l'ordre de la base de données
                    session.commit()
                    print(f"Devis {order_id} refusé.")

@app.get("/check_quote/{order_id}")
async def check_quote(order_id: int):
    db = sessionmaker(autocommit=False, autoflush=True, bind=engine)
    with db() as session:
        order = session.query(Order).filter(Order.id == order_id).first()
        if order and order.validated and order.validated_quote_supplier:
            return {"message": "Votre devis a été vérifiée"}
        elif order:
            return {"message": "Votre devis est en attente de validation"}
        else :
            return {"message": "Votre devis a été invalidée, veuillez replacer votre commande"}

def realization_service(order_id: int, background_tasks: BackgroundTasks):
    db = sessionmaker(autocommit=False, autoflush=True, bind=engine)
    with db() as session:
        order = session.query(Order).filter(Order.id == order_id).first()
        print(f"Service associé à la commande {order_id} réalisé.")
        order.service_realization = True
        session.commit()
        session.refresh(order)
        background_tasks.add_task(validation_realization_service, order_id, background_tasks)

@app.get("/check_realization/{order_id}")
async def check_realization(order_id: int):
    db = sessionmaker(autocommit=False, autoflush=True, bind=engine)
    with db() as session:
        order = session.query(Order).filter(Order.id == order_id).first()
        if order.service_realization:
            return {"message": "Le service a été réalisé"}
        else:
            return {"message": "Le service n'a pas encore été réalisé, des étapes préliminaires doivent être effectuées"}

async def validation_realization_service(order_id: int, background_tasks: BackgroundTasks):
    await asyncio.sleep(5)
    validation_realization_service = input(f"Le service associé à la commande {order_id} a t-il été réalisé comme convenu ? Tapez 'ok' pour valider, 'non' pour invalider: ")
    if validation_realization_service.lower() == "ok":
        print(f"Service associé à la commande {order_id} validé.")
    elif validation_realization_service.lower() == "non":
        print(f"Service associé à la commande {order_id} non validé. Le service doit être reconsidéré.")
        db = sessionmaker(autocommit=False, autoflush=True, bind=engine)
        with db() as session:
            order = session.query(Order).filter(Order.id == order_id).first()
            order.service_realization = False
            session.commit()
            session.refresh(order)
        background_tasks.add_task(realization_service, order_id, background_tasks)


# In[ ]:





# In[ ]:




