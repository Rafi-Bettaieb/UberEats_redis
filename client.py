# client.py
import redis
import json
import uuid
import time

r = redis.Redis(decode_responses=True)

def passer_commande():
    """Passe une commande et démarre la fenêtre d'acceptation de 60s pour les livreurs."""
    id_commande = str(uuid.uuid4())[:8]
    
    details_commande = {
        "id": id_commande,
        "client": "client_789",
        "restaurant": "La Bonne Fourchette",
        "articles": "1x Steak Frites, 1x Tarte Tatin",
        "status": "pending",
        "assigned_driver": "",
        "created_at": time.time()
    }
    
    print(f"🛒 [CLIENT] Passage de la commande {id_commande}.")
    
    # 1. Stocker les détails de la commande
    r.hset(f"order:{id_commande}", mapping=details_commande)
    
    # 2. Démarrer le MINUTEUR N°1 : La fenêtre d'acceptation pour les livreurs (60s)
    r.set(f"timer:acceptance_window:{id_commande}", "open", ex=60)
    
    # 3. Annoncer la nouvelle commande
    r.publish("new_orders_channel", id_commande)
    
    print(f"🛒 [CLIENT] Commande annoncée. La fenêtre d'acceptation pour les livreurs est ouverte pendant 60 secondes.")

if __name__ == "__main__":
    passer_commande()