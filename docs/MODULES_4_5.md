# TECHcare — Modules 4 et 5

Implémentation en HTML, CSS, JavaScript, Django et MySQL, selon le backlog pages 3–4 et le cahier des charges pages 5–9. Les nouveaux modules partagent les comptes, les PC, l’historique, les notifications et les documents déjà présents.

## Module 4 — Assistance & Réparation

### Parcours client

- Ouvrir **Assistance & réparation**, puis **Déclarer une panne**.
- Choisir un PC du compte et l’un des douze types de problème.
- Choisir un technicien actif, disponible et qualifié dans la liste proposée selon le problème.
- Décrire les symptômes et, si nécessaire, ajouter des précisions techniques et une photo.
- Suivre le statut, les événements, le diagnostic, la solution, les pièces et les coûts.
- Contacter le technicien dans la discussion de la demande après son affectation.
- Annuler avant le démarrage de la réparation ; consulter les documents après résolution.

Le client choisit désormais le technicien lors de la déclaration. La liste est filtrée par type de panne ; le serveur vérifie à nouveau l’activation, la disponibilité et les compétences. La demande passe directement à Affectée. Le client peut modifier son choix avant le début du diagnostic. La demande de réparation est indépendante d’un créneau de rendez-vous.

### Parcours technicien et droits d’accès

Le technicien retrouve les demandes qui lui sont adressées dans Mes réparations, avec recherche et filtre de statut. La rubrique a été retirée du backoffice ; les vues, actions et photos privées de réparation sont inaccessibles aux administrateurs, même via les anciennes URL.

Les comptes techniciens disposent de compétences **matériel**, **logiciel/système** et **réseau**. Elles se règlent dans le formulaire de compte du backoffice. Seuls les techniciens actifs, disponibles et possédant la compétence correspondant à la panne sont proposés. Les profils existants sont repris selon leur spécialité ; les profils de maintenance générale disposent par défaut des trois domaines.

Après le choix du client, seul le technicien concerné modifie le diagnostic, la solution, la main-d’œuvre et les statuts. Le client retrouve les événements et peut échanger des messages dans le même suivi.

```text
Envoyée → Affectée → En diagnostic → En réparation → Résolue
                          ↕                ↕
                         En attente de pièce
```

La résolution est aussi autorisée directement depuis le diagnostic. Le statut d’attente nécessite un motif ou le nom de la pièce attendue. Une annulation clôture la demande et restitue les composants déjà sortis, avec des mouvements de retour.

Pour résoudre : enregistrer un diagnostic et une solution, puis utiliser **Résoudre & clôturer**. Une transaction enregistre l’historique du PC, une facture et les notifications de fin/documents. Les données de la facture sont figées dans `Invoice.snapshot`. Une demande résolue ou annulée reste en lecture seule ; la discussion est également clôturée.

### Photos privées

- JPEG, PNG ou WebP, au maximum 5 Mo et 20 mégapixels.
- Décodage puis réencodage JPEG, redimensionnement et suppression des métadonnées ; nom de fichier aléatoire.
- Fichiers enregistrés sous `MEDIA_ROOT`, sans route publique `/media/`.
- Consultation par une vue authentifiée : client propriétaire ou technicien actuellement choisi.
- Réponses sans cache ; une réaffectation retire l’accès à l’ancien technicien.

La discussion intégrée est limitée aux demandes de réparation. Elle ne remplace pas un module général de messagerie couvrant tous les rendez-vous.

## Module 5 — Composants informatiques & Stock

### Catalogue et gestion

La **Vitrine composants** est réservée aux techniciens : chacun publie ses propres pièces et retrouve celles proposées par ses confrères, avec nom du vendeur, ville, prix et coordonnées. Voir [le guide de la vitrine](VITRINE_TECHNICIENS.md).

Le catalogue du **stock de l’atelier** est réservé aux techniciens et administrateurs : recherche par nom/référence/description, filtres de catégorie, marque, prix minimum/maximum et disponibilité. Une fiche présente le prix en TND, le stock, la description et les conditions de compatibilité. Les clients ordinaires ne disposent pas d’un accès aux pages de composants.

