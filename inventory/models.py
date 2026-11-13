from decimal import Decimal
import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import reverse


RAM_TYPES = [("", "Non renseigné"), ("DDR3", "DDR3"), ("DDR4", "DDR4"), ("DDR5", "DDR5"), ("LPDDR", "LPDDR soudée")]
RAM_FORMATS = [("", "Non renseigné"), ("DIMM", "DIMM — bureau"), ("SODIMM", "SO-DIMM — portable")]
INTERFACES = [("", "Non renseignée"), ("SATA", "SATA"), ("NVME", "M.2 NVMe"), ("M2SATA", "M.2 SATA")]


class Category(models.Model):
    name = models.CharField("nom", max_length=80, unique=True)
    code = models.SlugField("code", unique=True)
    description = models.CharField("description", max_length=250, blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "catégorie de composants"

    def __str__(self):
        return self.name


class SparePart(models.Model):
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="parts", verbose_name="catégorie")
    reference = models.CharField("référence", max_length=60, unique=True)
    name = models.CharField("nom", max_length=150)
    brand = models.CharField("marque", max_length=60)
    description = models.TextField("description", max_length=2000, blank=True)
    unit_price = models.DecimalField("prix unitaire (TND)", max_digits=10, decimal_places=3, validators=[MinValueValidator(0)])
    stock = models.PositiveIntegerField("stock", default=0, validators=[MaxValueValidator(100000)], editable=False)
    low_stock_threshold = models.PositiveIntegerField("seuil d’alerte", default=3, validators=[MaxValueValidator(100000)])
    is_active = models.BooleanField("visible au catalogue", default=True)
    device_type = models.CharField("type de PC compatible", max_length=10, choices=[("", "Portable et bureau"), ("laptop", "Portable"), ("desktop", "Bureau")], blank=True)
    compatible_brands = models.CharField("marques compatibles", max_length=500, blank=True, help_text="Marques séparées par des virgules. Vide : toutes les marques.")
    compatible_models = models.TextField("modèles compatibles", max_length=2000, blank=True, help_text="Un modèle exact par ligne. Vide : aucune restriction de modèle.")
    ram_type = models.CharField("génération RAM requise", max_length=8, choices=RAM_TYPES, blank=True)
    ram_format = models.CharField("format RAM requis", max_length=8, choices=RAM_FORMATS, blank=True)
    storage_interface = models.CharField("interface de stockage requise", max_length=8, choices=INTERFACES, blank=True)
    cpu_socket = models.CharField("socket processeur requis", max_length=50, blank=True)
    compatibility_notes = models.CharField("précisions de compatibilité", max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "pk"]
        verbose_name = "composant"
        constraints = [models.CheckConstraint(condition=models.Q(stock__gte=0) & models.Q(stock__lte=100000), name="component_stock_bounds")]

    def __str__(self):
        return f"{self.name} · {self.reference}"

    def get_absolute_url(self):
        return reverse("inventory:detail", args=[self.pk])


