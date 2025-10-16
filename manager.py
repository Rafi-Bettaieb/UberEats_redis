# manager.py (Version interactive)
import redis
import threading
import time

r = redis.Redis(decode_responses=True)

def prompt_manager_for_choice(id_commande, candidats):
    """
    Fonction exécutée dans un thread séparé pour demander au manager de choisir.
    Ne bloque pas le thread principal qui écoute Redis.
    """
    try:
        print("\n\n####################################################")
        print(f"### ACTION REQUISE pour la commande {id_commande} ###")
        print("####################################################")
        print("Voici la liste des livreurs qui ont accepté :")
        
        # Afficher la liste numérotée des candidats
        for index, livreur_id in enumerate(candidats, start=1):
            print(f"  {index}) {livreur_id}")
            
        # Demander au manager de faire un choix
        choice_str = input(">>> Entrez le numéro du livreur à choisir (ou laissez vide pour une attribution auto) : ")
        
        # Si le manager n'entre rien, le thread se termine et l'auto-assignation aura lieu
        if not choice_str:
            print("Aucun choix manuel. L'attribution automatique aura lieu si aucune action n'est prise.")
            return

        choice_index = int(choice_str) - 1 # Convertir en index de liste (qui commence à 0)

        # Valider le choix
        if 0 <= choice_index < len(candidats):
            livreur_choisi = candidats[choice_index]
            print(f"\n✅ Vous avez choisi {livreur_choisi}.")

            # Annuler le minuteur d'auto-assignation car une décision a été prise
            if r.delete(f"timer:manager_decision:{id_commande}"):
                print("⏱️  Le minuteur d'attribution automatique a été annulé.")
            
            # Notifier le livreur choisi
            r.publish(f"notify:driver:{livreur_choisi}", id_commande)
            
        else:
            print("❌ Numéro invalide. L'attribution automatique aura lieu.")

    except ValueError:
        print("❌ Entrée non valide. L'attribution automatique aura lieu.")
    finally:
        print("####################################################\n")


def ecouter_expirations():
    """Thread principal qui écoute les expirations de clés Redis."""
    pubsub = r.pubsub()
    pubsub.psubscribe("__keyevent@0__:expired")
    print("🧠 [MANAGER] Module d'écoute des minuteurs est actif.")

    for message in pubsub.listen():
        if message['type'] == 'pmessage':
            key = message['data']

            # CAS N°1 : La fenêtre d'acceptation des livreurs se termine
            if key.startswith("timer:acceptance_window:"):
                id_commande = key.split(":")[-1]
                print(f"\n⏱️  [MANAGER] Fenêtre d'acceptation pour la commande {id_commande} FERMÉE.")
                
                candidats = r.lrange(f"candidates:{id_commande}", 0, -1)
                if candidats:
                    # Démarrer le minuteur N°2 pour la décision du manager
                    r.set(f"timer:manager_decision:{id_commande}", "pending", ex=60)
                    
                    # Lancer le thread pour demander le choix au manager SANS attendre
                    choice_thread = threading.Thread(
                        target=prompt_manager_for_choice,
                        args=(id_commande, candidats)
                    )
                    choice_thread.start()
                else:
                    print("⚠️ Aucun livreur n'a accepté. La commande est en attente.")

            # CAS N°2 : La fenêtre de décision du manager se termine
            elif key.startswith("timer:manager_decision:"):
                id_commande = key.split(":")[-1]
                print(f"\n⏱️  [MANAGER] Fenêtre de décision pour {id_commande} FERMÉE.")

                if r.hget(f"order:{id_commande}", "status") == "pending":
                    candidats = r.lrange(f"candidates:{id_commande}", 0, -1)
                    if candidats:
                        premier_livreur = candidats[0]
                        print(f"🤖 Pas d'action manuelle. Attribution automatique à : {premier_livreur}.")
                        r.publish(f"notify:driver:{premier_livreur}", id_commande)


if __name__ == "__main__":
    thread_timers = threading.Thread(target=ecouter_expirations, daemon=True)
    thread_timers.start()
    
    print("--- 🧠 MANAGER EN LIGNE ---")
    print("Le système va gérer les fenêtres d'acceptation et de décision.")
    while True:
        time.sleep(1)