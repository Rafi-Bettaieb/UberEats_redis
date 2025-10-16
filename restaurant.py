# restaurant.py
import redis
import time
import random

r = redis.Redis(decode_responses=True)

def preparer_commandes():
    """Écoute et prépare les nouvelles commandes."""
    pubsub = r.pubsub()
    pubsub.subscribe("new_orders_channel")
    
    print("--- 🧑‍🍳 RESTAURANT ---")
    print("Prêt à recevoir des commandes.")
    
    for message in pubsub.listen():
        if message['type'] == 'message':
            id_commande = message['data']
            details = r.hgetall(f"order:{id_commande}")
            
            print(f"\n🧑‍🍳 Nouvelle commande {id_commande} reçue pour '{details['articles']}'.")
            
            # Simuler la préparation
            temps_preparation = random.randint(3, 8)
            print(f"🧑‍🍳 Préparation en cours... (environ {temps_preparation}s)")
            time.sleep(temps_preparation)
            print(f"✅ Commande {id_commande} est prête pour le livreur.")
            # Dans une vraie app, on mettrait à jour le statut ici.
            
if __name__ == "__main__":
    preparer_commandes()