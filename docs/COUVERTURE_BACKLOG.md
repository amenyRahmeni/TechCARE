# Couverture du backlog TECHcare

Référence : `backlog.pdf`, six pages. Réalisation web avec **Django, HTML, CSS, JavaScript natif et MySQL**, conformément au choix du projet. Les noms Spring Security, repositories et FXML du document sont adaptés aux mécanismes Django : services Python, ORM, migrations, vues, formulaires et templates.

## Fonctionnalités par rôle

| Espace | Fonctionnalités |
| --- | --- |
| Client | Inscription et connexion par e-mail ou identifiant ; profil et mot de passe ; CRUD de ses PC ; historique et recommandations ; réservation et suivi des rendez-vous ; déclaration de panne avec photo privée et choix du technicien qualifié ; discussion avec le technicien ; rapports et factures PDF ; avis de 1 à 5 après clôture ; FAQ et notifications personnelles. |
| Technicien | Rendez-vous et réparations assignés ; consultation technique des PC concernés ; modification/annulation avant réparation ; diagnostic, solution et statuts ; discussion avec le client ; compatibilité et utilisation de composants du stock ; annonces personnelles et vitrine des autres techniciens ; avis clients et note moyenne ; FAQ, profil et notifications. |
| Administrateur | Tableau de bord et graphiques ; gestion et suspension des comptes ; profils/compétences des techniciens ; parc informatique ; suivi des rendez-vous et de leurs échanges ; règles de maintenance ; stock et mouvements ; supervision de la vitrine ; documents PDF ; suivi des évaluations ; création, modification, publication et suppression de questions FAQ. |

Les contrôles s’appliquent aux vues **et aux services**, y compris en cas d’URL directe ou de formulaire modifié. Le client voit ses données ; le technicien voit ses prises en charge assignées ; l’administrateur supervise l’atelier. La rubrique Assistance & réparation est réservée au client et au technicien choisi ; ses pages et actions sont bloquées pour l’administrateur, y compris dans l’administration Django. Le client choisit le technicien dans une liste filtrée par compétence, disponibilité et activation. La création de nouveaux rendez-vous est réservée aux clients : l’administrateur consulte et gère les rendez-vous existants, sans pouvoir en réserver depuis une autre URL. L’inscription publique demande le prénom, le nom, l’e-mail et le mot de passe confirmé, puis crée un compte client actif. L’identifiant interne Django est généré automatiquement et n’est pas demandé au client. Les techniciens sont créés par l’administration avec leurs compétences.

## Matrice des user stories

