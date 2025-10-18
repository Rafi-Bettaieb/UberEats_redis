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
            
            # Vérifier si la commande existe toujours (au cas où)
            if not r.exists(f"order:{id_commande}"):
                continue
                
            details = r.hgetall(f"order:{id_commande}")
            
            print(f"\n🧑‍🍳 Nouvelle commande {id_commande} reçue pour '{details['articles']}'.")
            
            # Simuler la préparation
            temps_preparation = random.randint(3, 8)
            print(f"🧑‍🍳 Préparation en cours... (environ {temps_preparation}s)")
            time.sleep(temps_preparation)
            
            # MODIFIÉ: Mettre à jour le statut et notifier le client
            nouveau_statut = "ready"
            r.hset(f"order:{id_commande}", "status", nouveau_statut)
            r.publish(f"notify:order:{id_commande}", nouveau_statut)
            # ----------------------------------------------------
            
            print(f"✅ Commande {id_commande} est prête pour le livreur.")
            
if __name__ == "__main__":
    preparer_commandes()