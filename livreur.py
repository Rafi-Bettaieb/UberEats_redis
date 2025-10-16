# livreur.py (version interactive)
import redis
import threading
import time
import random

# --- CONFIGURATION ---
ID_LIVREUR = f"livreur_{random.randint(100, 999)}"
r = redis.Redis(decode_responses=True)

etat_commande = {
    "derniere_commande_id": None,
    "disponible_pour_acceptation": False
}

def ecouter_les_annonces():
    """Écoute les nouvelles commandes et les rend disponibles pour l'acceptation manuelle."""
    pubsub = r.pubsub()
    pubsub.subscribe("new_orders_channel")
    
    for message in pubsub.listen():
        if message['type'] == 'message':
            id_commande = message['data']
            etat_commande["derniere_commande_id"] = id_commande
            etat_commande["disponible_pour_acceptation"] = True
            print(f"\n\n--- NOUVELLE COMMANDE DISPONIBLE ---")
            print(f"ID de la Commande : {id_commande}")
            print(f">>> Appuyez sur 'Entrée' pour accepter (vous avez 60s) ! <<<")
            print("------------------------------------")

def attendre_assignation_et_livrer():
    """Attend sur son canal personnel et simule la livraison si assigné."""
    pubsub = r.pubsub()
    pubsub.subscribe(f"notify:driver:{ID_LIVREUR}")
    for message in pubsub.listen():
        if message['type'] == 'message':
            id_commande = message['data']
            print(f"\n🎉 {ID_LIVREUR}: On m'a assigné la commande {id_commande} !")
            r.hset(f"order:{id_commande}", "status", "assigned")
            r.hset(f"order:{id_commande}", "assigned_driver", ID_LIVREUR)
            print(f"🛵 {ID_LIVREUR}: Je pars en livraison...")
            time.sleep(random.randint(5, 10))
            r.hset(f"order:{id_commande}", "status", "delivered")
            print(f"✅ {ID_LIVREUR}: Commande {id_commande} livrée !")

# --- Programme Principal (boucle d'interaction) ---
if __name__ == "__main__":
    thread_ecoute = threading.Thread(target=ecouter_les_annonces, daemon=True)
    thread_assignation = threading.Thread(target=attendre_assignation_et_livrer, daemon=True)
    thread_ecoute.start()
    thread_assignation.start()
    
    print(f"--- 🛵 LIVREUR {ID_LIVREUR} EN LIGNE ---")
    
    while True:
        input() # Attend que l'utilisateur appuie sur "Entrée"
        
        if etat_commande["disponible_pour_acceptation"]:
            id_a_accepter = etat_commande["derniere_commande_id"]
            
            # !! VÉRIFICATION CRUCIALE !!
            # Le livreur vérifie si la fenêtre d'acceptation est toujours ouverte
            if r.exists(f"timer:acceptance_window:{id_a_accepter}"):
                r.rpush(f"candidates:{id_a_accepter}", ID_LIVREUR)
                print(f"👍 Vous avez accepté la commande {id_a_accepter} !")
            else:
                print(f"⏳ Trop tard ! La fenêtre d'acceptation pour la commande {id_a_accepter} est fermée.")
            
            etat_commande["disponible_pour_acceptation"] = False
        else:
            print("Aucune nouvelle commande à accepter pour le moment.")