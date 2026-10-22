# TECHcare — PC, rendez-vous, interventions et PDF

Application réalisée en **HTML, CSS, JavaScript natif et Django**, avec **MySQL**. Les modules 2 (PC & Maintenance), 3 (Rendez-vous & Interventions) et 7 (Rapports & Factures PDF) sont disponibles. Le serveur MySQL peut être installé sur votre PC ou hébergé en ligne ; ses coordonnées se configurent dans `.env`. Aucun framework frontend ni serveur Node n’est nécessaire.

## Démarrer sous Windows

Pour récupérer le projet depuis GitHub :

```powershell
git clone https://github.com/amenyRahmeni/TechCARE.git
cd TechCARE
```

### 1. Installer MySQL

Installer **[MySQL Community Server 8.4 ou supérieur](https://dev.mysql.com/downloads/mysql/8.4.html)**. Cette version convient au Django 6.1 installé dans le projet. **[MySQL Workbench](https://dev.mysql.com/downloads/workbench/)** est facultatif mais pratique pour exécuter le SQL et consulter les tables. XAMPP n’est pas nécessaire.

Dans MySQL Workbench, connecté avec un compte administrateur, ouvrir [sql/create_database.sql](sql/create_database.sql), remplacer `CHANGE_ME` par votre mot de passe pour le compte de l’application et exécuter le script. Il crée la base `atelier_pc` et l’utilisateur MySQL `atelier_pc`. Ce compte MySQL est distinct du compte client `demo` utilisé sur le site.

Si vous utilisez MySQL hébergé, créer la base et le compte depuis le tableau de bord du fournisseur et utiliser les paramètres fournis.

### 2. Configurer le projet

Depuis ce dossier, dans PowerShell, avec Python installé :

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Copier `.env.example` vers `.env` si ce fichier n’existe pas encore, puis renseigner les coordonnées de votre serveur MySQL. Les identifiants privés et les données locales ne sont pas inclus dans le dépôt.

```powershell
Copy-Item .env.example .env
```

Paramètres à adapter dans `.env` :

```dotenv
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_DATABASE=atelier_pc
MYSQL_USER=atelier_pc
MYSQL_PASSWORD=le_meme_mot_de_passe_que_dans_le_script_SQL
```

Pour un mot de passe contenant `#` ou des espaces, entourer sa valeur de guillemets dans `.env`. Ce fichier est ignoré par Git. Les variables d’environnement du système prennent priorité sur `.env`. Pour une base hébergée, remplacer l’hôte, le port, le nom et le compte par ceux du fournisseur ; `MYSQL_SSL_CA` permet d’indiquer son certificat CA pour vérifier la connexion TLS.

Pour un serveur installé sur votre PC, cet assistant peut créer ou réparer la base et son compte directement avec les paramètres de `.env` :

```powershell
.\.venv\Scripts\python.exe scripts\setup_mysql.py
```

Il demande le mot de passe **root** défini pendant l’installation de MySQL, sans l’enregistrer. Il synchronise le mot de passe de `atelier_pc` avec `.env`, accorde les droits sur la base du projet et vérifie la connexion. Il conserve les données existantes. Pour vérifier uniquement la connexion : ajouter `--check`.

### 3. Créer les tables et récupérer les données

Une fois le serveur MySQL démarré et `.env` renseigné :

```powershell
.\.venv\Scripts\python.exe manage.py migrate
```

**Pour conserver les comptes et les PC de l’ancienne base SQLite**, effectuer ensuite le transfert :

```powershell
.\.venv\Scripts\python.exe scripts\migrate_sqlite_to_mysql.py
```

Le script lit `db.sqlite3` en lecture seule, sauvegarde les données dans `backups/`, puis transfère les utilisateurs, groupes, PC, historiques, règles et recommandations vers MySQL. Les mots de passe existants sont conservés. Il refuse le transfert si MySQL contient déjà des utilisateurs ou des PC, pour éviter tout écrasement. Ne pas partager les sauvegardes : elles contiennent les données des comptes.

**Pour démarrer avec une nouvelle démonstration**, utiliser cette commande à la place du transfert :

```powershell
.\.venv\Scripts\python.exe manage.py seed_demo --with-admin
```

### 4. Lancer le site

Créer les deux profils techniciens de démonstration, si nécessaire :

```powershell
.\.venv\Scripts\python.exe manage.py seed_technicians
```

Cette commande s’exécute après le transfert des anciennes données. Elle conserve les comptes et les mots de passe existants et ne crée aucun rendez-vous ni facture fictive dans votre base.

```powershell
.\.venv\Scripts\python.exe manage.py runserver
```

Ouvrir **http://127.0.0.1:8000/**. Il n’est pas nécessaire d’activer l’environnement virtuel.

L’application utilise désormais le backend `django.db.backends.mysql`, le pilote `mysqlclient`, le jeu de caractères `utf8mb4` et des tables InnoDB. Aucun retour automatique à SQLite n’est effectué. L’ancien fichier `db.sqlite3` est conservé uniquement comme source de transfert ou sauvegarde.

### Comptes de démonstration locaux

| Accès | Identifiant | Mot de passe initial |
| --- | --- | --- |
| Espace client | `demo` | `AtelierPC2026!` |
| Administration `/admin/` | `admin_demo` | `AdminAtelier2026!` |
| Technicien matériel | `tech_amine` | `Technicien2026!` |
| Technicien logiciel | `tech_sarra` | `Technicien2026!` |

`seed_demo` ajoute trois PC, quatre comptes rendus et des recommandations. La commande peut être relancée : elle conserve les données et les mots de passe déjà existants. `--with-admin` est facultatif. Ces comptes sont réservés à la démonstration locale.

Pour un compte administrateur personnel :

```powershell
.\.venv\Scripts\python.exe manage.py createsuperuser
```

## Périmètre livré

Les demandes des **modules 2, 3 et 7** du backlog sont reprises avec la stack demandée : les références FXML, repositories Java et Spring du PDF sont remplacées par des templates, des vues, des formulaires et l’ORM Django.

- Ajouter, consulter, modifier et supprimer ses PC, avec confirmation avant suppression.
- Enregistrer nom, marque, modèle, type, OS, processeur, RAM, stockage, numéro de série, date d’achat et notes.
- Rechercher, filtrer par type et état, trier et parcourir la liste paginée.
- Consulter la fiche et l’historique de chaque PC, ainsi qu’un historique global filtrable.
- Calculer et enregistrer des recommandations à partir de règles paramétrables.
- Utiliser les interfaces sur ordinateur ou mobile, avec navigation clavier et formulaires validés côté serveur.
- Réserver, modifier ou annuler un rendez-vous avec un PC, un technicien et un créneau disponible.
- Suivre les interventions assignées côté technicien et mettre à jour leurs statuts.
- Renseigner diagnostic, solution, pièces utilisées et main-d’œuvre.
- Télécharger les rapports et factures PDF après la clôture d’une intervention.

La connexion utilise les sessions Django pour isoler les données : chaque client accède uniquement à ses PC, historiques et recommandations. La création de comptes relève du module 1 ; elle reste ici dans l’administration Django.

Les boutons « Prendre rendez-vous » des recommandations ouvrent le formulaire réel avec le PC et le motif préremplis. Les liens « Rendez-vous » et « Rapports & factures » du menu sont actifs.

## Rendez-vous et interventions

- **Client** : réserver depuis `/rendez-vous/nouveau/`, consulter son suivi et modifier/annuler tant que le rendez-vous n’est pas en réparation ou clôturé.
- **Technicien** : se connecter avec son compte, ouvrir « Mes interventions », confirmer les rendez-vous assignés puis faire avancer la prise en charge. Les clients et autres techniciens ne peuvent pas modifier ses comptes rendus.
- **Administrateur** : consulter et gérer tous les rendez-vous depuis les mêmes pages. Dans `/admin/`, créer un utilisateur puis un profil **Technicien** pour l’ajouter à l’équipe. Le champ « accepte des rendez-vous » désactive les nouvelles réservations sans supprimer son historique.

Les créneaux durent **une heure**, du **lundi au samedi, 09:00–18:00**, en heure de Tunis. Seuls les créneaux futurs des douze prochains mois sont réservables. La disponibilité est affichée dans le formulaire et revérifiée côté serveur. Des verrous MySQL et deux index uniques empêchent les doubles réservations du technicien et du PC, même avec des requêtes simultanées.

Parcours des statuts :

```text
En attente → Confirmé → En diagnostic → En réparation → Terminé
                                     └───────────────→ Terminé
```

L’annulation reste possible avant la réparation. Un changement de créneau remet le rendez-vous en attente de confirmation. Un rendez-vous terminé ou annulé reste en lecture seule. Un PC référencé par un rendez-vous est conservé avec son historique et ne peut plus être supprimé depuis l’espace client.

## Rapports et factures PDF

Le technicien renseigne le diagnostic, les travaux réalisés, les pièces (jusqu’à 20 lignes) et la main-d’œuvre, puis termine l’intervention. Les montants sont calculés côté serveur avec `Decimal`, en **TND avec trois décimales**. La saisie des pièces ne gère pas le stock du module 5.

À la clôture, dans une même transaction :

1. le statut devient « Terminé » ;
2. un historique est ajouté au PC et ses recommandations sont recalculées ;
3. une facture avec numéro unique et copie des données à la clôture est enregistrée ;
4. les deux téléchargements PDF deviennent disponibles.

Les documents incluent la configuration du PC, les pièces utilisées et les coûts. Le rapport inclut aussi le diagnostic et les travaux réalisés. La copie conservée à la clôture reste identique même si le PC ou le nom du client sont modifiés ensuite.

Les téléchargements sont accessibles au **client concerné et aux administrateurs**, dans `/documents/`, dans le suivi du rendez-vous et dans l’historique du PC. Les URL PDF vérifient les droits ; les documents ne sont pas exposés dans un dossier public. ReportLab construit les PDF avec tableaux, pagination et polices intégrées.

Pour tester le parcours : réserver avec `demo`, se déconnecter, confirmer et traiter avec `tech_amine` ou `tech_sarra` selon le choix effectué, enregistrer le compte rendu, puis terminer l’intervention. Revenir dans le compte `demo` et ouvrir « Rapports & factures ».

## Historique et règles de maintenance

Dans **http://127.0.0.1:8000/admin/**, un administrateur peut :

- créer un historique avec le PC, la date, le type d’entretien, le compte rendu et le technicien ;
- modifier les titres, conseils, priorités et seuils des règles ;
- activer ou désactiver une règle ;
- créer les comptes clients.

L’espace client affiche l’historique en lecture seule. La clôture des interventions alimente automatiquement les mêmes objets `MaintenanceRecord`. Les historiques liés à une intervention clôturée sont conservés en lecture seule dans l’administration.

Quatre règles initiales sont installées par migration :

| Critère | Valeur initiale | Priorité |
| --- | --- | --- |
| Délai depuis le dernier entretien | ≥ 180 jours | Prioritaire |
| RAM installée | < 8 Go | À prévoir |
| Disque mécanique | HDD | À prévoir |
| Capacité du stockage | < 256 Go | Conseil |

Ces valeurs sont des paramètres de démonstration, pas un diagnostic. La règle de stockage porte sur la capacité déclarée, pas sur l’espace libre. Sans historique, la règle d’entretien utilise la date d’achat, ou la date d’enregistrement si elle est inconnue.

Le calcul se met à jour après la création ou modification d’un PC, d’un historique ou d’une règle. Le bouton **Actualiser l’analyse** recalcule les recommandations du client connecté. Pour tenir compte du temps qui passe sans modifier un PC, cette commande peut aussi être planifiée quotidiennement :

```powershell
.\.venv\Scripts\python.exe manage.py refresh_recommendations
```

## Backoffice administrateur

Ouvrir **http://127.0.0.1:8000/backoffice/** et se connecter avec `admin_demo` / `AdminAtelier2026!` si les comptes de démonstration ont été créés. Une connexion avec un compte administrateur ouvre directement le tableau de bord.

- **Tableau de bord** : clients, parc PC, prises en charge, montants facturés, graphique des six derniers mois, rendez-vous à venir et PC prioritaires. Les statistiques utilisent les données MySQL ; les montants facturés ne sont pas un suivi des paiements.
- **Comptes & clients** : recherche, filtres, pagination, création, modification, activation et suspension. Les mots de passe sont hachés ; laisser les champs vides lors d’une modification conserve le mot de passe actuel.
- **Techniciens** : spécialité, disponibilité à la réservation et nombre d’interventions. Créer un compte avec le rôle Technicien ajoute son profil.
- **Parc informatique** : tous les PC, ajout pour un client, modification, configuration, historique et recommandations. Le propriétaire d’un PC existant est conservé. Une fiche liée à un rendez-vous ne peut pas être supprimée.
- **Rendez-vous & suivi** : réservation pour le propriétaire du PC, modification du créneau et du technicien, transitions de statut, compte rendu, pièces et clôture.
- **Rapports & factures** : recherche et téléchargement des documents PDF de tous les clients.
- **Règles de maintenance** : création, modification, activation et désactivation, avec recalcul des recommandations.

L’accès est réservé aux utilisateurs actifs avec `is_staff=True`. Seul un superadministrateur peut créer ou modifier les comptes administrateurs. Il est impossible de suspendre son propre compte ou de retirer son propre rôle. Un technicien ayant un historique conserve son profil ; sa disponibilité ou son compte peuvent être désactivés. La suspension conserve les données et les rendez-vous existants. Les actions sur les comptes, PC et règles sont enregistrées dans le journal d’administration Django. Les actions sensibles utilisent POST et la protection CSRF.

L’administration Django standard reste disponible à `/admin/` pour les opérations techniques autorisées.

## Thème des interfaces

Les espaces client, technicien et administrateur partagent le thème sombre TECHcare. La palette se règle dans `static/css/theme.css` : fond `#0B1320`, surfaces `#0D1B2A`, cartes `#1A2332`, bordures et éléments surélevés `#243247`, actions `#F77F00` / `#FF9F1C`, titres `#FFFFFF`, texte `#D6DCE5` et informations secondaires `#9AA8B8`.

Les formulaires, menus mobiles, tableaux, confirmations et états des interventions utilisent ces mêmes variables. Les boutons principaux orange portent un texte bleu nuit pour garder un contraste lisible. L’administration Django standard dispose du même thème dans `static/css/admin-theme.css`.

## Structure

```text
config/                  Configuration Django, URLs et WSGI
config/sqlite_export_settings.py  Lecture seule de l’ancienne base pour le transfert
sql/create_database.sql  Création de la base et de l’utilisateur MySQL
scripts/migrate_sqlite_to_mysql.py  Transfert des anciennes données
scripts/setup_mysql.py   Création/réparation du compte MySQL local
maintenance/models.py    PC, MaintenanceRecord, MaintenanceRule, Recommendation
maintenance/forms.py     Formulaire PC et validations
maintenance/services.py  Moteur de règles paramétriques
maintenance/views.py     Pages et contrôles de propriété
maintenance/admin.py     Gestion des comptes rendus et règles
maintenance/migrations/  Schéma et règles initiales
maintenance/tests.py     Tests fonctionnels et de sécurité
appointments/models.py  Techniciens, rendez-vous, réservations, interventions, pièces, factures
appointments/services.py  Disponibilité, transitions, clôture atomique et historique
appointments/pdf.py     Génération des rapports et factures PDF
appointments/tests.py   Parcours, permissions, concurrence MySQL et contenu PDF
backoffice/             Tableau de bord, gestion des comptes, PC et règles ; accès administrateur
templates/backoffice/   Interfaces du backoffice
static/css/backoffice.css  Style responsive du backoffice
static/css/theme.css     Palette sombre et styles communs des interfaces
static/css/admin-theme.css  Thème de l’administration Django standard
static/js/backoffice.js  Adaptation du formulaire selon le rôle
templates/               Pages HTML et composants Django
static/css/app.css       Style et mise en page responsive
static/js/app.js         Menu mobile, filtres, fenêtres et confort des formulaires
static/css/workflow.css  Interfaces rendez-vous, interventions et documents
```

## Vérifications

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe manage.py check --database default
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py test
```

Le serveur MySQL doit être démarré pour les tests. Ils créent une base séparée `test_atelier_pc`, puis la suppriment. Avec le compte local proposé, un administrateur doit d’abord lui accorder les droits sur cette base de test :

```sql
GRANT ALL PRIVILEGES ON test_atelier_pc.* TO 'atelier_pc'@'localhost';
```

Les tests couvrent notamment le CRUD, l’isolation entre clients, la protection CSRF, les dates invalides, les règles, la suppression en cascade et les filtres. Ils vérifient aussi l’unicité MySQL des numéros de série, les réservations concurrentes, les transitions autorisées, les coûts exacts, la clôture sans doublon et le contenu des PDF, y compris les rapports sur plusieurs pages. Le backoffice est testé pour les permissions, les rôles, les mots de passe, la suspension des comptes, la gestion des PC et règles, les statistiques et le parcours administrateur jusqu’aux PDF. Les numéros de série sont sensibles à la casse ; les valeurs vides sont enregistrées comme `NULL` pour conserver cette possibilité avec l’index unique MySQL.

### En cas d’erreur de connexion

- **2003 / connexion refusée** : vérifier que MySQL est démarré et que l’hôte/port de `.env` sont corrects.
- **1045 / accès refusé** : vérifier `.env`, puis lancer `scripts/setup_mysql.py` pour synchroniser le compte avec ce fichier. `CREATE USER IF NOT EXISTS` seul ne change pas le mot de passe d’un compte déjà existant.
- **1049 / base inconnue** : créer la base avant de lancer `migrate`.
- **Version non prise en charge** : le Django 6.1 de ce projet demande MySQL 8.4+. Les anciennes distributions XAMPP avec MariaDB ne remplacent pas cette installation.

La configuration par défaut est destinée au développement local. Pour un hébergement ultérieur, définir une clé `DJANGO_SECRET_KEY` privée, `DJANGO_DEBUG=0` et `DJANGO_ALLOWED_HOSTS`, configurer HTTPS et collecter les fichiers statiques. Aucun déploiement n’est réalisé dans cette étape.
