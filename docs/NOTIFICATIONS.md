# TECHcare — Notifications et alertes

## Exigences prises en compte

La réalisation s’appuie sur le module transverse du **backlog.pdf, pages 4–5**, et la section **13 — Notifications du cahier des charges PC TechCare, page 11**. Elle conserve la stack choisie pour ce projet : HTML, CSS, JavaScript, Django et MySQL.

| Événement demandé | Destinataires | Intégration dans la version actuelle |
| --- | --- | --- |
| Rendez-vous confirmé | Client | Automatique à la confirmation |
| Rappel J‑1 | Client et technicien | Automatique pour les rendez-vous confirmés du lendemain, en heure de Tunis |
| Rendez-vous modifié ou annulé | Client et technicien | Automatique ; l’ancien technicien est également averti lors d’une réaffectation |
| Nouvelle recommandation | Client propriétaire du PC | Automatique à la création ou réactivation d’un conseil ; les conseils actifs existants sont repris une seule fois |
| Technicien affecté | Client et technicien | Automatique pour les rendez-vous et les demandes de réparation ; l’ancien technicien est averti en cas de réaffectation |
| Changement de statut | Client | Automatique pour les rendez-vous et les réparations indépendantes |
| Message reçu | Client ou technicien concerné | Automatique pour les discussions des rendez-vous et des demandes de réparation |
| Évaluation reçue | Technicien concerné | Automatique après la publication d’un avis client sur une prise en charge clôturée |
| Pièce attendue / stock faible | Client et technicien pour la pièce attendue ; administrateurs pour le stock | La mise en attente d’une réparation avertit ses participants ; les alertes globales de stock restent dans l’administration |
| Rapport et facture prêts | Client | Notification supplémentaire à la clôture, liée au module 7 |

Les modules 4 et 5 sont intégrés via `repairs/services.py` et `inventory/services.py`. Les messages des rendez-vous et les nouveaux avis sont intégrés via `appointments/messaging.py` et `feedback/services.py`. Voir [la couverture du backlog](COUVERTURE_BACKLOG.md).

## Interfaces

- **Cloche** dans l’en-tête et lien **Notifications** dans le menu des espaces client, technicien et administrateur.
- **`/notifications/`** : notifications personnelles, compteurs, filtre non lues, catégories, recherche et pagination.
- Actions : consulter la ressource liée, marquer comme lue, marquer comme non lue et tout marquer comme lu.
- Compteur actualisé pendant l’utilisation du site ; une bannière propose de recharger une liste déjà ouverte quand une nouvelle alerte arrive.
- Les alertes reprennent le thème sombre bleu nuit et orange, avec les mêmes contrôles sur mobile.
- Le panneau **Activer les alertes** demande l’autorisation du navigateur uniquement après un clic de l’utilisateur.

Le centre `/notifications/` reste personnel, y compris pour les administrateurs. La cloche y conduit. Dans le menu de l’administrateur, **Gestion des notifications** ouvre désormais `/backoffice/notifications/` : une interface dédiée aux envois, avec historique, filtres et suivi de lecture. L’administration technique Django permet de consulter les événements et l’état des envois, sans exposer les clés des abonnements dans les formulaires.

### Gestion et envoi par l’administrateur

Cette interface ajoute l’envoi manuel demandé pour le projet aux rappels et alertes automatiques du backlog.

1. Ouvrir **Gestion des notifications → Envoyer une notification**.
2. Choisir **Tous les clients**, **Tous les techniciens**, **Clients et techniciens**, ou **Destinataires précis**. Dans ce dernier cas, rechercher et cocher les comptes concernés. Les comptes suspendus et les administrateurs sont exclus ; un technicien actif reçoit les communications même s’il n’accepte temporairement plus de nouveaux rendez-vous.
3. Rédiger un titre (150 caractères maximum), le message (700 caractères maximum) et choisir la priorité. Un aperçu et le nombre de destinataires sont affichés pendant la rédaction.
4. Cliquer sur **Envoyer la notification** : chaque compte reçoit immédiatement un message privé de type « Message de l’administration » dans son espace. L’alerte navigateur est mise en attente uniquement pour ses abonnements actifs.
5. Consulter **Voir le suivi** : destinataires, lecture/non-lecture, recherche, pagination et état des envois navigateur. Un push accepté par son fournisseur ne prouve pas que le destinataire a lu le message.
6. **Retirer la notification** masque cette diffusion dans les centres des destinataires et annule les push encore en attente. Le contenu, la liste des destinataires restants, le nombre initial et les lectures restent dans l’historique. Une alerte déjà affichée par un navigateur ne peut pas être rappelée.

