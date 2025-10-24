from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, Response
import redis
import hashlib
import uuid
import time
import threading
import json
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = 'votre_cle_secrete'

r = redis.Redis(decode_responses=True)

def init_test_users():
    password_hash = hashlib.sha256("123456".encode()).hexdigest()
    
    test_users = {
        "client1": {"password": password_hash, "role": "client"},
        "manager1": {"password": password_hash, "role": "manager"},
        "restaurant1": {"password": password_hash, "role": "restaurant"},
        "livreur1": {"password": password_hash, "role": "livreur"},
        "livreur2": {"password": password_hash, "role": "livreur"},
        "livreur3": {"password": password_hash, "role": "livreur"},
    }
    
    for username, user_data in test_users.items():
        if not r.hexists("users", username):
            r.hset("users", username, f"{user_data['password']}:{user_data['role']}")
            
    # Initialiser les scores des livreurs
    livreur_scores = {
        "livreur1": 4.8,
        "livreur2": 4.3,
        "livreur3": 4.6
    }
    for livreur, score in livreur_scores.items():
        r.zadd("livreurs:scores", {livreur: score})

def publish_event(event_type, data):
    """Publie un événement sur le canal Redis"""
    event_data = {
        'type': event_type,
        'data': data,
        'timestamp': datetime.now().isoformat()
    }
    r.publish('system_events', json.dumps(event_data))

def get_livreur_score(livreur_id):
    score = r.zscore("livreurs:scores", livreur_id)
    return float(score) if score else 0.0

def get_all_orders_with_details():
    orders = []
    for key in r.keys("order:*"):
        order_data = r.hgetall(key)
        if order_data:
            orders.append(order_data)
    return orders

def get_assigned_orders_for_livreur(livreur_id):
    orders = []
    for key in r.keys("order:*"):
        order_data = r.hgetall(key)
        if (order_data.get('assigned_driver') == livreur_id and 
            order_data.get('status') == 'assigned'):
            orders.append(order_data)
    return orders

@app.route('/')
def index():
    if 'username' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form['role']
        
        user_data = r.hget("users", username)
        
        if user_data:
            stored_hash, stored_role = user_data.split(':')
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            
            if password_hash == stored_hash and role == stored_role:
                session['username'] = username
                session['role'] = role
                flash('Connexion réussie!', 'success')
                return redirect(url_for('dashboard'))
        
        flash('Identifiants incorrects', 'error')
    
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    role = session['role']
    username = session['username']
    
    if role == 'client':
        orders = get_client_orders(username)
        return render_template('client_simple.html', username=username, orders=orders)
    elif role == 'manager':
        all_orders = get_all_orders_with_details()
        return render_template('manager_simple.html', 
                             username=username,
                             all_orders=all_orders,
                             get_livreur_score=get_livreur_score)
    elif role == 'restaurant':
        orders = get_restaurant_orders()
        return render_template('restaurant_simple.html', username=username, orders=orders)
    elif role == 'livreur':
        available_orders = get_available_orders()
        my_interests = get_my_interests(username)
        assigned_orders = get_assigned_orders_for_livreur(username)
        return render_template('livreur_simple.html', 
                             username=username, 
                             available_orders=available_orders, 
                             my_interests=my_interests,
                             assigned_orders=assigned_orders)
    
    return redirect(url_for('login'))

@app.route('/passer_commande', methods=['POST'])
def passer_commande():
    try:
        id_commande = str(uuid.uuid4())[:8]
        details_commande = {
            "id": id_commande,
            "client": session.get('username'),
            "restaurant": "La Bonne Fourchette",
            "articles": "1x Pizza, 1x Boisson",
            "status": "pending",
        }
        
        r.hset(f"order:{id_commande}", mapping=details_commande)
        publish_event('order_created', {'order_id': id_commande, 'details': details_commande})
        return {'status': 'success', 'order_id': id_commande}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

@app.route('/marquer_prete/<order_id>', methods=['POST'])
def marquer_prete(order_id):
    try:
        # Marquer la commande comme prête
        r.hset(f"order:{order_id}", "status", "ready")
        
        # Démarrer la fenêtre de 60s pour les livreurs
        start_acceptance_window(order_id)
        
        print(f"✅ Fenêtre d'acceptation ouverte pour {order_id}")
        return {'status': 'success'}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

