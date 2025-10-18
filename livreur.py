# livreur.py
import redis
import threading
import time
import random

# --- CONFIGURATION ---
ID_LIVREUR = f"livreur_{random.randint(100, 999)}"
r = redis.Redis(decode_responses=True)

# Simuler une position de départ à Paris
current_location = {
    "lon": round(random.uniform(2.25, 2.40), 5),
    "lat": round(random.uniform(48.82, 48.90), 5)
}

# --- Variables pour la version interactive ---
etat_commande = {
    "derniere_commande_id": None,
    "disponible_pour_acceptation": False
}

def update_location_periodically():
    """Thread qui met à jour la position GPS du livreur toutes les 10 secondes."""
    while True:
        try:
            time.sleep(10)
            current_location["lon"] += round(random.uniform(-0.001, 0.001), 5)
            current_location["lat"] += round(random.uniform(-0.001, 0.001), 5)
            r.geoadd("livreurs:positions", (current_location["lon"], current_location["lat"], ID_LIVREUR))
        except Exception as e:
            print(f"[Thread update_location] Erreur: {e}")
            time.sleep(10) 

def complete_delivery_and_update_score(id_commande):
    """Simule la fin d'une livraison, met à jour le statut, notifie le client et met à jour la note."""
    print(f"✅ {ID_LIVREUR}: Commande {id_commande} livrée !")
    
    # MODIFIÉ: Mettre à jour le statut final et notifier le client
    nouveau_statut = "delivered"
    r.hset(f"order:{id_commande}", "status", nouveau_statut)
    r.publish(f"notify:order:{id_commande}", nouveau_statut)
    # --------------------------------------------------------

    # ... (partie mise à jour du score, inchangée)
    new_rating = round(random.uniform(3.0, 5.0), 2)
    print(f"⭐️ {ID_LIVREUR}: Nouvelle note reçue : {new_rating} étoiles.")
    stats_key = f"livreur_stats:{ID_LIVREUR}"
    current_total_rating = float(r.hget(stats_key, "total_rating") or 0)
    num_deliveries = int(r.hget(stats_key, "num_deliveries") or 0)
    new_total_rating = current_total_rating + new_rating
    new_num_deliveries = num_deliveries + 1
    new_avg_rating = round(new_total_rating / new_num_deliveries, 2)
    r.hset(stats_key, mapping={"total_rating": new_total_rating, "num_deliveries": new_num_deliveries, "avg_rating": new_avg_rating})
    r.zadd("livreurs:scores", {ID_LIVREUR: new_avg_rating})
    print(f"🏆 {ID_LIVREUR}: Ma nouvelle note moyenne est de {new_avg_rating}.")


def ecouter_les_annonces():
    """Écoute les nouvelles commandes et les rend disponibles pour l'acceptation manuelle."""
    pubsub = r.pubsub()
    pubsub.subscribe("new_orders_channel")
    for message in pubsub.listen():
        if message['type'] == 'message':
            id_commande = message['data']
            # Petit check pour ne pas s'auto-notifier si la commande est déjà finie
            if r.hget(f"order:{id_commande}", "status") == "delivered":
                continue
            
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
            
            # MODIFIÉ: Mettre à jour le statut et notifier le client
            nouveau_statut = "assigned"
            r.hset(f"order:{id_commande}", "status", nouveau_statut)
            r.hset(f"order:{id_commande}", "assigned_driver", ID_LIVREUR)
            r.publish(f"notify:order:{id_commande}", nouveau_statut)
            # ----------------------------------------------------
            
            print(f"🛵 {ID_LIVREUR}: Je pars en livraison...")
            time.sleep(random.randint(5, 10))
            complete_delivery_and_update_score(id_commande)


if __name__ == "__main__":
    r.zadd("livreurs:scores", {ID_LIVREUR: 5.0})
    try:
        r.geoadd("livreurs:positions", (current_location["lon"], current_location["lat"], ID_LIVREUR))
        print(f"📍 {ID_LIVREUR}: Position initiale enregistrée: ({current_location['lon']}, {current_location['lat']})")
    except Exception as e:
        print(f"Erreur lors de l'ajout de la position initiale: {e}")

    thread_location = threading.Thread(target=update_location_periodically, daemon=True)
    thread_annonces = threading.Thread(target=ecouter_les_annonces, daemon=True)
    thread_assignation = threading.Thread(target=attendre_assignation_et_livrer, daemon=True)
    
    thread_location.start()
    thread_annonces.start()
    thread_assignation.start()
    
    print(f"--- 🛵 LIVREUR {ID_LIVREUR} EN LIGNE ---")
    
    while True:
        input()
        if etat_commande["disponible_pour_acceptation"]:
            id_a_accepter = etat_commande["derniere_commande_id"]
            if r.exists(f"timer:acceptance_window:{id_a_accepter}"):
                r.rpush(f"candidates:{id_a_accepter}", ID_LIVREUR)
                print(f"👍 Vous avez accepté la commande {id_a_accepter} !")
            else:
                print(f"⏳ Trop tard ! La fenêtre d'acceptation est fermée.")
            etat_commande["disponible_pour_acceptation"] = False
        else:
            print("Aucune nouvelle commande à accepter pour le moment.")