Les envois publiés ne se modifient pas : rédiger une nouvelle notification pour communiquer une correction. Chaque formulaire d’envoi possède un identifiant unique ; un double clic ou la répétition du même POST ne crée pas de doublon. Le public est figé lors de l’envoi : un nouveau compte créé ensuite ne reçoit pas rétroactivement le message.

Les trois écrans sont réservés aux administrateurs actifs ; les envois et retraits utilisent POST et CSRF et sont journalisés. Un envoi est atomique avec les notifications et les tâches push. Les tableaux de suivi portent sur les messages de l’administration ; les conversations privées client/technicien ne sont pas affichées dans cet historique. Les actions de lecture restent propres au destinataire.

Le panneau **Alertes automatiques** présente des compteurs des rappels J−1, réservations/modifications, conseils de maintenance et suivis/pièces/documents. Ces événements continuent de se déclencher via leurs règles métier. L’envoi manuel ne permet pas de fabriquer une confirmation ou un changement de statut de rendez-vous. La rubrique réparations reste retirée de l’espace administrateur.

## Mise en route

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py setup_webpush
.\.venv\Scripts\python.exe manage.py run_techcare
```

`run_techcare` démarre le serveur de développement et le traitement des rappels/envois dans le même processus serveur. L’autorechargement du code garde un seul traitement dans le processus qui sert effectivement l’application. Arrêter le serveur arrête ce traitement.

Ouvrir http://127.0.0.1:8000/notifications/ avec un compte connecté. Pour recevoir des alertes système, cliquer sur **Activer les alertes**, puis accepter la demande du navigateur. Cette autorisation est propre à chaque navigateur.

Le serveur doit rester lancé pour générer les événements, traiter les rappels et vérifier les notifications arrivant dans le navigateur. L’onglet peut être fermé.

### Exécution séparée ou planifiée

La commande habituelle `manage.py runserver` reste disponible. Avec elle, lancer le traitement dans un second terminal :

```powershell
.\.venv\Scripts\python.exe manage.py run_notifications
```

Un passage unique est disponible pour le Planificateur de tâches Windows ou cron :

```powershell
.\.venv\Scripts\python.exe manage.py run_notifications --once
```

Le passage peut être programmé chaque minute. Le mode continu vérifie les rappels et l’outbox toutes les 30 secondes et réévalue les recommandations au changement de date de Tunis. Il n’est pas nécessaire de lancer un second traitement quand `run_techcare` est utilisé.

## Web Push

Le centre MySQL et son compteur fonctionnent sans autorisation de notifications système. Les envois navigateur utilisent le standard Web Push avec un service worker, des clés VAPID et [pywebpush](https://github.com/web-push-libs/pywebpush).

`setup_webpush` génère une clé privée dans `.private/webpush-private.pem` et configure les variables `WEBPUSH_PRIVATE_KEY` / `WEBPUSH_PUBLIC_KEY` dans `.env`. Une clé privée existante est réutilisée, sans rotation automatique. `.private/` et `.env` sont exclus de Git. `WEBPUSH_SUBJECT` identifie le contact du projet par une URL HTTPS ou un contact `mailto:`.

Pour un hébergement, utiliser HTTPS et un processus permanent ou une tâche planifiée pour `run_notifications`. En développement, les adresses loopback sont utilisables comme contexte sécurisé. Le support et les autorisations dépendent du navigateur ; voir la [documentation de PushManager.subscribe()](https://developer.mozilla.org/en-US/docs/Web/API/PushManager/subscribe). Les fournisseurs de push doivent être accessibles par le réseau du navigateur et du serveur.

Le service worker reçoit le message, vérifie que l’utilisateur et le navigateur sont toujours autorisés, affiche la notification système et ouvre le centre d’alertes lors du clic. Il ne met pas en cache les pages ou les données privées.

## Règles métier et fiabilité

- Les événements métier et leurs notifications sont enregistrés dans la même transaction MySQL. Une réservation rejetée ou une transaction annulée ne laisse aucune notification partielle.
- Une contrainte unique `(recipient, event_key)` évite les doublons. La réévaluation d’un conseil déjà actif ne renvoie pas d’alerte identique.
- J‑1 correspond au **jour civil précédent en heure de Tunis**, pas à un délai glissant de 24 heures. Les bornes sont converties en dates/heures pour MySQL sans dépendre de ses tables de fuseaux horaires.
- Seuls les rendez-vous confirmés reçoivent un rappel. Une modification, annulation ou clôture invalide les anciens rappels.
- Les comptes inactifs ne reçoivent pas de nouveaux événements.
- Un lien d’une ancienne affectation n’accorde pas l’accès à un rendez-vous réaffecté à un autre technicien.
- Les rappels expirés et les conseils devenus inactifs sortent des alertes courantes.
- Le navigateur ne reçoit que les alertes destinées au compte actuellement connecté. La déconnexion désactive l’abonnement de ce navigateur et annule ses envois encore en attente.
- Un changement de compte dans un même navigateur requiert un nouvel accord dans l’interface ; le transfert d’un abonnement existant est lié à un cookie de navigateur signé et HttpOnly.
- Les abonnements Web Push vérifient les clés et n’acceptent que les domaines HTTPS des fournisseurs pris en charge. Les adresses locales, ports inattendus, identifiants dans l’URL et redirections sont refusés.

### Outbox des envois

Les requêtes métier ne contactent pas les fournisseurs de push. Elles créent des envois dans `PushDelivery`.

Le traitement réserve un lot avec des verrous MySQL, libère la transaction, puis contacte les fournisseurs avec un délai réseau borné. Les erreurs temporaires sont retentées avec un délai croissant, au maximum cinq essais. Les réponses 404/410 désactivent l’abonnement expiré. Un traitement interrompu est repris après expiration de sa réservation.

Chaque couple notification/navigateur est unique. Le tag système utilise l’identifiant de notification pour remplacer une éventuelle répétition de transport. Avant affichage, le service worker vérifie aussi que l’alerte n’est pas devenue périmée ou étrangère au compte courant.

## Emplacement du code

| Fichier | Rôle |
| --- | --- |
| `notifications/models.py` | Notifications, abonnements navigateur et outbox |
| `notifications/services.py` | Création, destinataires, déduplication, rappels et intégrations métier |
| `notifications/campaigns.py`, `forms.py` | Diffusions administrateur, publics actifs, validation, envoi atomique et retrait |
| `notifications/admin_views.py` | Historique, rédaction, suivi de lecture et retrait réservés au backoffice |
| `notifications/push.py` | Validation des abonnements, contrôles de pertinence, envois et reprises |
| `notifications/views.py`, `urls.py` | Centre, flux privé, lecture et gestion des abonnements |
| `notifications/context_processors.py` | Compteur et repère du dernier événement |
| `notifications/signals.py` | Désactivation du navigateur à la déconnexion |
| `notifications/management/commands/` | Clés, traitement continu et lancement intégré |
| `notifications/migrations/` | Schéma MySQL |
| `notifications/tests.py` | Événements, permissions, J‑1, Web Push et déduplication |
| `notifications/test_campaigns.py` | Destinataires, sécurité, déduplication d’envoi, suivi et retrait |
| `templates/notifications/` | Cloche et centre d’alertes |
| `static/css/notifications.css` | Styles responsive |
| `static/js/notifications.js` | Compteur, retours visuels et consentement |
| `static/css/notification-management.css`, `static/js/notification-management.js` | Interface admin responsive, aperçu et sélection des destinataires |
| `static/js/notifications-sw.js` | Réception des push et ouverture du centre |
| `appointments/services.py` | Déclenchements liés aux rendez-vous et interventions |
| `maintenance/services.py` | Déclenchements liés aux recommandations |

Tables ajoutées : `notifications_notification`, `notifications_pushsubscription`, `notifications_pushdelivery`, `notifications_notificationcampaign`. La migration `0005` ajoute les diffusions et leur lien facultatif dans les notifications, en conservant les anciens événements et abonnements.

## Vérification avec le professeur

1. Réserver un rendez-vous avec le compte client et consulter la notification de création.
2. Ouvrir le compte du technicien pour retrouver l’affectation et confirmer le rendez-vous.
3. Revenir au client pour montrer la confirmation et le compteur.
4. Avancer les statuts et clôturer l’intervention ; montrer le lien vers les PDF.
5. Montrer les actions lu/non lu, le filtre non lues et la recherche.
6. Ajouter un PC déclenchant une règle de maintenance ; montrer une seule alerte malgré plusieurs analyses.
7. Préparer un rendez-vous confirmé pour le lendemain puis lancer `run_notifications --once` afin de montrer le rappel J‑1 aux deux destinataires.
8. Activer les alertes sur un navigateur compatible et montrer le service worker. L’accord et la connexion aux services de push sont nécessaires pour un envoi réel.
9. Côté admin, ouvrir **Gestion des notifications**, choisir un client et un technicien, rédiger un message et l’envoyer. Montrer sa réception dans les deux espaces et le suivi de lecture dans l’administration.
10. Retirer cette diffusion et vérifier qu’elle quitte les centres des destinataires tout en restant dans l’historique administrateur.

Les tests serveur utilisent MySQL isolé. Les contrôles navigateur vérifient les pages, les compteurs et le service worker ; l’inscription au fournisseur peut être simulée dans le profil de test pour éviter de dépendre d’un service externe.
