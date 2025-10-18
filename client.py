# client.py
import redis
import json
import uuid
import time
import threading # NOUVEAU

r = redis.Redis(decode_responses=True)

# Coordonnées du restaurant (devraient venir d'une base de données en réalité)
RESTAURANT_COORDS = {"lon": "2.333", "lat": "48.865"}

def ecouter_statut_commande(id_commande):
    """Thread qui écoute les mises à jour de statut pour une commande."""
    pubsub = r.pubsub()
    pubsub.subscribe(f"notify:order:{id_commande}")
    
    print(f"👂 [CLIENT] J'écoute les mises à jour pour la commande {id_commande}...")
    
    for message in pubsub.listen():
        if message['type'] == 'message':
            status = message['data']
            
            # Afficher un message sympa en fonction du statut
            if status == "ready":
                print(f"🧑‍🍳 [CLIENT] Statut: La commande {id_commande} est prête au restaurant !")
            elif status == "assigned":
                print(f"🛵 [CLIENT] Statut: La commande {id_commande} est assignée à un livreur !")
            elif status == "delivered":
                print(f"✅ [CLIENT] Statut: La commande {id_commande} a été livrée ! Bon appétit.")
                pubsub.unsubscribe() # On a fini, on arrête d'écouter
                break
            else:
                print(f"🔄 [CLIENT] Statut: {id_commande} -> {status}")

def passer_commande():
    """Passe une commande et démarre la fenêtre d'acceptation de 60s pour les livreurs."""
    id_commande = str(uuid.uuid4())[:8]
    
    details_commande = {
        "id": id_commande,
        "client": "client_789",
        "restaurant": "La Bonne Fourchette",
        "restaurant_lon": RESTAURANT_COORDS["lon"],
        "restaurant_lat": RESTAURANT_COORDS["lat"],
        "articles": "1x Steak Frites, 1x Tarte Tatin",
        "status": "pending", # Statut initial
    }
    
    print(f"🛒 [CLIENT] Passage de la commande {id_commande}.")
    
    r.hset(f"order:{id_commande}", mapping=details_commande)
    r.set(f"timer:acceptance_window:{id_commande}", "open", ex=60)
    r.publish("new_orders_channel", id_commande)
    
    print(f"🛒 [CLIENT] Commande annoncée. Fenêtre d'acceptation ouverte pendant 60s.")
    
    return id_commande # NOUVEAU: On retourne l'ID pour pouvoir l'écouter

if __name__ == "__main__":
    id_commande_passee = passer_commande()
    
    # NOUVEAU: Démarrer le thread d'écoute
    thread_ecoute = threading.Thread(target=ecouter_statut_commande, args=(id_commande_passee,), daemon=True)
    thread_ecoute.start()
    
    # Garder le script principal en vie pendant que le thread écoute
    thread_ecoute.join()
    print("👋 [CLIENT] Fin de la session.")