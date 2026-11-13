from django.db import migrations


QUESTIONS = [
    ("account", "Comment créer mon compte TECHcare ?", "Depuis la page de connexion, choisissez Créer mon compte client. Renseignez votre prénom, nom, e-mail, identifiant et mot de passe. Le compte est actif dès son inscription. Les comptes techniciens sont créés par l’administrateur avec leurs compétences."),
    ("account", "Avec quoi puis-je me connecter ?", "Utilisez votre adresse e-mail ou votre identifiant, puis votre mot de passe TECHcare. Le mot de passe du site est distinct du mot de passe MySQL. Un compte suspendu doit être réactivé par l’administrateur."),
    ("maintenance", "Comment ajouter et suivre mon ordinateur ?", "Dans Mes ordinateurs, choisissez Ajouter un PC. Renseignez les caractéristiques disponibles : marque, modèle, système, RAM et stockage. Ouvrez ensuite sa fiche pour consulter ses entretiens et les interventions enregistrées."),
    ("maintenance", "Mon PC est lent : que vérifier en premier ?", "Redémarrez le PC, contrôlez l’espace libre du disque et fermez les applications inutilisées. Consultez les programmes lancés au démarrage et les mises à jour du système. Si le problème persiste, décrivez quand il survient dans une demande d’assistance."),
    ("maintenance", "Comment sont générées les recommandations de maintenance ?", "TECHcare analyse les caractéristiques et l’historique du PC à l’aide de règles paramétrées par l’atelier. Les conseils actifs apparaissent dans Recommandations et peuvent conduire à une prise de rendez-vous."),
    ("repair", "Comment déclarer une panne avec une photo ?", "Dans Assistance & réparation, choisissez Déclarer une panne, sélectionnez votre PC et le type de problème, puis décrivez les symptômes. Vous pouvez joindre une photo JPEG, PNG ou WebP de 5 Mo maximum. L’administration affectera un technicien qualifié."),
    ("repair", "Mon PC chauffe et le ventilateur est bruyant : que faire ?", "Posez le PC sur une surface rigide et dégagée, vérifiez que les aérations ne sont pas obstruées et arrêtez les applications très sollicitées. Si le PC s’éteint ou chauffe anormalement, éteignez-le et demandez un diagnostic. Évitez de démonter le matériel sans les compétences nécessaires."),
    ("repair", "Où échanger avec mon technicien et suivre la réparation ?", "Ouvrez le détail du rendez-vous ou de la demande de réparation. La discussion permet d’envoyer un message au technicien affecté et de retrouver ses réponses. Le diagnostic, la solution et le statut sont mis à jour sur cette même fiche. Après la clôture, les échanges restent consultables."),
    ("repair", "Que signifie le statut En attente de pièce ?", "La prise en charge attend un composant nécessaire. Le technicien renseigne la pièce attendue dans le suivi. Vous recevrez une notification lors d’une nouvelle mise à jour. Vous pouvez poser une question dans la discussion de la demande."),
    ("booking", "Comment réserver, modifier ou annuler un rendez-vous ?", "Dans Rendez-vous, choisissez votre PC, un technicien et un créneau disponible. L’atelier réserve une heure du lundi au samedi, entre 09:00 et 18:00, heure de Tunis. La modification et l’annulation sont possibles tant que le rendez-vous n’est pas en réparation. Un nouveau créneau nécessite une nouvelle confirmation."),
    ("documents", "Où télécharger mon rapport et ma facture PDF ?", "Après la clôture de l’intervention, ouvrez Rapports & factures ou le détail de la prise en charge. Les boutons Rapport PDF et Facture PDF permettent de télécharger les documents avec les caractéristiques du PC, les travaux, les pièces et les coûts en TND."),
    ("repair", "Comment évaluer la qualité de la réparation ?", "Après la clôture, ouvrez Mes évaluations ou la fiche de la prise en charge et choisissez Donner mon avis. Sélectionnez une note de 1 à 5 et ajoutez un commentaire. Une seule évaluation est acceptée par réparation ; elle est consultable par le technicien concerné et l’administration."),
]


def seed(apps, schema_editor):
    FAQItem = apps.get_model("support", "FAQItem")
    for position, (category, question, answer) in enumerate(QUESTIONS, 1):
        FAQItem.objects.using(schema_editor.connection.alias).get_or_create(question=question, defaults={"answer": answer, "category": category, "position": position * 10, "is_active": True})


class Migration(migrations.Migration):
    dependencies = [("support", "0001_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