Douze catégories sont installées par migration : RAM, SSD, HDD, batterie, chargeur, écran, clavier, ventilateur, carte mère, carte graphique, alimentation et accessoires. Elles sont modifiables et de nouvelles catégories peuvent être créées dans le backoffice.

L’administrateur crée et modifie les références, leurs prix et leurs contraintes. Le stock initial est enregistré comme un mouvement. Les variations ultérieures nécessitent une quantité et un motif. Une référence peut être archivée en désactivant **visible au catalogue** ; son historique est conservé. Aucune quantité fictive n’est ajoutée à votre stock lors de la migration.

### Compatibilité

Les contraintes renseignées pour le composant sont comparées au PC sélectionné :

- type portable/bureau ;
- marque et liste de modèles exacts ;
- génération de RAM et format DIMM/SO-DIMM ;
- interface SATA, M.2 NVMe ou M.2 SATA ;
- socket processeur.

Les quatre caractéristiques techniques supplémentaires se renseignent dans la fiche PC. Si une contrainte du composant exige une information absente du PC, l’utilisation est bloquée avec un message explicatif. Les valeurs sont déclaratives ; le technicien vérifie aussi les dimensions, connecteurs et spécifications du fabricant.

### Utilisation et retours

Depuis une réparation ou une intervention de rendez-vous, le technicien assigné ou l’administrateur sélectionne le composant et la quantité. Le serveur revérifie les droits, l’étape, la compatibilité et le stock dans une transaction MySQL.

- Le stock diminue lors de la **validation de l’utilisation**.
- Un enregistrement conserve quantité, prix unitaire et désignation au moment de la sortie.
- Un mouvement trace l’auteur, la date, la variation et le stock après l’action.
- Un identifiant unique de validation évite une double sortie lors d’un renvoi du même formulaire.
- Les verrous de transaction empêchent deux intervenants de consommer la même dernière unité.
- Avant clôture, **Retourner au stock** restitue les pièces avec un motif ; répéter un retour ne recrédite pas le stock.
- L’annulation d’une prise en charge restitue les sorties actives.
- Après clôture, les consommations restent figées et les documents conservent leurs prix initiaux.

Pour les rendez-vous existants, les composants du stock sont séparés des lignes manuelles de prestation. Enregistrer le compte rendu ne supprime pas les sorties du stock ; les deux types de lignes entrent dans le total et les PDF.

Le **journal des mouvements** est accessible aux techniciens et administrateurs. Seul l’administrateur effectue les entrées et corrections manuelles de stock. Les alertes de stock faible sont envoyées aux administrateurs et au technicien qui vient d’utiliser le composant. Une réparation mise en attente de pièce avertit également les participants concernés.

## Adresses

| Usage | Adresse |
| --- | --- |
| Demandes visibles selon le rôle | `/reparations/` |
| Déclarer une panne | `/reparations/nouvelle/` |
| Suivi | `/reparations/<id>/` |
| Vitrine entre techniciens | `/composants/` |
| Mes annonces / dépôt | `/composants/mes-annonces/`, `/composants/deposer/` |
| Catalogue du stock de l’atelier | `/composants/stock/` |
| Fiche et compatibilité du stock | `/composants/stock/<id>/` |
| Journal technicien | `/composants/mouvements/` |
| Affectation et gestion atelier | `/backoffice/reparations/` |
| Gestion des composants | `/backoffice/composants/` |
| Ajouter une référence | `/backoffice/composants/nouveau/` |
| Catégories | `/backoffice/categories/` |
| Journal administrateur | `/backoffice/stock/` |

## Où se trouve le code ?