def start_acceptance_window(order_id):
    """Démarre la fenêtre d'acceptation de 60s pour les livreurs"""
    expiration_time = datetime.now() + timedelta(seconds=60)
    r.hset(f"order_timer:{order_id}", 
           mapping={
               "type": "acceptance_window",
               "expires_at": expiration_time.isoformat(),
               "status": "active",
               "created_at": datetime.now().isoformat()
           })
    r.expire(f"order_timer:{order_id}", 60)
    
    # Programmer l'expiration pour déclencher la décision manager
    schedule_manager_decision(order_id, 60)
    
    publish_event('order_ready', {
        'order_id': order_id,
        'expires_at': expiration_time.isoformat()
    })

def schedule_manager_decision(order_id, delay_seconds):
    """Programme la décision du manager après un délai"""
    def start_manager_decision():
        time.sleep(delay_seconds)
        
        # Vérifier si la commande existe toujours et n'est pas déjà assignée
        order_data = r.hgetall(f"order:{order_id}")
        if not order_data or order_data.get('status') != 'ready':
            return
            
        candidates = r.lrange(f"candidates:{order_id}", 0, -1)
        
        if candidates:
            # Démarrer la fenêtre de décision du manager (60s)
            expiration_time = datetime.now() + timedelta(seconds=60)
            r.hset(f"order_timer:{order_id}", 
                   mapping={
                       "type": "manager_decision",
                       "expires_at": expiration_time.isoformat(),
                       "status": "active"
                   })
            r.expire(f"order_timer:{order_id}", 60)
            
            publish_event('manager_decision_started', {
                'order_id': order_id,
                'candidates_count': len(candidates),
                'expires_at': expiration_time.isoformat()
            })
            
            print(f"🔄 Fenêtre manager démarrée pour {order_id} avec {len(candidates)} candidats")
            
            # Programmer l'attribution automatique
            schedule_auto_assignment(order_id, 60)
        else:
            publish_event('no_candidates', {'order_id': order_id})
            print(f"❌ Aucun candidat pour {order_id}")
    
    thread = threading.Thread(target=start_manager_decision, daemon=True)
    thread.start()

def schedule_auto_assignment(order_id, delay_seconds):
    """Programme l'attribution automatique après un délai"""
    def auto_assign():
        time.sleep(delay_seconds)
        
        # Vérifier si la commande existe toujours et n'est pas déjà assignée
        order_data = r.hgetall(f"order:{order_id}")
        if not order_data or order_data.get('status') != 'ready':
            return
            
        candidates = r.lrange(f"candidates:{order_id}", 0, -1)
        
        if candidates:
            # Attribution automatique au meilleur livreur
            best_livreur = None
            best_score = -1
            
            for candidate in candidates:
                score = r.zscore("livreurs:scores", candidate) or 0
                if score > best_score:
                    best_score = score
                    best_livreur = candidate
            
            if best_livreur:
                # Assigner la commande
                r.hset(f"order:{order_id}", "status", "assigned")
                r.hset(f"order:{order_id}", "assigned_driver", best_livreur)
                r.delete(f"candidates:{order_id}")
                r.delete(f"order_timer:{order_id}")
                
                publish_event('auto_assignment', {
                    'order_id': order_id,
                    'driver_id': best_livreur,
                    'score': best_score
                })
                
                print(f"🤖 Attribution automatique: {order_id} -> {best_livreur} (score: {best_score})")
    
    thread = threading.Thread(target=auto_assign, daemon=True)
    thread.start()

@app.route('/montrer_interet/<order_id>', methods=['POST'])
def montrer_interet(order_id):
    try:
        livreur = session.get('username')
        
        # Vérifier si la fenêtre d'acceptation est encore ouverte
        timer_data = r.hgetall(f"order_timer:{order_id}")
        if not timer_data or timer_data.get('type') != 'acceptance_window':
            return {'status': 'error', 'message': 'Fenêtre d\'acceptation fermée'}
        
        # Ajouter le livreur à la liste des candidats
        r.rpush(f"candidates:{order_id}", livreur)
        
        publish_event('driver_interest', {
            'order_id': order_id,
            'driver_id': livreur,
            'driver_score': get_livreur_score(livreur)
        })
        
        print(f"✅ {livreur} a montré son intérêt pour {order_id}")
        return {'status': 'success'}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