| Module / US | Réalisation | Fichiers principaux |
| --- | --- | --- |
| 1 / 1 — Inscription | Identité, e-mail unique normalisé, validation, compte client actif, mot de passe haché BCrypt SHA-256. | `accounts/forms.py`, `accounts/services.py`, `accounts/models.py`, `templates/registration/signup.html` |
| 1 / 2 — Connexion e-mail / JWT | Authentification e-mail ou identifiant ; accès navigateur par session Django ; génération et validation de JWT signés, expiration 20 min et vérification du compte actif. | `accounts/backends.py`, `accounts/tokens.py`, `accounts/views.py`, `config/settings.py` |
| 1 / 3 — Gestion des comptes | Création, modification, activation/suspension et rôle ; protection des administrateurs et du compte de l’administrateur connecté ; audit. | `backoffice/forms.py`, `backoffice/views.py`, `templates/backoffice/accounts.html` |
| 1 / 4 — Messages liés à l’intervention | Discussions paginées des rendez-vous et demandes de réparation ; participants autorisés ; notifications ; conservation en lecture seule après clôture. | `appointments/messaging.py`, `appointments/models.py`, `templates/appointments/thread.html`, `repairs/services.py` |
| 2 / 1 — CRUD PC | Caractéristiques, composants techniques et validation ; propriétaire déterminé par le serveur. | `maintenance/models.py`, `maintenance/forms.py`, `maintenance/views.py` |
| 2 / 2 — Liste et historique | Liste filtrable, fiche et historique de maintenance ; consultation technique en lecture seule selon affectation. | `maintenance/permissions.py`, `templates/maintenance/`, `maintenance/views.py` |
| 2 / 3 — Recommandations | Moteur paramétrique, recalcul après changements et rendez-vous depuis un conseil. | `maintenance/services.py`, `maintenance/signals.py`, `templates/maintenance/recommendations.html` |
| 3 / 1 — Réservation | Choix PC, technicien, date et heure ; disponibilité ; contraintes MySQL contre les doubles réservations. | `appointments/forms.py`, `appointments/scheduling.py`, `appointments/services.py` |
| 3 / 2 — Modification / annulation | Client concerné et technicien assigné avant réparation ; libération du créneau ; nouvelle confirmation après modification. | `appointments/services.py`, `appointments/permissions.py` |
| 3 / 3 — Suivi technicien | Liste assignée, transitions de statut, diagnostic et clôture. | `appointments/views.py`, `templates/appointments/detail.html` |
| 4 / 1 — Déclaration de panne | Type, description et photo privée validée/réencodée. | `repairs/forms.py`, `repairs/uploads.py`, `repairs/views.py` |
| 4 / 2 — Choix du technicien (rôle adapté selon la demande) | Le client choisit un technicien actif, disponible et qualifié dans le formulaire. Qualification revérifiée à l’enregistrement ; changement possible avant le diagnostic. | `repairs/services.py`, `repairs/forms.py`, `repairs/permissions.py`, `static/js/modules.js` |
| 4 / 3 — Résolution | Diagnostic, solution, évolution du statut, historique du PC et facture créés à la résolution. | `repairs/services.py`, `repairs/models.py`, `templates/repairs/detail.html` |
| 5 / 1 — Recherche de composants | Catalogue filtrable par catégorie, prix et stock ; vitrine et annonces personnelles entre techniciens selon la demande spécifique du projet. | `inventory/views.py`, `inventory/marketplace_views.py`, `inventory/listing_forms.py` |
| 5 / 2 — Compatibilité | Contrôle des caractéristiques du PC et du composant avant utilisation. | `inventory/compatibility.py`, `inventory/services.py` |
| 5 / 3 — Stock automatique | Vérification, verrouillage MySQL, décrément, association à la prise en charge, retour et historique de mouvements. | `inventory/models.py`, `inventory/services.py` |
| Transverse / 1 — Dashboard | Indicateurs de comptes, PC, rendez-vous, pannes, stock, facturation ; graphiques ; note moyenne et nombre d’avis. | `backoffice/views.py`, `templates/backoffice/dashboard.html` |
| Transverse / 2 — Notifications | Centre personnel, événements métier, rappels J-1 et Web Push ; messages et nouveaux avis intégrés. Ajout demandé : envoi administrateur par public ou sélection, historique, lecture et retrait. | `notifications/models.py`, `notifications/services.py`, `notifications/push.py`, `notifications/campaigns.py`, `notifications/admin_views.py` |
| 6 / 1 — Feedback | Note 1–5 et commentaire après clôture ; un avis par prise en charge ; attribution au client et au technicien réels ; moyenne regroupant rendez-vous et réparations. | `feedback/models.py`, `feedback/services.py`, `feedback/views.py`, `templates/feedback/` |
| 7 / 1 — PDF | Rapport et facture privés pour client/admin, caractéristiques PC, pièces et coûts figés lors de la clôture. | `appointments/pdf.py`, `appointments/models.py`, `templates/appointments/documents.html` |
| 8 / 1 — FAQ interactive | Questions/réponses par catégorie ; 12 réponses initiales ; recherche textuelle ; accordéons accessibles ; gestion complète par admin. | `support/models.py`, `support/views.py`, `support/migrations/0002_initial_questions.py`, `templates/support/` |

La FAQ correspond aux tâches concrètes du module 8 : recherche textuelle et accordéons. Elle n’appelle aucun service d’IA externe. La vitrine reste réservée aux techniciens, selon la demande explicite du projet ; le stock utilisé pour les réparations demeure séparé des annonces de vente.

## Adresses des nouveaux écrans

