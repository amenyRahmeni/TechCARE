from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
import uuid

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import close_old_connections, connection, transaction
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse

from appointments.models import Invoice, PartLine, Technician
from appointments.services import book_appointment, cancel_appointment, save_intervention, update_status
from appointments.tests import future_start, make_pc
from notifications.models import Notification
from repairs.models import RepairRequest
from repairs.services import assign_technician, change_status, create_request, save_report
from .compatibility import compatibility
from .models import Category, ComponentUsage, SparePart, StockMovement
from .services import adjust_stock, return_component, use_component


class InventoryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.owner = User.objects.create_user("stock_client")
        cls.other = User.objects.create_user("stock_other")
        cls.admin = User.objects.create_user("stock_admin", is_staff=True)
        cls.tech_user = User.objects.create_user("stock_tech")
        cls.tech = Technician.objects.create(user=cls.tech_user)
        cls.pc = make_pc(cls.owner)
        cls.pc.ram_type, cls.pc.ram_format = "DDR4", "SODIMM"
        cls.pc.save()
        cls.part = SparePart.objects.create(category=Category.objects.get(code="ram"), reference="DDR4-8", name="RAM 8 Go", brand="Crucial", unit_price="30.125", stock=5, ram_type="DDR4", ram_format="SODIMM", device_type="laptop")

    def repair(self):
        repair = create_request(self.owner, {"pc": self.pc, "technician": self.tech, "problem": "memory", "description": "La mémoire ne fonctionne plus.", "technical_notes": ""})
        assign_technician(self.owner, repair.pk, self.tech.pk)
        return change_status(self.tech_user, repair.pk, "diagnosis")

    def use(self, repair, **changes):
        data = {"component_id": self.part.pk, "quantity": 2, "token": uuid.uuid4(), "repair_id": repair.pk}
        data.update(changes)
        return use_component(self.tech_user, **data)

    def test_compatibility_checks_type_brand_model_and_technical_data(self):
        self.assertEqual(compatibility(self.part, self.pc), [])
        for field, value in [("device_type", "desktop"), ("compatible_brands", "HP, Lenovo"), ("compatible_models", "Autre modèle"), ("ram_type", "DDR5"), ("ram_format", "DIMM"), ("storage_interface", "NVME"), ("cpu_socket", "AM5")]:
            part = SparePart.objects.get(pk=self.part.pk)
            setattr(part, field, value)
            self.assertTrue(compatibility(part, self.pc), field)
        self.pc.ram_type = ""
        self.assertIn("Renseignez", compatibility(self.part, self.pc)[0])

    def test_usage_decrements_stock_freezes_price_and_creates_movement(self):
        usage = self.use(self.repair())
        self.part.refresh_from_db()
        self.assertEqual(self.part.stock, 3)
        self.assertEqual(usage.total, Decimal("60.250"))
        movement = StockMovement.objects.get(usage=usage)
        self.assertEqual((movement.delta, movement.stock_after), (-2, 3))
        self.assertTrue(Notification.objects.filter(component=self.part, recipient=self.admin).exists())

    def test_duplicate_validation_does_not_consume_twice(self):
        repair = self.repair()
        token = uuid.uuid4()
        first = self.use(repair, token=token)
        second = self.use(repair, token=token)
        self.assertEqual(first.pk, second.pk)
        self.part.refresh_from_db()
        self.assertEqual(self.part.stock, 3)
        self.assertEqual(StockMovement.objects.filter(usage=first).count(), 1)
        with self.assertRaises(ValidationError):
            self.use(repair, token=token, quantity=1)

    def test_insufficient_incompatible_inactive_or_invalid_quantity_changes_nothing(self):
        repair = self.repair()
        for quantity in (0, -1, 6, 1001):
            with self.assertRaises(ValidationError):
                self.use(repair, quantity=quantity)
        self.part.ram_type = "DDR5"
        self.part.save()
        with self.assertRaises(ValidationError):
            self.use(repair)
        self.part.ram_type, self.part.is_active = "DDR4", False
        self.part.save()
        with self.assertRaises(ValidationError):
            self.use(repair)
        self.part.refresh_from_db()
        self.assertEqual(self.part.stock, 5)
        self.assertEqual(ComponentUsage.objects.count(), 0)

    def test_client_cannot_consume_or_adjust_stock(self):
        repair = self.repair()
        with self.assertRaises(PermissionDenied):
            use_component(self.owner, component_id=self.part.pk, quantity=1, repair_id=repair.pk, token=uuid.uuid4())
        with self.assertRaises(PermissionDenied):
            adjust_stock(self.tech_user, self.part.pk, 2, "Livraison")
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(reverse("inventory:consume"), {}).status_code, 403)
        self.assertEqual(self.client.get(reverse("inventory:movements")).status_code, 403)

    def test_adjustment_requires_reason_and_preserves_nonnegative_stock(self):
        movement = adjust_stock(self.admin, self.part.pk, 10, "Réception fournisseur")
        self.assertEqual(movement.stock_after, 15)
        for delta, reason in [(0, "Correction"), (-16, "Correction"), (100000, "Correction"), (2, "")]:
            with self.assertRaises(ValidationError):
                adjust_stock(self.admin, self.part.pk, delta, reason)
        self.part.refresh_from_db()
        self.assertEqual(self.part.stock, 15)

    def test_return_is_traced_and_idempotent(self):
        repair = self.repair()
        usage = self.use(repair)
        return_component(self.tech_user, usage.pk, "Pièce non installée")
        return_component(self.tech_user, usage.pk, "Même validation")
        self.part.refresh_from_db()
        self.assertEqual(self.part.stock, 5)
        self.assertEqual(StockMovement.objects.filter(usage=usage).count(), 2)
        self.assertEqual(repair.parts_total, Decimal("0.000"))

    def test_cancelled_repair_returns_components_once(self):
        repair = self.repair()
        usage = self.use(repair)
        change_status(self.tech_user, repair.pk, "cancelled")
        change_status(self.tech_user, repair.pk, "cancelled")
        self.part.refresh_from_db()
        usage.refresh_from_db()
        self.assertEqual(self.part.stock, 5)
        self.assertIsNotNone(usage.returned_at)

    def test_resolved_repair_cannot_return_or_consume_components(self):
        repair = self.repair()
        usage = self.use(repair)
        self.part.unit_price = Decimal("99.999")
        self.part.save()
        save_report(self.tech_user, repair.pk, {"diagnosis": "Mémoire défectueuse", "solution": "Remplacée", "labour_cost": Decimal("10.000")}, resolve=True)
        self.assertEqual(Invoice.objects.get(repair=repair).total_amount, Decimal("70.250"))
        with self.assertRaises(ValidationError):
            return_component(self.tech_user, usage.pk, "Après clôture")
        with self.assertRaises(ValidationError):
            self.use(repair)

    def test_appointment_manual_save_preserves_stock_lines_and_includes_in_invoice(self):
        appointment = book_appointment(self.owner, {"pc": self.pc, "technician": self.tech, "starts_at": future_start(), "category": "hardware", "reason": "RAM", "description": ""})
        update_status(self.tech_user, appointment.pk, "confirmed")
        update_status(self.tech_user, appointment.pk, "diagnosis")
        usage = use_component(self.tech_user, component_id=self.part.pk, quantity=1, appointment_id=appointment.pk, token=uuid.uuid4())
        data = {"diagnosis": "Mémoire usée", "solution": "Remplacement", "labour_cost": Decimal("9.125")}
        save_intervention(self.tech_user, appointment.pk, data, [{"name": "Nettoyage", "quantity": 1, "unit_price": Decimal("5.000")}])
        self.assertEqual(PartLine.objects.filter(intervention=appointment.intervention).count(), 2)
        self.client.force_login(self.tech_user)
        response = self.client.get(appointment.get_absolute_url())
        self.assertContains(response, "RAM 8 Go")
        self.assertEqual(list(response.context["parts_formset"].queryset.values_list("name", flat=True)), ["Nettoyage"])
        save_intervention(self.tech_user, appointment.pk, data, [{"name": "Nettoyage", "quantity": 1, "unit_price": Decimal("5.000")}], complete=True)
        self.assertEqual(Invoice.objects.get(intervention=appointment.intervention).total_amount, Decimal("44.250"))
        self.assertTrue(PartLine.objects.filter(stock_usage=usage).exists())

    def test_appointment_cancellation_returns_components(self):
        appointment = book_appointment(self.owner, {"pc": self.pc, "technician": self.tech, "starts_at": future_start(), "category": "hardware", "reason": "RAM", "description": ""})
        update_status(self.tech_user, appointment.pk, "confirmed")
        update_status(self.tech_user, appointment.pk, "diagnosis")
        use_component(self.tech_user, component_id=self.part.pk, quantity=1, appointment_id=appointment.pk, token=uuid.uuid4())
        cancel_appointment(self.owner, appointment.pk)
        self.part.refresh_from_db()
        self.assertEqual(self.part.stock, 5)
        self.assertFalse(PartLine.objects.filter(stock_usage__isnull=False).exists())

    def test_outer_rollback_restores_stock_usage_movements_and_notifications(self):
        repair = self.repair()
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                self.use(repair)
                raise RuntimeError("Abort")
        self.part.refresh_from_db()
        self.assertEqual(self.part.stock, 5)
        self.assertEqual(ComponentUsage.objects.count(), 0)
        self.assertFalse(Notification.objects.filter(component=self.part).exists())

    def test_catalog_filters_compatibility_permissions_and_history(self):
        self.repair()
        self.client.force_login(self.tech_user)
        self.assertContains(self.client.get(reverse("inventory:stock_catalog") + "?category=ram&brand=Crucial&min_price=30&max_price=31&availability=available"), self.part.reference)
        self.assertNotContains(self.client.get(reverse("inventory:stock_catalog") + "?max_price=2"), self.part.reference)
        self.assertContains(self.client.get(reverse("inventory:stock_catalog") + "?min_price=NaN"), "prix positif valide")
        self.assertContains(self.client.get(self.part.get_absolute_url() + f"?pc={self.pc.pk}"), "Compatible selon les critères renseignés")
        other_pc = make_pc(self.other)
        self.assertEqual(self.client.get(self.part.get_absolute_url() + f"?pc={other_pc.pk}").status_code, 404)
        self.part.is_active = False
        self.part.save()
        self.assertEqual(self.client.get(self.part.get_absolute_url()).status_code, 404)

    def test_staff_component_category_stock_forms_and_csrf(self):
        self.client.force_login(self.admin)
        for route, args in [("components", []), ("component_create", []), ("component_detail", [self.part.pk]), ("component_update", [self.part.pk]), ("categories", []), ("stock", [])]:
            self.assertEqual(self.client.get(reverse(f"backoffice:{route}", args=args)).status_code, 200, route)
        payload = {"category": self.part.category_id, "reference": "NEW-SSD", "name": "SSD neuf", "brand": "Kingston", "unit_price": "80.125", "low_stock_threshold": 2, "is_active": "on", "opening_stock": 10}
        result = self.client.post(reverse("backoffice:component_create"), payload)
        self.assertEqual(result.status_code, 302)
        new = SparePart.objects.get(reference="NEW-SSD")
        self.assertEqual(new.stock, 10)
        self.assertEqual(new.movements.get().delta, 10)
        self.client.post(reverse("backoffice:stock_adjust", args=[new.pk]), {"delta": -2, "reason": "Correction"})
        new.refresh_from_db()
        self.assertEqual(new.stock, 8)
        secure = Client(enforce_csrf_checks=True)
        secure.force_login(self.admin)
        self.assertEqual(secure.post(reverse("backoffice:stock_adjust", args=[new.pk]), {"delta": 5, "reason": "Sans CSRF"}).status_code, 403)