@app.route('/choisir_livreur/<order_id>/<livreur>', methods=['POST'])
def choisir_livreur(order_id, livreur):
    try:
        # Assigner la commande au livreur
        r.hset(f"order:{order_id}", "status", "assigned")
        r.hset(f"order:{order_id}", "assigned_driver", livreur)
        
        # Supprimer les candidats et les timers
        r.delete(f"candidates:{order_id}")
        r.delete(f"order_timer:{order_id}")
        
        publish_event('driver_assigned', {
            'order_id': order_id,
            'driver_id': livreur,
            'assigned_by': session.get('username')
        })
        
        print(f"✅ Manager a choisi {livreur} pour {order_id}")
        return {'status': 'success'}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

@app.route('/marquer_livree/<order_id>', methods=['POST'])
def marquer_livree(order_id):
    try:
        r.hset(f"order:{order_id}", "status", "delivered")
        
        publish_event('order_delivered', {
            'order_id': order_id,
            'driver_id': r.hget(f"order:{order_id}", "assigned_driver")
        })
        
        print(f"✅ Commande {order_id} livrée")
        return {'status': 'success'}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

@app.route('/get_order_candidates/<order_id>')
def get_order_candidates(order_id):
    """Récupère les candidats pour une commande spécifique"""
    try:
        candidates = r.lrange(f"candidates:{order_id}", 0, -1)
        candidates_with_scores = []
        
        for candidate in candidates:
            score = get_livreur_score(candidate)
            candidates_with_scores.append({
                'id': candidate,
                'score': score
            })
        
        # Trier par score décroissant
        candidates_with_scores.sort(key=lambda x: x['score'], reverse=True)
        
        return {
            'status': 'success', 
            'candidates': candidates_with_scores,
            'order_status': r.hget(f"order:{order_id}", "status")
        }
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

@app.route('/get_timer_status/<order_id>')
def get_timer_status(order_id):
    """Récupère le statut et le temps restant d'un timer"""
    try:
        timer_data = r.hgetall(f"order_timer:{order_id}")
        if not timer_data:
            return {'status': 'expired'}
        
        # Calculer le temps restant
        expires_at = datetime.fromisoformat(timer_data['expires_at'])
        time_left = max(0, (expires_at - datetime.now()).total_seconds())
        
        return {
            'status': 'active',
            'time_left': int(time_left),
            'type': timer_data.get('type', 'unknown')
        }
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

@app.route('/events')
def events():
    """Endpoint Server-Sent Events pour les mises à jour en temps réel"""
    def generate():
        pubsub = r.pubsub()
        pubsub.subscribe('system_events')
        
        yield "data: {}\n\n".format(json.dumps({'type': 'connected'}))
        
        for message in pubsub.listen():
            if message['type'] == 'message':
                yield "data: {}\n\n".format(message['data'])
    
    return Response(generate(), mimetype='text/event-stream')

@app.route('/debug_timers')
def debug_timers():
    """Page de debug pour voir l'état des timers"""
    timers_info = []
    for key in r.keys("order_timer:*"):
        order_id = key.split(":")[1]
        timer_data = r.hgetall(key)
        candidates = r.lrange(f"candidates:{order_id}", 0, -1)
        order_data = r.hgetall(f"order:{order_id}")
        
        timers_info.append({
            'order_id': order_id,
            'timer': timer_data,
            'candidates': candidates,
            'order_status': order_data.get('status') if order_data else 'unknown'
        })
    
    return jsonify(timers_info)

