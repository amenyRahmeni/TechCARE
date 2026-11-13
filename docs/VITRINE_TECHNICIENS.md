# TECHcare — Vitrine de composants entre techniciens

La rubrique **Vitrine composants** permet aux techniciens de proposer leurs propres pièces à la vente et de retrouver les composants disponibles chez leurs confrères.

## Parcours

1. Se connecter avec un compte technicien, par exemple `tech_amine` ou `tech_sarra`.
2. Ouvrir **Vitrine composants**, puis **Déposer une annonce**.
3. Renseigner le titre, la catégorie, la marque/référence, l’état, le prix en TND, la quantité et la description. Une photo et des précisions de compatibilité peuvent être ajoutées.
4. Indiquer la ville ou le lieu de remise, ainsi qu’un téléphone ou un e-mail de contact.
5. Publier immédiatement ou enregistrer un brouillon.

Chaque carte affiche **« Proposé par »**, le nom du technicien et sa ville. La fiche présente ses coordonnées, les boutons d’appel/e-mail et ses autres annonces. Le vendeur gère les changements depuis **Mes annonces** : modification, publication, passage à **Vendu** ou retrait.

Les techniciens recherchent une pièce par texte, ville, catégorie, vendeur et intervalle de prix. Le téléphone et l’e-mail publiés sont ceux fournis expressément dans l’annonce ; l’e-mail privé du compte n’est pas ajouté automatiquement.

## Accès et données

- Les clients ordinaires ne voient pas les liens de composants et ne peuvent ouvrir les pages, formulaires ou photos, même par URL directe.
- Un technicien consulte les annonces disponibles des autres techniciens ; il modifie uniquement les siennes.
- Les brouillons, annonces vendues et annonces retirées restent accessibles au vendeur dans son espace.
- Les annonces d’un compte désactivé sont masquées aux autres techniciens.
- La disponibilité du technicien pour de nouveaux rendez-vous n’affecte pas sa vitrine.
- L’administrateur conserve un accès de supervision. Déposer une nouvelle annonce requiert un profil technicien.
- Les photos sont réencodées, sans métadonnées, et servies par une vue authentifiée. Aucun dossier public ne les expose.
- Le renvoi d’un même formulaire de création ne publie pas deux fois l’annonce.

Les coordonnées sont annoncées dans le formulaire comme visibles aux autres techniciens. Le contact entre acheteur et vendeur permet de confirmer la disponibilité et d’organiser la remise.

Le **stock de l’atelier** conserve les références, utilisations et mouvements associés aux interventions. Chaque annonce personnelle possède sa quantité et son vendeur dans `ComponentListing`. Publier ou marquer une annonce vendue conserve les données du stock de l’atelier.

## Adresses

| Page | URL |
| --- | --- |
| Vitrine des techniciens | `/composants/` |
| Mes annonces | `/composants/mes-annonces/` |
| Déposer une annonce | `/composants/deposer/` |
| Fiche d’une annonce | `/composants/annonces/<id>/` |
| Modifier son annonce | `/composants/annonces/<id>/modifier/` |
| Stock réservé à l’atelier | `/composants/stock/` |
| Fiche d’une référence du stock | `/composants/stock/<id>/` |

## Code

| Fichier | Rôle |
| --- | --- |
| `inventory/models.py` | `ComponentListing` : vendeur, composant proposé, prix, quantité, coordonnées, photo et statut |
| `inventory/migrations/0004_componentlisting.py` | Table `inventory_componentlisting` et contraintes |
| `inventory/permissions.py` | Accès technicien et visibilité des annonces |
| `inventory/listing_forms.py` | Saisie, téléphone/e-mail et photo |
| `inventory/listing_services.py` | Création, modification, déduplication et changements de statut |
| `inventory/marketplace_views.py` | Vitrine, filtres, espace vendeur et photo privée |
| `inventory/urls.py` | Routes de la vitrine et du stock |
| `inventory/tests_showcase.py` | 20 tests de publication, propriété, photos, filtres et permissions |
| `templates/inventory/showcase.html` | Vitrine et liste personnelle |
| `templates/inventory/listing_card.html` | Carte avec nom du vendeur et ville |
| `templates/inventory/listing_detail.html` | Fiche du composant et contact du technicien |
| `templates/inventory/listing_form.html` | Dépôt et modification d’annonce |
| `static/css/showcase.css` | Thème bleu nuit/orange, cartes vendeur et responsive |

La migration ajoute une table sans attribuer les références du stock à un vendeur. À la demande de remplir la vitrine pour la présentation, la commande suivante ajoute **12 annonces de démonstration**, réparties entre les comptes `tech_amine` et `tech_sarra` :

```powershell
.\.venv\Scripts\python.exe manage.py seed_showcase
```

RAM, SSD, disque dur, carte graphique, alimentation, écran, clavier, ventilateur, chargeur et hub USB-C sont proposés avec prix indicatifs en TND, quantités, ville, vendeur et précisions de compatibilité. La référence porte la mention **DÉMO** et chaque description précise que ces données sont fictives. Les contacts utilisent exclusivement les e-mails de démonstration `@example.test` ; aucun numéro de téléphone réel n’est inventé.

Les deux comptes de démonstration doivent déjà exister, être actifs et conserver leurs e-mails de démonstration ; la commande ne crée pas de compte et ne modifie pas de mot de passe. Relancer la commande ne crée pas de doublons et conserve les annonces déjà modifiées, vendues ou retirées. Le stock de l’atelier reste indépendant.

## Vérification

Les tests dédiés à la vitrine couvrent la publication, les photos, les filtres, les droits et l’espace vendeur. `inventory/test_seed_showcase.py` vérifie aussi l’ajout des 12 annonces, l’absence de doublons, la conservation des modifications du vendeur et le refus d’attribuer ces exemples à une identité réelle. Les tests utilisent une base MySQL isolée.

Le parcours navigateur de la vitrine valide la publication avec photo, la modification par le propriétaire, l’affichage chez un autre technicien, le contact vendeur, le passage à vendu et le refus des accès clients ou modifications étrangères. **44 contrôles d’affichage** ont été validés entre 320 et 1440 pixels, sans erreur JavaScript. Les fixtures de ces tests restent isolées ; les annonces ajoutées pour remplir la vitrine du projet sont celles décrites plus haut et clairement signalées comme démonstration.