| Adresse | Accès |
| --- | --- |
| `/inscription/` | Visiteur : création d’un compte client |
| `/connexion/` | Tous : e-mail ou identifiant et mot de passe |
| `/mon-profil/` | Compte connecté : identité et e-mail |
| `/mon-profil/mot-de-passe/` | Compte connecté : modification avec l’ancien mot de passe |
| `/rendez-vous/<id>/#discussion` | Client concerné, technicien assigné, admin |
| `/avis/` | Client : ses avis et réparations à évaluer ; technicien : avis reçus et moyenne |
| `/avis/appointment/<id>/evaluer/` | Client concerné après intervention terminée |
| `/avis/repair/<id>/evaluer/` | Client concerné après réparation résolue |
| `/aide/` | Compte connecté : FAQ, recherche et catégories |
| `/backoffice/avis/` | Admin : tous les avis, filtres et statistiques |
| `/backoffice/notifications/` | Admin : historique des diffusions, filtres, lectures et aperçu des alertes automatiques |
| `/backoffice/notifications/nouvelle/` | Admin : envoi aux clients, techniciens ou destinataires précis |
| `/backoffice/notifications/<id>/` | Admin : contenu envoyé, destinataires, lectures, état des push et retrait |
| `/backoffice/faq/` | Admin : liste, recherche, brouillons et publications |
| `/backoffice/faq/nouvelle/` | Admin : nouvelle question |

## Authentification

Les anciens identifiants et mots de passe continuent de fonctionner. Les anciens hachages PBKDF2 sont lus par Django puis améliorés lors d’une connexion réussie. Les e-mails ambigus d’anciens comptes sont refusés pour l’authentification ; l’administrateur peut les corriger. Les nouvelles inscriptions et modifications de comptes réservent l’e-mail dans `accounts_emailaddress` avec une contrainte unique MySQL.

Le site HTML utilise les sessions Django et la protection CSRF. Pour vérifier l’US JWT, les endpoints Django sont :

- `POST /api/auth/token/` : JSON `{ "email": "adresse-du-compte", "password": "mot-de-passe" }`, avec le cookie CSRF et l’en-tête `X-CSRFToken` obtenus en ouvrant `/connexion/`.
- `GET /api/auth/me/` : en-tête `Authorization: Bearer <access_token>` ; renvoie l’identité et le rôle actuels.

Le jeton est signé HS256 avec une clé dérivée du secret Django, vérifie l’émetteur et le destinataire, expire après 20 minutes et devient inutilisable après changement de mot de passe ou suspension du compte. Les interfaces HTML ne stockent pas de JWT dans `localStorage`. Le mot de passe MySQL n’est jamais un identifiant du site.

Références techniques : [hachage des mots de passe Django](https://docs.djangoproject.com/en/6.0/topics/auth/passwords/), [API PyJWT](https://pyjwt.readthedocs.io/en/latest/api.html).

## Installation de la mise à jour

Depuis le dossier contenant `manage.py`, arrêter le serveur puis exécuter :

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py run_techcare
```

Les migrations ajoutent les tables d’e-mails, messages de rendez-vous, avis et FAQ, ainsi que les douze réponses de base. Elles ne créent aucun rendez-vous, réparation, annonce ou avis fictif dans la base du projet. Les comptes, PC et documents existants sont conservés.

## Organisation et vérification

Le projet contient **10 applications Django** : `accounts`, `maintenance`, `appointments`, `repairs`, `inventory`, `notifications`, `feedback`, `support`, `backoffice`, `predictions`. Il comporte **28 modèles métier**, en plus des modèles Django d’authentification et d’administration. Le modèle `NotificationCampaign` conserve les diffusions manuelles de l’administration. `backoffice` réutilise les modèles des autres applications. Le module supplémentaire [Prédiction des pannes par ML](PREDICTION_PANNES_ML.md) utilise une Random Forest de démonstration sur des données simulées, avec possibilité de réentraînement CSV.

Les **275 tests serveur** ont réussi sur MySQL 8.4.13. Ils couvrent les règles métier, les droits entre rôles, l’isolation des données, les contraintes MySQL, les transitions, les uploads privés, les PDF, les jetons, les messages, les avis, la FAQ, la prédiction ML et les diffusions de notifications par l’administrateur. Les parcours Chrome ont aussi réussi avec **56 vérifications de mise en page** pour les modules du backlog, **40 pour le module ML**, **28 pour la réservation client et la gestion admin** et **28 pour la gestion et l’envoi des notifications**, à 320, 390, 768 et 1440 pixels, sans erreur JavaScript.

Pour lancer les tests serveur :

```powershell
.\.venv\Scripts\python.exe manage.py test
```

Cette commande exige que le compte MySQL de test puisse créer la base de test Django. Les vérifications de développement ont été exécutées sur une instance MySQL isolée pour préserver les données du projet.
