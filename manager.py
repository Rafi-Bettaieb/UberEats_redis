# manager.py
import redis
import threading
import time
import math # NOUVEAU

r = redis.Redis(decode_responses=True)

# NOUVEAU: Fonction pour calculer la distance entre deux points GPS
def haversine(lon1, lat1, lon2, lat2):
    """
    Calcule la distance en kilomètres entre deux points
    (lon1, lat1) et (lon2, lat2).
    """
    try:
        # Convertir les degrés décimaux en radians
        lon1, lat1, lon2, lat2 = map(math.radians, [float(lon1), float(lat1), float(lon2), float(lat2)])
        
        # Formule Haversine
        dlon = lon2 - lon1
        dlat = lat2 - lat1
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        r_km = 6371 # Rayon de la Terre en kilomètres
        return c * r_km
    except (ValueError, TypeError):
        return float('inf') # Retourne l'infini si les coordonnées sont invalides

# NOUVEAU: Fonction pour calculer un score combiné
def calculate_recommendation_score(details):
    """
    Calcule un score de recommandation basé sur la note et la distance.
    Plus le score est élevé, meilleure est la recommandation.
    """
    score = details["score"]
    distance_km = details["distance_km"]
    
    if score == 0 or distance_km == float('inf'):
        return 0
    
    # Formule simple: (score^2) / (distance + 1)
    # On donne plus de poids au score (au carré)
    # On ajoute +1 à la distance pour éviter la division par zéro
    # et pour ne pas sur-pénaliser les distances < 1km.
    recommendation = (score ** 2) / (distance_km + 1)
    return recommendation

# MODIFIÉ: La fonction récupère maintenant tous les détails et les trie
def get_candidates_with_details(id_commande, candidats):
    """
    Prend une liste de candidats, récupère leur score ET leur distance,
    calcule un score de recommandation, et retourne la liste triée.
    """
    if not candidats:
        return []

    # 1. Récupérer les coordonnées du restaurant
    resto_coords = r.hmget(f"order:{id_commande}", "restaurant_lon", "restaurant_lat")
    resto_lon, resto_lat = resto_coords
    
    if not resto_lon or not resto_lat:
        print(f"Erreur: Coordonnées du restaurant non trouvées pour {id_commande}")
        return []

    # 2. Récupérer le score et la position de chaque candidat
    pipe = r.pipeline()
    for driver in candidats:
        pipe.zscore("livreurs:scores", driver)      # Obtenir le score
        pipe.geopos("livreurs:positions", driver)   # Obtenir la position [lon, lat]
    results = pipe.execute()
    
    driver_details = []
    # results est une liste plate: [score_liv1, pos_liv1, score_liv2, pos_liv2, ...]
    for i in range(len(candidats)):
        driver_id = candidats[i]
        score = results[i*2] or 0.0 # Score par défaut 0
        pos_data = results[i*2 + 1] # Sera [None] ou [[lon, lat]]
        
        distance_km = float('inf') # Distance par défaut
        driver_lon, driver_lat = None, None # NOUVEAU: Initialiser
        
        if pos_data and pos_data[0]:
            driver_lon, driver_lat = pos_data[0] # NOUVEAU: Stocker les coords
            distance_km = haversine(resto_lon, resto_lat, driver_lon, driver_lat)

        details = {
            "id": driver_id,
            "score": float(score),
            "distance_km": round(distance_km, 2), 
            "lon": driver_lon, # NOUVEAU: Ajouter lon aux détails
            "lat": driver_lat  # NOUVEAU: Ajouter lat aux détails
        }
        
        # 3. Calculer le score de recommandation
        details["recommendation"] = calculate_recommendation_score(details)
        driver_details.append(details)
    
    # 4. Trier par le score de recommandation (le plus élevé en premier)
    sorted_drivers = sorted(driver_details, key=lambda item: item['recommendation'], reverse=True)
    
    return sorted_drivers

