from datetime import timedelta
from io import StringIO
import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from appointments.models import Appointment, Technician
from appointments.tests import future_start, make_pc
from maintenance.models import MaintenanceRecord, PC
from .dataset import HEADERS, TARGET, demo_rows, read_csv, write_csv
from .engine import predict_score, risk_level
from .features import FEATURES, extract_features, validate_features
from .models import FailureModel, FailurePrediction
from .learning import evaluate, fit_forest, group_split
from .services import analyze_pc, context_for_pc, current_model
from .training import train_model


def csv_bytes(rows):
    stream = StringIO()
    write_csv(rows, stream)
    return stream.getvalue().encode("utf-8")


class MLDataAndEngineTests(SimpleTestCase):
    def test_demo_is_reproducible_and_roundtrips_through_csv(self):
        rows = demo_rows(300, seed=42)
        self.assertEqual(rows, demo_rows(300, seed=42))
        self.assertNotEqual(rows, demo_rows(300, seed=43))
        self.assertEqual(read_csv(csv_bytes(rows)), rows)
        self.assertEqual({row["data_origin"] for row in rows}, {"simulated"})

    def test_forest_learns_labeled_relation_and_preserves_scores_in_json(self):
        values = {name: demo_rows(100)[0][name] for name in FEATURES}
        values.update(pc_age_days=365, maintenance_count=1, repair_count=0, repairs_last_365d=0,
                      preventive_last_365d=1, days_since_last_maintenance=30)
        examples = [{**values, "ram_gb": ram} for ram in ([4] * 100 + [32] * 100)]
        forest, importance = fit_forest([[item[name] for name in FEATURES] for item in examples], [0] * 100 + [1] * 100, n_estimators=12, min_samples_leaf=5)
        reloaded = json.loads(json.dumps(forest))
        self.assertLess(predict_score(reloaded, {**values, "ram_gb": 8}), .1)
        self.assertGreater(predict_score(reloaded, {**values, "ram_gb": 24}), .9)
        self.assertAlmostEqual(sum(importance), 1)
        self.assertEqual(predict_score(forest, examples[0]), predict_score(reloaded, examples[0]))

    def test_evaluation_handles_ties_and_known_perfect_or_reversed_predictions(self):
        perfect = evaluate([0, 0, 1, 1], [0, 0, 1, 1], .5)
        self.assertEqual((perfect["roc_auc"], perfect["brier_score"], perfect["accuracy"]), (1, 0, 1))
        self.assertEqual(evaluate([0, 1], [.5, .5], .5)["roc_auc"], .5)
        self.assertEqual(evaluate([0, 1], [1, 0], .5)["roc_auc"], 0)

    def test_training_partition_does_not_share_a_machine(self):
        rows = demo_rows(100)
        rows += [{**row, "observed_on": "2025-02-01"} for row in rows]
        train, test = group_split(rows, TARGET)
        self.assertFalse({rows[i]["machine_id"] for i in train} & {rows[i]["machine_id"] for i in test})

    def test_risk_threshold_boundaries(self):
        for score, level in [(0, "low"), (.2499, "low"), (.25, "medium"), (.5999, "medium"), (.6, "high"), (1, "high")]:
            self.assertEqual(risk_level(score), level)
        for value in (-1, 2, float("nan")):
            with self.assertRaises(ValidationError):
                risk_level(value)

    def test_unknown_model_schema_and_invalid_features_are_rejected(self):
        values = {name: demo_rows(100)[0][name] for name in FEATURES}
        with self.assertRaises(ValidationError):
            predict_score({"schema_version": 9}, values)
        values["ram_gb"] = 0
        with self.assertRaises(ValidationError):
            validate_features(values)

    def test_csv_rejects_wrong_headers_corruption_and_oversize(self):
        for content in (b"email,password\na,b\n", b"\xff\xfe", b"x" * (5 * 1024 * 1024 + 1)):
            with self.assertRaises(ValidationError):
                read_csv(content)

    def test_csv_rejects_duplicate_observation_mixed_origin_and_bad_outcome(self):
        rows = demo_rows(100)
        with self.assertRaises(ValidationError):
            read_csv(csv_bytes([*rows, rows[0]]))
        rows[0]["data_origin"] = "real"
        rows[0]["machine_id"] = "real-machine-1"
        with self.assertRaises(ValidationError):
            read_csv(csv_bytes(rows))
        rows[0]["data_origin"] = "simulated"
        rows[0][TARGET] = 3
        with self.assertRaises(ValidationError):
            read_csv(csv_bytes(rows))

    def test_real_rows_require_complete_ninety_day_outcomes(self):
        rows = demo_rows(100)
        for row in rows:
            row["data_origin"] = "real"
            row["machine_id"] = row["machine_id"].replace("demo-", "machine-")
            row["observed_on"] = str(timezone.localdate() - timedelta(days=90))
        self.assertEqual(read_csv(csv_bytes(rows)), rows)
        rows[0]["observed_on"] = str(timezone.localdate() - timedelta(days=89))
        with self.assertRaises(ValidationError):
            read_csv(csv_bytes(rows))

    def test_inconsistent_history_counts_are_rejected(self):
        values = {name: demo_rows(100)[0][name] for name in FEATURES}
        values.update(maintenance_count=1, repair_count=2)
        with self.assertRaises(ValidationError):
            validate_features(values)


class PredictionWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.owner = User.objects.create_user("ml_client")
        cls.other = User.objects.create_user("ml_other")
        cls.tech_user = User.objects.create_user("ml_technician")
        cls.other_tech_user = User.objects.create_user("ml_other_technician")
        cls.staff = User.objects.create_user("ml_admin", is_staff=True)
        cls.tech = Technician.objects.create(user=cls.tech_user)
        cls.other_tech = Technician.objects.create(user=cls.other_tech_user)
        cls.pc = make_pc(cls.owner, "PC pour prédiction")
        cls.appointment = Appointment.objects.create(client=cls.owner, technician=cls.tech, pc=cls.pc, starts_at=future_start(), reason="PC assigné pour analyse")
        cls.model = train_model(demo_rows(400), cls.staff)

    def setUp(self):
        self.client.force_login(self.owner)

    def test_training_saves_real_forest_metrics_and_group_separation(self):
        self.assertTrue(self.model.is_demo)
        self.assertEqual(len(self.model.forest["trees"]), 80)
        self.assertEqual(self.model.train_count + self.model.test_count, 400)
        self.assertEqual(self.model.metrics["group_overlap_count"], 0)
        self.assertEqual(self.model.metrics["train_machine_count"] + self.model.metrics["test_machine_count"], 400)
        self.assertEqual(sum(sum(row) for row in self.model.metrics["confusion_matrix"]), self.model.test_count)
        self.assertEqual(PC.objects.count(), 1)
        self.assertEqual(MaintenanceRecord.objects.count(), 0)

    def test_repeated_machine_snapshots_stay_in_a_single_partition(self):
        rows = demo_rows(200)
        repeated = []
        for row in rows:
            repeated.extend([row, {**row, "observed_on": "2025-02-01"}])
        model = train_model(repeated)
        self.assertEqual(model.train_count, model.metrics["train_machine_count"] * 2)
        self.assertEqual(model.test_count, model.metrics["test_machine_count"] * 2)
        self.assertEqual(model.metrics["group_overlap_count"], 0)

    def test_training_rejects_small_or_single_class_datasets_without_switching_model(self):
        for rows in (demo_rows(100)[:10], [{**row, TARGET: 0} for row in demo_rows(100)]):
            with self.assertRaises(ValidationError):
                train_model(rows)
        self.assertEqual(current_model().pk, self.model.pk)

    def test_features_preserve_unknown_age_and_use_only_past_history(self):
        self.pc.purchased_on = None
        self.pc.save(update_fields=["purchased_on"])
        MaintenanceRecord.objects.create(pc=self.pc, title="Panne résolue", kind="repair", description="Test", completed_on=timezone.localdate() - timedelta(days=15))
        MaintenanceRecord.objects.create(pc=self.pc, title="Donnée future exclue", kind="repair", description="Test", completed_on=timezone.localdate() + timedelta(days=3))
        values = extract_features(self.pc)
        self.assertEqual(values["pc_age_days"], -1)
        self.assertEqual(values["repair_count"], 1)
        self.assertEqual(values["repairs_last_365d"], 1)
        self.assertEqual(values["days_since_last_maintenance"], 15)

    def test_no_history_is_not_invented_as_recent_maintenance(self):
        values = extract_features(self.pc)
        self.assertEqual(values["maintenance_count"], 0)
        self.assertEqual(values["days_since_last_maintenance"], -1)
        self.assertIn("Aucun entretien enregistré", context_for_pc(self.pc)["missing_features"][0])

    def test_prediction_is_model_based_and_idempotent(self):
        result = analyze_pc(self.owner, self.pc.pk)
        self.assertEqual(result.model_id, self.model.pk)
        self.assertAlmostEqual(result.score, predict_score(self.model.forest, extract_features(self.pc)), places=12)
        self.assertEqual(result.level, risk_level(result.score))
        self.assertEqual(analyze_pc(self.owner, self.pc.pk).pk, result.pk)
        self.assertEqual(FailurePrediction.objects.count(), 1)

    def test_only_owner_assigned_technician_and_admin_can_analyze(self):
        for actor in (self.owner, self.tech_user, self.staff):
            self.assertEqual(analyze_pc(actor, self.pc.pk).pc_id, self.pc.pk)
        for actor in (self.other, self.other_tech_user):
            with self.assertRaises(PermissionDenied):
                analyze_pc(actor, self.pc.pk)

    def test_direct_urls_and_dashboard_respect_pc_permissions(self):
        detail = reverse("predictions:detail", args=[self.pc.pk])
        analyze = reverse("predictions:analyze", args=[self.pc.pk])
        for actor in (self.other, self.other_tech_user):
            self.client.force_login(actor)
            self.assertEqual(self.client.get(detail).status_code, 404)
            self.assertEqual(self.client.post(analyze).status_code, 404)
            self.assertNotContains(self.client.get(reverse("predictions:dashboard")), self.pc.name)

    def test_reassignment_revokes_old_technician_access(self):
        Appointment.objects.filter(pk=self.appointment.pk).update(technician=self.other_tech)
        with self.assertRaises(PermissionDenied):
            analyze_pc(self.tech_user, self.pc.pk)
        self.assertEqual(analyze_pc(self.other_tech_user, self.pc.pk).pc_id, self.pc.pk)

    def test_get_does_not_create_prediction_and_post_ignores_injected_features(self):
        url = reverse("predictions:detail", args=[self.pc.pk])
        self.assertContains(self.client.get(url), "DÉMONSTRATION")
        self.assertEqual(FailurePrediction.objects.count(), 0)
        response = self.client.post(reverse("predictions:analyze", args=[self.pc.pk]), {"ram_gb": 1, "score": 1, "level": "high"})
        self.assertRedirects(response, url)
        self.assertEqual(FailurePrediction.objects.get().features["ram_gb"], self.pc.ram_gb)

    def test_missing_model_is_handled_without_a_fake_prediction(self):
        FailureModel.objects.all().delete()
        with self.assertRaises(ValidationError):
            analyze_pc(self.owner, self.pc.pk)
        self.assertContains(self.client.get(reverse("predictions:detail", args=[self.pc.pk])), "Aucun modèle")
        self.assertFalse(FailurePrediction.objects.exists())

    def test_snapshot_is_preserved_and_changed_features_mark_old_prediction_stale(self):
        original = analyze_pc(self.owner, self.pc.pk)
        self.pc.ram_gb = 32
        self.pc.save(update_fields=["ram_gb"])
        self.assertTrue(context_for_pc(self.pc)["prediction_stale"])
        updated = analyze_pc(self.owner, self.pc.pk)
        self.assertNotEqual(updated.pk, original.pk)
        original.refresh_from_db()
        self.assertEqual(original.features["ram_gb"], 16)
        self.assertFalse(context_for_pc(self.pc)["prediction_stale"])

    def test_next_day_and_new_model_mark_prediction_stale(self):
        analyze_pc(self.owner, self.pc.pk)
        tomorrow = timezone.localdate() + timedelta(days=1)
        with patch("predictions.features.timezone.localdate", return_value=tomorrow):
            self.assertTrue(context_for_pc(self.pc)["prediction_stale"])
        train_model(demo_rows(200), self.staff)
        self.assertTrue(context_for_pc(self.pc)["prediction_stale"])

    def test_ml_endpoints_require_login_post_and_csrf(self):
        url = reverse("predictions:analyze", args=[self.pc.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.owner)
        self.assertEqual(csrf_client.post(url).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("predictions:dashboard")).status_code, 302)

    def test_csv_training_is_admin_only(self):
        for actor in (self.owner, self.tech_user):
            self.client.force_login(actor)
            for url in (reverse("backoffice:ml_model"), reverse("backoffice:ml_template")):
                self.assertEqual(self.client.get(url).status_code, 403)
                self.assertEqual(self.client.post(url).status_code, 403)

    def test_admin_csv_training_persists_a_new_version_without_business_records(self):
        self.client.force_login(self.staff)
        file = SimpleUploadedFile("observations.csv", csv_bytes(demo_rows(200)), content_type="text/csv")
        response = self.client.post(reverse("backoffice:ml_model"), {"action": "csv", "dataset": file})
        self.assertRedirects(response, reverse("backoffice:ml_model"))
        self.assertEqual(FailureModel.objects.count(), 2)
        self.assertTrue(current_model().is_demo)
        self.assertEqual(PC.objects.count(), 1)
        self.assertFalse(MaintenanceRecord.objects.exists())

    def test_invalid_csv_preserves_current_model_and_shows_error(self):
        self.client.force_login(self.staff)
        file = SimpleUploadedFile("invalid.csv", b"bad\nwrong\n", content_type="text/csv")
        response = self.client.post(reverse("backoffice:ml_model"), {"action": "csv", "dataset": file})
        self.assertContains(response, "Colonnes CSV incorrectes")
        self.assertEqual(current_model().pk, self.model.pk)

    def test_model_management_and_template_download(self):
        self.client.force_login(self.staff)
        self.assertContains(self.client.get(reverse("backoffice:ml_model")), "ROC-AUC")
        response = self.client.get(reverse("backoffice:ml_template"))
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertEqual(response.content.decode().strip().split(","), list(HEADERS))

    def test_model_score_database_constraint(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            FailurePrediction.objects.create(pc=self.pc, model=self.model, features={}, input_fingerprint="bad", score=1.5, level="high")

    def test_pc_details_include_the_ml_panel_for_all_authorized_roles(self):
        for actor in (self.owner, self.tech_user, self.staff):
            self.client.force_login(actor)
            url = reverse("backoffice:pc_detail", args=[self.pc.pk]) if actor.is_staff else self.pc.get_absolute_url()
            self.assertContains(self.client.get(url), "Prédiction des pannes informatiques")