class ConcurrentStockTests(TransactionTestCase):
    def test_two_technicians_cannot_consume_the_same_last_unit(self):
        User = get_user_model()
        part = SparePart.objects.create(category=Category.objects.create(name="Concurrent", code="concurrent"), reference="LAST-UNIT", name="Dernière pièce", brand="Test", unit_price="1.000", stock=1)
        targets, actors = [], []
        for index in range(2):
            owner = User.objects.create_user(f"race_owner_{index}")
            actor = User.objects.create_user(f"race_tech_{index}")
            tech = Technician.objects.create(user=actor)
            targets.append(RepairRequest.objects.create(client=owner, pc=make_pc(owner), technician=tech, problem="other", description="Panne", status="diagnosis"))
            actors.append(actor)
        barrier = Barrier(2)

        def attempt(index):
            close_old_connections()
            try:
                barrier.wait(timeout=5)
                use_component(actors[index], component_id=part.pk, quantity=1, repair_id=targets[index].pk, token=uuid.uuid4())
                return "used"
            except ValidationError:
                return "insufficient"
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(attempt, range(2)))
        self.assertCountEqual(results, ["used", "insufficient"])
        part.refresh_from_db()
        self.assertEqual(part.stock, 0)
        self.assertEqual(ComponentUsage.objects.filter(component=part).count(), 1)
