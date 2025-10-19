// static/js/main.js

document.addEventListener("DOMContentLoaded", () => {
    // Se connecte au serveur SocketIO
    // (l'URL est implicite si servi par le même hôte)
    const socket = io();

    socket.on("connect", () => {
        console.log("Connecté au serveur SocketIO !");
    });

    // --- LOGIQUE CLIENT ---
    const btnPlaceOrder = document.getElementById("btn-place-order");
    const statusContainer = document.getElementById("status-container");

    if (btnPlaceOrder) {
        btnPlaceOrder.addEventListener("click", () => {
            const selectedItems = [];
            document.querySelectorAll("input[name='menu_item']:checked").forEach((checkbox) => {
                selectedItems.push(checkbox.value);
            });
            
            if (selectedItems.length > 0) {
                console.log("Envoi de la commande:", selectedItems);
                socket.emit("place_order", { articles: selectedItems });
                btnPlaceOrder.disabled = true;
                btnPlaceOrder.textContent = "Commande envoyée !";
            } else {
                alert("Veuillez sélectionner au moins un article.");
            }
        });
    }

    if (statusContainer) {
        // Écoute les mises à jour de statut de commande
        socket.on("order_status_update", (data) => {
            console.log("Mise à jour statut:", data);
            statusContainer.innerHTML = `
                <h3>Commande ${data.id}</h3>
                <p><strong>Statut: ${data.status}</strong></p>
                <p>${data.message}</p>
            `;
            if (data.status === "delivered") {
                 btnPlaceOrder.disabled = false;
                 btnPlaceOrder.textContent = "Passer la commande";
            }
        });

        // Écoute les mises à jour du menu (poussées par le restaurant)
        socket.on("menu_updated", (menu) => {
            const menuContainer = document.getElementById("menu-container");
            let menuHTML = '';
            let i = 1;
            for (const [item, price] of Object.entries(menu)) {
                menuHTML += `
                <div>
                    <input type="checkbox" name="menu_item" value="${item}" id="item-${i}">
                    <label for="item-${i}">${item} - ${price}€</label>
                </div>`;
                i++;
            }
            menuHTML += `<br><button id="btn-place-order">Passer la commande</button>`;
            menuContainer.innerHTML = menuHTML;
            // Recréer l'event listener car le bouton a été recréé
            document.getElementById("btn-place-order").addEventListener("click", () => {
                 // ... (logique de commande dupliquée, à améliorer)
            });
        });
    }

    // --- LOGIQUE RESTAURANT ---
    const btnAddItem = document.getElementById("btn-add-item");
    const restaurantTasks = document.getElementById("restaurant-tasks-container");

    if (btnAddItem) {
        btnAddItem.addEventListener("click", () => {
            const nom = document.getElementById("new-item-name").value;
            const prix = document.getElementById("new-item-price").value;
            if (nom && prix) {
                socket.emit("restaurant_add_item", { nom: nom, prix: parseFloat(prix) });
                // Mettre à jour la liste locale
                document.getElementById("menu-list").innerHTML += `<li>${nom} - ${prix}€</li>`;
                document.getElementById("new-item-name").value = '';
                document.getElementById("new-item-price").value = '';
            }
        });
    }

    if (restaurantTasks) {
        // Écoute les nouvelles commandes à préparer
        socket.on("new_order_for_restaurant", (order) => {
            if(restaurantTasks.querySelector('p')) restaurantTasks.innerHTML = ''; // Vider le msg par défaut
            
            const card = document.createElement("div");
            card.className = "card";
            card.id = `order-prep-${order.id}`;
            card.innerHTML = `
                <h4>Commande ${order.id}</h4>
                <p>Client: ${order.client}</p>
                <p>Articles: ${order.articles}</p>
                <p>Statut: <span id="status-${order.id}">${order.status}</span></p>
            `;
            restaurantTasks.appendChild(card);
            
            // NOTE: Le script 'restaurant.py' d'origine n'a pas d'action manuelle.
            // La préparation se lance automatiquement.
            // Dans une vraie app, on ajouterait un bouton "Commencer la préparation".
        });
        
        // Mettre à jour le statut si la commande devient prête (via le thread)
        socket.on("order_status_update", (data) => {
             const statusEl = document.getElementById(`status-${data.id}`);
             if (statusEl && data.status === 'ready') {
                 statusEl.textContent = 'Prête !';
             }
        });
    }


    // --- LOGIQUE LIVREUR ---
    const livreurTasks = document.getElementById("livreur-tasks-container");

    if (livreurTasks) {
        // Écoute les nouvelles commandes disponibles
        socket.on("new_order_for_livreur", (order) => {
            if(livreurTasks.querySelector('p')) livreurTasks.innerHTML = '';
            
            const card = document.createElement("div");
            card.className = "card";
            card.id = `order-accept-${order.id}`;
            card.innerHTML = `
                <h4>Nouvelle Commande: ${order.id}</h4>
                <p>Restaurant: ${order.restaurant}</p>
                <p>Articles: ${order.articles}</p>
                <button class="btn-accept" data-order-id="${order.id}">Accepter (Fenêtre de 60s)</button>
            `;
            livreurTasks.appendChild(card);
        });

        // Gérer le clic sur "Accepter"
        livreurTasks.addEventListener("click", (e) => {
            if (e.target.classList.contains("btn-accept")) {
                const id_commande = e.target.dataset.orderId;
                socket.emit("livreur_accept_order", { id_commande: id_commande });
                e.target.textContent = "Candidature envoyée...";
                e.target.disabled = true;
            }
        });
        
        // Confirmation ou échec de l'acceptation
        socket.on("acceptance_confirmed", (data) => {
             const btn = livreurTasks.querySelector(`.btn-accept[data-order-id="${data.id_commande}"]`);
             if(btn) btn.textContent = "Candidature reçue !";
        });
        socket.on("acceptance_failed", (data) => {
             alert(data.message); // Simple alerte
        });
        
        // Notification d'assignation
         socket.on("order_status_update", (data) => {
             if (data.status === 'assigned') {
                 // Si on est le livreur assigné (on ne le sait pas ici, mais on reçoit le statut)
                 // Pour simplifier, on vide les tâches
                 livreurTasks.innerHTML = `<p>Vous êtes en livraison pour la commande ${data.id}.</p>`;
             }
             if (data.status === 'delivered') {
                 livreurTasks.innerHTML = `<p>Commande ${data.id} livrée ! En attente de nouvelles commandes.</p>`;
             }
        });
    }
    

    // --- LOGIQUE MANAGER ---
    const managerTasks = document.getElementById("manager-tasks-container");
    
    if (managerTasks) {
        // Écoute les demandes de décision
        socket.on("manager_action_required", (data) => {
            if(managerTasks.querySelector('p')) managerTasks.innerHTML = '';
            
            const card = document.createElement("div");
            card.className = "card";
            card.id = `order-assign-${data.id_commande}`;
            
            let candidatsHTML = '<ul>';
            data.candidats.forEach(c => {
                candidatsHTML += `
                <li>
                    <strong>${c.id}</strong> (⭐ ${c.score}, 📍 ${c.distance_km} km, 📈 Reco: ${c.recommendation.toFixed(2)})
                    <button class="btn-assign" data-order-id="${data.id_commande}" data-livreur-id="${c.id}">
                        Assigner
                    </button>
                </li>`;
            });
            candidatsHTML += '</ul>';
            
            card.innerHTML = `
                <h4>Décision Requise: Commande ${data.id_commande} (Fenêtre de 60s)</h4>
                <p>Choisissez un livreur :</p>
                ${candidatsHTML}
            `;
            managerTasks.appendChild(card);
        });
        
        // Gérer le clic sur "Assigner"
        managerTasks.addEventListener("click", (e) => {
            if (e.target.classList.contains("btn-assign")) {
                const id_commande = e.target.dataset.orderId;
                const id_livreur = e.target.dataset.livreurId;
                
                socket.emit("manager_assign_driver", { id_commande: id_commande, id_livreur: id_livreur });
                
                // Mettre à jour l'interface
                const card = document.getElementById(`order-assign-${id_commande}`);
                card.innerHTML = `<h4>Assignation de ${id_commande} à ${id_livreur} en cours...</h4>`;
            }
        });
        
        // Gérer le cas où l'assignation auto a eu lieu
        socket.on("manager_auto_assigned", (data) => {
            const card = document.getElementById(`order-assign-${data.id_commande}`);
            if (card) {
                card.innerHTML = `<h4>Temps écoulé ! Commande ${data.id_commande} auto-assignée à ${data.livreur_id}.</h4>`;
            }
        });
        
        // Gérer le cas où la commande est assignée (par nous ou un autre manager)
        socket.on("order_status_update", (data) => {
             const card = document.getElementById(`order-assign-${data.id}`);
             if (card && (data.status === 'assigned' || data.status === 'delivered')) {
                 card.remove(); // Nettoyer la tâche
             }
        });
    }
});