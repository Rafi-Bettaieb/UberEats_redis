# Livraison Express - Application de Livraison de Nourriture

## Description
Application web de livraison de nourriture développée avec Flask et Redis. Le système permet aux clients de commander de la nourriture, aux restaurants de préparer les commandes, aux livreurs de livrer et aux managers de superviser le processus.

## Architecture
- Backend: Flask avec Redis comme base de données
- Frontend: Templates HTML avec Bootstrap
- Temps réel: Server-Sent Events (SSE) pour les mises à jour en direct

## Rôles Utilisateurs
1. Client - Passer des commandes et suivre leur statut
2. Restaurant - Préparer les commandes et les marquer comme prêtes
3. Livreur - Accepter et livrer les commandes
4. Manager - Superviser et assigner les livreurs ou assignation automatique après un certain temps

## Prérequis
- Python 3.8+
- Redis Server

## Installation

### 1. Cloner le repository
- en utilisant SSH :
  git clone git@github.com:Rafi-Bettaieb/UberEats_redis.git

- en utilisant HTTPS :
  https://github.com/Rafi-Bettaieb/UberEats_redis.git

cd delivery-app

### 2. Activer l'environnement virtuel

Sur Windows:
venv\Scripts\activate

Sur Mac/Linux:
source venv/bin/activate

### 3. Installer les dépendances
pip install -r requirements.txt

### 4. Démarrer Redis Server

Sur Windows:
- Téléchargez Redis depuis https://redis.io/download
- Extrayez et lancez redis-server.exe

Sur Mac (avec Homebrew):
brew install redis
redis-server

Sur Linux (Ubuntu/Debian):
sudo apt update
sudo apt install redis-server
redis-server

### 5. Vérifier que Redis fonctionne
Ouvrez un nouveau terminal et testez la connexion:
redis-cli ping
Vous devriez voir PONG comme réponse.

## Démarrage de l'Application
### 1. Lancer l'application Flask
python app_redis.py

### 2. Initialiser les données de test
L'application va automatiquement charger les données depuis donnees_fusionnees_avec_menus.json au premier démarrage.

### 3. Accéder à l'application
Ouvrez votre navigateur et allez sur:
http://localhost:5000

## Comptes de Test

Client
- Username: client1
- Password: 123456
- Role: client

Restaurant
- Username: restaurant1
- Password: 123456
- Role: restaurant

Livreur
- Username: livreur1
- Password: 123456
- Role: livreur

Manager
- Username: manager1
- Password: 123456
- Role: manager

## Utilisation

Pour les Clients:
1. Connectez-vous avec un compte client
2. Cliquez sur "Passer une commande"
3. Sélectionnez un restaurant et des articles
4. Suivez le statut de votre commande en temps réel
5. Notez le livreur après livraison

Pour les Restaurants:
1. Connectez-vous avec un compte restaurant
2. Consultez les commandes en attente
3. Marquez les commandes comme "prêtes" quand elles sont préparées

Pour les Livreurs:
1. Connectez-vous avec un compte livreur
2. Consultez les commandes disponibles
3. Montrez votre intérêt pour les commandes
4. Mettez à jour votre position GPS
5. Marquez les commandes comme livrées

Pour les Managers:
1. Connectez-vous avec un compte manager
2. Supervisez toutes les commandes
3. Assignez manuellement des livreurs si nécessaire

## Structure des Fichiers
delivery-app/
├── app_redis.py          # Application principale Flask
├── donnees_fusionnees_avec_menus.json  # Données de test
├── templates/            # Templates HTML
│   ├── client_simple.html
│   ├── restaurant_simple.html
│   ├── livreur_simple.html
│   ├── manager_simple.html
│   └── login.html
├── requirements.txt      # Dépendances Python
└── README.md            # Documentation

## Fonctionnalités Temps Réel
- Mise à jour automatique des statuts de commande
- Notifications en temps réel
- Fenêtres de temps pour l'acceptation des livreurs
- Attribution automatique des livreurs