# MODIFIÉ: La fonction utilise la nouvelle méthode de tri et affiche plus de détails
def prompt_manager_for_choice(id_commande, candidats):
    """Demande au manager de choisir parmi une liste de candidats TRIÉE."""
    
    sorted_candidates_details = get_candidates_with_details(id_commande, candidats)
    
    if not sorted_candidates_details:
        print("Aucun candidat avec des détails trouvés.")
        return

    try:
        print("\n\n####################################################")
        print(f"### ACTION REQUISE pour la commande {id_commande} ###")
        print("####################################################")
        print("Voici la liste des livreurs (triée par meilleure recommandation) :")
        
        # MODIFIÉ: Affichage des détails (score, distance, recommandation ET COORDS)
        for index, details in enumerate(sorted_candidates_details, start=1):
            
            # NOUVEAU: Formatter les coordonnées pour l'affichage
            if details['lon'] is not None and details['lat'] is not None:
                # Affichage des coordonnées avec 3 décimales
                coords_str = f"({details['lon']:.3f}, {details['lat']:.3f})"
            else:
                coords_str = "(Pos. inconnue)"
            
            # NOUVEAU: Ajout de coords_str à la ligne d'impression
            print(f"  {index}) {details['id']} (⭐ {details['score']}, 📍 {details['distance_km']} km {coords_str}, 📈 Reco: {details['recommendation']:.2f})")
            
        choice_str = input(">>> Entrez le numéro du livreur à choisir (ou laissez vide pour choisir le meilleur automatiquement) : ")
        
        if not choice_str:
            print("Aucun choix manuel. L'attribution automatique au meilleur livreur aura lieu.")
            return

        choice_index = int(choice_str) - 1
        if 0 <= choice_index < len(sorted_candidates_details):
            livreur_choisi = sorted_candidates_details[choice_index]['id']
            print(f"\n✅ Vous avez choisi {livreur_choisi}.")
            if r.delete(f"timer:manager_decision:{id_commande}"):
                print("⏱️  Le minuteur d'attribution automatique a été annulé.")
            r.publish(f"notify:driver:{livreur_choisi}", id_commande)
        else:
            print("❌ Numéro invalide.")
    except (ValueError, IndexError):
        print("❌ Entrée non valide.")
    finally:
        print("####################################################\n")


def ecouter_expirations():
    """Écoute les expirations de clés Redis."""
    pubsub = r.pubsub()
    pubsub.psubscribe("__keyevent@0__:expired")
    print("🧠 [MANAGER] Module d'écoute des minuteurs est actif.")

    for message in pubsub.listen():
        if message['type'] == 'pmessage':
            key = message['data']

            if key.startswith("timer:acceptance_window:"):
                id_commande = key.split(":")[-1]
                print(f"\n⏱️  [MANAGER] Fenêtre d'acceptation pour la commande {id_commande} FERMÉE.")
                candidats = r.lrange(f"candidates:{id_commande}", 0, -1)
                if candidats:
                    r.set(f"timer:manager_decision:{id_commande}", "pending", ex=60)
                    choice_thread = threading.Thread(target=prompt_manager_for_choice, args=(id_commande, candidats))
                    choice_thread.start()
                else:
                    print(f"⚠️ Aucun livreur n'a accepté la commande {id_commande}.")

            elif key.startswith("timer:manager_decision:"):
                id_commande = key.split(":")[-1]
                print(f"\n⏱️  [MANAGER] Fenêtre de décision pour {id_commande} FERMÉE.")
                if r.hget(f"order:{id_commande}", "status") == "pending":
                    candidats = r.lrange(f"candidates:{id_commande}", 0, -1)
                    
                    # MODIFIÉ: Utilisation de la nouvelle fonction de tri
                    sorted_candidats = get_candidates_with_details(id_commande, candidats)
                    
                    if sorted_candidats:
                        # MODIFIÉ: On prend l'ID du premier (le meilleur selon la recommandation)
                        meilleur_livreur = sorted_candidats[0]['id'] 
                        print(f"🤖 Pas d'action manuelle. Attribution automatique au MEILLEUR livreur (basé sur score/distance) : {meilleur_livreur}.")
                        r.publish(f"notify:driver:{meilleur_livreur}", id_commande)
                    else:
                        print(f"🤖 Pas d'action manuelle, mais aucun candidat n'était disponible pour {id_commande}.")


if __name__ == "__main__":
    thread_timers = threading.Thread(target=ecouter_expirations, daemon=True)
    thread_timers.start()
    
    print("--- 🧠 MANAGER EN LIGNE ---")
    while True: time.sleep(1)