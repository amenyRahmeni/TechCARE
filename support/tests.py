from django.contrib.auth import get_user_model
from django.contrib.admin.models import LogEntry
from django.test import TestCase
from django.urls import reverse

from appointments.models import Technician
from .models import FAQItem


class FAQTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.client_user = User.objects.create_user("faq_client")
        cls.technician_user = User.objects.create_user("faq_technician")
        Technician.objects.create(user=cls.technician_user)
        cls.staff = User.objects.create_user("faq_admin", is_staff=True)
        cls.question = FAQItem.objects.create(question="Comment entretenir le ventilateur du PC ?", answer="Le ventilateur évacue la chaleur. Consultez l’atelier.", category="maintenance")
        cls.draft = FAQItem.objects.create(question="Question confidentielle", answer="Réponse en préparation", category="repair", is_active=False)

    def setUp(self):
        self.client.force_login(self.client_user)

    def test_published_questions_only_with_accessible_accordion(self):
        response = self.client.get(reverse("support:faq"))
        self.assertContains(response, self.question.question)
        self.assertContains(response, "<details", html=False)
        self.assertNotContains(response, self.draft.question)

    def test_search_across_question_answer_terms_and_category(self):
        response = self.client.get(reverse("support:faq"), {"q": "ventilateur chaleur", "category": "maintenance"})
        self.assertContains(response, self.question.question)
        response = self.client.get(reverse("support:faq"), {"q": "ventilateur chaleur", "category": "booking"})
        self.assertNotContains(response, self.question.question)

    def test_no_result_and_escaped_query(self):
        response = self.client.get(reverse("support:faq"), {"q": "<script>unique</script>"})
        self.assertContains(response, "Aucune réponse")
        self.assertNotContains(response, "<script>unique</script>")

    def test_technician_help_has_no_client_actions(self):
        self.client.force_login(self.technician_user)
        response = self.client.get(reverse("support:faq"))
        self.assertContains(response, "Mes réparations")
        self.assertNotContains(response, 'href="/reparations/nouvelle/"')
        self.assertNotContains(response, 'href="/rendez-vous/nouveau/"')

    def test_admin_can_create_unpublish_edit_and_delete_with_audit(self):
        self.client.force_login(self.staff)
        data = {"question": "Question à gérer", "answer": "Réponse utile", "category": "account", "position": 3, "is_active": "on"}
        self.assertRedirects(self.client.post(reverse("backoffice:faq_create"), data), reverse("backoffice:faq"))
        item = FAQItem.objects.get(question="Question à gérer")
        self.assertTrue(LogEntry.objects.filter(object_id=str(item.pk)).exists())
        data.update(answer="Réponse révisée", is_active="")
        self.assertRedirects(self.client.post(reverse("backoffice:faq_update", args=[item.pk]), data), reverse("backoffice:faq"))
        self.assertNotContains(self.client.get(reverse("support:faq")), "Question à gérer")
        self.assertContains(self.client.get(reverse("backoffice:faq")), "Question à gérer")
        self.assertEqual(self.client.get(reverse("backoffice:faq_delete", args=[item.pk])).status_code, 200)
        self.assertTrue(FAQItem.objects.filter(pk=item.pk).exists())
        self.assertRedirects(self.client.post(reverse("backoffice:faq_delete", args=[item.pk])), reverse("backoffice:faq"))
        self.assertFalse(FAQItem.objects.filter(pk=item.pk).exists())

    def test_non_admin_cannot_manage_faq(self):
        for actor in (self.client_user, self.technician_user):
            self.client.force_login(actor)
            for url in (reverse("backoffice:faq"), reverse("backoffice:faq_create"), reverse("backoffice:faq_update", args=[self.question.pk]), reverse("backoffice:faq_delete", args=[self.question.pk])):
                self.assertEqual(self.client.get(url).status_code, 403)
                self.assertEqual(self.client.post(url, {}).status_code, 403)

    def test_admin_form_validates_empty_question_and_answer(self):
        self.client.force_login(self.staff)
        response = self.client.post(reverse("backoffice:faq_create"), {"question": "  ", "answer": "  ", "category": "maintenance", "position": 1})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)

    def test_login_required(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("support:faq")).status_code, 302)