@app.route('/force_auto_assign/<order_id>', methods=['POST'])
def force_auto_assign(order_id):
    """Forcer l'attribution automatique (pour tests) en utilisant le score et la distance"""
    try:
        candidates = r.lrange(f"candidates:{order_id}", 0, -1)
        
        if not candidates:
            return {'status': 'error', 'message': 'Aucun candidat'}

        # Récupérer les données de la commande pour la localisation du restaurant
        order_data = r.hgetall(f"order:{order_id}")
        if not order_data:
            return {'status': 'error', 'message': 'Commande non trouvée'}

        # Récupérer les coordonnées du restaurant
        resto_lon = order_data.get('restaurant_lon', '2.333')  # Default Paris
        resto_lat = order_data.get('restaurant_lat', '48.865')  # Default Paris
        
        # Calculer le meilleur livreur basé sur score et distance
        best_livreur = None
        best_combined_score = -1
        
        for candidate in candidates:
            # Récupérer le score
            driver_score = get_livreur_score(candidate)
            
            # Récupérer la position
            driver_pos = r.hgetall(f"livreur:{candidate}:position")
            
            if driver_pos:
                # Calculer la distance
                distance = calculate_distance(
                    resto_lon, resto_lat,
                    driver_pos['longitude'], driver_pos['latitude']
                )
                
                # Score combiné: (score^2) / (distance + 1)
                combined_score = (driver_score ** 2) / (distance + 1)
                
                if combined_score > best_combined_score:
                    best_combined_score = combined_score
                    best_livreur = candidate
            else:
                # Si pas de position, utiliser seulement le score
                if driver_score > best_combined_score:
                    best_combined_score = driver_score
                    best_livreur = candidate
        
        if best_livreur:
            r.hset(f"order:{order_id}", "status", "assigned")
            r.hset(f"order:{order_id}", "assigned_driver", best_livreur)
            r.delete(f"candidates:{order_id}")
            r.delete(f"order_timer:{order_id}")
            
            # Récupérer les infos pour le log/l'événement
            driver_pos = r.hgetall(f"livreur:{best_livreur}:position")
            distance_info = ""
            final_driver_score = get_livreur_score(best_livreur)
            
            if driver_pos:
                distance = calculate_distance(
                    resto_lon, resto_lat,
                    driver_pos['longitude'], driver_pos['latitude']
                )
                distance_info = f" (distance: {distance}km)"

            publish_event('auto_assignment', {
                'order_id': order_id,
                'driver_id': best_livreur,
                'score': final_driver_score,
                'distance': distance_info
            })
            
            print(f"🤖 [FORCE] Attribution: {order_id} -> {best_livreur}{distance_info}")

            return {'status': 'success', 
                    'assigned_to': best_livreur,
                    'score': final_driver_score,
                    'combined_score': best_combined_score
                   }
        else:
            return {'status': 'error', 'message': 'Aucun livreur valide'}
            
    except Exception as e:
        return {'status': 'error', 'message': str(e)}
    
@app.route('/logout')
def logout():
    session.clear()
    flash('Déconnexion réussie', 'info')
    return redirect(url_for('login'))

def get_client_orders(username):
    orders = []
    for key in r.keys("order:*"):
        order_data = r.hgetall(key)
        if order_data.get('client') == username:
            orders.append(order_data)
    return orders

def get_restaurant_orders():
    orders = []
    for key in r.keys("order:*"):
        order_data = r.hgetall(key)
        if order_data.get('status') in ['pending', 'ready']:
            orders.append(order_data)
    return orders

def get_available_orders():
    orders = []
    for key in r.keys("order:*"):
        order_data = r.hgetall(key)
        # Commandes prêtes et avec fenêtre d'acceptation active
        timer_data = r.hgetall(f"order_timer:{order_data['id']}")
        if (order_data.get('status') == 'ready' and 
            timer_data and timer_data.get('type') == 'acceptance_window'):
            orders.append(order_data)
    return orders

def get_my_interests(username):
    interests = []
    for key in r.keys("candidates:*"):
        order_id = key.split(":")[1]
        candidates = r.lrange(f"candidates:{order_id}", 0, -1)
        if username in candidates:
            order_data = r.hgetall(f"order:{order_id}")
            if order_data:
                interests.append(order_data)
    return interests

@app.route('/annuler_commande/<order_id>', methods=['POST'])
def annuler_commande(order_id):
    try:
        username = session.get('username')
        
        # Vérifier que la commande appartient bien au client
        order_data = r.hgetall(f"order:{order_id}")
        if not order_data:
            return {'status': 'error', 'message': 'Commande non trouvée'}
        
        if order_data.get('client') != username:
            return {'status': 'error', 'message': 'Vous ne pouvez pas annuler cette commande'}
        
        # Vérifier si un livreur est déjà assigné
        if order_data.get('status') == 'assigned':
            return {'status': 'error', 'message': 'Impossible d\'annuler: un livreur a déjà été assigné'}
        
        # Annuler la commande
        r.hset(f"order:{order_id}", "status", "cancelled")
        
        # Supprimer les candidats et timers associés
        r.delete(f"candidates:{order_id}")
        r.delete(f"order_timer:{order_id}")
        
        publish_event('order_cancelled', {
            'order_id': order_id,
            'client': username,
            'reason': 'Annulé par le client'
        })
        
        print(f"❌ Commande {order_id} annulée par {username}")
        return {'status': 'success'}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}


