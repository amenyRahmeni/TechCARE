def compatibility(component, pc):
    """Explicit declared constraints only; unknown required PC data blocks use."""
    issues = []
    if component.device_type and component.device_type != pc.device_type:
        issues.append("Le type de PC ne correspond pas (portable / bureau).")
    brands = {value.strip().casefold() for value in component.compatible_brands.split(",") if value.strip()}
    if brands and pc.brand.strip().casefold() not in brands:
        issues.append("La marque du PC ne fait pas partie des marques compatibles.")
    models = {value.strip().casefold() for value in component.compatible_models.splitlines() if value.strip()}
    if models and pc.model.strip().casefold() not in models:
        issues.append("Le modèle exact du PC ne figure pas dans la liste de compatibilité.")
    for name, label in (("ram_type", "génération de RAM"), ("ram_format", "format de RAM"), ("storage_interface", "interface de stockage"), ("cpu_socket", "socket processeur")):
        expected, actual = getattr(component, name), getattr(pc, name)
        if expected and not actual:
            issues.append(f"Renseignez le champ {label} dans la fiche du PC pour vérifier la compatibilité.")
        elif expected and expected.strip().casefold() != actual.strip().casefold():
            issues.append(f"Incompatibilité : {label} ({actual} / {expected}).")
    return issues