| Fichier | Rôle |
| --- | --- |
| `repairs/models.py` | `RepairRequest`, `RepairEvent`, `RepairMessage` |
| `repairs/forms.py` | Déclaration, affectation qualifiée et compte rendu |
| `repairs/uploads.py` | Contrôle et réencodage des photos |
| `repairs/permissions.py` | Visibilité et droits de gestion |
| `repairs/services.py` | Création, affectation, transitions, messages, historique et facture |
| `repairs/views.py`, `urls.py` | Pages et actions |
| `repairs/admin.py`, `apps.py`, `migrations/` | Administration technique, application et schéma |
| `repairs/tests.py` | 19 tests serveur du module et de ses intégrations, dont les discussions paginées |
| `inventory/models.py` | `Category`, `SparePart`, `ComponentUsage`, `StockMovement` et `ComponentListing` (vitrine personnelle) |
| `inventory/compatibility.py` | Comparaison des contraintes déclarées avec le PC |
| `inventory/services.py` | Entrées, utilisations, retours, transactions et alertes |
| `inventory/forms.py`, `views.py`, `urls.py` | Catalogue, fiches et gestion du stock |
| `inventory/admin.py`, `apps.py`, `migrations/` | Administration technique, schéma et catégories initiales |
| `inventory/tests.py` | 15 tests dont concurrence, coûts figés et absence de double décrément |
| `templates/repairs/` | Liste, déclaration, suivi et confirmation d’annulation |
| `templates/inventory/` | Catalogue, fiche, formulaires, catégories, journal et composants réutilisables |
| `static/css/modules.css` | Styles bleu nuit/orange et responsive |
| `static/js/modules.js` | Aperçu de la photo et vérification de sa taille côté navigateur |
| `appointments/models.py`, `services.py`, `pdf.py`, `permissions.py` | Factures unifiées et utilisation du stock dans les rendez-vous |
| `maintenance/models.py`, `forms.py` | Informations techniques nécessaires à la compatibilité |
| `notifications/models.py`, `services.py` | Alertes liées aux demandes et aux composants |

Tables ajoutées : `repairs_repairrequest`, `repairs_repairevent`, `repairs_repairmessage`, `inventory_category`, `inventory_sparepart`, `inventory_componentusage`, `inventory_stockmovement`.

Le projet comprend désormais **6 applications Django** et **21 modèles personnalisés**, dont `ComponentListing` pour les annonces, auxquels s’ajoutent les modèles fournis par Django, notamment `User`.

## Mise en route et démonstration

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py run_techcare
```

Pour présenter le parcours :

1. Administrateur : créer un composant et son stock initial ; renseigner ses contraintes.
2. Client : compléter les caractéristiques techniques du PC, puis déclarer une panne avec photo.
3. Administrateur : filtrer les demandes envoyées et affecter un technicien qualifié.
4. Technicien : ouvrir le diagnostic, enregistrer un message et utiliser une pièce compatible.
5. Montrer le stock décrémenté et le mouvement ; effectuer un retour puis une nouvelle utilisation.
6. Mettre la demande en attente de pièce et montrer l’alerte de l’administrateur.
7. Reprendre la réparation, enregistrer la solution et résoudre.
8. Client : consulter historique, notifications et PDF ; administrateur : consulter facturation et journal du stock.

Validation serveur : **166 tests réussis** sur MySQL isolé, dont les 101 tests existants, 34 tests des modules 4 et 5, 20 tests de la vitrine et 11 tests de séparation des rôles. Le transfert de l’ancienne SQLite est également vérifié sans modifier le fichier source ; l’export tient compte des colonnes absentes de l’ancien schéma. L’[espace technicien](ESPACE_TECHNICIEN.md) est réservé aux prises en charge assignées, avec PC en lecture seule.

Le parcours initial des modules 4 et 5 a été validé avec photo, affectation, utilisation/retour de stock, attente, message, résolution et PDF. La dernière évolution réserve les pages de composants aux techniciens : la vitrine a passé **44 contrôles d’affichage**, ainsi que les essais de publication, modification, contact vendeur et blocage des accès clients. Voir [le guide de la vitrine](VITRINE_TECHNICIENS.md). Les composants et photos de démonstration restent dans l’environnement de test isolé.