@app.route('/noter_livreur/<order_id>', methods=['POST'])
def noter_livreur(order_id):
    try:
        data = request.get_json()
        note = data.get('note')
        username = session.get('username')
        
        # Validation de la note
        if note is None or not (1 <= note <= 5):
            return {'status': 'error', 'message': 'Note invalide. Doit être entre 1 et 5'}
        
        # Vérifier que la commande existe et appartient au client
        order_data = r.hgetall(f"order:{order_id}")
        if not order_data:
            return {'status': 'error', 'message': 'Commande non trouvée'}
        
        if order_data.get('client') != username:
            return {'status': 'error', 'message': 'Vous ne pouvez noter que vos propres commandes'}
        
        # Vérifier que la commande est livrée
        if order_data.get('status') != 'delivered':
            return {'status': 'error', 'message': 'Vous ne pouvez noter que les commandes livrées'}
        
        # Vérifier que la commande n'a pas déjà été notée
        if r.hexists(f"order:{order_id}", "client_rating"):
            return {'status': 'error', 'message': 'Cette commande a déjà été notée'}
        
        livreur_id = order_data.get('assigned_driver')
        if not livreur_id:
            return {'status': 'error', 'message': 'Aucun livreur assigné à cette commande'}
        
        # Enregistrer la note
        r.hset(f"order:{order_id}", "client_rating", note)
        r.hset(f"order:{order_id}", "rated_at", datetime.now().isoformat())
        
        # Mettre à jour la note moyenne du livreur
        update_livreur_score(livreur_id, float(note))
        
        publish_event('driver_rated', {
            'order_id': order_id,
            'driver_id': livreur_id,
            'rating': note,
            'client': username
        })
        
        print(f"⭐ Livreur {livreur_id} noté {note}/5 pour la commande {order_id}")
        return {'status': 'success', 'message': f'Merci! Vous avez noté {livreur_id} avec {note} étoiles'}
        
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

def update_livreur_score(livreur_id, new_rating):
    """Met à jour la note moyenne d'un livreur"""
    try:
        # Récupérer les statistiques actuelles du livreur
        stats_key = f"livreur_stats:{livreur_id}"
        current_stats = r.hgetall(stats_key)
        
        if not current_stats:
            # Premier rating
            r.hset(stats_key, mapping={
                "total_rating": new_rating,
                "delivery_count": 1,
                "avg_rating": round(new_rating, 2)
            })
            r.zadd("livreurs:scores", {livreur_id: new_rating})
        else:
            # Mettre à jour les statistiques
            total_rating = float(current_stats.get("total_rating", 0)) + new_rating
            delivery_count = int(current_stats.get("delivery_count", 0)) + 1
            avg_rating = round(total_rating / delivery_count, 2)
            
            r.hset(stats_key, mapping={
                "total_rating": total_rating,
                "delivery_count": delivery_count,
                "avg_rating": avg_rating
            })
            r.zadd("livreurs:scores", {livreur_id: avg_rating})
        
        print(f"📊 Statistiques mises à jour pour {livreur_id}: {avg_rating}/5 ({delivery_count} livraisons)")
        
    except Exception as e:
        print(f"Erreur mise à jour score livreur: {e}")

@app.route('/get_livreur_stats/<livreur_id>')
def get_livreur_stats(livreur_id):
    """Récupère les statistiques d'un livreur"""
    try:
        stats = r.hgetall(f"livreur_stats:{livreur_id}")
        if not stats:
            return {
                'status': 'success',
                'stats': {
                    'avg_rating': 5.0,
                    'delivery_count': 0,
                    'total_rating': 0
                }
            }
        
        return {
            'status': 'success',
            'stats': {
                'avg_rating': float(stats.get('avg_rating', 5.0)),
                'delivery_count': int(stats.get('delivery_count', 0)),
                'total_rating': float(stats.get('total_rating', 0))
            }
        }
    except Exception as e:
        return {'status': 'error', 'message': str(e)}


# Ajouter cette fonction pour calculer la distance
def calculate_distance(lon1, lat1, lon2, lat2):
    """Calcule la distance en km entre deux points GPS"""
    try:
        from math import radians, sin, cos, sqrt, atan2
        
        # Convertir les degrés en radians
        lon1, lat1, lon2, lat2 = map(radians, [float(lon1), float(lat1), float(lon2), float(lat2)])
        
        # Formule de Haversine
        dlon = lon2 - lon1
        dlat = lat2 - lat1
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))
        radius_earth = 6371  # Rayon de la Terre en km
        
        return round(radius_earth * c, 2)
    except Exception as e:
        print(f"Erreur calcul distance: {e}")
        return float('inf')

