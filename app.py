from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import redis
import hashlib
import uuid
import time
import threading
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
        pending_decisions = get_pending_decisions()
        all_orders = get_all_orders_with_details()
        return render_template('manager_simple.html', 
                             username=username, 
                             pending_decisions=pending_decisions,
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
        return {'status': 'success', 'order_id': id_commande}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

@app.route('/marquer_prete/<order_id>', methods=['POST'])
def marquer_prete(order_id):
    try:
        # Marquer la commande comme prête
        r.hset(f"order:{order_id}", "status", "ready")
        
        # Démarrer la fenêtre de 60s pour les livreurs avec timestamp
        expiration_time = datetime.now() + timedelta(seconds=60)
        r.hset(f"order_timer:{order_id}", 
               mapping={
                   "type": "acceptance_window",
                   "expires_at": expiration_time.isoformat(),
                   "status": "active",
                   "created_at": datetime.now().isoformat()
               })
        r.expire(f"order_timer:{order_id}", 60)
        
        print(f"✅ Fenêtre d'acceptation ouverte pour {order_id}")
        return {'status': 'success', 'expires_at': expiration_time.isoformat()}
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
        
        print(f"✅ Manager a choisi {livreur} pour {order_id}")
        return {'status': 'success'}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

@app.route('/marquer_livree/<order_id>', methods=['POST'])
def marquer_livree(order_id):
    try:
        r.hset(f"order:{order_id}", "status", "delivered")
        print(f"✅ Commande {order_id} livrée")
        return {'status': 'success'}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

@app.route('/get_orders_status')
def get_orders_status():
    """Endpoint pour debuguer l'état des commandes"""
    orders_info = []
    for key in r.keys("order:*"):
        order_data = r.hgetall(key)
        timer_data = r.hgetall(f"order_timer:{order_data['id']}")
        candidates = r.lrange(f"candidates:{order_data['id']}", 0, -1)
        
        orders_info.append({
            'order': order_data,
            'timer': timer_data,
            'candidates': candidates
        })
    
    return jsonify(orders_info)

@app.route('/debug_timers')
def debug_timers():
    """Page de debug pour voir tous les timers"""
    timers = []
    for key in r.keys("order_timer:*"):
        timer_data = r.hgetall(key)
        order_id = key.split(":")[1]
        timers.append({
            'order_id': order_id,
            'data': timer_data
        })
    
    return jsonify(timers)

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

def get_pending_decisions():
    """Récupère les commandes qui attendent une décision du manager"""
    decisions = []
    for key in r.keys("order_timer:*"):
        timer_data = r.hgetall(key)
        order_id = key.split(":")[1]
        
        # Vérifier si c'est une fenêtre manager active OU si la commande est ready avec des candidats
        if (timer_data.get('type') == 'manager_decision' or 
            (timer_data.get('type') == 'acceptance_window' and r.llen(f"candidates:{order_id}") > 0)):
            
            order_data = r.hgetall(f"order:{order_id}")
            candidates = r.lrange(f"candidates:{order_id}", 0, -1)
            
            if order_data and order_data.get('status') == 'ready':
                # Ajouter les scores des candidats
                candidates_with_scores = []
                for candidate in candidates:
                    score = get_livreur_score(candidate)
                    candidates_with_scores.append({
                        'id': candidate,
                        'score': score
                    })
                
                # Trier par score
                candidates_with_scores.sort(key=lambda x: x['score'], reverse=True)
                
                decisions.append({
                    'order': order_data,
                    'candidates': candidates_with_scores,
                    'timer_type': timer_data.get('type', 'unknown')
                })
    
    return decisions

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

# Thread pour gérer les expirations de timers
def start_timer_listener():
    def check_expirations():
        while True:
            try:
                # Vérifier les fenêtres d'acceptation qui expirent
                for key in r.keys("order_timer:*"):
                    timer_data = r.hgetall(key)
                    order_id = key.split(":")[1]
                    
                    if timer_data.get('type') == 'acceptance_window':
                        # Vérifier si le timer a expiré
                        if not r.exists(key):
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
                                print(f"🔄 Fenêtre manager démarrée pour {order_id} avec {len(candidates)} candidats")
                            else:
                                print(f"❌ Aucun candidat pour {order_id}")
                
                # Vérifier les décisions manager qui expirent
                for key in r.keys("order_timer:*"):
                    timer_data = r.hgetall(key)
                    order_id = key.split(":")[1]
                    
                    if timer_data.get('type') == 'manager_decision':
                        # Vérifier si le timer a expiré
                        if not r.exists(key):
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
                                    r.hset(f"order:{order_id}", "status", "assigned")
                                    r.hset(f"order:{order_id}", "assigned_driver", best_livreur)
                                    r.delete(f"candidates:{order_id}")
                                    print(f"🤖 Attribution automatique: {order_id} -> {best_livreur} (score: {best_score})")
                
                time.sleep(2)  # Vérifier toutes les 2 secondes
            except Exception as e:
                print(f"Erreur timer: {e}")
                time.sleep(5)
    
    thread = threading.Thread(target=check_expirations, daemon=True)
    thread.start()

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
        start_timer_listener()
    app.run(debug=True, port=5000)