class ComponentUsage(models.Model):
    component = models.ForeignKey(SparePart, on_delete=models.PROTECT, related_name="usages")
    repair = models.ForeignKey("repairs.RepairRequest", on_delete=models.PROTECT, null=True, blank=True, related_name="component_usages")
    appointment = models.ForeignKey("appointments.Appointment", on_delete=models.PROTECT, null=True, blank=True, related_name="component_usages")
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1), MaxValueValidator(1000)])
    unit_price = models.DecimalField(max_digits=10, decimal_places=3)
    name_snapshot = models.CharField(max_length=220)
    used_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    token = models.UUIDField(default=uuid.uuid4, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    returned_at = models.DateTimeField(null=True, blank=True)
    return_reason = models.CharField(max_length=250, blank=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = "utilisation de composant"
        constraints = [models.CheckConstraint(condition=(models.Q(repair__isnull=False, appointment__isnull=True) | models.Q(repair__isnull=True, appointment__isnull=False)), name="usage_exactly_one_target")]

    @property
    def total(self):
        return self.unit_price * self.quantity


class StockMovement(models.Model):
    class Kind(models.TextChoices):
        ENTRY = "entry", "Entrée / ajustement"
        USE = "use", "Utilisation"
        RETURN = "return", "Retour"

    component = models.ForeignKey(SparePart, on_delete=models.PROTECT, related_name="movements")
    kind = models.CharField(max_length=8, choices=Kind.choices)
    delta = models.IntegerField("variation")
    stock_after = models.PositiveIntegerField("stock après mouvement")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    usage = models.ForeignKey(ComponentUsage, on_delete=models.PROTECT, null=True, blank=True, related_name="movements")
    reason = models.CharField("motif", max_length=250)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = "mouvement de stock"
        constraints = [models.CheckConstraint(condition=~models.Q(delta=0), name="stock_delta_nonzero"), models.UniqueConstraint(fields=["usage", "kind"], name="unique_usage_stock_action")]


def listing_photo_path(instance, filename):
    return f"component-listings/{uuid.uuid4().hex}.jpg"


class ComponentListing(models.Model):
    class Condition(models.TextChoices):
        NEW = "new", "Neuf"
        LIKE_NEW = "like_new", "Comme neuf"
        USED = "used", "Occasion"
        REFURBISHED = "refurbished", "Reconditionné"

    class Status(models.TextChoices):
        DRAFT = "draft", "Brouillon"
        PUBLISHED = "published", "Disponible"
        SOLD = "sold", "Vendu"
        WITHDRAWN = "withdrawn", "Retiré"

    seller = models.ForeignKey("appointments.Technician", on_delete=models.PROTECT, related_name="component_listings", verbose_name="technicien vendeur")
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="listings", verbose_name="catégorie")
    title = models.CharField("titre de l’annonce", max_length=150)
    brand = models.CharField("marque", max_length=60)
    reference = models.CharField("modèle / référence", max_length=80, blank=True)
    description = models.TextField("description", max_length=3000)
    condition = models.CharField("état du composant", max_length=12, choices=Condition.choices, default=Condition.USED)
    unit_price = models.DecimalField("prix unitaire (TND)", max_digits=10, decimal_places=3, validators=[MinValueValidator(0)])
    quantity = models.PositiveIntegerField("quantité proposée", default=1, validators=[MinValueValidator(1), MaxValueValidator(100000)])
    compatibility_notes = models.CharField("compatibilité / précisions", max_length=500, blank=True)
    location = models.CharField("ville / lieu de remise", max_length=150)
    contact_phone = models.CharField("téléphone de contact", max_length=30, blank=True)
    contact_email = models.EmailField("e-mail de contact", blank=True)
    photo = models.ImageField("photo du composant", upload_to=listing_photo_path, blank=True)
    status = models.CharField("statut", max_length=12, choices=Status.choices, default=Status.PUBLISHED, db_index=True)
    submission_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = "annonce de composant"
        indexes = [models.Index(fields=["seller", "status"], name="listing_seller_status_idx")]
        constraints = [models.CheckConstraint(condition=models.Q(quantity__gte=1) & models.Q(quantity__lte=100000), name="listing_quantity_bounds")]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("inventory:listing_detail", args=[self.pk])

    @property
    def seller_name(self):
        return self.seller.user.get_full_name() or self.seller.user.username

    @property
    def phone_link(self):
        import re
        return "tel:" + re.sub(r"[^+0-9]", "", self.contact_phone)

    def clean(self):
        import re
        from django.core.exceptions import ValidationError
        super().clean()
        if not self.contact_phone.strip() and not self.contact_email.strip():
            raise ValidationError("Indiquez un téléphone ou un e-mail de contact.")
        if self.contact_phone and (not re.fullmatch(r"\+?[0-9 ()-]+", self.contact_phone) or len(re.sub(r"[^0-9]", "", self.contact_phone)) < 6):
            raise ValidationError({"contact_phone": "Indiquez un téléphone valide."})
