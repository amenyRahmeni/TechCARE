# TECHcare — Espace technicien

L’espace comprend également **Mes avis clients** (notes reçues et moyenne), **FAQ & aide** et **Mon profil**. Les discussions des rendez-vous sont accessibles depuis leur fiche ; voir [la couverture complète du backlog](COUVERTURE_BACKLOG.md).

L’espace technicien présente les tâches professionnelles du backlog. L’ajout et la gestion des PC sont réservés aux clients et à l’administration. Un technicien ouvre directement **Mes interventions**, y compris après un clic sur le logo ou une ouverture de `/`.

## Fonctions disponibles

| Fonction | Accès technicien |
| --- | --- |
| Mes interventions | Rendez-vous assignés uniquement ; confirmation, diagnostic, réparation et clôture |
| Modification / annulation d’un rendez-vous assigné | Avant réparation, selon le module 3 du backlog ; le PC de la demande reste fixé |
| Mes réparations | Demandes affectées : diagnostic, solution, statuts, pièces et discussion |
| Fiche d’un PC concerné | Configuration et historique en lecture seule, depuis une prise en charge assignée |
| Vitrine composants / Mes annonces | Recherche des pièces proposées et gestion de ses annonces, selon la demande de vitrine entre techniciens |
| Stock de l’atelier | Consultation, compatibilité et utilisation/retour de composants dans une prise en charge autorisée |
| Notifications | Alertes personnelles de suivi et de stock |

## Actions de l’espace client

Ces actions sont retirées des menus et refusées au technicien sur les URL directes :

- ajouter, modifier ou supprimer un PC ;
- gérer un historique personnel et actualiser ses recommandations personnelles ;
- réserver un nouveau rendez-vous en tant que client ;
- déclarer une nouvelle panne en tant que client ;
- consulter ou télécharger les rapports et factures PDF, réservés au client concerné et à l’administrateur dans le module 7.

Le technicien continue de rédiger le compte rendu et de clôturer ses interventions ; les documents sont alors disponibles dans l’espace du client.

La consultation du PC repose sur l’affectation de l’utilisateur au rendez-vous ou à la réparation. Posséder un ancien PC personnel ne donne pas de droits client au compte technicien. Après réaffectation de toutes ses prises en charge pour ce PC, l’ancien technicien n’en consulte plus la fiche.

## Emplacements

| Fichier | Rôle |
| --- | --- |
| `appointments/permissions.py` | Identification de l’espace technicien, autorisation des fonctions client et filtrage des rendez-vous/documents |
| `appointments/context_processors.py` | Navigation, page d’accueil et indicateurs de rôle communs aux interfaces |
| `maintenance/permissions.py` | PC accessibles selon l’affectation |
| `maintenance/views.py` | Redirection de l’accueil, lecture seule et refus des opérations client |
| `templates/base.html` | Menu technicien, logo et encart de suivi professionnel |
| `templates/maintenance/assigned_pc_detail.html` | Configuration et historique du PC sans actions de modification |
| `appointments/views.py`, `forms.py`, `services.py` | Blocage des nouvelles réservations et conservation de la modification des rendez-vous assignés |
| `repairs/permissions.py`, `views.py`, `services.py` | Filtrage des demandes affectées et blocage de la déclaration client |
| `templates/appointments/list.html`, `templates/repairs/list.html` | Titres, actions et états vides adaptés au technicien |
| `notifications/models.py`, `services.py`, `push.py` | Liens adaptés aux droits et absence de nouvelles alertes de recommandations personnelles pour un technicien |
| `appointments/tests_roles.py` | 11 tests de séparation des rôles et de consultation des PC assignés |

Validation : **166 tests serveur réussis**, avec **44 contrôles d’affichage** sur mobile et ordinateur. Le parcours navigateur vérifie le refus des URL/actions client, le diagnostic et la clôture par le technicien, puis la disponibilité du PDF pour le client. Les essais utilisent une base MySQL isolée.