# Ajouter cette route pour mettre à jour la position du livreur
@app.route('/update_position', methods=['POST'])
def update_position():
    try:
        data = request.get_json()
        livreur_id = session.get('username')
        longitude = data.get('longitude')
        latitude = data.get('latitude')
        
        if not longitude or not latitude:
            return {'status': 'error', 'message': 'Coordonnées manquantes'}
        
        # Stocker la position du livreur
        r.geoadd("livreurs:positions", (longitude, latitude, livreur_id))
        
        # Stocker aussi dans un hash pour récupération facile
        r.hset(f"livreur:{livreur_id}:position", mapping={
            "longitude": longitude,
            "latitude": latitude,
            "updated_at": datetime.now().isoformat()
        })
        
        publish_event('position_updated', {
            'driver_id': livreur_id,
            'longitude': longitude,
            'latitude': latitude
        })
        
        return {'status': 'success', 'message': 'Position mise à jour'}
        
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

# Modifier la fonction d'attribution automatique pour utiliser la distance
def schedule_auto_assignment(order_id, delay_seconds):
    """Programme l'attribution automatique après un délai"""
    def auto_assign():
        time.sleep(delay_seconds)
        
        # Vérifier si la commande existe toujours et n'est pas déjà assignée
        order_data = r.hgetall(f"order:{order_id}")
        if not order_data or order_data.get('status') != 'ready':
            return
            
        candidates = r.lrange(f"candidates:{order_id}", 0, -1)
        
        if candidates:
            # Récupérer les coordonnées du restaurant
            resto_lon = order_data.get('restaurant_lon', '2.333')  # Default Paris
            resto_lat = order_data.get('restaurant_lat', '48.865')  # Default Paris
            
            # Calculer le meilleur livreur basé sur score et distance
            best_livreur = None
            best_score = -1
            
            for candidate in candidates:
                # Récupérer le score
                driver_score = get_livreur_score(candidate)
                
                # Récupérer la position
                driver_pos = r.hgetall(f"livreur:{candidate}:position")
                if driver_pos:
                    # Calculer la distance
                    distance = calculate_distance(
                        resto_lon, resto_lat,
                        driver_pos['longitude'], driver_pos['latitude']
                    )
                    
                    # Score combiné: (score^2) / (distance + 1)
                    # On donne plus de poids au score et on évite la division par zéro
                    combined_score = (driver_score ** 2) / (distance + 1)
                    
                    if combined_score > best_score:
                        best_score = combined_score
                        best_livreur = candidate
                else:
                    # Si pas de position, utiliser seulement le score
                    if driver_score > best_score:
                        best_score = driver_score
                        best_livreur = candidate
            
            if best_livreur:
                # Assigner la commande
                r.hset(f"order:{order_id}", "status", "assigned")
                r.hset(f"order:{order_id}", "assigned_driver", best_livreur)
                r.delete(f"candidates:{order_id}")
                r.delete(f"order_timer:{order_id}")
                
                # Récupérer les infos pour le log
                driver_pos = r.hgetall(f"livreur:{best_livreur}:position")
                distance_info = ""
                if driver_pos:
                    distance = calculate_distance(
                        resto_lon, resto_lat,
                        driver_pos['longitude'], driver_pos['latitude']
                    )
                    distance_info = f" (distance: {distance}km)"
                
                publish_event('auto_assignment', {
                    'order_id': order_id,
                    'driver_id': best_livreur,
                    'score': get_livreur_score(best_livreur),
                    'distance': distance_info
                })
                
                print(f"🤖 Attribution automatique: {order_id} -> {best_livreur}{distance_info}")
    
    thread = threading.Thread(target=auto_assign, daemon=True)
    thread.start()

# Ajouter une route pour récupérer la position actuelle
@app.route('/get_my_position')
def get_my_position():
    try:
        livreur_id = session.get('username')
        position = r.hgetall(f"livreur:{livreur_id}:position")
        
        if position:
            return {
                'status': 'success',
                'position': position
            }
        else:
            return {
                'status': 'success',
                'position': None
            }
    except Exception as e:
        return {'status': 'error', 'message': str(e)}


@app.context_processor
def utility_processor():
    def has_candidates(order_id):
        return r.llen(f"candidates:{order_id}") > 0
    
    def get_candidates_count(order_id):
        return r.llen(f"candidates:{order_id}")
    
    def get_timer_data(order_id):
        return r.hgetall(f"order_timer:{order_id}")
    
    return {
        'has_candidates': has_candidates,
        'get_candidates_count': get_candidates_count,
        'get_timer_data': get_timer_data
    }

if __name__ == '__main__':
    with app.app_context():
        init_test_users()
    app.run(debug=True, port=5000, threaded=True)